"""DuckDB warehouse configuration."""

from __future__ import annotations

from pydantic import field_validator
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
        ```python
        DuckDBConfig(database="/data/warehouse.db")  # file-backed
        DuckDBConfig()  # in-memory, shared by every pooled connection
        ```
    """

    model_config = SettingsConfigDict(env_prefix="DUCKDB_")

    database: str = ":memory:"
    """File path or ':memory:'. Env: DUCKDB_DATABASE."""

    pool_size: int = 5
    """Number of connections in the pool. Env: DUCKDB_POOL_SIZE.

    Defaults to 5 for both file-backed and in-memory databases. Every pooled
    connection is cloned from one source connection and opens the same
    database, so with ':memory:' all of them share one in-memory database,
    which lives until the pool is closed. Tables, views, attached catalogs and
    loaded extensions are visible from every connection, including ones the
    pool opens later to replace a recycled connection. Temporary tables and
    connection-scoped settings stay per connection, as they do for a file.
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

    def _driver_path(self) -> str:
        # adbc_driver_duckdb uses driver_path() (no underscore prefix)
        return self._resolve_driver_path("adbc_driver_duckdb", method_name="driver_path")

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert config to ADBC driver connection kwargs.

        Returns:
            Dict with ``'path'`` key (always) and ``'access_mode'`` set to
            ``'READ_ONLY'`` when ``read_only`` is True.
        """
        result: dict[str, str] = {"path": self.database}
        if self.read_only:
            result["access_mode"] = "READ_ONLY"
        return result
