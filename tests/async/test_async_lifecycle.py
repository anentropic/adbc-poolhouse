"""
Happy-path lifecycle + sync-surface coverage for the async wrapper (real DuckDB).

Every test here runs under BOTH asyncio and trio (via the `anyio_backend`
fixture) and drives the REAL in-process DuckDB driver end to end:
`create_async_pool` -> `connect` -> `cursor` -> `execute` -> `fetch_arrow_table`
-> check-in. Together they prove the must-have "the happy path passes against the
real driver under both backends" and pin the sync surface (ACONN-03 / ACUR-07:
`cursor()` and the cursor properties are read with NO `await`).

A Snowflake `pytest-adbc-replay` cassette leg drives the SAME async layer through
a second backend without live credentials (D-24-04 backend-genericity proof); it
is skipped cleanly when the Snowflake driver or its cassette is unavailable.
"""

from __future__ import annotations

import importlib
import inspect
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow
import pytest

from adbc_poolhouse import (
    DuckDBConfig,
    SnowflakeConfig,
    close_async_pool,
    create_async_pool,
    managed_async_pool,
)

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

_CASSETTE_ROOT = Path(__file__).parent.parent / "cassettes"

# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = importlib.import_module("tests.async._edge_helpers").concurrency_marks


class TestHappyPath:
    """The create -> connect -> cursor -> execute -> fetch -> check-in round trip."""

    @pytest.mark.anyio
    async def test_execute_fetch_arrow_table(self, duckdb_async_pool: AsyncPool) -> None:
        """A full round trip returns a `pyarrow.Table` and checks the connection back in."""
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 42 AS answer")
            tbl = await cur.fetch_arrow_table()
            assert isinstance(tbl, pyarrow.Table)
            assert tbl.num_rows == 1
            assert tbl.column("answer")[0].as_py() == 42
        # __aexit__ checked the connection back in.
        assert duckdb_async_pool._pool.checkedout() == 0

    @pytest.mark.anyio
    async def test_managed_pool_auto_close(self, anyio_backend_name: str) -> None:
        """`managed_async_pool` opens, serves a query, and disposes on block exit (APOOL-02/03)."""
        del anyio_backend_name
        import tempfile

        db = str(Path(tempfile.mkdtemp()) / "managed.db")
        async with managed_async_pool(DuckDBConfig(database=db)) as pool:
            async with await pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT 7 AS n")
                tbl = await cur.fetch_arrow_table()
                assert tbl.column("n")[0].as_py() == 7
            assert pool._pool.checkedout() == 0


class TestSyncSurface:
    """`cursor()` and the cursor properties are read WITHOUT `await` (ACONN-03 / ACUR-07)."""

    @pytest.mark.anyio
    async def test_cursor_is_not_a_coroutine(self, duckdb_async_pool: AsyncPool) -> None:
        """`conn.cursor()` returns a cursor synchronously --- it is not a coroutine."""
        async with await duckdb_async_pool.connect() as conn:
            result = conn.cursor()
            # If cursor() were async, this would be a coroutine object instead.
            assert not inspect.iscoroutine(result)
            assert hasattr(result, "execute")

    @pytest.mark.anyio
    async def test_description_rowcount_arraysize_are_sync(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """`description` / `rowcount` / `arraysize` are plain reads, never awaitable."""
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS one")
            # Read the properties directly --- no await. A coroutine property would
            # surface here as a "coroutine never awaited" object.
            assert not inspect.iscoroutine(cur.description)
            assert not inspect.iscoroutine(cur.rowcount)
            assert not inspect.iscoroutine(cur.arraysize)
            assert cur.description is not None


class TestLifecycleOps:
    """commit / rollback / close on the connection (ACONN-04/05)."""

    @pytest.mark.anyio
    async def test_commit_and_rollback(self, duckdb_async_pool: AsyncPool) -> None:
        """`commit()` and `rollback()` are awaitable no-error round trips (ACONN-04)."""
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("CREATE TABLE t (x INTEGER)")
            await cur.execute("INSERT INTO t VALUES (1)")
            await conn.commit()
            await cur.execute("INSERT INTO t VALUES (2)")
            await conn.rollback()
        assert duckdb_async_pool._pool.checkedout() == 0

    @pytest.mark.anyio
    async def test_explicit_close_checks_in(self, duckdb_async_pool: AsyncPool) -> None:
        """An explicit `await conn.close()` returns the connection to the pool (ACONN-05)."""
        conn = await duckdb_async_pool.connect()
        cur = conn.cursor()
        await cur.execute("SELECT 1")
        await cur.fetch_arrow_table()
        await conn.close()
        assert duckdb_async_pool._pool.checkedout() == 0


class TestSnowflakeCassetteLeg:
    """D-24-04: the async layer driven through a SECOND backend via a replay cassette."""

    @pytest.mark.anyio
    @pytest.mark.snowflake
    @pytest.mark.adbc_cassette("snowflake_arrow_round_trip")
    async def test_async_snowflake_arrow_round_trip(self, anyio_backend_name: str) -> None:
        """
        Drive `create_async_pool(SnowflakeConfig)` through the Snowflake cassette.

        Proves the async wrapper is backend-generic: the SAME offload/limiter
        machinery that serves DuckDB serves a wholly different driver, replayed
        from `tests/cassettes/snowflake_arrow_round_trip/` with no live
        credentials (D-24-04). Skipped cleanly when the Snowflake driver or its
        cassette is absent so the suite stays green in a minimal environment.
        """
        del anyio_backend_name
        pytest.importorskip(
            "adbc_driver_snowflake.dbapi",
            reason="Snowflake driver not installed; cassette leg skipped",
        )
        if not (_CASSETTE_ROOT / "snowflake_arrow_round_trip").exists():
            pytest.skip("snowflake_arrow_round_trip cassette absent")
        # In replay mode real creds are absent; a dummy account satisfies the
        # validator and the cassette intercepts before any real connection.
        os.environ.setdefault("SNOWFLAKE_ACCOUNT", "replay-account")
        pool = create_async_pool(SnowflakeConfig())  # type: ignore[call-arg]
        try:
            async with await pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT 1 AS n, 'hello' AS s")
                table: Any = await cur.fetch_arrow_table()
            assert table is not None
            assert table.num_rows == 1
        finally:
            await close_async_pool(pool)
