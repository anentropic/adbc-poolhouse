"""DuckDB warehouse configuration."""

from __future__ import annotations

from typing import Self

from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


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

    def _adbc_driver_key(self) -> str:
        return "duckdb"

    @model_validator(mode="after")
    def check_memory_pool_size(self) -> Self:
        if self.database == ":memory:" and self.pool_size > 1:
            raise ValueError(
                'pool_size > 1 with database=":memory:" will give each pool '
                "connection an isolated in-memory database (each connection "
                "sees a different empty DB, so shared state is impossible). "
                "Use pool_size=1 for in-memory DuckDB, or set database to a "
                "file path for shared state across connections."
            )
        return self
