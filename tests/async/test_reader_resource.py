"""
Reader finalizer discipline (EDGE-22 / EDGE-23) --- Wave-0 RED scaffolding.

An `AsyncRecordBatchReader` cannot `await` inside `__del__`, so its finalizer is
warn-only (D-29-15):

- **EDGE-22:** an unclosed reader's `__del__` emits a `ResourceWarning` (nudging
  the user toward `async with await cursor.fetch_record_batch() as reader:`), and
  it NEVER calls `self.close()` --- doing so would create an un-awaited coroutine
  and emit a "coroutine was never awaited" `RuntimeWarning`, which EDGE-22 forbids.
- **EDGE-23:** the happy path (closed via `async with`) emits NEITHER a
  `ResourceWarning` NOR a "coroutine was never awaited" `RuntimeWarning`.

Actual buffer release rides the pool reset event on checkin (D-29-12); `__del__`
only warns. EDGE-22 is asserted on asyncio (finalizer timing is loop-agnostic);
EDGE-23 runs both backends. Wave-0 status: `AsyncRecordBatchReader` /
`fetch_record_batch` do not exist yet, so these FAIL (RED).
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
import gc
import warnings
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestEdge22UnclosedWarns:
    """EDGE-22: an unclosed reader's `__del__` emits `ResourceWarning` (only)."""

    @pytest.mark.anyio
    async def test_unclosed_reader_del_emits_resource_warning(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        Dropping a reader without closing it emits a `ResourceWarning` on `__del__`.

        The reader is created and then dropped WITHOUT `close()` / `async with`.
        Forcing finalization (`del` + `gc.collect()`) triggers `__del__`, which warns
        `ResourceWarning`. The warning nudges toward the canonical `async with` usage.
        """
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(4) AS t(n)")
            reader = await cur.fetch_record_batch()
            await reader.__anext__()  # open the stream, then abandon it
            with pytest.warns(ResourceWarning):
                del reader
                gc.collect()

    @pytest.mark.anyio
    async def test_unclosed_reader_del_emits_no_coroutine_warning(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        `__del__` NEVER emits a "coroutine was never awaited" `RuntimeWarning`.

        The finalizer is warn-only --- it must NOT call `self.close()` (an
        un-awaited coroutine). Capturing all warnings, the only `RuntimeWarning`
        forbidden is the "coroutine ... was never awaited" one; a `ResourceWarning`
        is expected and allowed.
        """
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(4) AS t(n)")
            reader = await cur.fetch_record_batch()
            await reader.__anext__()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                del reader
                gc.collect()
            coroutine_warnings = [
                w
                for w in caught
                if issubclass(w.category, RuntimeWarning) and "never awaited" in str(w.message)
            ]
            assert coroutine_warnings == []


class TestEdge23HappyPathClean:
    """EDGE-23: closing via `async with` emits neither warning."""

    @pytest.mark.anyio
    async def test_closed_reader_emits_no_warnings(self, duckdb_async_pool: AsyncPool) -> None:
        """
        A reader closed via `async with` emits NO `ResourceWarning` and NO coroutine warning.

        The canonical path: `async with await cursor.fetch_record_batch() as reader:`
        drains and closes cleanly. After the block exits and the object is finalized,
        neither a `ResourceWarning` (it was closed) nor a "coroutine never awaited"
        `RuntimeWarning` is recorded.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT * FROM range(4) AS t(n)")
                async with await cur.fetch_record_batch() as reader:
                    async for _batch in reader:
                        pass
                del reader
                gc.collect()
        offending = [
            w
            for w in caught
            if issubclass(w.category, ResourceWarning)
            or (issubclass(w.category, RuntimeWarning) and "never awaited" in str(w.message))
        ]
        assert offending == []
