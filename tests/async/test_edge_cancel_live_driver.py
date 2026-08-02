"""
Live-driver cancel regression: poison-recovery must not race the aborted worker (D-25-09).

Every other cancel test in this suite gates a *stub* worker
([`BlockingStubCursor`][tests._async_harness.stubs.BlockingStubCursor]), whose
`adbc_cancel` returns the worker cleanly and instantly. That is exactly why none of
them caught this: with a stub, the window between "`adbc_cancel` fired" and "the
worker is out of the call" is empty, so running `on_abort` (the connection's
`invalidate`, which CLOSES the connection) immediately after `adbc_cancel` looked
safe. Against a real driver the window is real, and closing a connection whose
worker thread is still unwinding out of the C call wedges that thread forever ---
DuckDB deadlocks on it, deterministically.

The consequence is severe rather than cosmetic: `offload` runs with
`abandon_on_cancel=False`, so the awaiting task can never complete once the worker
is wedged. No enclosing `move_on_after` can rescue it --- a client disconnect during
a query hangs the request task permanently and leaks a thread plus a connection.
This is the same two-thread-on-one-connection hazard as CR-34-01, one step further
in: there the worker could not be aborted at all, here it can, but the abort takes
non-zero time and the recovery must wait for it.

**Why the drive loop runs on a side thread.** A wedged worker cannot be released by
anything the test can do --- there is no stub to `close()`, so
[`real_clock_watchdog`][tests.async._edge_helpers.real_clock_watchdog] has no
handle to pull. Awaiting the cancelled call on the main thread would therefore hang
the whole session on a regression. Instead the entire loop runs in a daemon thread
and the test waits on a `threading.Event` with a real-clock budget: a regression
fails this test in seconds and lets the rest of the suite run, which is the same
"no test ever hangs" guarantee `real_clock_watchdog` gives the stub legs.

The cancel is fired after a REAL (off-loop) settle so the worker is genuinely inside
DuckDB's C call, not merely dispatched --- the wall clock is the only signal a real
driver offers, and running it off-loop via a worker thread keeps it independent of
the trio `MockClock`. Both anyio backends are covered by explicit parametrization
(the loop is started by hand here, so the `anyio_backend` fixture does not apply).
Pre-fix each leg wedges when run on its own; the asyncio leg wedges unconditionally,
while the trio leg can slip through if the asyncio leg has already stranded a worker
inside the driver ahead of it. Post-fix both legs pass in any order --- which is what
this test is here to hold.
"""

from __future__ import annotations

import functools
import threading
import time
from typing import TYPE_CHECKING

import anyio
import anyio.to_thread
import pytest

from adbc_poolhouse import DuckDBConfig, create_async_pool

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from pathlib import Path

# A cross join filtered on a modulo match: ~5.7e9 result rows from a 200k-row build
# side, so it runs effectively forever on the wall clock while staying small in
# memory. It exists to be interrupted, never to finish.
_LONG_QUERY = (
    "SELECT count(*) FROM range(200000) a, range(200000) b WHERE a.range % 7 = b.range % 7"
)

# Real seconds to let the worker settle INSIDE the driver's C call before cancelling.
# Slept off-loop (on a worker thread) so the trio `MockClock` cannot autojump past it.
_SETTLE_S = 0.5

# Real seconds the driving loop is given to cancel, recover, and return. The fixed
# path needs a few milliseconds; the pre-fix path never returns at all, so this is
# purely the bound that converts a permanent wedge into a prompt failure.
_BUDGET_S = 20.0


def _drive_cancelled_query(
    backend: str,
    database: str,
    outcome: MutableMapping[str, object],
    completed: threading.Event,
) -> None:
    """
    Run one cancelled real-DuckDB query to completion in a private event loop.

    Executed on a daemon side thread so a wedged worker cannot hang the pytest main
    thread. Records what happened in `outcome` and always sets `completed` --- unless
    the regression is present, in which case the loop never unwinds and `completed`
    stays clear, which is precisely the signal the test asserts on.

    Args:
        backend: The anyio backend to run the loop on (`"asyncio"` or `"trio"`).
        database: Filesystem path for the DuckDB database backing the pool.
        outcome: Mapping the loop records its observations into.
        completed: Set once the loop has fully unwound (successfully or not).
    """

    async def _main() -> None:
        pool = create_async_pool(DuckDBConfig(database=database))
        try:
            conn = await pool.connect()
            cur = conn.cursor()
            started = time.monotonic()
            async with anyio.create_task_group() as tg:

                async def _settle_then_cancel() -> None:
                    # Off-loop real sleep: the only "the worker is inside the C call"
                    # signal a live driver offers, and clock-independent under trio.
                    await anyio.to_thread.run_sync(functools.partial(time.sleep, _SETTLE_S))
                    tg.cancel_scope.cancel()

                tg.start_soon(_settle_then_cancel)
                await cur.execute(_LONG_QUERY)
                outcome["returned_normally"] = True  # the query was NOT interrupted
            outcome["elapsed"] = time.monotonic() - started
            # The poison-recovery ran: the aborted connection left the pool (CANCEL-02).
            outcome["checkedout"] = pool._pool.checkedout()  # noqa: SLF001
        finally:
            await pool.close()

    try:
        anyio.run(_main, backend=backend)
    except BaseException as exc:  # noqa: BLE001  reported to the main thread, never swallowed
        outcome["error"] = exc
    finally:
        completed.set()


@pytest.mark.parametrize("backend", ["asyncio", "trio"])
def test_cancel_during_live_query_does_not_wedge_worker(backend: str, tmp_path: Path) -> None:
    """
    D-25-09: a cancelled live DuckDB query unwinds instead of deadlocking forever.

    Drives a genuinely long-running query on a real in-process DuckDB connection,
    cancels the surrounding scope while the worker is inside the C call, and requires
    the whole thing to unwind within a real-clock budget.

    Pre-fix, the watcher fired `adbc_cancel` and then immediately awaited `on_abort`
    (`AsyncConnection.invalidate`), closing the connection out from under a worker
    that had not yet left the driver call. The worker wedged permanently inside
    `dbapi.execute`, and because `offload` is `abandon_on_cancel=False` the task group
    could never join it: the loop below never returned and `completed` was never set.
    Post-fix the watcher awaits the worker's `done` event before recovering, so the
    interrupt lands, the worker returns, `invalidate` runs on a quiescent connection,
    and the pool drains to zero.
    """
    completed = threading.Event()
    outcome: dict[str, object] = {}
    driver = threading.Thread(
        target=_drive_cancelled_query,
        args=(backend, str(tmp_path / "cancel_live.db"), outcome, completed),
        daemon=True,
    )
    driver.start()
    unwound = completed.wait(_BUDGET_S)

    assert unwound, (
        f"cancelled query never unwound within {_BUDGET_S}s on {backend}: the worker is "
        "wedged in the driver call (poison-recovery closed the connection before the "
        "aborted worker left it)"
    )
    assert outcome.get("error") is None, f"driving loop raised: {outcome.get('error')!r}"
    # The cancel really interrupted the query rather than the query finishing first.
    assert outcome.get("returned_normally") is not True
    # The poison-recovery ran to completion on a now-quiescent connection.
    assert outcome.get("checkedout") == 0
