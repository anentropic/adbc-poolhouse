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
from adbc_poolhouse._clickhouse_config import ClickHouseConfig
from adbc_poolhouse._clickhouse_translator import translate_clickhouse
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._databricks_translator import translate_databricks
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._duckdb_translator import translate_duckdb
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._flightsql_translator import translate_flightsql
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._mssql_translator import translate_mssql
from adbc_poolhouse._mysql_config import MySQLConfig
from adbc_poolhouse._mysql_translator import translate_mysql
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._postgresql_translator import translate_postgresql
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._redshift_translator import translate_redshift
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._snowflake_translator import translate_snowflake
from adbc_poolhouse._sqlite_config import SQLiteConfig
from adbc_poolhouse._sqlite_translator import translate_sqlite
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

    def test_no_fields_empty(self) -> None:
        """PostgreSQLConfig() with no fields → empty dict (libpq uses its own env)."""
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

    def test_individual_fields_builds_uri(self) -> None:
        """Individual fields → builds a libpq URI."""
        result = translate_postgresql(
            PostgreSQLConfig(host="db.example.com", user="me", database="mydb")
        )
        assert result == {"uri": "postgresql://me@db.example.com/mydb"}

    def test_individual_fields_with_password(self) -> None:
        """Password is URL-encoded and embedded in the URI."""
        from pydantic import SecretStr

        result = translate_postgresql(
            PostgreSQLConfig(
                host="db.example.com",
                user="me",
                password=SecretStr("s3cr+t"),  # pragma: allowlist secret
                database="mydb",
            )
        )
        assert (
            result["uri"]
            == "postgresql://me:s3cr%2Bt@db.example.com/mydb"  # pragma: allowlist secret
        )

    def test_individual_fields_with_port_and_sslmode(self) -> None:
        """Port and sslmode are appended correctly."""
        result = translate_postgresql(
            PostgreSQLConfig(
                host="db.example.com",
                user="me",
                port=5433,
                database="mydb",
                sslmode="require",
            )
        )
        assert result == {"uri": "postgresql://me@db.example.com:5433/mydb?sslmode=require"}

    def test_uri_takes_precedence_over_individual_fields(self) -> None:
        """When uri is set, individual fields are ignored."""
        result = translate_postgresql(
            PostgreSQLConfig(
                uri="postgresql://override@host/db",
                host="ignored",
                user="ignored",
            )
        )
        assert result == {"uri": "postgresql://override@host/db"}


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

    def test_uri_mode_secret_extracted(self) -> None:
        """URI mode: SecretStr extracted, returned as plain string."""
        secret_uri = SecretStr("databricks://host/catalog")  # pragma: allowlist secret
        result = translate_databricks(DatabricksConfig(uri=secret_uri))
        assert result == {"uri": "databricks://host/catalog"}

    def test_decomposed_fields_url_encoded_token(self) -> None:
        """Decomposed mode: token with special chars is percent-encoded."""
        config = DatabricksConfig(
            host="host",
            http_path="/sql/1.0/warehouses/abc",
            token=SecretStr("dapi+test=value/path"),  # pragma: allowlist secret
        )
        result = translate_databricks(config)
        expected = "databricks://token:dapi%2Btest%3Dvalue%2Fpath@host:443/sql/1.0/warehouses/abc"  # pragma: allowlist secret  # noqa: E501
        assert result == {"uri": expected}

    def test_decomposed_fields_plain_token(self) -> None:
        """Decomposed mode: token with no special chars passes through cleanly."""
        config = DatabricksConfig(
            host="adb-xxx.azuredatabricks.net",
            http_path="/sql/1.0/warehouses/abc123",
            token=SecretStr("dapitoken"),  # pragma: allowlist secret
        )
        result = translate_databricks(config)
        expected = "databricks://token:dapitoken@adb-xxx.azuredatabricks.net:443/sql/1.0/warehouses/abc123"  # pragma: allowlist secret  # noqa: E501
        assert result == {"uri": expected}

    def test_no_args_raises_validation_error(self) -> None:
        """DatabricksConfig() with no args raises ValidationError; silent empty dict path closed."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DatabricksConfig()


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

    def test_individual_fields_builds_redshift_uri(self) -> None:
        """Individual fields → builds a redshift:// URI."""
        result = translate_redshift(
            RedshiftConfig(host="rs.example.com", user="admin", database="analytics")
        )
        assert result == {"uri": "redshift://admin@rs.example.com/analytics"}

    def test_password_url_encoded(self) -> None:
        """Password with special chars is URL-encoded in the URI."""
        result = translate_redshift(
            RedshiftConfig(
                host="rs.example.com",
                user="admin",
                password=SecretStr("p+a=b/c"),  # pragma: allowlist secret
                database="analytics",
            )
        )
        assert result["uri"] == (
            "redshift://admin:p%2Ba%3Db%2Fc@rs.example.com/analytics"  # pragma: allowlist secret
        )

    def test_iam_fields_included_as_separate_kwargs(self) -> None:
        """IAM/cluster fields appear as separate kwargs alongside uri."""
        result = translate_redshift(
            RedshiftConfig(
                uri="redshift://host:5439/mydb",
                cluster_type="redshift-iam",
                cluster_identifier="my-cluster",
                aws_region="us-east-1",
            )
        )
        assert result["uri"] == "redshift://host:5439/mydb"
        assert result["redshift.cluster_type"] == "redshift-iam"
        assert result["redshift.cluster_identifier"] == "my-cluster"
        assert result["aws_region"] == "us-east-1"

    def test_uri_takes_precedence_over_individual_fields(self) -> None:
        """When uri is set, individual fields are not used to build URI."""
        result = translate_redshift(
            RedshiftConfig(
                uri="redshift://override@host/db",
                host="ignored",
                user="ignored",
            )
        )
        assert result["uri"] == "redshift://override@host/db"

    def test_aws_secret_access_key_extracted(self) -> None:
        """aws_secret_access_key SecretStr value is extracted via get_secret_value()."""
        result = translate_redshift(
            RedshiftConfig(
                aws_secret_access_key=SecretStr("mysecretkey"),  # pragma: allowlist secret
            )
        )
        assert result["aws_secret_access_key"] == "mysecretkey"  # pragma: allowlist secret


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

    def test_bigquery_dispatch(self) -> None:
        """translate_config() dispatches BigQueryConfig to translate_bigquery()."""
        config = BigQueryConfig()
        assert translate_config(config) == translate_bigquery(config)

    def test_postgresql_dispatch(self) -> None:
        """translate_config() dispatches PostgreSQLConfig to translate_postgresql()."""
        config = PostgreSQLConfig()
        assert translate_config(config) == translate_postgresql(config)

    def test_flightsql_dispatch(self) -> None:
        """translate_config() dispatches FlightSQLConfig to translate_flightsql()."""
        config = FlightSQLConfig()
        assert translate_config(config) == translate_flightsql(config)

    def test_databricks_dispatch(self) -> None:
        """translate_config() dispatches DatabricksConfig to translate_databricks()."""
        config = DatabricksConfig(
            uri=SecretStr("databricks://token:dapi@host:443/wh/abc")  # pragma: allowlist secret
        )
        assert translate_config(config) == translate_databricks(config)

    def test_redshift_dispatch(self) -> None:
        """translate_config() dispatches RedshiftConfig to translate_redshift()."""
        config = RedshiftConfig()
        assert translate_config(config) == translate_redshift(config)

    def test_trino_dispatch(self) -> None:
        """translate_config() dispatches TrinoConfig to translate_trino()."""
        config = TrinoConfig()
        assert translate_config(config) == translate_trino(config)

    def test_mssql_dispatch(self) -> None:
        """translate_config() dispatches MSSQLConfig to translate_mssql()."""
        config = MSSQLConfig()
        assert translate_config(config) == translate_mssql(config)

    def test_mysql_dispatch(self) -> None:
        """translate_config() dispatches MySQLConfig to translate_mysql()."""
        config = MySQLConfig(host="h", user="u", database="db")
        assert translate_config(config) == translate_mysql(config)

    def test_sqlite_dispatch(self) -> None:
        """translate_config() dispatches SQLiteConfig to translate_sqlite()."""
        config = SQLiteConfig()
        assert translate_config(config) == translate_sqlite(config)

    def test_unsupported_type_raises_type_error(self) -> None:
        """translate_config() with unknown type raises TypeError."""
        with pytest.raises(TypeError, match="Unsupported config type"):
            translate_config("not a config")  # type: ignore[arg-type]


