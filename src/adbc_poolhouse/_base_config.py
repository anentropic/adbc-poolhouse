"""Base warehouse configuration: base class and Protocol type."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic_settings import BaseSettings


@runtime_checkable
class WarehouseConfig(Protocol):
    """
    Structural type for any adbc-poolhouse warehouse config model.

    Downstream code annotates function parameters as `config: WarehouseConfig`
    to accept any supported warehouse config without importing concrete classes.
    """

    pool_size: int
    """Number of connections to keep open in the pool."""

    max_overflow: int
    """Connections allowed above pool_size when the pool is exhausted."""

    timeout: int
    """Seconds to wait for a connection before raising TimeoutError."""

    recycle: int
    """Seconds before a connection is closed and replaced."""

    def _adbc_entrypoint(self) -> str | None: ...


class BaseWarehouseConfig(BaseSettings):
    """
    Base class for all warehouse config models.

    Provides pool tuning fields with library defaults. Not intended to be
    instantiated directly — use a concrete subclass (e.g. DuckDBConfig).

    Pool tuning fields are inherited by all concrete configs, and each
    concrete config's env_prefix applies to these fields automatically.
    For example, DUCKDB_POOL_SIZE populates DuckDBConfig.pool_size.
    """

    pool_size: int = 5
    """Number of connections to keep open in the pool. Default: 5."""

    max_overflow: int = 3
    """Connections allowed above pool_size when pool is exhausted. Default: 3."""

    timeout: int = 30
    """Seconds to wait for a connection before raising TimeoutError. Default: 30."""

    recycle: int = 3600
    """Seconds before a connection is closed and replaced. Default: 3600."""

    def _adbc_entrypoint(self) -> str | None:
        """
        Return the ADBC entry-point symbol, or None if not required.

        DuckDB overrides this to return ``'duckdb_adbc_init'``.
        All other drivers do not need an explicit entry point.

        Internal only — not part of the public API.
        """
        return None
