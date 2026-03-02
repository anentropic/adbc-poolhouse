"""Databricks integration tests: cassette-based, CI-safe."""

from __future__ import annotations

from typing import Any

import adbc_driver_manager.dbapi
import pytest


@pytest.mark.databricks
@pytest.mark.adbc_cassette("databricks_health")
def test_connection_health() -> None:
    """
    Pool path works: DatabricksConfig + connect + SELECT 1.

    In CI: replayed from tests/cassettes/databricks_health/ (no credentials required).
    To record: pytest --adbc-record=once -m databricks (requires Databricks credentials set).
    """
    conn: Any = adbc_driver_manager.dbapi.connect(  # type: ignore[union-attr]
        driver="databricks",
        entrypoint="AdbcDriverDatabricksInit",
        db_kwargs={},
    )
    cur: Any = conn.cursor()
    cur.execute("SELECT 1")
    row: Any = cur.fetchone()
    assert row is not None
    assert row[0] == 1
    cur.close()
    conn.close()


@pytest.mark.databricks
@pytest.mark.adbc_cassette("databricks_arrow_round_trip")
def test_arrow_round_trip() -> None:
    """
    Arrow round-trip via Databricks; cassette enforces stable schema.

    In CI: replayed from tests/cassettes/databricks_arrow_round_trip/ (no credentials required).
    To record: pytest --adbc-record=once -m databricks (requires Databricks credentials set).
    """
    conn: Any = adbc_driver_manager.dbapi.connect(  # type: ignore[union-attr]
        driver="databricks",
        entrypoint="AdbcDriverDatabricksInit",
        db_kwargs={},
    )
    cur: Any = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table: Any = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table is not None
    assert table.num_rows == 1
