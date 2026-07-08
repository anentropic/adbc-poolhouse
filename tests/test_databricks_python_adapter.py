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
        self.description = [(f.name, None, None, None, None, None, None) for f in table.schema]
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
