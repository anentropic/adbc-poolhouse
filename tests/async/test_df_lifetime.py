"""
Async DataFrame self-owning-frame lifetime (DF-04) --- Wave-0 RED scaffolding.

`fetch_df` / `fetch_polars` are whole-operation offloads: the connection checks
back in the instant the offload returns (no `_reader_open` lifetime lock, D-31-03).
The returned frame must therefore be self-owning --- its buffers are materialized
by `reader.read_pandas()` / `polars.from_arrow(read_all())` into frame-owned /
refcounted heap, NOT bound to the connection's C stream (DF-04, EDGE-21, D-31-04).
These tests prove it by reading the frame AFTER the `async with ... as conn:` block
exits (the connection is checked in): a valid read means no dangling C stream and
no use-after-free / segfault.

Each flavour is `pytest.importorskip`-guarded (PKG-02). Both backends via
`anyio_backend`; DuckDB is the real driver leg.

Wave-0 status: `AsyncCursor.fetch_df` / `fetch_polars` do NOT exist yet, so these
FAIL (RED) --- the acceptance signal. Closes threat T-31-02 (use-after-free reading
a frame after checkin) once GREEN.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestDf04FetchDfValidAfterCheckin:
    """DF-04: a `fetch_df` frame stays readable after the connection checks in."""

    @pytest.mark.anyio
    async def test_fetch_df_valid_after_checkin(self, duckdb_async_pool: AsyncPool) -> None:
        """
        A pandas frame read AFTER connection checkin is still valid (self-owning).

        The frame is materialized inside the `async with`, but read only AFTER the
        block exits and the connection has checked back in. A valid `.tolist()` proves
        the frame owns its buffers (no dangling C stream, no segfault) --- the EDGE-21
        guarantee inherited from `fetch_arrow_table` (D-31-04).
        """
        pandas = pytest.importorskip("pandas")
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS a")
            df = await cur.fetch_df()
        # Connection is now checked in; the frame must still be readable.
        assert isinstance(df, pandas.DataFrame)
        assert df["a"].tolist() == [1]


class TestDf04FetchPolarsValidAfterCheckin:
    """DF-04: a `fetch_polars` frame stays readable after the connection checks in."""

    @pytest.mark.anyio
    async def test_fetch_polars_valid_after_checkin(self, duckdb_async_pool: AsyncPool) -> None:
        """
        A polars frame read AFTER connection checkin is still valid (self-owning).

        The `fetch_polars` twin of the pandas lifetime proof: read the frame only
        AFTER the `async with` exits (connection checked in) and assert a valid
        `.to_list()`, proving the polars frame owns its buffers (DF-04).
        """
        polars = pytest.importorskip("polars")
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS a")
            df = await cur.fetch_polars()
        # Connection is now checked in; the frame must still be readable.
        assert isinstance(df, polars.DataFrame)
        assert df["a"].to_list() == [1]
