"""Snowflake integration tests: cassette-based, CI-safe (TEST-03 successor)."""

from __future__ import annotations

from typing import Any

import adbc_driver_snowflake.dbapi  # intercepted by adbc_auto_patch in replay mode
import pytest


@pytest.mark.snowflake
@pytest.mark.adbc_cassette("snowflake_health")
def test_connection_health() -> None:
    """
    Pool path works: connect + SELECT 1 + checkin.

    In CI: replayed from tests/cassettes/snowflake_health/ (no credentials required).
    To record: pytest --adbc-record=once -m snowflake (requires SNOWFLAKE_ACCOUNT set).
    """
    conn: Any = adbc_driver_snowflake.dbapi.connect()  # type: ignore[union-attr]
    cur: Any = conn.cursor()
    cur.execute("SELECT 1")
    row: Any = cur.fetchone()
    assert row is not None
    assert row[0] == 1
    cur.close()
    conn.close()


@pytest.mark.snowflake
@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")
def test_arrow_round_trip() -> None:
    """
    Arrow schema + rows round-trip correctly; cassette enforces stable output.

    In CI: replayed from tests/cassettes/snowflake_arrow_round_trip/ (no credentials required).
    To record: pytest --adbc-record=once -m snowflake (requires SNOWFLAKE_ACCOUNT set).
    """
    conn: Any = adbc_driver_snowflake.dbapi.connect()  # type: ignore[union-attr]
    cur: Any = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table: Any = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table is not None
    assert table.num_rows == 1
