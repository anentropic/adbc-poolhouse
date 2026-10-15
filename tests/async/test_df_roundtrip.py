"""
Async DataFrame convenience round-trip (DF-01/DF-02) --- regression coverage.

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

Status: `AsyncCursor.fetch_df` / `fetch_polars` are implemented (Plan 31-02 cloned the
`fetch_arrow_table` shape); this file is passing regression coverage of the round-trip
contracts above. Both backends (asyncio x trio) via the `anyio_backend` fixture; DuckDB is
the real driver leg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from adbc_poolhouse._async._cursor import _fetch_polars_frame

if TYPE_CHECKING:
    import polars as pl

    from adbc_poolhouse._async._cursor import _SyncCursor
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

    @pytest.mark.anyio
    async def test_fetch_polars_empty_result_keeps_columns(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        An empty result still comes back as a `polars.DataFrame` with its columns.

        Under polars 2 the driver's `polars.from_arrow` yields a struct `Series`;
        the zero-row case is where an unnest could lose the schema. The frame must
        keep both column names and their dtypes, with no rows.
        """
        polars = pytest.importorskip("polars")
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1::BIGINT AS a, 'x' AS b WHERE false")
            df = await cur.fetch_polars()
        assert isinstance(df, polars.DataFrame)
        assert df.height == 0
        assert df.schema == polars.Schema({"a": polars.Int64, "b": polars.String})


class _FixedPolarsCursor:
    """A sync-cursor fake whose `fetch_polars` returns a preset object."""

    def __init__(self, result: object) -> None:
        self._result = result

    def fetch_polars(self) -> object:
        return self._result


class TestFetchPolarsFrameNormalization:
    """
    Both branches of `_fetch_polars_frame`, whatever polars version is installed.

    The real-driver tests above only reach the branch the locked polars takes
    (the struct-`Series` unnest under polars 2). These drive the helper directly
    so a frame passes through untouched and a struct `Series` is unnested on any
    polars version.
    """

    def test_dataframe_passes_through_unchanged(self) -> None:
        """A driver that already returns a frame (polars 1, Databricks) gets it back as-is."""
        polars = pytest.importorskip("polars")
        frame = polars.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        cursor = cast("_SyncCursor", _FixedPolarsCursor(frame))
        assert _fetch_polars_frame(cursor) is frame

    def test_struct_series_is_unnested_into_frame(self) -> None:
        """A one-column struct `Series` (polars 2 stream result) becomes the frame it wraps."""
        polars = pytest.importorskip("polars")
        frame = polars.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        cursor = cast("_SyncCursor", _FixedPolarsCursor(frame.to_struct("result")))
        result = _fetch_polars_frame(cursor)
        assert isinstance(result, polars.DataFrame)
        assert cast("pl.DataFrame", result).equals(frame)
