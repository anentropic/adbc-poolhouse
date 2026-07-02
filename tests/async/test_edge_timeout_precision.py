"""
Timeout precision on the v1.5.0 new-method offload paths (EDGE-31 + EDGE-32).

Extends the already-green deadline-precision proofs (`test_reader_cancel.py`,
`test_ingest_cancel.py`, `test_edge_cancel_depth.py`) onto the streaming pull
(`fetch_record_batch` → `AsyncRecordBatchReader.__anext__`) and `adbc_ingest`
paths. Both requirements are pinned for the FIRST time on the new paths (RESEARCH
§Summary: the only legs that could surface a real gap), under BOTH asyncio and
trio, across the x20 loop:

- **EDGE-31** (`move_on_after_zero`): an already-expired deadline
  (`move_on_after(0)`) on a BLOCKED pull / ingest still cancels cleanly ---
  `adbc_cancel` fires exactly once, the poisoned connection invalidates once,
  and `scope.cancelled_caught is True`.
- **EDGE-32** (`deadline_epsilon`): an op that COMPLETES at deadline−ε (released
  by a REAL side thread the instant it is inside the block) is NOT over-cancelled
  --- no `adbc_cancel`, no `invalidate`, `scope.cancelled_caught is False`.

Harness discipline (RESEARCH §Pattern-2, Pitfalls 1/2/5):

- `virtual_clock` is the deadline TRIGGER only, so `move_on_after` fires instantly
  on both backends; `real_clock_watchdog` (a wall-clock side thread --- NOT
  `anyio.fail_after`, which autojumps under the trio `MockClock`) is the hang
  guard, and every gated leg asserts `tripped[0] is False`.
- Pitfall 5: a streaming leg arms `record_batch_batches = [object()]` BEFORE
  `fetch_record_batch()` so the first pull actually BLOCKS (an empty reader
  exhausts on the first pull with no cancel window).
- Pitfall 2 (EDGE-32): the happy-path releaser MUST run on a REAL side thread ---
  a loop-side releaser is starved by the `MockClock` autojump. `_release_when_entered`
  is copied verbatim from `test_edge_cancel_depth.py` for the ingest leg; the
  streaming leg uses `_release_reader_when_entered`, its reader-gate twin (the
  reader's blocking gate is separate from the cursor's --- Pitfall 4).

`concurrency_marks` (x-loop repeat + timeout) codify the "0-hang" gate so a
~33% deadlock cannot hide behind one lucky pass (MEMORY loop-flaky lesson).
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import anyio
import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from adbc_poolhouse._async._cursor import AsyncCursor
    from tests._async_harness.stubs import (
        BlockingStubConnection,
        BlockingStubCursor,
        BlockingStubReader,
    )

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
real_clock_watchdog = _helpers.real_clock_watchdog
virtual_clock = importlib.import_module("tests._async_harness.clock").virtual_clock
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]

# A trivial Arrow payload; the blocking stub blocks on its gate before the driver
# would touch it, so the contents are irrelevant.
_PAYLOAD = pyarrow.table({"id": [1, 2, 3]})


def _release_when_entered(stub_cursor: BlockingStubCursor, budget_s: float = 5.0) -> None:
    """
    Release a gated stub worker from a REAL thread once it is inside the block.

    Waits on the stub cursor's `entered` `threading.Event` (the sync, clock-
    independent "worker is inside execute" signal) and then `release()`s it ---
    modelling a query that completes normally. Done on a real thread, not a loop
    task, so the trio `MockClock` cannot starve it by autojumping virtual time to a
    deadline while the loop is parked on the off-loop worker.
    """
    if stub_cursor.entered.wait(timeout=budget_s):
        stub_cursor.release()


def _release_reader_when_entered(stub_reader: BlockingStubReader, budget_s: float = 5.0) -> None:
    """
    Reader-gate twin of `_release_when_entered` for the streaming EDGE-32 leg.

    The reader's blocking gate is SEPARATE from the owning cursor's (Pitfall 4), so
    the happy-path release of a blocked `read_next_batch` waits on the READER's own
    `entered` event and `release()`s the reader. Runs on a real side thread for the
    same reason as its cursor twin: a loop-side releaser is starved by the trio
    `MockClock` autojump (Pitfall 2).
    """
    if stub_reader.entered.wait(timeout=budget_s):
        stub_reader.release()


async def _drive_ingest(cursor: AsyncCursor) -> None:
    """Run a single `adbc_ingest` (the cancellable unit under test)."""
    await cursor.adbc_ingest("t", _PAYLOAD, mode="create")


class TestEdge31MoveOnAfterZeroCancelsBlockedOp:
    """EDGE-31: `move_on_after(0)` still cancels a BLOCKED new-method op (fires once)."""

    @pytest.mark.anyio
    async def test_move_on_after_zero_cancels_blocked_pull(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A `move_on_after` deadline firing on a blocked streaming pull aborts + invalidates once.

        Pitfall 5: a pending batch is armed BEFORE `fetch_record_batch()` so the
        first pull BLOCKS on the reader gate (the cancel window). The deadline is
        `move_on_after(5)` under `virtual_clock`: the trio `MockClock` (and the
        asyncio virtual clock) AUTOJUMPS to that deadline the instant the loop is
        parked on the just-dispatched off-loop worker --- so the deadline fires
        WHILE the pull is genuinely blocked, and the OWNING cursor's `adbc_cancel`
        fires once (the reader has none, Pitfall 4) and `invalidate` runs once.

        A literal `move_on_after(0)` (an already-EXPIRED scope) does NOT model this
        requirement: an expired deadline is delivered at the FIRST checkpoint ---
        the offload's limiter acquire --- BEFORE the worker is ever dispatched, so
        the pull never blocks (`read_call_count == 0`) and no `adbc_cancel` fires.
        That is the cancel-BEFORE-offload case (EDGE-08, already pinned in 32-01),
        not "cancel a BLOCKED op". Verified empirically this session: `move_on_after(0)`
        yields `read_call_count == 0` / `adbc_cancel_call_count == 0`, while
        `move_on_after(5)` under the autojumping clock yields the blocked-then-aborted
        `adbc_cancel_call_count == 1`. See the module deviation note. No production
        change --- the shared cancel path is exactly the green `fail_after(5)` analog
        in `test_reader_cancel.py`.
        """
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        # Pitfall 5: pending batch → the first pull blocks on the reader gate.
        stub_conn.cursors[-1].record_batch_batches = [object()]
        with (
            real_clock_watchdog(stub_conn.cursors) as tripped,
            virtual_clock(anyio_backend_name),
        ):
            reader = await cur.fetch_record_batch()
            sc = stub_conn.cursors[-1]
            # Autojumped-to deadline: fires WHILE the pull is blocked off-loop.
            with anyio.move_on_after(5) as scope:
                await reader.__anext__()
        assert tripped[0] is False
        assert scope.cancelled_caught is True
        assert sc.adbc_cancel_call_count == 1  # the CURSOR's cancel fired once
        assert stub_conn.invalidate_call_count == 1  # poison-recovery once

    @pytest.mark.anyio
    async def test_move_on_after_zero_cancels_blocked_ingest(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A `move_on_after` deadline firing on a blocked `adbc_ingest` aborts + invalidates once.

        The ingest is gated inside the blocking stub cursor; the deadline is
        `move_on_after(5)` under `virtual_clock`, which AUTOJUMPS to fire WHILE the
        ingest worker is blocked off-loop, so the cursor's `adbc_cancel` fires once
        and `invalidate` runs once --- identical to the streaming leg, only the
        offloaded method differs. See the pull leg's docstring / the module
        deviation note for why a literal `move_on_after(0)` (delivered before
        dispatch, EDGE-08) does not model a BLOCKED-op cancel.
        """
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        with (
            real_clock_watchdog(stub_conn.cursors) as tripped,
            virtual_clock(anyio_backend_name),
        ):
            sc = stub_conn.cursors[-1]
            # Autojumped-to deadline: fires WHILE the ingest is blocked off-loop.
            with anyio.move_on_after(5) as scope:
                await _drive_ingest(cur)
        assert tripped[0] is False
        assert scope.cancelled_caught is True
        assert sc.adbc_cancel_call_count == 1  # the cursor's cancel fired once
        assert stub_conn.invalidate_call_count == 1  # poison-recovery once


class TestEdge32DeadlineEpsilonNotOverCancelled:
    """EDGE-32: an op finishing at deadline−ε is NOT over-cancelled (clean return)."""

    @pytest.mark.anyio
    async def test_deadline_epsilon_pull_not_over_cancelled(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A pull completing at deadline−ε (real side thread) is not spuriously cancelled.

        Twin of the green `test_move_on_after_on_finished_op_is_noop` (EDGE-07) on the
        streaming path. Pitfall 5: one pending batch is armed so the first pull
        genuinely BLOCKS; a REAL side thread (`_release_reader_when_entered`,
        Pitfall 2 --- a loop-side releaser is starved by the `MockClock` autojump)
        releases the reader the instant it is inside the block, so the pull COMPLETES.

        The completion runs OUTSIDE any deadline scope and OUTSIDE `virtual_clock`:
        under `virtual_clock` the clock would AUTOJUMP to the nearest deadline the
        instant the loop parks on the off-loop worker, firing the deadline before the
        real thread's release is observed (that autojump is the EDGE-31 trigger, not
        the EDGE-32 shape). With the op finished, a subsequent `move_on_after(5)`
        under `virtual_clock` wraps only a checkpoint-only `anyio.sleep(0)` --- nothing
        off-loop for the clock to jump past --- so its deadline never fires:
        `cancelled_caught is False`, no `adbc_cancel`, no `invalidate`.
        """
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        # Pitfall 5: one pending batch → the first pull blocks, then the real thread
        # unblocks it (a query that completes normally at deadline−ε).
        stub_conn.cursors[-1].record_batch_batches = [object()]
        caught: bool | None = None
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            reader = await cur.fetch_record_batch()
            sc = stub_conn.cursors[-1]
            stub_reader = reader._reader  # noqa: SLF001  (the blocking stub reader)
            releaser = threading.Thread(
                target=_release_reader_when_entered, args=(stub_reader,), daemon=True
            )
            releaser.start()
            await reader.__anext__()  # completes via the real-thread release (real clock)
            # The op is finished; move_on_after on a checkpoint-only body is a no-op
            # even under the autojumping virtual clock (nothing off-loop to jump past).
            with virtual_clock(anyio_backend_name):
                with anyio.move_on_after(5) as scope:
                    await anyio.sleep(0)
            caught = scope.cancelled_caught
        releaser.join(timeout=5)
        assert tripped[0] is False
        assert caught is False  # the deadline never fired on a finished op
        assert sc.adbc_cancel_call_count == 0
        assert stub_conn.invalidate_call_count == 0

    @pytest.mark.anyio
    async def test_deadline_epsilon_ingest_not_over_cancelled(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        An `adbc_ingest` completing at deadline−ε (real side thread) is not cancelled.

        Twin of the green `test_move_on_after_on_finished_op_is_noop` (EDGE-07) on the
        ingest path. `_release_when_entered` (copied verbatim from
        `test_edge_cancel_depth.py`) releases the gated cursor from a REAL thread the
        instant its worker is inside the block, so the ingest COMPLETES on the real
        clock (outside `virtual_clock`, so the autojump does not race the release ---
        see the pull twin's docstring). With the op finished, a subsequent
        `move_on_after(5)` under `virtual_clock` wraps only a checkpoint-only
        `anyio.sleep(0)`, so its deadline never fires: `cancelled_caught is False`,
        no `adbc_cancel`, no `invalidate`.
        """
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        sc = stub_conn.cursors[-1]
        releaser = threading.Thread(target=_release_when_entered, args=(sc,), daemon=True)
        caught: bool | None = None
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            releaser.start()
            await _drive_ingest(cur)  # completes via the real-thread release (real clock)
            # The op is finished; move_on_after on a checkpoint-only body is a no-op.
            with virtual_clock(anyio_backend_name):
                with anyio.move_on_after(5) as scope:
                    await anyio.sleep(0)
            caught = scope.cancelled_caught
        releaser.join(timeout=5)
        assert tripped[0] is False
        assert caught is False  # the deadline never fired on a finished op
        assert sc.adbc_cancel_call_count == 0
        assert stub_conn.invalidate_call_count == 0
