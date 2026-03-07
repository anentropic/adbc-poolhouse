"""Databricks integration tests: cassette-based, CI-safe."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import adbc_driver_manager.dbapi  # intercepted by adbc_auto_patch in replay mode
import pytest
from dotenv import load_dotenv

from adbc_poolhouse import DatabricksConfig
from adbc_poolhouse._drivers import resolve_driver
from adbc_poolhouse._translators import translate_config


def _databricks_connect_kwargs() -> tuple[str, dict[str, str]]:
    """
    Build (driver_path, kwargs) from .env / environment.

    Returns ("", {}) when credentials are absent — replay mode ignores
    kwargs entirely, so the tests still pass in CI without any env vars set.
    """
    load_dotenv(Path(__file__).parent.parent.parent / ".env", override=False)
    try:
        config = DatabricksConfig()  # type: ignore[call-arg]
        return resolve_driver(config), translate_config(config)
    except Exception:
        return "", {}


@pytest.mark.databricks
@pytest.mark.adbc_cassette("databricks_health")
def test_connection_health() -> None:
    """
    Connect + SELECT 1 round-trip via adbc_driver_manager (Foundry/Databricks driver).

    In CI: replayed from tests/cassettes/databricks_health/ (no credentials required).
    To record: set credentials in .env, then run:
        pytest --adbc-record=once -m databricks
    """
    driver, kwargs = _databricks_connect_kwargs()
    conn: Any = adbc_driver_manager.dbapi.connect(driver=driver, **kwargs)  # type: ignore[union-attr]
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
    To record: set credentials in .env, then run:
        pytest --adbc-record=once -m databricks
    """
    driver, kwargs = _databricks_connect_kwargs()
    conn: Any = adbc_driver_manager.dbapi.connect(driver=driver, **kwargs)  # type: ignore[union-attr]
    cur: Any = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table: Any = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table is not None
    assert table.num_rows == 1
