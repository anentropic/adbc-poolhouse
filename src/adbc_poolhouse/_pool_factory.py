"""
Pool factory: public create_pool() entry point.

This module wires together config methods and the ADBC source+clone
pattern to create a SQLAlchemy QueuePool.  Each config instance is
self-describing -- it carries its own driver path, kwargs translation,
entrypoint, and optional DBAPI module -- so no registry or dispatch
layer is needed.

Three call patterns are supported:

1. ``create_pool(config)`` -- config-based (original path)
2. ``create_pool(driver_path=..., db_kwargs=...)`` -- native ADBC driver
3. ``create_pool(dbapi_module=..., db_kwargs=...)`` -- Python dbapi module

No module-level pool or connection objects exist here (POOL-05).

Internal helpers are prefixed with _ and not exported.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, overload

import sqlalchemy.pool
from sqlalchemy import event

from adbc_poolhouse._driver_api import create_adbc_connection

if TYPE_CHECKING:
    import collections.abc

    from adbc_poolhouse._base_config import WarehouseConfig


def _create_pool_impl(
    config: WarehouseConfig | None,
    driver_path: str | None,
    db_kwargs: dict[str, str] | None,
    entrypoint: str | None,
    dbapi_module: str | None,
    pool_size: int,
    max_overflow: int,
    timeout: int,
    recycle: int,
    pre_ping: bool,
) -> sqlalchemy.pool.QueuePool:
    """Internal: create pool from either config or raw driver args."""
    if driver_path is not None and dbapi_module is not None:
        raise TypeError("create_pool() accepts driver_path or dbapi_module, not both")

    if config is not None:
        # Config path -- extract driver info from config methods
        cfg_driver_path = config._driver_path()
        cfg_dbapi_module = config._dbapi_module()
        if cfg_driver_path is None and cfg_dbapi_module is None:
            raise TypeError(
                f"{type(config).__name__} must provide _driver_path() or "
                "_dbapi_module() (both returned None)"
            )
        resolved_driver_path = cfg_driver_path if cfg_driver_path is not None else ""
        resolved_kwargs = config.to_adbc_kwargs()
        resolved_entrypoint = config._adbc_entrypoint()
        resolved_dbapi_module = cfg_dbapi_module
    elif driver_path is not None:
        # Native ADBC driver path
        if db_kwargs is None:
            raise TypeError("db_kwargs is required when using driver_path")
        resolved_driver_path = driver_path
        resolved_kwargs = db_kwargs
        resolved_entrypoint = entrypoint
        resolved_dbapi_module = None
    elif dbapi_module is not None:
        # Python dbapi module path -- driver_path unused by this branch
        if db_kwargs is None:
            raise TypeError("db_kwargs is required when using dbapi_module")
        resolved_driver_path = ""
        resolved_kwargs = db_kwargs
        resolved_entrypoint = None
        resolved_dbapi_module = dbapi_module
    else:
        raise TypeError(
            "create_pool() requires one of: a config object (positional), "
            "driver_path=..., or dbapi_module=..."
        )

    source = create_adbc_connection(
        resolved_driver_path,
        resolved_kwargs,
        entrypoint=resolved_entrypoint,
        dbapi_module=resolved_dbapi_module,
    )

    pool = sqlalchemy.pool.QueuePool(
        source.adbc_clone,  # type: ignore[arg-type]
        pool_size=pool_size,
        max_overflow=max_overflow,
        timeout=timeout,
        recycle=recycle,
        pre_ping=pre_ping,
    )

    pool._adbc_source = source  # type: ignore[attr-defined]

    event.listen(pool, "reset", _release_arrow_allocators)

    return pool


@overload
def create_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool: ...


@overload
def create_pool(
    *,
    driver_path: str,
    db_kwargs: dict[str, str],
    entrypoint: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool: ...


@overload
def create_pool(
    *,
    dbapi_module: str,
    db_kwargs: dict[str, str],
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool: ...


def create_pool(
    config: WarehouseConfig | None = None,
    *,
    driver_path: str | None = None,
    db_kwargs: dict[str, str] | None = None,
    entrypoint: str | None = None,
    dbapi_module: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool:
    """
    Create a SQLAlchemy QueuePool backed by an ADBC driver.

    Three call patterns are supported:

        pool = create_pool(DuckDBConfig(...))           # from a config object
        pool = create_pool(driver_path="...", ...)       # native ADBC driver
        pool = create_pool(dbapi_module="...", ...)      # Python dbapi module

    The config path extracts driver information from the config object's
    methods. The two raw paths accept driver arguments directly, bypassing
    config objects entirely.

    Args:
        config: A warehouse config model instance (e.g. ``DuckDBConfig``).
            Mutually exclusive with ``driver_path`` and ``dbapi_module``.
        driver_path: Path to a native ADBC driver shared library, or a
            short driver name for manifest-based resolution. Requires
            ``db_kwargs``. Mutually exclusive with ``config`` and
            ``dbapi_module``.
        db_kwargs: ADBC connection keyword arguments as ``dict[str, str]``.
            Required when using ``driver_path`` or ``dbapi_module``.
        entrypoint: ADBC entry-point symbol. Only used with ``driver_path``
            (e.g. ``"duckdb_adbc_init"`` for DuckDB). Default: ``None``.
        dbapi_module: Dotted module name for a Python package implementing
            the ADBC dbapi interface (e.g. ``"adbc_driver_snowflake.dbapi"``
            or a custom ``"my_driver.dbapi"``). Requires ``db_kwargs``.
            Mutually exclusive with ``config`` and ``driver_path``.
        pool_size: Number of connections to keep in the pool. Default: 5.
        max_overflow: Extra connections allowed above pool_size. Default: 3.
        timeout: Seconds to wait for a connection before raising. Default: 30.
        recycle: Seconds before a connection is recycled. Default: 3600.
        pre_ping: Whether to ping connections before checkout. Default: False.
            Pre-ping does not function on a standalone QueuePool without a
            SQLAlchemy dialect; recycle is the preferred health mechanism.

    Returns:
        A configured ``sqlalchemy.pool.QueuePool`` ready for use.

    Raises:
        TypeError: If none of ``config``, ``driver_path``, or ``dbapi_module``
            is provided, or if both ``driver_path`` and ``dbapi_module`` are
            provided.
        ImportError: If the required ADBC driver is not installed.

    Example:
        Config path:

        ```python
        from adbc_poolhouse import create_pool, close_pool
        from adbc_poolhouse import DuckDBConfig

        pool = create_pool(DuckDBConfig(database="/tmp/my.db"))
        close_pool(pool)
        ```

        Raw native driver path:

        ```python
        pool = create_pool(
            driver_path="/path/to/libduckdb.dylib",
            db_kwargs={"path": "/tmp/my.db"},
            entrypoint="duckdb_adbc_init",
        )
        close_pool(pool)
        ```
    """
    return _create_pool_impl(
        config,
        driver_path,
        db_kwargs,
        entrypoint,
        dbapi_module,
        pool_size,
        max_overflow,
        timeout,
        recycle,
        pre_ping,
    )


def close_pool(pool: sqlalchemy.pool.QueuePool) -> None:
    """
    Dispose a pool and close its underlying ADBC source connection.

    Replaces the two-step pattern ``pool.dispose()`` followed by
    ``pool._adbc_source.close()``. Always call this instead of calling
    ``pool.dispose()`` directly to avoid leaving the ADBC source connection open.

    Args:
        pool: A pool returned by `create_pool`.

    Example:
        ```python
        from adbc_poolhouse import DuckDBConfig, create_pool, close_pool

        pool = create_pool(DuckDBConfig(database="/tmp/wh.db"))
        close_pool(pool)
        ```
    """
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]


@overload
def managed_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> contextlib.AbstractContextManager[sqlalchemy.pool.QueuePool]: ...


@overload
def managed_pool(
    *,
    driver_path: str,
    db_kwargs: dict[str, str],
    entrypoint: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> contextlib.AbstractContextManager[sqlalchemy.pool.QueuePool]: ...


@overload
def managed_pool(
    *,
    dbapi_module: str,
    db_kwargs: dict[str, str],
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> contextlib.AbstractContextManager[sqlalchemy.pool.QueuePool]: ...


@contextlib.contextmanager
def managed_pool(
    config: WarehouseConfig | None = None,
    *,
    driver_path: str | None = None,
    db_kwargs: dict[str, str] | None = None,
    entrypoint: str | None = None,
    dbapi_module: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> collections.abc.Generator[sqlalchemy.pool.QueuePool, None, None]:
    """
    Context manager that creates a pool and closes it on exit.

    The pool is created when the ``with`` block is entered and disposed
    (via `close_pool`) when the block exits, whether normally or by
    exception.

    Three call patterns are supported:

        with managed_pool(DuckDBConfig(...)) as pool: ...          # config
        with managed_pool(driver_path="...", ...) as pool: ...     # native
        with managed_pool(dbapi_module="...", ...) as pool: ...    # dbapi

    Args:
        config: A warehouse config model instance (e.g. ``DuckDBConfig``).
            Mutually exclusive with ``driver_path`` and ``dbapi_module``.
        driver_path: Path to a native ADBC driver shared library, or a
            short driver name for manifest-based resolution. Requires
            ``db_kwargs``. Mutually exclusive with ``config`` and
            ``dbapi_module``.
        db_kwargs: ADBC connection keyword arguments as ``dict[str, str]``.
            Required when using ``driver_path`` or ``dbapi_module``.
        entrypoint: ADBC entry-point symbol. Only used with ``driver_path``
            (e.g. ``"duckdb_adbc_init"`` for DuckDB). Default: ``None``.
        dbapi_module: Dotted module name for a Python package implementing
            the ADBC dbapi interface (e.g. ``"adbc_driver_snowflake.dbapi"``
            or a custom ``"my_driver.dbapi"``). Requires ``db_kwargs``.
            Mutually exclusive with ``config`` and ``driver_path``.
        pool_size: Number of connections to keep in the pool. Default: 5.
        max_overflow: Extra connections allowed above pool_size. Default: 3.
        timeout: Seconds to wait for a connection before raising. Default: 30.
        recycle: Seconds before a connection is recycled. Default: 3600.
        pre_ping: Whether to ping connections before checkout. Default: False.

    Yields:
        A configured ``sqlalchemy.pool.QueuePool``. The pool is automatically
        closed when the ``with`` block exits.

    Raises:
        TypeError: If none of ``config``, ``driver_path``, or ``dbapi_module``
            is provided, or if both ``driver_path`` and ``dbapi_module`` are
            provided.
        ImportError: If the required ADBC driver is not installed.

    Example:
        Config path:

        ```python
        from adbc_poolhouse import DuckDBConfig, managed_pool

        with managed_pool(DuckDBConfig(database="/tmp/wh.db")) as pool:
            with pool.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
        ```

        Raw native driver path:

        ```python
        with managed_pool(
            driver_path="/path/to/libduckdb.dylib",
            db_kwargs={"path": "/tmp/my.db"},
            entrypoint="duckdb_adbc_init",
        ) as pool:
            with pool.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 42")
        ```
    """
    pool = _create_pool_impl(
        config,
        driver_path,
        db_kwargs,
        entrypoint,
        dbapi_module,
        pool_size,
        max_overflow,
        timeout,
        recycle,
        pre_ping,
    )
    try:
        yield pool
    finally:
        close_pool(pool)


def _release_arrow_allocators(
    dbapi_conn: object,
    connection_record: object,
    reset_state: object,
) -> None:
    """
    Close any open cursors to release Arrow record batch readers.

    Registered on the pool ``reset`` event, which fires on all connection
    return paths: normal checkin, invalidation, and error. The ``reset``
    event is preferred over ``checkin`` because ``checkin`` receives
    ``None`` as ``dbapi_conn`` when the connection is invalidated.

    ADBC connections store open cursors in ``_cursors: weakref.WeakSet``.
    Iterating and closing them releases Arrow streaming memory.
    """
    if dbapi_conn is None:
        return
    for cur in list(getattr(dbapi_conn, "_cursors", [])):
        if not getattr(cur, "_closed", True):
            with contextlib.suppress(Exception):
                cur.close()