class TestMySQLTranslator:
    """Unit tests for translate_mysql()."""

    def test_uri_mode_secret_extracted(self) -> None:
        """URI mode returns SecretStr value directly in {'uri': ...}."""
        config = MySQLConfig(uri=SecretStr("mysql://user:pass@host/db"))  # pragma: allowlist secret
        result = translate_mysql(config)
        assert result == {"uri": "mysql://user:pass@host/db"}  # pragma: allowlist secret

    def test_decomposed_with_password(self) -> None:
        """Decomposed mode produces Go DSN user:pass@tcp(host:port)/db."""
        config = MySQLConfig(
            host="localhost",
            user="root",
            password=SecretStr("my-secret-pw"),  # pragma: allowlist secret
            database="demo",
        )
        result = translate_mysql(config)
        expected = "root:my-secret-pw@tcp(localhost:3306)/demo"  # pragma: allowlist secret
        assert result == {"uri": expected}

    def test_decomposed_without_password(self) -> None:
        """Decomposed mode without password omits :pass segment entirely."""
        config = MySQLConfig(host="localhost", user="root", database="demo")
        result = translate_mysql(config)
        assert result == {"uri": "root@tcp(localhost:3306)/demo"}

    def test_special_chars_in_password_are_percent_encoded(self) -> None:
        """Special chars in password are percent-encoded via quote(safe='')."""
        config = MySQLConfig(
            host="h",
            user="u",
            password=SecretStr("p+a=b/c"),  # pragma: allowlist secret
            database="db",
        )
        result = translate_mysql(config)
        assert "p%2Ba%3Db%2Fc" in result["uri"]

    def test_custom_port_appears_in_uri(self) -> None:
        """Non-default port appears in tcp(host:port) segment."""
        config = MySQLConfig(host="host", user="user", database="db", port=5306)
        result = translate_mysql(config)
        assert "tcp(host:5306)" in result["uri"]

    def test_output_has_only_uri_key(self) -> None:
        """translate_mysql() always returns exactly one key ('uri')."""
        config = MySQLConfig(host="h", user="u", database="db")
        result = translate_mysql(config)
        assert list(result.keys()) == ["uri"]


