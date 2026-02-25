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
    PostgreSQLConfig,
    RedshiftConfig,
    SnowflakeConfig,
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


class TestFoundryBackendConfigs:
    """Smoke tests for Databricks, Redshift, Trino, MSSQL."""

    def test_databricks_default_construction(self) -> None:
        db = DatabricksConfig()
        assert db.pool_size == 5
        assert db.token is None
        assert isinstance(db, WarehouseConfig)

    def test_databricks_token_is_secret_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi123")
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
