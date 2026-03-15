"""Tests for _driver_api.py dbapi connect() signature dispatch."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from adbc_poolhouse._driver_api import create_adbc_connection


class TestDbApiModuleSignatureDispatch:
    """Tests for signature-aware dispatch of dbapi_module connect() calls."""

    def test_family_a_uses_db_kwargs(self) -> None:
        """Family A (Snowflake, PostgreSQL, BigQuery, FlightSQL): connect(db_kwargs=...)."""
        call_record: dict[str, Any] = {}

        # Real function with db_kwargs parameter so inspect.signature sees it
        def connect(db_kwargs: dict[str, str] | None = None, **kwargs: str) -> MagicMock:
            call_record["db_kwargs"] = db_kwargs
            call_record.update(kwargs)
            return MagicMock()

        mock_mod = MagicMock()
        mock_mod.connect = connect

        with patch("importlib.import_module", return_value=mock_mod):
            create_adbc_connection("", {"key": "val"}, dbapi_module="mock_family_a")
            assert call_record["db_kwargs"] == {"key": "val"}

    def test_family_b_unpacks_kwargs(self) -> None:
        """Family B (DuckDB, SQLite): connect(**kwargs) -- no db_kwargs param."""
        call_record: dict[str, Any] = {}

        # Real function WITHOUT db_kwargs parameter
        def connect(**kwargs: str) -> MagicMock:
            call_record.update(kwargs)
            return MagicMock()

        mock_mod = MagicMock()
        mock_mod.connect = connect

        with patch("importlib.import_module", return_value=mock_mod):
            create_adbc_connection("", {"path": ":memory:"}, dbapi_module="mock_family_b")
            # Should have unpacked kwargs, not passed db_kwargs=
            assert call_record.get("path") == ":memory:"
            assert "db_kwargs" not in call_record

    def test_family_b_duckdb_integration(self) -> None:
        """DuckDB integration: dbapi_module path creates a working connection."""
        conn = create_adbc_connection(
            "", {"path": ":memory:"}, dbapi_module="adbc_driver_duckdb.dbapi"
        )
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 42")  # type: ignore[reportUnknownMemberType]
            result: tuple[Any, ...] | None = cursor.fetchone()  # type: ignore[reportUnknownMemberType]
            assert result == (42,)
            cursor.close()
        finally:
            conn.close()
