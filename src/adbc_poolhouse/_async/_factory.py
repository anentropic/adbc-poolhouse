"""
Async pool factory: `create_async_pool` / `managed_async_pool` / `close_async_pool`.

These mirror the synchronous `create_pool` / `managed_pool` / `close_pool` entry
points exactly --- same three call patterns, same keyword defaults --- and reuse
the unchanged sync core (`_create_pool_impl`, `close_pool`) verbatim. There is no
per-backend code here: the factory touches only the `WarehouseConfig` Protocol and
the sync `QueuePool`, so all 13 backends are supported by construction (CORE-04,
D-24-04).

Pool construction stays synchronous --- `_create_pool_impl` does no per-call I/O,
so `create_async_pool` need not be a coroutine. Only `connect` / `close` (and the
per-call cursor methods in Plan 03) are offloaded to worker threads.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, overload

from adbc_poolhouse._async._pool import AsyncPool
from adbc_poolhouse._pool_factory import _create_pool_impl

if TYPE_CHECKING:
    import collections.abc

    from adbc_poolhouse._base_config import WarehouseConfig


@overload
def create_async_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> AsyncPool: ...


@overload
def create_async_pool(
    *,
    driver_path: str,
    db_kwargs: dict[str, str],
    entrypoint: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> AsyncPool: ...


@overload
def create_async_pool(
    *,
    dbapi_module: str,
    db_kwargs: dict[str, str],
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> AsyncPool: ...


def create_async_pool(
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
) -> AsyncPool:
    """
    Create an `AsyncPool` backed by an ADBC driver.

    The signature mirrors [`create_pool`][adbc_poolhouse.create_pool] exactly,
    with the same three call patterns and keyword defaults. The pool is built
    synchronously by the shared sync core (`_create_pool_impl`), then wrapped in an
    `AsyncPool` that owns a dedicated `anyio.CapacityLimiter(pool_size +
    max_overflow)`. There is no per-backend code, so any of the supported
    warehouse configs works.

    Three call patterns are supported:

        pool = create_async_pool(DuckDBConfig(...))           # from a config object
        pool = create_async_pool(driver_path="...", ...)       # native ADBC driver
        pool = create_async_pool(dbapi_module="...", ...)      # Python dbapi module

    Args:
        config: A warehouse config model instance (e.g. `DuckDBConfig`).
            Mutually exclusive with `driver_path` and `dbapi_module`.
        driver_path: Path to a native ADBC driver shared library, or a short
            driver name for manifest-based resolution. Requires `db_kwargs`.
            Mutually exclusive with `config` and `dbapi_module`.
        db_kwargs: ADBC connection keyword arguments as `dict[str, str]`. Required
            when using `driver_path` or `dbapi_module`.
        entrypoint: ADBC entry-point symbol. Only used with `driver_path`
            (e.g. `"duckdb_adbc_init"` for DuckDB). Default: `None`.
        dbapi_module: Dotted module name for a Python package implementing the ADBC
            dbapi interface (e.g. `"adbc_driver_snowflake.dbapi"`). Requires
            `db_kwargs`. Mutually exclusive with `config` and `driver_path`.
        pool_size: Number of connections to keep in the pool. Default: 5.
        max_overflow: Extra connections allowed above `pool_size`. Default: 3.
        timeout: Seconds to wait for a connection before raising. Default: 30.
        recycle: Seconds before a connection is recycled. Default: 3600.
        pre_ping: Whether to ping connections before checkout. Default: False.

    Returns:
        A configured `AsyncPool` ready for use.

    Raises:
        TypeError: If none of `config`, `driver_path`, or `dbapi_module` is
            provided, or if both `driver_path` and `dbapi_module` are provided.
        ImportError: If the required ADBC driver is not installed.

    Example:
        ```python
        import anyio
        from adbc_poolhouse import DuckDBConfig, create_async_pool, close_async_pool


        async def main():
            pool = create_async_pool(DuckDBConfig(database="/tmp/wh.db"))
            try:
                async with await pool.connect() as conn:
                    cur = conn.cursor()
                    await cur.execute("SELECT 1")
            finally:
                await close_async_pool(pool)


        anyio.run(main)
        ```
    """
    sync_pool = _create_pool_impl(
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
    return AsyncPool(sync_pool, pool_size=pool_size, max_overflow=max_overflow)


async def close_async_pool(pool: AsyncPool) -> None:
    """
    Dispose an `AsyncPool` and close its underlying ADBC source.

    The async analog of [`close_pool`][adbc_poolhouse.close_pool]. The blocking
    teardown runs on a worker thread inside a shielded cancel scope (in
    `AsyncPool.close`), so a cancellation cannot abandon the pool mid-close and
    leak driver resources.

    Args:
        pool: A pool returned by `create_async_pool`.

    Example:
        ```python
        from adbc_poolhouse import DuckDBConfig, create_async_pool, close_async_pool

        pool = create_async_pool(DuckDBConfig(database="/tmp/wh.db"))
        await close_async_pool(pool)
        ```
    """
    await pool.close()


@overload
def managed_async_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> contextlib.AbstractAsyncContextManager[AsyncPool]: ...


@overload
def managed_async_pool(
    *,
    driver_path: str,
    db_kwargs: dict[str, str],
    entrypoint: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> contextlib.AbstractAsyncContextManager[AsyncPool]: ...


@overload
def managed_async_pool(
    *,
    dbapi_module: str,
    db_kwargs: dict[str, str],
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> contextlib.AbstractAsyncContextManager[AsyncPool]: ...


@contextlib.asynccontextmanager
async def managed_async_pool(
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
) -> collections.abc.AsyncGenerator[AsyncPool, None]:
    """
    Async context manager that creates an `AsyncPool` and closes it on exit.

    The async analog of [`managed_pool`][adbc_poolhouse.managed_pool]. The pool is
    created when the `async with` block is entered and closed (via
    `close_async_pool`, whose teardown is shielded from cancellation) when the
    block exits, whether normally or by exception.

    Three call patterns are supported:

        async with managed_async_pool(DuckDBConfig(...)) as pool: ...        # config
        async with managed_async_pool(driver_path="...", ...) as pool: ...   # native
        async with managed_async_pool(dbapi_module="...", ...) as pool: ...  # dbapi

    Args:
        config: A warehouse config model instance (e.g. `DuckDBConfig`).
            Mutually exclusive with `driver_path` and `dbapi_module`.
        driver_path: Path to a native ADBC driver shared library, or a short
            driver name for manifest-based resolution. Requires `db_kwargs`.
            Mutually exclusive with `config` and `dbapi_module`.
        db_kwargs: ADBC connection keyword arguments as `dict[str, str]`. Required
            when using `driver_path` or `dbapi_module`.
        entrypoint: ADBC entry-point symbol. Only used with `driver_path`
            (e.g. `"duckdb_adbc_init"` for DuckDB). Default: `None`.
        dbapi_module: Dotted module name for a Python package implementing the ADBC
            dbapi interface (e.g. `"adbc_driver_snowflake.dbapi"`). Requires
            `db_kwargs`. Mutually exclusive with `config` and `driver_path`.
        pool_size: Number of connections to keep in the pool. Default: 5.
        max_overflow: Extra connections allowed above `pool_size`. Default: 3.
        timeout: Seconds to wait for a connection before raising. Default: 30.
        recycle: Seconds before a connection is recycled. Default: 3600.
        pre_ping: Whether to ping connections before checkout. Default: False.

    Yields:
        A configured `AsyncPool`, closed automatically when the block exits.

    Raises:
        TypeError: If none of `config`, `driver_path`, or `dbapi_module` is
            provided, or if both `driver_path` and `dbapi_module` are provided.
        ImportError: If the required ADBC driver is not installed.

    Example:
        ```python
        from adbc_poolhouse import DuckDBConfig, managed_async_pool

        async with managed_async_pool(DuckDBConfig(database="/tmp/wh.db")) as pool:
            async with await pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT 42")
        ```
    """
    sync_pool = _create_pool_impl(
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
    pool = AsyncPool(sync_pool, pool_size=pool_size, max_overflow=max_overflow)
    try:
        yield pool
    finally:
        await close_async_pool(pool)
