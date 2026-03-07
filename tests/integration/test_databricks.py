"""Databricks integration tests: cassette-based, CI-safe."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.databricks
@pytest.mark.adbc_cassette("databricks_health")
def test_connection_health(databricks_pool: Any) -> None:
    """
    Connect + SELECT 1 round-trip via pool API (Databricks driver).

    In CI: replayed from tests/cassettes/databricks_health/ (no credentials required).
    To record: set credentials in .env, then run:
        pytest --adbc-record=once -m databricks
    """
    conn: Any = databricks_pool.connect()
    cur: Any = conn.cursor()
    cur.execute("SELECT 1")
    row: Any = cur.fetchone()
    assert row is not None
    assert row[0] == 1
    cur.close()
    conn.close()


@pytest.mark.databricks
@pytest.mark.adbc_cassette("databricks_arrow_round_trip")
def test_arrow_round_trip(databricks_pool: Any) -> None:
    """
    Arrow round-trip via Databricks pool; cassette enforces stable schema.

    In CI: replayed from tests/cassettes/databricks_arrow_round_trip/ (no credentials required).
    To record: set credentials in .env, then run:
        pytest --adbc-record=once -m databricks
    """
    conn: Any = databricks_pool.connect()
    cur: Any = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table: Any = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table is not None
    assert table.num_rows == 1
