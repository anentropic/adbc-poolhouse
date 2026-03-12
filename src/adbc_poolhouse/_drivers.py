"""
Resolve the ADBC driver path or short name for a given warehouse config.

Queries the backend registry for the appropriate driver_path, All
12 built-in backends are registered lazily on avoid importing all translator
modules at startup.

Internal only — not exported from ``__init__.py``.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from adbc_poolhouse._bigquery_config import BigQueryConfig
from adbc_poolhouse._clickhouse_config import ClickHouseConfig
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._mysql_config import MySQLConfig
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._registry import ensure_registered, get_driver_path, register_lazy
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._sqlite_config import SQLiteConfig
from adbc_poolhouse._trino_config import TrinoConfig

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig


# PyPI-installed warehouse drivers: (package_name, pip_extra_name).
# Used by resolve_dbapi_module() to determine if driver is installed.
_PYPI_PACKAGES: dict[type, tuple[str, str]] = {
    SnowflakeConfig: ("adbc_driver_snowflake", "snowflake"),
    BigQueryConfig: ("adbc_driver_bigquery", "bigquery"),
    PostgreSQLConfig: ("adbc_driver_postgresql", "postgresql"),
    FlightSQLConfig: ("adbc_driver_flightsql", "flightsql"),
    SQLiteConfig: ("adbc_driver_sqlite", "sqlite"),
}


def resolve_driver(config: WarehouseConfig) -> str:
    """
    Resolve the ADBC driver path or short name for a warehouse config.

    Queries the backend registry for the appropriate driver_path.

    Returns:
        For DuckDB: absolute path to ``_duckdb`` shared library.
        For PyPI drivers: absolute path returned by ``pkg._driver_path()`` or
            package name for manifest fallback.
        For Foundry drivers: the short driver name string (e.g. ``"databricks"``).

    Raises:
        ImportError: For DuckDB when ``_duckdb`` C extension is not installed.
            Message includes ``pip install adbc-poolhouse[duckdb]``.
        BackendNotRegisteredError: If ``config`` is not a registered WarehouseConfig subclass.
    """
    ensure_registered(config)
    return get_driver_path(config)


def resolve_dbapi_module(config: WarehouseConfig) -> str | None:
    """
    Return the DBAPI module name for PyPI drivers, or None for Foundry/DuckDB.

    When a PyPI driver is installed, its own ``.dbapi.connect()`` should be
    used instead of routing through ``adbc_driver_manager.dbapi``.  This
    ensures that tools which monkeypatch per-driver DBAPI modules (e.g.
    pytest-adbc-replay) intercept at the correct location.

    SQLite is excluded because its ``dbapi.connect()`` has an incompatible
    signature (takes ``uri`` positionally, no ``db_kwargs``).

    Args:
        config: A warehouse config model instance.

    Returns:
        A dotted module name such as ``"adbc_driver_snowflake.dbapi"`` when
        the driver package is installed, or ``None`` for Foundry drivers,
        DuckDB, SQLite, and PyPI drivers that are not currently installed.
    """
    config_type = type(config)
    if config_type is SQLiteConfig:
        return None
    if config_type in _PYPI_PACKAGES:
        pkg_name, _ = _PYPI_PACKAGES[config_type]
        if importlib.util.find_spec(pkg_name) is not None:
            return f"{pkg_name}.dbapi"
    return None


def _resolve_duckdb() -> str:
    """
    Locate the DuckDB ADBC C extension (_duckdb) inside the duckdb wheel.

    DuckDB bundles its ADBC driver as the ``_duckdb`` C extension (not a
    separate ``adbc_driver_duckdb`` package). find_spec("_duckdb") locates
    the compiled extension. There is no manifest fallback for DuckDB.

    Returns:
        Absolute path to the ``_duckdb`` shared library.

    Raises:
        ImportError: If ``_duckdb`` is not installed (duckdb not in env).
    """
    spec = importlib.util.find_spec("_duckdb")
    if spec is None or spec.origin is None:
        raise ImportError("DuckDB ADBC driver not found. Run: `pip install adbc-poolhouse[duckdb]`")
    return spec.origin


def _resolve_pypi_driver(pkg_name: str, extra: str) -> str:  # noqa: ARG001
    """
    Locate a PyPI-published ADBC warehouse driver.

    Path 1: find_spec finds the package → import it and call _driver_path().
    Path 2: find_spec returns None → return pkg_name so adbc_driver_manager
        can attempt manifest-based resolution. If that also fails,
        create_adbc_connection() in _driver_api.py raises ImportError.

    Args:
        pkg_name: The Python package name (e.g. ``"adbc_driver_snowflake"``).
        extra: The adbc-poolhouse pip extra name (unused here; used by caller
            for error message construction in _driver_api.py).

    Returns:
        Absolute path to the driver shared library (Path 1), or the package
        name string as a manifest fallback key (Path 2).
    """
    spec = importlib.util.find_spec(pkg_name)
    if spec is not None:
        pkg: Any = __import__(pkg_name)
        return pkg._driver_path()
    # Path 2: return package name for adbc_driver_manager manifest resolution.
    # If manifest is also absent, create_adbc_connection() will catch NOT_FOUND
    # and raise ImportError with the install instructions.
    return pkg_name


def _setup_lazy_registrations() -> None:
    """
    Register lazy initialization functions for all 12 built-in backends.

    Each lazy registration function imports the translator and config class,
    resolves the driver path, and calls register_backend().
    """
    from adbc_poolhouse._registry import register_backend

    # DuckDB - special case, uses _resolve_duckdb()
    def _register_duckdb() -> None:
        from adbc_poolhouse._duckdb_translator import translate_duckdb

        register_backend(
            name="adbc_driver_duckdb",
            config_class=DuckDBConfig,
            translator=translate_duckdb,  # type: ignore[arg-type]
            driver_path=_resolve_duckdb(),
        )

    # Snowflake
    def _register_snowflake() -> None:
        from adbc_poolhouse._snowflake_translator import translate_snowflake

        register_backend(
            name="adbc_driver_snowflake",
            config_class=SnowflakeConfig,
            translator=translate_snowflake,  # type: ignore[arg-type]
            driver_path=_resolve_pypi_driver("adbc_driver_snowflake", "snowflake"),
        )

    # BigQuery
    def _register_bigquery() -> None:
        from adbc_poolhouse._bigquery_translator import translate_bigquery

        register_backend(
            name="adbc_driver_bigquery",
            config_class=BigQueryConfig,
            translator=translate_bigquery,  # type: ignore[arg-type]
            driver_path=_resolve_pypi_driver("adbc_driver_bigquery", "bigquery"),
        )

    # PostgreSQL
    def _register_postgresql() -> None:
        from adbc_poolhouse._postgresql_translator import translate_postgresql

        register_backend(
            name="adbc_driver_postgresql",
            config_class=PostgreSQLConfig,
            translator=translate_postgresql,  # type: ignore[arg-type]
            driver_path=_resolve_pypi_driver("adbc_driver_postgresql", "postgresql"),
        )

    # FlightSQL
    def _register_flightsql() -> None:
        from adbc_poolhouse._flightsql_translator import translate_flightsql

        register_backend(
            name="adbc_driver_flightsql",
            config_class=FlightSQLConfig,
            translator=translate_flightsql,  # type: ignore[arg-type]
            driver_path=_resolve_pypi_driver("adbc_driver_flightsql", "flightsql"),
        )

    # SQLite
    def _register_sqlite() -> None:
        from adbc_poolhouse._sqlite_translator import translate_sqlite

        register_backend(
            name="adbc_driver_sqlite",
            config_class=SQLiteConfig,
            translator=translate_sqlite,  # type: ignore[arg-type]
            driver_path=_resolve_pypi_driver("adbc_driver_sqlite", "sqlite"),
        )

    # ClickHouse (Foundry)
    def _register_clickhouse() -> None:
        from adbc_poolhouse._clickhouse_translator import translate_clickhouse

        register_backend(
            name="__dbc__clickhouse",
            config_class=ClickHouseConfig,
            translator=translate_clickhouse,  # type: ignore[arg-type]
            driver_path="clickhouse",
        )

    # Databricks (Foundry)
    def _register_databricks() -> None:
        from adbc_poolhouse._databricks_translator import translate_databricks

        register_backend(
            name="__dbc__databricks",
            config_class=DatabricksConfig,
            translator=translate_databricks,  # type: ignore[arg-type]
            driver_path="databricks",
        )

    # MSSQL (Foundry)
    def _register_mssql() -> None:
        from adbc_poolhouse._mssql_translator import translate_mssql

        register_backend(
            name="__dbc__mssql",
            config_class=MSSQLConfig,
            translator=translate_mssql,  # type: ignore[arg-type]
            driver_path="mssql",
        )

    # MySQL (Foundry)
    def _register_mysql() -> None:
        from adbc_poolhouse._mysql_translator import translate_mysql

        register_backend(
            name="__dbc__mysql",
            config_class=MySQLConfig,
            translator=translate_mysql,  # type: ignore[arg-type]
            driver_path="mysql",
        )

    # Redshift (Foundry)
    def _register_redshift() -> None:
        from adbc_poolhouse._redshift_translator import translate_redshift

        register_backend(
            name="__dbc__redshift",
            config_class=RedshiftConfig,
            translator=translate_redshift,  # type: ignore[arg-type]
            driver_path="redshift",
        )

    # Trino (Foundry)
    def _register_trino() -> None:
        from adbc_poolhouse._trino_translator import translate_trino

        register_backend(
            name="__dbc__trino",
            config_class=TrinoConfig,
            translator=translate_trino,  # type: ignore[arg-type]
            driver_path="trino",
        )

    # Register all lazy handlers
    register_lazy(DuckDBConfig, _register_duckdb)
    register_lazy(SnowflakeConfig, _register_snowflake)
    register_lazy(BigQueryConfig, _register_bigquery)
    register_lazy(PostgreSQLConfig, _register_postgresql)
    register_lazy(FlightSQLConfig, _register_flightsql)
    register_lazy(SQLiteConfig, _register_sqlite)
    register_lazy(ClickHouseConfig, _register_clickhouse)
    register_lazy(DatabricksConfig, _register_databricks)
    register_lazy(MSSQLConfig, _register_mssql)
    register_lazy(MySQLConfig, _register_mysql)
    register_lazy(RedshiftConfig, _register_redshift)
    register_lazy(TrinoConfig, _register_trino)


# Set up lazy registrations at module import time
_setup_lazy_registrations()
