"""
Regression: a failed poison-recovery on the cancel path surfaces BARE (WR-02).

[`cancellable_offload`][adbc_poolhouse._async._cancel.cancellable_offload] runs the
blocking call in a two-task group (watcher + worker). When the scope is cancelled
the watcher fires `adbc_cancel` --- which makes a real driver's in-flight call
return by *raising* its interrupt error --- and then awaits the connection's
`on_abort` poison-recovery (`invalidate`). If that recovery ITSELF raises, two
exceptions exist at once: the worker's expected interrupt and the recovery failure.

The bug this pins: those two used to leave the task group as a single, opaque
two-member `BaseExceptionGroup` (the cancel branch was keyed on a flag set only
*after* a clean recovery, so a failed recovery fell through to the non-cancel
unwrap, which only collapses a one-member group). The caller then saw a
`BaseExceptionGroup` instead of either a cancellation or the actionable recovery
error. The fix recognises OUR interrupt by a flag set the instant `adbc_cancel`
fires (never by sniffing the error), captures a failed `on_abort`, and re-raises
THAT bare on the cancel branch.

The worker here is a hand-rolled blocking callable (not the
[`BlockingStubCursor`][tests._async_harness.stubs.BlockingStubCursor], whose
`adbc_cancel` returns the worker *cleanly* with no interrupt) precisely because the
two-member group only forms when the worker also raises --- the real-driver shape.
Runs on both anyio backends via the `anyio_backend` fixture.
"""

from __future__ import annotations

import importlib
import threading

import anyio
import pytest

from adbc_poolhouse._async._cancel import cancellable_offload

# `tests/async/` is not importable by dotted path (`async` is a keyword), so the
# sibling helper module is loaded via importlib (mirrored from the EDGE suites).
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks


class _DriverInterrupt(Exception):
    """Stand-in for the driver's in-flight interrupt raised after `adbc_cancel`."""


class _RecoveryFailed(Exception):
    """Stand-in for an `on_abort` (invalidate) poison-recovery that itself fails."""


@pytest.mark.anyio
async def test_failed_on_abort_surfaces_bare_not_group(anyio_backend_name: str) -> None:
    """
    A cancel whose worker interrupts AND whose `on_abort` fails raises the recovery error bare.

    Gates a worker inside its blocking call, cancels the scope, and arranges for the
    worker to raise `_DriverInterrupt` once `adbc_cancel` releases it while
    `on_abort` raises `_RecoveryFailed`. The exception that escapes
    `cancellable_offload` must be the bare `_RecoveryFailed` --- the actionable
    failure --- and explicitly NOT a `BaseExceptionGroup` carrying both it and the
    expected interrupt. Also confirms `adbc_cancel` fired exactly once and the
    recovery was attempted.
    """
    del anyio_backend_name
    released = threading.Event()
    lock = threading.Lock()
    state = {"inside": 0, "cancelled": 0, "aborted": 0}

    def fn() -> None:
        with lock:
            state["inside"] += 1
        # Block until `adbc_cancel` releases us, then raise like a real driver whose
        # in-flight call was interrupted (the second member of the old leaked group).
        released.wait(5.0)
        raise _DriverInterrupt("interrupted in flight")

    def adbc_cancel() -> None:
        with lock:
            state["cancelled"] += 1
        released.set()

    async def on_abort() -> None:
        with lock:
            state["aborted"] += 1
        raise _RecoveryFailed("invalidate blew up")

    limiter = anyio.CapacityLimiter(1)
    caught: dict[str, BaseException] = {}

    async with anyio.create_task_group() as tg:

        async def _drive() -> None:
            # Capture exactly what `cancellable_offload` raises, before the outer
            # task group can re-wrap it --- the bare/group distinction is the point.
            try:
                await cancellable_offload(adbc_cancel, fn, limiter=limiter, on_abort=on_abort)
            except BaseException as exc:  # noqa: BLE001
                caught["exc"] = exc

        tg.start_soon(_drive)
        await await_inside(lambda: state["inside"] == 1)
        tg.cancel_scope.cancel()

    assert "exc" in caught, "cancellable_offload returned without raising"
    # The actionable recovery failure, raised BARE (the regression: not a group).
    assert isinstance(caught["exc"], _RecoveryFailed)
    assert not isinstance(caught["exc"], BaseExceptionGroup)
    assert state["cancelled"] == 1  # adbc_cancel fired exactly once
    assert state["aborted"] == 1  # the poison-recovery was attempted
