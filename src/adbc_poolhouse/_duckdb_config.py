"""DuckDB warehouse configuration."""

from __future__ import annotations

from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class DuckDBConfig(BaseWarehouseConfig):
    """
    DuckDB warehouse configuration.

    Covers all DuckDB ADBC connection parameters. Pool tuning fields
    (pool_size, max_overflow, timeout, recycle) are inherited from
    BaseWarehouseConfig and loaded from DUCKDB_* environment variables.

    Example:
        DuckDBConfig(database='/data/warehouse.db', pool_size=5)
        DuckDBConfig()  # in-memory, pool_size=1 enforced by validator
    """

    model_config = SettingsConfigDict(env_prefix="DUCKDB_")

    database: str = ":memory:"
    """File path or ':memory:'. Env: DUCKDB_DATABASE."""

    pool_size: int = 1
    """Number of connections in the pool. Default 1 for in-memory DuckDB.

    In-memory DuckDB databases are isolated per connection — each pool
    connection gets a different empty DB. Use pool_size=1 for ':memory:',
    or set database to a file path if you need pool_size > 1. Setting
    pool_size > 1 with database=':memory:' raises ValidationError.
    Env: DUCKDB_POOL_SIZE.
    """

    read_only: bool = False
    """Open the database in read-only mode. Env: DUCKDB_READ_ONLY."""

    @field_validator("pool_size")
    @classmethod
    def validate_pool_size(cls, v: int) -> int:
        if v <= 0:
            raise ConfigurationError(f"pool_size must be > 0, got {v}")
        return v

    @field_validator("max_overflow")
    @classmethod
    def validate_max_overflow(cls, v: int) -> int:
        if v < 0:
            raise ConfigurationError(f"max_overflow must be >= 0, got {v}")
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v <= 0:
            raise ConfigurationError(f"timeout must be > 0, got {v}")
        return v

    @field_validator("recycle")
    @classmethod
    def validate_recycle(cls, v: int) -> int:
        if v <= 0:
            raise ConfigurationError(f"recycle must be > 0, got {v}")
        return v

    @field_validator("database")
    @classmethod
    def validate_database(cls, v: str) -> str:
        if not v or not v.strip():
            raise ConfigurationError(f"database must be a non-empty string, got {v!r}")
        return v

    def _adbc_entrypoint(self) -> str | None:
        return "duckdb_adbc_init"

    @model_validator(mode="after")
    def check_memory_pool_size(self) -> Self:
        if self.database == ":memory:" and self.pool_size > 1:
            raise ConfigurationError(
                'pool_size > 1 with database=":memory:" will give each pool '
                "connection an isolated in-memory database (each connection "
                "sees a different empty DB, so shared state is impossible). "
                "Use pool_size=1 for in-memory DuckDB, or set database to a "
                "file path for shared state across connections."
            )
        return self
