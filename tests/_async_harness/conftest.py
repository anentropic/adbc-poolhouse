"""
Nested anyio backend parametrization for the async harness (Phase 23, D-06).

The `anyio_backend` fixture is defined HERE, inside `tests/_async_harness/`,
rather than in the root `tests/conftest.py`, on purpose. pytest conftest
fixtures propagate DOWNWARD only -- to the conftest's own directory and its
subdirectories, never to a parent or sibling file. Two consequences follow,
both load-bearing:

1. The existing sync suite (`tests/test_configs.py`, `tests/test_pool_factory.py`,
   ...) sits ABOVE this directory, so it never sees `anyio_backend` and is never
   dragged under the anyio plugin. Hoisting the fixture into the root conftest --
   or setting `anyio_mode = "auto"` in `[tool.pytest.ini_options]` -- would force
   every sync test through the plugin and break collection (RESEARCH Pitfall 4;
   protects future PKG-04, where the sync suite must pass with anyio uninstalled).

2. The dual-backend self-tests that CONSUME `anyio_backend` (Plan 04) must live
   at or below this directory, i.e. `tests/_async_harness/test_harness.py`. A
   sibling file such as `tests/test_async_harness.py` would be a parent-level peer
   and would fail collection with `fixture 'anyio_backend' not found`. A
   `test_*.py` file inside this package is still collected normally -- collection
   of `test_*.py` is independent of the `__init__.py` package marker.
"""

from __future__ import annotations

import pytest
import trio.testing


@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: pytest.FixtureRequest) -> object:
    """
    Parametrize async tests over the asyncio and trio backends (D-06).

    Used by anyio's pytest plugin: every `@pytest.mark.anyio` test that requests
    this fixture (directly or via `anyio_backend_name`) runs once per backend. The
    trio leg returns the `("trio", {options})` tuple form so anyio forwards the
    options dict straight through to `trio.lowlevel.start_guest_run`, injecting a
    `trio.testing.MockClock(autojump_threshold=0)` into the trio loop. With
    `autojump_threshold=0` the clock jumps to the next scheduled deadline the
    instant every task is blocked, so `anyio.fail_after` / `move_on_after` fire on
    virtual time with no wall-clock cost (D-01, trio leg).

    The fixture is FUNCTION-scoped (the default) deliberately: it constructs a
    fresh `MockClock` for every test. A session- or module-scoped fixture would
    share one clock instance across tests in that scope, letting advanced virtual
    time bleed from one test into the next. Function scope keeps each test's clock
    isolated.

    Args:
        request: The pytest fixture request; `request.param` is `"asyncio"` or
            `"trio"` (the `params` list above).

    Returns:
        For the asyncio leg, the string `"asyncio"`. For the trio leg, the tuple
        `("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})`, which
        anyio splits into the backend name plus the options forwarded to the trio
        runner.

    Example:
        ```python
        import anyio
        import pytest


        @pytest.mark.anyio
        async def test_runs_on_both_backends(anyio_backend_name: str) -> None:
            assert anyio_backend_name in ("asyncio", "trio")
            with anyio.fail_after(3600):  # fires instantly under the trio MockClock
                await anyio.sleep(1)
        ```
    """
    if request.param == "trio":
        return ("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})
    return "asyncio"
