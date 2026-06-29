"""
Loop-hygiene EDGE coverage (EDGE-25 behavioural leg + EDGE-26).

EDGE-25 (behavioural): a blocking call runs OFF the event-loop thread --- the
stub records each `execute` caller's thread id, which must differ from the loop
thread's id (`threading.get_ident()` read on the loop). EDGE-26: while a worker is
blocked off-loop inside `execute`, a concurrent coroutine keeps making progress
across several `anyio.sleep(0)` checkpoints --- proving the offload never blocks
the loop. The static leg of EDGE-25 (the guard scan) lives in
`tests/test_async_guard.py`.

Both run under BOTH backends, under a real-clock watchdog (the autojump-immune
substitute for `anyio.fail_after`), releasing the gated worker in a `finally`.
"""

from __future__ import annotations

import functools
import importlib
import threading

import anyio
import pytest

from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks

# Number of cooperative checkpoints the concurrent coroutine must advance while
# the offload is blocked (EDGE-26).
_PROGRESS_CHECKPOINTS = 5


def _stub_conn() -> tuple[AsyncConnection, BlockingStubConnection]:
    """Build a real `AsyncConnection` over a fresh blocking stub."""
    limiter = anyio.CapacityLimiter(4)
    stub_conn = BlockingStubConnection()
    async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
    return async_conn, stub_conn


class TestEdge25OffLoopThread:
    """The blocking call runs on a worker thread, not the loop thread."""

    @pytest.mark.anyio
    async def test_worker_thread_differs_from_loop_thread(self, anyio_backend_name: str) -> None:
        """
        The stub's recorded `execute` thread id differs from the loop thread id.

        Captures the loop thread id with `threading.get_ident()` on the loop, gates
        a worker inside the stub's `execute`, then compares the worker's recorded
        thread id --- they must differ, proving the call genuinely ran off-loop
        (EDGE-25 behavioural leg).
        """
        del anyio_backend_name
        loop_tid = threading.get_ident()
        async_conn, stub_conn = _stub_conn()
        cur = async_conn.cursor()
        worker_tid = -1
        with real_clock_watchdog(stub_conn.cursors) as watchdog:
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(cur.execute, "SELECT 1"))
                try:
                    blocking_stub = stub_conn.cursors[0]
                    await await_inside(lambda: bool(blocking_stub.execute_thread_ids))
                    worker_tid = blocking_stub.execute_thread_ids[0]
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert watchdog[0] is False, "EDGE-25 watchdog tripped: a worker hung"
        assert worker_tid != -1
        assert worker_tid != loop_tid


class TestEdge26LoopKeepsRunning:
    """A concurrent coroutine advances while the offload is blocked off-loop."""

    @pytest.mark.anyio
    async def test_concurrent_coroutine_advances_during_offload(
        self, anyio_backend_name: str
    ) -> None:
        """
        A counter coroutine advances across N checkpoints while `execute` blocks.

        With a worker blocked off-loop inside the stub's `execute`, a sibling
        coroutine runs `anyio.sleep(0)` in a loop, incrementing a counter each
        checkpoint. The counter reaches its target WHILE the offload is still
        blocked --- the loop kept scheduling other tasks, so the blocking call
        never stalled the event loop (EDGE-26). The worker is released afterward.
        """
        del anyio_backend_name
        async_conn, stub_conn = _stub_conn()
        cur = async_conn.cursor()
        progress = {"n": 0}

        async def _ticker() -> None:
            for _ in range(_PROGRESS_CHECKPOINTS):
                progress["n"] += 1
                await anyio.sleep(0)

        with real_clock_watchdog(stub_conn.cursors) as watchdog:
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(cur.execute, "SELECT 1"))
                try:
                    blocking_stub = stub_conn.cursors[0]
                    # Wait until the worker is provably blocked off-loop.
                    await await_inside(lambda: blocking_stub.execute_call_count == 1)
                    # Now run the ticker; it must complete while the offload is
                    # STILL blocked (we have not released it yet).
                    await _ticker()
                    assert progress["n"] == _PROGRESS_CHECKPOINTS
                    assert blocking_stub.execute_call_count == 1  # still blocked
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert watchdog[0] is False, "EDGE-26 watchdog tripped: a worker hung"
        assert progress["n"] == _PROGRESS_CHECKPOINTS
