"""
Async `adbc_execute_schema` native-error passthrough (PREP-02, EDGE-17).

Locked decision D-35-06 (the milestone's governing principle: no bespoke async
error type) says an async prepared-statement method mirrors the sync driver's
native error. The async wrapper must surface whatever the sync
`adbc_driver_manager.dbapi.Cursor.adbc_execute_schema` does --- UNCHANGED --- with
no `PoolhouseError` wrapping, no `find_spec` pre-check, no swallowing, through the
single offload chokepoint (EDGE-17), and the connection must still check back in
cleanly after a failed call (`pool.checkedout() == 0`, T-35-02).

Driver note (updated for adbc-driver-duckdb / duckdb 1.5.4): DuckDB now *does*
implement result-schema resolution, so `adbc_execute_schema` on a valid query
returns a `pyarrow.Schema` rather than raising `NotSupportedError` (the earlier
`NOT_IMPLEMENTED` behavior was removed upstream). The native-error passthrough is
therefore pinned against a query the driver genuinely errors on (an unknown table,
which raises a native `adbc_driver_manager.InternalError` catalog error). The
assertion is that the error is the driver's own native `adbc_driver_manager.Error`
--- never a `PoolhouseError` --- so the "no invented error type" contract holds
regardless of which native error the driver raises. Both backends (asyncio x trio)
via `anyio_backend`; DuckDB is the real driver leg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow
import pytest
from adbc_driver_manager import Error as AdbcError

from adbc_poolhouse._exceptions import PoolhouseError

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestPrep02NativeErrorPassthrough:
    """PREP-02: `adbc_execute_schema` surfaces the driver's native error unwrapped."""

    @pytest.mark.anyio
    async def test_execute_schema_native_error_passthrough(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        A native driver error from `adbc_execute_schema()` propagates unchanged.

        Querying an unknown table makes DuckDB raise a native
        `adbc_driver_manager.InternalError` (a catalog error). The async wrapper must
        let that native `adbc_driver_manager.Error` propagate unchanged (D-35-06,
        EDGE-17) --- the "no invented error type" assertion: the error is the driver's
        own, never a `PoolhouseError`, surfaced through the single offload chokepoint.
        After the failed call the connection still checks back in cleanly, so
        `pool.checkedout()` returns to 0 --- the failed call does not leak the
        connection (T-35-02).
        """
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            with pytest.raises(AdbcError) as excinfo:
                await cursor.adbc_execute_schema("SELECT * FROM __adbc_poolhouse_no_such_table__")
            assert not isinstance(excinfo.value, PoolhouseError)
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001

    @pytest.mark.anyio
    async def test_execute_schema_supported_returns_schema(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        On a driver that implements it, `adbc_execute_schema()` returns the schema.

        DuckDB 1.5.4 resolves the result schema without executing the query, so a
        valid statement returns a `pyarrow.Schema` (PREP-02's positive contract on the
        real driver). The connection checks back in cleanly afterwards.
        """
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            schema = await cursor.adbc_execute_schema("SELECT 1 AS a")
            assert isinstance(schema, pyarrow.Schema)
            assert schema.names == ["a"]
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
