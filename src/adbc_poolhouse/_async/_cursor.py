"""
The async cursor wrapper: offloaded DBAPI surface, materialized Arrow, sync props.

[`AsyncCursor`][adbc_poolhouse._async._cursor.AsyncCursor] wraps a single sync
ADBC dbapi cursor and offloads every blocking call --- `execute`, `executemany`,
`fetchone`, `fetchmany`, `fetchall`, `fetch_arrow_table`, `close` --- through the
owning pool's limiter. Each offloaded call brackets the work with the parent
[`AsyncConnection`][adbc_poolhouse._async._connection.AsyncConnection]'s
`_in_use` guard, so concurrent use of one cursor (or two cursors on one
connection) from two tasks is rejected with
[`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] --- concurrent cursor
use IS concurrent connection use (EDGE-15).

Two deliberate non-offloads:

- **Sync properties (ACUR-07).** `description`, `rowcount`, and `arraysize` are
  plain `@property` reads of the underlying cursor. They touch no I/O, so they are
  NOT offloaded and NOT `async` --- a coroutine property would surface as a
  "coroutine was never awaited" bug (Pitfall 4).
- **Materialized Arrow (ACUR-04/EDGE-21).** `fetch_arrow_table` returns the dbapi
  result unchanged: a fully-materialized `pyarrow.Table` that owns its own buffers.
  It is safe to read after the connection is checked in. The cursor never wraps it
  or hands back a streaming `RecordBatchReader`, which would dangle once the cursor
  closed (Pitfall 7).

Worker exceptions are never re-wrapped (ACUR-06/EDGE-17): the single
[`offload`][adbc_poolhouse._async._offload.offload] chokepoint re-raises an
`AdbcError` with its exact type and traceback, and nothing here catches it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import anyio

from adbc_poolhouse._async._offload import offload

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    import pyarrow
    from anyio import CapacityLimiter

    from adbc_poolhouse._async._connection import AsyncConnection


class _SyncCursor(Protocol):
    """
    Structural type for the sync ADBC dbapi cursor surface `AsyncCursor` offloads.

    Declared structurally (a `Protocol`) rather than imported from a concrete
    driver so the async layer stays driver-agnostic --- the dbapi module is
    resolved dynamically by the sync core, so there is no single class to import.
    Any object exposing this surface (the ADBC `Cursor`, or a test stub) satisfies
    it.
    """

    @property
    def description(self) -> object: ...
    @property
    def rowcount(self) -> int: ...
    @property
    def arraysize(self) -> int: ...
    def execute(self, operation: str, parameters: object = ..., /) -> object: ...
    def executemany(self, operation: str, seq_of_parameters: object, /) -> object: ...
    def fetchone(self) -> object: ...
    def fetchmany(self, size: int = ..., /) -> Sequence[object]: ...
    def fetchall(self) -> Sequence[object]: ...
    def fetch_arrow_table(self) -> pyarrow.Table: ...
    def close(self) -> None: ...


class AsyncCursor:
    """
    Async wrapper over a sync ADBC cursor.

    Opened synchronously by
    [`AsyncConnection.cursor`][adbc_poolhouse._async._connection.AsyncConnection.cursor].
    One `AsyncCursor` belongs to exactly one task, mirroring the synchronous
    connection-per-thread convention. Every blocking call is offloaded through the
    owning pool's limiter and guards the parent connection's `_in_use` flag, so a
    second concurrent caller is rejected with
    [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError].

    `description`, `rowcount`, and `arraysize` are synchronous property reads (no
    `await`, no offload). `fetch_arrow_table` returns a fully-materialized
    `pyarrow.Table`, safe after the connection is checked in.

    Example:
        ```python
        import adbc_poolhouse

        pool = await adbc_poolhouse.create_async_pool(config)
        async with await pool.connect() as conn:
            cursor = conn.cursor()
            await cursor.execute("SELECT * FROM events WHERE day = ?", ["2026-06-27"])
            table = await cursor.fetch_arrow_table()  # materialized pyarrow.Table
            print(cursor.rowcount)  # sync property, no await
        await adbc_poolhouse.close_async_pool(pool)
        ```
    """

    def __init__(
        self,
        sync_cursor: _SyncCursor,
        limiter: CapacityLimiter,
        owner: AsyncConnection,
    ) -> None:
        """
        Bind a sync cursor to its limiter and owning connection.

        Args:
            sync_cursor: The underlying ADBC dbapi cursor to wrap.
            limiter: The owning pool's `anyio.CapacityLimiter`, used to bound
                every offloaded call. Identical to `owner`'s limiter; held directly
                so the cursor never reaches through the connection on the hot path.
            owner: The `AsyncConnection` this cursor was opened on. Every offloaded
                call brackets itself with `owner._enter_offload()` /
                `owner._exit_offload()`, so concurrent cursor use raises
                `ConnectionBusyError` via the connection's single-task guard.
        """
        self._cursor = sync_cursor
        self._limiter = limiter
        self._owner = owner

    @property
    def description(self) -> object:
        """
        The dbapi `description` of the last query (synchronous; no offload).

        Returns:
            The underlying cursor's `description` (a sequence of column-metadata
            tuples, or `None` before any query). Read directly --- it touches no
            I/O, so it is not offloaded.
        """
        return self._cursor.description

    @property
    def rowcount(self) -> int:
        """
        The dbapi `rowcount` of the last operation (synchronous; no offload).

        Returns:
            The underlying cursor's `rowcount` (`-1` when undetermined). Read
            directly --- it touches no I/O, so it is not offloaded.
        """
        return self._cursor.rowcount

    @property
    def arraysize(self) -> int:
        """
        The dbapi `arraysize` (default `fetchmany` batch size; synchronous).

        Returns:
            The underlying cursor's `arraysize`. Read directly --- it touches no
            I/O, so it is not offloaded.
        """
        return self._cursor.arraysize

    async def execute(self, operation: str, parameters: object = None) -> None:
        """
        Execute a statement on a worker thread.

        Offloads the dbapi `execute` through the pool limiter while holding the
        parent connection's `_in_use` guard, so a concurrent call on the same
        connection is rejected with `ConnectionBusyError` (EDGE-15).

        Args:
            operation: The SQL text to execute.
            parameters: Optional bound parameters, forwarded to the dbapi cursor.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        self._owner._enter_offload()  # noqa: SLF001 (intentional parent guard, see module docstring)
        try:
            await offload(
                self._cursor.execute,
                operation,
                parameters,
                limiter=self._limiter,
            )
        finally:
            self._owner._exit_offload()  # noqa: SLF001

    async def executemany(self, operation: str, seq_of_parameters: object) -> None:
        """
        Execute a statement once per parameter set on a worker thread.

        Offloads the dbapi `executemany` through the pool limiter while holding the
        parent connection's `_in_use` guard.

        Args:
            operation: The SQL text to execute.
            seq_of_parameters: The sequence of parameter sets, forwarded to the
                dbapi cursor.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        self._owner._enter_offload()  # noqa: SLF001
        try:
            await offload(
                self._cursor.executemany,
                operation,
                seq_of_parameters,
                limiter=self._limiter,
            )
        finally:
            self._owner._exit_offload()  # noqa: SLF001

    async def fetchone(self) -> object:
        """
        Fetch the next row on a worker thread.

        Returns:
            The next row (a tuple), or `None` when the result set is exhausted.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        self._owner._enter_offload()  # noqa: SLF001
        try:
            return await offload(
                self._cursor.fetchone,
                limiter=self._limiter,
            )
        finally:
            self._owner._exit_offload()  # noqa: SLF001

    async def fetchmany(self, size: int | None = None) -> object:
        """
        Fetch the next batch of rows on a worker thread.

        Args:
            size: The number of rows to fetch. When `None`, the dbapi cursor's
                `arraysize` is used.

        Returns:
            A sequence of rows (possibly empty when the result set is exhausted).

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        self._owner._enter_offload()  # noqa: SLF001
        try:
            if size is None:
                return await offload(
                    self._cursor.fetchmany,
                    limiter=self._limiter,
                )
            return await offload(
                self._cursor.fetchmany,
                size,
                limiter=self._limiter,
            )
        finally:
            self._owner._exit_offload()  # noqa: SLF001

    async def fetchall(self) -> object:
        """
        Fetch all remaining rows on a worker thread.

        Returns:
            A sequence of all remaining rows.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        self._owner._enter_offload()  # noqa: SLF001
        try:
            return await offload(
                self._cursor.fetchall,
                limiter=self._limiter,
            )
        finally:
            self._owner._exit_offload()  # noqa: SLF001

    async def fetch_arrow_table(self) -> pyarrow.Table:
        """
        Materialize the full result set as a `pyarrow.Table` on a worker thread.

        Offloads the dbapi `fetch_arrow_table` through the pool limiter and returns
        its result unchanged: a fully-materialized `pyarrow.Table` that owns its own
        buffers. The table is safe to read after the connection is checked in --- it
        is never a streaming `RecordBatchReader` bound to the (soon-closed) cursor
        (EDGE-21 / Pitfall 7).

        Returns:
            The materialized `pyarrow.Table` for the current result set.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        self._owner._enter_offload()  # noqa: SLF001
        try:
            return await offload(
                self._cursor.fetch_arrow_table,
                limiter=self._limiter,
            )
        finally:
            self._owner._exit_offload()  # noqa: SLF001

    async def close(self) -> None:
        """
        Close the underlying cursor on a worker thread (shielded).

        Offloads the dbapi `close` inside `anyio.CancelScope(shield=True)`, so a
        cancellation arriving mid-close cannot abandon an open cursor (which would
        pin Arrow readers). The parent connection's `_in_use` guard is held across
        the shielded offload.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        self._owner._enter_offload()  # noqa: SLF001
        try:
            with anyio.CancelScope(shield=True):
                await offload(
                    self._cursor.close,
                    limiter=self._limiter,
                )
        finally:
            self._owner._exit_offload()  # noqa: SLF001

    async def __aenter__(self) -> AsyncCursor:
        """
        Enter the async context.

        Returns:
            This `AsyncCursor`.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Close the cursor on context exit (shielded close).

        Args:
            exc_type: The exception type if the block raised, else `None`.
            exc: The exception instance if the block raised, else `None`.
            tb: The traceback if the block raised, else `None`.
        """
        await self.close()
