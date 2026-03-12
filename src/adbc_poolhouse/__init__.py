"""Connection pooling for ADBC drivers from typed warehouse configs."""

from adbc_poolhouse._base_config import BaseWarehouseConfig, WarehouseConfig
from adbc_poolhouse._bigquery_config import BigQueryConfig
from adbc_poolhouse._clickhouse_config import ClickHouseConfig
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._exceptions import (
    BackendAlreadyRegisteredError,
    BackendNotRegisteredError,
    ConfigurationError,
    PoolhouseError,
    RegistryError,
)
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._mysql_config import MySQLConfig
from adbc_poolhouse._pool_factory import close_pool, create_pool, managed_pool
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._registry import register_backend
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._sqlite_config import SQLiteConfig
from adbc_poolhouse._trino_config import TrinoConfig

__all__ = [
    "BackendAlreadyRegisteredError",
    "BackendNotRegisteredError",
    "BaseWarehouseConfig",
    "BigQueryConfig",
    "ClickHouseConfig",
    "ConfigurationError",
    "DatabricksConfig",
    "DuckDBConfig",
    "FlightSQLConfig",
    "MSSQLConfig",
    "MySQLConfig",
    "PoolhouseError",
    "PostgreSQLConfig",
    "RedshiftConfig",
    "RegistryError",
    "SnowflakeConfig",
    "SQLiteConfig",
    "TrinoConfig",
    "WarehouseConfig",
    "close_pool",
    "create_pool",
    "managed_pool",
    "register_backend",
]
