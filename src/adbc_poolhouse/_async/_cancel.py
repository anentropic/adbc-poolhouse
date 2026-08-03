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

Firing the abort is only half of it: the poison-recovery that follows CLOSES the
connection, so it must not run until the aborted worker has actually left the
driver call (D-25-09). Two threads touching one ADBC connection is what the spec
forbids, and DuckDB deadlocks on it outright --- the watcher therefore waits on the
worker's `done` event before recovering.

The same event decides whether to abort at all (D-25-10). A cancellation that lands
after the worker has finished has nothing to abort: the watcher checks the event
before firing, so a completed call is never sent an `adbc_cancel` and a healthy
connection is never invalidated out of the pool.

The literal `anyio.to_thread.run_sync` chokepoint stays in `_offload.py`: this
module calls `offload`, never `to_thread.run_sync` directly, so the
`scan_async_package` source guard still audits the offload discipline in exactly
one place (D-25-08 / RESEARCH Pitfall 5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, TypeVarTuple, Unpack

import anyio
from anyio import get_cancelled_exc_class

from adbc_poolhouse._async._offload import offload

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from anyio import CapacityLimiter

_T = TypeVar("_T")
_Ts = TypeVarTuple("_Ts")


async def cancellable_offload(
    adbc_cancel: Callable[[], None],
    fn: Callable[[Unpack[_Ts]], _T],
    *args: Unpack[_Ts],  # noqa: UP044  Unpack[] spelling for 3.11 clarity (PKG-05)
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

    A worker that has already finished is treated the same way (D-25-10). If the
    cancellation lands after the worker set `done` --- reachable on both backends,
    since setting the event only schedules the parked watcher rather than resuming it
    --- then the driver call is over, its token is released, and its result or error is
    in hand. There is nothing to abort and nothing poisoned to recover, so the watcher
    skips both and simply lets the cancellation propagate. Without that check the
    library fired `adbc_cancel` at a completed statement and invalidated a healthy
    connection, evicting it from the pool for no reason.

    When the worker had started and is still inside the call, the watcher fires
    `adbc_cancel()` inside `anyio.CancelScope(shield=True)` (so a second cancellation
    arriving during the abort cannot abort the abort --- `adbc_cancel` fires exactly
    once, D-25-07) and
    sets `aborted_by_us` immediately, so the worker's resulting error is recognised
    as OUR interrupt by that flag alone (D-25-02), never by sniffing its type or
    message. Still shielded, it then waits for the aborted worker to LEAVE the driver
    call --- the same `done` event the worker sets in its `finally` --- and only then
    awaits `on_abort()` if supplied (the connection's poison-recovery).

    That ordering is load-bearing (D-25-09). `on_abort` is typically
    `AsyncConnection.invalidate`, which closes the connection, and closing a
    connection whose worker thread is still unwinding out of the C call is the
    concurrent single-connection access ADBC forbids: DuckDB deadlocks on it and
    wedges the worker permanently, which --- with `offload` running
    `abandon_on_cancel=False` --- hangs the awaiting task forever, beyond the reach of
    any enclosing `move_on_after`. Waiting first introduces no new hang class,
    because that same `abandon_on_cancel=False` means the task group could not exit
    without joining the worker regardless; the wait only moves the join earlier, ahead
    of the close instead of after it. It is the two-thread-on-one-connection hazard
    CR-34-01 fixed for the no-op-cancel metadata reader, one step further in: there
    the worker could not be aborted at all, here it can, but the abort takes non-zero
    time and the recovery has to wait it out. A stub worker that returns the instant
    `adbc_cancel` fires makes the wait a no-op, which is exactly why the stub-driven
    cancel suites never saw the race.

    If `on_abort` itself raises (WR-02) its exception
    is captured in `abort_error` and surfaced *bare* on the cancel branch --- it is
    the actionable failure, raised in place of the expected driver interrupt rather
    than riding out as an opaque multi-member `ExceptionGroup` next to it. The
    watcher always re-raises the cancellation it caught --- never swallows it
    (D-25-06).

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
    `except` branch and `adbc_cancel` is never called. A cancellation arriving in that
    same scheduler turn does enter the `except` branch, but finds the event set and
    leaves the finished call alone (D-25-10). That same `finally` is what the cancel
    path waits on before recovering (D-25-09): the worker sets the `Event` once
    `offload` has returned, which is after it has released its pool token, so a
    poison-recovery reaching the driver finds the connection genuinely quiescent.

    On the **cancel path** the just-aborted worker's blocking call typically
    returns by *raising* the driver's interrupt error (the live DuckDB probe
    raises `ProgrammingError("...INTERRUPT Error: Interrupted!")`), so the task
    group surfaces a single-member `ExceptionGroup` carrying that interrupt rather
    than collapsing to the framework cancellation. Because `aborted_by_us` is set,
    this helper recognises that interrupt as the expected side-effect of its own
    `adbc_cancel` (D-25-02 --- identified by the flag, never by sniffing the error
    type or message), swallows it, and re-raises the cancellation rather than
    returning a value (WR-01/WR-04): it surfaces an enclosing cancellation if one
    is pending at the `await anyio.sleep(0)` checkpoint (a caller's `fail_after` /
    `move_on_after` / `scope.cancel`), and otherwise raises
    `get_cancelled_exc_class()`, so a cancelled call can never return `None`/stale
    as though the query had succeeded. If the poison-recovery failed, the captured
    `abort_error` is raised bare here instead, so that failure is never lost behind
    the expected interrupt. A stub worker that returns cleanly on `adbc_cancel`
    produces no interrupt at all, so the cancel path simply re-raises the framework
    cancellation without reaching the interrupt-swallowing logic.

    On the **non-cancel path** (`aborted_by_us` stays `False`) a genuine worker
    `AdbcError` exits the task group wrapped in a single-member `ExceptionGroup`;
    this helper unwraps it via `eg.exceptions[0]` so the caller sees the bare
    `AdbcError` with its exact type and off-loop worker frame intact, preserving
    the Phase 24 EDGE-17 contract (EDGE-19).

    Args:
        adbc_cancel: The driver's thread-safe cancel hook (e.g.
            `cursor.adbc_cancel`). Called once, shielded, from the loop thread
            only when the surrounding scope is cancelled while the worker is
            genuinely running the driver call. Never called on the success path,
            nor when the worker was cancelled while still queued for a token, nor
            when the worker finished before the cancellation reached the watcher
            (D-25-10).
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
            started and when it had already finished (D-25-10), so a clean
            (never-poisoned) connection is not invalidated in either case.
            Run only once the aborted worker has left the driver call (D-25-09), so
            a recovery that closes the connection never races the worker still
            unwinding out of it.

    Returns:
        Whatever `fn(*args)` returns --- only on the success path. The cancel path
        never returns a value (WR-01/WR-04): it always raises.

    Raises:
        BaseException: On the cancel path the framework cancellation (from
            `anyio.get_cancelled_exc_class()`) is raised --- an enclosing pending
            cancellation surfaces at the `await anyio.sleep(0)` checkpoint,
            otherwise a fresh `get_cancelled_exc_class()` is raised so a cancelled
            call never returns a stale/`None` value. A failed `on_abort`
            poison-recovery is re-raised bare on the cancel path, in place of the
            cancellation. A genuine worker error (e.g. an `AdbcError`) is re-raised
            bare on the non-cancel path, unwrapped from its single-member
            `ExceptionGroup`.
    """
    done = anyio.Event()
    result: dict[str, _T] = {}
    worker_started = False
    aborted_by_us = False
    # Set when the cancellation arrived too late to abort anything (D-25-10). It routes
    # the unwind down the SAME cancel branch as `aborted_by_us` --- a cancelled call
    # surfaces the cancellation, never the worker's error --- without having fired
    # `adbc_cancel` or the poison-recovery.
    cancelled_late = False
    # A holder (the same idiom as `result`) so a failed poison-recovery survives the
    # `_watcher` closure without a captured Optional --- mutated, never rebound.
    abort_error: dict[str, BaseException] = {}

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
        nonlocal aborted_by_us, abort_error, cancelled_late
        try:
            await done.wait()  # event-driven park, NOT a poll
        except get_cancelled_exc_class():
            # A set `done` means the worker is already OUT of the driver call, off its
            # pool token, and its result (or error) is in hand: there is nothing left to
            # abort and nothing poisoned to recover from (D-25-10). The cancellation is
            # real and still propagates below --- what is skipped is firing `adbc_cancel`
            # at a statement that has already finished and invalidating a connection that
            # was never poisoned. That interleaving is reachable on both backends: `set()`
            # only schedules the waiting watcher, so a cancellation delivered before it
            # resumes lands here with the event already set.
            if worker_started and not done.is_set():
                with anyio.CancelScope(shield=True):
                    adbc_cancel()  # thread-safe; unblocks the worker, fires ONCE
                    # From here the worker's resulting error is OUR interrupt,
                    # recognised by this flag alone (D-25-02) --- never by sniffing
                    # the error type or message. Set BEFORE `on_abort` so a failing
                    # poison-recovery is still attributed to the cancel path.
                    aborted_by_us = True
                    if on_abort is not None:
                        # D-25-09: let the aborted worker LEAVE the driver call before
                        # recovering. `on_abort` closes the connection, and closing one
                        # whose worker thread is still unwinding out of the C call is the
                        # concurrent single-connection access ADBC forbids --- DuckDB
                        # deadlocks on it and wedges that worker permanently. The worker
                        # sets `done` in its `finally`, so this wait ends exactly when it
                        # is out. It adds no new hang class: `offload` runs
                        # `abandon_on_cancel=False`, so the task group below cannot exit
                        # without joining that same worker anyway --- the wait only moves
                        # the join earlier, ahead of the close instead of after it. Kept
                        # OUTSIDE the `try` so only an `on_abort` failure lands in
                        # `abort_error` (WR-02); the shield makes this wait uncancellable.
                        await done.wait()
                        try:
                            await on_abort()  # poison recovery (D-25-03), shielded
                        except BaseException as exc:  # noqa: BLE001
                            # The poison-recovery itself failed (WR-02). Capture it
                            # so the handler can surface it BARE on the cancel branch,
                            # instead of letting it ride out as an opaque, multi-member
                            # `ExceptionGroup` next to our own expected interrupt.
                            abort_error["exc"] = exc
            elif worker_started:
                # Too late to abort: the worker is already out (D-25-10). Nothing is
                # fired and nothing is recovered, but the call was still cancelled, so
                # flag it to unwind down the cancel branch below rather than the
                # ordinary worker-error path. Otherwise a worker that failed in this
                # same turn would surface its driver error --- or, under trio, a
                # two-member `ExceptionGroup` of that error next to the cancellation ---
                # where every other cancelled call raises the cancellation alone.
                cancelled_late = True
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
        if aborted_by_us or cancelled_late:
            # CANCEL path, entered on either flag (never by sniffing the error's
            # type/message, D-25-02). With `aborted_by_us`, OUR `adbc_cancel` aborted the
            # worker and it returned by raising the driver's interrupt (e.g. DuckDB's
            # `ProgrammingError("...Interrupted!")`), the expected side-effect of the
            # abort. With `cancelled_late` the worker was already out and whatever it
            # carried --- a value or its own error --- belongs to a call the caller has
            # since cancelled (D-25-10). Both unwind the same way: the cancellation is
            # what the caller sees.
            if "exc" in abort_error:
                # The poison-recovery itself failed (WR-02). Surface THAT bare --- it
                # is the actionable error --- in place of the expected interrupt,
                # rather than re-raising an opaque multi-member `ExceptionGroup`
                # carrying both. (Without this, an `on_abort` failure that coincided
                # with the worker's interrupt leaked a two-member group to the caller.)
                raise abort_error["exc"] from None
            # Recovery succeeded (or none was supplied): swallow the expected interrupt
            # and re-raise the cancellation. NEVER return a value here (WR-01/WR-04):
            # yield once so an enclosing cancelled scope (the caller's fail_after /
            # move_on_after / scope.cancel) surfaces its own cancellation at this
            # checkpoint, and if none is pending raise the framework cancellation
            # outright --- a cancelled, poisoned call must never look like a successful
            # `None`/stale result (D-25-05).
            await anyio.sleep(0)
            raise get_cancelled_exc_class() from None
        # NON-cancel path: the task group wraps a lone worker AdbcError in a
        # single-member group. Unwrap to preserve the exact type + off-loop worker
        # frame (EDGE-17/19).
        if len(eg.exceptions) == 1:
            raise eg.exceptions[0] from None
        raise
    if cancelled_late:
        # The task group absorbed the cancellation instead of propagating it, so no
        # group reached the handler above. The call was still cancelled and must not
        # hand back the value the worker happened to finish with (WR-01/WR-04, D-25-05).
        await anyio.sleep(0)
        raise get_cancelled_exc_class() from None
    return result["v"]
