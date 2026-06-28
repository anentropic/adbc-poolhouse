"""
TEST-04 limiter saturation stress: no deadlock or starvation above `pool_size`.

The dedicated per-pool `CapacityLimiter(pool_size + max_overflow)` is the only
thing that caps how many blocking `execute` offloads run at once. This module
proves it holds that bound under a deliberate flood, without self-deadlock and
without starving any queued worker.

Two complementary tests, both `@pytest.mark.anyio` (run under BOTH asyncio and
trio):

- The PRIMARY proof is a stub-gated deterministic flood (D-27-10), reusing the
  EDGE-12 pattern: `4 x (pool_size + max_overflow)` workers share ONE
  `anyio.CapacityLimiter`, every worker blocks inside a `BlockingStubConnection`'s
  `execute`. The flood proves the bound TWO ways: it polls `borrowed_tokens` to
  confirm saturation was reached, and --- the load-bearing over-admission check ---
  it sums each stub's live `in_execute` counter (workers actually inside the
  blocked section, counted independently of the limiter's own accounting) and
  asserts that cross-cursor sum equals the bound and is never exceeded. It then
  drains and asserts every queued worker eventually ran (`borrowed_tokens == 0`, no
  starvation). It uses the shipped defaults `pool_size=5 + max_overflow=3 = 8`, so
  the flood proves the real bound the library ships (Open Question 1).
- A small real-DuckDB smoke flood adds realism: `4 x bound` genuine
  connect -> execute -> fetch round trips against `duckdb_async_pool` all complete
  and leave `checkedout() == 0`.

Two load-bearing landmines (Phase 24-26):

- Deadlock detection is a real-clock `time.monotonic()` watchdog thread
  (`real_clock_watchdog`), NEVER `anyio.fail_after`: a virtual `fail_after`
  autojumps to its own deadline under the trio `MockClock(autojump_threshold=0)`
  the instant every worker blocks off-loop, tripping every run (D-27-11).
- The gated flood drains via `close()` on each stub cursor, never `release()`:
  `close()` latches the sticky `_closed` flag so `_block` short-circuits even for a
  worker that has not yet entered, whereas a plain `release()` re-arms on the next
  `_block` and strands a late worker (the Phase 26 lost-wakeup).

No `src/` changes. The gated mechanics stay DuckDB + stub only --- the Snowflake
cassette `ReplayCursor` cannot block-gate (D-27-06).
"""

from __future__ import annotations

import functools
import importlib
from typing import TYPE_CHECKING

import anyio
import pytest

from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog

# The shipped pool defaults (Open Question 1): the flood proves the REAL bound the
# library ships, not a stand-in. 32 gated stubs is cheap (no real I/O).
_POOL_SIZE = 5
_MAX_OVERFLOW = 3
_BOUND = _POOL_SIZE + _MAX_OVERFLOW  # 8
_FLOOD = _BOUND * 4  # 32


def _stub_conn_on(limiter: anyio.CapacityLimiter) -> tuple[AsyncConnection, BlockingStubConnection]:
    """Build a real `AsyncConnection` over a fresh blocking stub, sharing `limiter`."""
    stub_conn = BlockingStubConnection()
    async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
    return async_conn, stub_conn


