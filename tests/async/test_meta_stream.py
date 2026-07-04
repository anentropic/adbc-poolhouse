"""
Async metadata streaming reader (META-02) --- Wave-0 RED scaffolding.

Locked decision #1 streams the Arrow-returning metadata surfaces rather than
materializing them: `adbc_get_objects` hands back a live
[`AsyncRecordBatchReader`][adbc_poolhouse._async._reader.AsyncRecordBatchReader]
bound to the checked-out connection, drained batch-by-batch off the event loop ---
never an eager `pyarrow.Table`. This suite pins that streaming contract against the
real DuckDB driver:

- **Drain (STREAM-04 analog):** `async with await conn.adbc_get_objects(...) as
  reader:` exposes `reader.schema` as a `pyarrow.Schema` (a sync property
  passthrough) and yields `pyarrow.RecordBatch` values under `async for`; on scope
  exit the connection checks back in and `pool.checkedout()` returns to 0.
- **Busy-guard (locked decision #5 / D-29-10):** while the metadata reader is live
  it holds the connection's reader-lifetime lock (`_reader_open`), so a foreign
  `await conn.commit()` is rejected with
  [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] rather than
  interleaving into the still-open C stream.

Wave-0 status: `adbc_get_objects` does not exist on `AsyncConnection` yet, so every
test here FAILS (RED) with `AttributeError` --- the acceptance signal Plan 34-02
turns GREEN. Both backends (asyncio x trio) via `anyio_backend`; DuckDB is the real
driver leg. The drain body keeps no shared mutable state across iterations so it
stays loop-safe under the `ADBC_ASYNC_REPEAT=20` wave-merge gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow
import pytest

from adbc_poolhouse import ConnectionBusyError

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestMeta02Stream:
    """META-02: `adbc_get_objects` streams via `AsyncRecordBatchReader` (no materialization)."""

    @pytest.mark.anyio
    async def test_get_objects_drains_then_checkin_duckdb(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        Draining `adbc_get_objects(depth="tables")` yields batches; the pool then drains.

        Iterates the metadata reader INSIDE the connection scope (the safe, canonical
        path): `reader.schema` is a `pyarrow.Schema` (sync property passthrough) and
        every `async for` batch is a `pyarrow.RecordBatch`. On scope exit the
        connection is checked back in and `pool.checkedout()` returns to 0, proving
        the streaming reader releases the connection's reader-lifetime lock cleanly.
        """
        batch_count = 0
        async with (
            await duckdb_async_pool.connect() as conn,
            await conn.adbc_get_objects(depth="tables") as reader,
        ):
            assert isinstance(reader.schema, pyarrow.Schema)
            async for batch in reader:
                assert isinstance(batch, pyarrow.RecordBatch)
                batch_count += 1
        assert batch_count >= 1
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001

    @pytest.mark.anyio
    async def test_live_metadata_reader_blocks_foreign_commit_duckdb(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        A foreign `commit` while the metadata reader is live raises `ConnectionBusyError`.

        The live `adbc_get_objects` reader holds the connection's reader-lifetime lock
        (`_reader_open`, D-29-10), so a concurrent `commit` on the same connection is
        rejected with `ConnectionBusyError` rather than interleaving into the
        still-open C stream. This locks the two-tier guard for the connection-level
        metadata reader as cheaply as the cursor-level streaming path (locked decision
        #5). After the scope exits, the connection still checks back in cleanly.
        """
        async with (
            await duckdb_async_pool.connect() as conn,
            await conn.adbc_get_objects(depth="tables") as reader,
        ):
            assert isinstance(reader.schema, pyarrow.Schema)
            with pytest.raises(ConnectionBusyError):
                await conn.commit()
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001

    @pytest.mark.anyio
    async def test_get_objects_forwards_filters_duckdb(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `adbc_get_objects` forwards its keyword filters through `functools.partial`.

        Creates a table, then streams `adbc_get_objects` with explicit
        `catalog_filter` / `db_schema_filter` / `table_name_filter` keywords (WR-34-02).
        The reader still drains and the pool drains to 0 --- proving the non-default
        filters reach the driver arity-checked rather than being dropped or raising.
        """
        async with await duckdb_async_pool.connect() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("CREATE TABLE scoped_t (id INTEGER)")
            batch_count = 0
            async with await conn.adbc_get_objects(
                depth="columns",
                db_schema_filter="main",
                table_name_filter="scoped_t",
            ) as reader:
                async for batch in reader:
                    assert isinstance(batch, pyarrow.RecordBatch)
                    batch_count += 1
            assert batch_count >= 1
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001

    @pytest.mark.anyio
    async def test_streaming_metadata_reader_is_not_poison_on_cancel_duckdb(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        The metadata reader is wired non-poisoning (CR-34-01 wiring guard).

        The streaming metadata methods have no `adbc_cancel`, so their reader is built
        with `poison_on_cancel=False`: a cancelled pull must NOT invalidate a
        connection whose worker cannot be aborted (that would race a second thread
        against the live read). This asserts the wiring directly; the cancel-time
        behavior itself is exercised deterministically in `test_meta_cancel.py`.
        """
        async with (
            await duckdb_async_pool.connect() as conn,
            await conn.adbc_get_objects(depth="tables") as reader,
        ):
            assert reader._poison_on_cancel is False  # noqa: SLF001


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
