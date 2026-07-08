"""
Connection-backend abstraction for non-ADBC pool sources.

The pool factory builds a `sqlalchemy.pool.QueuePool` from an ADBC "source"
connection and its ``adbc_clone`` method. That source+clone shape is specific to
the ADBC driver manager. A `ConnectionBackend` generalizes the three things the
factory actually needs from a source — a creator callable, a teardown, and a
pool-reset hook — so a driver without ``adbc_clone`` (the Databricks Python
connector) can back a pool too.

Only the config path uses this seam: `BaseWarehouseConfig._make_backend` returns
``None`` for every ADBC config (the factory keeps its unchanged ADBC path) and a
`ConnectionBackend` for a native one.
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


class NativeConnectorBackend:
    """
    A `ConnectionBackend` backed by the Databricks Python connector.

    Each pooled connection is an independent connector connection (there is no
    cheap ``adbc_clone``), opened through the module-level
    ``_databricks_python_driver.connect`` so `pytest-adbc-replay` can intercept
    it. There is no shared source to close; the reset hook closes any open
    cursors to release Arrow/CloudFetch buffers.

    Args:
        connect_kwargs: Connector kwargs from
            ``DatabricksPythonConfig.to_connect_kwargs()``.
    """

    def __init__(self, connect_kwargs: dict[str, Any]) -> None:
        self._connect_kwargs = connect_kwargs

    def creator(self) -> Callable[[], Any]:
        """
        Return a callable that opens one connector connection.

        The callable resolves ``connect`` off the driver module at call time (not
        import time) so a `pytest-adbc-replay` monkeypatch of the module's
        ``connect`` is honored.
        """
        # Import the module (not the function) so attribute access happens at
        # call time and picks up any patched connect.
        from adbc_poolhouse import _databricks_python_driver as driver  # noqa: PLC0415

        kwargs = self._connect_kwargs

        def _open() -> Any:
            return driver.connect(**kwargs)

        return _open

    def close(self) -> None:
        """No shared source to close; pooled connections are closed by ``dispose``."""

    def on_reset(self, dbapi_conn: object) -> None:
        """Close open cursors on ``dbapi_conn`` to release Arrow buffers, if it tracks any."""
        closer = getattr(dbapi_conn, "_close_open_cursors", None)
        if closer is not None:
            closer()
