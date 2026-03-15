"""
Unit tests for config ``to_adbc_kwargs()`` methods (TEST-05).

Tests assert exact ``dict[str, str]`` output for given config inputs.
Config models are pure data objects -- no mocking needed, no ADBC driver installed.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

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


class TestDuckDBToAdbcKwargs:
    """Unit tests for DuckDBConfig.to_adbc_kwargs() method."""

    def test_memory_database(self) -> None:
        """DuckDBConfig().to_adbc_kwargs() uses ':memory:' by default — maps to path key."""
        result = DuckDBConfig().to_adbc_kwargs()
        assert result == {"path": ":memory:"}

    def test_file_database(self) -> None:
        """DuckDBConfig(database=...).to_adbc_kwargs() maps database to 'path' key."""
        result = DuckDBConfig(database="/tmp/test.db").to_adbc_kwargs()
        assert result == {"path": "/tmp/test.db"}

    def test_read_only(self) -> None:
        """read_only=True adds 'access_mode' = 'READ_ONLY' via to_adbc_kwargs()."""
        result = DuckDBConfig(database="/tmp/test.db", read_only=True).to_adbc_kwargs()
        assert result == {"path": "/tmp/test.db", "access_mode": "READ_ONLY"}

    def test_read_only_false_omitted(self) -> None:
        """read_only=False (default) does not emit 'access_mode' via to_adbc_kwargs()."""
        result = DuckDBConfig(database="/tmp/test.db", read_only=False).to_adbc_kwargs()
        assert "access_mode" not in result

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields (pool_size, max_overflow, timeout, recycle) excluded."""
        result = DuckDBConfig().to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestSnowflakeToAdbcKwargs:
    """Unit tests for SnowflakeConfig.to_adbc_kwargs() method."""

    def test_account_only(self) -> None:
        """SnowflakeConfig.to_adbc_kwargs() with only account set."""
        result = SnowflakeConfig(account="myorg-myaccount").to_adbc_kwargs()
        assert result["adbc.snowflake.sql.account"] == "myorg-myaccount"
        assert "username" not in result
        assert "password" not in result  # pragma: allowlist secret

    def test_user_and_password(self) -> None:
        """SnowflakeConfig.to_adbc_kwargs() with user+password."""
        secret = SecretStr("s3cr3t")  # pragma: allowlist secret
        result = SnowflakeConfig(account="a", user="bob", password=secret).to_adbc_kwargs()
        assert result["username"] == "bob"
        assert result["password"] == "s3cr3t"  # pragma: allowlist secret

    def test_schema_mapping(self) -> None:
        """schema_ Python attribute maps to ADBC key via to_adbc_kwargs()."""
        config = SnowflakeConfig.model_validate({"account": "a", "schema": "PUBLIC"})
        result = config.to_adbc_kwargs()
        assert result["adbc.snowflake.sql.schema"] == "PUBLIC"

    def test_bool_defaults_as_strings(self) -> None:
        """Default boolean flags always appear as 'true'/'false' strings via to_adbc_kwargs()."""
        result = SnowflakeConfig(account="a").to_adbc_kwargs()
        assert result["adbc.snowflake.sql.client_option.tls_skip_verify"] == "false"
        assert result["adbc.snowflake.sql.client_option.ocsp_fail_open_mode"] == "true"

    def test_private_key_path(self) -> None:
        """private_key_path maps to jwt_private_key ADBC key via to_adbc_kwargs()."""
        key_path = Path("/tmp/key.pem")
        result = SnowflakeConfig(account="a", private_key_path=key_path).to_adbc_kwargs()
        assert result["adbc.snowflake.sql.client_option.jwt_private_key"] == "/tmp/key.pem"

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields (pool_size, max_overflow, timeout, recycle) excluded."""
        result = SnowflakeConfig(account="a").to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result

    def test_oauth_token(self) -> None:
        """oauth_token SecretStr extracted via to_adbc_kwargs()."""
        config = SnowflakeConfig(
            account="a",
            auth_type="auth_oauth",
            oauth_token=SecretStr("tok"),  # pragma: allowlist secret
        )
        result = config.to_adbc_kwargs()
        assert result["adbc.snowflake.sql.client_option.auth_token"] == "tok"


class TestBigQueryToAdbcKwargs:
    """Unit tests for BigQueryConfig.to_adbc_kwargs() method."""

    def test_all_optional_empty(self) -> None:
        """BigQueryConfig().to_adbc_kwargs() with no args returns empty dict."""
        result = BigQueryConfig().to_adbc_kwargs()
        assert result == {}

    def test_project_id(self) -> None:
        """project_id maps to 'adbc.bigquery.sql.project_id' via to_adbc_kwargs()."""
        result = BigQueryConfig(project_id="my-proj").to_adbc_kwargs()
        assert result == {"adbc.bigquery.sql.project_id": "my-proj"}

    def test_auth_type(self) -> None:
        """auth_type maps to 'adbc.bigquery.sql.auth_type' via to_adbc_kwargs()."""
        result = BigQueryConfig(auth_type="SERVICE_ACCOUNT").to_adbc_kwargs()
        assert result == {"adbc.bigquery.sql.auth_type": "SERVICE_ACCOUNT"}

    def test_auth_credentials_secret_extracted(self) -> None:
        """auth_credentials SecretStr extracted via to_adbc_kwargs()."""
        config = BigQueryConfig(
            auth_credentials=SecretStr("/path/to/creds.json"),
        )
        result = config.to_adbc_kwargs()
        assert result["adbc.bigquery.sql.auth_credentials"] == "/path/to/creds.json"

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        result = BigQueryConfig().to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestPostgreSQLToAdbcKwargs:
    """Unit tests for PostgreSQLConfig.to_adbc_kwargs() method."""

    def test_no_fields_empty(self) -> None:
        """PostgreSQLConfig().to_adbc_kwargs() with no fields returns empty dict."""
        result = PostgreSQLConfig().to_adbc_kwargs()
        assert result == {}

    def test_uri_passthrough(self) -> None:
        """Uri set via to_adbc_kwargs() maps to 'uri' key."""
        result = PostgreSQLConfig(uri="postgresql://localhost/mydb").to_adbc_kwargs()
        assert result == {"uri": "postgresql://localhost/mydb"}

    def test_use_copy_not_in_output(self) -> None:
        """use_copy is a StatementOptions key, not a connect kwarg."""
        result = PostgreSQLConfig(uri="postgresql://localhost/mydb").to_adbc_kwargs()
        assert "adbc.postgresql.use_copy" not in result
        assert "use_copy" not in result

    def test_individual_fields_builds_uri(self) -> None:
        """Individual fields via to_adbc_kwargs() builds a libpq URI."""
        result = PostgreSQLConfig(
            host="db.example.com", user="me", database="mydb"
        ).to_adbc_kwargs()
        assert result == {"uri": "postgresql://me@db.example.com/mydb"}

    def test_individual_fields_with_password(self) -> None:
        """Password is URL-encoded and embedded in the URI via to_adbc_kwargs()."""
        result = PostgreSQLConfig(
            host="db.example.com",
            user="me",
            password=SecretStr("s3cr+t"),  # pragma: allowlist secret
            database="mydb",
        ).to_adbc_kwargs()
        assert (
            result["uri"]
            == "postgresql://me:s3cr%2Bt@db.example.com/mydb"  # pragma: allowlist secret
        )

    def test_individual_fields_with_port_and_sslmode(self) -> None:
        """Port and sslmode appended correctly via to_adbc_kwargs()."""
        result = PostgreSQLConfig(
            host="db.example.com",
            user="me",
            port=5433,
            database="mydb",
            sslmode="require",
        ).to_adbc_kwargs()
        assert result == {"uri": "postgresql://me@db.example.com:5433/mydb?sslmode=require"}

    def test_uri_takes_precedence_over_individual_fields(self) -> None:
        """When uri is set, individual fields are ignored via to_adbc_kwargs()."""
        result = PostgreSQLConfig(
            uri="postgresql://override@host/db",
            host="ignored",
            user="ignored",
        ).to_adbc_kwargs()
        assert result == {"uri": "postgresql://override@host/db"}

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        result = PostgreSQLConfig().to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestFlightSQLToAdbcKwargs:
    """Unit tests for FlightSQLConfig.to_adbc_kwargs() method."""

    def test_no_uri_returns_bool_defaults(self) -> None:
        """FlightSQLConfig().to_adbc_kwargs() with no args returns only boolean defaults."""
        result = FlightSQLConfig().to_adbc_kwargs()
        assert result == {
            "adbc.flight.sql.client_option.tls_skip_verify": "false",
            "adbc.flight.sql.rpc.with_cookie_middleware": "false",
        }

    def test_uri_included(self) -> None:
        """Uri set via to_adbc_kwargs() maps to 'uri' key in output."""
        result = FlightSQLConfig(uri="grpc://localhost:32010").to_adbc_kwargs()
        assert result["uri"] == "grpc://localhost:32010"

    def test_tls_skip_verify_true(self) -> None:
        """tls_skip_verify=True via to_adbc_kwargs()."""
        result = FlightSQLConfig(tls_skip_verify=True).to_adbc_kwargs()
        assert result["adbc.flight.sql.client_option.tls_skip_verify"] == "true"

    def test_username_and_password(self) -> None:
        """Username and password are included via to_adbc_kwargs()."""
        result = FlightSQLConfig(
            username="user",
            password=SecretStr("pass"),  # pragma: allowlist secret
        ).to_adbc_kwargs()
        assert result["username"] == "user"
        assert result["password"] == "pass"  # pragma: allowlist secret

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        result = FlightSQLConfig().to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result

    def test_all_optional_fields(self) -> None:
        """All optional fields are included when set via to_adbc_kwargs()."""
        config = FlightSQLConfig(
            uri="grpc://host:443",
            username="user",
            password=SecretStr("pw"),  # pragma: allowlist secret
            authorization_header=SecretStr("Bearer tok"),  # pragma: allowlist secret
            mtls_cert_chain="cert-pem",
            mtls_private_key=SecretStr("key-pem"),  # pragma: allowlist secret
            tls_root_certs="root-ca",
            tls_skip_verify=True,
            tls_override_hostname="override-host",
            connect_timeout=10.0,
            query_timeout=30.0,
            fetch_timeout=60.0,
            update_timeout=120.0,
            authority="authority-value",
            max_msg_size=1024,
            with_cookie_middleware=True,
        )
        result = config.to_adbc_kwargs()
        assert result["uri"] == "grpc://host:443"
        assert result["username"] == "user"
        assert result["password"] == "pw"  # pragma: allowlist secret
        assert result["adbc.flight.sql.authorization_header"] == "Bearer tok"
        assert result["adbc.flight.sql.client_option.mtls_cert_chain"] == "cert-pem"
        assert (
            result["adbc.flight.sql.client_option.mtls_private_key"]  # pragma: allowlist secret
            == "key-pem"
        )
        assert result["adbc.flight.sql.client_option.tls_root_certs"] == "root-ca"
        assert result["adbc.flight.sql.client_option.tls_skip_verify"] == "true"
        assert result["adbc.flight.sql.client_option.tls_override_hostname"] == "override-host"
        assert result["adbc.flight.sql.rpc.timeout_seconds.fetch"] == "60.0"
        assert result["adbc.flight.sql.rpc.timeout_seconds.query"] == "30.0"
        assert result["adbc.flight.sql.rpc.timeout_seconds.update"] == "120.0"
        assert result["adbc.flight.sql.rpc.with_cookie_middleware"] == "true"


class TestDatabricksToAdbcKwargs:
    """Unit tests for DatabricksConfig.to_adbc_kwargs() method."""

    def test_uri_mode_secret_extracted(self) -> None:
        """URI mode extracts SecretStr value via to_adbc_kwargs()."""
        secret_uri = SecretStr("databricks://host/catalog")  # pragma: allowlist secret
        result = DatabricksConfig(uri=secret_uri).to_adbc_kwargs()
        assert result == {"uri": "databricks://host/catalog"}

    def test_decomposed_fields_url_encoded_token(self) -> None:
        """Decomposed mode: token with special chars percent-encoded via to_adbc_kwargs()."""
        config = DatabricksConfig(
            host="host",
            http_path="/sql/1.0/warehouses/abc",
            token=SecretStr("dapi+test=value/path"),  # pragma: allowlist secret
        )
        result = config.to_adbc_kwargs()
        expected = "databricks://token:dapi%2Btest%3Dvalue%2Fpath@host:443/sql/1.0/warehouses/abc"  # pragma: allowlist secret  # noqa: E501
        assert result == {"uri": expected}

    def test_decomposed_fields_plain_token(self) -> None:
        """Decomposed mode: plain token passes through via to_adbc_kwargs()."""
        config = DatabricksConfig(
            host="adb-xxx.azuredatabricks.net",
            http_path="/sql/1.0/warehouses/abc123",
            token=SecretStr("dapitoken"),  # pragma: allowlist secret
        )
        result = config.to_adbc_kwargs()
        expected = "databricks://token:dapitoken@adb-xxx.azuredatabricks.net:443/sql/1.0/warehouses/abc123"  # pragma: allowlist secret  # noqa: E501
        assert result == {"uri": expected}

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        config = DatabricksConfig(
            uri=SecretStr("databricks://host/catalog")  # pragma: allowlist secret
        )
        result = config.to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestRedshiftToAdbcKwargs:
    """Unit tests for RedshiftConfig.to_adbc_kwargs() method."""

    def test_no_uri_empty(self) -> None:
        """RedshiftConfig().to_adbc_kwargs() with no fields returns empty dict."""
        result = RedshiftConfig().to_adbc_kwargs()
        assert result == {}

    def test_uri_passthrough(self) -> None:
        """Uri set via to_adbc_kwargs() maps to 'uri' key."""
        result = RedshiftConfig(uri="redshift://host:5439/mydb").to_adbc_kwargs()
        assert result == {"uri": "redshift://host:5439/mydb"}

    def test_individual_fields_builds_redshift_uri(self) -> None:
        """Individual fields via to_adbc_kwargs() builds a redshift:// URI."""
        result = RedshiftConfig(
            host="rs.example.com", user="admin", database="analytics"
        ).to_adbc_kwargs()
        assert result == {"uri": "redshift://admin@rs.example.com/analytics"}

    def test_password_url_encoded(self) -> None:
        """Password with special chars URL-encoded via to_adbc_kwargs()."""
        result = RedshiftConfig(
            host="rs.example.com",
            user="admin",
            password=SecretStr("p+a=b/c"),  # pragma: allowlist secret
            database="analytics",
        ).to_adbc_kwargs()
        assert result["uri"] == (
            "redshift://admin:p%2Ba%3Db%2Fc@rs.example.com/analytics"  # pragma: allowlist secret
        )

    def test_iam_fields_included_as_separate_kwargs(self) -> None:
        """IAM/cluster fields as separate kwargs via to_adbc_kwargs()."""
        result = RedshiftConfig(
            uri="redshift://host:5439/mydb",
            cluster_type="redshift-iam",
            cluster_identifier="my-cluster",
            aws_region="us-east-1",
        ).to_adbc_kwargs()
        assert result["uri"] == "redshift://host:5439/mydb"
        assert result["redshift.cluster_type"] == "redshift-iam"
        assert result["redshift.cluster_identifier"] == "my-cluster"
        assert result["aws_region"] == "us-east-1"

    def test_uri_takes_precedence_over_individual_fields(self) -> None:
        """When uri is set, individual fields ignored via to_adbc_kwargs()."""
        result = RedshiftConfig(
            uri="redshift://override@host/db",
            host="ignored",
            user="ignored",
        ).to_adbc_kwargs()
        assert result["uri"] == "redshift://override@host/db"

    def test_aws_secret_access_key_extracted(self) -> None:
        """aws_secret_access_key SecretStr extracted via to_adbc_kwargs()."""
        result = RedshiftConfig(
            aws_secret_access_key=SecretStr("mysecretkey"),  # pragma: allowlist secret
        ).to_adbc_kwargs()
        assert result["aws_secret_access_key"] == "mysecretkey"  # pragma: allowlist secret

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        result = RedshiftConfig().to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestTrinoToAdbcKwargs:
    """Unit tests for TrinoConfig.to_adbc_kwargs() method."""

    def test_no_uri_uses_decomposed_fields(self) -> None:
        """TrinoConfig().to_adbc_kwargs() with no uri returns ssl defaults."""
        result = TrinoConfig().to_adbc_kwargs()
        assert result["ssl"] == "true"
        assert result["ssl_verify"] == "true"
        assert "uri" not in result

    def test_uri_takes_precedence(self) -> None:
        """Uri set via to_adbc_kwargs() returns only {'uri': ...}."""
        result = TrinoConfig(uri="trino://user@host:8080/catalog").to_adbc_kwargs()
        assert result == {"uri": "trino://user@host:8080/catalog"}

    def test_host_and_catalog(self) -> None:
        """Host and catalog via to_adbc_kwargs()."""
        result = TrinoConfig(host="trino-host", catalog="my_catalog").to_adbc_kwargs()
        assert result["host"] == "trino-host"
        assert result["catalog"] == "my_catalog"

    def test_ssl_false(self) -> None:
        """ssl=False via to_adbc_kwargs()."""
        result = TrinoConfig(ssl=False).to_adbc_kwargs()
        assert result["ssl"] == "false"

    def test_full_decomposed(self) -> None:
        """All decomposed fields via to_adbc_kwargs()."""
        config = TrinoConfig.model_validate(
            {
                "host": "trino-host",
                "port": 8443,
                "user": "alice",
                "password": "secret",  # pragma: allowlist secret
                "catalog": "hive",
                "schema": "default",
                "ssl": True,
                "ssl_verify": False,
                "source": "my-app",
            }
        )
        result = config.to_adbc_kwargs()
        assert result["host"] == "trino-host"
        assert result["port"] == "8443"
        assert result["username"] == "alice"
        assert result["password"] == "secret"  # pragma: allowlist secret
        assert result["catalog"] == "hive"
        assert result["schema"] == "default"
        assert result["ssl"] == "true"
        assert result["ssl_verify"] == "false"
        assert result["source"] == "my-app"

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        result = TrinoConfig().to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestMSSQLToAdbcKwargs:
    """Unit tests for MSSQLConfig.to_adbc_kwargs() method."""

    def test_no_uri_uses_decomposed_fields(self) -> None:
        """MSSQLConfig().to_adbc_kwargs() with no uri returns trust_server_certificate."""
        result = MSSQLConfig().to_adbc_kwargs()
        assert result["trustServerCertificate"] == "false"
        assert "uri" not in result

    def test_uri_takes_precedence(self) -> None:
        """Uri set via to_adbc_kwargs() returns only {'uri': ...}."""
        result = MSSQLConfig(uri="mssql://host/db").to_adbc_kwargs()
        assert result == {"uri": "mssql://host/db"}

    def test_trust_server_certificate_true(self) -> None:
        """trust_server_certificate=True via to_adbc_kwargs()."""
        result = MSSQLConfig(trust_server_certificate=True).to_adbc_kwargs()
        assert result["trustServerCertificate"] == "true"

    def test_decomposed_with_all_fields(self) -> None:
        """All decomposed fields included via to_adbc_kwargs()."""
        config = MSSQLConfig(
            host="sql-server",
            port=1433,
            instance="SQLExpress",
            user="sa",
            password=SecretStr("pw"),  # pragma: allowlist secret
            database="mydb",
            trust_server_certificate=True,
            connection_timeout=30,
            fedauth="ActiveDirectoryMsi",
        )
        result = config.to_adbc_kwargs()
        assert result["host"] == "sql-server"
        assert result["port"] == "1433"
        assert result["instance"] == "SQLExpress"
        assert result["username"] == "sa"
        assert result["password"] == "pw"  # pragma: allowlist secret
        assert result["database"] == "mydb"
        assert result["trustServerCertificate"] == "true"
        assert result["connectionTimeout"] == "30"
        assert result["fedauth"] == "ActiveDirectoryMsi"

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        result = MSSQLConfig().to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestMySQLToAdbcKwargs:
    """Unit tests for MySQLConfig.to_adbc_kwargs() method."""

    def test_uri_mode_secret_extracted(self) -> None:
        """URI mode extracts SecretStr value via to_adbc_kwargs()."""
        config = MySQLConfig(
            uri=SecretStr("mysql://user:pass@host/db")  # pragma: allowlist secret
        )
        result = config.to_adbc_kwargs()
        assert result == {"uri": "mysql://user:pass@host/db"}  # pragma: allowlist secret

    def test_decomposed_with_password(self) -> None:
        """Decomposed mode produces Go DSN via to_adbc_kwargs()."""
        config = MySQLConfig(
            host="localhost",
            user="root",
            password=SecretStr("my-secret-pw"),  # pragma: allowlist secret
            database="demo",
        )
        result = config.to_adbc_kwargs()
        expected = "root:my-secret-pw@tcp(localhost:3306)/demo"  # pragma: allowlist secret
        assert result == {"uri": expected}

    def test_decomposed_without_password(self) -> None:
        """Decomposed mode without password omits :pass via to_adbc_kwargs()."""
        config = MySQLConfig(host="localhost", user="root", database="demo")
        result = config.to_adbc_kwargs()
        assert result == {"uri": "root@tcp(localhost:3306)/demo"}

    def test_special_chars_in_password_are_percent_encoded(self) -> None:
        """Special chars in password are percent-encoded via to_adbc_kwargs()."""
        config = MySQLConfig(
            host="h",
            user="u",
            password=SecretStr("p+a=b/c"),  # pragma: allowlist secret
            database="db",
        )
        result = config.to_adbc_kwargs()
        assert "p%2Ba%3Db%2Fc" in result["uri"]

    def test_custom_port_appears_in_uri(self) -> None:
        """Non-default port appears in tcp(host:port) via to_adbc_kwargs()."""
        config = MySQLConfig(host="host", user="user", database="db", port=5306)
        result = config.to_adbc_kwargs()
        assert "tcp(host:5306)" in result["uri"]

    def test_output_has_only_uri_key(self) -> None:
        """to_adbc_kwargs() always returns exactly one key ('uri')."""
        config = MySQLConfig(host="h", user="u", database="db")
        result = config.to_adbc_kwargs()
        assert list(result.keys()) == ["uri"]

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        config = MySQLConfig(host="h", user="u", database="db")
        result = config.to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestSQLiteToAdbcKwargs:
    """Unit tests for SQLiteConfig.to_adbc_kwargs() method."""

    def test_memory_database(self) -> None:
        """SQLiteConfig().to_adbc_kwargs() uses ':memory:' by default — maps to 'uri' key."""
        result = SQLiteConfig().to_adbc_kwargs()
        assert result == {"uri": ":memory:"}

    def test_file_database(self) -> None:
        """SQLiteConfig(database=...).to_adbc_kwargs() maps database to 'uri' key."""
        result = SQLiteConfig(database="/data/x.db").to_adbc_kwargs()
        assert result == {"uri": "/data/x.db"}

    def test_output_has_only_uri_key(self) -> None:
        """to_adbc_kwargs() returns exactly one key ('uri')."""
        result = SQLiteConfig().to_adbc_kwargs()
        assert list(result.keys()) == ["uri"]

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        result = SQLiteConfig().to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result


