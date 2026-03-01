"""Unit tests for all adbc_poolhouse config models (TEST-04)."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from adbc_poolhouse import (
    BaseWarehouseConfig,
    BigQueryConfig,
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
    WarehouseConfig,
)


class TestBaseWarehouseConfig:
    def test_pool_tuning_defaults(self) -> None:
        """Base class pool tuning defaults are inherited by all concrete configs."""
        assert BaseWarehouseConfig.model_fields["pool_size"].default == 5
        assert BaseWarehouseConfig.model_fields["max_overflow"].default == 3
        assert BaseWarehouseConfig.model_fields["timeout"].default == 30
        assert BaseWarehouseConfig.model_fields["recycle"].default == 3600


class TestDuckDBConfig:
    def test_default_construction(self) -> None:
        d = DuckDBConfig()
        assert d.database == ":memory:"
        assert d.pool_size == 1  # DuckDB in-memory default is 1
        assert d.max_overflow == 3
        assert d.timeout == 30
        assert d.recycle == 3600
        assert d.read_only is False

    def test_memory_pool_size_validator_fires(self) -> None:
        with pytest.raises(ValidationError, match="pool_size > 1"):
            DuckDBConfig(database=":memory:", pool_size=2)

    def test_memory_pool_size_1_is_valid(self) -> None:
        d = DuckDBConfig(database=":memory:", pool_size=1)
        assert d.pool_size == 1

    def test_file_database_pool_size_gt1_is_valid(self) -> None:
        d = DuckDBConfig(database="/tmp/test.duckdb", pool_size=5)
        assert d.pool_size == 5

    def test_env_prefix_pool_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Use a file database since pool_size > 1 with :memory: raises ValidationError
        monkeypatch.setenv("DUCKDB_POOL_SIZE", "8")
        monkeypatch.setenv("DUCKDB_DATABASE", "/tmp/test.duckdb")
        d = DuckDBConfig()
        assert d.pool_size == 8

    def test_env_prefix_isolation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Use a file database since pool_size > 1 with :memory: raises ValidationError
        monkeypatch.setenv("DUCKDB_POOL_SIZE", "8")
        monkeypatch.setenv("DUCKDB_DATABASE", "/tmp/test.duckdb")
        monkeypatch.setenv("SNOWFLAKE_POOL_SIZE", "3")
        d = DuckDBConfig()
        assert d.pool_size == 8  # SNOWFLAKE_ prefix does not affect DuckDB

    def test_warehouse_config_protocol(self) -> None:
        assert isinstance(DuckDBConfig(), WarehouseConfig)


class TestSnowflakeConfig:
    def test_basic_construction(self) -> None:
        s = SnowflakeConfig(account="myaccount")
        assert s.account == "myaccount"
        assert s.pool_size == 5
        assert s.password is None

    def test_private_key_mutual_exclusion(self) -> None:
        pem = SecretStr("-----BEGIN PRIVATE KEY-----")  # pragma: allowlist secret
        with pytest.raises(ValidationError, match="private_key_path"):
            SnowflakeConfig(
                account="myaccount",
                private_key_path=Path("/tmp/key.p8"),
                private_key_pem=pem,
            )

    def test_private_key_path_only_valid(self) -> None:
        s = SnowflakeConfig(account="myaccount", private_key_path=Path("/tmp/key.p8"))
        assert s.private_key_path == Path("/tmp/key.p8")
        assert s.private_key_pem is None

    def test_private_key_pem_only_valid(self) -> None:
        pem = SecretStr("-----BEGIN")  # pragma: allowlist secret
        s = SnowflakeConfig(account="myaccount", private_key_pem=pem)
        assert s.private_key_pem is not None
        assert s.private_key_path is None

    def test_password_is_secret_str(self) -> None:
        pwd = SecretStr("supersecret")  # pragma: allowlist secret
        s = SnowflakeConfig(account="myaccount", password=pwd)
        assert "supersecret" not in repr(s)
        assert s.password is not None
        assert s.password.get_secret_value() == "supersecret"

    def test_env_prefix_account(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "envaccount")
        s = SnowflakeConfig()  # type: ignore[call-arg]
        assert s.account == "envaccount"

    def test_env_prefix_pool_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "x")
        monkeypatch.setenv("SNOWFLAKE_POOL_SIZE", "3")
        monkeypatch.setenv("DUCKDB_POOL_SIZE", "10")
        s = SnowflakeConfig()  # type: ignore[call-arg]
        assert s.pool_size == 3  # DUCKDB_ prefix does not affect Snowflake

    def test_warehouse_config_protocol(self) -> None:
        assert isinstance(SnowflakeConfig(account="x"), WarehouseConfig)


class TestApacheBackendConfigs:
    """Smoke tests for BigQuery, PostgreSQL, FlightSQL."""

    def test_bigquery_default_construction(self) -> None:
        bq = BigQueryConfig()
        assert bq.pool_size == 5
        assert isinstance(bq, WarehouseConfig)

    def test_postgresql_default_construction(self) -> None:
        pg = PostgreSQLConfig()
        assert pg.pool_size == 5
        assert pg.use_copy is True
        assert isinstance(pg, WarehouseConfig)

    def test_flightsql_default_construction(self) -> None:
        f = FlightSQLConfig()
        assert f.pool_size == 5
        assert f.tls_skip_verify is False
        assert isinstance(f, WarehouseConfig)

    def test_env_prefix_isolation_bigquery(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BIGQUERY_POOL_SIZE", "7")
        monkeypatch.setenv("DUCKDB_POOL_SIZE", "2")
        bq = BigQueryConfig()
        assert bq.pool_size == 7


class TestPostgreSQLConfig:
    """Unit tests for PostgreSQLConfig — individual fields and env prefix."""

    def test_individual_fields_constructs(self) -> None:
        """PostgreSQLConfig with host/user/database constructs and reads back correctly."""
        c = PostgreSQLConfig(host="db.example.com", user="me", database="mydb")
        assert c.host == "db.example.com"
        assert c.user == "me"
        assert c.database == "mydb"
        assert c.port is None
        assert isinstance(c, WarehouseConfig)

    def test_password_is_secret_str(self) -> None:
        """Password field is SecretStr — repr does not expose value."""
        c = PostgreSQLConfig(
            host="db.example.com",
            user="me",
            password=SecretStr("hunter2"),  # pragma: allowlist secret
            database="mydb",
        )
        assert "hunter2" not in repr(c)

    def test_env_prefix_loads_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POSTGRESQL_HOST, POSTGRESQL_USER, POSTGRESQL_DATABASE load via env_prefix."""
        monkeypatch.setenv("POSTGRESQL_HOST", "envhost")
        monkeypatch.setenv("POSTGRESQL_USER", "envuser")
        monkeypatch.setenv("POSTGRESQL_DATABASE", "envdb")
        c = PostgreSQLConfig()
        assert c.host == "envhost"
        assert c.user == "envuser"
        assert c.database == "envdb"

    def test_env_prefix_pool_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POSTGRESQL_POOL_SIZE env var sets pool_size via env_prefix."""
        monkeypatch.setenv("POSTGRESQL_POOL_SIZE", "7")
        c = PostgreSQLConfig()
        assert c.pool_size == 7


class TestFoundryBackendConfigs:
    """Smoke tests for Databricks, Redshift, Trino, MSSQL."""

    def test_databricks_no_args_raises(self) -> None:
        """DatabricksConfig() with no connection spec raises ValidationError."""
        with pytest.raises(ValidationError):
            DatabricksConfig()

    def test_databricks_uri_constructs(self) -> None:
        """DatabricksConfig with uri= constructs successfully."""
        db = DatabricksConfig(
            uri=SecretStr("databricks://token:dapi@host:443/sql/1.0/warehouses/abc")
        )  # pragma: allowlist secret
        assert db.pool_size == 5
        assert isinstance(db, WarehouseConfig)

    def test_databricks_token_is_secret_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABRICKS_HOST", "adb-xxx.azuredatabricks.net")
        monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc")
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")  # pragma: allowlist secret
        db = DatabricksConfig()
        assert isinstance(db.token, SecretStr)
        assert "dapi123" not in repr(db)

    def test_redshift_default_construction(self) -> None:
        rs = RedshiftConfig()
        assert rs.pool_size == 5
        assert isinstance(rs, WarehouseConfig)

    def test_trino_default_construction(self) -> None:
        t = TrinoConfig()
        assert t.ssl is True
        assert t.ssl_verify is True
        assert isinstance(t, WarehouseConfig)

    def test_mssql_default_construction(self) -> None:
        m = MSSQLConfig()
        assert m.trust_server_certificate is False
        assert isinstance(m, WarehouseConfig)


class TestSQLiteConfig:
    def test_default_construction(self) -> None:
        s = SQLiteConfig()
        assert s.database == ":memory:"
        assert s.pool_size == 1
        assert s.max_overflow == 3
        assert s.timeout == 30
        assert s.recycle == 3600

    def test_memory_pool_size_validator_fires(self) -> None:
        with pytest.raises(ValidationError, match="pool_size > 1"):
            SQLiteConfig(database=":memory:", pool_size=2)

    def test_memory_pool_size_1_is_valid(self) -> None:
        s = SQLiteConfig(database=":memory:", pool_size=1)
        assert s.pool_size == 1

    def test_file_database_pool_size_gt1_is_valid(self) -> None:
        s = SQLiteConfig(database="/tmp/x.db", pool_size=5)
        assert s.pool_size == 5

    def test_env_prefix_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SQLITE_DATABASE", "/tmp/envtest.db")
        s = SQLiteConfig()
        assert s.database == "/tmp/envtest.db"

    def test_env_prefix_pool_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SQLITE_POOL_SIZE", "8")
        monkeypatch.setenv("SQLITE_DATABASE", "/tmp/test.db")
        s = SQLiteConfig()
        assert s.pool_size == 8

    def test_env_prefix_isolation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SQLITE_POOL_SIZE", "8")
        monkeypatch.setenv("SQLITE_DATABASE", "/tmp/test.db")
        monkeypatch.setenv("DUCKDB_POOL_SIZE", "3")
        s = SQLiteConfig()
        assert s.pool_size == 8  # DUCKDB_ prefix does not affect SQLite

    def test_warehouse_config_protocol(self) -> None:
        assert isinstance(SQLiteConfig(), WarehouseConfig)


class TestMySQLConfig:
    """Unit tests for MySQLConfig — connection validation and env prefix."""

    def test_no_args_raises(self) -> None:
        """MySQLConfig() with no connection spec raises ValidationError."""
        with pytest.raises(ValidationError):
            MySQLConfig()

    def test_uri_mode_constructs(self) -> None:
        """MySQLConfig with uri= constructs successfully."""
        c = MySQLConfig(uri=SecretStr("mysql://user:pass@host:3306/db"))  # pragma: allowlist secret
        assert c.uri is not None
        assert isinstance(c, WarehouseConfig)

    def test_decomposed_no_password(self) -> None:
        """MySQLConfig with host/user/database and no password constructs."""
        c = MySQLConfig(host="localhost", user="root", database="demo")
        assert c.password is None
        assert c.port == 3306
        assert isinstance(c, WarehouseConfig)

    def test_decomposed_with_password(self) -> None:
        """MySQLConfig with host/user/database/password constructs."""
        c = MySQLConfig(
            host="localhost",
            user="root",
            password=SecretStr("secret"),  # pragma: allowlist secret
            database="demo",
        )
        assert c.password is not None
        assert isinstance(c, WarehouseConfig)

    def test_host_only_raises(self) -> None:
        """MySQLConfig(host=...) with missing user and database raises ValidationError."""
        with pytest.raises(ValidationError):
            MySQLConfig(host="localhost")

    def test_host_and_user_raises(self) -> None:
        """MySQLConfig(host=..., user=...) with missing database raises ValidationError."""
        with pytest.raises(ValidationError):
            MySQLConfig(host="localhost", user="root")

    def test_custom_port(self) -> None:
        """MySQLConfig accepts a non-default port."""
        c = MySQLConfig(host="h", user="u", database="db", port=5306)
        assert c.port == 5306

    def test_password_is_secret_str(self) -> None:
        """Password field is SecretStr — repr does not expose value."""
        c = MySQLConfig(
            host="h",
            user="u",
            password=SecretStr("hunter2"),  # pragma: allowlist secret
            database="db",
        )
        assert "hunter2" not in repr(c)

    def test_env_prefix_loads_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE env vars load via env_prefix."""
        monkeypatch.setenv("MYSQL_HOST", "envhost")
        monkeypatch.setenv("MYSQL_USER", "envuser")
        monkeypatch.setenv("MYSQL_DATABASE", "envdb")
        c = MySQLConfig()
        assert c.host == "envhost"
        assert c.user == "envuser"
        assert c.database == "envdb"

    def test_env_prefix_pool_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MYSQL_POOL_SIZE env var sets pool_size via env_prefix."""
        monkeypatch.setenv("MYSQL_HOST", "h")
        monkeypatch.setenv("MYSQL_USER", "u")
        monkeypatch.setenv("MYSQL_DATABASE", "db")
        monkeypatch.setenv("MYSQL_POOL_SIZE", "7")
        c = MySQLConfig()
        assert c.pool_size == 7
