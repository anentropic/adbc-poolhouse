"""
The single off-loop dispatch chokepoint for the async layer (CORE-01/EDGE-25).

Every blocking ADBC call the async wrappers make --- `connect`, `execute`,
`executemany`, `fetch*`, `fetch_arrow_table`, `commit`, `rollback`, `close` ---
goes through [`offload`][adbc_poolhouse._async._offload.offload]. It is the ONLY
place in `adbc_poolhouse._async` that calls `anyio.to_thread.run_sync`, so the
offload discipline (an explicit per-pool `limiter=` and the non-cancellable
`abandon_on_cancel=False`) is enforced in exactly one location and audited by the
`scan_async_package` source guard.

The literal `anyio.to_thread.run_sync` attribute chain is kept un-aliased so the
guard's attribute-chain matcher can see it (an aliased re-import would slip the
guard --- RESEARCH Pitfall 5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import anyio.to_thread

if TYPE_CHECKING:
    from collections.abc import Callable

    from anyio import CapacityLimiter

_T = TypeVar("_T")


async def offload(
    fn: Callable[..., _T],
    *args: object,
    limiter: CapacityLimiter,
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
    cooperative-cancel path (driver `adbc_cancel` to unblock the worker) is built
    in a later phase; until then a blocking call always runs to completion.

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

    Returns:
        Whatever `fn(*args)` returns.
    """
    return await anyio.to_thread.run_sync(
        lambda: fn(*args),
        limiter=limiter,
        abandon_on_cancel=False,
    )
