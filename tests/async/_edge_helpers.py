"""
Shared gating helpers for the Phase 24 EDGE suite (watchdog + inside-poll).

Two load-bearing utilities the concurrency EDGE tests reuse:

- `real_clock_watchdog`: a wall-clock side-thread watchdog that `close()`s a
  blocking stub if the body overruns, so a gating regression that strands a
  non-cancellable worker FAILS FAST instead of hanging CI. It is deliberately NOT
  `anyio.fail_after`: under the trio leg's `MockClock(autojump_threshold=0)` a
  virtual `fail_after` autojumps to its OWN deadline the instant every task is
  blocked off-loop, so it would trip spuriously every run (Plan 01 lesson, MEMORY
  MockClock gotcha). The watchdog gives the same "no test ever hangs" guarantee
  the `fail_after` wording in the plan asks for, measured on real time.
- `await_inside`: the bounded `anyio.sleep(0)` poll from the harness, used to wait
  until a gated worker is provably inside the stub's blocked section before
  asserting (the production `offload` path has no `entered` bridge, so we poll the
  stub's lock-guarded counters instead).
"""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING

import anyio

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from tests._async_harness.stubs import BlockingStubCursor

# Bound for the inside-poll: each iteration is one `anyio.sleep(0)` checkpoint (no
# wall-clock), so this is just a generous ceiling on scheduler hand-offs.
_ENTRY_POLL_TRIES = 100_000


@contextlib.contextmanager
def real_clock_watchdog(
    cursors: list[BlockingStubCursor],
    budget_s: float = 5.0,
) -> Generator[list[bool]]:
    """
    Break stranded non-cancellable workers open after `budget_s` REAL seconds.

    A side thread waits `budget_s` on the wall clock; if the body has not exited by
    then it `close()`s every supplied stub cursor, releasing any worker still
    blocked in `_block` so the task group can exit and the post-body assertion
    trips --- a gating regression fails fast instead of hanging. This is the
    real-clock substitute for the plan's `anyio.fail_after` watchdog: a virtual
    `fail_after` would autojump to its own deadline under the trio `MockClock` the
    instant the workers block off-loop and trip every run.

    Args:
        cursors: The stub cursors whose blocked workers must be released on a
            timeout.
        budget_s: Real wall-clock seconds to wait before forcing the stubs open.

    Yields:
        A one-element list whose single `bool` is `True` iff the watchdog fired;
        assert it is `False` after the body to prove no worker hung.
    """
    tripped = [False]
    done = threading.Event()

    def _watch() -> None:
        if not done.wait(timeout=budget_s):
            tripped[0] = True
            for cur in cursors:
                cur.close()  # release any stranded worker so the group can exit

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()
    try:
        yield tripped
    finally:
        done.set()
        watcher.join(timeout=budget_s)


async def await_inside(predicate: Callable[[], bool]) -> bool:
    """
    Yield (`anyio.sleep(0)` only) until `predicate()` holds or the bound is hit.

    The production `offload` path has no loop-facing `entered` event, so a test
    that needs "the worker is now inside the blocked stub call" polls the stub's
    lock-guarded counters here instead. Each iteration is a pure `sleep(0)`
    checkpoint (no wall-clock), so this settles deterministically under both the
    asyncio and trio MockClock legs. Returns the final `predicate()` value so the
    caller can assert on a settled observation.

    Args:
        predicate: A zero-argument check on the stub state to wait for.

    Returns:
        `True` if `predicate()` became true within the bound, else its final value.
    """
    for _ in range(_ENTRY_POLL_TRIES):
        if predicate():
            return True
        await anyio.sleep(0)
    return predicate()
