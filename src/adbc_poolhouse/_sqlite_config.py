"""SQLite warehouse configuration."""

from __future__ import annotations

from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class SQLiteConfig(BaseWarehouseConfig):
    """
    SQLite warehouse configuration.

    Covers SQLite ADBC connection parameters. Pool tuning fields
    (pool_size, max_overflow, timeout, recycle) are inherited from
    BaseWarehouseConfig and loaded from SQLITE_* environment variables.

    Unlike DuckDB, an SQLite in-memory database is shared across all
    connections in the pool. This means pool_size > 1 with
    database=':memory:' is almost always unintended (connection state
    races across a single shared DB), so it is rejected by a validator.

    Args:
        database: File path or ':memory:'. Default ':memory:'.
        pool_size: Number of connections in the pool. Default 1.

    Example:
        SQLiteConfig(database='/data/warehouse.db', pool_size=5)
        SQLiteConfig()  # in-memory, pool_size=1 enforced by validator
    """

    model_config = SettingsConfigDict(env_prefix="SQLITE_")

    database: str = ":memory:"
    """File path or ':memory:'. Env: SQLITE_DATABASE."""

    pool_size: int = 1
    """Number of connections in the pool. Default 1 for in-memory SQLite.

    SQLite in-memory databases are shared across all connections in the
    pool — unlike DuckDB, where each connection gets its own isolated
    empty DB. Use pool_size=1 for ':memory:', or set database to a file
    path if you need pool_size > 1. Setting pool_size > 1 with
    database=':memory:' raises ValidationError.
    Env: SQLITE_POOL_SIZE.
    """

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
        """
        Return the ADBC entry-point symbol for the SQLite driver.

        Internal only — not part of the public API.
        """
        return "adbc_driver_sqlite_init"

    @model_validator(mode="after")
    def check_memory_pool_size(self) -> Self:
        if self.database == ":memory:" and self.pool_size > 1:
            raise ConfigurationError(
                'pool_size > 1 with database=":memory:" is not supported for '
                "in-memory SQLite. Unlike DuckDB, in-memory SQLite is shared "
                "across all connections in the pool — so pool_size > 1 creates "
                "connection state races on a single shared in-memory database. "
                "Use pool_size=1 for in-memory SQLite, or set database to a "
                "file path to allow pool_size > 1."
            )
        return self
