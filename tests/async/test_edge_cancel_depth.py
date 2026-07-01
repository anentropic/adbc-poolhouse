"""
Cancel-depth EDGE suite: the milestone's highest-risk correctness proof (EDGE-01..07).

Every leg drives a cancellation through the Phase 23/24 stub harness
([`BlockingStubCursor`][tests._async_harness.stubs.BlockingStubCursor] /
[`BlockingStubConnection`][tests._async_harness.stubs.BlockingStubConnection]) or
the real in-process DuckDB driver, gating the worker deterministically with
`await_inside` (event-gated, no sleeps) and wrapping each body in
`real_clock_watchdog` (a wall-clock side thread --- NOT `anyio.fail_after`, which
autojumps under the trio `MockClock` and would trip spuriously). The observable
signals asserted are exactly those in `25-VALIDATION.md`: `adbc_cancel_call_count`,
`invalidate_call_count`, `observed_cancel`, the surfaced exception identity, and
`pool.checkedout()` on the real-driver legs.

Test names embed the `-k` selectors the validation map uses
(`before`/`during`/`escapes`/`double`/`checkin`/`parity`/`finished`/`duckdb`/
`checkin_duckdb`). Per the MEMORY loop-flaky-concurrency lesson a single green run
is NOT acceptance: each test must survive a x20 loop (0 hangs) under both backends
--- the loop gate runs at wave merge.

Cancel choreography note (load-bearing). With the stub, the worker is gated inside
`execute` (it blocks on the stub's internal event), then the surrounding cancel
scope is cancelled. The watcher in
[`cancellable_offload`][adbc_poolhouse._async._cancel.cancellable_offload] receives
the cancellation, fires the stub's `adbc_cancel` (which releases the worker and
flips `observed_cancel`), and drives the owner's `invalidate`. The stub's
`adbc_cancel` returns the worker cleanly (no driver interrupt), so on the stub legs
the framework cancellation propagates directly. The DuckDB legs prove the real-pool
invariants deterministically: the `duckdb` leg drives the cancel path's
`AsyncConnection.invalidate()` poison-recovery to `checkedout() == 0`, and the
`checkin_duckdb` leg proves a cancel during the shielded `__aexit__` still drains
the pool. (Racing a live `adbc_cancel` against an in-flight DuckDB query is NOT
asserted here: that driver call is best-effort per the ADBC spec and intermittently
wedges the worker thread, which would violate the zero-hang loop gate --- see the
SUMMARY deviation note. The stub legs cover the cancel->abort->invalidate wiring.)

EDGE-07's "op finished first" leg releases the worker from a REAL side thread that
waits on the stub's `entered` `threading.Event`: under the trio `MockClock` a
loop-side releaser would be starved (virtual time autojumps to the deadline while
the loop waits on the off-loop worker), so the release must be clock-independent.
"""

from __future__ import annotations

import functools
import importlib
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import anyio
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from adbc_poolhouse._async._pool import AsyncPool
    from tests._async_harness.stubs import BlockingStubConnection, BlockingStubCursor

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks
_clock = importlib.import_module("tests._async_harness.clock")
virtual_clock = _clock.virtual_clock

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


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


