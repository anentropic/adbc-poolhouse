"""
Async prepared-statement cancel: cancellable BUT non-poisoning (D-35-04) --- Wave-0 RED.

Cancelling or timing out an in-flight `adbc_prepare` must fire the cursor's
`adbc_cancel` exactly once (the call IS cancellable --- the sync method routes
through `_blocking_call(..., self._stmt.cancel)`), yet must NOT invalidate the
connection: neither `adbc_prepare` nor `adbc_execute_schema` executes the query or
writes data, so an aborted call cannot leave a half-applied state that poisons the
connection. Per D-35-04 `on_abort` is therefore OMITTED, and a cancelled prepare
fires `adbc_cancel` once, re-raises the cancellation, and returns a CLEAN connection
to the pool. The two-axis observables:

- `stub_cursor.adbc_cancel_call_count == 1` --- CANCELLABLE (differs from
  `test_meta_cancel.py`, whose no-op cancel hook leaves it at `0`);
- `stub_conn.invalidate_call_count == 0` --- NON-POISONING (differs from
  `test_ingest_cancel.py`, which asserts `== 1` because a partial write poisons the
  connection).

Harness discipline (MEMORY carried-forward gotchas): `await_inside` (event-gated, no
sleeps) waits until the worker is inside the blocked prepare; `real_clock_watchdog`
(a wall-clock side thread --- NOT `anyio.fail_after`, which autojumps under the trio
`MockClock`) fails fast on a hang; `concurrency_marks` (x-loop repeat + timeout) so a
rare deadlock cannot hide behind one lucky pass (loop-flaky-concurrency lesson). Both
backends. The timeout twin uses `virtual_clock` + `anyio.fail_after` ONLY as the
cancellation TRIGGER (the watchdog stays real-clock).

Wave-0 status: `AsyncCursor.adbc_prepare` does not exist yet, so these FAIL (RED).
Closes threat T-35-02 (connection-left-busy-after-cancel) once GREEN.
"""

from __future__ import annotations

import functools
import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import anyio
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from adbc_poolhouse._async._cursor import AsyncCursor
    from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
virtual_clock = importlib.import_module("tests._async_harness.clock").virtual_clock
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks

_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


class TestPrepCancelNonPoisoning:
    """D-35-04: a cancelled prepare fires `adbc_cancel` once but NEVER invalidates."""

    @pytest.mark.anyio
    async def test_cancel_during_prepare_aborts_without_invalidating(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A cancel while a prepare is blocked fires the cursor's `adbc_cancel` once, no invalidate.

        The prepare is gated inside the blocking stub cursor; the surrounding scope is
        then cancelled once the worker is provably inside the blocked call
        (`prepare_call_count >= 1`). The offload watcher fires the cursor's
        `adbc_cancel` exactly once (CANCELLABLE) but --- with `on_abort` omitted
        (D-35-04) --- NEVER drives the owner's `invalidate` (NON-POISONING), so a clean
        connection returns to the pool. Dual-backend, looped, real-clock watchdog.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            stub_cursor = stub_conn.cursors[-1]
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_prepare, cur))
                try:
                    await await_inside(lambda: stub_conn.cursors[-1].prepare_call_count >= 1)
                    tg.cancel_scope.cancel()
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert stub_cursor.adbc_cancel_call_count == 1  # CANCELLABLE: fired once
        assert stub_conn.invalidate_call_count == 0  # NON-POISONING (D-35-04) --- NOT 1

    @pytest.mark.anyio
    async def test_timeout_during_prepare_aborts_without_invalidating(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A `fail_after` deadline on a blocked prepare aborts identically (fires once, no invalidate).

        Uses `virtual_clock` + `anyio.fail_after` ONLY as the cancellation trigger under
        test (the watchdog stays `real_clock_watchdog`): the deadline fires in the
        prepare window, the abort runs, and the caller sees `TimeoutError`. `adbc_cancel`
        fires once and `invalidate` is still NOT called (D-35-04) --- only the surfaced
        type differs from the explicit-cancel leg.
        """
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        timed_out = False
        with (
            real_clock_watchdog(stub_conn.cursors) as tripped,
            virtual_clock(anyio_backend_name),
        ):
            stub_cursor = stub_conn.cursors[-1]
            try:
                with anyio.fail_after(5):
                    await _drive_prepare(cur)
            except TimeoutError:
                timed_out = True
        assert tripped[0] is False
        assert timed_out is True
        assert stub_cursor.adbc_cancel_call_count == 1  # CANCELLABLE: fired once
        assert stub_conn.invalidate_call_count == 0  # NON-POISONING (D-35-04) --- NOT 1


async def _drive_prepare(cursor: AsyncCursor) -> None:
    """Run a single `adbc_prepare` (the cancellable unit under test)."""
    await cursor.adbc_prepare("SELECT 1")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
