"""
Async partitioned-execution native-error passthrough (PART-02, EDGE-17).

Partitioned execution (`adbc_execute_partitions` / `adbc_read_partition`) is an ADBC
extension for distributed result sets (Flight SQL and similar). Most backends do not
implement it; the async wrapper must surface whatever the sync
`adbc_driver_manager.dbapi` method does --- UNCHANGED --- with no `PoolhouseError`
wrapping, no `find_spec` pre-check, no swallowing, through the single offload
chokepoint (EDGE-17), and the connection must still check back in cleanly after a
failed call (`pool.checkedout() == 0`).

Driver note: DuckDB (adbc-driver-duckdb) implements neither method --- both raise a
native `adbc_driver_manager.NotSupportedError` ("Execute/Read Partitions are not
supported in DuckDB"). That is the real-driver leg here: the assertion is that the
error is the driver's own native `adbc_driver_manager.Error`, never a
`PoolhouseError`, so the "no invented error type" contract holds. A normal worker
error (not a cancellation) does NOT trip the abort path, so the connection is not
invalidated and checks back in cleanly. Both backends (asyncio x trio) via
`anyio_backend`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from adbc_driver_manager import Error as AdbcError

from adbc_poolhouse._exceptions import PoolhouseError

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestPart02NativeErrorPassthrough:
    """PART-02: the partition methods surface the driver's native error unwrapped."""

    @pytest.mark.anyio
    async def test_execute_partitions_native_error_passthrough(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        A native driver error from `adbc_execute_partitions()` propagates unchanged.

        DuckDB does not implement partitioned execution and raises a native
        `adbc_driver_manager.NotSupportedError`. The async wrapper must let that native
        `adbc_driver_manager.Error` propagate unchanged (EDGE-17) --- never a
        `PoolhouseError`. After the failed (non-cancelled) call the connection still
        checks back in cleanly, so `pool.checkedout()` returns to 0.
        """
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            with pytest.raises(AdbcError) as excinfo:
                await cursor.adbc_execute_partitions("SELECT 1 AS a")
            assert not isinstance(excinfo.value, PoolhouseError)
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001

    @pytest.mark.anyio
    async def test_read_partition_native_error_passthrough(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        A native driver error from `adbc_read_partition()` propagates unchanged.

        DuckDB does not implement partition reads and raises a native
        `adbc_driver_manager.NotSupportedError` for any descriptor. The async wrapper
        surfaces it unchanged (never a `PoolhouseError`), and the connection checks
        back in cleanly afterwards.
        """
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            with pytest.raises(AdbcError) as excinfo:
                await cursor.adbc_read_partition(b"\x00bogus-descriptor")
            assert not isinstance(excinfo.value, PoolhouseError)
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
