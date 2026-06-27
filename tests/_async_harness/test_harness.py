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
import time
from typing import TYPE_CHECKING

import anyio
import pytest

from tests._async_harness.clock import virtual_clock
from tests._async_harness.gating import run_blocking
from tests._async_harness.stubs import BlockingStubCursor

if TYPE_CHECKING:
    from collections.abc import Callable

# Real wall-clock budget for the virtual-clock watchdog: a virtual 3600s deadline
# must fire in far less than this many real seconds, else it rode wall-clock.
_WALL_CLOCK_BUDGET_S = 5.0

# Tests parametrized over the anyio_backend fixture (asyncio + trio); the
# collection-level check below asserts both ids are present.
_BACKEND_IDS = frozenset({"asyncio", "trio"})

# Bound for the "worker is inside the blocked section" poll below. Each iteration
# is a single `anyio.sleep(0)` checkpoint (no wall-clock), so this is just a
# generous ceiling on scheduler hand-offs, not a timeout.
_ENTRY_POLL_TRIES = 100_000


async def _await_inside(predicate: Callable[[], bool]) -> bool:
    """
    Yield (`sleep(0)` only) until `predicate()` holds or the bound is exhausted.

    The loop-facing `entered` event signals when a worker STARTS (before it runs
    the stub call and enters the lock-guarded blocked section), so a test that
    asserts a stub invariant the instant `entered` fires races the worker. This
    closes that gap deterministically without a wall-clock sleep: it spins on
    `anyio.sleep(0)` checkpoints until the worker has provably reached the state
    the test is about to assert on. Returns the final `predicate()` value so the
    caller can assert on a settled observation.
    """
    for _ in range(_ENTRY_POLL_TRIES):
        if predicate():
            return True
        await anyio.sleep(0)
    return predicate()


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
            try:
                await entered.wait()
                # `entered` fires as the worker starts, before `execute` records;
                # poll until it has, then release. ALWAYS release in `finally` so
                # a missed observation cannot strand the non-cancellable worker
                # and deadlock the group at exit.
                await _await_inside(lambda: stub.execute_call_count == 1)
            finally:
                stub.release()  # unblock the worker -- no sleep
        assert stub.execute_call_count == 1
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
        worker_tid = -1
        async with anyio.create_task_group() as tg:
            tg.start_soon(gated, stub.execute, "SELECT 1")
            try:
                await entered.wait()
                # `entered` fires before `execute` appends its thread id, so poll
                # until it has, capture it, and ALWAYS release in `finally` -- an
                # `IndexError` from reading [0] too early would otherwise unwind
                # the group while the non-cancellable worker is still blocked.
                await _await_inside(lambda: bool(stub.execute_thread_ids))
                worker_tid = stub.execute_thread_ids[0]
            finally:
                stub.release()
        assert worker_tid != threading.get_ident()

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
        observed_max = 0
        async with anyio.create_task_group() as tg:
            tg.start_soon(gated_a, stub.execute, "SELECT 1")
            tg.start_soon(gated_b, stub.execute, "SELECT 2")
            try:
                await entered_a.wait()
                await entered_b.wait()
                # `entered` fires as each worker STARTS, before it enters the
                # stub's lock-guarded blocked section, so poll the high-water mark
                # until both workers are provably inside. Asserting on the bare
                # `entered` events races the count and, on a miss, would unwind the
                # group while the non-cancellable workers are still blocked ->
                # deadlock. ALWAYS release in `finally` so that can never happen.
                await _await_inside(lambda: stub.max_concurrent_in_execute == 2)
                observed_max = stub.max_concurrent_in_execute
            finally:
                stub.release()  # release both blocked calls; let the group finish
        assert observed_max == 2


class TestVirtualClock:
    """`virtual_clock` makes anyio deadlines fire on virtual time, no wall-clock."""

    @pytest.mark.anyio
    async def test_trio_virtual_clock(self, anyio_backend_name: str) -> None:
        """Trio leg: `move_on_after(3600)` fires on VIRTUAL time, no wall-clock spent."""
        if anyio_backend_name != "trio":
            pytest.skip("trio-leg virtual-clock assertion (MockClock injected at runner)")
        # REAL wall-clock watchdog (T-23-08): a virtual 3600s deadline must fire
        # in a tiny fraction of a real second. A nested virtual fail_after would
        # autojump to ITS deadline first under MockClock, so the watchdog must be
        # measured on the monotonic wall clock, not on anyio virtual time.
        wall_start = time.monotonic()
        with virtual_clock(anyio_backend_name):
            with anyio.move_on_after(3600) as scope:
                await anyio.Event().wait()  # never set -- only the deadline ends it
        wall_elapsed = time.monotonic() - wall_start
        assert scope.cancelled_caught  # the virtual 3600s deadline fired
        assert wall_elapsed < _WALL_CLOCK_BUDGET_S  # but no real time was consumed

    @pytest.mark.anyio
    async def test_asyncio_virtual_clock(self, anyio_backend_name: str) -> None:
        """Asyncio leg (A1): `move_on_after(3600)` fires under aiotools `patch_loop()`."""
        if anyio_backend_name != "asyncio":
            pytest.skip("asyncio-leg virtual-clock assertion (aiotools patch_loop)")
        # Same real wall-clock watchdog shape; this RESOLVES open-question A1 --
        # does anyio's asyncio move_on_after/fail_after honour the aiotools
        # VirtualClock the facade installs via patch_loop()?
        wall_start = time.monotonic()
        with virtual_clock(anyio_backend_name):
            with anyio.move_on_after(3600) as scope:
                await anyio.Event().wait()
        wall_elapsed = time.monotonic() - wall_start
        assert scope.cancelled_caught
        assert wall_elapsed < _WALL_CLOCK_BUDGET_S


def test_dual_parametrization(request: pytest.FixtureRequest) -> None:
    """
    Every async self-test in this module is parametrized over both backend ids.

    Inspects the collected node ids (typed strings) rather than each item's
    `callspec` (untyped under basedpyright strict): a backend-parametrized item's
    id ends in `[asyncio]` or `[trio]`, so the set of suffixes across this
    module's async tests must equal both ids.
    """
    seen_ids: set[str] = set()
    for item in request.session.items:
        node_id = item.nodeid
        if not node_id.startswith("tests/_async_harness/test_harness.py::"):
            continue
        for backend_id in _BACKEND_IDS:
            if node_id.endswith(f"[{backend_id}]"):
                seen_ids.add(backend_id)
    assert seen_ids == _BACKEND_IDS
