"""
Resolve the ADBC driver path or short name for a given warehouse config.

Three-path detection strategy (DRIV-01, DRIV-04):

  Path 1 — PyPI driver installed: use ``importlib.util.find_spec()`` to locate
      the package, then call ``pkg._driver_path()`` to get the shared library path.
  Path 2 — PyPI driver absent, manifest may exist: return the package name so
      ``adbc_driver_manager`` can attempt manifest-based resolution at connect time.
  Path 3 — manifest also absent: ``create_adbc_connection()`` in ``_driver_api.py``
      catches the NOT_FOUND status from ``adbc_driver_manager`` and re-raises it as
      a user-friendly ImportError pointing to https://docs.adbc-drivers.org/.

  Foundry drivers (Databricks, Redshift, Trino, MSSQL, Teradata): skip find_spec
      entirely — return the short driver name for manifest resolution directly.

  DuckDB is special: it bundles its ADBC driver as the ``_duckdb`` C extension
      inside the ``duckdb`` wheel (no separate ``adbc_driver_duckdb`` package).
      find_spec("_duckdb") locates the C extension; if absent, raise ImportError
      immediately (no manifest fallback for DuckDB).

All warehouse-specific driver imports are kept inside function bodies to preserve
bare-import safety (DRIV-04). Only config class imports (no ADBC driver packages)
appear at module level.

Internal only — not exported from ``__init__.py``.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from adbc_poolhouse._bigquery_config import BigQueryConfig
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._teradata_config import TeradataConfig
from adbc_poolhouse._trino_config import TrinoConfig

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig

# PyPI-installed warehouse drivers: (package_name, pip_extra_name).
# package_name is passed to find_spec() and used for Path 2 fallback.
# pip_extra_name is the adbc-poolhouse[extra] install name for error messages.
_PYPI_PACKAGES: dict[type, tuple[str, str]] = {
    SnowflakeConfig: ("adbc_driver_snowflake", "snowflake"),
    BigQueryConfig: ("adbc_driver_bigquery", "bigquery"),
    PostgreSQLConfig: ("adbc_driver_postgresql", "postgresql"),
    FlightSQLConfig: ("adbc_driver_flightsql", "flightsql"),
}

# Foundry (manifest-based) drivers: (driver_manager_name, dbc_install_name).
# driver_manager_name is returned directly as the driver_path for adbc_driver_manager.
# dbc_install_name is used in ImportError messages from _driver_api.py.
_FOUNDRY_DRIVERS: dict[type, tuple[str, str]] = {
    DatabricksConfig: ("databricks", "databricks"),
    RedshiftConfig: ("redshift", "redshift"),
    TrinoConfig: ("trino", "trino"),
    MSSQLConfig: ("mssql", "mssql"),
    TeradataConfig: ("teradata", "teradata"),  # LOW confidence name
}


def resolve_driver(config: WarehouseConfig) -> str:
    """
    Resolve the ADBC driver path or short name for a warehouse config.

    Uses the 3-path detection strategy described in this module's docstring.

    Returns:
        For DuckDB (Path 1): absolute path to ``_duckdb`` shared library.
        For PyPI drivers (Path 1): absolute path returned by ``pkg._driver_path()``.
        For PyPI drivers (Path 2 fallback): the package name string.
        For Foundry drivers: the short driver name string (e.g. ``"databricks"``).

    Raises:
        ImportError: For DuckDB when ``_duckdb`` C extension is not installed.
            Message includes ``pip install adbc-poolhouse[duckdb]``.
        TypeError: If ``config`` is not a recognised WarehouseConfig subclass.
    """
    config_type = type(config)

    if config_type is DuckDBConfig:
        return _resolve_duckdb()

    if config_type in _PYPI_PACKAGES:
        pkg_name, extra = _PYPI_PACKAGES[config_type]
        return _resolve_pypi_driver(pkg_name, extra)

    if config_type in _FOUNDRY_DRIVERS:
        driver_name, _ = _FOUNDRY_DRIVERS[config_type]
        return driver_name

    raise TypeError(f"Unsupported config type: {type(config).__name__}")


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
        pkg = __import__(pkg_name)
        return pkg._driver_path()  # type: ignore[attr-defined]
    # Path 2: return package name for adbc_driver_manager manifest resolution.
    # If manifest is also absent, create_adbc_connection() will catch NOT_FOUND
    # and raise ImportError with the install instructions.
    return pkg_name
