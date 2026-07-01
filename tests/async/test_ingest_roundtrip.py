"""
Async bulk-write round-trip + data pass-through (INGEST-01/03) --- Wave-0 RED scaffolding.

Phase 30 adds `await cursor.adbc_ingest(table_name, data, *, mode=...)`, a single
whole-operation offload that hands an Arrow payload to the driver untouched and
returns the affected row count as an `int`. These tests pin the two happy-path
contracts against the real DuckDB driver:

- **INGEST-01:** a `create` ingest returns the driver row count (`int`), the rows
  land, and a follow-up `append` accumulates --- a genuine whole-op offload, with
  the connection checked back in the instant each ingest returns (no reader
  lifetime lock).
- **INGEST-03:** `data` is pass-through with ZERO conversion --- both a
  `pyarrow.Table` and a `pyarrow.RecordBatch` ingest and round-trip unchanged.

Wave-0 status: `AsyncCursor.adbc_ingest` does NOT exist yet, so every test here
FAILS (RED). That is the acceptance signal --- the tests encode the observable
contract Plan 30-02 turns GREEN. Both backends (asyncio x trio) via the
`anyio_backend` fixture; DuckDB is the real driver leg.
"""

from __future__ import annotations

# Wave-0 RED scaffolding: `AsyncCursor.adbc_ingest` does not exist until Plan 30-02
# lands, so every reference to it is statically "unknown". These pragmas suppress
# ONLY the errors that are a direct consequence of that not-yet-existing method;
# delete the `adbc_ingest`-driven pragmas once the production method lands and the
# file type-checks cleanly under the strict whole-project gate (PKG-01). The
# `object`-fetch pragmas (`reportIndexIssue` etc.) reflect the deliberately-loose
# `fetchone`/`fetchall` return typing (`_SyncCursor` returns `object`), matching the
# Phase 29 reader-test precedent.
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportIndexIssue=false
# pyright: reportGeneralTypeIssues=false
from typing import TYPE_CHECKING

import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestIngest01RoundTrip:
    """INGEST-01: `adbc_ingest` returns the driver row count; create then append."""

    @pytest.mark.anyio
    async def test_create_then_append_round_trip(self, duckdb_async_pool: AsyncPool) -> None:
        """
        A `create` ingest returns the row count and the rows are queryable; `append` accumulates.

        Mirrors the RESEARCH round-trip: ingest three rows with `mode="create"`
        (returns `3`), count them back (`3`), then ingest the same table again with
        `mode="append"` (returns `3`) and count the accumulated total (`6`). Proves
        the whole-op offload materializes and the connection is usable immediately
        after each ingest.
        """
        table = pyarrow.table({"id": [1, 2, 3], "name": ["a", "b", "c"]})
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()

            created = await cursor.adbc_ingest("people", table, mode="create")
            assert created == 3

            await cursor.execute("SELECT count(*) FROM people")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 3

            appended = await cursor.adbc_ingest("people", table, mode="append")
            assert appended == 3

            await cursor.execute("SELECT count(*) FROM people")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 6


class TestIngest03DataPassThrough:
    """INGEST-03: `data` is handed to the driver unconverted (Table and RecordBatch)."""

    @pytest.mark.anyio
    async def test_data_passthrough(self, duckdb_async_pool: AsyncPool) -> None:
        """
        Both a `pyarrow.Table` and a `pyarrow.RecordBatch` ingest and round-trip unchanged.

        INGEST-03's zero-conversion contract: poolhouse never rewraps the Arrow
        payload. A `pyarrow.Table` ingests into one table and a `pyarrow.RecordBatch`
        into another; both round-trip their exact rows back through a `SELECT`,
        proving the driver received the object poolhouse was handed with no
        conversion in between.
        """
        table = pyarrow.table({"id": [10, 20], "label": ["x", "y"]})
        batch = pyarrow.record_batch({"id": [30, 40, 50], "label": ["p", "q", "r"]})
        async with await duckdb_async_pool.connect() as conn:
            cursor = conn.cursor()

            table_rows = await cursor.adbc_ingest("from_table", table, mode="create")
            assert table_rows == 2
            batch_rows = await cursor.adbc_ingest("from_batch", batch, mode="create")
            assert batch_rows == 3

            await cursor.execute("SELECT id FROM from_table ORDER BY id")
            table_ids = [r[0] for r in await cursor.fetchall()]
            assert table_ids == [10, 20]

            await cursor.execute("SELECT id FROM from_batch ORDER BY id")
            batch_ids = [r[0] for r in await cursor.fetchall()]
            assert batch_ids == [30, 40, 50]
