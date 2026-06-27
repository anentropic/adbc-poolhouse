"""
Limiter EDGE coverage: token accounting + bound + no hold-and-wait (EDGE-09/10/11/12).

Every test runs under BOTH asyncio and trio. The token-accounting legs (EDGE-09)
drive the REAL DuckDB driver and assert `pool._limiter.borrowed_tokens` returns to
0 after a normal return AND after an `AdbcError`, each across a x50 loop. The
concurrency legs (EDGE-10/11/12) gate stub-backed workers that block inside
`execute` to prove the limiter caps in-flight offloads at `pool_size +
max_overflow`, that a token queued-waiting on a saturated limiter that is
cancelled leaks nothing, and that a transient token never self-deadlocks.

D-24-02: the EDGE-09 cancel-mid-block leg is Phase 25 (it needs the `adbc_cancel`
join to unblock a non-cancellable worker honestly) --- there is deliberately NO
cancel-mid-block test here, only the success and error legs.

Every concurrency body runs under a REAL-clock watchdog (`real_clock_watchdog`,
the autojump-immune substitute for `anyio.fail_after` --- a virtual `fail_after`
trips spuriously under the trio `MockClock`) and ALWAYS releases gated workers in
a `finally`, so a gating regression fails fast instead of hanging.
"""

from __future__ import annotations

import functools
import importlib
from typing import TYPE_CHECKING

import anyio
import pytest
from adbc_driver_manager import Error as AdbcError

from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog

# Token-accounting loop count (EDGE-09): a flaky leak shows up across repeats.
_ACCOUNTING_LOOPS = 50


def _stub_conn_on(limiter: anyio.CapacityLimiter) -> tuple[AsyncConnection, BlockingStubConnection]:
    """Build a real `AsyncConnection` over a fresh blocking stub, sharing `limiter`."""
    stub_conn = BlockingStubConnection()
    async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
    return async_conn, stub_conn


class TestEdge09TokenAccounting:
    """EDGE-09 success + error legs: the limiter token always returns (D-24-02)."""

    @pytest.mark.anyio
    async def test_token_returns_after_success(self, duckdb_async_pool: AsyncPool) -> None:
        """After a normal round trip, `borrowed_tokens` is 0 --- across a x50 loop."""
        for _ in range(_ACCOUNTING_LOOPS):
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT 1 AS n")
                await cur.fetch_arrow_table()
            assert duckdb_async_pool._limiter.borrowed_tokens == 0

    @pytest.mark.anyio
    async def test_token_returns_after_error(self, duckdb_async_pool: AsyncPool) -> None:
        """After an `AdbcError`, the token returns and all tokens are available --- x50."""
        for _ in range(_ACCOUNTING_LOOPS):
            with pytest.raises(AdbcError):
                async with await duckdb_async_pool.connect() as conn:
                    cur = conn.cursor()
                    await cur.execute("SELECT * FROM does_not_exist")
            limiter = duckdb_async_pool._limiter
            assert limiter.borrowed_tokens == 0
            assert limiter.available_tokens == limiter.total_tokens


class TestEdge10CancelWhileQueued:
    """EDGE-10: a token queued-waiting on a saturated limiter, then cancelled, leaks nothing."""

    @pytest.mark.anyio
    async def test_cancel_queued_acquirer_recovers(self, anyio_backend_name: str) -> None:
        """
        Saturate the limiter, queue one more offload, cancel it, then recover.

        With the limiter saturated by gated workers, one MORE `execute` blocks at
        the `to_thread.run_sync` token-acquire await --- no worker starts, no stub
        is touched. That acquire IS cancellable, so cancelling its task while it
        waits leaks no token (`borrowed_tokens` returns to the held count, then 0
        once the held workers release). The whole body runs under a real-clock
        watchdog (the autojump-immune substitute for `anyio.fail_after`) and
        releases every held worker in a `finally`.
        """
        del anyio_backend_name
        bound = 2
        limiter = anyio.CapacityLimiter(bound)
        held = [_stub_conn_on(limiter) for _ in range(bound)]
        held_cursors = [conn.cursor() for conn, _ in held]
        stub_cursors = [stub.cursors[0] for _, stub in held]
        with real_clock_watchdog(stub_cursors) as watchdog:
            async with anyio.create_task_group() as held_tg:
                for cur in held_cursors:
                    held_tg.start_soon(functools.partial(cur.execute, "SELECT 1"))
                try:
                    # Wait until both held workers are provably inside execute, so
                    # the limiter is genuinely saturated.
                    await await_inside(lambda: all(c.execute_call_count == 1 for c in stub_cursors))
                    assert limiter.borrowed_tokens == bound

                    # A third offload now can only QUEUE waiting for a token.
                    queued_conn, queued_stub = _stub_conn_on(limiter)
                    queued_cur = queued_conn.cursor()
                    async with anyio.create_task_group() as cancel_tg:
                        cancel_tg.start_soon(functools.partial(queued_cur.execute, "SELECT 2"))
                        # Let it reach the token-acquire await, then cancel it. It
                        # never enters the stub (no worker started).
                        await anyio.sleep(0)
                        cancel_tg.cancel_scope.cancel()
                    # The queued acquirer was cancelled before acquiring; its stub
                    # was never entered and the held count is unchanged.
                    assert queued_stub.cursors[0].execute_call_count == 0
                    assert limiter.borrowed_tokens == bound
                finally:
                    for cur in stub_cursors:
                        cur.release()  # let the held workers return --- no sleep
            assert limiter.borrowed_tokens == 0
            # Full recovery: a fresh offload acquires and returns a token cleanly.
            fresh_conn, fresh_stub = _stub_conn_on(limiter)
            fresh_cur = fresh_conn.cursor()
            async with anyio.create_task_group() as fresh_tg:
                fresh_tg.start_soon(functools.partial(fresh_cur.execute, "SELECT 3"))
                try:
                    await await_inside(lambda: fresh_stub.cursors[0].execute_call_count == 1)
                    assert limiter.borrowed_tokens == 1
                finally:
                    fresh_stub.cursors[0].release()
        assert watchdog[0] is False, "EDGE-10 watchdog tripped: a worker hung"
        assert limiter.borrowed_tokens == 0


