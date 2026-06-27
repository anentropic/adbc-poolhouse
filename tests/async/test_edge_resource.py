"""
Arrow-lifetime EDGE coverage (EDGE-21): the table outlives the connection check-in.

`fetch_arrow_table` returns a fully-materialized `pyarrow.Table` that owns its own
buffers, NOT a streaming `RecordBatchReader` bound to the soon-closed cursor
(Pitfall 7). This proves it: fetch the table, exit the connection scope so the
connection is checked back in (and its Arrow allocators released via the pool
reset event), and only THEN read the table's values --- they must be intact, with
no use-after-checkin segfault. Looped a few times to surface any allocator reuse
issue. Real DuckDB, both backends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

# A few repeats so an allocator-reuse / use-after-free bug has a chance to surface.
_LIFETIME_LOOPS = 5


class TestEdge21ArrowLifetime:
    """A `pyarrow.Table` is readable AFTER its connection is checked back in."""

    @pytest.mark.anyio
    async def test_table_readable_after_checkin(self, duckdb_async_pool: AsyncPool) -> None:
        """
        Read the table's values after the connection scope has exited (checkin).

        The table is fetched inside the scope but READ outside it --- after
        `__aexit__` has returned the connection to the pool and fired the Arrow
        allocator reset. A materialized table survives this; a reader bound to the
        cursor would dangle. The values must round-trip intact, looped a few times
        to catch allocator reuse.
        """
        for i in range(_LIFETIME_LOOPS):
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute(f"SELECT {i} AS i, 'row-{i}' AS label")
                tbl = await cur.fetch_arrow_table()
            # The connection is now checked back in. Reading the table here proves
            # it owns its own buffers (EDGE-21 / Pitfall 7).
            assert duckdb_async_pool._pool.checkedout() == 0
            assert isinstance(tbl, pyarrow.Table)
            assert tbl.num_rows == 1
            assert tbl.column("i")[0].as_py() == i
            assert tbl.column("label")[0].as_py() == f"row-{i}"

    @pytest.mark.anyio
    async def test_table_survives_pool_close(self, anyio_backend_name: str) -> None:
        """A table read after the WHOLE pool is closed still has intact values."""
        del anyio_backend_name
        import tempfile
        from pathlib import Path

        from adbc_poolhouse import DuckDBConfig, close_async_pool, create_async_pool

        db = str(Path(tempfile.mkdtemp()) / "lifetime.db")
        pool = create_async_pool(DuckDBConfig(database=db))
        async with await pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 99 AS v")
            tbl = await cur.fetch_arrow_table()
        await close_async_pool(pool)
        # Pool gone, connection gone --- the materialized table still reads.
        assert isinstance(tbl, pyarrow.Table)
        assert tbl.column("v")[0].as_py() == 99
