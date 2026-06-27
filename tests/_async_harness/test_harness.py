"""
Dual-backend self-tests for the async harness (Phase 23, D-06).

This file is the validation surface for the whole phase: it drives the
[`stubs`][tests._async_harness.stubs], [`gating`][tests._async_harness.gating],
and [`clock`][tests._async_harness.clock] machinery through event-gating
(block->release, block->`adbc_cancel`->unblock) and the virtual clock on
synthetic inputs -- no DB, no driver, and no real sleeps. Every async test is
marked `@pytest.mark.anyio` and runs under BOTH asyncio and trio via the
`anyio_backend` fixture (the dual-backend contract Phases 24/25/27 ride on).

CRITICAL LOCATION: this file lives INSIDE `tests/_async_harness/` -- the package
that holds the `conftest.py` defining `anyio_backend` -- on purpose. pytest
conftest fixtures propagate DOWNWARD only (the conftest's own directory and its
subdirectories). A sibling such as `tests/test_async_harness.py` would be a
parent-level peer and every `@pytest.mark.anyio` test would fail collection with
`fixture 'anyio_backend' not found`. A `test_*.py` file inside the package is
collected normally regardless of the `__init__.py` marker, and it now sits
at/below the conftest, so the fixture is visible.

Dual-`entered` warning: the loop-facing gate awaited on the event loop is the
`anyio.Event` passed to
[`run_blocking`][tests._async_harness.gating.run_blocking] -- NOT the stub's
`entered` attribute, which is a `threading.Event` (the sync signal for the
pure-threading self-tests in `test_stubs.py`). They share a name but are
different objects; never await the stub's `threading.Event` on the loop.
"""

from __future__ import annotations

import functools
import threading

import anyio
import pytest

from tests._async_harness.gating import run_blocking
from tests._async_harness.stubs import BlockingStubCursor


class TestEventGating:
    """Block->release / cancel / off-loop / max-concurrent paths under both backends."""

    @pytest.mark.anyio
    async def test_block_then_release(self, anyio_backend_name: str) -> None:
        """A gated worker enters execute, then `release()` lets it return uncancelled."""
        del anyio_backend_name
        stub = BlockingStubCursor()
        limiter = anyio.CapacityLimiter(1)
        entered = anyio.Event()
        gated = functools.partial(run_blocking, entered=entered, limiter=limiter)
        async with anyio.create_task_group() as tg:
            tg.start_soon(gated, stub.execute, "SELECT 1")
            await entered.wait()  # deterministic -- worker is inside execute, no sleep
            assert stub.execute_call_count == 1
            stub.release()  # unblock the worker -- no sleep
        assert stub.observed_cancel is False

    @pytest.mark.anyio
    async def test_block_then_adbc_cancel(self, anyio_backend_name: str) -> None:
        """`adbc_cancel()` on a gated worker releases it and flips `observed_cancel`."""
        del anyio_backend_name
        stub = BlockingStubCursor()
        limiter = anyio.CapacityLimiter(1)
        entered = anyio.Event()
        gated = functools.partial(run_blocking, entered=entered, limiter=limiter)
        async with anyio.create_task_group() as tg:
            tg.start_soon(gated, stub.execute, "SELECT 1")
            await entered.wait()
            stub.adbc_cancel()  # releases the worker + flips observed_cancel
        assert stub.observed_cancel is True
        assert stub.adbc_cancel_call_count == 1

    @pytest.mark.anyio
    async def test_offloaded_thread_id(self, anyio_backend_name: str) -> None:
        """The worker ran OFF the loop thread (pre-proves the EDGE-25 mechanism)."""
        del anyio_backend_name
        stub = BlockingStubCursor()
        limiter = anyio.CapacityLimiter(1)
        entered = anyio.Event()
        gated = functools.partial(run_blocking, entered=entered, limiter=limiter)
        async with anyio.create_task_group() as tg:
            tg.start_soon(gated, stub.execute, "SELECT 1")
            await entered.wait()
            assert stub.execute_thread_ids[0] != threading.get_ident()
            stub.release()

    @pytest.mark.anyio
    async def test_max_concurrent(self, anyio_backend_name: str) -> None:
        """Two offloaded calls, each gated by its OWN event, drive max_concurrent to 2."""
        del anyio_backend_name
        stub = BlockingStubCursor()
        limiter = anyio.CapacityLimiter(2)
        entered_a = anyio.Event()
        entered_b = anyio.Event()
        gated_a = functools.partial(run_blocking, entered=entered_a, limiter=limiter)
        gated_b = functools.partial(run_blocking, entered=entered_b, limiter=limiter)
        async with anyio.create_task_group() as tg:
            tg.start_soon(gated_a, stub.execute, "SELECT 1")
            tg.start_soon(gated_b, stub.execute, "SELECT 2")
            await entered_a.wait()  # both workers must be inside execute before asserting
            await entered_b.wait()
            assert stub.max_concurrent_in_execute == 2
            stub.release()  # release both blocked calls; let the group finish
