"""
Async bulk-write mode forwarding (INGEST-02) --- Wave-0 RED scaffolding.

Phase 30 forwards `mode` verbatim to the driver as a typed
`Literal["create", "append", "replace", "create_append"]` --- poolhouse does no
validation and no remapping. These tests pin that each of the four modes reaches
the DuckDB driver and produces its documented effect, with special attention to
`replace`, whose name misleads: ADBC's `replace` DROPS the existing table and
recreates it (not a row-level upsert).

- **create:** builds a new table.
- **append:** adds rows to an existing table (cumulative count).
- **create_append:** creates the table if absent, else appends.
- **replace:** drops-then-recreates --- the post-replace count is the NEW table's
  row count, never the cumulative total (the load-bearing INGEST-02 assertion).

Wave-0 status: `AsyncCursor.adbc_ingest` does NOT exist yet, so every test here
FAILS (RED) --- the acceptance signal. Both backends via `anyio_backend`; DuckDB
is the real driver leg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


async def _count(cursor: object, table_name: str) -> int:
    """Return `count(*)` for a table via the async cursor (test helper)."""
    await cursor.execute(f"SELECT count(*) FROM {table_name}")  # type: ignore[attr-defined]
    row = await cursor.fetchone()  # type: ignore[attr-defined]
    assert row is not None
    return int(row[0])  # type: ignore[index]  # _SyncCursor.fetchone returns object


class TestIngest02Modes:
    """INGEST-02: each of the four `Literal` modes reaches the driver verbatim."""

    @pytest.mark.anyio
    async def test_create_and_append(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `create` builds the table; `append` accumulates onto it.

        The two most common modes: a `create` of three rows followed by an `append`
        of three more leaves six rows, proving both modes reach the driver and
        `append` is additive.
        """
        table = pyarrow.table({"id": [1, 2, 3]})
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            await cursor.adbc_ingest("t_ca", table, mode="create")
            assert await _count(cursor, "t_ca") == 3
            await cursor.adbc_ingest("t_ca", table, mode="append")
            assert await _count(cursor, "t_ca") == 6

    @pytest.mark.anyio
    async def test_create_append(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `create_append` creates when absent, then appends on the second call.

        A first `create_append` builds the table (three rows); a second
        `create_append` of the same data appends rather than failing on the existing
        table --- the count reaches six.
        """
        table = pyarrow.table({"id": [1, 2, 3]})
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            await cursor.adbc_ingest("t_crapp", table, mode="create_append")
            assert await _count(cursor, "t_crapp") == 3
            await cursor.adbc_ingest("t_crapp", table, mode="create_append")
            assert await _count(cursor, "t_crapp") == 6

    @pytest.mark.anyio
    async def test_replace_drops_then_recreates(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `replace` DROPS the existing table and recreates it --- not a cumulative add.

        The load-bearing INGEST-02 assertion (and Pitfall 4): after ingesting three
        rows, a `replace` with a TWO-row table leaves exactly two rows, NOT five. If
        `replace` were additive the count would be five; drop-then-create makes it
        two.
        """
        three = pyarrow.table({"id": [1, 2, 3]})
        two = pyarrow.table({"id": [7, 8]})
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()
            await cursor.adbc_ingest("t_repl", three, mode="create")
            assert await _count(cursor, "t_repl") == 3
            await cursor.adbc_ingest("t_repl", two, mode="replace")
            # Drop-then-create: the new table's row count, never the cumulative 5.
            assert await _count(cursor, "t_repl") == 2
