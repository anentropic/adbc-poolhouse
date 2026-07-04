"""
Async `adbc_prepare` DuckDB round-trip (PREP-01, D-35-02) --- Wave-0 RED scaffolding.

Phase 35 adds `await cursor.adbc_prepare(operation)`, a single whole-operation
offload that prepares a query WITHOUT executing it and returns the driver's
bind-parameter schema. The sync driver types this as `Optional[pyarrow.Schema]`
--- DuckDB returns a real `pyarrow.Schema`, but a backend that cannot determine
the bind schema returns `None`, and poolhouse forwards either unchanged (D-35-02,
RESEARCH Pitfall 2). This test therefore tolerates BOTH shapes and must NOT assert
a non-null schema.

Because there is no reader lifetime lock (D-35-01), the connection checks back in
the instant the offload returns, so `pool.checkedout()` is `0` once the scope
exits.

Wave-0 status: `AsyncCursor.adbc_prepare` does NOT exist yet, so the call raises
`AttributeError` and this test FAILS (RED) --- the acceptance signal Plan 35-02
turns GREEN. Both backends (asyncio x trio) via `anyio_backend`; DuckDB is the
real driver leg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestPrep01RoundTrip:
    """PREP-01: `adbc_prepare` returns the driver's bind schema (Schema or None)."""

    @pytest.mark.anyio
    async def test_prepare_round_trip(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `adbc_prepare` on DuckDB returns a `pyarrow.Schema` OR `None`; the connection checks in.

        Creates a table, prepares a parameterized `SELECT` against it, and asserts
        the result is `isinstance(result, (pyarrow.Schema, type(None)))` --- Pitfall 2:
        the driver may return the bind-parameter schema OR `None`, and poolhouse
        forwards either unchanged (D-35-02). After the scope exits the pool is drained
        (`checkedout() == 0`) --- there is no reader lifetime lock, so the connection
        returns the moment the offload completes.
        """
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            await cursor.execute("CREATE TABLE t (id INTEGER)")
            result = await cursor.adbc_prepare("SELECT * FROM t WHERE id = ?")
            # Pitfall 2: tolerate BOTH shapes --- do NOT assert a non-null schema.
            assert isinstance(result, (pyarrow.Schema, type(None)))
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001  (no reader lifetime lock)
