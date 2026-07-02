"""
Async DataFrame busy-guard parity (T-31-03) --- Wave-0 RED scaffolding.

An ADBC connection permits serialized but not concurrent C-access. `fetch_df` /
`fetch_polars` bracket their offload with `self._owner._offloading()` (the `_in_use`
guard), exactly like `fetch_arrow_table`, so a SECOND in-flight op on the same
connection while a `fetch_df` / `fetch_polars` is blocked must raise
`ConnectionBusyError` --- never silently serialize (parity with every other
offloaded method).

These tests prove it with the Phase 23 stub: one worker is gated INSIDE the stub's
`fetch_df` / `fetch_polars` (holding `_in_use`), then a second concurrent call on a
second cursor of the SAME connection is rejected with `ConnectionBusyError`, while
the stub's `max_concurrent_in_execute` stays 1 (no two C calls ever ran on one
connection). The gated worker is released in a `finally`; a `real_clock_watchdog`
(the autojump-immune substitute for `anyio.fail_after`) fails fast on a hang, and
`concurrency_marks` (x-loop repeat + timeout) so a ~33% deadlock cannot hide behind
one lucky pass (MEMORY loop-flaky-concurrency lesson). Both backends.

Wave-0 status: `AsyncCursor.fetch_df` / `fetch_polars` do NOT exist yet, so these
FAIL (RED) --- the acceptance signal. Closes threat T-31-03 (concurrent C-access on
one connection) once GREEN.
"""

from __future__ import annotations

import functools
import importlib
from typing import TYPE_CHECKING

import anyio
import pytest

from adbc_poolhouse import ConnectionBusyError
from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

if TYPE_CHECKING:
    from adbc_poolhouse._async._cursor import AsyncCursor

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks


class TestDf03BusyGuardParity:
    """A second in-flight op while `fetch_df`/`fetch_polars` is offloaded raises busy."""

    @pytest.mark.anyio
    async def test_second_op_during_fetch_df_raises_busy(self, anyio_backend_name: str) -> None:
        """
        While one cursor blocks in `fetch_df`, a second concurrent call raises busy.

        The first worker is gated inside the stub's `fetch_df` (holding the
        connection's `_in_use` flag via `_offloading()`). A second task then calls
        `execute` on a second cursor of the SAME connection; the `_in_use`
        check-and-set rejects it with `ConnectionBusyError` before any offload
        starts, so the stub is never entered twice --- `max_concurrent_in_execute`
        stays 1. The first worker is released in a `finally`.
        """
        del anyio_backend_name
        limiter = anyio.CapacityLimiter(4)
        stub_conn = BlockingStubConnection()
        async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
        first_cur = async_conn.cursor()
        second_cur = async_conn.cursor()  # a SECOND cursor on the same connection
        busy_raised = False
        with real_clock_watchdog(stub_conn.cursors) as watchdog:
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_fetch_df, first_cur))
                try:
                    blocking_stub = stub_conn.cursors[0]
                    await await_inside(lambda: blocking_stub.df_call_count >= 1)
                    try:
                        await second_cur.execute("SELECT 2")
                    except ConnectionBusyError:
                        busy_raised = True
                finally:
                    for cur in stub_conn.cursors:
                        cur.release()
        assert watchdog[0] is False, "busy watchdog tripped: a worker hung"
        assert busy_raised, "the second concurrent caller was not rejected"
        assert stub_conn.cursors[0].max_concurrent_in_execute == 1
        assert all(c.max_concurrent_in_execute <= 1 for c in stub_conn.cursors)

    @pytest.mark.anyio
    async def test_second_op_during_fetch_polars_raises_busy(self, anyio_backend_name: str) -> None:
        """
        While one cursor blocks in `fetch_polars`, a second concurrent call raises busy.

        The `fetch_polars` twin of the `fetch_df` busy proof: gate the first worker
        inside `fetch_polars` (`polars_call_count >= 1`), then a second concurrent op
        on the same connection is rejected with `ConnectionBusyError`.
        """
        del anyio_backend_name
        limiter = anyio.CapacityLimiter(4)
        stub_conn = BlockingStubConnection()
        async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
        first_cur = async_conn.cursor()
        second_cur = async_conn.cursor()
        busy_raised = False
        with real_clock_watchdog(stub_conn.cursors) as watchdog:
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_fetch_polars, first_cur))
                try:
                    blocking_stub = stub_conn.cursors[0]
                    await await_inside(lambda: blocking_stub.polars_call_count >= 1)
                    try:
                        await second_cur.execute("SELECT 2")
                    except ConnectionBusyError:
                        busy_raised = True
                finally:
                    for cur in stub_conn.cursors:
                        cur.release()
        assert watchdog[0] is False, "busy watchdog tripped: a worker hung"
        assert busy_raised, "the second concurrent caller was not rejected"
        assert stub_conn.cursors[0].max_concurrent_in_execute == 1
        assert all(c.max_concurrent_in_execute <= 1 for c in stub_conn.cursors)


async def _drive_fetch_df(cursor: AsyncCursor) -> None:
    """Run a single `fetch_df` (the blocked op holding `_in_use`)."""
    await cursor.fetch_df()


async def _drive_fetch_polars(cursor: AsyncCursor) -> None:
    """Run a single `fetch_polars` (the blocked op holding `_in_use`)."""
    await cursor.fetch_polars()
