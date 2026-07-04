"""
The async cursor wrapper: offloaded DBAPI surface, materialized Arrow, sync props.

[`AsyncCursor`][adbc_poolhouse._async._cursor.AsyncCursor] wraps a single sync
ADBC dbapi cursor and offloads every blocking call --- `execute`, `executemany`,
`fetchone`, `fetchmany`, `fetchall`, `fetch_arrow_table`, `fetch_df`,
`fetch_polars`, `adbc_ingest`, `close`
--- through the
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

import functools
from typing import TYPE_CHECKING, Protocol, cast

import anyio

from adbc_poolhouse._async._cancel import cancellable_offload
from adbc_poolhouse._async._offload import offload
from adbc_poolhouse._async._reader import AsyncRecordBatchReader

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType
    from typing import Literal

    import pandas
    import polars
    import pyarrow
    from anyio import CapacityLimiter
    from typing_extensions import CapsuleType

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
    def fetch_record_batch(self) -> pyarrow.RecordBatchReader: ...
    def fetch_df(self) -> object: ...
    def fetch_polars(self) -> object: ...
    def adbc_ingest(
        self,
        table_name: str,
        data: pyarrow.RecordBatch | pyarrow.Table | pyarrow.RecordBatchReader | CapsuleType,
        mode: Literal["append", "create", "replace", "create_append"] = ...,
        *,
        catalog_name: str | None = ...,
        db_schema_name: str | None = ...,
        temporary: bool = ...,
    ) -> int: ...
    def adbc_prepare(self, operation: bytes | str, /) -> object: ...
    def adbc_execute_schema(self, operation: str, parameters: object = ..., /) -> object: ...
    def adbc_cancel(self) -> None: ...
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

    def _adbc_cancel(self) -> None:
        """
        Fire the driver's thread-safe `adbc_cancel` to abort an in-flight call.

        Resolved lazily and called only by `cancellable_offload` when a
        genuinely-running offload is cancelled (never on the success path). The
        ADBC dbapi cursor always exposes `adbc_cancel`; a replay/cassette backend
        that does not block (and so never aborts mid-flight) need not provide it,
        so its absence is tolerated as a no-op rather than surfaced --- the abort
        path is unreachable for an instant, non-blocking backend.
        """
        cancel = getattr(self._cursor, "adbc_cancel", None)
        if cancel is not None:
            cancel()

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

        If the surrounding scope is cancelled or times out while the statement is
        in flight, the in-flight C call is aborted with `cursor.adbc_cancel`, the
        now-poisoned connection is invalidated (shielded), and the cancellation is
        re-raised --- the connection never returns to the pool busy (CANCEL-01/02).

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        with self._owner._offloading():  # noqa: SLF001 (intentional parent guard, see module docstring)
            await cancellable_offload(
                self._adbc_cancel,
                self._cursor.execute,
                operation,
                parameters,
                limiter=self._limiter,
                on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
            )

    async def executemany(self, operation: str, seq_of_parameters: object) -> None:
        """
        Execute a statement once per parameter set on a worker thread.

        Offloads the dbapi `executemany` through the pool limiter while holding the
        parent connection's `_in_use` guard.

        Args:
            operation: The SQL text to execute.
            seq_of_parameters: The sequence of parameter sets, forwarded to the
                dbapi cursor.

        If the surrounding scope is cancelled mid-flight, the in-flight call is
        aborted with `cursor.adbc_cancel`, the poisoned connection is invalidated
        (shielded), and the cancellation is re-raised (CANCEL-01/02).

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        with self._owner._offloading():  # noqa: SLF001
            await cancellable_offload(
                self._adbc_cancel,
                self._cursor.executemany,
                operation,
                seq_of_parameters,
                limiter=self._limiter,
                on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
            )

    async def fetchone(self) -> object:
        """
        Fetch the next row on a worker thread.

        If the surrounding scope is cancelled mid-fetch, the in-flight call is
        aborted with `cursor.adbc_cancel`, the poisoned connection is invalidated
        (shielded), and the cancellation is re-raised (CANCEL-01/02).

        Returns:
            The next row (a tuple), or `None` when the result set is exhausted.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        with self._owner._offloading():  # noqa: SLF001
            return await cancellable_offload(
                self._adbc_cancel,
                self._cursor.fetchone,
                limiter=self._limiter,
                on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
            )

    async def fetchmany(self, size: int | None = None) -> object:
        """
        Fetch the next batch of rows on a worker thread.

        Args:
            size: The number of rows to fetch. When `None`, the dbapi cursor's
                `arraysize` is used.

        If the surrounding scope is cancelled mid-fetch, the in-flight call is
        aborted with `cursor.adbc_cancel`, the poisoned connection is invalidated
        (shielded), and the cancellation is re-raised (CANCEL-01/02).

        Returns:
            A sequence of rows (possibly empty when the result set is exhausted).

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        with self._owner._offloading():  # noqa: SLF001
            # Forward `size` only when given, so the dbapi cursor falls back to its
            # own `arraysize` default. The two arms differ only by that argument; a
            # single `*tuple`-spread call would lose the `TypeVarTuple` arity the
            # `cancellable_offload` signature enforces, so the branch stays explicit.
            if size is None:
                return await cancellable_offload(
                    self._adbc_cancel,
                    self._cursor.fetchmany,
                    limiter=self._limiter,
                    on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
                )
            return await cancellable_offload(
                self._adbc_cancel,
                self._cursor.fetchmany,
                size,
                limiter=self._limiter,
                on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
            )

    async def fetchall(self) -> object:
        """
        Fetch all remaining rows on a worker thread.

        If the surrounding scope is cancelled mid-fetch, the in-flight call is
        aborted with `cursor.adbc_cancel`, the poisoned connection is invalidated
        (shielded), and the cancellation is re-raised (CANCEL-01/02).

        Returns:
            A sequence of all remaining rows.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        with self._owner._offloading():  # noqa: SLF001
            return await cancellable_offload(
                self._adbc_cancel,
                self._cursor.fetchall,
                limiter=self._limiter,
                on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
            )

    async def fetch_arrow_table(self) -> pyarrow.Table:
        """
        Materialize the full result set as a `pyarrow.Table` on a worker thread.

        Offloads the dbapi `fetch_arrow_table` through the pool limiter and returns
        its result unchanged: a fully-materialized `pyarrow.Table` that owns its own
        buffers. The table is safe to read after the connection is checked in --- it
        is never a streaming `RecordBatchReader` bound to the (soon-closed) cursor
        (EDGE-21 / Pitfall 7).

        If the surrounding scope is cancelled or times out while the result is
        being materialized, the in-flight C call is aborted with
        `cursor.adbc_cancel`, the now-poisoned connection is invalidated
        (shielded), and the cancellation is re-raised (CANCEL-01/02).

        Returns:
            The materialized `pyarrow.Table` for the current result set.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
        """
        with self._owner._offloading():  # noqa: SLF001
            return await cancellable_offload(
                self._adbc_cancel,
                self._cursor.fetch_arrow_table,
                limiter=self._limiter,
                on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
            )

    async def fetch_df(self) -> pandas.DataFrame:
        """
        Materialize the full result set as a `pandas.DataFrame` on a worker thread.

        Offloads the driver's native `fetch_df` through the pool limiter and returns
        its result unchanged: a fully-materialized `pandas.DataFrame` that owns its
        own buffers. The frame is safe to read after the connection is checked in ---
        it is never bound to the (soon-closed) cursor's C stream (EDGE-21 / Pitfall 7).

        `pandas` is not a poolhouse dependency --- you install it yourself. poolhouse
        never imports it: the driver imports `pandas` inside the worker, so a missing
        install surfaces the native `ModuleNotFoundError` unchanged, with no
        pre-check and no wrapping.

        If the surrounding scope is cancelled or times out while the result is
        being materialized, the in-flight C call is aborted with
        `cursor.adbc_cancel`, the now-poisoned connection is invalidated
        (shielded), and the cancellation is re-raised (CANCEL-01/02).

        Returns:
            The materialized `pandas.DataFrame` for the current result set.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
            ModuleNotFoundError: If `pandas` is not installed. Raised by the driver
                in the worker and propagated unchanged.

        Example:
            ```python
            async with await pool.connect() as conn:
                cursor = conn.cursor()
                await cursor.execute("SELECT * FROM events")
                df = await cursor.fetch_df()  # a pandas.DataFrame
            ```
        """
        with self._owner._offloading():  # noqa: SLF001
            # `_SyncCursor.fetch_df` is typed `-> object` to keep the Protocol
            # driver-agnostic and free of a pandas stub dependency (D-31-06); cast
            # back to the public return type. No runtime effect --- the driver
            # materializes and returns the pandas.DataFrame itself.
            return cast(
                "pandas.DataFrame",
                await cancellable_offload(
                    self._adbc_cancel,
                    self._cursor.fetch_df,
                    limiter=self._limiter,
                    on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
                ),
            )

    async def fetch_polars(self) -> polars.DataFrame:
        """
        Materialize the full result set as a `polars.DataFrame` on a worker thread.

        Offloads the driver's native `fetch_polars` through the pool limiter and
        returns its result unchanged: a fully-materialized `polars.DataFrame` that
        owns its own buffers. The frame is safe to read after the connection is
        checked in --- it is never bound to the (soon-closed) cursor's C stream
        (EDGE-21 / Pitfall 7).

        `polars` is not a poolhouse dependency --- you install it yourself. poolhouse
        never imports it: the driver imports `polars` inside the worker, so a missing
        install surfaces the native `ModuleNotFoundError` unchanged, with no
        pre-check and no wrapping.

        If the surrounding scope is cancelled or times out while the result is
        being materialized, the in-flight C call is aborted with
        `cursor.adbc_cancel`, the now-poisoned connection is invalidated
        (shielded), and the cancellation is re-raised (CANCEL-01/02).

        Returns:
            The materialized `polars.DataFrame` for the current result set.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
            ModuleNotFoundError: If `polars` is not installed. Raised by the driver
                in the worker and propagated unchanged.

        Example:
            ```python
            async with await pool.connect() as conn:
                cursor = conn.cursor()
                await cursor.execute("SELECT * FROM events")
                df = await cursor.fetch_polars()  # a polars.DataFrame
            ```
        """
        with self._owner._offloading():  # noqa: SLF001
            # `_SyncCursor.fetch_polars` is typed `-> object` to keep the Protocol
            # driver-agnostic (D-31-06); cast back to the public return type. No
            # runtime effect --- the driver materializes and returns the
            # polars.DataFrame itself.
            return cast(
                "polars.DataFrame",
                await cancellable_offload(
                    self._adbc_cancel,
                    self._cursor.fetch_polars,
                    limiter=self._limiter,
                    on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
                ),
            )

    async def adbc_ingest(
        self,
        table_name: str,
        data: pyarrow.RecordBatch | pyarrow.Table | pyarrow.RecordBatchReader | CapsuleType,
        *,
        mode: Literal["create", "append", "replace", "create_append"] = "create",
        catalog_name: str | None = None,
        db_schema_name: str | None = None,
        temporary: bool = False,
    ) -> int:
        """
        Bulk-load an Arrow dataset into a table on a worker thread.

        Offloads the dbapi `adbc_ingest` through the pool limiter while holding the
        parent connection's `_in_use` guard, so a concurrent call on the same
        connection is rejected with `ConnectionBusyError` (EDGE-15). This is a
        single whole-operation offload --- the connection checks back in the moment
        the ingest returns, unlike `fetch_record_batch`, which holds the connection
        for a reader's whole lifetime.

        `data` is handed to the driver untouched: poolhouse performs no conversion
        and no validation. The driver owns the Arrow binding and the table
        identifier, so a malformed dataset or a bad identifier surfaces the driver's
        native error unchanged.

        If the surrounding scope is cancelled or times out while the ingest is in
        flight, the in-flight C call is aborted with `cursor.adbc_cancel`, the
        now-poisoned connection is invalidated (shielded), and the cancellation is
        re-raised --- the connection never returns to the pool busy (CANCEL-01/02).
        Recovery restores the *connection*, not the *table*: an aborted bulk load
        can leave rows already written, and poolhouse does not roll that back. Treat
        a cancelled ingest as leaving the table in an undefined state.

        Args:
            table_name: The target table. Passed straight to the driver as a SQL
                identifier; poolhouse does not quote or sanitize it.
            data: The Arrow dataset to load --- a `pyarrow.Table`, `RecordBatch`,
                `RecordBatchReader`, or an Arrow C-stream capsule. Forwarded to the
                driver with zero conversion.
            mode: How to write the data. `"create"` (the default) makes a new table
                and fails if it exists; `"append"` adds rows to an existing table;
                `"create_append"` creates the table if needed, then appends;
                `"replace"` **drops** the existing table and recreates it --- the old
                rows are lost, so it is not a row-level upsert. Forwarded to the
                driver verbatim.
            catalog_name: EXPERIMENTAL. Target catalog for the table. No stability
                guarantee; surfaced as-is from the driver.
            db_schema_name: EXPERIMENTAL. Target schema for the table. No stability
                guarantee; surfaced as-is from the driver.
            temporary: EXPERIMENTAL. Create the table as temporary. No stability
                guarantee; surfaced as-is from the driver.

        Returns:
            The number of rows written, or `-1` when the driver cannot report a
            count. Poolhouse returns the driver's value unchanged.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.

        Example:
            ```python
            import pyarrow as pa

            people = pa.table({"id": [1, 2, 3], "name": ["a", "b", "c"]})
            async with await pool.connect() as conn:
                cursor = conn.cursor()
                await cursor.adbc_ingest("people", people, mode="create")  # returns 3
                await cursor.adbc_ingest("people", people, mode="append")  # returns 3 (6 total)
            ```
        """
        with self._owner._offloading():  # noqa: SLF001
            return await cancellable_offload(
                self._adbc_cancel,
                functools.partial(
                    self._cursor.adbc_ingest,
                    table_name,
                    data,
                    mode=mode,
                    catalog_name=catalog_name,
                    db_schema_name=db_schema_name,
                    temporary=temporary,
                ),
                limiter=self._limiter,
                on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
            )

    async def adbc_prepare(self, operation: bytes | str) -> pyarrow.Schema | None:
        """
        Prepare a statement without executing it, on a worker thread.

        Offloads the dbapi `adbc_prepare` through the pool limiter while holding the
        parent connection's `_in_use` guard, so a concurrent call on the same
        connection is rejected with `ConnectionBusyError` (EDGE-15). The query is
        prepared but NOT executed --- no rows are read and no data is written.

        Returns the schema of the query's BIND PARAMETERS, or `None` when the driver
        cannot determine it. Poolhouse forwards the driver's value unchanged; treat a
        `None` result as "the backend does not report a parameter schema", not an
        error.

        If the surrounding scope is cancelled or times out while the prepare is in
        flight, the in-flight C call is aborted with `cursor.adbc_cancel` and the
        cancellation is re-raised. Because a prepare writes no state, the connection
        is NOT invalidated --- it is cancellable but non-poisoning, returning clean to
        the pool (D-35-04). This is the deliberate difference from `execute`, which
        invalidates on abort.

        Args:
            operation: The SQL text to prepare. Passed to the driver verbatim;
                poolhouse constructs no SQL and adds no sanitization.

        Returns:
            The `pyarrow.Schema` describing the query's bind parameters, or `None`
            when the driver cannot determine a parameter schema.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.

        Example:
            ```python
            async with await pool.connect() as conn:
                cursor = conn.cursor()
                schema = await cursor.adbc_prepare("SELECT * FROM t WHERE id = ?")
                # `schema` describes the `?` bind parameters (or is None).
            ```
        """
        with self._owner._offloading():  # noqa: SLF001
            # `_SyncCursor.adbc_prepare` is typed `-> object` to keep the Protocol
            # driver-agnostic (D-35-05); cast back to the public return type. No
            # runtime effect --- the driver returns the pyarrow.Schema (or None).
            return cast(
                "pyarrow.Schema | None",
                await cancellable_offload(
                    self._adbc_cancel,
                    self._cursor.adbc_prepare,
                    operation,
                    limiter=self._limiter,
                    # on_abort OMITTED (D-35-04): cancellable but non-poisoning ---
                    # a prepare writes no state, so an aborted call leaves the
                    # connection clean; do NOT invalidate (unlike execute).
                ),
            )

    async def adbc_execute_schema(
        self, operation: str, parameters: object = None
    ) -> pyarrow.Schema:
        """
        Get a query's result-set schema without executing it, on a worker thread.

        Offloads the dbapi `adbc_execute_schema` through the pool limiter while
        holding the parent connection's `_in_use` guard, so a concurrent call on the
        same connection is rejected with `ConnectionBusyError` (EDGE-15). The query is
        planned but NOT run --- no rows are fetched and no side effects occur; only the
        result-set schema is returned.

        If the surrounding scope is cancelled or times out while the call is in
        flight, the in-flight C call is aborted with `cursor.adbc_cancel` and the
        cancellation is re-raised. Because the query never executes, the connection is
        NOT invalidated --- it is cancellable but non-poisoning, returning clean to the
        pool (D-35-04).

        An unsupported backend surfaces the driver's native error unchanged: poolhouse
        does not catch, wrap, or `find_spec`-pre-check it (D-35-06). DuckDB, for
        example, does not implement result-schema introspection and raises
        `NotSupportedError` straight through the single offload chokepoint (EDGE-17).

        Args:
            operation: The SQL text whose result schema to resolve. Passed to the
                driver verbatim; poolhouse constructs no SQL and adds no sanitization.
            parameters: Optional bound parameters, forwarded to the dbapi cursor.

        Returns:
            The `pyarrow.Schema` describing the query's result set, resolved without
            executing the query.

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.
            NotSupportedError: If the driver does not implement result-schema
                introspection (e.g. DuckDB). Raised by the driver in the worker and
                propagated unchanged through the offload chokepoint (EDGE-17).

        Example:
            ```python
            async with await pool.connect() as conn:
                cursor = conn.cursor()
                schema = await cursor.adbc_execute_schema("SELECT id, name FROM t")
                # `schema` is the result-set schema; the query never ran.
            ```
        """
        with self._owner._offloading():  # noqa: SLF001
            # `_SyncCursor.adbc_execute_schema` is typed `-> object` to keep the
            # Protocol driver-agnostic (D-35-05); cast back to the public return type.
            # No runtime effect --- the driver returns the pyarrow.Schema itself.
            return cast(
                "pyarrow.Schema",
                await cancellable_offload(
                    self._adbc_cancel,
                    self._cursor.adbc_execute_schema,
                    operation,
                    parameters,
                    limiter=self._limiter,
                    # on_abort OMITTED (D-35-04): cancellable but non-poisoning ---
                    # the query never executes, so an aborted call leaves the
                    # connection clean; do NOT invalidate (unlike execute).
                ),
            )

    async def fetch_record_batch(self) -> AsyncRecordBatchReader:
        """
        Stream the result set as an `AsyncRecordBatchReader` off a worker thread.

        Offloads the dbapi `fetch_record_batch` through the pool limiter to create
        the sync `pyarrow.RecordBatchReader`, then wraps it in an
        `AsyncRecordBatchReader` whose every batch pull is itself offloaded (D-29-03).
        Unlike
        `fetch_arrow_table`, the result is a live stream bound to this connection's C
        Arrow stream, so the reader locks the connection for its WHOLE lifetime: a
        foreign op raises `ConnectionBusyError` until the reader is closed (STREAM-06),
        and a read after the reader is closed / the connection is checked in surfaces
        the driver's native `pyarrow.lib.ArrowInvalid` (never a segfault, T-29-01).

        The `_reader_open` lifetime lock is set AFTER the `_offloading()` span exits
        (which already cleared the per-call `_in_use`) and ONLY on the success path,
        so a cancelled or failed creation leaves the connection usable rather than
        permanently busy (Pitfall 5).

        If the surrounding scope is cancelled or times out while the reader is being
        created, the in-flight C call is aborted with `cursor.adbc_cancel`, the
        now-poisoned connection is invalidated (shielded), and the cancellation is
        re-raised --- the connection never returns to the pool busy (CANCEL-01/02).

        Returns:
            An `AsyncRecordBatchReader` streaming the current result set, threaded
            with this cursor's `adbc_cancel` so a cancelled pull aborts through the
            cursor (the reader has no cancel of its own, Pitfall 4).

        Raises:
            ConnectionBusyError: If another offloaded call on the owning connection
                is already in flight.

        Example:
            ```python
            await cursor.execute("SELECT * FROM events")
            async with await cursor.fetch_record_batch() as reader:
                async for batch in reader:
                    process(batch)  # a pyarrow.RecordBatch, each pull offloaded
            ```
        """
        with self._owner._offloading():  # noqa: SLF001  foreign-tier guard: _in_use OR _reader_open
            sync_reader = await cancellable_offload(
                self._adbc_cancel,
                self._cursor.fetch_record_batch,
                limiter=self._limiter,
                on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
            )
        # Lock the connection for the reader's WHOLE lifetime (D-29-08/09). Set AFTER
        # the _offloading() span exits (it already cleared _in_use) and ONLY on the
        # success path, so a cancelled/failed creation leaves _reader_open False and
        # the connection usable (Pitfall 5).
        self._owner._reader_open = True  # noqa: SLF001
        # Pass this cursor's own `_adbc_cancel` as the 4th arg: a cancelled pull must
        # abort through the cursor, since the reader has no cancel of its own (Pitfall 4).
        return AsyncRecordBatchReader(
            sync_reader,
            self._limiter,
            self._owner,
            self._adbc_cancel,
        )

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
        with self._owner._offloading(), anyio.CancelScope(shield=True):  # noqa: SLF001
            await offload(
                self._cursor.close,
                limiter=self._limiter,
            )

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
