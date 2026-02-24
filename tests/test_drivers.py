"""
Driver detection unit tests (TEST-06).

Tests cover all three detection paths using unittest.mock.patch to simulate
driver presence/absence — no real ADBC driver connection is made. Tests also
verify Foundry backends skip find_spec entirely and that create_adbc_connection()
re-raises adbc_driver_manager NOT_FOUND as ImportError with
https://docs.adbc-drivers.org/ (DRIV-03).

Patch target for find_spec: "importlib.util.find_spec"
  _drivers.py does `import importlib.util` at module level and calls
  `importlib.util.find_spec()` inside functions, so patching the global
  importlib.util.find_spec is the correct strategy.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._drivers import resolve_driver
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._teradata_config import TeradataConfig


class TestResolveDuckDB:
    """Tests for DuckDB special-case driver detection (no manifest fallback)."""

    def test_path1_duckdb_found_via_find_spec(self) -> None:
        """Path 1: find_spec('_duckdb') returns spec with origin."""
        mock_spec = MagicMock()
        mock_spec.origin = "/path/to/_duckdb.cpython-314-darwin.so"
        with patch("importlib.util.find_spec", return_value=mock_spec):
            path = resolve_driver(DuckDBConfig())
        assert path == "/path/to/_duckdb.cpython-314-darwin.so"

    def test_path3_duckdb_missing_raises_import_error(self) -> None:
        """Path 3: find_spec returns None -> ImportError with install command."""
        with (
            patch("importlib.util.find_spec", return_value=None),
            pytest.raises(ImportError, match=r"pip install adbc-poolhouse\[duckdb\]"),
        ):
            resolve_driver(DuckDBConfig())

    def test_path3_duckdb_spec_with_none_origin_raises_import_error(self) -> None:
        """Path 3 variant: find_spec returns a spec but origin is None -> ImportError."""
        mock_spec = MagicMock()
        mock_spec.origin = None
        with (
            patch("importlib.util.find_spec", return_value=mock_spec),
            pytest.raises(ImportError, match=r"pip install adbc-poolhouse\[duckdb\]"),
        ):
            resolve_driver(DuckDBConfig())


class TestResolvePyPIDriver:
    """Tests for PyPI-installed warehouse driver detection (Paths 1 and 2)."""

    def test_path2_snowflake_missing_returns_package_name(self) -> None:
        """Path 2: find_spec None -> returns package name for manifest fallback."""
        with patch("importlib.util.find_spec", return_value=None):
            result = resolve_driver(SnowflakeConfig(account="a"))
        assert result == "adbc_driver_snowflake"

    def test_path1_snowflake_found_returns_driver_path(self) -> None:
        """Path 1: find_spec returns a spec -> import pkg and call _driver_path()."""
        mock_spec = MagicMock()
        mock_pkg = MagicMock()
        mock_pkg._driver_path.return_value = "/path/to/adbc_driver_snowflake.so"
        with (
            patch("importlib.util.find_spec", return_value=mock_spec),
            patch("builtins.__import__", return_value=mock_pkg),
        ):
            result = resolve_driver(SnowflakeConfig(account="a"))
        assert result == "/path/to/adbc_driver_snowflake.so"


class TestResolveFoundryDriver:
    """Tests for Foundry (manifest-based) driver detection (skip find_spec)."""

    def test_databricks_returns_short_name_without_find_spec(self) -> None:
        """Foundry: resolve_driver returns driver name without calling find_spec."""
        with patch("importlib.util.find_spec") as mock_find:
            result = resolve_driver(DatabricksConfig())
        mock_find.assert_not_called()
        assert result == "databricks"

    def test_redshift_returns_short_name(self) -> None:
        """Foundry: Redshift returns 'redshift' without calling find_spec."""
        with patch("importlib.util.find_spec") as mock_find:
            result = resolve_driver(RedshiftConfig())
        mock_find.assert_not_called()
        assert result == "redshift"

    def test_teradata_returns_short_name(self) -> None:
        """Foundry: Teradata returns 'teradata' (LOW confidence driver name)."""
        # LOW confidence: driver name 'teradata' inferred from pattern
        with patch("importlib.util.find_spec") as mock_find:
            result = resolve_driver(TeradataConfig())
        mock_find.assert_not_called()
        assert result == "teradata"


class TestResolveDriverEdgeCases:
    """Tests for edge cases and unsupported config types."""

    def test_unknown_config_raises_type_error(self) -> None:
        """Custom class not in dispatch map -> TypeError raised."""

        class CustomConfig:
            pass

        with pytest.raises(TypeError, match=r"Unsupported config type: CustomConfig"):
            resolve_driver(CustomConfig())  # type: ignore[arg-type]


class TestCreateAdbcConnectionFoundryNotFound:
    """Tests for DRIV-03: Foundry NOT_FOUND -> ImportError with docs URL."""

    def test_foundry_not_found_raises_import_error_with_docs_url(self) -> None:
        """DRIV-03: Foundry NOT_FOUND -> ImportError with docs URL."""
        import adbc_driver_manager

        from adbc_poolhouse._driver_api import create_adbc_connection

        # adbc_driver_manager.Error requires status_code kwarg.
        # NOT_FOUND (int-enum value 3) triggers the catch-and-reraise in _driver_api.py.
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
