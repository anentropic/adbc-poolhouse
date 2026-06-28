"""
The async connection wrapper: sync `cursor()`, offloaded txn surface, shielded check-in.

[`AsyncConnection`][adbc_poolhouse._async._connection.AsyncConnection] wraps a
single checked-out sync pool connection (a SQLAlchemy `PoolProxiedConnection`,
the "fairy") and adds the async surface. It holds the fairy for its whole lifetime
but borrows a limiter token only for the duration of each individual offloaded
call (transient-token model, D-24-01), so it retains no token between calls.

Three structural guarantees live here:

- **Aliasing rejection (D-24-03).** A cheap `_in_use` flag is set on entry to any
  offloading call and cleared on exit. A second concurrent caller --- a cursor on
  the same connection driven from another task, or a direct `commit`/`close` ---
  hits the flag and gets [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError]
  rather than silently interleaving statements inside one transaction. The
  check-and-set runs in one synchronous span with no `await` between the read and
  the write, so it is race-free on the single-threaded event loop.
- **Synchronous `cursor()` (ACONN-03).** `cursor()` is a plain `def`: the dbapi
  `cursor()` does no I/O, so it is not offloaded and needs no `await`.
- **Shielded check-in (ACONN-02/06).** `close()` and `__aexit__` run the offloaded
  `fairy.close()` inside `anyio.CancelScope(shield=True)`, so a cancellation
  arriving mid-check-in cannot abandon a connection in an unknown state. The
  offloaded `fairy.close()` fires the sync pool's existing `reset` event
  (`_release_arrow_allocators`) unchanged, so Arrow allocators are released on the
  normal path with no new cleanup code.

The check-in routes through the fairy's own methods (`fairy.cursor`,
`fairy.commit`, `fairy.rollback`, `fairy.close`), which SQLAlchemy's
`_ConnectionFairy` proxies to the underlying dbapi `Connection`; no
`driver_connection` unwrap is needed (Open Q1/A3, settled by probe against the
DuckDB driver).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import anyio

from adbc_poolhouse._async._cursor import AsyncCursor
from adbc_poolhouse._async._offload import offload
from adbc_poolhouse._exceptions import ConnectionBusyError

if TYPE_CHECKING:
    from types import TracebackType

    from anyio import CapacityLimiter
    from sqlalchemy.pool import PoolProxiedConnection

    from adbc_poolhouse._async._cursor import _SyncCursor


class AsyncConnection:
    """
    Async wrapper over a pooled ADBC connection.

    Returned by [`AsyncPool.connect`][adbc_poolhouse._async._pool.AsyncPool.connect].
    It holds a checked-out sync pool connection (a SQLAlchemy
    `PoolProxiedConnection`) for its lifetime but borrows a limiter token only for
    the duration of each individual offloaded call (transient-token model,
    D-24-01) --- it retains no token between calls.

    One `AsyncConnection` belongs to exactly one task. A cheap `_in_use` guard
    rejects a second concurrent caller (another task using a cursor on this
    connection, or a concurrent `commit`/`close`) with
    [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] rather than
    silently serializing (D-24-03). The check-in (`close` / `__aexit__`) is
    shielded from cancellation so a connection is never returned to the pool in an
    unknown state.

    Attributes:
        _in_use: True while an offloaded call on this connection (or one of its
            cursors) is in flight. The single-task aliasing guard; deliberately a
            plain bool, never a serializing lock, so a second concurrent caller is
            rejected rather than queued (D-24-03).

    Example:
        ```python
        import adbc_poolhouse

        pool = await adbc_poolhouse.create_async_pool(config)
        async with await pool.connect() as conn:
            cursor = conn.cursor()  # synchronous, no await
            await cursor.execute("SELECT 42")
            table = await cursor.fetch_arrow_table()
            await conn.commit()
        await adbc_poolhouse.close_async_pool(pool)
        ```
    """

    def __init__(
        self,
        fairy: PoolProxiedConnection,
        limiter: CapacityLimiter,
    ) -> None:
        """
        Bind a checked-out sync connection to its pool limiter.

        Args:
            fairy: The checked-out sync pool connection (SQLAlchemy
                `PoolProxiedConnection`) returned by the underlying
                `QueuePool.connect()`.
            limiter: The owning pool's `anyio.CapacityLimiter`, threaded into
                every offloaded call on this connection and its cursors.
        """
        self._fairy = fairy
        self._limiter = limiter
        self._in_use = False

    def _enter_offload(self) -> None:
        """
        Claim this connection for one offloaded call, or reject an aliased caller.

        Raises `ConnectionBusyError` if the connection is already executing a call
        (from this task or another), otherwise marks it busy. The read of
        `_in_use` and the write that sets it run in one synchronous span with NO
        `await` between them, so on the single-threaded event loop two tasks can
        never both observe `_in_use == False` and both proceed (Pitfall 3 / the
        check-and-set race). Always paired with `_exit_offload` in a `finally`.

        Raises:
            ConnectionBusyError: If an offloaded call on this connection is already
                in flight.
        """
        if self._in_use:
            raise ConnectionBusyError
        self._in_use = True

    def _exit_offload(self) -> None:
        """Release the connection after an offloaded call (call from `finally`)."""
        self._in_use = False

    def cursor(self) -> AsyncCursor:
        """
        Open a cursor on this connection.

        This is a plain synchronous accessor (NOT `async`): the dbapi `cursor()`
        does no I/O, so there is nothing to offload and no token to borrow. The
        returned cursor guards this connection's `_in_use` flag, so concurrent use
        of two cursors on one connection --- like concurrent use of the connection
        itself --- raises `ConnectionBusyError`.

        Returns:
            An `AsyncCursor` bound to a fresh dbapi cursor and to this connection.
        """
        # SQLAlchemy types the fairy's cursor as the generic PEP 249 DBAPICursor;
        # at runtime it is the ADBC cursor, which adds `fetch_arrow_table`. Bridge
        # the narrow static type to the structural ADBC surface the wrapper needs.
        sync_cursor = cast("_SyncCursor", self._fairy.cursor())
        return AsyncCursor(sync_cursor, self._limiter, self)

    async def commit(self) -> None:
        """
        Commit the current transaction on a worker thread.

        Offloads `fairy.commit()` through the pool limiter while holding the
        `_in_use` guard, so a concurrent commit/query on this connection is
        rejected with `ConnectionBusyError`.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.
        """
        self._enter_offload()
        try:
            await offload(self._fairy.commit, limiter=self._limiter)
        finally:
            self._exit_offload()

    async def rollback(self) -> None:
        """
        Roll back the current transaction on a worker thread.

        Offloads `fairy.rollback()` through the pool limiter while holding the
        `_in_use` guard.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.
        """
        self._enter_offload()
        try:
            await offload(self._fairy.rollback, limiter=self._limiter)
        finally:
            self._exit_offload()

    async def close(self) -> None:
        """
        Return the connection to the pool (shielded check-in).

        Offloads `fairy.close()` --- which returns the connection to the sync pool
        and fires the pool's `reset` event (`_release_arrow_allocators`) unchanged
        --- inside `anyio.CancelScope(shield=True)`, so a cancellation arriving
        mid-check-in cannot abandon the connection in an unknown state (ACONN-02).
        The `_in_use` guard is held across the shielded offload.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.
        """
        self._enter_offload()
        try:
            with anyio.CancelScope(shield=True):
                await offload(self._fairy.close, limiter=self._limiter)
        finally:
            self._exit_offload()

    async def invalidate(self) -> None:
        """
        Drop a poisoned connection from the pool (offloaded, shielded).

        A connection whose in-flight call was cancelled is genuinely poisoned ---
        the driver leaves it with an aborted transaction, so reusing it fails
        (D-25-03). This drops it instead of returning it: it offloads the fairy's
        `invalidate()`, which detaches the underlying dbapi connection and drives
        the sync pool's `checkedout()` to 0, inside `anyio.CancelScope(shield=True)`
        so a second cancellation arriving mid-recovery cannot leave the pool
        accounting wrong (CANCEL-02 / D-25-07).

        Like `__aexit__`, it bypasses the `_in_use` guard: the cursor method that
        drives this recovery still holds `_in_use` across its own `try`/`finally`,
        so a connection left marked busy by the cancelled call is still reclaimed.

        It is the poison-recovery counterpart to `close`: invalidate is the cancel
        path, `close` the normal check-in. A `close()` after an `invalidate()` is a
        safe no-op (probe-confirmed).
        """
        with anyio.CancelScope(shield=True):
            await offload(self._fairy.invalidate, limiter=self._limiter)

    async def __aenter__(self) -> AsyncConnection:
        """
        Enter the async context.

        Returns:
            This `AsyncConnection`.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Return the connection to the pool on context exit (shielded check-in).

        Runs the offloaded `fairy.close()` inside `anyio.CancelScope(shield=True)`
        regardless of whether the body raised, so the connection always goes back
        to the pool and the `reset` event fires. The check-in is reclaim-safe: even
        if `__aenter__`/post-checkout setup raised before the body ran, exiting the
        context still closes the fairy, so the sync pool's `checkedout()` returns to
        0 and no connection leaks (EDGE-18). Bypasses the `_in_use` guard so a
        connection left marked busy by a failed in-flight call is still reclaimed.

        Args:
            exc_type: The exception type if the block raised, else `None`.
            exc: The exception instance if the block raised, else `None`.
            tb: The traceback if the block raised, else `None`.
        """
        with anyio.CancelScope(shield=True):
            await offload(self._fairy.close, limiter=self._limiter)
