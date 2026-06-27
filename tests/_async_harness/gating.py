"""
Offload glue + worker->loop `entered` bridge for the async harness (Phase 23).

This is the module where anyio lives -- deliberately, and in contrast to
[`stubs.py`][tests._async_harness.stubs], which stays pure-`threading` so the
fakes are framework-neutral (D-03). The single public helper,
[`run_blocking`][tests._async_harness.gating.run_blocking], models the offload
shape the Phase 24 async wrappers will use: it runs a blocking stub call on an
anyio worker thread (`anyio.to_thread.run_sync`) and bridges an `entered` signal
back to the event loop so a test can deterministically wait until the worker is
actually inside the blocked call before triggering cancel / timeout (Pattern 3).

The explicit `limiter=` keyword on `to_thread.run_sync` is load-bearing: it is
the compliant call shape the Plan 03 source-scan guard enforces (a bare
`to_thread.run_sync(...)` without `limiter=` is banned), so the harness models
exactly what later code must do.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import anyio.from_thread
import anyio.to_thread

if TYPE_CHECKING:
    from collections.abc import Callable


async def run_blocking(
    stub_call: Callable[..., object],
    *args: object,
    entered: anyio.Event,
    limiter: anyio.CapacityLimiter,
) -> object:
    """
    Offload a blocking stub call onto a worker thread, bridging `entered`.

    Runs `stub_call(*args)` -- which blocks on the stub's internal
    `threading.Event` -- on an anyio worker thread via `to_thread.run_sync`, and
    signals `entered` on the event loop the instant the worker starts (before it
    blocks). The async caller does `await entered.wait()` to know, with no poll
    and no sleep, that the worker is inside the blocked call, and only then
    triggers the release / cancel / timeout (Pattern 3, Pitfall 2).

    Because `_worker` already runs on an anyio worker thread,
    `anyio.from_thread.run_sync(entered.set)` reaches the loop with NO `token=`
    argument -- a token is only needed when calling in from a foreign
    (non-anyio) thread.

    Args:
        stub_call: The blocking callable to offload, e.g. a
            [`BlockingStubCursor`][tests._async_harness.stubs.BlockingStubCursor]
            `execute` / `fetch_arrow_table` bound method.
        *args: Positional arguments forwarded to `stub_call`.
        entered: The loop-facing gate. This MUST be an `anyio.Event` -- it is
            what makes "wait until the worker is inside execute" deterministic on
            the loop: the test creates it, passes it here, and `await
            entered.wait()`s it. This is DISTINCT from
            [`BlockingStubCursor.entered`][tests._async_harness.stubs.BlockingStubCursor],
            which is a `threading.Event` (the SYNC signal for pure-threading
            self-tests). They share a name but are different objects: never pass
            the stub's `threading.Event` here, and never await the stub's
            `entered` on the loop (that reintroduces the worker-entry race).
        limiter: The `anyio.CapacityLimiter` passed explicitly to
            `to_thread.run_sync`. Passing it by keyword is mandatory -- it is the
            compliant shape the Plan 03 guard enforces.

    Returns:
        Whatever `stub_call(*args)` returns once it is released (e.g. `None` from
        `execute`, or the fake's `fetch_arrow_table` result).
    """

    def _worker() -> object:
        # On an anyio worker thread -> from_thread.run_sync needs no token.
        anyio.from_thread.run_sync(entered.set)  # signal the loop BEFORE blocking
        return stub_call(*args)  # blocks on the stub's threading.Event

    return await anyio.to_thread.run_sync(_worker, limiter=limiter)
