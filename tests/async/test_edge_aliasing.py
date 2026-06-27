"""
Connection-aliasing rejection EDGE coverage (EDGE-15, D-24-03).

Two tasks concurrently using ONE `AsyncConnection` --- via two cursors on it, or
the same cursor --- is a bug: an ADBC connection permits serialized but not
concurrent access. The wrapper rejects the second concurrent caller with
[`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] rather than silently
serializing (D-24-03). This proves it: one task enters `execute` and blocks (gated
via the Phase 23 stub), a second concurrent task calls `execute` on the same
connection, and the second raises `ConnectionBusyError` while the stub's
`max_concurrent_in_execute` stays at 1 (no real concurrency-violation ever
occurred).

Runs under BOTH backends, under a real-clock watchdog (the autojump-immune
substitute for `anyio.fail_after`), releasing the gated worker in a `finally`.
"""

from __future__ import annotations

import functools
import importlib

import anyio
import pytest

from adbc_poolhouse import ConnectionBusyError
from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog


class TestEdge15Aliasing:
    """A second concurrent caller on one connection is rejected, not serialized."""

    @pytest.mark.anyio
    async def test_second_concurrent_caller_raises_busy(self, anyio_backend_name: str) -> None:
        """
        While one cursor blocks in `execute`, a second concurrent call raises.

        The first worker is gated inside the stub's `execute` (it holds the
        connection's `_in_use` flag). A second task then calls `execute` on a
        cursor of the SAME connection; the `_in_use` check-and-set rejects it with
        `ConnectionBusyError` before any offload starts, so the stub is never
        entered twice --- `max_concurrent_in_execute` stays 1 (no two C calls ever
        ran on one connection). The first worker is released in a `finally`.
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
                tg.start_soon(functools.partial(first_cur.execute, "SELECT 1"))
                try:
                    # Wait until the first worker is provably inside execute (it now
                    # holds _in_use).
                    blocking_stub = stub_conn.cursors[0]
                    await await_inside(lambda: blocking_stub.execute_call_count == 1)
                    # A concurrent second call on the same connection must reject.
                    try:
                        await second_cur.execute("SELECT 2")
                    except ConnectionBusyError:
                        busy_raised = True
                finally:
                    for cur in stub_conn.cursors:
                        cur.release()
        assert watchdog[0] is False, "EDGE-15 watchdog tripped: a worker hung"
        assert busy_raised, "the second concurrent caller was not rejected"
        # The second cursor uses a DIFFERENT stub cursor, which was never entered;
        # the first stub cursor only ever had one worker inside it.
        assert stub_conn.cursors[0].max_concurrent_in_execute == 1
        # No real concurrency-violation: at most one worker was ever in any one
        # stub cursor's blocked section.
        assert all(c.max_concurrent_in_execute <= 1 for c in stub_conn.cursors)
