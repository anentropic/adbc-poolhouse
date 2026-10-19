"""
Unit tests for the Databricks Python-connector ADBC adapters.

These drive `_DatabricksPythonCursor` / `_DatabricksPythonConnection` over a fake
connector cursor so the ADBC-name translation and the `NotSupportedError` gaps are
covered without a live connector or a cassette.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa
import pytest
from adbc_driver_manager.dbapi import NotSupportedError

from adbc_poolhouse._adapters._databricks_python import _DatabricksPythonConnection


class _FakeCursor:
    """Minimal Databricks connector cursor stand-in."""

    def __init__(self, table: pa.Table) -> None:
        self._table = table
        self._offset = 0
        self.arraysize = 2
        self.rowcount = -1
        self.description = [
            (name, None, None, None, None, None, None) for name in table.schema.names
        ]
        self.rownumber = 0
        self.cancelled = False
        self.closed = False
        self.last_execute: tuple[Any, Any] | None = None

    def execute(self, operation: str, parameters: Any = None) -> None:
        self.last_execute = (operation, parameters)

    def executemany(self, operation: str, seq_of_parameters: Any) -> None:
        self.last_execute = (operation, seq_of_parameters)

    def fetchall_arrow(self) -> pa.Table:
        return self._table

    def fetchmany_arrow(self, size: int) -> pa.Table:
        sliced = self._table.slice(self._offset, size)
        self._offset += sliced.num_rows
        return sliced

    def fetchone(self) -> Any:
        if self._offset >= self._table.num_rows:
            return None
        row = self._table.slice(self._offset, 1).to_pylist()[0]
        self._offset += 1
        return row

    def fetchmany(self, size: int) -> list[Any]:
        rows = self._table.slice(self._offset, size).to_pylist()
        self._offset += len(rows)
        return rows

    def fetchall(self) -> list[Any]:
        rows = self._table.slice(self._offset).to_pylist()
        self._offset = self._table.num_rows
        return rows

    def setinputsizes(self, sizes: Any) -> None:
        pass

    def setoutputsize(self, size: Any, column: Any = None) -> None:
        pass

    def cancel(self) -> None:
        self.cancelled = True

    def close(self) -> None:
        self.closed = True


class _FakeConn:
    def __init__(self, table: pa.Table) -> None:
        self._cursor = _FakeCursor(table)
        self.closed = False
        self.autocommit = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


@pytest.fixture
def table() -> pa.Table:
    return pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})


@pytest.fixture
def adapter(table: pa.Table) -> _DatabricksPythonConnection:
    return _DatabricksPythonConnection(_FakeConn(table))


def test_fetch_arrow_table_maps_to_fetchall_arrow(adapter: _DatabricksPythonConnection) -> None:
    cur = adapter.cursor()
    assert cur.fetch_arrow_table().num_rows == 3
    assert cur.fetchallarrow().num_rows == 3


def test_fetch_record_batch_streams_all_rows(adapter: _DatabricksPythonConnection) -> None:
    cur = adapter.cursor()
    reader = cur.fetch_record_batch()
    total = sum(batch.num_rows for batch in reader)
    assert total == 3


def test_fetch_df(adapter: _DatabricksPythonConnection) -> None:
    pytest.importorskip("pandas")
    cur = adapter.cursor()
    assert list(cur.fetch_df()["a"]) == [1, 2, 3]


def test_fetch_polars(adapter: _DatabricksPythonConnection) -> None:
    pytest.importorskip("polars")
    cur = adapter.cursor()
    pl_df = cur.fetch_polars()
    assert pl_df.shape[0] == 3


def test_fetchmany_defaults_to_arraysize(adapter: _DatabricksPythonConnection) -> None:
    cur = adapter.cursor()
    # arraysize is 2 on the fake cursor; fetchmany(None) must use it.
    assert len(cur.fetchmany()) == 2


def test_passthrough_properties(adapter: _DatabricksPythonConnection) -> None:
    cur = adapter.cursor()
    assert cur.rowcount == -1
    assert cur.description is not None
    assert cur.arraysize == 2
    cur.arraysize = 10
    assert cur.arraysize == 10
    assert cur.connection is adapter


def test_adbc_cancel_maps_to_connector_cancel(adapter: _DatabricksPythonConnection) -> None:
    cur = adapter.cursor()
    cur.adbc_cancel()
    assert adapter._conn._cursor.cancelled is True  # noqa: SLF001


def test_close_open_cursors_releases_buffers(adapter: _DatabricksPythonConnection) -> None:
    cur = adapter.cursor()
    adapter._close_open_cursors()  # noqa: SLF001
    assert adapter._conn._cursor.closed is True  # noqa: SLF001
    assert cur._closed is True  # noqa: SLF001


@pytest.mark.parametrize(
    "method",
    [
        "fetch_arrow",
        "adbc_ingest",
        "adbc_prepare",
        "adbc_execute_schema",
        "adbc_execute_partitions",
        "adbc_read_partition",
    ],
)
def test_cursor_gaps_raise_not_supported(adapter: _DatabricksPythonConnection, method: str) -> None:
    cur = adapter.cursor()
    with pytest.raises(NotSupportedError):
        getattr(cur, method)()


@pytest.mark.parametrize(
    "method",
    ["adbc_get_info", "adbc_get_objects", "adbc_get_table_schema", "adbc_get_table_types"],
)
def test_connection_metadata_gaps_raise_not_supported(
    adapter: _DatabricksPythonConnection, method: str
) -> None:
    with pytest.raises(NotSupportedError):
        getattr(adapter, method)()


# ----- Connector errors surface as ADBC DBAPI errors -----
#
# Callers catch `adbc_driver_manager` errors; a connector `databricks.sql.exc` error that
# passed through unchanged slipped past every such handler. The adapter re-raises each one as
# the ADBC class of the same PEP 249 category, chaining the connector error as `__cause__`.

dbsql_exc = pytest.importorskip("databricks.sql.exc")


def _error_classes() -> list[tuple[str, str]]:
    """(connector class name, expected ADBC class name), most specific connector class first."""
    return [
        ("ServerOperationError", "DatabaseError"),
        ("RequestError", "OperationalError"),
        ("OperationalError", "OperationalError"),
        ("ProgrammingError", "ProgrammingError"),
        ("NotSupportedError", "NotSupportedError"),
        ("IntegrityError", "IntegrityError"),
        ("DataError", "DataError"),
        ("InternalError", "InternalError"),
        ("InterfaceError", "InterfaceError"),
        ("DatabaseError", "DatabaseError"),
        ("Error", "Error"),
    ]


class _RaisingCursor(_FakeCursor):
    """A fake connector cursor whose every connector call raises ``error``."""

    def __init__(self, table: pa.Table, error: BaseException) -> None:
        super().__init__(table)
        self.error = error

    def _raise(self, *args: Any, **kwargs: Any) -> Any:
        raise self.error

    execute = executemany = fetchone = fetchmany = fetchall = _raise
    fetchall_arrow = fetchmany_arrow = cancel = _raise


def _raising_adapter(table: pa.Table, error: BaseException) -> _DatabricksPythonConnection:
    conn = _FakeConn(table)
    conn._cursor = _RaisingCursor(table, error)  # noqa: SLF001
    return _DatabricksPythonConnection(conn)


@pytest.mark.parametrize(("connector_cls", "adbc_cls"), _error_classes())
def test_execute_reraises_connector_errors_as_adbc(
    table: pa.Table, connector_cls: str, adbc_cls: str
) -> None:
    import adbc_driver_manager.dbapi as adbc

    error = getattr(dbsql_exc, connector_cls)("warehouse said no")
    cur = _raising_adapter(table, error).cursor()

    with pytest.raises(adbc.Error) as info:
        cur.execute("SELECT 1")

    assert type(info.value) is getattr(adbc, adbc_cls)
    assert info.value.__cause__ is error
    assert "warehouse said no" in str(info.value)


@pytest.mark.parametrize(
    "call",
    [
        lambda cur: cur.executemany("INSERT", [()]),
        lambda cur: cur.fetchone(),
        lambda cur: cur.fetchmany(1),
        lambda cur: cur.fetchall(),
        lambda cur: cur.fetch_arrow_table(),
        lambda cur: cur.fetchallarrow(),
        lambda cur: cur.fetch_record_batch(),
        lambda cur: cur.fetch_df(),
        lambda cur: cur.fetch_polars(),
        lambda cur: cur.adbc_cancel(),
    ],
    ids=[
        "executemany",
        "fetchone",
        "fetchmany",
        "fetchall",
        "fetch_arrow_table",
        "fetchallarrow",
        "fetch_record_batch",
        "fetch_df",
        "fetch_polars",
        "adbc_cancel",
    ],
)
def test_every_cursor_call_translates(table: pa.Table, call: Any) -> None:
    import adbc_driver_manager.dbapi as adbc

    error = dbsql_exc.RequestError("connection dropped")
    cur = _raising_adapter(table, error).cursor()

    with pytest.raises(adbc.OperationalError) as info:
        call(cur)

    assert info.value.__cause__ is error


def test_a_failure_mid_stream_translates(table: pa.Table) -> None:
    """An error fetching a later batch surfaces from ``read_next_batch`` as an ADBC error."""
    import adbc_driver_manager.dbapi as adbc

    conn = _FakeConn(table)
    calls = {"n": 0}
    real = conn._cursor.fetchmany_arrow  # noqa: SLF001
    error = dbsql_exc.RequestError("CloudFetch link expired")

    def _second_call_fails(size: int) -> pa.Table:
        calls["n"] += 1
        if calls["n"] > 1:
            raise error
        return real(size)

    conn._cursor.fetchmany_arrow = _second_call_fails  # type: ignore[method-assign]  # noqa: SLF001
    reader = _DatabricksPythonConnection(conn).cursor().fetch_record_batch()

    reader.read_next_batch()
    with pytest.raises(adbc.OperationalError) as info:
        reader.read_next_batch()
    assert info.value.__cause__ is error


@pytest.mark.parametrize("method", ["close", "commit", "rollback", "cursor"])
def test_connection_calls_translate(table: pa.Table, method: str) -> None:
    import adbc_driver_manager.dbapi as adbc

    error = dbsql_exc.InterfaceError("session closed")
    conn = _FakeConn(table)

    def _raise(*_args: Any) -> Any:
        raise error

    setattr(conn, method, _raise)

    with pytest.raises(adbc.InterfaceError) as info:
        getattr(_DatabricksPythonConnection(conn), method)()
    assert info.value.__cause__ is error


def test_connect_translates_connector_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused connection (bad token, unreachable host) is an ADBC ``OperationalError``."""
    import adbc_driver_manager.dbapi as adbc
    import databricks.sql

    from adbc_poolhouse._adapters import _databricks_python

    error = dbsql_exc.RequestError("Error during request to server: 401")

    def _refuse(**_kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(databricks.sql, "connect", _refuse)

    with pytest.raises(adbc.OperationalError) as info:
        _databricks_python.connect(server_hostname="h", http_path="p")
    assert info.value.__cause__ is error


def test_non_connector_errors_pass_through(table: pa.Table) -> None:
    """Only connector DB-API errors are translated; a plain bug keeps its own type."""
    error = ValueError("not a database error")
    cur = _raising_adapter(table, error).cursor()

    with pytest.raises(ValueError, match="not a database error"):
        cur.execute("SELECT 1")
