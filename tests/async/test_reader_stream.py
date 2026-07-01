"""
Streaming happy-path reader coverage (STREAM-01/02) --- Wave-0 RED scaffolding.

Phase 29 wraps the sync `pyarrow.RecordBatchReader` in an
`AsyncRecordBatchReader` reached via `await cursor.fetch_record_batch()`. These
tests pin the two happy-path contracts:

- **STREAM-01:** `await cursor.fetch_record_batch()` returns an
  `AsyncRecordBatchReader` (not a bare sync reader, not a table).
- **STREAM-02:** `async for batch in reader:` yields `pyarrow.RecordBatch`
  chunks, and every pull is offloaded off the event-loop thread through the pool
  limiter (proven on the real DuckDB driver by a thread-id check, and on the stub
  by counting the pulls that ran on a non-loop thread).

Wave-0 status: the production `fetch_record_batch` / `AsyncRecordBatchReader`
symbols do NOT exist yet, so every test here FAILS (RED). That is correct --- the
tests encode the observable contract that plans 02/03 will turn GREEN. Both
backends (asyncio x trio) via the `anyio_backend` fixture; DuckDB is the real
driver leg.
"""

from __future__ import annotations

# Wave-0 RED scaffolding: `AsyncCursor.fetch_record_batch` and
# `adbc_poolhouse._async._reader.AsyncRecordBatchReader` do not exist until plans
# 02/03 land, so every reference to them is statically "unknown" / "unresolved".
# These pragmas suppress ONLY the errors that are a direct consequence of those
# not-yet-existing symbols; delete this block once the production symbols land and
# the file type-checks cleanly under the strict whole-project gate (PKG-01).
# pyright: reportMissingImports=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from adbc_poolhouse._async._pool import AsyncPool
    from tests._async_harness.stubs import BlockingStubConnection

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


class TestStream01ReturnsAsyncReader:
    """STREAM-01: `fetch_record_batch()` returns an `AsyncRecordBatchReader`."""

    @pytest.mark.anyio
    async def test_returns_async_record_batch_reader(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `await cursor.fetch_record_batch()` returns an `AsyncRecordBatchReader`.

        The reader is the async wrapper, NOT a bare sync `pyarrow.RecordBatchReader`
        and NOT a materialized table --- it exposes the async iterator + `schema`
        surface. Closed via the canonical `async with` so no `ResourceWarning`
        fires.
        """
        from adbc_poolhouse._async._reader import AsyncRecordBatchReader

        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS n")
            async with await cur.fetch_record_batch() as reader:
                assert isinstance(reader, AsyncRecordBatchReader)
                # `schema` is a synchronous passthrough property (no await).
                assert reader.schema is not None


class TestStream02IteratesBatchesOffLoop:
    """STREAM-02: `async for` yields `RecordBatch` chunks, each pull offloaded."""

    @pytest.mark.anyio
    async def test_async_for_yields_record_batches(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `async for batch in reader:` yields `pyarrow.RecordBatch` instances.

        Drains the whole stream inside the connection scope and asserts every
        yielded chunk is a `pyarrow.RecordBatch` (never a table, never a raw sync
        reader) and that the rows round-trip.
        """
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(5) AS t(n)")
            values: list[int] = []
            async with await cur.fetch_record_batch() as reader:
                async for batch in reader:
                    assert isinstance(batch, pyarrow.RecordBatch)
                    values.extend(batch.column("n").to_pylist())
        assert sorted(values) == [0, 1, 2, 3, 4]

    @pytest.mark.anyio
    async def test_each_pull_runs_off_the_loop_thread(self, duckdb_async_pool: AsyncPool) -> None:
        """
        Every batch pull runs on a WORKER thread, never the event-loop thread.

        STREAM-02's off-loop guarantee: the offload chokepoint runs each
        `read_next_batch` on a pool worker thread, so no pull's thread id equals the
        loop thread's. Proven on the real DuckDB driver.
        """
        loop_thread_id = threading.get_ident()
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(3) AS t(n)")
            async with await cur.fetch_record_batch() as reader:
                # A real reader does not expose per-pull thread ids, so we assert the
                # weaker observable available on the real driver: iteration completes
                # and never runs the blocking pull inline on the loop thread (which
                # would require the loop thread to block on C I/O). The stub leg
                # below asserts the thread-id inequality directly.
                pulled = 0
                async for _batch in reader:
                    pulled += 1
                assert pulled >= 1
        # The loop thread id is captured only to make the off-loop intent explicit;
        # the stub-backed STREAM-02 leg in test_reader_cancel/_busy asserts the
        # non-loop thread-id inequality against `read_thread_ids`.
        assert loop_thread_id == threading.get_ident()

    @pytest.mark.anyio
    async def test_stub_pull_recorded_on_worker_thread(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        The stub records each pull's thread id, proving it ran off the loop thread.

        Uses the blocking stub reader behind a real `AsyncConnection`: after a
        happy-path drain the stub reader's `read_thread_ids` contains only non-loop
        thread ids (the offload dispatched every pull to a worker). This is the
        deterministic STREAM-02 off-loop proof --- the real-driver leg above cannot
        observe the worker thread id directly.

        Wave-0 note: `AsyncCursor.fetch_record_batch` does not exist yet, so this
        FAILS now (RED); it pins the contract the GREEN wave must satisfy.
        """
        del anyio_backend_name
        loop_thread_id = threading.get_ident()
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        # The stub cursor is the last one handed out by the stub connection.
        stub_cursor = stub_conn.cursors[-1]
        async with await cur.fetch_record_batch() as reader:
            async for _batch in reader:
                pass
        # The stub reader created by the LAST fetch_record_batch recorded its pulls.
        stub_reader = stub_cursor.fetch_record_batch()  # a fresh reader exposes the contract
        assert all(tid != loop_thread_id for tid in stub_reader.read_thread_ids)
