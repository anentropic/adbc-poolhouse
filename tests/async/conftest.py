"""
Async-suite fixtures: dual-backend parametrization, real DuckDB pool, stub plumbing.

The `anyio_backend` fixture is a VERBATIM mirror of the one in
`tests/_async_harness/conftest.py`, defined HERE (inside `tests/async/`) and
nowhere higher. pytest conftest fixtures propagate DOWNWARD only, so confining it
to this directory keeps the synchronous suite (`tests/test_*.py`, which sits
above this package) out of the anyio plugin entirely --- hoisting it to the root
conftest, or setting `anyio_mode = "auto"`, would force every sync test through
the plugin and break PKG-04 (the sync suite must pass with anyio absent). This
is RESEARCH Pitfall 6, and the threat register's T-24-04-COLL: the lifecycle and
EDGE tests below all live at/below this conftest so the fixture is visible to
them, and only to them.

The fixtures fall into two groups:

- A real-driver DuckDB `AsyncPool` (`duckdb_async_pool`) for the happy-path
  lifecycle, the EDGE-09 token-accounting legs, and the EDGE-21 Arrow-lifetime
  proof --- everything that needs a genuine `pyarrow.Table` and a real check-in.
- Stub-backed plumbing (`make_stub_async_connection`) that wraps a Phase 23
  `BlockingStubConnection` / `BlockingStubCursor` in a real `AsyncConnection`, so
  the limiter / aliasing / loop-hygiene EDGE tests can gate a worker
  deterministically (block it inside `execute`, assert, then release) without a
  live driver.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import trio.testing

from adbc_poolhouse import DuckDBConfig, create_async_pool
from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from adbc_poolhouse._async._pool import AsyncPool


@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: pytest.FixtureRequest) -> object:
    """
    Parametrize async tests over the asyncio and trio backends (D-06).

    Verbatim mirror of `tests/_async_harness/conftest.py::anyio_backend`. Used by
    anyio's pytest plugin: every `@pytest.mark.anyio` test that requests this
    fixture (directly or via `anyio_backend_name`) runs once per backend. The trio
    leg returns the `("trio", {options})` tuple so anyio forwards a
    `trio.testing.MockClock(autojump_threshold=0)` into the trio loop, making
    virtual deadlines fire with no wall-clock cost.

    Function-scoped on purpose: a fresh `MockClock` per test prevents virtual-time
    bleed between tests.

    Args:
        request: The pytest fixture request; `request.param` is `"asyncio"` or
            `"trio"`.

    Returns:
        `"asyncio"` for the asyncio leg, or the
        `("trio", {"clock": MockClock(autojump_threshold=0)})` tuple for the trio
        leg, which anyio splits into the backend name plus runner options.
    """
    if request.param == "trio":
        return ("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})
    return "asyncio"


@pytest.fixture
async def duckdb_async_pool() -> AsyncIterator[AsyncPool]:
    """
    A real-driver DuckDB `AsyncPool` on a temp file, closed on teardown.

    Backs every test that needs a genuine ADBC round-trip --- the happy-path
    lifecycle, the EDGE-09 token-accounting legs, and the EDGE-21 Arrow-lifetime
    proof. A file-backed (not `:memory:`) database is used so a checked-in
    connection's state survives across checkouts within the test. The pool is
    disposed and its ADBC source closed via `pool.close()` on teardown.

    Yields:
        A ready `AsyncPool` wrapping a real in-process DuckDB driver.
    """
    tmpdir = tempfile.mkdtemp()
    pool = create_async_pool(DuckDBConfig(database=str(Path(tmpdir) / "async_edge.db")))
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
def make_stub_async_connection() -> Callable[[], tuple[AsyncConnection, BlockingStubConnection]]:
    """
    Factory: a real `AsyncConnection` wrapping a Phase 23 blocking stub.

    Returns a zero-argument factory so a test can build as many independent
    stub-backed connections as it needs (e.g. EDGE-12's flood). Each call wires a
    fresh [`BlockingStubConnection`][tests._async_harness.stubs.BlockingStubConnection]
    as the "fairy" behind a genuine
    [`AsyncConnection`][adbc_poolhouse._async._connection.AsyncConnection]: the
    `AsyncConnection` offloads `cursor().execute(...)` etc. straight onto the
    stub's blocking methods, so a test can gate a worker inside `execute` (it
    blocks on the stub's internal event), assert the limiter / aliasing / off-loop
    invariant, then release it.

    The connection's own limiter is supplied per call by the test (via the
    returned `AsyncConnection`'s `_limiter`), so the factory hands back BOTH the
    connection and its backing stub-connection for assertions
    (`stub_conn.cursors[0]` is the `BlockingStubCursor` the worker blocks in).

    Returns:
        A factory producing `(async_connection, stub_connection)` pairs. The
        caller sets up a limiter and gates the stub cursor; the
        `BlockingStubCursor` is reachable via `stub_connection.cursors`.
    """
    import anyio

    def _factory() -> tuple[AsyncConnection, BlockingStubConnection]:
        stub_conn = BlockingStubConnection()
        # A generously sized default limiter; tests that assert a bound build
        # their own connection with an explicitly sized limiter instead.
        limiter = anyio.CapacityLimiter(8)
        # AsyncConnection treats its first arg as the SQLAlchemy fairy and calls
        # .cursor()/.commit()/.rollback()/.close() on it; BlockingStubConnection
        # exposes exactly that surface, so it slots in unchanged. The cast keeps
        # basedpyright happy without affecting runtime behaviour.
        async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
        return async_conn, stub_conn

    return _factory
