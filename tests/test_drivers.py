"""
Driver detection unit tests (TEST-06).

Tests cover all three detection paths using unittest.mock.patch to simulate
driver presence/absence -- no real ADBC driver connection is made.  Tests
also verify Foundry backends return static strings and that
create_adbc_connection() re-raises adbc_driver_manager NOT_FOUND as
ImportError with https://docs.adbc-drivers.org/ (DRIV-03).

After Phase 18 (registration removal), driver resolution is handled by each
config's ``_driver_path()`` method, which calls the shared
``_resolve_driver_path()`` helper on ``BaseWarehouseConfig``.

Patch target for find_spec: "importlib.util.find_spec"
  _base_config.py does `import importlib.util` at module level and calls
  `importlib.util.find_spec()` inside `_resolve_driver_path()`, so
  patching the global importlib.util.find_spec is the correct strategy.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adbc_poolhouse import ClickHouseConfig
from adbc_poolhouse._bigquery_config import BigQueryConfig
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._mysql_config import MySQLConfig
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._sqlite_config import SQLiteConfig
from adbc_poolhouse._trino_config import TrinoConfig


class TestDuckDBDriverPath:
    """Tests for DuckDB driver path resolution via config._driver_path()."""

    def test_path1_duckdb_found_via_find_spec(self) -> None:
        """Path 1: find_spec('adbc_driver_duckdb') returns spec -> calls driver_path()."""
        config = DuckDBConfig()
        mock_spec = MagicMock()
        mock_pkg = MagicMock()
        mock_pkg.__dict__ = {"driver_path": lambda: "/path/to/_duckdb.cpython-314-darwin.so"}
        with (
            patch("importlib.util.find_spec", return_value=mock_spec),
            patch("builtins.__import__", return_value=mock_pkg),
        ):
            path = config._driver_path()
        assert path == "/path/to/_duckdb.cpython-314-darwin.so"

    def test_path2_duckdb_missing_returns_package_name(self) -> None:
        """Path 2: find_spec returns None -> returns 'adbc_driver_duckdb' for manifest fallback."""
        with patch("importlib.util.find_spec", return_value=None):
            path = DuckDBConfig()._driver_path()
        assert path == "adbc_driver_duckdb"


class TestPyPIDriverPath:
    """Tests for PyPI-installed warehouse driver detection via config._driver_path()."""

    def test_path2_snowflake_missing_returns_package_name(self) -> None:
        """Path 2: find_spec None -> returns package name for manifest fallback."""
        with patch("importlib.util.find_spec", return_value=None):
            result = SnowflakeConfig(account="a")._driver_path()
        assert result == "adbc_driver_snowflake"

    def test_path1_snowflake_found_returns_driver_path(self) -> None:
        """Path 1: find_spec returns a spec -> import pkg and call _driver_path()."""
        config = SnowflakeConfig(account="a")
        mock_spec = MagicMock()
        mock_pkg = MagicMock()
        mock_pkg.__dict__ = {"_driver_path": lambda: "/path/to/adbc_driver_snowflake.so"}
        with (
            patch("importlib.util.find_spec", return_value=mock_spec),
            patch("builtins.__import__", return_value=mock_pkg),
        ):
            result = config._driver_path()
        assert result == "/path/to/adbc_driver_snowflake.so"

    def test_path2_bigquery_missing_returns_package_name(self) -> None:
        """Path 2: find_spec None -> returns 'adbc_driver_bigquery'."""
        with patch("importlib.util.find_spec", return_value=None):
            result = BigQueryConfig()._driver_path()
        assert result == "adbc_driver_bigquery"

    def test_path2_postgresql_missing_returns_package_name(self) -> None:
        """Path 2: find_spec None -> returns 'adbc_driver_postgresql'."""
        with patch("importlib.util.find_spec", return_value=None):
            result = PostgreSQLConfig()._driver_path()
        assert result == "adbc_driver_postgresql"

    def test_path2_flightsql_missing_returns_package_name(self) -> None:
        """Path 2: find_spec None -> returns 'adbc_driver_flightsql'."""
        with patch("importlib.util.find_spec", return_value=None):
            result = FlightSQLConfig()._driver_path()
        assert result == "adbc_driver_flightsql"

    def test_path2_sqlite_missing_returns_package_name(self) -> None:
        """Path 2: find_spec None -> returns 'adbc_driver_sqlite'."""
        with patch("importlib.util.find_spec", return_value=None):
            result = SQLiteConfig()._driver_path()
        assert result == "adbc_driver_sqlite"


class TestFoundryDriverPath:
    """Tests for Foundry (manifest-based) driver detection -- static strings."""

    def test_databricks_returns_short_name(self) -> None:
        """Foundry: _driver_path() returns 'databricks'."""
        from pydantic import SecretStr

        _dbx_uri = "databricks://token:dapi@host:443/wh/abc"  # pragma: allowlist secret
        config = DatabricksConfig(uri=SecretStr(_dbx_uri))
        assert config._driver_path() == "databricks"

    def test_redshift_returns_short_name(self) -> None:
        """Foundry: Redshift returns 'redshift'."""
        assert RedshiftConfig()._driver_path() == "redshift"

    def test_mysql_returns_short_name(self) -> None:
        """Foundry: MySQL returns 'mysql'."""
        assert MySQLConfig(host="h", user="u", database="db")._driver_path() == "mysql"

    def test_clickhouse_returns_short_name(self) -> None:
        """Foundry: ClickHouse returns 'clickhouse'."""
        assert ClickHouseConfig(host="h", username="u")._driver_path() == "clickhouse"

    def test_trino_returns_short_name(self) -> None:
        """Foundry: Trino returns 'trino'."""
        assert TrinoConfig()._driver_path() == "trino"

    def test_mssql_returns_short_name(self) -> None:
        """Foundry: MSSQL returns 'mssql'."""
        assert MSSQLConfig()._driver_path() == "mssql"


class TestDbApiModule:
    """Tests for config._dbapi_module() return values."""

    def test_snowflake_dbapi_when_installed(self) -> None:
        """Snowflake returns dbapi module name when driver package is installed."""
        mock_spec = MagicMock()
        with patch("importlib.util.find_spec", return_value=mock_spec):
            result = SnowflakeConfig(account="a")._dbapi_module()
        assert result == "adbc_driver_snowflake.dbapi"

    def test_snowflake_dbapi_when_missing(self) -> None:
        """Snowflake returns None when driver package is not installed."""
        with patch("importlib.util.find_spec", return_value=None):
            result = SnowflakeConfig(account="a")._dbapi_module()
        assert result is None

    def test_duckdb_dbapi_returns_none(self) -> None:
        """DuckDB always returns None (routes through adbc_driver_manager)."""
        assert DuckDBConfig()._dbapi_module() is None

    def test_sqlite_dbapi_returns_none(self) -> None:
        """SQLite returns None (incompatible dbapi signature)."""
        assert SQLiteConfig()._dbapi_module() is None

    def test_foundry_dbapi_returns_none(self) -> None:
        """Foundry configs return None (route through adbc_driver_manager)."""
        from pydantic import SecretStr

        _dbx_uri = "databricks://token:dapi@host:443/wh/abc"  # pragma: allowlist secret
        assert DatabricksConfig(uri=SecretStr(_dbx_uri))._dbapi_module() is None
        assert RedshiftConfig()._dbapi_module() is None
        assert TrinoConfig()._dbapi_module() is None
        assert MSSQLConfig()._dbapi_module() is None
        assert MySQLConfig(host="h", user="u", database="db")._dbapi_module() is None
        assert ClickHouseConfig(host="h", username="u")._dbapi_module() is None


class TestCreateAdbcConnectionFoundryNotFound:
    """Tests for DRIV-03: Foundry NOT_FOUND -> ImportError with docs URL."""

    def test_foundry_not_found_raises_import_error_with_docs_url(self) -> None:
        """DRIV-03: Foundry NOT_FOUND -> ImportError with docs URL."""
        import adbc_driver_manager

        from adbc_poolhouse._driver_api import create_adbc_connection

        not_found_exc = adbc_driver_manager.Error(
            "NOT_FOUND: no driver manifest for 'databricks'",
            status_code=adbc_driver_manager.AdbcStatusCode.NOT_FOUND,
        )

        with (
            patch("adbc_driver_manager.dbapi.connect", side_effect=not_found_exc),
            pytest.raises(ImportError, match=r"https://docs\.adbc-drivers\.org/"),
        ):
            create_adbc_connection("databricks", {})

    def test_foundry_not_found_message_contains_install_command(self) -> None:
        """DRIV-03: ImportError message includes dbc install command."""
        import adbc_driver_manager

        from adbc_poolhouse._driver_api import create_adbc_connection

        not_found_exc = adbc_driver_manager.Error(
            "NOT_FOUND: no driver manifest for 'databricks'",
            status_code=adbc_driver_manager.AdbcStatusCode.NOT_FOUND,
        )

        with (
            patch("adbc_driver_manager.dbapi.connect", side_effect=not_found_exc),
            pytest.raises(ImportError, match=r"dbc install databricks"),
        ):
            create_adbc_connection("databricks", {})
