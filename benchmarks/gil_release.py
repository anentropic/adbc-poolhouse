"""
GIL-release measurements for ADBC `execute` and `fetch_arrow_table` (SPIKE-01/02).

This is the kept benchmark. It drives the *real* production checkout path --
`create_pool(DuckDBConfig(database=<file>, pool_size=N))` -- so it measures the
exact code path Phase 24's async wrappers will offload to threads. Two heavy,
C-side DuckDB operations are timed under `N` barrier-gated concurrent threads:

- SPIKE-01: a heavy `execute` (large join, tiny `fetchone()` result) -- expected
  to *parallelize* (`speedup` approaches `N`) because the ADBC C path releases
  the GIL during query execution.
- SPIKE-02: a large `fetch_arrow_table` (20M-row projection) -- expected to
  *serialize* (`speedup` approaches `1`) because Arrow materialization re-holds
  the GIL.

The script prints a `report` dict per measurement; the interpretation lives in
`22-GO-NO-GO.md` (plan 02). No absolute-speedup assertion appears here -- those
ratios are hardware-dependent and would be flaky. Concurrency is raw threads
only (via `benchmarks._harness.concurrent_wall`); no anyio, no async code.

Run:
    .venv/bin/python -m benchmarks.gil_release --measure both
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

from adbc_poolhouse import DuckDBConfig, create_pool
from benchmarks._harness import concurrent_wall, median, report

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

# SPIKE-01: heavy C-side join; tiny result isolates the execute path (not fetch).
HEAVY_EXEC = """
SELECT count(*) FROM (
  SELECT a.i AS x FROM range(0, {rows}) a(i)
  JOIN range(0, 30) b(j) ON (a.i % 7) = (b.j % 7)
) t
"""

# SPIKE-02: large projection materialized to an Arrow table (the GIL-bound path).
HEAVY_FETCH = (
    "SELECT i, i*2 AS j, i%97 AS k, hash(i) AS h, (i*3.14159) AS f FROM range(0, {rows}) t(i)"
)


def time_execute(conn: object, rows: int) -> float:
    """
    Time one heavy `execute` call (SPIKE-01).

    Runs a large C-side join and consumes a single row via `fetchone()` so the
    measured time reflects query *execution*, not result materialization.

    Args:
        conn: A checked-out pool connection (one per thread; never shared).
        rows: Row count for the driving `range(...)` join.

    Returns:
        The per-call elapsed time in seconds (`time.perf_counter` delta).
    """
    cur = conn.cursor()  # type: ignore[attr-defined]
    t0 = time.perf_counter()
    cur.execute(HEAVY_EXEC.format(rows=rows))
    cur.fetchone()  # tiny result: isolates execute, not materialization
    dt = time.perf_counter() - t0
    cur.close()
    return dt


def time_fetch(conn: object, rows: int) -> float:
    """
    Time one large `fetch_arrow_table` call (SPIKE-02).

    Executes a wide projection and materializes the full result as an Arrow
    table -- the GIL-bound path under test.

    Args:
        conn: A checked-out pool connection (one per thread; never shared).
        rows: Row count for the driving `range(...)` projection.

    Returns:
        The per-call elapsed time in seconds (`time.perf_counter` delta).
    """
    cur = conn.cursor()  # type: ignore[attr-defined]
    t0 = time.perf_counter()
    cur.execute(HEAVY_FETCH.format(rows=rows))
    cur.fetch_arrow_table()  # the GIL-bound materialization under test
    dt = time.perf_counter() - t0
    cur.close()
    return dt


@contextmanager
def _pool(n: int) -> Iterator[object]:
    """
    Yield a file-backed DuckDB pool sized for `n` concurrent connections.

    Uses a temp-file database (never `:memory:`, which `DuckDBConfig` rejects for
    `pool_size > 1`). Pairs `pool.dispose()` with `pool._adbc_source.close()` in a
    `finally` -- the verbatim teardown idiom from `tests/test_pool_factory.py` --
    and asserts `pool.checkedout() == 0` afterward to prove the checkout path is
    leak-free.

    Args:
        n: Pool size (and number of concurrent connections to be checked out).

    Yields:
        The configured pool object.
    """
    db = os.path.join(tempfile.mkdtemp(), "bench.db")
    pool = create_pool(DuckDBConfig(database=db, pool_size=n, max_overflow=0))
    try:
        yield pool
    finally:
        assert pool.checkedout() == 0, "connections leaked from the pool"  # noqa: S101
        pool.dispose()
        pool._adbc_source.close()  # type: ignore[attr-defined]


def measure(
    name: str,
    call: Callable[[object, int], float],
    n: int,
    rows: int,
    trials: int,
) -> dict[str, float]:
    """
    Measure one operation through the real `create_pool` checkout path.

    Checks out `n` connections from a file-backed pool, warms up once (seeding
    live connections), records the median single-call baseline (1 thread), then
    the median concurrent wall-clock (`n` barrier-gated threads), and returns the
    six-key `report` dict.

    Args:
        name: Label for the measurement (`"execute"` or `"fetch"`).
        call: A `(conn, rows) -> seconds` timer (`time_execute` or `time_fetch`).
        n: Number of concurrent connections/threads.
        rows: Row count driving the heavy query.
        trials: Number of trials; the median of each phase is taken.

    Returns:
        The `report` dict (`single_call_s`, `wall_s`, `ideal_parallel_s`,
        `full_serial_s`, `speedup_x`, `parallel_efficiency`).
    """
    with _pool(n) as pool:
        conns = [pool.connect() for _ in range(n)]  # type: ignore[attr-defined]
        try:
            call(conns[0], rows)  # warm up: seed live connections, prime caches
            single = median(call(conns[0], rows) for _ in range(trials))
            wall = concurrent_wall(lambda c: call(c, rows), conns, n, trials)
            result = report(single, wall, n)
        finally:
            for c in conns:
                c.close()
    print(f"[{name}] N={n} rows={rows} trials={trials}: {result}")
    return result


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for the benchmark."""
    default_n = min(4, os.cpu_count() or 1)
    parser = argparse.ArgumentParser(
        prog="benchmarks.gil_release",
        description="Measure GIL release for ADBC execute (SPIKE-01) and "
        "fetch_arrow_table (SPIKE-02) via the real create_pool checkout path.",
    )
    parser.add_argument(
        "--measure",
        choices=("execute", "fetch", "both"),
        default="both",
        help="Which operation(s) to measure (default: both).",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=default_n,
        help=f"Concurrent connections/threads (default: min(4, cpu_count)={default_n}).",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=20_000_000,
        help="Row count for the heavy query (default: 20_000_000).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=5,
        help="Trials per phase; median is reported (default: 5).",
    )
    return parser


def main() -> None:
    """Parse CLI args and run the requested measurement(s)."""
    args = _build_parser().parse_args()
    # Execute joins are heavier per row; scale rows down so single-call stays
    # in the seconds range without dominating runtime.
    exec_rows = max(1, args.rows // 6)
    if args.measure in ("execute", "both"):
        measure("execute", time_execute, args.n, exec_rows, args.trials)
    if args.measure in ("fetch", "both"):
        measure("fetch", time_fetch, args.n, args.rows, args.trials)


if __name__ == "__main__":
    main()
