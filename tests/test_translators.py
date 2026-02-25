"""
Unit tests for all 10 warehouse parameter translator functions (TEST-05).

Tests assert exact dict[str, str] output for given config inputs.
Translators are pure functions — no mocking needed, no ADBC driver installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

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
from adbc_poolhouse._translators import translate_config
from adbc_poolhouse._trino_config import TrinoConfig
from adbc_poolhouse._trino_translator import translate_trino


class TestDuckDBTranslator:
    """Unit tests for translate_duckdb()."""

    def test_memory_database(self) -> None:
        """DuckDBConfig() uses ':memory:' by default — maps to path key."""
        result = translate_duckdb(DuckDBConfig())
        assert result == {"path": ":memory:"}

    def test_file_database(self) -> None:
        """DuckDBConfig(database=...) maps database attribute to 'path' key."""
        result = translate_duckdb(DuckDBConfig(database="/tmp/test.db"))
        assert result == {"path": "/tmp/test.db"}

    def test_read_only(self) -> None:
        """read_only=True adds 'access_mode' = 'READ_ONLY' to output dict."""
        result = translate_duckdb(DuckDBConfig(database="/tmp/test.db", read_only=True))
        assert result == {"path": "/tmp/test.db", "access_mode": "READ_ONLY"}

    def test_read_only_false_omitted(self) -> None:
        """read_only=False (default) does not emit 'access_mode' key."""
        result = translate_duckdb(DuckDBConfig(database="/tmp/test.db", read_only=False))
        assert "access_mode" not in result


class TestSnowflakeTranslator:
    """Unit tests for translate_snowflake()."""

    def test_account_only(self) -> None:
        """SnowflakeConfig with only account set — no 'username' key in output."""
        result = translate_snowflake(SnowflakeConfig(account="myorg-myaccount"))
        assert result["adbc.snowflake.sql.account"] == "myorg-myaccount"
        assert "username" not in result
        assert "password" not in result  # pragma: allowlist secret

    def test_user_and_password(self) -> None:
        """SnowflakeConfig with user+password — both appear as plain string keys."""
        secret = SecretStr("s3cr3t")  # pragma: allowlist secret
        result = translate_snowflake(SnowflakeConfig(account="a", user="bob", password=secret))
        assert result["username"] == "bob"
        assert result["password"] == "s3cr3t"  # pragma: allowlist secret

    def test_schema_mapping(self) -> None:
        """
        schema_ Python attribute maps to ADBC key without trailing underscore.

        SnowflakeConfig.schema_ has validation_alias='schema' — must be passed
        via keyword dict to avoid Python keyword conflict.
        """
        result = translate_snowflake(
            SnowflakeConfig.model_validate({"account": "a", "schema": "PUBLIC"})
        )
        assert result["adbc.snowflake.sql.schema"] == "PUBLIC"

    def test_bool_defaults_as_strings(self) -> None:
        """Default boolean flags always appear as 'true'/'false' strings."""
        result = translate_snowflake(SnowflakeConfig(account="a"))
        # tls_skip_verify defaults to False → 'false'
        assert result["adbc.snowflake.sql.client_option.tls_skip_verify"] == "false"
        # ocsp_fail_open_mode defaults to True → 'true'
        assert result["adbc.snowflake.sql.client_option.ocsp_fail_open_mode"] == "true"

    def test_private_key_path(self) -> None:
        """private_key_path set → maps to jwt_private_key ADBC key as str."""
        key_path = Path("/tmp/key.pem")
        result = translate_snowflake(SnowflakeConfig(account="a", private_key_path=key_path))
        assert result["adbc.snowflake.sql.client_option.jwt_private_key"] == "/tmp/key.pem"


class TestBigQueryTranslator:
    """Unit tests for translate_bigquery()."""

    def test_all_optional_empty(self) -> None:
        """BigQueryConfig() with no args → empty dict (all fields optional)."""
        result = translate_bigquery(BigQueryConfig())
        assert result == {}

    def test_project_id(self) -> None:
        """project_id set → maps to 'adbc.bigquery.sql.project_id' key."""
        result = translate_bigquery(BigQueryConfig(project_id="my-proj"))
        assert result == {"adbc.bigquery.sql.project_id": "my-proj"}

    def test_auth_type(self) -> None:
        """auth_type set → maps to 'adbc.bigquery.sql.auth_type' key."""
        result = translate_bigquery(BigQueryConfig(auth_type="SERVICE_ACCOUNT"))
        assert result == {"adbc.bigquery.sql.auth_type": "SERVICE_ACCOUNT"}


class TestPostgreSQLTranslator:
    """Unit tests for translate_postgresql()."""

    def test_no_uri_empty(self) -> None:
        """PostgreSQLConfig() with no uri → empty dict."""
        result = translate_postgresql(PostgreSQLConfig())
        assert result == {}

    def test_uri_passthrough(self) -> None:
        """Uri set → maps to 'uri' key; use_copy is intentionally absent."""
        result = translate_postgresql(PostgreSQLConfig(uri="postgresql://localhost/mydb"))
        assert result == {"uri": "postgresql://localhost/mydb"}

    def test_use_copy_not_in_output(self) -> None:
        """
        use_copy is a StatementOptions key (per-statement), not a connect kwarg.

        'adbc.postgresql.use_copy' must NOT appear in the translator output.
        Phase 5 handles it at cursor level if needed.
        """
        result = translate_postgresql(PostgreSQLConfig(uri="postgresql://localhost/mydb"))
        assert "adbc.postgresql.use_copy" not in result
        assert "use_copy" not in result


class TestFlightSQLTranslator:
    """Unit tests for translate_flightsql()."""

    def test_no_uri_returns_bool_defaults(self) -> None:
        """
        FlightSQLConfig() with no args returns dict with only boolean defaults.

        tls_skip_verify and with_cookie_middleware are bool fields with defaults
        — always emitted as 'true'/'false' strings.
        """
        result = translate_flightsql(FlightSQLConfig())
        assert result == {
            "adbc.flight.sql.client_option.tls_skip_verify": "false",
            "adbc.flight.sql.rpc.with_cookie_middleware": "false",
        }

    def test_uri_included(self) -> None:
        """Uri set → maps to 'uri' key in output."""
        result = translate_flightsql(FlightSQLConfig(uri="grpc://localhost:32010"))
        assert result["uri"] == "grpc://localhost:32010"

    def test_tls_skip_verify_true(self) -> None:
        """tls_skip_verify=True → 'adbc.flight.sql.client_option.tls_skip_verify' = 'true'."""
        result = translate_flightsql(FlightSQLConfig(tls_skip_verify=True))
        assert result["adbc.flight.sql.client_option.tls_skip_verify"] == "true"


class TestDatabricksTranslator:
    """Unit tests for translate_databricks()."""

    def test_no_uri_empty(self) -> None:
        """DatabricksConfig() with no uri → empty dict."""
        result = translate_databricks(DatabricksConfig())
        assert result == {}

    def test_uri_secret_extracted(self) -> None:
        """Uri is SecretStr — get_secret_value() is called, plain string in output."""
        secret_uri = SecretStr("databricks://host/catalog")  # pragma: allowlist secret
        result = translate_databricks(DatabricksConfig(uri=secret_uri))
        assert result == {"uri": "databricks://host/catalog"}


class TestRedshiftTranslator:
    """Unit tests for translate_redshift()."""

    def test_no_uri_empty(self) -> None:
        """RedshiftConfig() with no uri → empty dict."""
        result = translate_redshift(RedshiftConfig())
        assert result == {}

    def test_uri_passthrough(self) -> None:
        """Uri set → maps to 'uri' key in output."""
        result = translate_redshift(RedshiftConfig(uri="redshift://host:5439/mydb"))
        assert result == {"uri": "redshift://host:5439/mydb"}


class TestTrinoTranslator:
    """
    Unit tests for translate_trino().

    Note: Trino ADBC key names are LOW confidence — triangulated from
    non-authoritative sources. See _trino_translator.py comments.
    """

    def test_no_uri_uses_decomposed_fields(self) -> None:
        """TrinoConfig() with no uri → decomposed field mode; bool defaults included."""
        result = translate_trino(TrinoConfig())
        # ssl and ssl_verify default to True → 'true'/'true' strings
        assert result["ssl"] == "true"
        assert result["ssl_verify"] == "true"
        # No uri key
        assert "uri" not in result

    def test_uri_takes_precedence(self) -> None:
        """Uri set → URI-first: returns only {'uri': ...}, ignores other fields."""
        result = translate_trino(TrinoConfig(uri="trino://user@host:8080/catalog"))
        assert result == {"uri": "trino://user@host:8080/catalog"}

    def test_host_and_catalog(self) -> None:
        """Host and catalog in decomposed mode → appear under LOW confidence keys."""
        result = translate_trino(TrinoConfig(host="trino-host", catalog="my_catalog"))
        assert result["host"] == "trino-host"
        assert result["catalog"] == "my_catalog"


class TestMSSQLTranslator:
    """
    Unit tests for translate_mssql().

    Note: MSSQL ADBC key names are LOW confidence — triangulated from
    non-authoritative sources. See _mssql_translator.py comments.
    """

    def test_no_uri_uses_decomposed_fields(self) -> None:
        """MSSQLConfig() with no uri → decomposed mode; trust_server_certificate always included."""
        result = translate_mssql(MSSQLConfig())
        # trust_server_certificate defaults to False → always emitted
        assert result["trustServerCertificate"] == "false"
        assert "uri" not in result

    def test_uri_takes_precedence(self) -> None:
        """Uri set → URI-first: returns only {'uri': ...}, ignores decomposed fields."""
        result = translate_mssql(MSSQLConfig(uri="mssql://host/db"))
        assert result == {"uri": "mssql://host/db"}


class TestTranslateConfig:
    """Unit tests for translate_config() dispatch coordinator."""

    def test_duckdb_dispatch(self) -> None:
        """translate_config() dispatches DuckDBConfig to translate_duckdb()."""
        config = DuckDBConfig()
        assert translate_config(config) == translate_duckdb(config)

    def test_snowflake_dispatch(self) -> None:
        """translate_config() dispatches SnowflakeConfig to translate_snowflake()."""
        config = SnowflakeConfig(account="a")
        assert translate_config(config) == translate_snowflake(config)

    def test_unsupported_type_raises_type_error(self) -> None:
        """translate_config() with unknown type raises TypeError."""
        with pytest.raises(TypeError, match="Unsupported config type"):
            translate_config("not a config")  # type: ignore[arg-type]
