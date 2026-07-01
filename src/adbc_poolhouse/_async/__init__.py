"""
Async connection pooling for ADBC drivers (the optional `[async]` surface).

This package wraps the synchronous pool core in an anyio-based async API: it
reuses the unchanged sync factory (`_create_pool_impl`), config dispatch, and the
13-backend `WarehouseConfig` Protocol, offloading every blocking ADBC call to a
worker thread through the single [`offload`][adbc_poolhouse._async._offload.offload]
chokepoint, bounded by a per-pool `anyio.CapacityLimiter`.

It is imported lazily by the top-level package (PEP 562 `__getattr__`) so that a
plain `import adbc_poolhouse` stays anyio-free for synchronous users; `anyio` is
only required when an async entry point is first accessed.
"""

from adbc_poolhouse._async._factory import (
    close_async_pool,
    create_async_pool,
    managed_async_pool,
)

__all__ = [
    "close_async_pool",
    "create_async_pool",
    "managed_async_pool",
]
