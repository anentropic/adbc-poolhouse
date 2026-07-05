"""
Async metadata native-error surfacing (META-03) --- regression coverage.

Locked decision #6 (the milestone's governing principle: no bespoke async error
type) says an async metadata method mirrors the sync driver's native error. The
DuckDB driver does not implement statistics, so both
`adbc_driver_manager.dbapi.Connection.adbc_get_statistics` and
`adbc_get_statistic_names` raise `adbc_driver_manager.NotSupportedError`
[VERIFIED against the installed driver]. This suite pins that the async wrapper
surfaces that native error UNCHANGED --- no `PoolhouseError` wrapping, no
swallowing --- and that the connection still checks back in cleanly after the
failed call (`pool.checkedout() == 0`, T-34-02).

Status: `adbc_get_statistics` and `adbc_get_statistic_names` are implemented on
`AsyncConnection` (Plan 34-02); this file is passing regression coverage of the
native `NotSupportedError` passthrough and clean-checkin contract above. Both
backends (asyncio x trio) via `anyio_backend`; DuckDB is the real driver leg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from adbc_driver_manager import NotSupportedError

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestMeta03Unsupported:
    """META-03: unsupported statistics methods surface the native `NotSupportedError`."""

    @pytest.mark.anyio
    async def test_get_statistics_unsupported_duckdb(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `adbc_get_statistics()` raises the driver's native `NotSupportedError` on DuckDB.

        DuckDB does not implement statistics; the async wrapper must let the native
        `adbc_driver_manager.NotSupportedError` propagate unchanged (locked decision
        #6). After the failed call the connection still checks back in cleanly, so
        `pool.checkedout()` returns to 0 --- the failed metadata call does not leak
        the connection.
        """
        async with await duckdb_async_pool.connect() as conn:
            with pytest.raises(NotSupportedError):
                await conn.adbc_get_statistics()
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001

    @pytest.mark.anyio
    async def test_get_statistic_names_unsupported_duckdb(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        `adbc_get_statistic_names()` raises the native `NotSupportedError` on DuckDB.

        The statistic-names surface is likewise unimplemented by DuckDB; the async
        wrapper surfaces `adbc_driver_manager.NotSupportedError` unchanged, and the
        connection checks back in cleanly afterward (`pool.checkedout() == 0`).
        """
        async with await duckdb_async_pool.connect() as conn:
            with pytest.raises(NotSupportedError):
                await conn.adbc_get_statistic_names()
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
