"""Pool fixtures for cloud integration tests (Snowflake, Databricks)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from adbc_poolhouse import DatabricksConfig, SnowflakeConfig, create_pool


@pytest.fixture(scope="session")
def snowflake_pool():
    """
    Session-scoped Snowflake pool.

    Used for recording cassettes locally. Skips if SNOWFLAKE_ACCOUNT is absent.
    Cassette tests do not depend on this fixture during CI replay.
    """
    dotenv_path = Path(__file__).parent.parent.parent / ".env.snowflake"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    if not os.environ.get("SNOWFLAKE_ACCOUNT"):
        pytest.skip("SNOWFLAKE_ACCOUNT not set — skipping live Snowflake; use cassette replay")

    config = SnowflakeConfig()  # type: ignore[call-arg]  # reads SNOWFLAKE_* env vars
    pool = create_pool(config)
    yield pool
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def databricks_pool():
    """
    Session-scoped Databricks pool.

    Used for recording cassettes locally. Skips if Databricks credentials are absent.
    Cassette tests do not depend on this fixture during CI replay.
    """
    dotenv_path = Path(__file__).parent.parent.parent / ".env.databricks"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    has_uri = bool(os.environ.get("DATABRICKS_URI"))
    has_decomposed = all(
        os.environ.get(k) for k in ["DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"]
    )
    if not has_uri and not has_decomposed:
        pytest.skip(
            "Databricks credentials not set — skipping live Databricks; use cassette replay"
        )

    config = DatabricksConfig()  # type: ignore[call-arg]  # reads DATABRICKS_* env vars
    pool = create_pool(config)
    yield pool
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]
