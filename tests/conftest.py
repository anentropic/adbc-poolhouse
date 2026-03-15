"""
Shared pytest fixtures for adbc_poolhouse test suite.

The ``_clear_warehouse_env_vars`` autouse fixture below prevents environment
variable contamination across tests.  pydantic-settings ``BaseSettings``
reads matching env vars at ``__init__`` time, so any ``SNOWFLAKE_*`` /
``DATABRICKS_*`` / etc. variables present in ``os.environ`` will override
explicit kwargs passed to a config constructor.  Clearing them before every
test keeps unit tests deterministic regardless of which dotenv files (or
CI secrets) happen to be loaded in the process.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from pydantic_settings import SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import Generator

    from adbc_poolhouse._base_config import WarehouseConfig

from adbc_poolhouse._base_config import BaseWarehouseConfig

_WAREHOUSE_ENV_PREFIXES: tuple[str, ...] = (
    "BIGQUERY_",
    "CLICKHOUSE_",
    "DATABRICKS_",
    "DUCKDB_",
    "FLIGHTSQL_",
    "MSSQL_",
    "MYSQL_",
    "POSTGRESQL_",
    "REDSHIFT_",
    "SNOWFLAKE_",
    "SQLITE_",
    "TERADATA_",
    "TRINO_",
)


class DummyConfig(BaseWarehouseConfig):
    """
    Minimal config class for testing registry without real drivers.

    Inherits from BaseWarehouseConfig to satisfy the WarehouseConfig Protocol.
    Uses SettingsConfigDict(extra="forbid") to catch typos in tests.
    """

    model_config = SettingsConfigDict(extra="forbid")

    def _adbc_entrypoint(self) -> str | None:
        """Return None - no entry point required for dummy backend."""
        return None

    def _driver_path(self) -> str:
        return "dummy"

    def to_adbc_kwargs(self) -> dict[str, str]:
        return {"dummy_key": "dummy_value"}


def dummy_translator(config: WarehouseConfig) -> dict[str, str]:
    """
    Minimal translator function for testing registry.

    Args:
        config: A DummyConfig instance (typed as WarehouseConfig for Protocol).

    Returns:
        A dict with dummy connection kwargs.
    """
    return {"dummy_key": "dummy_value"}


@pytest.fixture
def dummy_backend() -> dict[str, object]:
    """
    Fixture providing a complete dummy backend for registry testing.

    Returns:
        A dict with keys:
        - name: Backend name string
        - config_class: The DummyConfig class
        - translator: The dummy_translator function
        - driver_path: A test driver path string
        - config_instance: A DummyConfig instance
    """
    return {
        "name": "test_dummy_backend",
        "config_class": DummyConfig,
        "translator": dummy_translator,
        "driver_path": "test_driver_path",
        "config_instance": DummyConfig(),
    }


@pytest.fixture(autouse=True)
def _clear_warehouse_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """
    Remove all warehouse-prefixed env vars before each test.

    Uses ``monkeypatch`` so the original environment is automatically restored
    on teardown -- no manual cleanup required.
    """
    for key in list(os.environ):
        if key.startswith(_WAREHOUSE_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def clean_registry() -> Generator[None, None, None]:
    """
    Clear the backend registry and re-register lazy handlers.

    This fixture ensures each test starts with a clean registry state.
    It clears _registry, _config_to_name, and re-registers lazy handlers
    so that driver path resolution happens fresh for each test.

    Use this fixture in tests that mock importlib.util.find_spec to control
    driver path resolution.
    """
    from adbc_poolhouse import _registry

    # Clear the registry state
    _registry._registry.clear()
    _registry._config_to_name.clear()
    # Note: We don't clear _lazy_registrations - those are set up once at module import

    yield

    # Clean up after test
    _registry._registry.clear()
    _registry._config_to_name.clear()
