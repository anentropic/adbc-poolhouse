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

import pytest

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