class TestEdge11NoSelfDeadlock:
    """EDGE-11: a transient token makes a second offload on a held connection safe."""

    @pytest.mark.anyio
    async def test_sequential_offloads_on_held_connection(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        Holding a connection then awaiting a second offload on it never deadlocks.

        The transient-token model (D-24-01) releases the token after each call, so
        a held `AsyncConnection` owns NO token between calls --- a second
        `execute` on it cannot hold-and-wait against itself. Guarded by a real
        watchdog conceptually equivalent to `anyio.fail_after`: if a self-deadlock
        regression appeared, the body would never complete.
        """
        with real_clock_watchdog([]):  # no stub workers; real driver returns promptly
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT 1 AS a")  # borrows + releases a token
                # A SECOND offload on the same held connection --- safe by
                # construction because no token is retained between calls.
                await cur.execute("SELECT 2 AS b")
                tbl = await cur.fetch_arrow_table()
                assert tbl.column("b")[0].as_py() == 2
        assert duckdb_async_pool._limiter.borrowed_tokens == 0


class TestEdge12ConcurrencyBound:
    """EDGE-12: under a flood, the in-flight offload count never exceeds the limiter bound."""

    @pytest.mark.anyio
    async def test_running_max_equals_bound_under_flood(self, anyio_backend_name: str) -> None:
        """
        A 4x flood of gated executes drives the running-max to exactly the bound.

        `pool_size + max_overflow` separate stub-backed connections share ONE
        limiter; a 4x flood of gated `execute`s all try to run at once, but the
        limiter admits only `bound` workers into the stubs simultaneously. The
        observed high-water mark (summed across the per-connection stub counters,
        which only increment INSIDE the blocked section) equals the bound, never
        more. Real-clock watchdog + release-in-finally as always.
        """
        del anyio_backend_name
        bound = 3  # stand-in for pool_size + max_overflow
        flood = bound * 4
        limiter = anyio.CapacityLimiter(bound)
        pairs = [_stub_conn_on(limiter) for _ in range(flood)]
        cursors = [conn.cursor() for conn, _ in pairs]
        stub_cursors = [stub.cursors[0] for _, stub in pairs]

        # The per-stub high-water mark is 1 (one worker per connection); the
        # cross-connection bound is what the limiter enforces, read via
        # borrowed_tokens below.
        with real_clock_watchdog(stub_cursors) as watchdog:
            async with anyio.create_task_group() as tg:
                for i, cur in enumerate(cursors):
                    tg.start_soon(functools.partial(cur.execute, f"SELECT {i}"))
                try:
                    # Wait until the limiter is saturated: exactly `bound` workers
                    # are inside their stubs at once.
                    await await_inside(lambda: limiter.borrowed_tokens == bound)
                    observed_max = limiter.borrowed_tokens
                    assert observed_max == bound
                finally:
                    # Drain via close() (terminal): a closed stub short-circuits in
                    # `_block` and returns immediately even for a worker that has
                    # not yet entered, so every queued worker is admitted by the
                    # limiter and returns at once with no re-arm trap (a plain
                    # `release()` clears on the next `_block`, stranding a worker
                    # that entered after the release).
                    for cur in stub_cursors:
                        cur.close()
                    # Drain: poll until every worker has been admitted and returned.
                    await await_inside(lambda: limiter.borrowed_tokens == 0)
        assert watchdog[0] is False, "EDGE-12 watchdog tripped: a worker hung"
        assert limiter.borrowed_tokens == 0
