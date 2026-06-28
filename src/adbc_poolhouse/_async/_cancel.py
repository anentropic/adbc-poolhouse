"""
Cooperative cancellation for the non-interruptible offload (CANCEL-01, EDGE-19).

An offloaded ADBC call runs on a worker thread that anyio cannot interrupt: the
worker is blocked in the driver's C call and never reaches a cancellation
checkpoint. The one abort path is the driver's thread-safe `adbc_cancel`, and
the only way the event loop can fire it while otherwise parked on the offload is
a second task that receives the framework cancellation.

[`cancellable_offload`][adbc_poolhouse._async._cancel.cancellable_offload]
supplies that structure: a two-task anyio task group pairing a *watcher* (parks
on an `Event`, fires `adbc_cancel` if it is cancelled) with a *worker* (runs the
blocking call through the [`offload`][adbc_poolhouse._async._offload.offload]
chokepoint). The worker stays `abandon_on_cancel=False`, so it is always joined
rather than abandoned in an unknown state.

The literal `anyio.to_thread.run_sync` chokepoint stays in `_offload.py`: this
module calls `offload`, never `to_thread.run_sync` directly, so the
`scan_async_package` source guard still audits the offload discipline in exactly
one place (D-25-08 / RESEARCH Pitfall 5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import anyio
from anyio import get_cancelled_exc_class

from adbc_poolhouse._async._offload import offload

if TYPE_CHECKING:
    from collections.abc import Callable

    from anyio import CapacityLimiter

_T = TypeVar("_T")


async def cancellable_offload(
    adbc_cancel: Callable[[], None],
    fn: Callable[..., _T],
    *args: object,
    limiter: CapacityLimiter,
) -> _T:
    """
    Run a blocking call off the loop, abortable via the driver's `adbc_cancel`.

    Runs `fn(*args)` on a worker thread through the
    [`offload`][adbc_poolhouse._async._offload.offload] chokepoint, but unlike a
    bare offload this call is cooperatively cancellable. A watcher task parks on
    an internal `Event` with zero cost until the worker finishes; if the
    surrounding scope is cancelled while the worker is mid-call, the watcher
    receives the cancellation and fires `adbc_cancel()` from the loop thread to
    abort the in-flight C call. That call is the one documented thread-safe ADBC
    operation, so firing it across the loop/worker boundary is the intended
    interrupt path (CANCEL-01).

    The watcher carries a `cancelled_by_us` flag, set the moment it fires
    `adbc_cancel`, so "this driver error is the side-effect of our own cancel" is
    decided by an explicit flag rather than by sniffing the (non-portable) driver
    error type or message (D-25-02). The `adbc_cancel()` call runs inside
    `anyio.CancelScope(shield=True)` so a second cancellation arriving during the
    abort cannot abort the abort: `adbc_cancel` fires exactly once (D-25-07). The
    watcher always re-raises the cancellation it caught --- it never swallows it
    (D-25-06).

    On the success or error path the worker releases the watcher by setting the
    `Event` in a `finally`, so the watcher exits cleanly without ever entering its
    `except` branch and `adbc_cancel` is never called.

    On the **cancel path** anyio collapses the task group's bundled exceptions
    (the framework cancellation plus the worker's driver interrupt) back into the
    framework cancellation before control reaches the `except BaseExceptionGroup`
    branch, so the caller sees only its own `TimeoutError` (or nothing, for an
    explicit `scope.cancel()`) and never a spurious "Interrupted!". On the
    **non-cancel path** a genuine worker `AdbcError` exits the task group wrapped
    in a single-member `ExceptionGroup`; this helper unwraps it via
    `eg.exceptions[0]` so the caller sees the bare `AdbcError` with its exact type
    and off-loop worker frame intact, preserving the Phase 24 EDGE-17 contract
    (EDGE-19).

    Args:
        adbc_cancel: The driver's thread-safe cancel hook (e.g.
            `cursor.adbc_cancel`). Called once, shielded, from the loop thread
            only when the surrounding scope is cancelled while the worker is
            mid-call. Never called on the success path.
        fn: The blocking callable to run off the event loop (typically a bound
            method of the sync cursor).
        *args: Positional arguments forwarded to `fn`.
        limiter: The pool's dedicated `anyio.CapacityLimiter`, forwarded to
            `offload` by keyword. Bounds how many worker threads run at once and
            is borrowed only for the duration of this one call (transient-token
            model).

    Returns:
        Whatever `fn(*args)` returns.

    Raises:
        BaseException: The framework cancellation (from
            `anyio.get_cancelled_exc_class()`) is re-raised unchanged on the
            cancel path. A genuine worker error (e.g. an `AdbcError`) is re-raised
            bare on the non-cancel path, unwrapped from its single-member
            `ExceptionGroup`.
    """
    done = anyio.Event()
    result: dict[str, _T] = {}
    cancelled_by_us = False

    async def _watcher() -> None:
        nonlocal cancelled_by_us
        try:
            await done.wait()  # event-driven park, NOT a poll
        except get_cancelled_exc_class():
            cancelled_by_us = True
            with anyio.CancelScope(shield=True):
                adbc_cancel()  # thread-safe; unblocks the worker, fires ONCE
            raise  # never swallow the cancellation (D-25-06)

    async def _worker() -> None:
        try:
            result["v"] = await offload(fn, *args, limiter=limiter)  # abandon_on_cancel=False
        finally:
            done.set()  # release the watcher on the success/error path

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(_watcher)
            tg.start_soon(_worker)
    except BaseExceptionGroup as eg:  # NON-cancel path: the worker raised a real error
        # The task group wraps a lone worker AdbcError in a single-member group.
        # Unwrap to preserve the exact type + off-loop worker frame (EDGE-17/19).
        # On the cancel path anyio collapses the bundle to the framework
        # cancellation before reaching here, so a group that arrives is GENUINE.
        if len(eg.exceptions) == 1:
            raise eg.exceptions[0] from None
        raise
    return result["v"]
