"""
Databricks Python-connector backend: pool backend, ADBC-dbapi adapters, connect().

`adbc-poolhouse` pools ADBC connections and downstream code relies on the ADBC
DBAPI surface (``cursor.fetch_arrow_table()``, ``adbc_cancel()``, ...). The
Databricks Python connector (`databricks-sql-connector`) is PEP 249 DB-API 2.0
but spells its Arrow accessors differently (``fetchall_arrow`` /
``fetchmany_arrow``) and lacks the ``adbc_*`` extensions.

This module holds everything specific to that connector:

- ``_DatabricksPythonCursor`` and ``_DatabricksPythonConnection`` translate a
  connector connection/cursor into the ADBC DBAPI shape, so the backend is
  indistinguishable from an ADBC one to callers and to the async layer. ADBC-only
  methods with no faithful connector equivalent raise ``NotSupportedError`` (the
  ADBC DBAPI error type callers already catch).
- ``connect`` is the single patchable entry point `pytest-adbc-replay` intercepts
  (via ``adbc_auto_patch``).
- ``DatabricksPythonBackend`` is the `ConnectionBackend` the pool factory builds a
  QueuePool from.

The connector and `pyarrow` are imported lazily, so `import adbc_poolhouse` and
pytest session-start patching stay connector-free.
"""

from __future__ import annotations

import contextlib
import weakref
from typing import TYPE_CHECKING, Any

from adbc_driver_manager.dbapi import NotSupportedError

if TYPE_CHECKING:
    from collections.abc import Callable

    import pyarrow


class _DatabricksPythonCursor:
    """
    Present a Databricks connector cursor as an ADBC DBAPI cursor.

    Wraps a single connector ``Cursor`` and forwards the DB-API 2.0 surface
    unchanged while mapping ADBC's Arrow accessors onto the connector's
    (``fetch_arrow_table`` -> ``fetchall_arrow``, etc.). ADBC-only extensions
    that the connector cannot serve raise ``NotSupportedError``.

    Args:
        cursor: The underlying connector cursor to wrap.
        connection: The owning `_DatabricksPythonConnection`, returned by the
            DB-API ``connection`` attribute.
    """

    def __init__(self, cursor: Any, connection: _DatabricksPythonConnection) -> None:
        self._cursor = cursor
        self._connection = connection
        self._closed = False

    # ----- DB-API 2.0 pass-through -----

    def execute(self, operation: str, parameters: Any = None) -> _DatabricksPythonCursor:
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
    def connection(self) -> _DatabricksPythonConnection:
        """The `_DatabricksPythonConnection` that opened this cursor."""
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


class _DatabricksPythonConnection:
    """
    Present a Databricks connector connection as an ADBC DBAPI connection.

    Wraps a connector ``Connection``, hands out `_DatabricksPythonCursor` cursors,
    and forwards ``close`` / ``commit`` / ``rollback`` / ``autocommit``. ADBC
    connection-metadata methods (``adbc_get_info`` etc.) raise
    ``NotSupportedError``. Open cursors are tracked weakly so the pool's reset
    hook can close them and release Arrow buffers on check-in.

    Args:
        connection: The underlying connector connection to wrap.
    """

    def __init__(self, connection: Any) -> None:
        self._conn = connection
        self._open_cursors: weakref.WeakSet[_DatabricksPythonCursor] = weakref.WeakSet()

    def cursor(self) -> _DatabricksPythonCursor:
        """Open a new ADBC-shaped cursor over the connector connection."""
        cursor = _DatabricksPythonCursor(self._conn.cursor(), connection=self)
        self._open_cursors.add(cursor)
        return cursor

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
        """Close any still-open cursors to release Arrow/CloudFetch buffers."""
        for cursor in list(self._open_cursors):
            if not cursor._closed:  # noqa: SLF001  (sibling adapter, intentional)
                with contextlib.suppress(Exception):  # best-effort buffer release
                    cursor.close()

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


def connect(**kwargs: Any) -> _DatabricksPythonConnection:
    """
    Open a Databricks Python-connector connection wrapped as ADBC DBAPI.

    This is the single patchable entry point `pytest-adbc-replay` intercepts (via
    ``adbc_auto_patch``); recording happens below the returned adapter, which
    already presents the ADBC DBAPI surface. The connector import is deferred to
    call time so this module imports connector-free at pytest session start.

    Args:
        **kwargs: Connector connection kwargs as built by
            ``DatabricksPythonConfig.to_connect_kwargs()`` (``server_hostname``,
            ``http_path``, ``access_token`` / ``credentials_provider`` /
            ``auth_type``, ``catalog``, ``schema``, ``use_kernel``, ...).

    Returns:
        A `_DatabricksPythonConnection` presenting the ADBC DBAPI surface.
    """
    # The connector ships no type stubs; suppressions are concentrated on this
    # single lazy import + call, the only place the connector is touched directly.
    from databricks import sql  # type: ignore[reportMissingTypeStubs]  # noqa: PLC0415

    return _DatabricksPythonConnection(sql.connect(**kwargs))  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]


class DatabricksPythonBackend:
    """
    A `ConnectionBackend` backed by the Databricks Python connector.

    Each pooled connection is an independent connector connection (there is no
    cheap ``adbc_clone``), opened through the module-level `connect` so
    `pytest-adbc-replay` can intercept it. There is no shared source to close;
    the reset hook closes any open cursors to release Arrow/CloudFetch buffers.

    Args:
        connect_kwargs: Connector kwargs from
            ``DatabricksPythonConfig.to_connect_kwargs()``.
    """

    def __init__(self, connect_kwargs: dict[str, Any]) -> None:
        self._connect_kwargs = connect_kwargs

    def creator(self) -> Callable[[], Any]:
        """
        Return a callable that opens one connector connection.

        The callable resolves ``connect`` off this module at call time (not import
        time) so a `pytest-adbc-replay` monkeypatch of the module's ``connect`` is
        honored.
        """
        # Reference the module (not the bare function) so attribute access happens
        # at call time and picks up any patched connect.
        from adbc_poolhouse._adapters import _databricks_python as module  # noqa: PLC0415

        kwargs = self._connect_kwargs

        def _open() -> Any:
            return module.connect(**kwargs)

        return _open

    def close(self) -> None:
        """No shared source to close; pooled connections are closed by ``dispose``."""

    def on_reset(self, dbapi_conn: object) -> None:
        """Close open cursors on ``dbapi_conn`` to release Arrow buffers, if it tracks any."""
        closer = getattr(dbapi_conn, "_close_open_cursors", None)
        if closer is not None:
            closer()
