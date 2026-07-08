"""
Databricks Python-connector integration tests: cassette-based, CI-safe.

These exercise the non-ADBC ``DatabricksPythonConfig`` backend. Cassettes are
recorded below the ADBC cursor adapter (via the ``adbc_poolhouse._adapters._databricks_python``
module in ``adbc_auto_patch``), so the same replay methodology as the ADBC
backends applies with no bespoke mocking.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.databricks_python
@pytest.mark.adbc_cassette("databricks_python_health")
def test_connection_health(databricks_python_pool: Any) -> None:
    """
    Connect + SELECT 1 round-trip via pool API (Databricks Python connector).

    In CI: replayed from tests/cassettes/databricks_python_health/ (no credentials).
    To record against a live warehouse (e.g. Lakehouse//RT): set DATABRICKS_PYTHON_*
    in .env, then run:
        pytest --adbc-record=once -m databricks_python
    """
    conn: Any = databricks_python_pool.connect()
    cur: Any = conn.cursor()
    cur.execute("SELECT 1")
    row: Any = cur.fetchone()
    assert row is not None
    assert row[0] == 1
    cur.close()
    conn.close()


@pytest.mark.databricks_python
@pytest.mark.adbc_cassette("databricks_python_arrow_round_trip")
def test_arrow_round_trip(databricks_python_pool: Any) -> None:
    """
    Arrow round-trip via the Python-connector pool; cassette enforces stable schema.

    In CI: replayed from tests/cassettes/databricks_python_arrow_round_trip/.
    To record: set DATABRICKS_PYTHON_* in .env, then run:
        pytest --adbc-record=once -m databricks_python
    """
    conn: Any = databricks_python_pool.connect()
    cur: Any = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table: Any = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table is not None
    assert table.num_rows == 1
