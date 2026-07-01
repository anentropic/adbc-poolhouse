"""
Async bulk-write cancel/invalidate parity (INGEST-04, T-30-01) --- Wave-0 RED scaffolding.

Cancelling or timing out an in-flight `adbc_ingest` must fire the cursor's
`adbc_cancel` exactly once (`on_abort=owner.invalidate`), invalidate the
now-poisoned connection so it drops out of the pool, and leave the pool drained.
A partial bulk write poisons the connection; the abort recovers the CONNECTION,
not the partially-applied rows (D-30-10 / Pitfall 5) --- so these tests assert ONLY
connection recovery, never post-cancel table state. The observables:

- `stub_cursor.adbc_cancel_call_count == 1` --- the cursor's cancel fired once;
- `stub_conn.invalidate_call_count == 1` --- poison-recovery ran once;
- `pool.checkedout() == 0` --- on the real DuckDB drain leg.

Harness discipline (copied verbatim from `test_reader_cancel.py`): `await_inside`
(event-gated, no sleeps) waits until the worker is inside the blocked ingest;
`real_clock_watchdog` (a wall-clock side thread --- NOT `anyio.fail_after`, which
autojumps under the trio `MockClock`) fails fast on a hang; `concurrency_marks`
(x-loop repeat + timeout) so a ~33% deadlock cannot hide behind one lucky pass
(MEMORY loop-flaky-concurrency lesson). Both backends.

Wave-0 status: `AsyncCursor.adbc_ingest` does not exist yet, so these FAIL (RED).
Closes threat T-30-01 (poisoned-connection-returned-to-pool / pool-starvation)
once GREEN.
"""

from __future__ import annotations

import functools
import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import anyio
import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from adbc_poolhouse._async._cursor import AsyncCursor
    from adbc_poolhouse._async._pool import AsyncPool
    from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
virtual_clock = importlib.import_module("tests._async_harness.clock").virtual_clock
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]

# A trivial Arrow payload; the blocking stub ignores it, so its contents are
# irrelevant --- the stub blocks on the gate before the driver would touch it.
_PAYLOAD = pyarrow.table({"id": [1, 2, 3]})


class TestIngest04CancelInFlight:
    """INGEST-04: cancelling an in-flight ingest fires the cursor abort + invalidates once."""

    @pytest.mark.anyio
    async def test_cancel_during_ingest_aborts_and_invalidates(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A cancel while an ingest is blocked fires the cursor's `adbc_cancel` + invalidate once.

        The ingest is gated inside the blocking stub cursor; the surrounding scope is
        then cancelled. The offload watcher fires the cursor's `adbc_cancel` exactly
        once and drives the owner's `invalidate` once, leaving the connection
        recovered. Asserts connection recovery ONLY --- never table state after the
        cancelled write (D-30-10). Dual-backend, looped.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            stub_cursor = stub_conn.cursors[-1]
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_ingest, cur))
                try:
                    await await_inside(lambda: stub_conn.cursors[-1].ingest_call_count >= 1)
                    tg.cancel_scope.cancel()
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert stub_cursor.adbc_cancel_call_count == 1  # the cursor's cancel fired once
        assert stub_conn.invalidate_call_count == 1  # poison-recovery once

    @pytest.mark.anyio
    async def test_timeout_during_ingest_aborts_and_invalidates(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A `fail_after` deadline on a blocked ingest aborts identically (fires once).

        Uses `virtual_clock` + `anyio.fail_after` ONLY as the cancellation trigger
        under test (the watchdog stays `real_clock_watchdog`): the deadline fires in
        the ingest window, the abort runs, and the caller sees `TimeoutError`.
        `adbc_cancel` fires once and `invalidate` once --- only the surfaced type
        differs from the explicit-cancel leg.
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
                    await _drive_ingest(cur)
            except TimeoutError:
                timed_out = True
        assert tripped[0] is False
        assert timed_out is True
        assert stub_cursor.adbc_cancel_call_count == 1
        assert stub_conn.invalidate_call_count == 1


class TestIngest04DrainsPool:
    """INGEST-04 real-driver end: the cancel path's invalidate leaves the pool drained."""

    @pytest.mark.anyio
    async def test_invalidate_drains_pool_duckdb(
        self,
        duckdb_async_pool: AsyncPool,
        anyio_backend_name: str,
    ) -> None:
        """
        The cancel path's `invalidate` drops an in-use connection to `checkedout() == 0`.

        Mirrors `test_reader_cancel.py::...drains_pool_duckdb`: rather than race a live
        `adbc_cancel` against an in-flight DuckDB ingest (best-effort per the ADBC
        spec, and it can wedge the worker --- violating the zero-hang gate), this
        drives the same `AsyncConnection.invalidate()` the ingest cancel path drives,
        proving the real-pool drainage deterministically. A checked-out connection
        holds the pool at 1; invalidate drops it straight to 0. Asserts connection
        recovery only, never table state (D-30-10).
        """
        del anyio_backend_name
        conn = await duckdb_async_pool.connect()
        cur = conn.cursor()
        # A committed ingest keeps the connection checked out (the whole-op offload
        # returns and the connection stays out until close/invalidate).
        await cur.adbc_ingest("drained", _PAYLOAD, mode="create")
        assert duckdb_async_pool._pool.checkedout() == 1  # noqa: SLF001
        await conn.invalidate()  # the cancel path's poison-recovery
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
        await conn.close()  # safe no-op after invalidate
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001


async def _drive_ingest(cursor: AsyncCursor) -> None:
    """Run a single `adbc_ingest` (the cancellable unit under test)."""
    await cursor.adbc_ingest("t", _PAYLOAD, mode="create")
