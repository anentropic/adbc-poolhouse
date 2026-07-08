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

    Example:
        ```python
        SQLiteConfig(database="/data/warehouse.db")  # file-backed, pool_size defaults to 5
        SQLiteConfig()  # in-memory, pool_size defaults to 1
        ```
    """

    model_config = SettingsConfigDict(env_prefix="SQLITE_")

    database: str = ":memory:"
    """File path or ':memory:'. Env: SQLITE_DATABASE."""

    pool_size: int = 1
    """Number of connections in the pool. Defaults to 5 for a file-backed
    database and 1 for in-memory.

    SQLite in-memory databases are shared across all connections in the
    pool — unlike DuckDB, where each connection gets its own isolated
    empty DB — and pool_size > 1 races connection state on that single shared
    DB, so ':memory:' pins the default to 1. A file-backed database defaults to
    5 like the other backends. Setting pool_size > 1 with database=':memory:'
    raises ValidationError. Env: SQLITE_POOL_SIZE.
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
        # NOTE: The C source uses "AdbcDriverSqliteInit" (PascalCase), not the
        # snake_case "adbc_driver_sqlite_init" that the module name might suggest.
        # Confirmed by integration testing: "adbc_driver_sqlite_init" raises
        # dlsym symbol-not-found; "AdbcDriverSqliteInit" resolves correctly.
        return "AdbcDriverSqliteInit"

    def _driver_path(self) -> str:
        return self._resolve_driver_path("adbc_driver_sqlite")

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert config to ADBC driver connection kwargs.

        Returns:
            Dict with a single ``'uri'`` key set to the database path
            (or ``':memory:'``).
        """
        return {"uri": self.database}

    @model_validator(mode="after")
    def default_pool_size_for_file(self) -> Self:
        """
        Raise the pool_size default to 5 for a file-backed database.

        The field default is 1, the only safe value for a shared in-memory
        database. When the database is a file and the caller did not set
        pool_size explicitly (via keyword or environment), bump it to 5 to match
        the other backends.
        """
        if "pool_size" not in self.model_fields_set and self.database != ":memory:":
            self.pool_size = 5
        return self

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
