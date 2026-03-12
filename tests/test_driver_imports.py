"""
Semi-integration tests for driver imports and pool creation wiring (TEST-01..04).

These tests verify the full driver import → pool creation → connection attempt flow
for all 12 supported ADBC backends. Real driver imports are used (not mocked), but
the actual connection is mocked to assert correct kwargs without requiring credentials
or network access.

Mocking strategy (per user decision in CONTEXT.md):
- Foundry drivers + DuckDB + SQLite: mock `adbc_driver_manager.dbapi.connect`
- PyPI drivers (Snowflake, BigQuery, PostgreSQL, FlightSQL): mock each driver's own `dbapi.connect`
  when the driver is installed; fall back to `adbc_driver_manager.dbapi.connect` when not installed.
"""

from __future__ import annotations

import importlib.util
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from adbc_poolhouse import (
    BigQueryConfig,
    ClickHouseConfig,
    DatabricksConfig,
    DuckDBConfig,
    FlightSQLConfig,
    MSSQLConfig,
    MySQLConfig,
    PostgreSQLConfig,
    RedshiftConfig,
    SnowflakeConfig,
    SQLiteConfig,
    TrinoConfig,
    create_pool,
)


def _driver_installed(pkg_name: str) -> bool:
    """Check if a PyPI driver package is installed."""
    return importlib.util.find_spec(pkg_name) is not None


class TestDuckDBImports:
    """Semi-integration test: real DuckDB driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real DuckDB driver, mock connection, assert correct kwargs."""
        config = DuckDBConfig()  # :memory: by default
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_driver_manager.dbapi.connect",
            return_value=mock_conn,
        ) as mock_connect:
            pool = create_pool(config)
            pool.dispose()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        # DuckDB: assert entrypoint='duckdb_adbc_init'
        assert call_kwargs.get("entrypoint") == "duckdb_adbc_init"
        # All Foundry/DuckDB use driver= kwarg
        assert "driver" in call_kwargs


class TestSnowflakeImports:
    """Semi-integration test: real Snowflake driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real Snowflake driver, mock connection, assert correct kwargs."""
        config = SnowflakeConfig(account="test")
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        if _driver_installed("adbc_driver_snowflake"):
            # Driver installed: mock driver's own dbapi.connect
            with patch(
                "adbc_driver_snowflake.dbapi.connect",
                return_value=mock_conn,
            ) as mock_connect:
                pool = create_pool(config)
                pool.dispose()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            # PyPI drivers use db_kwargs= kwarg
            assert "db_kwargs" in call_kwargs
        else:
            # Driver not installed: mock adbc_driver_manager.dbapi.connect
            with patch(
                "adbc_driver_manager.dbapi.connect",
                return_value=mock_conn,
            ) as mock_connect:
                pool = create_pool(config)
                pool.dispose()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            # Falls back to driver= kwarg
            assert "driver" in call_kwargs


class TestBigQueryImports:
    """Semi-integration test: real BigQuery driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real BigQuery driver, mock connection, assert correct kwargs."""
        config = BigQueryConfig()
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        if _driver_installed("adbc_driver_bigquery"):
            # Driver installed: mock driver's own dbapi.connect
            with patch(
                "adbc_driver_bigquery.dbapi.connect",
                return_value=mock_conn,
            ) as mock_connect:
                pool = create_pool(config)
                pool.dispose()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            # PyPI drivers use db_kwargs= kwarg
            assert "db_kwargs" in call_kwargs
        else:
            # Driver not installed: mock adbc_driver_manager.dbapi.connect
            with patch(
                "adbc_driver_manager.dbapi.connect",
                return_value=mock_conn,
            ) as mock_connect:
                pool = create_pool(config)
                pool.dispose()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            # Falls back to driver= kwarg
            assert "driver" in call_kwargs


class TestPostgreSQLImports:
    """Semi-integration test: real PostgreSQL driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real PostgreSQL driver, mock connection, assert correct kwargs."""
        config = PostgreSQLConfig()
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        if _driver_installed("adbc_driver_postgresql"):
            # Driver installed: mock driver's own dbapi.connect
            with patch(
                "adbc_driver_postgresql.dbapi.connect",
                return_value=mock_conn,
            ) as mock_connect:
                pool = create_pool(config)
                pool.dispose()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            # PyPI drivers use db_kwargs= kwarg
            assert "db_kwargs" in call_kwargs
        else:
            # Driver not installed: mock adbc_driver_manager.dbapi.connect
            with patch(
                "adbc_driver_manager.dbapi.connect",
                return_value=mock_conn,
            ) as mock_connect:
                pool = create_pool(config)
                pool.dispose()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            # Falls back to driver= kwarg
            assert "driver" in call_kwargs


