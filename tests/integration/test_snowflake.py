"""Snowflake integration tests: cassette-based, CI-safe (TEST-03 successor)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import adbc_driver_snowflake.dbapi  # intercepted by adbc_auto_patch in replay mode
import pytest
from dotenv import load_dotenv

from adbc_poolhouse import SnowflakeConfig
from adbc_poolhouse._translators import translate_config


def _snowflake_kwargs() -> dict[str, str]:
    """
    Build connect kwargs from .env.snowflake / environment.

    Returns an empty dict when credentials are absent — replay mode ignores
    kwargs entirely, so the tests still pass in CI without any env vars set.
    """
    load_dotenv(Path(__file__).parent.parent.parent / ".env.snowflake", override=False)
    try:
        return translate_config(SnowflakeConfig())  # type: ignore[call-arg]
    except Exception:
        return {}


@pytest.mark.snowflake
@pytest.mark.adbc_cassette("snowflake_health")
def test_connection_health() -> None:
    """
    Connect + SELECT 1 round-trip via adbc_driver_snowflake.

    In CI: replayed from tests/cassettes/snowflake_health/ (no credentials required).
    To record: set SNOWFLAKE_ACCOUNT (+ auth) in .env.snowflake, then run
        pytest --adbc-record=once -m snowflake
    """
    conn: Any = adbc_driver_snowflake.dbapi.connect(**_snowflake_kwargs())  # type: ignore[union-attr]
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
    To record: set SNOWFLAKE_ACCOUNT (+ auth) in .env.snowflake, then run
        pytest --adbc-record=once -m snowflake
    """
    conn: Any = adbc_driver_snowflake.dbapi.connect(**_snowflake_kwargs())  # type: ignore[union-attr]
    cur: Any = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table: Any = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table is not None
    assert table.num_rows == 1
