"""
Backend-dispatching virtual-clock facade for the async harness (Phase 23, D-01).

A single helper,
[`virtual_clock`][tests._async_harness.clock.virtual_clock], gives the timeout /
deadline tests one entry point that advances time virtually on BOTH anyio
backends -- so `anyio.fail_after` / `move_on_after` fire instantly with no
wall-clock cost. Event-gating (see
[`gating.py`][tests._async_harness.gating]) remains the PRIMARY mechanism for
cancel-path determinism (D-02); the virtual clock covers the deadline / timeout
paths.

The two backends inject virtual time in structurally different ways, which is
WHY the facade dispatches on the backend name (D-01):

- trio: the `trio.testing.MockClock(autojump_threshold=0)` is injected at the
  RUNNER by the `anyio_backend` fixture (it forwards `clock=` straight to the
  trio guest run). There is nothing to do in-body, so the trio leg is a bare
  `yield`.
- asyncio: there is no runner hook, so the clock is patched IN-BODY with
  `aiotools.VirtualClock().patch_loop()`, a sync context manager that patches
  the running loop's clock for the duration of the `with` block.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import aiotools

if TYPE_CHECKING:
    from collections.abc import Generator


@contextlib.contextmanager
def virtual_clock(anyio_backend_name: str) -> Generator[None]:
    """
    Enter the right virtual-clock mechanism for the active anyio backend (D-01).

    On the trio leg the clock is already injected at the runner (via the
    `anyio_backend` fixture), so this is a no-op `yield`. On the asyncio leg
    there is no runner hook, so it patches the running loop in-body with
    `aiotools.VirtualClock().patch_loop()`. Either way, inside the `with` block
    `anyio.fail_after` / `move_on_after` advance on virtual time and fire without
    consuming wall-clock.

    Args:
        anyio_backend_name: The active backend, `"asyncio"` or `"trio"` (the
            `anyio_backend_name` fixture anyio provides to parametrized tests).

    Yields:
        `None`. The helper is used purely for its context-manager side effect of
        installing the virtual clock for the body's duration.

    Example:
        ```python
        import anyio
        import pytest

        from tests._async_harness.clock import virtual_clock


        @pytest.mark.anyio
        async def test_deadline_fires(anyio_backend_name: str) -> None:
            with virtual_clock(anyio_backend_name):
                with anyio.fail_after(5):  # fires on virtual time, no wall-clock
                    await anyio.sleep(3600)
        ```
    """
    if anyio_backend_name == "trio":
        # Clock already injected at the runner; nothing to do in-body.
        yield
    else:  # asyncio
        with aiotools.VirtualClock().patch_loop():
            yield
