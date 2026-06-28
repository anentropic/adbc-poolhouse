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
    from collections.abc import Awaitable, Callable

    from anyio import CapacityLimiter

_T = TypeVar("_T")


async def cancellable_offload(
    adbc_cancel: Callable[[], None],
    fn: Callable[..., _T],
    *args: object,
    limiter: CapacityLimiter,
    on_abort: Callable[[], Awaitable[None]] | None = None,
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

    The abort is gated on a `worker_started` flag set by an `on_dispatch` callback
    that `offload` runs once the worker has acquired a limiter token and is about
    to enter the driver call. The callback is bridged from the worker thread back
    to the loop thread, so the flag is written --- and read by the watcher --- on
    the same (loop) thread, with no cross-thread race (CR-01). A cancellation that
    arrives while the worker is still *queued* at token-acquire (the limiter is
    saturated, the worker never touched the driver) leaves `worker_started` False,
    so neither `adbc_cancel` nor the `on_abort` recovery runs: a never-started
    call leaves the connection clean (EDGE-01/07 semantics), and gating the
    recovery this way also avoids a deadlock where a poison-recovery that itself
    needs a limiter token would wait forever behind the very workers saturating
    the limiter.

    When the worker *had* started, the watcher fires `adbc_cancel()` inside
    `anyio.CancelScope(shield=True)` (so a second cancellation arriving during the
    abort cannot abort the abort --- `adbc_cancel` fires exactly once, D-25-07),
    then, still shielded, awaits `on_abort()` if supplied (the connection's
    poison-recovery). `cancelled_by_us` is set to `True` only *after* both
    `adbc_cancel()` and `on_abort()` have returned without raising (WR-02): if the
    poison-recovery itself fails, the flag stays `False` so its exception is
    surfaced on the non-cancel branch rather than silently swallowed. The watcher
    always re-raises the cancellation it caught --- it never swallows it (D-25-06).

    The synchronization that makes `worker_started` safe (CR-01 / IN-01): the flag
    is set by an `on_dispatch` callback that `offload` runs --- bridged from the
    worker thread back to the LOOP thread via `anyio.from_thread.run_sync` ---
    once the worker has acquired its limiter token and immediately before it enters
    the driver call. Both the write (the bridge) and the watcher's read happen on
    the loop thread, so there is no cross-thread read of `worker_started` and no
    TOCTOU window: a cancellation cannot observe a stale `False` for a worker that
    will go on to block in the driver. A worker cancelled while still *queued* for
    a token is never dispatched, so the bridge never runs, the flag stays `False`,
    and neither `adbc_cancel` nor `on_abort` fires (EDGE-01/07: a never-started
    call leaves the connection clean, `invalidate_call_count == 0`).

    On the success or error path the worker releases the watcher by setting the
    `Event` in a `finally`, so the watcher exits cleanly without ever entering its
    `except` branch and `adbc_cancel` is never called.

    On the **cancel path** the just-aborted worker's blocking call typically
    returns by *raising* the driver's interrupt error (the live DuckDB probe
    raises `ProgrammingError("...INTERRUPT Error: Interrupted!")`), so the task
    group surfaces a single-member `ExceptionGroup` carrying that interrupt rather
    than collapsing to the framework cancellation. Because `cancelled_by_us` is
    set, this helper recognises that interrupt as the expected side-effect of its
    own `adbc_cancel` (D-25-02 --- identified by the flag, never by sniffing the
    error type or message), swallows it, and re-raises the cancellation rather than
    returning a value (WR-01/WR-04): it surfaces an enclosing cancellation if one
    is pending at the `await anyio.sleep(0)` checkpoint (a caller's `fail_after` /
    `move_on_after` / `scope.cancel`), and otherwise raises
    `get_cancelled_exc_class()`, so a cancelled call can never return `None`/stale
    as though the query had succeeded. A stub worker that returns cleanly on
    `adbc_cancel` produces no interrupt at all, so the cancel path simply re-raises
    the framework cancellation without reaching this branch.

    On the **non-cancel path** (`cancelled_by_us` stays `False`) a genuine worker
    `AdbcError` exits the task group wrapped in a single-member `ExceptionGroup`;
    this helper unwraps it via `eg.exceptions[0]` so the caller sees the bare
    `AdbcError` with its exact type and off-loop worker frame intact, preserving
    the Phase 24 EDGE-17 contract (EDGE-19).

    Args:
        adbc_cancel: The driver's thread-safe cancel hook (e.g.
            `cursor.adbc_cancel`). Called once, shielded, from the loop thread
            only when the surrounding scope is cancelled while the worker is
            genuinely running the driver call. Never called on the success path
            nor when the worker was cancelled while still queued for a token.
        fn: The blocking callable to run off the event loop (typically a bound
            method of the sync cursor).
        *args: Positional arguments forwarded to `fn`.
        limiter: The pool's dedicated `anyio.CapacityLimiter`, forwarded to
            `offload` by keyword. Bounds how many worker threads run at once and
            is borrowed only for the duration of this one call (transient-token
            model).
        on_abort: Optional async poison-recovery to run (shielded) only when a
            genuinely-started call was aborted by `adbc_cancel` --- typically the
            owning connection's `invalidate`. Skipped when the worker never
            started, so a clean (never-poisoned) connection is not invalidated.

    Returns:
        Whatever `fn(*args)` returns --- only on the success path. The cancel path
        never returns a value (WR-01/WR-04): it always raises.

    Raises:
        BaseException: On the cancel path the framework cancellation (from
            `anyio.get_cancelled_exc_class()`) is raised --- an enclosing pending
            cancellation surfaces at the `await anyio.sleep(0)` checkpoint,
            otherwise a fresh `get_cancelled_exc_class()` is raised so a cancelled
            call never returns a stale/`None` value. A genuine worker error (e.g.
            an `AdbcError`), or a failed `on_abort` poison-recovery, is re-raised
            bare on the non-cancel path, unwrapped from its single-member
            `ExceptionGroup`.
    """
    done = anyio.Event()
    result: dict[str, _T] = {}
    worker_started = False
    cancelled_by_us = False

    def _mark_started() -> None:
        # Runs on the LOOP thread (bridged there by `offload` via
        # `from_thread.run_sync`) once the worker holds a token and is about to
        # enter the driver call. Because both this write and the watcher's read of
        # `worker_started` happen on the loop thread, there is no cross-thread race
        # (CR-01 / IN-01). A worker cancelled while still queued for a token is
        # never dispatched, so this never runs and the flag stays False.
        nonlocal worker_started
        worker_started = True

    async def _watcher() -> None:
        nonlocal cancelled_by_us
        try:
            await done.wait()  # event-driven park, NOT a poll
        except get_cancelled_exc_class():
            if worker_started:
                with anyio.CancelScope(shield=True):
                    adbc_cancel()  # thread-safe; unblocks the worker, fires ONCE
                    if on_abort is not None:
                        await on_abort()  # poison recovery (D-25-03), shielded
                # Set ONLY after both the abort and the recovery returned cleanly
                # (WR-02): if `on_abort` raised, the flag stays False so that
                # failure surfaces on the non-cancel branch rather than being
                # swallowed as the expected driver interrupt.
                cancelled_by_us = True
            raise  # never swallow the cancellation (D-25-06)

    async def _worker() -> None:
        try:
            result["v"] = await offload(
                fn,
                *args,
                limiter=limiter,
                on_dispatch=_mark_started,
            )  # abandon_on_cancel=False
        finally:
            done.set()  # release the watcher on the success/error path

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(_watcher)
            tg.start_soon(_worker)
    except BaseExceptionGroup as eg:
        if cancelled_by_us:
            # CANCEL path: the aborted worker returned by raising the driver's
            # interrupt (e.g. DuckDB's `ProgrammingError("...Interrupted!")`). That
            # error is the expected side-effect of OUR `adbc_cancel`, identified by
            # the flag (D-25-02 --- never by sniffing the type/message), so swallow
            # it. NEVER return a value here (WR-01/WR-04): yield once so an enclosing
            # cancelled scope (the caller's fail_after / move_on_after /
            # scope.cancel) surfaces its own cancellation at this checkpoint, and if
            # none is pending raise the framework cancellation outright --- a
            # cancelled, poisoned call must never look like a successful `None`/stale
            # result (D-25-05).
            await anyio.sleep(0)
            raise get_cancelled_exc_class() from None
        # NON-cancel path: the task group wraps a lone worker AdbcError in a
        # single-member group. Unwrap to preserve the exact type + off-loop worker
        # frame (EDGE-17/19). A failed `on_abort` (WR-02) also reaches here, bare.
        if len(eg.exceptions) == 1:
            raise eg.exceptions[0] from None
        raise
    return result["v"]
