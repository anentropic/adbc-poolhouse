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

import contextlib
import functools
from typing import TYPE_CHECKING, Protocol, cast

import anyio

from adbc_poolhouse._async._cursor import AsyncCursor
from adbc_poolhouse._async._offload import offload
from adbc_poolhouse._async._reader import AsyncRecordBatchReader
from adbc_poolhouse._exceptions import ConnectionBusyError

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import TracebackType
    from typing import Any, Literal

    import pyarrow
    from anyio import CapacityLimiter
    from sqlalchemy.pool import PoolProxiedConnection

    from adbc_poolhouse._async._cursor import _SyncCursor


def _noop_cancel() -> None:
    """
    No-op cancel hook for connection-level metadata readers (no `adbc_cancel` exists).

    A connection --- unlike a cursor --- exposes no `adbc_cancel`, so a metadata
    reader has nothing to abort through. `AsyncRecordBatchReader` takes a
    zero-argument cancel callback as its fourth constructor argument, so the streaming
    metadata methods thread this no-op in and pair it with `poison_on_cancel=False` ---
    a hook that cannot abort the worker must not trigger poison-recovery (CR-34-01).
    It is a module-level function (not a lambda) only to keep the `scan_async_package`
    source guard's matcher clean.
    """


class _SyncConnection(Protocol):
    """
    Structural type for the sync ADBC dbapi Connection metadata surface.

    Mirrors `_SyncCursor`: declared structurally (a `Protocol`) rather than
    imported from a concrete driver, so the async layer stays driver-agnostic ---
    the dbapi module is resolved dynamically by the sync core, so there is no single
    class to import. Any object exposing this surface (the ADBC dbapi `Connection`,
    or a test stub) satisfies it. `AsyncConnection` casts its SQLAlchemy fairy to
    this Protocol so each offloaded metadata call stays arity-checked under
    basedpyright.
    """

    def adbc_get_info(self) -> dict[str | int, Any]: ...
    def adbc_get_objects(
        self,
        *,
        depth: Literal["all", "catalogs", "db_schemas", "tables", "columns"] = ...,
        catalog_filter: str | None = ...,
        db_schema_filter: str | None = ...,
        table_name_filter: str | None = ...,
        table_types_filter: list[str] | None = ...,
        column_name_filter: str | None = ...,
    ) -> pyarrow.RecordBatchReader: ...
    def adbc_get_table_schema(
        self,
        table_name: str,
        *,
        catalog_filter: str | None = ...,
        db_schema_filter: str | None = ...,
    ) -> pyarrow.Schema: ...
    def adbc_get_table_types(self) -> list[str]: ...
    def adbc_get_statistics(
        self,
        *,
        catalog_filter: str | None = ...,
        db_schema_filter: str | None = ...,
        table_name_filter: str | None = ...,
        approximate: bool = ...,
    ) -> pyarrow.RecordBatchReader: ...
    def adbc_get_statistic_names(self) -> pyarrow.RecordBatchReader: ...


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

    Two-tier entry guard (D-29-10). The entry method layers a persistent
    reader-lifetime tier on top of the per-call `_in_use` tier:

    - **Foreign callers** (`execute`, `commit`, another cursor, a new
      `fetch_record_batch`) are rejected while a reader is live --- they hit
      `_in_use` **or** `_reader_open` and get `ConnectionBusyError`.
    - **A live reader's own per-batch pulls** pass `from_reader=True`, which exempts
      them from the `_reader_open` tier only (the reentrancy exemption --- a reader
      must not deadlock on its own lifetime lock) while STILL taking the per-call
      `_in_use` C-access tier.

    Attributes:
        _in_use: True while an offloaded call on this connection (or one of its
            cursors) is in flight. The single-task aliasing guard; deliberately a
            plain bool, never a serializing lock, so a second concurrent caller is
            rejected rather than queued (D-24-03).
        _reader_open: True for the WHOLE lifetime of a live Arrow reader on this
            connection (Model B, D-29-08/09), distinct from the per-call `_in_use`.
            A live reader locks the connection so no foreign op can touch the still
            -open C stream between pulls, closing the gap `_in_use` alone leaves
            (STREAM-06). Set by `fetch_record_batch` and cleared by `reader.close()`
            / checkin (plan 03); `_exit_offload` NEVER touches it. A stale
            `_reader_open == True` is harmless because a fresh `AsyncConnection`
            wraps each `connect()`, so checkin is the backstop eraser (D-29-13).
        _teardown_limiter: A dedicated 1-token `anyio.CapacityLimiter` the
            poison-recovery `invalidate` offloads through, kept separate from the
            shared pool `limiter` so recovery never contends for the pool token the
            just-aborted worker is still releasing (WR-03).

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
        # D-29-09: a live Arrow reader locks the connection for its WHOLE lifetime,
        # not just during an in-flight pull. Distinct from the per-call `_in_use`
        # (which reads False between pulls, leaving the STREAM-06 gap this closes).
        # Owned by fetch_record_batch (set) / reader.close() + checkin (clear) in
        # plan 03; `_exit_offload` must never touch it (D-29-11/13).
        self._reader_open = False
        # Poison-recovery (`invalidate`) runs off a DEDICATED 1-token limiter, not
        # the pool's shared `limiter` (WR-03). Teardown is not throughput-bounded,
        # and on a `pool_size + max_overflow == 1` pool the just-aborted worker
        # still holds the single pool token until its thread returns; borrowing the
        # pool token here would make recovery wait on the very worker it just
        # aborted. A private limiter sidesteps that ordering dependency entirely.
        self._teardown_limiter: CapacityLimiter = anyio.CapacityLimiter(1)

    def _enter_offload(self, *, from_reader: bool = False) -> None:
        """
        Claim this connection for one offloaded call, or reject an aliased caller.

        Applies the two-tier entry guard (D-29-10). First the per-call C-access tier:
        raise `ConnectionBusyError` if the connection is already executing a call
        (from this task or another) --- this tier is unconditional, so `from_reader`
        never bypasses it. Then the reader-lifetime tier: raise `ConnectionBusyError`
        if a reader is live (`_reader_open`) UNLESS the caller is that reader's own
        pull (`from_reader=True`), which is exempt from this tier only (the
        reentrancy exemption --- a reader must not deadlock on its own lifetime
        lock). If both tiers pass, mark the connection busy.

        The read of `_in_use` and the write that sets it run in one synchronous span
        with NO `await` between them, so on the single-threaded event loop two tasks
        can never both observe `_in_use == False` and both proceed (Pitfall 3 / the
        check-and-set race). Always paired with `_exit_offload` in a `finally`.

        Args:
            from_reader: True only for a live reader's own per-batch pull, exempting
                it from the `_reader_open` tier (not the `_in_use` tier). Defaults
                False, so every existing (foreign) call site is unchanged.

        Raises:
            ConnectionBusyError: If an offloaded call on this connection is already
                in flight (`_in_use`), or a reader is live and the caller is foreign
                (`_reader_open and not from_reader`).
        """
        if self._in_use:
            raise ConnectionBusyError
        # Reader-lifetime tier: foreign callers are rejected while a reader is live.
        # The reader's own pulls pass from_reader=True to skip ONLY this tier
        # (D-29-10); they still took the _in_use tier above.
        if self._reader_open and not from_reader:
            raise ConnectionBusyError
        self._in_use = True

    def _exit_offload(self) -> None:
        """Release the connection after an offloaded call (call from `finally`)."""
        self._in_use = False

    @contextlib.contextmanager
    def _offloading(self, *, from_reader: bool = False) -> Generator[None]:
        """
        Hold the two-tier entry guard for the span of one offloaded call.

        Claims the connection on entry (raising `ConnectionBusyError` if it is
        already executing a call, or if a reader is live and the caller is foreign)
        and releases the per-call `_in_use` tier on exit, so every offloading method
        on this connection --- and on its cursors --- brackets its work identically
        without repeating the `try`/`finally` (D-24-03). If the guard rejects the
        caller the body never runs and the flags are left untouched for the call
        that legitimately holds them.

        `_reader_open` is deliberately NOT cleared here: its lifetime spans many
        offload calls and is owned by `reader.close()` / checkin (D-29-11), so
        `_exit_offload` only clears `_in_use`.

        Args:
            from_reader: Forwarded to `_enter_offload`. True only for a live
                reader's own per-batch pull (the reentrancy exemption); defaults
                False so every existing call site keeps its foreign-tier semantics
                with no edit.

        Yields:
            `None`. The guarded offload runs inside the `with` body.

        Raises:
            ConnectionBusyError: If an offloaded call on this connection is already
                in flight, or a reader is live and the caller is foreign.
        """
        self._enter_offload(from_reader=from_reader)
        try:
            yield
        finally:
            self._exit_offload()

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

        Unlike the cursor's `execute`/`fetch*`, this call is **not** cooperatively
        cancellable: it runs through the non-interruptible `offload` with no
        `adbc_cancel` hook, so a surrounding timeout or cancellation cannot abort an
        in-flight commit. The loop defers the cancellation and waits for the driver
        call to return before raising it. Keep commits short, or enforce a
        server-side statement timeout, if you need a bound on how long a commit can
        block.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.
        """
        with self._offloading():
            await offload(self._fairy.commit, limiter=self._limiter)

    async def rollback(self) -> None:
        """
        Roll back the current transaction on a worker thread.

        Offloads `fairy.rollback()` through the pool limiter while holding the
        `_in_use` guard.

        Like `commit`, this call is **not** cooperatively cancellable: a surrounding
        timeout or cancellation cannot abort an in-flight rollback. The loop defers
        the cancellation and waits for the driver call to return before raising it.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.
        """
        with self._offloading():
            await offload(self._fairy.rollback, limiter=self._limiter)

    async def adbc_get_info(self) -> dict[str | int, Any]:
        """
        Read the driver and vendor info codes on a worker thread.

        Offloads the sync `adbc_get_info()` through the pool limiter while holding
        the `_in_use` guard, so a concurrent call on this connection is rejected with
        `ConnectionBusyError`. The driver's own `dict` is returned unchanged --- keys
        are ADBC info codes (`str` or `int`), values the backend's reported metadata.

        Like `commit`, this call is **not** cooperatively cancellable: it runs
        through the non-interruptible `offload` with no cancel hook, so a surrounding
        timeout or cancellation cannot abort an in-flight metadata read. The loop
        defers the cancellation and waits for the driver call to return before
        raising it.

        Returns:
            The driver's info mapping, keyed by ADBC info code. Returned unchanged.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.

        Example:
            ```python
            async with await pool.connect() as conn:
                info = await conn.adbc_get_info()
                print(info)  # a dict of driver/vendor codes
            ```
        """
        sync_conn = cast("_SyncConnection", self._fairy)
        with self._offloading():
            return await offload(sync_conn.adbc_get_info, limiter=self._limiter)

    async def adbc_get_table_types(self) -> list[str]:
        """
        List the backend's table-type names on a worker thread.

        Offloads the sync `adbc_get_table_types()` through the pool limiter while
        holding the `_in_use` guard, so a concurrent call on this connection is
        rejected with `ConnectionBusyError`. The driver's own `list` of table-type
        strings (for example `"table"`, `"view"`) is returned unchanged.

        Like `commit`, this call is **not** cooperatively cancellable: a surrounding
        timeout or cancellation cannot abort an in-flight metadata read. The loop
        defers the cancellation and waits for the driver call to return before
        raising it.

        Returns:
            The backend's table-type strings, in the driver's order. Returned
            unchanged.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.

        Example:
            ```python
            async with await pool.connect() as conn:
                types = await conn.adbc_get_table_types()
                print(types)  # e.g. ["table", "view"]
            ```
        """
        sync_conn = cast("_SyncConnection", self._fairy)
        with self._offloading():
            return await offload(sync_conn.adbc_get_table_types, limiter=self._limiter)

    async def adbc_get_table_schema(
        self,
        table_name: str,
        *,
        catalog_filter: str | None = None,
        db_schema_filter: str | None = None,
    ) -> pyarrow.Schema:
        """
        Read a single table's Arrow schema on a worker thread.

        Offloads the sync `adbc_get_table_schema()` through the pool limiter while
        holding the `_in_use` guard, so a concurrent call on this connection is
        rejected with `ConnectionBusyError`. The driver's own `pyarrow.Schema` is
        returned unchanged. The arguments forward through `functools.partial` so the
        keyword-only filters reach the driver arity-checked.

        Like `commit`, this call is **not** cooperatively cancellable: a surrounding
        timeout or cancellation cannot abort an in-flight metadata read. The loop
        defers the cancellation and waits for the driver call to return before
        raising it.

        Args:
            table_name: The table to describe. Passed straight to the driver as an
                identifier; poolhouse does not quote or sanitize it.
            catalog_filter: Restrict the lookup to this catalog. Forwarded to the
                driver unchanged; `None` (the default) leaves it unrestricted.
            db_schema_filter: Restrict the lookup to this schema. Forwarded to the
                driver unchanged; `None` (the default) leaves it unrestricted.

        Returns:
            The table's `pyarrow.Schema`, returned unchanged from the driver.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.

        Example:
            ```python
            async with await pool.connect() as conn:
                schema = await conn.adbc_get_table_schema("people")
                print(schema.names)  # e.g. ["id", "name"]
            ```
        """
        sync_conn = cast("_SyncConnection", self._fairy)
        with self._offloading():
            return await offload(
                functools.partial(
                    sync_conn.adbc_get_table_schema,
                    table_name,
                    catalog_filter=catalog_filter,
                    db_schema_filter=db_schema_filter,
                ),
                limiter=self._limiter,
            )

    async def adbc_get_objects(
        self,
        *,
        depth: Literal["all", "catalogs", "db_schemas", "tables", "columns"] = "all",
        catalog_filter: str | None = None,
        db_schema_filter: str | None = None,
        table_name_filter: str | None = None,
        table_types_filter: list[str] | None = None,
        column_name_filter: str | None = None,
    ) -> AsyncRecordBatchReader:
        """
        Stream the catalog/schema/table hierarchy as an `AsyncRecordBatchReader`.

        Offloads the sync `adbc_get_objects()` through the pool limiter to create the
        native `pyarrow.RecordBatchReader`, then wraps it in an
        `AsyncRecordBatchReader` whose every batch pull is itself offloaded --- the
        result is never materialized to a `pyarrow.Table`. The filter arguments
        forward through `functools.partial` so they reach the driver arity-checked.

        Like `commit`, creating the reader is **not** cooperatively cancellable: a
        surrounding timeout or cancellation cannot abort the in-flight metadata call,
        which runs through the non-interruptible `offload`.

        The returned reader is a live stream bound to this connection's C Arrow
        stream, so it locks the connection for its WHOLE lifetime: a foreign op
        (`commit`, a cursor, another metadata call) raises `ConnectionBusyError`
        until the reader is closed (STREAM-06), and a read after the reader is closed
        / the connection is checked in surfaces the driver's native
        `pyarrow.lib.ArrowInvalid` (never a segfault). The `_reader_open` lifetime
        lock is set AFTER the `_offloading()` span exits and ONLY on the success
        path, so a failed creation leaves the connection usable.

        The reader has no cancel of its own (the connection has no `adbc_cancel`), so
        a cancelled per-batch pull cannot abort the in-flight C call: the worker
        finishes its read, the cancellation is then re-raised, and the pulled batch is
        discarded. The connection is NOT invalidated --- it was never poisoned, and
        invalidating would race a second thread against the still-running read on the
        same connection (CR-34-01) --- so it returns to the pool on the normal checkin.

        Args:
            depth: How deep to descend the hierarchy --- `"all"` (the default),
                `"catalogs"`, `"db_schemas"`, `"tables"`, or `"columns"`. Forwarded
                to the driver unchanged.
            catalog_filter: Restrict to this catalog. Forwarded unchanged; `None`
                (the default) leaves it unrestricted.
            db_schema_filter: Restrict to this schema. Forwarded unchanged; `None`
                (the default) leaves it unrestricted.
            table_name_filter: Restrict to this table name. Forwarded unchanged;
                `None` (the default) leaves it unrestricted.
            table_types_filter: Restrict to these table types. Forwarded unchanged;
                `None` (the default) leaves it unrestricted.
            column_name_filter: Restrict to this column name. Forwarded unchanged;
                `None` (the default) leaves it unrestricted.

        Returns:
            An `AsyncRecordBatchReader` streaming the object hierarchy, each pull
            offloaded through the pool limiter.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.

        Example:
            ```python
            async with await pool.connect() as conn:
                async with await conn.adbc_get_objects(depth="tables") as reader:
                    async for batch in reader:
                        process(batch)  # a pyarrow.RecordBatch, each pull offloaded
            ```
        """
        sync_conn = cast("_SyncConnection", self._fairy)
        with self._offloading():
            sync_reader = await offload(
                functools.partial(
                    sync_conn.adbc_get_objects,
                    depth=depth,
                    catalog_filter=catalog_filter,
                    db_schema_filter=db_schema_filter,
                    table_name_filter=table_name_filter,
                    table_types_filter=table_types_filter,
                    column_name_filter=column_name_filter,
                ),
                limiter=self._limiter,
            )
        # Lock the connection for the reader's WHOLE lifetime (D-29-08/09). Set AFTER
        # the _offloading() span exits (it already cleared _in_use) and ONLY on the
        # success path, so a cancelled/failed creation leaves _reader_open False and
        # the connection usable (Pitfall 3).
        self._reader_open = True
        return AsyncRecordBatchReader(
            sync_reader, self._limiter, self, _noop_cancel, poison_on_cancel=False
        )

    async def adbc_get_statistics(
        self,
        *,
        catalog_filter: str | None = None,
        db_schema_filter: str | None = None,
        table_name_filter: str | None = None,
        approximate: bool = True,
    ) -> AsyncRecordBatchReader:
        """
        Stream table statistics as an `AsyncRecordBatchReader`.

        Offloads the sync `adbc_get_statistics()` through the pool limiter to create
        the native `pyarrow.RecordBatchReader`, then wraps it in an
        `AsyncRecordBatchReader` whose every batch pull is itself offloaded --- never
        materialized. The filter arguments forward through `functools.partial`. A
        backend that does not implement statistics (for example DuckDB) surfaces the
        driver's native `NotSupportedError` unchanged (locked decision #6).

        Like `commit`, creating the reader is **not** cooperatively cancellable: a
        surrounding timeout or cancellation cannot abort the in-flight metadata call.

        The returned reader locks the connection for its WHOLE lifetime: a foreign op
        raises `ConnectionBusyError` until the reader is closed (STREAM-06), and a
        read after close / check-in surfaces the driver's native
        `pyarrow.lib.ArrowInvalid`. The `_reader_open` lifetime lock is set AFTER the
        `_offloading()` span exits and ONLY on the success path. The reader has no
        cancel of its own, so a cancelled per-batch pull cannot abort the C call: the
        worker finishes its read and the cancellation is re-raised. The connection is
        NOT invalidated (it was never poisoned) --- it returns to the pool on the
        normal checkin (CR-34-01).

        Args:
            catalog_filter: Restrict to this catalog. Forwarded unchanged; `None`
                (the default) leaves it unrestricted.
            db_schema_filter: Restrict to this schema. Forwarded unchanged; `None`
                (the default) leaves it unrestricted.
            table_name_filter: Restrict to this table name. Forwarded unchanged;
                `None` (the default) leaves it unrestricted.
            approximate: Allow the backend to return approximate statistics. `True`
                (the default) is forwarded to the driver unchanged.

        Returns:
            An `AsyncRecordBatchReader` streaming the statistics, each pull offloaded
            through the pool limiter.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.

        Example:
            ```python
            async with await pool.connect() as conn:
                async with await conn.adbc_get_statistics() as reader:
                    async for batch in reader:
                        process(batch)  # a pyarrow.RecordBatch, each pull offloaded
            ```
        """
        sync_conn = cast("_SyncConnection", self._fairy)
        with self._offloading():
            sync_reader = await offload(
                functools.partial(
                    sync_conn.adbc_get_statistics,
                    catalog_filter=catalog_filter,
                    db_schema_filter=db_schema_filter,
                    table_name_filter=table_name_filter,
                    approximate=approximate,
                ),
                limiter=self._limiter,
            )
        # Set AFTER the _offloading() span exits, success path ONLY (see
        # `adbc_get_objects` for the lifetime-lock rationale, Pitfall 3).
        self._reader_open = True
        return AsyncRecordBatchReader(
            sync_reader, self._limiter, self, _noop_cancel, poison_on_cancel=False
        )

    async def adbc_get_statistic_names(self) -> AsyncRecordBatchReader:
        """
        Stream the backend's statistic names as an `AsyncRecordBatchReader`.

        Offloads the sync `adbc_get_statistic_names()` through the pool limiter to
        create the native `pyarrow.RecordBatchReader`, then wraps it in an
        `AsyncRecordBatchReader` whose every batch pull is itself offloaded --- never
        materialized. A backend that does not implement statistics (for example
        DuckDB) surfaces the driver's native `NotSupportedError` unchanged (locked
        decision #6).

        Like `commit`, creating the reader is **not** cooperatively cancellable: a
        surrounding timeout or cancellation cannot abort the in-flight metadata call.

        The returned reader locks the connection for its WHOLE lifetime: a foreign op
        raises `ConnectionBusyError` until the reader is closed (STREAM-06), and a
        read after close / check-in surfaces the driver's native
        `pyarrow.lib.ArrowInvalid`. The `_reader_open` lifetime lock is set AFTER the
        `_offloading()` span exits and ONLY on the success path. The reader has no
        cancel of its own, so a cancelled per-batch pull cannot abort the C call: the
        worker finishes its read and the cancellation is re-raised. The connection is
        NOT invalidated (it was never poisoned) --- it returns to the pool on the
        normal checkin (CR-34-01).

        Returns:
            An `AsyncRecordBatchReader` streaming the statistic names, each pull
            offloaded through the pool limiter.

        Raises:
            ConnectionBusyError: If another offloaded call on this connection is
                already in flight.

        Example:
            ```python
            async with await pool.connect() as conn:
                async with await conn.adbc_get_statistic_names() as reader:
                    async for batch in reader:
                        process(batch)  # a pyarrow.RecordBatch, each pull offloaded
            ```
        """
        sync_conn = cast("_SyncConnection", self._fairy)
        with self._offloading():
            sync_reader = await offload(sync_conn.adbc_get_statistic_names, limiter=self._limiter)
        # Set AFTER the _offloading() span exits, success path ONLY (see
        # `adbc_get_objects` for the lifetime-lock rationale, Pitfall 3).
        self._reader_open = True
        return AsyncRecordBatchReader(
            sync_reader, self._limiter, self, _noop_cancel, poison_on_cancel=False
        )

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
        with self._offloading(), anyio.CancelScope(shield=True):
            await offload(self._fairy.close, limiter=self._limiter)

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

        It offloads through a DEDICATED 1-token teardown limiter, NOT the pool's
        shared `limiter` (WR-03): on a single-token pool the just-aborted worker
        still holds the only pool token until its thread returns, so borrowing the
        pool token here would deadlock recovery behind the very worker it just
        aborted. Teardown is not throughput-bounded, so giving it a private token
        is correct and removes the unenforced scheduler-ordering dependency. Since
        D-25-09 the cancel path also waits for the aborted worker to return before
        calling this, so the pool token is already free by then --- the private
        limiter is now belt-and-braces on that path rather than the only thing
        preventing the deadlock, and it still keeps teardown off the pool's budget
        for every other caller.

        It is the poison-recovery counterpart to `close`: invalidate is the cancel
        path, `close` the normal check-in. A `close()` after an `invalidate()` is a
        safe no-op (probe-confirmed).

        Releasing a live reader's lifetime lock (D-29-16): if a streaming
        `AsyncRecordBatchReader` held this connection (`_reader_open == True`) when its
        pull was cancelled, dropping the connection also clears `_reader_open`. The
        connection is being detached from the pool, so its reader-lifetime lock is
        meaningless --- and a subsequent explicit `close()` (which takes the foreign
        tier) must stay the documented safe no-op rather than raise
        `ConnectionBusyError` on the now-defunct lock. The per-`connect()` fresh
        `AsyncConnection` is the ultimate backstop (D-29-13), but clearing it here
        keeps close-after-invalidate correct on the same handle.
        """
        self._reader_open = False
        with anyio.CancelScope(shield=True):
            await offload(self._fairy.invalidate, limiter=self._teardown_limiter)

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