class TestLimiterFloodBound:
    """TEST-04 primary proof: running-max == bound, no starvation, no deadlock."""

    @pytest.mark.anyio
    async def test_running_max_equals_bound_no_starvation(self, anyio_backend_name: str) -> None:
        """
        A `4x(pool_size+max_overflow)` stub-gated flood holds the bound and starves no one.

        `_FLOOD` separate stub-backed connections share ONE `CapacityLimiter(_BOUND)`;
        every worker blocks inside its stub's `execute`. Saturation is confirmed by
        polling `borrowed_tokens == _BOUND`. The real over-admission proof, however,
        is sampled stub-side, independent of the limiter's own token accounting: each
        stub cursor holds exactly one worker, and every worker lock-increments its
        cursor's `_in_execute` on entry to `_block`, so summing `_in_execute` across
        all cursors counts the workers ACTUALLY inside their blocked section right
        now. Polling that cross-cursor sum and asserting it never exceeds `_BOUND`
        (and reaches it) catches an over-admitting wrapper even though
        `borrowed_tokens` is structurally capped at `_BOUND` by the `CapacityLimiter`
        type and so could never reveal over-admission on its own. The flood then
        drains via `close()` (the sticky-latch terminal that admits even a worker
        that has not yet entered), and `borrowed_tokens` settling to 0 proves every
        queued worker eventually ran (no starvation).

        Deadlock detection is the real-clock `real_clock_watchdog` (NEVER
        `anyio.fail_after`, which autojumps under the trio `MockClock`): if a worker
        ever hung, the side thread `close()`s the stubs so the group exits and the
        `watchdog[0] is False` assertion below trips fast instead of hanging.
        """
        del anyio_backend_name
        limiter = anyio.CapacityLimiter(_BOUND)
        pairs = [_stub_conn_on(limiter) for _ in range(_FLOOD)]
        cursors = [conn.cursor() for conn, _ in pairs]
        stub_cursors = [stub.cursors[0] for _, stub in pairs]

        with real_clock_watchdog(stub_cursors) as watchdog:
            async with anyio.create_task_group() as tg:
                for i, cur in enumerate(cursors):
                    tg.start_soon(functools.partial(cur.execute, f"SELECT {i}"))
                try:
                    # Saturation is sampled stub-side, not via `borrowed_tokens`: a
                    # worker holds a limiter token from the moment the offload path
                    # acquires it, but does not reach the stub's `_block` (and so does
                    # not lock-increment `_in_execute`) until its worker thread runs.
                    # Polling the cross-cursor `in_execute` sum waits for the workers
                    # to be genuinely INSIDE the blocked section, closing that race.
                    def _inside_now() -> int:
                        return sum(sc.in_execute for sc in stub_cursors)

                    await await_inside(lambda: _inside_now() == _BOUND)
                    # Genuine over-admission check, independent of the limiter's own
                    # token accounting: the workers ACTUALLY inside their blocked
                    # section must number exactly `_BOUND` --- never more (an
                    # over-admitting wrapper would push this above the bound) and not
                    # less (saturation was genuinely reached).
                    inside_now = _inside_now()
                    assert inside_now == _BOUND, (
                        f"workers inside execute = {inside_now}, expected {_BOUND}"
                    )
                    assert limiter.borrowed_tokens == _BOUND  # limiter agrees
                finally:
                    # Drain via close() (terminal sticky latch): a closed stub
                    # short-circuits in `_block` and returns at once even for a worker
                    # that has not yet entered, so the limiter admits every queued
                    # worker and they all return --- no re-arm trap. A plain
                    # `release()` clears on the next `_block` and would strand a late
                    # worker (the Phase 26 lost-wakeup).
                    for cur in stub_cursors:
                        cur.close()
                    # No starvation: poll until every queued worker has been admitted
                    # and returned its token.
                    await await_inside(lambda: limiter.borrowed_tokens == 0)
        assert watchdog[0] is False, "TEST-04 flood watchdog tripped: a worker hung"
        assert limiter.borrowed_tokens == 0  # every queued worker ran; full drain


class TestLimiterSmokeFlood:
    """TEST-04 realism leg: a small real-DuckDB flood drains cleanly (D-27-10)."""

    @pytest.mark.anyio
    async def test_real_duckdb_flood_drains(self, duckdb_async_pool: AsyncPool) -> None:
        """
        A `4x bound` real connect -> execute -> fetch flood completes with no checkout leak.

        The stub test is the gating proof; this leg confirms the real driver behaves
        under the same saturation shape. `_FLOOD` genuine round trips run against
        `duckdb_async_pool`, but each task acquires a `CapacityLimiter(_BOUND)` slot
        BEFORE calling `connect` so no more than `_BOUND` connections are held at
        once --- otherwise the `_FLOOD` concurrent holders would exceed the real
        `QueuePool` (size `_POOL_SIZE` + overflow `_MAX_OVERFLOW`) and block in
        checkout (a real bounded-resource limit, not a wrapper bug). Each connection
        is held only across its own round trip and released promptly, so the bounded
        pool cycles all `_FLOOD` workers through and `checkedout() == 0` afterwards.

        Deadlock backstop: unlike the stub leg, this flood has NO blocking stub the
        watchdog could `close()` to force a stranded worker open --- the real ADBC
        round trips are not gated, so `real_clock_watchdog([])` is passed an empty
        cursor list and cannot interrupt a genuinely wedged worker. If the real
        flood ever deadlocked the `async with` body would never return, so the
        post-body `watchdog[0]` assertion would never be reached; the actual
        fail-fast guarantee here is the SUITE-LEVEL / CI job timeout, not this
        watchdog. The watchdog is retained only as a soft over-budget signal for the
        non-deadlock case (a slow-but-completing flood): if the body finishes after
        the wall-clock budget, the side thread will have set `tripped[0]`, and the
        assertion flags the regression. A virtual `anyio.fail_after` is deliberately
        NOT used as the backstop --- it autojumps to its own deadline under the trio
        `MockClock` the instant the workers block off-loop and would trip every run
        (Phase 24-26 landmine).
        """
        with real_clock_watchdog([]) as watchdog:
            # Hold no more than the pool's capacity at once, so the bounded real
            # QueuePool cycles every worker through instead of timing out a holder.
            gate = anyio.CapacityLimiter(_BOUND)

            async def _round_trip(i: int) -> None:
                async with gate, await duckdb_async_pool.connect() as conn:
                    cur = conn.cursor()
                    await cur.execute(f"SELECT {i} AS n")
                    tbl = await cur.fetch_arrow_table()
                    assert tbl.column("n")[0].as_py() == i

            async with anyio.create_task_group() as tg:
                for i in range(_FLOOD):
                    tg.start_soon(_round_trip, i)
        # Soft over-budget signal only (see docstring): a wedged worker is caught
        # by the suite/CI timeout, not here, since the empty watchdog cannot break
        # an ungated real worker open.
        assert watchdog[0] is False, "TEST-04 smoke flood exceeded its wall-clock budget"
        # No checkout leak: every connection the flood borrowed is back in the pool.
        assert duckdb_async_pool._pool.checkedout() == 0
        assert duckdb_async_pool._limiter.borrowed_tokens == 0
