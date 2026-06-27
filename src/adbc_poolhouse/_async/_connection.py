"""
Async connection/cursor contracts (interface-first; bodies land in Plan 03).

This module fixes the *interface* that
[`AsyncPool.connect`][adbc_poolhouse._async._pool.AsyncPool.connect] returns, so
the pool and factory are fully typeable and basedpyright-strict-clean in this
plan. The behavioral bodies --- the `_in_use` aliasing guard
(`ConnectionBusyError`), the shielded check-in, the synchronous `cursor()`
accessor, and the offloaded `execute` / `fetch_arrow_table` --- are implemented in
Plan 03 against these fixed signatures.

The constructor contract is load-bearing and frozen here:
`AsyncConnection(fairy, limiter)` and `AsyncCursor(sync_cursor, limiter, owner)`.
Plan 03 fills the bodies without changing these signatures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType

    import pyarrow
    from anyio import CapacityLimiter
    from sqlalchemy.pool import PoolProxiedConnection


class AsyncCursor:
    """
    Async wrapper over a sync ADBC cursor (contract; body in Plan 03).

    One `AsyncCursor` belongs to exactly one task, mirroring the synchronous
    connection-per-thread convention. Every blocking call (`execute`,
    `executemany`, `fetch_arrow_table`) is offloaded through the owning pool's
    limiter in Plan 03; here only the typed surface and the constructor contract
    are fixed.
    """

    def __init__(
        self,
        sync_cursor: object,
        limiter: CapacityLimiter,
        owner: AsyncConnection,
    ) -> None:
        """
        Bind a sync cursor to its limiter and owning connection.

        Args:
            sync_cursor: The underlying ADBC dbapi cursor to wrap.
            limiter: The owning pool's `anyio.CapacityLimiter`, used to bound
                every offloaded call.
            owner: The `AsyncConnection` this cursor was opened on. Used by Plan
                03 to enforce the single-task aliasing guard.
        """
        self._cursor = sync_cursor
        self._limiter = limiter
        self._owner = owner

    async def execute(self, operation: str, parameters: object = None) -> None:
        """
        Execute a statement on a worker thread (body in Plan 03).

        Args:
            operation: The SQL text to execute.
            parameters: Optional bound parameters.

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncCursor.execute is implemented in Plan 03")

    async def executemany(self, operation: str, seq_of_parameters: object) -> None:
        """
        Execute a statement for many parameter sets (body in Plan 03).

        Args:
            operation: The SQL text to execute.
            seq_of_parameters: The sequence of parameter sets.

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncCursor.executemany is implemented in Plan 03")

    async def fetch_arrow_table(self) -> pyarrow.Table:
        """
        Materialize results as a `pyarrow.Table` (body in Plan 03).

        Returns:
            A fully-materialized `pyarrow.Table` (safe after check-in; streaming
            readers are deferred to v1.4.x).

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncCursor.fetch_arrow_table is implemented in Plan 03")

    async def close(self) -> None:
        """
        Close the underlying cursor on a worker thread (body in Plan 03).

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncCursor.close is implemented in Plan 03")


class AsyncConnection:
    """
    Async wrapper over a pooled ADBC connection (contract; body in Plan 03).

    Returned by [`AsyncPool.connect`][adbc_poolhouse._async._pool.AsyncPool.connect].
    It holds a checked-out sync pool connection (a SQLAlchemy
    `PoolProxiedConnection`) for its lifetime but borrows a limiter token only for
    the duration of each individual offloaded call (transient-token model,
    D-24-01) --- it retains no token between calls.

    One `AsyncConnection` belongs to exactly one task. Plan 03 adds a cheap
    `_in_use` guard that rejects a second concurrent caller with
    [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] rather than
    silently serializing (D-24-03). The check-in (`close` / `__aexit__`) is
    shielded from cancellation in Plan 03 so a connection is never returned to the
    pool in an unknown state.
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

    def cursor(self) -> AsyncCursor:
        """
        Open a cursor on this connection (synchronous accessor; body in Plan 03).

        Returns:
            An `AsyncCursor` bound to this connection and its limiter.

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncConnection.cursor is implemented in Plan 03")

    async def commit(self) -> None:
        """
        Commit the current transaction on a worker thread (body in Plan 03).

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncConnection.commit is implemented in Plan 03")

    async def rollback(self) -> None:
        """
        Roll back the current transaction on a worker thread (body in Plan 03).

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncConnection.rollback is implemented in Plan 03")

    async def close(self) -> None:
        """
        Return the connection to the pool (shielded check-in; body in Plan 03).

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncConnection.close is implemented in Plan 03")

    async def __aenter__(self) -> AsyncConnection:
        """
        Enter the async context, returning this connection (body in Plan 03).

        Returns:
            This `AsyncConnection`.

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncConnection.__aenter__ is implemented in Plan 03")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Exit the async context, returning the connection (body in Plan 03).

        Args:
            exc_type: The exception type if the block raised, else `None`.
            exc: The exception instance if the block raised, else `None`.
            tb: The traceback if the block raised, else `None`.

        Raises:
            NotImplementedError: Always, until Plan 03 supplies the body.
        """
        raise NotImplementedError("AsyncConnection.__aexit__ is implemented in Plan 03")
