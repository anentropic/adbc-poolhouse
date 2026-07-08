"""
ADBC-dbapi adapters over the Databricks Python connector.

`adbc-poolhouse` pools ADBC connections and downstream code relies on the ADBC
DBAPI surface (``cursor.fetch_arrow_table()``, ``adbc_cancel()``, ...). The
Databricks Python connector (`databricks-sql-connector`) is PEP 249 DB-API 2.0
but spells its Arrow accessors differently (``fetchall_arrow`` /
``fetchmany_arrow``) and lacks the ``adbc_*`` extensions.

[`_AdbcCursorShim`][adbc_poolhouse._native_adapter._AdbcCursorShim] and
[`_ConnectionAdapter`][adbc_poolhouse._native_adapter._ConnectionAdapter] translate
a connector connection/cursor into the ADBC DBAPI shape so the native backend is
indistinguishable from an ADBC one to callers and to the async layer. ADBC-only
methods that have no faithful connector equivalent raise ``NotSupportedError``
(the ADBC DBAPI error type, so callers catch the same exception they already do).

All imports of `pyarrow` and the connector are internal to this package; nothing
here imports the connector, so `import adbc_poolhouse` stays connector-free.
"""

from __future__ import annotations

import contextlib
import weakref
from typing import TYPE_CHECKING, Any

from adbc_driver_manager.dbapi import NotSupportedError

if TYPE_CHECKING:
    import pyarrow


class _AdbcCursorShim:
    """
    Present a Databricks connector cursor as an ADBC DBAPI cursor.

    Wraps a single connector ``Cursor`` and forwards the DB-API 2.0 surface
    unchanged while mapping ADBC's Arrow accessors onto the connector's
    (``fetch_arrow_table`` -> ``fetchall_arrow``, etc.). ADBC-only extensions
    that the connector cannot serve raise ``NotSupportedError``.

    Args:
        cursor: The underlying connector cursor to wrap.
        connection: The owning `_ConnectionAdapter`, returned by the DB-API
            ``connection`` attribute.
    """

    def __init__(self, cursor: Any, connection: _ConnectionAdapter) -> None:
        self._cursor = cursor
        self._connection = connection
        self._closed = False

    # ----- DB-API 2.0 pass-through -----

    def execute(self, operation: str, parameters: Any = None) -> _AdbcCursorShim:
        """Execute a query, forwarding to the connector cursor."""
        self._cursor.execute(operation, parameters)
        return self

    def executemany(self, operation: str, seq_of_parameters: Any) -> None:
        """Execute a query once per parameter sequence."""
        self._cursor.executemany(operation, seq_of_parameters)

    def fetchone(self) -> Any:
        """Fetch the next row, or ``None`` when exhausted."""
        return self._cursor.fetchone()

    def fetchmany(self, size: int | None = None) -> list[Any]:
        """
        Fetch up to ``size`` rows.

        Args:
            size: Row count. When ``None`` (the ADBC default), the connector's
                ``arraysize`` is used, matching DB-API semantics. The connector's
                own ``fetchmany`` requires an explicit size, so the default is
                resolved here.
        """
        return self._cursor.fetchmany(self._cursor.arraysize if size is None else size)

    def fetchall(self) -> list[Any]:
        """Fetch all remaining rows."""
        return self._cursor.fetchall()

    def close(self) -> None:
        """Close the underlying connector cursor (idempotent)."""
        if not self._closed:
            self._closed = True
            self._cursor.close()

    def setinputsizes(self, sizes: Any) -> None:
        """DB-API no-op, forwarded for compatibility."""
        self._cursor.setinputsizes(sizes)

    def setoutputsize(self, size: Any, column: Any = None) -> None:
        """DB-API no-op, forwarded for compatibility."""
        self._cursor.setoutputsize(size, column)

    @property
    def description(self) -> Any:
        """DB-API description of the last result set."""
        return self._cursor.description

    @property
    def rowcount(self) -> int:
        """Row count of the last operation (the connector reports ``-1``)."""
        return self._cursor.rowcount

    @property
    def arraysize(self) -> int:
        """Default ``fetchmany`` batch size."""
        return self._cursor.arraysize

    @arraysize.setter
    def arraysize(self, value: int) -> None:
        self._cursor.arraysize = value

    @property
    def rownumber(self) -> int | None:
        """Zero-based index of the next row to fetch."""
        return self._cursor.rownumber

    @property
    def connection(self) -> _ConnectionAdapter:
        """The `_ConnectionAdapter` that opened this cursor."""
        return self._connection

    # ----- Arrow accessors (ADBC names -> connector names) -----

    def fetch_arrow_table(self) -> pyarrow.Table:
        """Fetch the whole result as a ``pyarrow.Table`` (ADBC name)."""
        return self._cursor.fetchall_arrow()

    def fetchallarrow(self) -> pyarrow.Table:
        """Legacy alias of `fetch_arrow_table`."""
        return self._cursor.fetchall_arrow()

    def fetch_record_batch(self) -> pyarrow.RecordBatchReader:
        """
        Stream the result as a ``pyarrow.RecordBatchReader``.

        Synthesized over the connector's ``fetchmany_arrow`` so batches are
        pulled incrementally (CloudFetch) rather than materialized at once. The
        batch size follows ``arraysize``, so chunk boundaries need not match the
        server's own batching.

        Returns:
            A reader whose ``schema`` / ``read_next_batch`` / ``close`` satisfy
            the streaming contract the async layer wraps.
        """
        import pyarrow as pa  # noqa: PLC0415  (lazy: pyarrow ships with the extra)

        arraysize = self._cursor.arraysize
        first = self._cursor.fetchmany_arrow(arraysize)
        schema = first.schema

        def _batches() -> Any:
            yield from first.to_batches()
            while True:
                table = self._cursor.fetchmany_arrow(arraysize)
                if table.num_rows == 0:
                    break
                yield from table.to_batches()

        return pa.RecordBatchReader.from_batches(schema, _batches())

    def fetch_df(self) -> Any:
        """Fetch the result as a ``pandas.DataFrame``."""
        return self._cursor.fetchall_arrow().to_pandas()

    def fetch_polars(self) -> Any:
        """Fetch the result as a ``polars.DataFrame``."""
        import polars  # noqa: PLC0415  (lazy: optional consumer dependency)

        return polars.from_arrow(self._cursor.fetchall_arrow())

    def adbc_cancel(self) -> None:
        """Abort the in-flight statement (maps to the connector's ``cancel``)."""
        self._cursor.cancel()

    # ----- ADBC-only extensions with no connector equivalent -----

    def fetch_arrow(self) -> Any:
        """Unsupported: ADBC returns a raw C-stream handle; use `fetch_record_batch`."""
        raise NotSupportedError(
            "fetch_arrow() (raw Arrow C-stream handle) is not available on the "
            "Databricks Python connector backend; use fetch_record_batch() instead."
        )

    def adbc_ingest(self, *args: Any, **kwargs: Any) -> int:
        """Unsupported: the connector has no Arrow bulk-ingest API."""
        raise NotSupportedError(
            "adbc_ingest() is not available on the Databricks Python connector "
            "backend; write with SQL INSERT / COPY INTO."
        )

    def adbc_prepare(self, *args: Any, **kwargs: Any) -> Any:
        """Unsupported: no standalone prepare on the connector."""
        raise NotSupportedError(
            "adbc_prepare() is not available on the Databricks Python connector backend."
        )

    def adbc_execute_schema(self, *args: Any, **kwargs: Any) -> Any:
        """Unsupported: no describe-without-execute on the connector."""
        raise NotSupportedError(
            "adbc_execute_schema() is not available on the Databricks Python connector backend."
        )

    def adbc_execute_partitions(self, *args: Any, **kwargs: Any) -> Any:
        """Unsupported: partitioned result distribution is ADBC-specific."""
        raise NotSupportedError(
            "adbc_execute_partitions() is not available on the Databricks Python connector backend."
        )

    def adbc_read_partition(self, *args: Any, **kwargs: Any) -> None:
        """Unsupported: partitioned result distribution is ADBC-specific."""
        raise NotSupportedError(
            "adbc_read_partition() is not available on the Databricks Python connector backend."
        )


