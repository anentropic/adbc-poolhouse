"""
Connection-backend seam for non-ADBC pool sources.

The pool factory builds a `sqlalchemy.pool.QueuePool` from an ADBC "source"
connection and its ``adbc_clone`` method. That source+clone shape is specific to
the ADBC driver manager. A `ConnectionBackend` generalizes the three things the
factory actually needs from a source — a creator callable, a teardown, and a
pool-reset hook — so a driver without ``adbc_clone`` (e.g. the Databricks Python
connector) can back a pool too.

This module holds only the connector-agnostic protocol; each concrete backend
lives beside its connector in `adbc_poolhouse._adapters` (e.g.
`DatabricksPythonBackend`). Only the config path uses this seam:
`BaseWarehouseConfig._make_backend` returns ``None`` for every ADBC config (the
factory keeps its unchanged ADBC path) and a `ConnectionBackend` for a native one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable


@runtime_checkable
class ConnectionBackend(Protocol):
    """
    Everything the pool factory needs from a non-ADBC connection source.

    Implementations supply a creator callable for
    `sqlalchemy.pool.QueuePool`, a teardown for any shared state, and a hook run
    on the pool ``reset`` event to release per-connection resources.
    """

    def creator(self) -> Callable[[], Any]:
        """Return the callable QueuePool invokes to open each pooled connection."""
        ...

    def close(self) -> None:
        """Tear down any shared source (a no-op for stateless backends)."""
        ...

    def on_reset(self, dbapi_conn: object) -> None:
        """Release per-connection resources when a connection returns to the pool."""
        ...
