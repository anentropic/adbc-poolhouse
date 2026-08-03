"""
Regression: a cancellation that arrives after the worker finished aborts nothing (D-25-10).

[`cancellable_offload`][adbc_poolhouse._async._cancel.cancellable_offload]'s watcher
parks on a `done` event and, if cancelled, fires the driver's `adbc_cancel` and runs
the connection's poison-recovery (`on_abort` --- `AsyncConnection.invalidate`, which
drops the connection from the pool). That is right while the worker is inside the
driver call. It is wrong once the worker is out.

Setting the event does not resume the parked watcher, it only schedules it. A
cancellation delivered in the window between those two things reaches the watcher with
`done` already set: the driver call is over, the pool token is released, and the
result is in hand. The pre-fix watcher could not tell that apart from a live call, so
it fired `adbc_cancel` at a statement that had already completed and invalidated a
connection nothing had poisoned --- evicting a healthy connection from the pool on
every occurrence. The fix checks the event before aborting.

**Why the event is wrapped rather than raced.** The window is one scheduler turn wide,
so provoking it by timing would be exactly the flaky, load-dependent test this suite
refuses to ship. Instead the `done` event is wrapped for the duration of the call by a
delegate that cancels the caller's scope immediately after the real event is set. The
cancellation is genuine and anyio delivers it through its own machinery; only its
*timing* is pinned. The wrapper asserts the state it is there to create
(`done.is_set()` is True at the moment of cancelling), so it cannot silently decay into
testing the ordinary mid-call abort path.

Both anyio backends are covered by the `anyio_backend` fixture; the interleaving is
reachable on each, and pre-fix both fire the spurious abort.
"""

from __future__ import annotations

import importlib
import threading
from typing import TYPE_CHECKING, Any

import anyio
import pytest

from adbc_poolhouse._async._cancel import cancellable_offload

if TYPE_CHECKING:
    from collections.abc import Callable

# `tests/async/` is not importable by dotted path (`async` is a keyword), so the
# sibling helper module is loaded via importlib (mirrored from the EDGE suites).
_helpers = importlib.import_module("tests.async._edge_helpers")
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks

_REAL_EVENT = anyio.Event


def _cancel_after_set_event(scope_box: dict[str, anyio.CancelScope]) -> Callable[[], Any]:
    """
    Build an `anyio.Event` stand-in that cancels a scope the moment it is set.

    The returned factory replaces `anyio.Event` for exactly one
    `cancellable_offload` call, so the `done` event it builds delegates to a real
    event and, once set, cancels `scope_box["scope"]` and yields so the cancellation
    is delivered while `wait()` is still on the stack. That reproduces the
    finished-worker interleaving deterministically instead of racing for it.

    Args:
        scope_box: Mapping holding the caller's cancel scope under `"scope"`,
            populated after the scope is entered.

    Returns:
        A zero-argument factory usable as a drop-in for `anyio.Event`.
    """
    armed = {"value": True}

    class _CancelAfterSetEvent:
        def __init__(self) -> None:
            self._event = _REAL_EVENT()

        def set(self) -> None:
            self._event.set()

        def is_set(self) -> bool:
            return self._event.is_set()

        async def wait(self) -> None:
            await self._event.wait()
            if armed["value"]:
                armed["value"] = False
                # The state this whole test exists to create: the worker is out and
                # the event is set, and only now does the cancellation land.
                assert self._event.is_set()
                scope_box["scope"].cancel()
                await anyio.sleep(0)  # deliver the real cancellation here

    return _CancelAfterSetEvent


class _DriverError(Exception):
    """Stand-in for a driver error raised by the worker in the same turn as the cancel."""


@pytest.mark.anyio
@pytest.mark.parametrize("worker_raises", [False, True], ids=["worker-returned", "worker-raised"])
async def test_cancel_after_worker_finished_does_not_abort(
    anyio_backend_name: str, monkeypatch: pytest.MonkeyPatch, worker_raises: bool
) -> None:
    """
    D-25-10: a cancellation landing after `done` is set fires no abort and no recovery.

    Runs a worker that finishes, then delivers a real cancellation to the watcher at the
    one moment the event is set but the watcher has not yet resumed. Nothing about that
    call needs aborting: `adbc_cancel` must not fire and the poison-recovery must not
    run, or a healthy connection is dropped from the pool. The cancellation itself still
    propagates --- the caller's scope catches it, and the call does not hand back a value
    (WR-01/WR-04).

    Both worker outcomes are covered, because they unwind differently. When the worker
    *raised* in that same turn, its error and the cancellation exist at once, and the
    caller must still see the cancellation alone. Skipping the abort without also
    routing this case down the cancel branch surfaced the driver error instead under
    asyncio, and a two-member `ExceptionGroup` of the error next to the cancellation
    under trio --- the WR-02 group-leak shape, in a new path.
    """
    del anyio_backend_name
    lock = threading.Lock()
    state = {"inside": 0, "cancelled": 0, "aborted": 0}
    returned: dict[str, object] = {}
    scope_box: dict[str, anyio.CancelScope] = {}

    def fn() -> str:
        with lock:
            state["inside"] += 1
        if worker_raises:
            raise _DriverError("driver failed in the same turn as the cancel")
        return "clean result"  # completes normally: never interrupted, never poisoned

    def adbc_cancel() -> None:
        with lock:
            state["cancelled"] += 1

    async def on_abort() -> None:
        with lock:
            state["aborted"] += 1

    limiter = anyio.CapacityLimiter(1)
    monkeypatch.setattr(anyio, "Event", _cancel_after_set_event(scope_box))
    escaped: dict[str, BaseException] = {}

    with anyio.CancelScope() as scope:
        scope_box["scope"] = scope
        # Capture whatever escapes before the scope absorbs it: the bare/group and
        # cancellation/driver-error distinctions are exactly what this pins.
        try:
            returned["v"] = await cancellable_offload(
                adbc_cancel, fn, limiter=limiter, on_abort=on_abort
            )
        except BaseException as exc:  # noqa: BLE001
            escaped["exc"] = exc
            raise

    assert state["inside"] == 1, "the worker never ran, so the race was not exercised"
    assert scope.cancelled_caught, "the cancellation did not reach the caller's scope"
    # The point of the fix: a finished call is not aborted and not recovered from.
    assert state["cancelled"] == 0, "adbc_cancel fired at an already-completed call"
    assert state["aborted"] == 0, "poison-recovery invalidated a connection nothing poisoned"
    # A cancelled call still never hands back a value (WR-01/WR-04).
    assert "v" not in returned
    # A cancelled call raises the cancellation ALONE --- never the worker's own error,
    # and never an opaque group carrying both (the regression the parametrization pins).
    exc = escaped.get("exc")
    assert isinstance(exc, anyio.get_cancelled_exc_class()), f"expected a cancellation, got {exc!r}"
    assert not isinstance(exc, BaseExceptionGroup)
    assert not isinstance(exc, _DriverError)