class _ConnectionAdapter:
    """
    Present a Databricks connector connection as an ADBC DBAPI connection.

    Wraps a connector ``Connection``, hands out `_AdbcCursorShim` cursors, and
    forwards ``close`` / ``commit`` / ``rollback`` / ``autocommit``. ADBC
    connection-metadata methods (``adbc_get_info`` etc.) raise
    ``NotSupportedError``. Open cursors are tracked weakly so the pool's reset
    hook can close them and release Arrow buffers on check-in.

    Args:
        connection: The underlying connector connection to wrap.
    """

    def __init__(self, connection: Any) -> None:
        self._conn = connection
        self._open_cursors: weakref.WeakSet[_AdbcCursorShim] = weakref.WeakSet()

    def cursor(self) -> _AdbcCursorShim:
        """Open a new ADBC-shaped cursor over the connector connection."""
        shim = _AdbcCursorShim(self._conn.cursor(), connection=self)
        self._open_cursors.add(shim)
        return shim

    def close(self) -> None:
        """Close the underlying connector connection."""
        self._conn.close()

    def commit(self) -> None:
        """Commit (DB-API compat; a connector no-op when transactions are ignored)."""
        self._conn.commit()

    def rollback(self) -> None:
        """Roll back (DB-API compat; called by the pool on check-in)."""
        self._conn.rollback()

    @property
    def autocommit(self) -> bool:
        """Autocommit state of the underlying connection."""
        return self._conn.autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        self._conn.autocommit = value

    def _close_open_cursors(self) -> None:
        """Close any still-open shim cursors to release Arrow/CloudFetch buffers."""
        for shim in list(self._open_cursors):
            if not shim._closed:  # noqa: SLF001  (sibling adapter, intentional)
                with contextlib.suppress(Exception):  # best-effort buffer release
                    shim.close()

    def _adbc_unsupported(self, name: str) -> Any:
        raise NotSupportedError(
            f"{name}() is not available on the Databricks Python connector backend."
        )

    def adbc_get_info(self, *args: Any, **kwargs: Any) -> Any:
        """Unsupported: ADBC driver-metadata introspection."""
        return self._adbc_unsupported("adbc_get_info")

    def adbc_get_objects(self, *args: Any, **kwargs: Any) -> Any:
        """Unsupported: ADBC catalog/schema introspection."""
        return self._adbc_unsupported("adbc_get_objects")

    def adbc_get_table_schema(self, *args: Any, **kwargs: Any) -> Any:
        """Unsupported: ADBC table-schema introspection."""
        return self._adbc_unsupported("adbc_get_table_schema")

    def adbc_get_table_types(self, *args: Any, **kwargs: Any) -> Any:
        """Unsupported: ADBC table-type introspection."""
        return self._adbc_unsupported("adbc_get_table_types")
