"""
Async metadata value round-trip (META-01/02) --- Wave-0 RED scaffolding.

Phase 34 adds the value-returning metadata methods to
[`AsyncConnection`][adbc_poolhouse._async._connection.AsyncConnection]: each hands
the sync `adbc_driver_manager.dbapi.Connection` call to a worker thread and returns
the driver's own object untouched (locked decision #4 --- no rewrapping). This
suite pins the three happy-path return-type contracts against the real DuckDB
driver:

- `adbc_get_info()` → a `dict` of driver/vendor info codes.
- `adbc_get_table_types()` → a `list` of the backend's table-type strings.
- `adbc_get_table_schema("t")` → a `pyarrow.Schema` whose field names match the
  columns of the table just created.

The connection checks back in the instant each value method returns (no reader
lifetime lock), so `pool.checkedout()` returns to 0 once the scope exits ---
proving the `_offloading()` guard releases the connection cleanly (T-34-02).

Wave-0 status: none of the metadata methods exist on `AsyncConnection` yet, so
every test here FAILS (RED) with `AttributeError`. That is the acceptance signal
--- the tests encode the observable contract Plan 34-02 turns GREEN. Both backends
(asyncio x trio) via the `anyio_backend` fixture; DuckDB is the real driver leg.
"""

from __future__ import annotations

# Wave-0 RED scaffolding: the `adbc_get_*` methods on `AsyncConnection` do not
# exist until plan 34-02 lands them, so every reference to them is statically
# "unknown". These pragmas suppress ONLY the errors that are a direct consequence
# of those not-yet-existing symbols; delete this block once the production symbols
# land and the file type-checks cleanly under the strict whole-project gate.
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
from typing import TYPE_CHECKING

import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestMeta01ValueRoundTrip:
    """META-01/02: the value metadata methods return the driver's native objects."""

    @pytest.mark.anyio
    async def test_value_methods_round_trip_duckdb(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `adbc_get_info` / `adbc_get_table_types` / `adbc_get_table_schema` return native values.

        Inside one connection scope: `adbc_get_info()` yields a `dict`,
        `adbc_get_table_types()` yields a `list`, and --- after creating a two-column
        table --- `adbc_get_table_schema("t")` yields a `pyarrow.Schema` whose field
        names are exactly the created columns. On scope exit the connection is checked
        back in and `pool.checkedout()` returns to 0, proving each whole-op offload
        released the connection.
        """
        async with await duckdb_async_pool.connect() as conn:
            info = await conn.adbc_get_info()
            assert isinstance(info, dict)

            table_types = await conn.adbc_get_table_types()
            assert isinstance(table_types, list)

            cursor = conn.cursor()
            await cursor.execute("CREATE TABLE t (id INTEGER, name VARCHAR)")

            schema = await conn.adbc_get_table_schema("t")
            assert isinstance(schema, pyarrow.Schema)
            assert schema.names == ["id", "name"]

        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
