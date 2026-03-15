"""Base warehouse configuration: base class and Protocol type."""

from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from pydantic_settings import BaseSettings


@runtime_checkable
class WarehouseConfig(Protocol):
    """
    Structural type for warehouse config objects.

    Any class with these attributes and methods can be passed to
    `create_pool` or `managed_pool`. The built-in config
    classes all satisfy this protocol through
    `BaseWarehouseConfig`.

    Third-party authors: inherit from `BaseWarehouseConfig`
    for pool-tuning defaults and `_resolve_driver_path`, or
    implement the full protocol from scratch.
    """

    pool_size: int
    """Number of connections to keep open in the pool."""

    max_overflow: int
    """Connections allowed above pool_size when the pool is exhausted."""

    timeout: int
    """Seconds to wait for a connection before raising TimeoutError."""

    recycle: int
    """Seconds before a connection is closed and replaced."""

    def _adbc_entrypoint(self) -> str | None:
        """
        Return the ADBC driver init symbol, or ``None`` for the default.

        Most ADBC drivers use a default init function and this method
        should return ``None``. Override only when the driver requires a
        non-standard symbol -- for example, DuckDB needs
        ``"duckdb_adbc_init"``.
        """
        ...

    def _driver_path(self) -> str | None:
        """
        Return the ADBC driver path or short name, or ``None``.

        Called by ``create_pool`` to locate the native driver library.
        Two return styles are supported:

        - An absolute filesystem path to a shared library
          (e.g. ``/usr/lib/libadbc_driver_snowflake.so``).
        - A short package name (e.g. ``"adbc_driver_snowflake"``)
          that ``adbc_driver_manager`` resolves via its manifest.

        Return ``None`` when the driver uses a Python dbapi module
        instead (see `_dbapi_module`). At least one of
        ``_driver_path`` or ``_dbapi_module`` must return a non-None
        value.

        Most implementations delegate to
        `BaseWarehouseConfig._resolve_driver_path`.
        """
        ...

    def _dbapi_module(self) -> str | None:
        """
        Return a dotted Python module path exposing ``connect()``, or ``None``.

        When set, ``create_pool`` imports this module and calls its
        ``connect()`` function instead of loading a native shared library
        through ``adbc_driver_manager``. Typical value:
        ``"adbc_driver_snowflake.dbapi"``.

        Return ``None`` (the default) for drivers that do not ship a
        Python package with a ``dbapi`` sub-module.
        """
        ...

    def to_adbc_kwargs(self) -> dict[str, str]:
        """Convert config to ADBC driver connection kwargs."""
        ...


class BaseWarehouseConfig(BaseSettings, ABC):
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
        Return the ADBC driver init symbol, or ``None`` for the default.

        The base implementation returns ``None``. Override in subclasses
        where the driver uses a non-standard init symbol (e.g. DuckDB
        returns ``"duckdb_adbc_init"``).
        """
        return None

    def _driver_path(self) -> str | None:
        """
        Return the ADBC driver path or short name, or ``None``.

        Override to provide a native ADBC driver. Most implementations
        call ``self._resolve_driver_path("adbc_driver_<name>")``.

        The base implementation returns ``None``. At least one of
        ``_driver_path`` or ``_dbapi_module`` must be overridden to
        return a non-None value.
        """
        return None

    def _dbapi_module(self) -> str | None:
        """
        Return a dotted Python module path exposing ``connect()``, or ``None``.

        The base implementation returns ``None``. Override when the
        driver ships a Python package with a ``dbapi`` sub-module
        (e.g. ``"adbc_driver_snowflake.dbapi"``).
        """
        return None

    @abstractmethod
    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert config to ADBC driver connection kwargs.

        Subclasses must override this method to provide backend-specific
        serialization.
        """
        ...

    @staticmethod
    def _resolve_driver_path(
        pkg_name: str,
        *,
        method_name: str = "_driver_path",
    ) -> str:
        """
        Resolve driver path from a PyPI ADBC driver package.

        Tries ``find_spec`` -> ``import`` -> call ``method_name()``. Falls back
        to returning *pkg_name* for ``adbc_driver_manager`` manifest resolution.

        Args:
            pkg_name: Python package name (e.g. ``"adbc_driver_snowflake"``).
            method_name: Function name on the package module. Apache drivers
                use ``"_driver_path"``, DuckDB uses ``"driver_path"``.

        Returns:
            Absolute path to driver shared library, or *pkg_name* as fallback.
        """
        spec = importlib.util.find_spec(pkg_name)
        if spec is not None:
            pkg: Any = __import__(pkg_name)
            return pkg.__dict__[method_name]()
        return pkg_name
