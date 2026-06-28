"""
The single off-loop dispatch chokepoint for the async layer (CORE-01/EDGE-25).

Every blocking ADBC call the async wrappers make --- `connect`, `execute`,
`executemany`, `fetch*`, `fetch_arrow_table`, `commit`, `rollback`, `close` ---
goes through [`offload`][adbc_poolhouse._async._offload.offload]. It is the ONLY
place in `adbc_poolhouse._async` that calls `anyio.to_thread.run_sync`, so the
offload discipline (an explicit `limiter=` and the non-cancellable
`abandon_on_cancel=False`) is enforced in exactly one location and audited by the
`scan_async_package` source guard.

The per-pool token is acquired on the loop thread (`async with limiter`) and the
worker dispatch then runs under a per-call unbounded inner limiter: this lets the
caller flip a "worker dispatched" flag SYNCHRONOUSLY on the loop thread before the
worker starts (CR-01), while real concurrency stays bounded by the held per-pool
token. `to_thread.run_sync` borrows on behalf of the current task, so it cannot
re-borrow the per-pool token already held across the `async with`.

The literal `anyio.to_thread.run_sync` attribute chain is kept un-aliased so the
guard's attribute-chain matcher can see it (an aliased re-import would slip the
guard --- RESEARCH Pitfall 5).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, TypeVar, TypeVarTuple, Unpack

import anyio
import anyio.to_thread

if TYPE_CHECKING:
    from collections.abc import Callable

    from anyio import CapacityLimiter

_T = TypeVar("_T")
_Ts = TypeVarTuple("_Ts")


async def offload(
    fn: Callable[[Unpack[_Ts]], _T],
    *args: Unpack[_Ts],  # noqa: UP044  Unpack[] spelling for 3.11 clarity (PKG-05)
    limiter: CapacityLimiter,
    on_dispatch: Callable[[], None] | None = None,
) -> _T:
    """
    Run a blocking callable on a worker thread under the pool's limiter.

    This is the single off-loop dispatch point for the whole async layer. It
    runs `fn(*args)` on an anyio worker thread via `anyio.to_thread.run_sync`,
    bounded by the supplied `limiter`, and awaits the result on the event loop.
    The worker exception (if any) is re-raised by `to_thread.run_sync` with its
    exact type and traceback intact --- this helper deliberately does NOT catch
    or re-wrap it, so an `AdbcError` from the driver reaches the caller unchanged
    (EDGE-17).

    The offload is NON-cancellable (`abandon_on_cancel=False`): if the
    surrounding scope is cancelled while the worker is mid-call, the loop waits to
    join the worker rather than abandoning a connection in an unknown state. The
    cooperative-cancel path (driver `adbc_cancel` to unblock the worker) is wired
    in [`cancellable_offload`][adbc_poolhouse._async._cancel.cancellable_offload].

    Args:
        fn: The blocking callable to run off the event loop (typically a bound
            method of the sync pool, connection, or cursor).
        *args: Positional arguments forwarded to `fn`.
        limiter: The pool's dedicated `anyio.CapacityLimiter`. Passing it by
            keyword is mandatory --- it caps how many worker threads run at once
            and is the compliant call shape the source guard enforces. A token is
            borrowed only for the duration of this one call (transient-token
            model) and released on return, so a connection holds no token between
            calls.
        on_dispatch: Optional zero-argument callback run SYNCHRONOUSLY on the
            event-loop thread the instant the limiter token is acquired and
            immediately BEFORE the worker thread is dispatched. The token is
            acquired here on the loop thread (`async with limiter`), so the
            callback --- and the watcher that later reads anything it wrote ---
            both run on the loop thread with no cross-thread hand-off, closing the
            CR-01 TOCTOU window: a cancellation delivered after acquire cannot
            observe a stale "not started" state, and a cancellation delivered while
            still queued at acquire runs the callback never (the worker was never
            dispatched). The set is synchronous and has no checkpoint between
            acquire and the callback, so it is also immune to the trio `MockClock`
            autojumping a deadline past a worker-thread signal (a
            `from_thread`-bridged flag would be). Defaults to `None` (no hook),
            which keeps every existing caller unchanged.

    Returns:
        Whatever `fn(*args)` returns.
    """
    # Acquire the real per-pool token on the LOOP thread, then fire `on_dispatch`
    # synchronously (no checkpoint between the two), so `cancellable_offload` can
    # flip `worker_started` on the loop thread before the worker is dispatched
    # (CR-01). The blocking call itself runs under a per-call unbounded inner
    # limiter: concurrency is already bounded by the real token held across this
    # `async with`, and `to_thread.run_sync` borrows on behalf of the current task,
    # so it cannot re-borrow the real token we already hold. The literal
    # `anyio.to_thread.run_sync(..., limiter=, abandon_on_cancel=False)` chokepoint
    # is preserved so the `scan_async_package` guard still audits exactly one site.
    async with limiter:
        if on_dispatch is not None:
            on_dispatch()
        inner_limiter = anyio.CapacityLimiter(math.inf)
        return await anyio.to_thread.run_sync(
            lambda: fn(*args),
            limiter=inner_limiter,
            abandon_on_cancel=False,
        )
