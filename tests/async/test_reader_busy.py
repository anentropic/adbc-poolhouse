"""
Reader two-tier connection guard (STREAM-06) --- Wave-0 RED scaffolding.

A live reader locks its parent connection for the reader's WHOLE lifetime
(`_reader_open == True`, D-29-08/09). While the reader is live:

- **Foreign ops are rejected:** a second `execute`, a second `fetch_record_batch`,
  a `fetch_arrow_table`, or a `commit` on the same connection raises
  `ConnectionBusyError` (the foreign tier of the two-tier guard, D-29-10).
- **The reader's OWN pulls are exempt:** `async for batch in reader:` passes
  `from_reader=True` through the guard, so its pulls do NOT raise
  `ConnectionBusyError` on themselves (the reentrancy exemption).

`_reader_open` is cleared ONLY by `reader.close()` / checkin --- never at drain
(D-29-11): a drained-but-unclosed reader keeps the connection locked, which is why
`async with reader:` is the canonical usage.

Dual-backend via `anyio_backend`; `concurrency_marks` (loop + timeout) guard the
hang-prone gating. Wave-0 status: production `fetch_record_batch` /
`AsyncRecordBatchReader` / the `_reader_open` guard do not exist yet, so these FAIL
(RED).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from adbc_poolhouse import ConnectionBusyError

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from adbc_poolhouse._async._pool import AsyncPool
    from tests._async_harness.stubs import BlockingStubConnection

# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = importlib.import_module("tests.async._edge_helpers").concurrency_marks

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


class TestStream06ForeignOpRejected:
    """STREAM-06: a foreign op while the reader is live raises `ConnectionBusyError`."""

    @pytest.mark.anyio
    async def test_execute_while_reader_live_raises_busy(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        A second `execute` on the connection while the reader is live raises busy.

        The reader holds `_reader_open`; a foreign `execute` hits the foreign tier of
        the guard and raises `ConnectionBusyError`. Inside the `async with reader:`
        the connection is locked to the reader.
        """
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(4) AS t(n)")
            async with await cur.fetch_record_batch():
                with pytest.raises(ConnectionBusyError):
                    await cur.execute("SELECT 99 AS other")

    @pytest.mark.anyio
    async def test_second_fetch_record_batch_while_reader_live_raises_busy(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        A second `fetch_record_batch` while one reader is live raises busy.

        Opening a second reader is itself a foreign op (only one reader may hold the
        connection at a time), so it is rejected with `ConnectionBusyError`.
        """
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(4) AS t(n)")
            async with await cur.fetch_record_batch():
                with pytest.raises(ConnectionBusyError):
                    await cur.fetch_record_batch()

    @pytest.mark.anyio
    async def test_commit_while_reader_live_raises_busy(self, duckdb_async_pool: AsyncPool) -> None:
        """
        A `commit` on the connection while the reader is live raises busy.

        Connection-level foreign ops are rejected the same way cursor-level ones
        are: the reader lock spans the whole connection.
        """
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(4) AS t(n)")
            async with await cur.fetch_record_batch():
                with pytest.raises(ConnectionBusyError):
                    await conn.commit()


class TestStream06OwnPullsExempt:
    """STREAM-06: the reader's own pulls pass `from_reader=True` and are exempt."""

    @pytest.mark.anyio
    async def test_own_pulls_do_not_raise_busy(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `async for batch in reader:` does NOT raise `ConnectionBusyError` on itself.

        Each pull passes `from_reader=True` through the guard (the reentrancy
        exemption, D-29-10), so draining the reader --- multiple pulls back to back
        --- never rejects its own iteration. The full stream drains cleanly.
        """
        rows = 0
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(6) AS t(n)")
            async with await cur.fetch_record_batch() as reader:
                async for batch in reader:
                    rows += batch.num_rows
        assert rows == 6

    @pytest.mark.anyio
    async def test_reader_lock_persists_until_close_not_drain(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        A drained-but-unclosed reader keeps the connection locked (cleared on close).

        `_reader_open` is cleared by `close()`, NOT at drain (D-29-11): after the
        `async for` exhausts, a foreign op still raises `ConnectionBusyError` while
        the reader remains open. Only after `close()` (via `async with` exit) is a
        foreign op accepted.
        """
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(3) AS t(n)")
            reader = await cur.fetch_record_batch()
            async for _batch in reader:  # drain fully (but do NOT close)
                pass
            with pytest.raises(ConnectionBusyError):
                await cur.execute("SELECT 1 AS n")  # still locked: drain != close
            await reader.close()  # NOW the lock clears
            await cur.execute("SELECT 7 AS n")  # accepted
            tbl = await cur.fetch_arrow_table()
            assert tbl.column("n")[0].as_py() == 7
