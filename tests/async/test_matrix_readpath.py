"""
Backend-generic read-path matrix for the async wrapper (TEST-01/02).

One async layer, two real backends, two event loops. Each test takes an indirect
`pool` fixture parametrized over the POOL FIXTURE NAME — `duckdb_async_pool` (real
in-process DuckDB) and `snowflake_async_pool` (the Phase 25
`snowflake_arrow_round_trip` cassette, replayed offline). The `pool` fixture
resolves the underlying async fixture lazily via `request.getfixturevalue(...)`
DURING SETUP (a sync fixture, not the running test coroutine), so the Snowflake
leg skips on its own when the driver or cassette is absent without taking the
DuckDB leg down with it. Resolving inside the test body instead would re-enter the
anyio runner (`RuntimeError: ... another is already running`), so the indirection
lives in a setup-phase fixture. The `{asyncio, trio}` axis (TEST-01) comes for
free from `@pytest.mark.anyio` plus the `anyio_backend` fixture in `conftest.py`;
there is no hand-rolled backend loop.

The surface under test is strictly read-path (D-27-05/06): the happy-path
lifecycle (connect -> execute -> `fetch_arrow_table` -> check-in) and the
`AsyncCursor` row-fetch surface (`fetchall`). The cassette `ReplayCursor` is
read-only — it has no `adbc_cancel` and cannot block-gate a worker — so nothing
here gates, cancels, or mutates. The Snowflake leg uses the SELECT shape
(`SELECT 1 AS n, 'hello' AS s`) the existing cassette already records, and the
cassette holds a SINGLE interaction, so each test issues `execute` exactly once;
no live warehouse is touched. Value assertions are backend-neutral: Snowflake
folds the column aliases to `N`/`S` and returns `N` as a `Decimal`, so columns are
looked up case-insensitively and compared by value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pyarrow
import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence

    from adbc_poolhouse._async._pool import AsyncPool

# The backend axis: each entry is a POOL FIXTURE NAME resolved lazily by the
# `pool` fixture below via `request.getfixturevalue(...)`. The Snowflake param
# carries BOTH the `snowflake` marker and the `adbc_cassette` marker — the
# cassette is mounted by the marker, NOT by the fixture (RESEARCH Pitfall 3);
# without it the leg would attempt a real connection instead of replaying offline.
_BACKENDS = [
    "duckdb_async_pool",
    pytest.param(
        "snowflake_async_pool",
        marks=[
            pytest.mark.snowflake,
            pytest.mark.adbc_cassette("snowflake_arrow_round_trip"),
        ],
    ),
]

# The single read-path SELECT both backends share. The Snowflake cassette records
# exactly this shape; reusing it keeps the cassette leg offline. The cassette
# records ONE interaction, so each test issues `execute` exactly once.
_READ_QUERY = "SELECT 1 AS n, 'hello' AS s"


def _col(table: pyarrow.Table, name: str) -> pyarrow.ChunkedArray:
    """
    Look a column up case-insensitively, backend-neutrally.

    DuckDB preserves the lowercase alias (`n` / `s`); Snowflake folds unquoted
    identifiers to uppercase (`N` / `S`). The matrix asserts on values, not on a
    backend's casing convention, so column access normalises the name.

    Args:
        table: The fetched result table.
        name: The column alias from the SELECT, in any case.

    Returns:
        The matching column.
    """
    by_lower = {n.lower(): n for n in table.column_names}
    return table.column(by_lower[name.lower()])


@pytest.fixture(params=_BACKENDS)
def pool(request: pytest.FixtureRequest) -> AsyncPool:
    """
    Resolve the parametrized backend pool during SETUP, one param per backend.

    `request.param` is a pool fixture name (`duckdb_async_pool` or
    `snowflake_async_pool`); `request.getfixturevalue(...)` materialises the
    matching async-generator fixture here, in the setup phase, NOT inside the
    running test coroutine. Resolving an async fixture from within a
    `@pytest.mark.anyio` test body re-enters the anyio runner and raises (or, on
    trio, deadlocks); doing it in this sync fixture lets the plugin set the async
    fixture up normally. The Snowflake leg's `importorskip` / `skip` fires here,
    so an absent driver or cassette skips just that param.

    Args:
        request: The pytest fixture request; `request.param` is the backend pool
            fixture name supplied by `parametrize`.

    Returns:
        The resolved [`AsyncPool`][adbc_poolhouse._async._pool.AsyncPool] for the
        current backend, already set up and torn down by its own fixture.
    """
    return request.getfixturevalue(request.param)


class TestReadPathMatrix:
    """connect -> execute -> fetch -> check-in, over both backends and both loops."""

    @pytest.mark.anyio
    async def test_fetch_arrow_table_round_trip(self, pool: AsyncPool) -> None:
        """
        A full round trip returns a `pyarrow.Table` and checks the connection back in.

        The same async lifecycle drives DuckDB and the Snowflake cassette (the
        `pool` fixture's two params), parametrized over `{asyncio, trio}` via
        `@pytest.mark.anyio`. After the connection context exits, the pool must
        show zero checked-out connections (TEST-02: backend-neutral check-in on
        the read path).
        """
        async with await pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute(_READ_QUERY)
            table = await cur.fetch_arrow_table()
            assert isinstance(table, pyarrow.Table)
            assert table.num_rows == 1
            # Values, not casing: Snowflake yields N == Decimal("1"), DuckDB int 1,
            # both == 1; column access is case-insensitive (see `_col`).
            assert _col(table, "n")[0].as_py() == 1
            assert _col(table, "s")[0].as_py() == "hello"
        # __aexit__ checked the connection back in on both backends.
        assert pool._pool.checkedout() == 0

    @pytest.mark.anyio
    async def test_cursor_fetchall_surface(self, pool: AsyncPool) -> None:
        """
        The `AsyncCursor` `fetchall` row surface reads on both backends.

        Covers the read-path DBAPI row-fetch surface the cassette supports
        (D-27-05), exercised over both backends and both event loops. A single
        `execute` (the cassette records one interaction), then `fetchall`. Strictly
        read-path: no gating, no cancel, no mutation. Check-in is asserted after
        the round trip.
        """
        async with await pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute(_READ_QUERY)
            # `fetchall()` is typed `object` on the async surface (it forwards the
            # driver's DBAPI rows); cast to a row sequence for the assertions.
            rows = cast("Sequence[Sequence[object]]", await cur.fetchall())
            assert len(rows) == 1
            # Decimal("1") == 1, so the tuple compares equal on both backends.
            assert tuple(rows[0]) == (1, "hello")
        assert pool._pool.checkedout() == 0