class TestFlightSQLImports:
    """Semi-integration test: real FlightSQL driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real FlightSQL driver, mock connection, assert correct kwargs."""
        config = FlightSQLConfig(uri="grpc://localhost:8815")
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        if _driver_installed("adbc_driver_flightsql"):
            # Driver installed: mock driver's own dbapi.connect
            with patch(
                "adbc_driver_flightsql.dbapi.connect",
                return_value=mock_conn,
            ) as mock_connect:
                pool = create_pool(config)
                pool.dispose()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            # PyPI drivers use db_kwargs= kwarg
            assert "db_kwargs" in call_kwargs
        else:
            # Driver not installed: mock adbc_driver_manager.dbapi.connect
            with patch(
                "adbc_driver_manager.dbapi.connect",
                return_value=mock_conn,
            ) as mock_connect:
                pool = create_pool(config)
                pool.dispose()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            # Falls back to driver= kwarg
            assert "driver" in call_kwargs


class TestSQLiteImports:
    """Semi-integration test: real SQLite driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real SQLite driver, mock connection, assert correct kwargs."""
        config = SQLiteConfig()  # :memory: by default
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        # SQLite uses adbc_driver_manager.dbapi.connect (not its own dbapi)
        # because SQLite dbapi has incompatible signature
        with patch(
            "adbc_driver_manager.dbapi.connect",
            return_value=mock_conn,
        ) as mock_connect:
            pool = create_pool(config)
            pool.dispose()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        # Foundry/DuckDB/SQLite use driver= kwarg
        assert "driver" in call_kwargs


class TestDatabricksImports:
    """Semi-integration test: real Databricks driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real Databricks driver, mock connection, assert correct kwargs."""
        config = DatabricksConfig(
            host="host",
            http_path="/sql/1.0/warehouses/abc",
            token=SecretStr("token"),  # pragma: allowlist secret
        )
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_driver_manager.dbapi.connect",
            return_value=mock_conn,
        ) as mock_connect:
            pool = create_pool(config)
            pool.dispose()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        # Foundry drivers use driver= kwarg
        assert "driver" in call_kwargs


class TestRedshiftImports:
    """Semi-integration test: real Redshift driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real Redshift driver, mock connection, assert correct kwargs."""
        config = RedshiftConfig()
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_driver_manager.dbapi.connect",
            return_value=mock_conn,
        ) as mock_connect:
            pool = create_pool(config)
            pool.dispose()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        # Foundry drivers use driver= kwarg
        assert "driver" in call_kwargs


class TestTrinoImports:
    """Semi-integration test: real Trino driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real Trino driver, mock connection, assert correct kwargs."""
        config = TrinoConfig()
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_driver_manager.dbapi.connect",
            return_value=mock_conn,
        ) as mock_connect:
            pool = create_pool(config)
            pool.dispose()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        # Foundry drivers use driver= kwarg
        assert "driver" in call_kwargs


class TestMSSQLImports:
    """Semi-integration test: real MSSQL driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real MSSQL driver, mock connection, assert correct kwargs."""
        config = MSSQLConfig()
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_driver_manager.dbapi.connect",
            return_value=mock_conn,
        ) as mock_connect:
            pool = create_pool(config)
            pool.dispose()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        # Foundry drivers use driver= kwarg
        assert "driver" in call_kwargs


class TestMySQLImports:
    """Semi-integration test: real MySQL driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real MySQL driver, mock connection, assert correct kwargs."""
        config = MySQLConfig(host="localhost", user="root", database="demo")
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_driver_manager.dbapi.connect",
            return_value=mock_conn,
        ) as mock_connect:
            pool = create_pool(config)
            pool.dispose()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        # Foundry drivers use driver= kwarg
        assert "driver" in call_kwargs


class TestClickHouseImports:
    """Semi-integration test: real ClickHouse driver import, mocked connection."""

    def test_create_pool_wiring(self) -> None:
        """Import real ClickHouse driver, mock connection, assert correct kwargs."""
        config = ClickHouseConfig(host="localhost", username="default")
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        with patch(
            "adbc_driver_manager.dbapi.connect",
            return_value=mock_conn,
        ) as mock_connect:
            pool = create_pool(config)
            pool.dispose()

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        # Foundry drivers use driver= kwarg
        assert "driver" in call_kwargs
