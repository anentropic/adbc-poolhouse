"""
Pool factory: public create_pool() entry point.

This module wires together config translation, driver resolution, and
the ADBC source+clone pattern to create a SQLAlchemy QueuePool.

No module-level pool or connection objects exist here (POOL-05).

Internal helpers are prefixed with _ and not exported.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import sqlalchemy.pool
from sqlalchemy import event

from adbc_poolhouse._driver_api import create_adbc_connection
from adbc_poolhouse._drivers import resolve_driver
from adbc_poolhouse._translators import translate_config

if TYPE_CHECKING:
    import collections.abc

    from adbc_poolhouse._base_config import WarehouseConfig


def create_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool:
    """
    Create a SQLAlchemy QueuePool backed by an ADBC warehouse driver.

    Accepts any supported warehouse config model and returns a ready-to-use
    ``sqlalchemy.pool.QueuePool``. The pool uses the official ADBC
    ``adbc_clone`` pattern: one source connection is created, and each pool
    checkout calls ``source.adbc_clone()`` to open a new connection sharing
    the same underlying ``AdbcDatabase`` via reference counting.

    An Arrow allocator cleanup listener is registered on the pool's ``reset``
    event. Any cursors left open when a connection is returned to the pool are
    closed automatically, releasing Arrow record batch reader memory (POOL-04).

    The source connection is attached to the pool as ``pool._adbc_source``.
    To shut down cleanly, call :func:`close_pool`::

        close_pool(pool)

    Args:
        config: A warehouse config model instance (e.g. ``DuckDBConfig``).
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
        ImportError: If the required ADBC driver is not installed.
        TypeError: If ``config`` is not a recognised warehouse config type.
    """
    driver_path = resolve_driver(config)
    kwargs = translate_config(config)
    entrypoint = config._adbc_entrypoint()

    source = create_adbc_connection(driver_path, kwargs, entrypoint=entrypoint)

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


def close_pool(pool: sqlalchemy.pool.QueuePool) -> None:
    """
    Dispose a pool and close its underlying ADBC source connection.

    Replaces the two-step pattern ``pool.dispose()`` followed by
    ``pool._adbc_source.close()``. Always call this instead of calling
    ``pool.dispose()`` directly to avoid leaving the ADBC source connection open.

    Args:
        pool: A pool returned by :func:`create_pool`.

    Example:
        from adbc_poolhouse import DuckDBConfig, create_pool, close_pool

        pool = create_pool(DuckDBConfig(database='/tmp/wh.db'))
        # ... use pool ...
        close_pool(pool)
    """
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]


@contextlib.contextmanager
def managed_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> collections.abc.Iterator[sqlalchemy.pool.QueuePool]:
    """
    Context manager that creates a pool and closes it on exit.

    The pool is created when the ``with`` block is entered and closed
    (via :func:`close_pool`) when the block exits, whether it exits normally
    or raises an exception.

    Args:
        config: A warehouse config model instance (e.g. ``DuckDBConfig``).
        pool_size: Number of connections to keep in the pool. Default: 5.
        max_overflow: Extra connections allowed above pool_size. Default: 3.
        timeout: Seconds to wait for a connection before raising. Default: 30.
        recycle: Seconds before a connection is recycled. Default: 3600.
        pre_ping: Whether to ping connections before checkout. Default: False.

    Yields:
        A configured ``sqlalchemy.pool.QueuePool``.

    Example:
        from adbc_poolhouse import DuckDBConfig, managed_pool

        with managed_pool(DuckDBConfig(database='/tmp/wh.db')) as pool:
            with pool.connect() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1')
    """
    pool = create_pool(
        config,
        pool_size=pool_size,
        max_overflow=max_overflow,
        timeout=timeout,
        recycle=recycle,
        pre_ping=pre_ping,
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
