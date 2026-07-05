"""
Reader close discipline (STREAM-03 + EDGE-20) --- regression coverage.

- **STREAM-03:** `schema` is a synchronous passthrough property (no offload, no
  `await`); the blocking members are replaced by async twins; and
  `async with await cursor.fetch_record_batch() as reader:` closes the reader
  offloaded-and-shielded on exit.
- **EDGE-20:** if the shielded `close()` itself raises, the body error still
  chains through `__context__`, and the connection's `_reader_open` lock is
  cleared (released) regardless --- a failed cleanup never strands the connection
  busy.

Status: `AsyncRecordBatchReader` / `fetch_record_batch` are implemented; this file
is passing regression coverage of the contract above. Both backends via
`anyio_backend`; the EDGE-20 raise-on-close leg drives the stub reader so `close`
can be made to raise deterministically.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from adbc_poolhouse._async._pool import AsyncPool
    from tests._async_harness.stubs import BlockingStubConnection

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


class TestStream03CloseOnContextExit:
    """STREAM-03: `async with` closes the reader offloaded-and-shielded."""

    @pytest.mark.anyio
    async def test_context_manager_closes_reader(self, duckdb_async_pool: AsyncPool) -> None:
        """
        Exiting `async with await cursor.fetch_record_batch()` closes the reader.

        After the `async with` block exits, the reader is closed --- its subsequent
        reads would raise (proven in `test_reader_lifetime.py`); here we assert the
        canonical close path completes without error and releases the connection's
        reader lock so the connection is usable again.
        """
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS n")
            async with await cur.fetch_record_batch() as reader:
                assert reader.schema is not None
            # The reader lock is cleared on close, so a fresh execute succeeds.
            await cur.execute("SELECT 2 AS n")
            tbl = await cur.fetch_arrow_table()
            assert tbl.column("n")[0].as_py() == 2

    @pytest.mark.anyio
    async def test_schema_is_synchronous_property(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `reader.schema` is a plain property --- accessing it returns a schema, not a coroutine.

        STREAM-03's "hide nothing safe to expose" rule keeps `schema` synchronous
        (no offload, no `await`), so touching it never produces a "coroutine was
        never awaited" warning. Asserting it is not awaitable pins that contract.
        """
        import inspect

        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS n")
            async with await cur.fetch_record_batch() as reader:
                schema = reader.schema
                assert not inspect.isawaitable(schema)


class TestEdge20ShieldedCleanupChains:
    """EDGE-20: a raising shielded close chains the body error and still releases."""

    @pytest.mark.anyio
    async def test_shielded_cleanup_chains(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A `close` that raises inside the body chains via `__context__` and releases.

        The stub reader's `close` is patched to raise. Inside
        `async with await cursor.fetch_record_batch() as reader:` the body raises
        first; the shielded `__aexit__` close then raises too. The surfaced error's
        `__context__` links back to the body error (Python's implicit chaining), and
        the connection's `_reader_open` lock is cleared regardless (EDGE-20 / D-29-16)
        --- a foreign op afterwards must NOT raise `ConnectionBusyError`.
        """
        del anyio_backend_name
        async_conn, _stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        reader = await cur.fetch_record_batch()

        class _CloseBoom(RuntimeError):
            """Marker raised by the patched reader close."""

        class _BodyBoom(RuntimeError):
            """Marker raised by the async-with body."""

        # Make the reader's shielded close raise.
        def _raising_close() -> None:
            raise _CloseBoom("close failed")

        # Patch the close of the reader WE hold (reader._reader), not a fresh reader,
        # so the shielded-close-raises path is actually exercised (EDGE-20).
        reader._reader.close = _raising_close  # type: ignore[method-assign]

        surfaced: BaseException | None = None
        try:
            async with reader:
                raise _BodyBoom("body failed")
        except BaseException as exc:  # noqa: BLE001 (EDGE-20: capture whichever surfaces)
            surfaced = exc

        assert surfaced is not None
        # Either the close error surfaces with the body error chained via __context__,
        # or the body error surfaces --- either way the body error is reachable in the
        # chain and the connection lock is released.
        chain: list[BaseException] = []
        cursor_exc: BaseException | None = surfaced
        while cursor_exc is not None:
            chain.append(cursor_exc)
            cursor_exc = cursor_exc.__context__
        assert any(isinstance(e, _BodyBoom) for e in chain)
        # The reader lock was cleared even though close raised: no ConnectionBusyError.
        assert async_conn._reader_open is False  # noqa: SLF001
