"""
Pure timing/arithmetic core for the GIL-release spike (SPIKE-01, SPIKE-02).

This module is deliberately ADBC-free: it imports no `adbc_poolhouse`, no
`create_pool`, and no driver. Every function operates on plain floats or on a
caller-supplied `call`, so the arithmetic is unit-testable without a database,
a connection pool, or any wall-clock assertion.

The headline figure is a speedup ratio bounded by two reference points:

- `speedup == N` means the work parallelized fully (the GIL was released).
- `speedup == 1` means the work serialized (the GIL was re-held).

The concurrency primitive ([`concurrent_wall`][benchmarks._harness.concurrent_wall])
uses raw threads only (`threading.Barrier` + `ThreadPoolExecutor`); it never uses
anyio or any async machinery.
"""

from __future__ import annotations

import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

_Conn = TypeVar("_Conn")


def median(values: Iterable[float]) -> float:
    """
    Return the median of `values`.

    Thin wrapper over `statistics.median`, kept as the single aggregator so the
    benchmark and its tests agree on the central-tendency definition.

    Args:
        values: An iterable of timing samples in seconds.

    Returns:
        The median of `values` as a float.
    """
    return statistics.median(values)


def speedup(single: float, wall: float, n: int) -> float:
    """
    Compute the concurrent speedup ratio.

    The ratio is `(n * single) / wall`. With ideal-parallel timings
    (`wall == single`) it equals `n`; with full-serial timings
    (`wall == n * single`) it equals `1.0`.

    Args:
        single: Median single-call time in seconds (1 thread).
        wall: Median concurrent wall-clock time in seconds (n threads).
        n: Number of concurrent calls.

    Returns:
        The speedup ratio, bounded by `1.0` (serial) and `n` (ideal parallel).

    Raises:
        ValueError: If `wall <= 0.0`. A non-positive wall-clock means the query
            finished below the timer's resolution, so the ratio is undefined; the
            fix is to time more work (e.g. increase `--rows`) rather than report a
            bogus number or crash with a bare `ZeroDivisionError`.
    """
    if wall <= 0.0:
        msg = (
            f"wall must be > 0 (got {wall}); query finished below timer "
            "resolution -- increase --rows so the concurrent phase is timeable"
        )
        raise ValueError(msg)
    return (n * single) / wall


def parallel_efficiency(single: float, wall: float, n: int) -> float:
    """
    Compute the parallel efficiency `speedup / n`.

    Args:
        single: Median single-call time in seconds (1 thread).
        wall: Median concurrent wall-clock time in seconds (n threads).
        n: Number of concurrent calls.

    Returns:
        The fraction of ideal parallelism achieved: `1.0` for ideal,
        `1 / n` for full serialization.
    """
    return speedup(single, wall, n) / n


def report(single: float, wall: float, n: int) -> dict[str, float]:
    """
    Build the six-key result dict for one measurement.

    Args:
        single: Median single-call time in seconds (1 thread).
        wall: Median concurrent wall-clock time in seconds (n threads).
        n: Number of concurrent calls.

    Returns:
        A dict with keys `single_call_s`, `wall_s`, `ideal_parallel_s`
        (the lower bound, equal to `single`), `full_serial_s` (the upper bound,
        equal to `n * single`), `speedup_x`, and `parallel_efficiency`.
    """
    return {
        "single_call_s": single,
        "wall_s": wall,
        "ideal_parallel_s": single,
        "full_serial_s": n * single,
        "speedup_x": speedup(single, wall, n),
        "parallel_efficiency": parallel_efficiency(single, wall, n),
    }


def concurrent_wall(
    call: Callable[[_Conn], float],
    conns: Sequence[_Conn],
    n: int,
    trials: int,
) -> float:
    """
    Measure the median wall-clock time of `n` barrier-gated concurrent calls.

    Each trial spins up a `ThreadPoolExecutor(max_workers=n)` and gates every
    worker on a `threading.Barrier(n)` so all calls start together; staggered
    starts would understate parallelism. The timed region wraps the whole
    barrier-released batch. Raw threads only -- never anyio.

    Args:
        call: A function taking one checked-out connection and returning its own
            per-call elapsed time (ignored here; only the batch wall-clock is timed).
        conns: The `n` per-thread connections (each thread uses its own; ADBC
            forbids sharing a connection across threads).
        n: Number of concurrent threads/connections. Must equal `len(conns)`.
        trials: Number of trials to run; the median wall-clock is returned.

    Returns:
        The median batch wall-clock time in seconds across `trials`.

    Raises:
        ValueError: If `len(conns) != n`. The barrier is sized for `n` parties but
            one task is spawned per connection; a mismatch would leave the barrier
            permanently un-tripped and hang on the executor's exit, so it is
            rejected up front instead.
    """
    if len(conns) != n:
        msg = f"len(conns)={len(conns)} must equal n={n}"
        raise ValueError(msg)

    def trial() -> float:
        # Barrier timeout: a defence-in-depth guard so any future caller that
        # slips past the length check still fails loudly (BrokenBarrierError)
        # rather than blocking the executor forever.
        barrier = threading.Barrier(n, timeout=60)

        def task(conn: _Conn) -> float:
            barrier.wait()  # release all threads together
            return call(conn)

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(task, conns))
        return time.perf_counter() - t0

    return median(trial() for _ in range(trials))
