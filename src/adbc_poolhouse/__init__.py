"""Connection pooling for ADBC drivers from typed warehouse configs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adbc_poolhouse._base_config import BaseWarehouseConfig, WarehouseConfig
from adbc_poolhouse._bigquery_config import BigQueryConfig
from adbc_poolhouse._clickhouse_config import ClickHouseConfig
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._exceptions import (
    ConfigurationError,
    ConnectionBusyError,
    PoolhouseError,
)
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._mysql_config import MySQLConfig
from adbc_poolhouse._pool_factory import close_pool, create_pool, managed_pool
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._quack_config import QuackConfig
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._sqlite_config import SQLiteConfig
from adbc_poolhouse._trino_config import TrinoConfig

if TYPE_CHECKING:
    # Async entry points are resolved lazily via __getattr__ at runtime (PEP 562)
    # to keep `import adbc_poolhouse` anyio-free; re-declared here only so static
    # type checkers and IDEs see them as package attributes.
    from adbc_poolhouse._async import (
        close_async_pool,
        create_async_pool,
        managed_async_pool,
    )

__all__ = [
    "BaseWarehouseConfig",
    "BigQueryConfig",
    "ClickHouseConfig",
    "ConfigurationError",
    "ConnectionBusyError",
    "DatabricksConfig",
    "DuckDBConfig",
    "FlightSQLConfig",
    "MSSQLConfig",
    "MySQLConfig",
    "PoolhouseError",
    "PostgreSQLConfig",
    "QuackConfig",
    "RedshiftConfig",
    "SnowflakeConfig",
    "SQLiteConfig",
    "TrinoConfig",
    "WarehouseConfig",
    "close_async_pool",
    "close_pool",
    "create_async_pool",
    "create_pool",
    "managed_async_pool",
    "managed_pool",
]

# Async entry points exposed lazily (PEP 562). Importing them eagerly would pull
# in anyio at `import adbc_poolhouse` time and break the zero-cost sync path
# (PKG-04), so they are resolved from the `_async` subpackage only on first
# access. If anyio is not installed, the access raises a clear ImportError
# naming the [async] extra rather than a bare "No module named 'anyio'".
_LAZY_ASYNC_NAMES = frozenset({"create_async_pool", "managed_async_pool", "close_async_pool"})


def __getattr__(name: str) -> object:
    """
    Lazily resolve the async entry points (PEP 562 module __getattr__).

    Args:
        name: The attribute being accessed on the `adbc_poolhouse` package.

    Returns:
        The requested async entry point from `adbc_poolhouse._async`.

    Raises:
        ImportError: If `name` is an async entry point but the optional `anyio`
            dependency is not installed.
        AttributeError: If `name` is not a known package attribute.
    """
    if name in _LAZY_ASYNC_NAMES:
        try:
            from adbc_poolhouse import _async
        except ImportError as exc:  # anyio (the [async] extra) is missing
            raise ImportError(
                f"{name!r} requires the optional async dependencies. "
                "Install them with: pip install adbc-poolhouse[async]"
            ) from exc
        return getattr(_async, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return the package's public names, including the lazy async entries."""
    return sorted(__all__)
