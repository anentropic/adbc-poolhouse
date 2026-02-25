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
    max_overflow: int
    timeout: int
    recycle: int

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
    max_overflow: int = 3
    timeout: int = 30
    recycle: int = 3600

    def _adbc_entrypoint(self) -> str | None:
        """
        Return the ADBC entry-point symbol, or None if not required.

        DuckDB overrides this to return ``'duckdb_adbc_init'``.
        All other drivers do not need an explicit entry point.

        Internal only — not part of the public API.
        """
        return None
