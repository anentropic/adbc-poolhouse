"""
`AsyncPool`: the async pool wrapper owning its dedicated `CapacityLimiter`.

`AsyncPool` wraps a synchronous SQLAlchemy `QueuePool` (built unchanged by the
sync factory) and adds the async surface. It owns ONE dedicated
`anyio.CapacityLimiter(pool_size + max_overflow)` --- never anyio's global
40-token default --- so concurrency is bounded to exactly the pool's checkout
ceiling (CORE-02). Every blocking call goes through the single
[`offload`][adbc_poolhouse._async._offload.offload] chokepoint with that limiter,
except the checkout itself, which runs under a second limiter of the same size
so a task waiting for a free connection never holds a token that a connection
holder needs to give one back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio

from adbc_poolhouse._async._connection import AsyncConnection
from adbc_poolhouse._async._offload import offload
from adbc_poolhouse._pool_factory import close_pool

if TYPE_CHECKING:
    import sqlalchemy.pool


class AsyncPool:
    """
    Async wrapper over a synchronous ADBC `QueuePool`.

    Created by [`create_async_pool`][adbc_poolhouse.create_async_pool]. The pool
    construction itself is synchronous (it does no per-call I/O); only `connect`
    and `close` are offloaded to worker threads.

    The pool owns one dedicated `anyio.CapacityLimiter` sized to
    `pool_size + max_overflow`, shared by every offloaded call on its connections
    and by `close`. A limiter token is borrowed only for the duration of each
    individual call (transient-token model, D-24-01), so a checked-out connection
    holds no token between calls and the worst-case in-flight offload count
    exactly fits the limiter.

    `connect` runs under a separate checkout limiter of the same size. With more
    concurrent tasks than connections, the extra tasks block inside
    `QueuePool.connect()` until a connection comes back. If they held tokens from
    the shared limiter while blocked, the tasks holding connections could not run
    the `execute`, `fetch` or `close` that returns one, and every waiter would
    stall until the pool's `timeout`. Keeping checkout on its own limiter means
    holders always find a token. At most `pool_size + max_overflow` worker
    threads wait in checkout; further callers wait on the event loop.

    Attributes:
        _limiter: The pool's dedicated `anyio.CapacityLimiter`. Exposed for tests
            that assert token accounting (e.g. `pool._limiter.borrowed_tokens`).
        _checkout_limiter: The limiter `connect` offloads `QueuePool.connect()`
            under, kept separate from `_limiter` so checkout waiters cannot
            starve connection holders.

    Example:
        ```python
        import anyio
        from adbc_poolhouse import DuckDBConfig, create_async_pool, close_async_pool


        async def main():
            pool = create_async_pool(DuckDBConfig(database="/tmp/wh.db"))
            try:
                async with await pool.connect() as conn:
                    cur = conn.cursor()  # synchronous, no await
                    await cur.execute("SELECT 42")
                    table = await cur.fetch_arrow_table()
                    print(table.num_rows)
            finally:
                await close_async_pool(pool)


        anyio.run(main)
        ```
    """

    def __init__(
        self,
        sync_pool: sqlalchemy.pool.QueuePool,
        *,
        pool_size: int,
        max_overflow: int,
    ) -> None:
        """
        Wrap a sync pool and build its dedicated limiter.

        Args:
            sync_pool: The synchronous `QueuePool` built by the sync factory.
            pool_size: The pool's steady-state connection count. Must match the
                value passed to the sync pool.
            max_overflow: Extra connections allowed above `pool_size`. Must match
                the value passed to the sync pool.
        """
        self._pool = sync_pool
        # Dedicated per-pool limiter sized to the checkout ceiling --- never the
        # anyio global 40-token default (CORE-02).
        self._limiter = anyio.CapacityLimiter(pool_size + max_overflow)
        # Checkout gets its own limiter: a `connect()` blocked waiting for a free
        # connection must not hold a `_limiter` token, or the holders that would
        # free one cannot run their execute/fetch/close (they need that token).
        self._checkout_limiter = anyio.CapacityLimiter(pool_size + max_overflow)

    async def connect(self) -> AsyncConnection:
        """
        Check out a connection from the pool on a worker thread.

        The blocking `QueuePool.connect()` runs through the offload chokepoint
        under the pool's checkout limiter, not the limiter its connections use,
        so a checkout that waits for a free connection never blocks the holders
        that would return one. The borrowed token is released as soon as the
        checkout returns (transient-token model). The returned `AsyncConnection`
        belongs to exactly one task --- do not share it across concurrent tasks.

        Returns:
            An `AsyncConnection` wrapping the checked-out sync connection.
        """
        fairy = await offload(self._pool.connect, limiter=self._checkout_limiter)
        return AsyncConnection(fairy, self._limiter)

    async def close(self) -> None:
        """
        Dispose the pool and close its ADBC source, shielded from cancellation.

        The blocking teardown (`close_pool`, which disposes the pool and closes
        the underlying ADBC source connection) is offloaded under the pool limiter
        and wrapped in `anyio.CancelScope(shield=True)`, so a cancellation
        arriving mid-close cannot abandon the pool with leaked driver resources.
        """
        with anyio.CancelScope(shield=True):
            await offload(close_pool, self._pool, limiter=self._limiter)
