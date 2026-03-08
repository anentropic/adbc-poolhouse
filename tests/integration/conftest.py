"""Pool fixtures for cloud integration tests (Snowflake, Databricks)."""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import dotenv_values

from adbc_poolhouse import DatabricksConfig, SnowflakeConfig, close_pool, create_pool

_dotenv_path = Path(__file__).parent.parent.parent / ".env"
_dotenv_values: dict[str, str] = (
    {k: v for k, v in dotenv_values(dotenv_path=_dotenv_path).items() if v is not None}
    if _dotenv_path.exists()
    else {}
)


def _restore_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-inject .env values after the root conftest's autouse clear."""
    for key, val in _dotenv_values.items():
        monkeypatch.setenv(key, val)


@pytest.fixture
def snowflake_pool(monkeypatch: pytest.MonkeyPatch):
    """Snowflake pool — function-scoped so each test gets its own cassette path."""
    # Restore warehouse env vars cleared by the autouse _clear_warehouse_env_vars
    # fixture in the root conftest. Integration tests need credentials available
    # when constructing configs.
    _restore_dotenv(monkeypatch)
    config = SnowflakeConfig()  # type: ignore[call-arg]  # reads SNOWFLAKE_* env vars
    pool = create_pool(config)
    yield pool
    close_pool(pool)


@pytest.fixture
def databricks_pool(monkeypatch: pytest.MonkeyPatch):
    """Databricks pool — function-scoped so each test gets its own cassette path."""
    _restore_dotenv(monkeypatch)
    config = DatabricksConfig()  # type: ignore[call-arg]  # reads DATABRICKS_* env vars
    pool = create_pool(config)
    yield pool
    close_pool(pool)
