"""
Async DataFrame convenience round-trip (DF-01/DF-02) --- Wave-0 RED scaffolding.

Phase 31 adds `await cursor.fetch_df()` returning a `pandas.DataFrame` and
`await cursor.fetch_polars()` returning a `polars.DataFrame`, each a single
whole-operation offload that hands the driver's NATIVE method through the same
cancellable offload bracket as `fetch_arrow_table` (D-31-01/D-31-03). These tests
pin the two happy-path return-type contracts against the real DuckDB driver:

- **DF-01:** `await cur.fetch_df()` returns a real `pandas.DataFrame` whose values
  round-trip the executed query.
- **DF-02:** `await cur.fetch_polars()` returns a real `polars.DataFrame` whose
  values round-trip.

Each flavour is guarded by `pytest.importorskip`, so the file collects and runs
cleanly where pandas/polars are absent (PKG-02, D-31-08). The two cases carry
`fetch_df` / `fetch_polars` in their names so the VALIDATION test map can select
them with `-k`.

Wave-0 status: `AsyncCursor.fetch_df` / `fetch_polars` do NOT exist yet, so every
test here FAILS (RED). That is the acceptance signal --- Plan 31-02 turns them
GREEN by cloning the `fetch_arrow_table` shape. Both backends (asyncio x trio) via
the `anyio_backend` fixture; DuckDB is the real driver leg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestDf01FetchDfRoundTrip:
    """DF-01: `fetch_df` returns a `pandas.DataFrame` whose values round-trip."""

    @pytest.mark.anyio
    async def test_fetch_df_returns_pandas_dataframe(self, duckdb_async_pool: AsyncPool) -> None:
        """
        `await cur.fetch_df()` returns a real `pandas.DataFrame` with the queried values.

        Executes `SELECT 1 AS a, 2 AS b`, materializes the result as a pandas frame,
        and asserts both the type and the round-tripped values. `importorskip` skips
        cleanly where pandas is absent (PKG-02).
        """
        pandas = pytest.importorskip("pandas")
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS a, 2 AS b")
            df = await cur.fetch_df()
        assert isinstance(df, pandas.DataFrame)
        assert df.to_dict("list") == {"a": [1], "b": [2]}


class TestDf02FetchPolarsRoundTrip:
    """DF-02: `fetch_polars` returns a `polars.DataFrame` whose values round-trip."""

    @pytest.mark.anyio
    async def test_fetch_polars_returns_polars_dataframe(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        `await cur.fetch_polars()` returns a real `polars.DataFrame` with the queried values.

        Executes the same `SELECT 1 AS a, 2 AS b`, materializes the result as a
        polars frame, and asserts both the type and the round-tripped values.
        `importorskip` skips cleanly where polars is absent (PKG-02).
        """
        polars = pytest.importorskip("polars")
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS a, 2 AS b")
            df = await cur.fetch_polars()
        assert isinstance(df, polars.DataFrame)
        assert df.to_dict(as_series=False) == {"a": [1], "b": [2]}
