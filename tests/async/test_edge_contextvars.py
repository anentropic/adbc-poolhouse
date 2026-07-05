"""
EDGE-13/14: contextvar copy-in + no-leak-back across a NEW-method offload (`fetch_df`).

Two deterministic single-offload assertions of an `anyio.to_thread.run_sync`
guarantee, pinned on the `fetch_df` path. anyio copies the caller's context into
the worker thread (via `copy_context`) and DISCARDS the worker's mutations, so:

- **EDGE-13 (`copied_in`)**: a contextvar set before `await cur.fetch_df()` is
  visible inside the worker (the probe reads `"outer"`).
- **EDGE-14 (`no_leak`)**: a mutation the worker makes to that contextvar does not
  leak back to the calling task (the caller still reads `"outer"` after the offload
  returns, not the worker's `"inner"`).

The worker-side read/mutate is wired through the stub's shared `on_enter`
attribute (PATTERNS §Pattern 1(a) --- worker-entry probe, zero stub edits): the
probe fires from INSIDE `_block`, on the worker thread, immediately before the
worker parks --- the clean place to observe the copied-in context. (The
`register_on_enter` sibling keys its hook by the CALLING thread's id, which would
never match here: the probe is registered from the loop thread but `_block`
dispatches per-thread hooks by the WORKER thread id. `on_enter` is `_block`'s
documented fallback and is what actually fires.) Because the probe runs before the
block, the gated `fetch_df` worker is released from a real side thread (waiting on
the stub's `entered` `threading.Event`) so the offload can return; `on_enter` is
cleared in the same `finally`.

These legs need NO gating: no `real_clock_watchdog`, no `virtual_clock`, no
`concurrency_marks` (RESEARCH §Pattern-1 --- "EDGE-13/14 need NO gating"). The
real side-thread release keeps the trio `MockClock` from starving a loop-side
releaser, but it is a release mechanism, not a watchdog. Both tests are
`@pytest.mark.anyio` (dual-backend) with `-k`-selectable names (`copied_in` /
`no_leak`).
"""

from __future__ import annotations

import contextvars
import importlib
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from tests._async_harness.stubs import BlockingStubConnection, BlockingStubCursor

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib --- the same shape
# as test_edge_cancel_depth.py, but WITHOUT virtual_clock / real_clock_watchdog /
# concurrency_marks (these deterministic single-offload assertions need no gating).
_helpers = importlib.import_module("tests.async._edge_helpers")

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]

# A module-level contextvar the caller sets and the worker-side probe reads/mutates.
_cv: contextvars.ContextVar[str] = contextvars.ContextVar("trace")


def _release_when_entered(stub_cursor: BlockingStubCursor, budget_s: float = 5.0) -> None:
    """
    Release the gated `fetch_df` worker from a REAL thread once it is inside `_block`.

    The probe registered via `register_on_enter` runs on the worker thread just
    before it parks on the stub's internal event; this side thread waits on the
    sync, clock-independent `entered` `threading.Event` and then `release()`s the
    worker so the offloaded `fetch_df` returns. Done on a real thread (not a loop
    task) so the trio `MockClock` cannot starve it by autojumping virtual time while
    the loop is parked on the off-loop worker.
    """
    if stub_cursor.entered.wait(timeout=budget_s):
        stub_cursor.release()


@pytest.mark.anyio
async def test_contextvar_copied_in_to_fetch_df_worker(
    make_stub_async_connection: _StubFactory,
    anyio_backend_name: str,
) -> None:
    """
    EDGE-13 `copied_in`: a contextvar set before `fetch_df` is visible in the worker.

    Sets `_cv` to `"outer"` on the calling task, registers a worker-side probe via
    `register_on_enter` that records `_cv.get("MISSING")`, then awaits
    `cur.fetch_df()`. The probe fires inside `_block` on the worker thread, so the
    recorded value is what anyio copied into the worker --- asserted to be `"outer"`
    (the copied-in value), proving `to_thread.run_sync`'s `copy_context` carried the
    caller's context across the offload boundary. Dual-backend.
    """
    del anyio_backend_name
    async_conn, stub_conn = make_stub_async_connection()
    cur = async_conn.cursor()
    sc = stub_conn.cursors[0]
    seen: list[object] = []

    def _probe() -> None:
        # Runs INSIDE _block on the worker thread (register_on_enter): record the
        # contextvar value anyio copied into this worker.
        seen.append(_cv.get("MISSING"))

    _cv.set("outer")
    # The `on_enter` shared attribute (not `register_on_enter`) is the correct
    # worker-entry hook here: `register_on_enter` keys the hook by the CALLING
    # thread's id, but this probe is registered from the loop thread while `_block`
    # dispatches by the WORKER thread's id --- so the per-thread hook would never
    # match. `_block` falls back to `on_enter`, which fires on the worker thread
    # inside the blocked section (stubs.py `_block`: hook = ...get(id, self.on_enter)).
    sc.on_enter = _probe
    releaser = threading.Thread(target=_release_when_entered, args=(sc,), daemon=True)
    releaser.start()
    try:
        await cur.fetch_df()
    finally:
        sc.on_enter = None
        releaser.join(timeout=5)
    assert seen == ["outer"]  # the worker saw the copied-in value
    assert sc.df_call_count == 1  # the real fetch_df offload path ran


@pytest.mark.anyio
async def test_contextvar_mutation_does_not_leak_back_from_fetch_df(
    make_stub_async_connection: _StubFactory,
    anyio_backend_name: str,
) -> None:
    """
    EDGE-14 `no_leak`: a worker's contextvar mutation does not leak back to the caller.

    Sets `_cv` to `"outer"`, registers a probe that both reads `_cv` AND mutates it
    to `"inner"` on the worker thread, then awaits `cur.fetch_df()`. After the
    offload returns, the caller's `_cv.get()` is asserted to still be `"outer"`: the
    worker ran on a COPY of the context (anyio's `copy_context`), so its `"inner"`
    write was discarded at the boundary and never reached the calling task.
    Dual-backend.
    """
    del anyio_backend_name
    async_conn, stub_conn = make_stub_async_connection()
    cur = async_conn.cursor()
    sc = stub_conn.cursors[0]
    seen: list[object] = []

    def _probe() -> None:
        # Runs INSIDE _block on the worker thread: read then MUTATE the contextvar.
        # The mutation must NOT leak back to the calling task after the offload.
        seen.append(_cv.get("MISSING"))
        _cv.set("inner")

    _cv.set("outer")
    # `on_enter` (not `register_on_enter`): the probe is registered from the loop
    # thread but `_block` dispatches per-thread hooks by the WORKER thread id, so the
    # shared `on_enter` fallback is what actually fires on the worker (see the
    # copied-in test for the full rationale).
    sc.on_enter = _probe
    releaser = threading.Thread(target=_release_when_entered, args=(sc,), daemon=True)
    releaser.start()
    try:
        await cur.fetch_df()
    finally:
        sc.on_enter = None
        releaser.join(timeout=5)
    assert seen == ["outer"]  # the worker saw the copied-in value...
    assert _cv.get() == "outer"  # ...but its "inner" write was discarded (no leak back)
