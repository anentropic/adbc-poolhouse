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
    abandon_on_cancel: bool = False,
) -> object:
    """
    Offload a blocking stub call onto a worker thread, bridging `entered`.

    Runs `stub_call(*args)` -- which blocks on the stub's internal
    `threading.Event` -- on an anyio worker thread via `to_thread.run_sync`, and
    signals `entered` on the event loop from INSIDE the stub's blocked section
    via the stub's `on_enter` hook (NOT before the stub call runs). The async
    caller does `await entered.wait()` to know, with no poll and no sleep, that
    the worker is genuinely inside the blocked call, and only then triggers the
    release / cancel / timeout (Pattern 3, Pitfall 2, D-CF-01).

    Entered-after-block (D-CF-01): an earlier design fired `entered` before the
    stub call ran, so `await entered.wait()` only meant "the worker started," not
    "the worker is inside the block." With a re-armable gate that gap let a worker
    register its wait AFTER the test's `release()`, then wait on a never-set event
    forever (the WR-01 deadlock). Bridging `entered` through the stub's `on_enter`
    -- which the stub invokes after recording concurrency and before waiting --
    makes `await entered.wait()` a true "inside the block" signal, so a re-armable
    cursor (`execute` then `fetch_arrow_table`) gates correctly with no race.

    NON-cancellable by design (WR-04): with the default `abandon_on_cancel=False`,
    `to_thread.run_sync` does NOT abandon the worker on cancellation. If the
    surrounding task group or a `fail_after` cancels while the worker is blocked,
    the loop will WAIT to join the worker at scope exit -- and the worker stays
    blocked until SOME OTHER actor releases the stub. Consumers MUST therefore
    release / `adbc_cancel` / `close` the stub to unblock the worker; the loop
    will not reclaim it on cancel. A consumer that wraps this in `fail_after`
    without separately poking the stub will deadlock at scope exit. Pass
    `abandon_on_cancel=True` to opt into the cancellable variant for the timeout
    EDGE cases, where the loop abandons the still-running worker on cancel
    instead of waiting to join it.

    Because the `on_enter` hook runs on the same anyio worker thread as the stub
    call, `anyio.from_thread.run_sync(entered.set)` reaches the loop with NO
    `token=` argument -- a token is only needed when calling in from a foreign
    (non-anyio) thread.

    The hook is registered per worker thread via `register_on_enter` from INSIDE
    the offload, so two workers blocking on the SAME cursor at once (the
    max-concurrent path) each bridge their OWN loop-facing event with no clobber,
    and the registration is removed in a `finally` so a reused cursor is never
    left with a dangling per-thread bridge. This requires the offloaded
    `stub_call` be a bound method of a stub exposing `register_on_enter` (the
    `BlockingStubCursor` contract).

    Args:
        stub_call: The blocking callable to offload, e.g. a
            [`BlockingStubCursor`][tests._async_harness.stubs.BlockingStubCursor]
            `execute` / `fetch_arrow_table` bound method. Its `__self__` must
            expose `register_on_enter` (the worker-entry hook bridged to
            `entered`).
        *args: Positional arguments forwarded to `stub_call`.
        entered: The loop-facing gate. This MUST be an `anyio.Event` -- it is
            what makes "wait until the worker is inside execute" deterministic on
            the loop: the test creates it, passes it here, and `await
            entered.wait()`s it. It is set from inside the stub's blocked section
            via the `on_enter` bridge. This is DISTINCT from
            [`BlockingStubCursor.entered`][tests._async_harness.stubs.BlockingStubCursor],
            which is a `threading.Event` (the SYNC signal for pure-threading
            self-tests). They share a name but are different objects: never pass
            the stub's `threading.Event` here, and never await the stub's
            `entered` on the loop (that reintroduces the worker-entry race).
        limiter: The `anyio.CapacityLimiter` passed explicitly to
            `to_thread.run_sync`. Passing it by keyword is mandatory -- it is the
            compliant shape the Plan 03 guard enforces.
        abandon_on_cancel: Forwarded to `to_thread.run_sync`. Defaults to `False`
            (the offload is NON-cancellable -- see the warning above). Pass `True`
            in a timeout EDGE case to let the loop abandon the still-blocked
            worker on cancel instead of waiting to join it. Additive and
            default-false, so existing callers are unaffected.

    Returns:
        Whatever `stub_call(*args)` returns once it is released (e.g. `None` from
        `execute`, or the fake's `fetch_arrow_table` result).
    """

    def _on_enter() -> None:
        # Runs INSIDE the stub's blocked section, on the anyio worker thread, so
        # from_thread.run_sync needs no token. Bridges the loop-facing anyio.Event
        # only once the worker is genuinely inside the block (D-CF-01).
        anyio.from_thread.run_sync(entered.set)

    stub = stub_call.__self__  # type: ignore[attr-defined]

    def _worker() -> object:
        # Register this worker thread's entry hook from INSIDE the offload so
        # concurrent workers on one cursor each bridge their own event; clean up
        # the per-thread registration on the way out.
        cleanup = stub.register_on_enter(_on_enter)
        try:
            return stub_call(*args)  # blocks on the stub's threading.Event
        finally:
            cleanup()

    return await anyio.to_thread.run_sync(
        _worker, limiter=limiter, abandon_on_cancel=abandon_on_cancel
    )
