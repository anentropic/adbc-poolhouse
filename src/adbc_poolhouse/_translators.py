"""
Translate any warehouse config to ADBC driver kwargs.

This module is the dispatch coordinator for Phase 4. It imports all
10 per-warehouse translator functions and exposes a single
``translate_config()`` entry point for Phase 5.

Internal only — not exported from ``__init__.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adbc_poolhouse._bigquery_config import BigQueryConfig
from adbc_poolhouse._bigquery_translator import translate_bigquery
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._databricks_translator import translate_databricks
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._duckdb_translator import translate_duckdb
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._flightsql_translator import translate_flightsql
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._mssql_translator import translate_mssql
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._postgresql_translator import translate_postgresql
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._redshift_translator import translate_redshift
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._snowflake_translator import translate_snowflake
from adbc_poolhouse._teradata_config import TeradataConfig
from adbc_poolhouse._teradata_translator import translate_teradata
from adbc_poolhouse._trino_config import TrinoConfig
from adbc_poolhouse._trino_translator import translate_trino

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig


def translate_config(config: WarehouseConfig) -> dict[str, str]:
    """
    Translate any supported warehouse config to ADBC driver kwargs.

    Dispatches to the appropriate per-warehouse translator function using
    isinstance checks. All concrete config classes are direct siblings of
    BaseWarehouseConfig (no multi-level inheritance), so check order does
    not affect correctness; order is alphabetical within PyPI vs Foundry groups.

    Returns:
        A dict[str, str] of kwargs to pass as ``db_kwargs`` to
        ``adbc_driver_manager.dbapi.connect()``. All values are strings.

    Raises:
        TypeError: If ``config`` is not a recognised WarehouseConfig subclass.
    """
    if isinstance(config, BigQueryConfig):
        return translate_bigquery(config)
    if isinstance(config, DatabricksConfig):
        return translate_databricks(config)
    if isinstance(config, DuckDBConfig):
        return translate_duckdb(config)
    if isinstance(config, FlightSQLConfig):
        return translate_flightsql(config)
    if isinstance(config, MSSQLConfig):
        return translate_mssql(config)
    if isinstance(config, PostgreSQLConfig):
        return translate_postgresql(config)
    if isinstance(config, RedshiftConfig):
        return translate_redshift(config)
    if isinstance(config, SnowflakeConfig):
        return translate_snowflake(config)
    if isinstance(config, TeradataConfig):
        return translate_teradata(config)
    if isinstance(config, TrinoConfig):
        return translate_trino(config)
    raise TypeError(f"Unsupported config type: {type(config).__name__}")
