"""
`AsyncPool`: the async pool wrapper owning its dedicated `CapacityLimiter`.

`AsyncPool` wraps a synchronous SQLAlchemy `QueuePool` (built unchanged by the
sync factory) and adds the async surface. It owns ONE dedicated
`anyio.CapacityLimiter(pool_size + max_overflow)` --- never anyio's global
40-token default --- so concurrency is bounded to exactly the pool's checkout
ceiling (CORE-02). Every blocking call goes through the single
[`offload`][adbc_poolhouse._async._offload.offload] chokepoint with that limiter.
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
    `pool_size + max_overflow`, shared by every offloaded call on the pool and its
    connections. A limiter token is borrowed only for the duration of each
    individual call (transient-token model, D-24-01), so a checked-out connection
    holds no token between calls and the worst-case in-flight offload count
    exactly fits the limiter.

    Attributes:
        _limiter: The pool's dedicated `anyio.CapacityLimiter`. Exposed for tests
            that assert token accounting (e.g. `pool._limiter.borrowed_tokens`).
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

    async def connect(self) -> AsyncConnection:
        """
        Check out a connection from the pool on a worker thread.

        The blocking `QueuePool.connect()` runs through the offload chokepoint
        under the pool limiter; the borrowed token is released as soon as the
        checkout returns (transient-token model). The returned `AsyncConnection`
        belongs to exactly one task --- do not share it across concurrent tasks.

        Returns:
            An `AsyncConnection` wrapping the checked-out sync connection.
        """
        fairy = await offload(self._pool.connect, limiter=self._limiter)
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