class TestSQLiteTranslator:
    """Unit tests for translate_sqlite()."""

    def test_memory_database(self) -> None:
        """SQLiteConfig() uses ':memory:' by default — maps to 'uri' key."""
        result = translate_sqlite(SQLiteConfig())
        assert result == {"uri": ":memory:"}

    def test_file_database(self) -> None:
        """SQLiteConfig(database=...) maps database attribute to 'uri' key."""
        result = translate_sqlite(SQLiteConfig(database="/data/x.db"))
        assert result == {"uri": "/data/x.db"}

    def test_output_has_only_uri_key(self) -> None:
        """translate_sqlite() returns exactly one key ('uri')."""
        result = translate_sqlite(SQLiteConfig())
        assert list(result.keys()) == ["uri"]


class TestClickHouseTranslator:
    """Unit tests for translate_clickhouse()."""

    def test_uri_mode_secret_extracted(self) -> None:
        """URI mode returns SecretStr value directly in {'uri': ...}."""
        config = ClickHouseConfig(
            uri=SecretStr("http://user:pass@localhost:8123/db")  # pragma: allowlist secret
        )
        result = translate_clickhouse(config)
        assert result == {"uri": "http://user:pass@localhost:8123/db"}  # pragma: allowlist secret

    def test_decomposed_minimum(self) -> None:
        """Decomposed minimum: host and username → three-key dict with port as string."""
        config = ClickHouseConfig(host="localhost", username="default")
        result = translate_clickhouse(config)
        assert result == {"username": "default", "host": "localhost", "port": "8123"}

    def test_decomposed_full(self) -> None:
        """Full decomposed mode includes password and database."""
        config = ClickHouseConfig(
            host="localhost",
            username="default",
            password=SecretStr("secret"),  # pragma: allowlist secret
            database="mydb",
        )
        result = translate_clickhouse(config)
        assert result == {
            "username": "default",
            "host": "localhost",
            "port": "8123",
            "password": "secret",  # pragma: allowlist secret
            "database": "mydb",
        }

    def test_port_is_string(self) -> None:
        """Port is always str(config.port) — dict[str, str] contract."""
        config = ClickHouseConfig(host="h", username="u")
        result = translate_clickhouse(config)
        assert result["port"] == "8123"
        assert isinstance(result["port"], str)

    def test_custom_port_as_string(self) -> None:
        """Non-default port appears as string in output."""
        config = ClickHouseConfig(host="h", username="u", port=8443)
        result = translate_clickhouse(config)
        assert result["port"] == "8443"

    def test_password_omitted_when_none(self) -> None:
        """Password key is absent from result when password is None."""
        config = ClickHouseConfig(host="h", username="u")
        result = translate_clickhouse(config)
        assert "password" not in result  # pragma: allowlist secret

    def test_database_omitted_when_none(self) -> None:
        """Database key is absent from result when database is None."""
        config = ClickHouseConfig(host="h", username="u")
        result = translate_clickhouse(config)
        assert "database" not in result

    def test_username_key_not_user(self) -> None:
        """Output dict uses 'username' key, not 'user' — critical for silent auth failure."""
        config = ClickHouseConfig(host="h", username="default")
        result = translate_clickhouse(config)
        assert "username" in result
        assert "user" not in result

    def test_decomposed_mode_does_not_build_uri(self) -> None:
        """Decomposed mode returns individual kwargs — no 'uri' key, unlike MySQL."""
        config = ClickHouseConfig(host="h", username="u")
        result = translate_clickhouse(config)
        assert "uri" not in result

    def test_uri_mode_returns_only_uri_key(self) -> None:
        """URI mode returns exactly one key ('uri')."""
        config = ClickHouseConfig(
            uri=SecretStr("http://user:pass@h:8123/db")  # pragma: allowlist secret
        )
        result = translate_clickhouse(config)
        assert list(result.keys()) == ["uri"]