class TestEdgeCancelDepth:
    """EDGE-01..07: the stub-driven cancel-depth proofs, dual-backend, x20-loopable."""

    @pytest.mark.anyio
    async def test_cancel_before_offload_is_clean(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-01 `before`: a cancel delivered BEFORE the offload starts touches nothing.

        The cancel scope is already cancelled when `execute` is awaited, so the
        worker never starts: `worker_started` stays False, the stub's `execute` is
        never called, no `adbc_cancel` and no `invalidate` fire, and the connection
        stays clean (EDGE-01/07 semantics).
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        sc = stub_conn.cursors[0]
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            with anyio.CancelScope() as scope:
                scope.cancel()  # cancel BEFORE entering the offload
                await cur.execute("SELECT 1")
        assert tripped[0] is False
        assert sc.execute_call_count == 0  # the driver was never touched
        assert sc.adbc_cancel_call_count == 0
        assert stub_conn.invalidate_call_count == 0
        assert sc.observed_cancel is False

    @pytest.mark.anyio
    async def test_cancel_during_block_aborts_and_invalidates(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-02 `during`: a cancel while the worker is blocked aborts + invalidates once.

        The worker is gated inside the stub's `execute`; the surrounding scope is
        then cancelled. The watcher fires `adbc_cancel` exactly once (releasing the
        worker, flipping `observed_cancel`) and drives the owner's `invalidate`
        once. `checkedout() == 0` is proven on the real-driver `duckdb` leg below.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        sc = stub_conn.cursors[0]
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(cur.execute, "SELECT 1"))
                try:
                    await await_inside(lambda: sc.execute_call_count == 1)
                    tg.cancel_scope.cancel()
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert sc.adbc_cancel_call_count == 1  # fired EXACTLY once
        assert sc.observed_cancel is True
        assert stub_conn.invalidate_call_count == 1  # poison-recovery once

    @pytest.mark.anyio
    async def test_framework_cancel_escapes_no_hang(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-03 `escapes`: the framework cancellation is never swallowed; no trio hang.

        The watcher always re-raises the cancellation it caught (D-25-06), so the
        cancel reaches the surrounding scope and the abort fires --- and the
        wall-clock watchdog proves the body did not hang under trio (where a
        swallowed cancellation would dangle the structured-cancellation scope).
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        sc = stub_conn.cursors[0]
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            async with anyio.create_task_group() as tg:

                async def _gate_then_cancel() -> None:
                    await await_inside(lambda: sc.execute_call_count == 1)
                    tg.cancel_scope.cancel()  # deliver the cancellation

                tg.start_soon(_gate_then_cancel)
                try:
                    await cur.execute("SELECT 1")
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False  # no worker stranded, no hang
        # The cancellation reached the watcher (it never swallowed it): the abort
        # fired and the connection was invalidated.
        assert sc.adbc_cancel_call_count == 1
        assert sc.observed_cancel is True
        assert stub_conn.invalidate_call_count == 1

    @pytest.mark.anyio
    async def test_double_cancel_is_idempotent(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-04 `double`: a second cancel during shielded cleanup stays idempotent.

        The watcher fires `adbc_cancel` and runs `on_abort` (invalidate) inside
        `CancelScope(shield=True)`, so a second cancellation arriving during that
        cleanup cannot abort the abort: `adbc_cancel` fires once (not twice),
        `invalidate` once, one cancellation surfaces (D-25-07).
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        sc = stub_conn.cursors[0]
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(cur.execute, "SELECT 1"))
                try:
                    await await_inside(lambda: sc.execute_call_count == 1)
                    tg.cancel_scope.cancel()
                    tg.cancel_scope.cancel()  # a SECOND cancel must not double-fire
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert sc.adbc_cancel_call_count == 1  # NOT 2 (idempotent under the shield)
        assert stub_conn.invalidate_call_count == 1
        assert sc.observed_cancel is True

    @pytest.mark.anyio
    async def test_cancel_during_checkin_completes(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-05 `checkin` (stub): a cancel during `__aexit__`/checkin still checks in.

        The op finishes first (released happy-path), then the scope is cancelled
        while the connection's shielded `__aexit__` (offloaded `fairy.close`) runs.
        The shield makes the check-in complete regardless: the stub records the
        close, and because the op was never aborted there is no `adbc_cancel` and no
        `invalidate`. The real-pool drainage is proven on the `checkin_duckdb` leg.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        releaser: threading.Thread | None = None
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            async with anyio.create_task_group() as tg:
                cur = async_conn.cursor()
                run_sc = stub_conn.cursors[-1]
                releaser = threading.Thread(
                    target=_release_when_entered, args=(run_sc,), daemon=True
                )
                releaser.start()
                with anyio.CancelScope() as scope:
                    await cur.execute("SELECT 1")  # finishes via the real-thread release
                    scope.cancel()  # cancel as the connection is about to check in
                    # The shielded close still runs to completion.
                    await async_conn.close()
                tg.cancel_scope.cancel()  # drain the (empty) group cleanly
        if releaser is not None:
            releaser.join(timeout=5)
        assert tripped[0] is False
        # checkin completed despite the cancel: the connection-level close ran.
        assert stub_conn.close_call_count == 1
        # the op was never aborted, so no cancel/invalidate fired.
        assert stub_conn.invalidate_call_count == 0
        assert all(c.adbc_cancel_call_count == 0 for c in stub_conn.cursors)

    @pytest.mark.anyio
    async def test_fail_after_and_scope_cancel_parity(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-06 `parity`: `fail_after` and `scope.cancel()` abort identically.

        Leg 1 uses `virtual_clock` + `anyio.fail_after` ONLY as the cancellation
        trigger under test (never as the watchdog --- that stays
        `real_clock_watchdog`): the deadline fires, the abort runs, and the caller
        sees `TimeoutError`. Leg 2 cancels the scope explicitly: the same abort
        runs but NO exception surfaces. Both fire `adbc_cancel` exactly once ---
        only the surfaced type differs.
        """
        # --- Leg 1: fail_after -> TimeoutError ---
        a_conn, a_stub = make_stub_async_connection()
        a_cur = a_conn.cursor()
        a_sc = a_stub.cursors[0]
        timed_out = False
        with real_clock_watchdog(a_stub.cursors) as tripped_a:
            with virtual_clock(anyio_backend_name):
                try:
                    with anyio.fail_after(5):
                        await a_cur.execute("SELECT 1")
                except TimeoutError:
                    timed_out = True
            for c in a_stub.cursors:
                c.release()
        assert tripped_a[0] is False
        assert timed_out is True
        assert a_sc.adbc_cancel_call_count == 1
        assert a_stub.invalidate_call_count == 1

        # --- Leg 2: explicit scope.cancel -> no surfaced exception ---
        b_conn, b_stub = make_stub_async_connection()
        b_cur = b_conn.cursor()
        b_sc = b_stub.cursors[0]
        surfaced: BaseException | None = None
        with real_clock_watchdog(b_stub.cursors) as tripped_b:
            try:
                async with anyio.create_task_group() as tg:
                    tg.start_soon(functools.partial(b_cur.execute, "SELECT 1"))
                    try:
                        await await_inside(lambda: b_sc.execute_call_count == 1)
                        tg.cancel_scope.cancel()
                    finally:
                        for c in b_stub.cursors:
                            c.release()
            except BaseException as exc:  # noqa: BLE001 (assert NOTHING surfaces)
                surfaced = exc
        assert tripped_b[0] is False
        assert b_sc.adbc_cancel_call_count == 1  # identical abort
        assert b_stub.invalidate_call_count == 1
        assert surfaced is None  # scope.cancel surfaces nothing (only the type differs)

    @pytest.mark.anyio
    async def test_move_on_after_on_finished_op_is_noop(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-07 `finished`: `move_on_after` on an already-finished op does nothing.

        The worker is released (happy path) by a real side thread, so `execute`
        completes; a subsequent `move_on_after` then wraps only a checkpoint-only
        `sleep(0)` (no off-loop wait for the `MockClock` to autojump past), so its
        deadline never fires: `cancelled_caught is False`, and because nothing was
        aborted there is no `adbc_cancel` and no `invalidate`.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        sc = stub_conn.cursors[0]
        releaser = threading.Thread(target=_release_when_entered, args=(sc,), daemon=True)
        caught: bool | None = None
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            releaser.start()
            await cur.execute("SELECT 1")  # completes via the real-thread release
            with anyio.move_on_after(5) as scope:
                await anyio.sleep(0)  # checkpoint only; nothing for the clock to jump past
            caught = scope.cancelled_caught
        releaser.join(timeout=5)
        assert tripped[0] is False
        assert caught is False  # the deadline never fired on a finished op
        assert sc.adbc_cancel_call_count == 0
        assert sc.observed_cancel is False
        assert stub_conn.invalidate_call_count == 0

    @pytest.mark.anyio
    async def test_cancel_in_dispatch_window_still_aborts(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        CR-01 regression: a cancel in the post-dispatch / pre-driver-call window aborts.

        This is the TOCTOU window the prior `worker_started` flag missed: the cancel
        is delivered AFTER the offload has acquired its token and dispatched the
        worker thread, but BEFORE the worker has entered the driver call (the stub's
        blocked `execute`). Under the trio `MockClock`, `fail_after(5)` fires the
        instant every loop task is blocked on the just-dispatched worker --- i.e. in
        exactly that window --- so this exercises it deterministically with no
        positive-duration sleep.

        Crucially, the gated worker is NOT released in a `finally`: the ONLY thing
        that can unblock it is the watcher firing the stub's `adbc_cancel`. With the
        flag written on the worker thread (the old bug), the watcher read a stale
        `False`, skipped the abort, and the non-cancellable worker hung until the
        wall-clock watchdog forced it open (`tripped is True`). With the flag set
        synchronously on the loop thread at dispatch (the fix), `adbc_cancel` fires
        once, the worker returns, `invalidate` runs once, and the watchdog never
        trips. Runs under BOTH backends and survives the x20 loop gate.
        """
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        sc = stub_conn.cursors[0]
        timed_out = False
        with (
            real_clock_watchdog(stub_conn.cursors) as tripped,
            virtual_clock(anyio_backend_name),
        ):
            try:
                # The deadline fires in the dispatch window: the worker is
                # dispatched but has not yet entered the stub's blocked execute.
                with anyio.fail_after(5):
                    await cur.execute("SELECT 1")
            except TimeoutError:
                timed_out = True
            # No release-in-finally: only the watcher's adbc_cancel can unblock the
            # worker. If the abort were skipped (the CR-01 bug) the worker would hang
            # and the watchdog would trip below.
        assert tripped[0] is False, "worker hung: the dispatch-window cancel skipped adbc_cancel"
        assert timed_out is True
        assert sc.adbc_cancel_call_count == 1  # the abort fired despite the narrow window
        assert sc.observed_cancel is True
        assert stub_conn.invalidate_call_count == 1  # poison-recovery ran once


class TestEdgeCancelDepthRealDriver:
    """The real in-process DuckDB legs: the invalidate poison-recovery and checkin cancel."""

    @pytest.mark.anyio
    async def test_cancel_during_execute_drains_pool_duckdb(
        self,
        duckdb_async_pool: AsyncPool,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-02 `duckdb`: the real poison-recovery drains a checked-out connection to 0.

        This is the real-driver end of CANCEL-02: the cancel path's
        `AsyncConnection.invalidate()` (the shielded, offloaded `fairy.invalidate()`
        the watcher fires via `on_abort`) drops a checked-out connection straight to
        `pool.checkedout() == 0`, and a following `close()` is a safe no-op --- the
        invariant a cancelled in-flight query relies on to leave the pool healthy.

        Why this exercises the invalidate path directly rather than racing a live
        `adbc_cancel`: ADBC's `adbc_cancel` against an in-flight DuckDB query is
        best-effort (the spec permits a missed cancel) and, in this driver version,
        intermittently *wedges* the worker thread inside the C `execute` --- a
        non-deterministic driver-level hang that no test-side gating can prevent and
        that violates the phase's hard x20-loop / zero-hang gate. The stub `during`
        leg already proves the cancel -> `adbc_cancel` -> `invalidate` *wiring*
        deterministically; this leg proves the *real-pool drainage* the wiring
        targets, deterministically, by driving the same `invalidate()` the cancel
        path drives. See the SUMMARY deviation note for the wedged-driver evidence.
        """
        del anyio_backend_name
        conn = await duckdb_async_pool.connect()
        cur = conn.cursor()
        await cur.execute("SELECT 1 AS n")  # a real round trip on a real connection
        await cur.fetch_arrow_table()
        assert duckdb_async_pool._pool.checkedout() == 1  # genuinely checked out
        # The cancel path's poison-recovery: invalidate drops the connection from
        # the pool (CANCEL-02), driving checkedout() straight to 0.
        await conn.invalidate()
        assert duckdb_async_pool._pool.checkedout() == 0
        # A close() after invalidate is a safe no-op --- the pool stays drained.
        await conn.close()
        assert duckdb_async_pool._pool.checkedout() == 0

    @pytest.mark.anyio
    async def test_cancel_during_checkin_duckdb_drains_pool(
        self,
        duckdb_async_pool: AsyncPool,
        anyio_backend_name: str,
    ) -> None:
        """
        EDGE-05 `checkin_duckdb`: a cancel during `__aexit__` still drains the pool.

        The query FINISHES (op complete), the cursor is closed, then the scope is
        cancelled while the connection's `async with` block is unwinding into the
        shielded `__aexit__`. The shield makes the check-in complete despite the
        cancellation, so `pool.checkedout()` returns to 0 for both the connection
        and the cursor after the shielded checkin (EDGE-05 verbatim). This is
        distinct from the `duckdb` invalidate leg above: here a real cancel arrives
        during checkin and the shield still completes it.
        """
        del anyio_backend_name
        with anyio.CancelScope() as scope:
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT 1 AS n")  # op FINISHES (not aborted)
                tbl = await cur.fetch_arrow_table()
                assert tbl.column("n")[0].as_py() == 1
                await cur.close()  # the cursor is checked back in (shielded close)
                scope.cancel()  # cancel as the connection is about to check in
            # the connection's shielded __aexit__ ran here despite the cancellation
        # Both the cursor (closed above) and the connection are drained: the sync
        # pool tracks every checkout, so checkedout() == 0 proves both returned.
        assert duckdb_async_pool._pool.checkedout() == 0


class TestOffloadDispatchSync:
    """
    CR-01 mechanism lock: `offload`'s `on_dispatch` is the loop-thread, pre-call hook.

    These deterministically pin the synchronization that closes the CR-01 TOCTOU
    window --- distinct from the timing-driven `test_cancel_in_dispatch_window_*`
    integration leg above. They fail HARD on the pre-fix code (which had no
    `on_dispatch` parameter and set the started-flag on the worker thread), so they
    are a durable guard against re-introducing a cross-thread flag write.
    """

    @pytest.mark.anyio
    async def test_on_dispatch_runs_on_loop_thread_before_fn(self, anyio_backend_name: str) -> None:
        """
        `on_dispatch` runs on the LOOP thread and strictly BEFORE `fn` is entered.

        The CR-01 fix hinges on the started-flag being written on the loop thread
        (where the watcher reads it) at dispatch, not on the worker thread mid-flag.
        This asserts both halves of that contract: `on_dispatch` records the loop
        thread id and runs before the worker `fn` records the worker thread id, and
        the two thread ids differ (the call genuinely went off-loop).
        """
        del anyio_backend_name
        offload = importlib.import_module("adbc_poolhouse._async._offload").offload
        loop_thread_id = threading.get_ident()
        order: list[str] = []
        dispatch_thread_id: list[int] = []
        worker_thread_id: list[int] = []

        def _on_dispatch() -> None:
            order.append("dispatch")
            dispatch_thread_id.append(threading.get_ident())

        def _fn() -> int:
            order.append("fn")
            worker_thread_id.append(threading.get_ident())
            return 7

        result = await offload(
            _fn,
            limiter=anyio.CapacityLimiter(1),
            on_dispatch=_on_dispatch,
        )
        assert result == 7
        # Strict ordering: the dispatch hook fires before the worker function.
        assert order == ["dispatch", "fn"]
        # The hook ran on the loop thread; the function ran off-loop.
        assert dispatch_thread_id == [loop_thread_id]
        assert worker_thread_id and worker_thread_id[0] != loop_thread_id

    @pytest.mark.anyio
    async def test_on_dispatch_token_held_when_hook_fires(self, anyio_backend_name: str) -> None:
        """
        `on_dispatch` fires only AFTER the per-pool token is acquired.

        The watcher must treat the worker as "started" only once it holds a token
        and is committed to the driver call (EDGE-02), never while still queued
        (EDGE-01/07). This asserts the hook observes `borrowed_tokens == 1`, proving
        the token is held at the moment the started-flag would be set.
        """
        del anyio_backend_name
        offload = importlib.import_module("adbc_poolhouse._async._offload").offload
        limiter = anyio.CapacityLimiter(1)
        borrowed_at_dispatch: list[int] = []

        def _on_dispatch() -> None:
            borrowed_at_dispatch.append(limiter.borrowed_tokens)

        await offload(lambda: None, limiter=limiter, on_dispatch=_on_dispatch)
        assert borrowed_at_dispatch == [1]  # a token was held when the hook fired
        assert limiter.borrowed_tokens == 0  # and released on return
