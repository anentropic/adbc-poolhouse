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

    def test_family_a_prime_pops_uri_when_required_positional(self) -> None:
        """Family A' (Quack/Postgres/FlightSQL): required-positional uri + db_kwargs."""
        call_record: dict[str, Any] = {}

        # Real function with the affected signature shape: required-positional
        # `uri` (no default), keyword-only `db_kwargs`.
        def connect(uri: str, *, db_kwargs: dict[str, str] | None = None) -> MagicMock:
            call_record["uri_positional"] = uri
            call_record["db_kwargs"] = db_kwargs
            return MagicMock()

        mock_mod = MagicMock()
        mock_mod.connect = connect

        with patch("importlib.import_module", return_value=mock_mod):
            create_adbc_connection(
                "",
                {"uri": "quack://h:1", "adbc.quack.token": "t"},
                dbapi_module="mock_family_a_prime",
            )

        # uri was popped and passed positionally; the rest stayed in db_kwargs.
        assert call_record["uri_positional"] == "quack://h:1"
        assert call_record["db_kwargs"] == {"adbc.quack.token": "t"}
        assert "uri" not in (call_record["db_kwargs"] or {})

    def test_family_a_prime_keyword_only_required_uri_passes_by_name(self) -> None:
        """
        Required keyword-only `uri` — pop and pass by name (not positionally).

        Hypothetical driver: ``def connect(*, uri, db_kwargs=None)``. Passing `uri`
        positionally would raise `TypeError: connect() takes 0 positional arguments`.
        The dispatcher detects `kind is KEYWORD_ONLY` and switches to `uri=...`.
        """
        call_record: dict[str, Any] = {}

        def connect(*, uri: str, db_kwargs: dict[str, str] | None = None) -> MagicMock:
            call_record["uri_keyword"] = uri
            call_record["db_kwargs"] = db_kwargs
            return MagicMock()

        mock_mod = MagicMock()
        mock_mod.connect = connect

        with patch("importlib.import_module", return_value=mock_mod):
            create_adbc_connection(
                "",
                {"uri": "kw://h:1", "extra": "v"},
                dbapi_module="mock_keyword_only_uri",
            )

        # uri was popped and passed by name; the rest stayed in db_kwargs.
        assert call_record["uri_keyword"] == "kw://h:1"
        assert call_record["db_kwargs"] == {"extra": "v"}
        assert "uri" not in (call_record["db_kwargs"] or {})

    def test_family_a_prime_does_not_mutate_caller_kwargs(self) -> None:
        """
        Pinning the no-mutation contract: the Family A' pop must not be visible.

        The raw call path `create_pool(dbapi_module=..., db_kwargs=user_dict)` forwards
        `user_dict` through `_pool_factory` by reference, so a bare `kwargs.pop("uri")`
        inside the dispatcher would mutate the caller's dict. `create_adbc_connection`
        shallow-copies on entry to keep its input dict pristine.
        """

        def connect(uri: str, *, db_kwargs: dict[str, str] | None = None) -> MagicMock:
            return MagicMock()

        mock_mod = MagicMock()
        mock_mod.connect = connect

        caller_kwargs = {"uri": "quack://h:1", "adbc.quack.token": "t"}
        snapshot = dict(caller_kwargs)

        with patch("importlib.import_module", return_value=mock_mod):
            create_adbc_connection(
                "",
                caller_kwargs,
                dbapi_module="mock_no_mutation_check",
            )

        assert caller_kwargs == snapshot
