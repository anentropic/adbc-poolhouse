"""
Async `adbc_execute_schema` native-error passthrough (PREP-02, EDGE-17) --- Wave-0 RED.

Locked decision D-35-06 (the milestone's governing principle: no bespoke async
error type) says an async prepared-statement method mirrors the sync driver's
native error. DuckDB does not implement `adbc_execute_schema`, so the sync
`adbc_driver_manager.dbapi.Cursor.adbc_execute_schema` raises
`adbc_driver_manager.NotSupportedError` (`NOT_IMPLEMENTED: [Driver Manager]
AdbcStatementExecuteSchema not implemented`) [VERIFIED against the installed
driver]. This suite pins that the async wrapper surfaces that native error
UNCHANGED --- no `PoolhouseError` wrapping, no `find_spec` pre-check, no swallowing
--- through the single offload chokepoint (EDGE-17), and that the connection still
checks back in cleanly after the failed call (`pool.checkedout() == 0`, T-35-02).

Wave-0 status: `AsyncCursor.adbc_execute_schema` does not exist on `AsyncCursor`
yet, so `pytest.raises(NotSupportedError)` does NOT match the `AttributeError` the
missing method raises, and this test FAILS (RED). That is the acceptance signal ---
Plan 35-02 turns it GREEN. Both backends (asyncio x trio) via `anyio_backend`;
DuckDB is the real driver leg.
"""

from __future__ import annotations

# Wave-0 RED scaffolding: `AsyncCursor.adbc_execute_schema` does not exist until Plan
# 35-02 lands, so every reference to it is statically "unknown". These pragmas suppress
# ONLY the errors that are a direct consequence of that not-yet-existing method; delete
# them once the production method lands and the file type-checks cleanly under the
# strict whole-project gate (PKG-01). Matches the Phase 30 RED precedent.
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownMemberType=false
from typing import TYPE_CHECKING

import pytest
from adbc_driver_manager import NotSupportedError

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestPrep02Unsupported:
    """PREP-02: unsupported `adbc_execute_schema` surfaces the native `NotSupportedError`."""

    @pytest.mark.anyio
    async def test_execute_schema_unsupported_passthrough(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        `adbc_execute_schema()` raises the driver's native `NotSupportedError` on DuckDB.

        DuckDB does not implement result-schema resolution; the async wrapper must let
        the native `adbc_driver_manager.NotSupportedError` propagate unchanged (D-35-06,
        EDGE-17) --- the "no invented error type" assertion, the driver's native
        `NOT_IMPLEMENTED` message surfaced unwrapped through the single offload
        chokepoint. After the failed call the connection still checks back in cleanly,
        so `pool.checkedout()` returns to 0 --- the failed call does not leak the
        connection (T-35-02).
        """
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            with pytest.raises(NotSupportedError):
                await cursor.adbc_execute_schema("SELECT 1")
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