class TestClickHouseToAdbcKwargs:
    """Unit tests for ClickHouseConfig.to_adbc_kwargs() method."""

    def test_uri_mode_secret_extracted(self) -> None:
        """URI mode extracts SecretStr value via to_adbc_kwargs()."""
        config = ClickHouseConfig(
            uri=SecretStr("http://user:pass@localhost:8123/db")  # pragma: allowlist secret
        )
        result = config.to_adbc_kwargs()
        assert result == {"uri": "http://user:pass@localhost:8123/db"}  # pragma: allowlist secret

    def test_decomposed_minimum(self) -> None:
        """Decomposed minimum via to_adbc_kwargs(): host, username, port as string."""
        config = ClickHouseConfig(host="localhost", username="default")
        result = config.to_adbc_kwargs()
        assert result == {"username": "default", "host": "localhost", "port": "8123"}

    def test_decomposed_full(self) -> None:
        """Full decomposed mode via to_adbc_kwargs() includes password and database."""
        config = ClickHouseConfig(
            host="localhost",
            username="default",
            password=SecretStr("secret"),  # pragma: allowlist secret
            database="mydb",
        )
        result = config.to_adbc_kwargs()
        assert result == {
            "username": "default",
            "host": "localhost",
            "port": "8123",
            "password": "secret",  # pragma: allowlist secret
            "database": "mydb",
        }

    def test_port_is_string(self) -> None:
        """Port is always str via to_adbc_kwargs()."""
        config = ClickHouseConfig(host="h", username="u")
        result = config.to_adbc_kwargs()
        assert result["port"] == "8123"
        assert isinstance(result["port"], str)

    def test_custom_port_as_string(self) -> None:
        """Non-default port appears as string via to_adbc_kwargs()."""
        config = ClickHouseConfig(host="h", username="u", port=8443)
        result = config.to_adbc_kwargs()
        assert result["port"] == "8443"

    def test_password_omitted_when_none(self) -> None:
        """Password absent from to_adbc_kwargs() when password is None."""
        config = ClickHouseConfig(host="h", username="u")
        result = config.to_adbc_kwargs()
        assert "password" not in result  # pragma: allowlist secret

    def test_database_omitted_when_none(self) -> None:
        """Database absent from to_adbc_kwargs() when database is None."""
        config = ClickHouseConfig(host="h", username="u")
        result = config.to_adbc_kwargs()
        assert "database" not in result

    def test_username_key_not_user(self) -> None:
        """to_adbc_kwargs() uses 'username' key, not 'user'."""
        config = ClickHouseConfig(host="h", username="default")
        result = config.to_adbc_kwargs()
        assert "username" in result
        assert "user" not in result

    def test_no_pool_fields_in_output(self) -> None:
        """Pool tuning fields excluded from to_adbc_kwargs() output."""
        config = ClickHouseConfig(host="h", username="u")
        result = config.to_adbc_kwargs()
        for key in ("pool_size", "max_overflow", "timeout", "recycle"):
            assert key not in result
