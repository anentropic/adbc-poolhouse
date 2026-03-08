"""
Pool fixtures for cloud integration tests (Snowflake, Databricks).

In replay mode (CI), real credentials are absent. The fixtures fall back to
dummy config values so the config validators pass; the cassette intercepts
before any real connection is attempted.
"""

from __future__ import annotations

import os
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


def _ensure_snowflake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy Snowflake env vars if real credentials are absent (replay mode)."""
    if not os.environ.get("SNOWFLAKE_ACCOUNT") and "SNOWFLAKE_ACCOUNT" not in _dotenv_values:
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "replay-account")


def _ensure_databricks_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy Databricks env vars if real credentials are absent (replay mode)."""
    has_uri = os.environ.get("DATABRICKS_URI") or "DATABRICKS_URI" in _dotenv_values
    has_decomposed = all(
        os.environ.get(k) or k in _dotenv_values
        for k in ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")
    )
    if not has_uri and not has_decomposed:
        monkeypatch.setenv("DATABRICKS_HOST", "replay-host")
        monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/replay")
        monkeypatch.setenv("DATABRICKS_TOKEN", "replay-token")


@pytest.fixture
def snowflake_pool(monkeypatch: pytest.MonkeyPatch):
    """Snowflake pool — function-scoped so each test gets its own cassette path."""
    _restore_dotenv(monkeypatch)
    _ensure_snowflake_env(monkeypatch)
    config = SnowflakeConfig()  # type: ignore[call-arg]  # reads SNOWFLAKE_* env vars
    pool = create_pool(config)
    yield pool
    close_pool(pool)


@pytest.fixture
def databricks_pool(monkeypatch: pytest.MonkeyPatch):
    """Databricks pool — function-scoped so each test gets its own cassette path."""
    _restore_dotenv(monkeypatch)
    _ensure_databricks_env(monkeypatch)
    config = DatabricksConfig()  # type: ignore[call-arg]  # reads DATABRICKS_* env vars
    pool = create_pool(config)
    yield pool
    close_pool(pool)
