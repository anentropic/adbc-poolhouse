"""
Async partitioned-execution cancel/invalidate parity (PART-03) --- regression coverage.

`adbc_execute_partitions` executes the query and `adbc_read_partition` opens a result
set, so both are poisoning-on-abort, exactly like `execute` / `adbc_ingest` (the
deliberate difference from the non-poisoning `adbc_prepare` / `adbc_execute_schema`).
Cancelling or timing out either in flight must fire the cursor's `adbc_cancel` exactly
once (`on_abort=owner.invalidate`), invalidate the now-poisoned connection so it drops
out of the pool, and leave the pool drained. The observables:

- `stub_cursor.adbc_cancel_call_count == 1` --- the cursor's cancel fired once;
- `stub_conn.invalidate_call_count == 1` --- poison-recovery ran once;
- `pool.checkedout() == 0` --- on the real DuckDB drain leg.

Harness discipline (copied from `test_ingest_cancel.py`): `await_inside` (event-gated,
no sleeps) waits until the worker is inside the blocked call; `real_clock_watchdog` (a
wall-clock side thread --- NOT `anyio.fail_after`, which autojumps under the trio
`MockClock`) fails fast on a hang; `concurrency_marks` (x-loop repeat + timeout) so a
~33% deadlock cannot hide behind one lucky pass. Both backends.
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
pytestmark = _helpers.concurrency_marks

_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]

# A trivial Arrow payload for the DuckDB drain leg; the stub legs ignore it.
_PAYLOAD = pyarrow.table({"id": [1, 2, 3]})


class TestPart03CancelInFlight:
    """PART-03: cancelling an in-flight partition call fires the cursor abort + invalidates once."""

    @pytest.mark.anyio
    async def test_cancel_during_execute_partitions_aborts_and_invalidates(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A cancel while `adbc_execute_partitions` is blocked fires abort + invalidate once.

        The call is gated inside the blocking stub cursor; the surrounding scope is then
        cancelled. The offload watcher fires the cursor's `adbc_cancel` exactly once and
        drives the owner's `invalidate` once, leaving the connection recovered.
        Dual-backend, looped.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            stub_cursor = stub_conn.cursors[-1]
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_execute_partitions, cur))
                try:
                    await await_inside(
                        lambda: stub_conn.cursors[-1].execute_partitions_call_count >= 1
                    )
                    tg.cancel_scope.cancel()
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert stub_cursor.adbc_cancel_call_count == 1
        assert stub_conn.invalidate_call_count == 1

    @pytest.mark.anyio
    async def test_cancel_during_read_partition_aborts_and_invalidates(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A cancel while `adbc_read_partition` is blocked fires abort + invalidate once.

        The read is gated inside the blocking stub cursor; the surrounding scope is then
        cancelled. The offload watcher fires the cursor's `adbc_cancel` once and drives
        `invalidate` once. Dual-backend, looped.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            stub_cursor = stub_conn.cursors[-1]
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_read_partition, cur))
                try:
                    await await_inside(lambda: stub_conn.cursors[-1].read_partition_call_count >= 1)
                    tg.cancel_scope.cancel()
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert stub_cursor.adbc_cancel_call_count == 1
        assert stub_conn.invalidate_call_count == 1

    @pytest.mark.anyio
    async def test_timeout_during_execute_partitions_aborts_and_invalidates(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A `fail_after` deadline on a blocked `adbc_execute_partitions` aborts identically.

        Uses `virtual_clock` + `anyio.fail_after` ONLY as the cancellation trigger under
        test (the watchdog stays `real_clock_watchdog`): the deadline fires in the call
        window, the abort runs, and the caller sees `TimeoutError`. `adbc_cancel` fires
        once and `invalidate` once --- only the surfaced type differs from the
        explicit-cancel leg.
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
                    await _drive_execute_partitions(cur)
            except TimeoutError:
                timed_out = True
        assert tripped[0] is False
        assert timed_out is True
        assert stub_cursor.adbc_cancel_call_count == 1
        assert stub_conn.invalidate_call_count == 1


class TestPart03DrainsPool:
    """PART-03 real-driver end: the cancel path's invalidate leaves the pool drained."""

    @pytest.mark.anyio
    async def test_invalidate_drains_pool_duckdb(
        self,
        duckdb_async_pool: AsyncPool,
        anyio_backend_name: str,
    ) -> None:
        """
        The cancel path's `invalidate` drops an in-use connection to `checkedout() == 0`.

        Mirrors `test_ingest_cancel.py::...drains_pool_duckdb`: rather than race a live
        `adbc_cancel` against an in-flight partition call (DuckDB does not even support
        the call), this drives the same `AsyncConnection.invalidate()` the partition
        cancel path drives, proving real-pool drainage deterministically. A checked-out
        connection holds the pool at 1; invalidate drops it straight to 0.
        """
        del anyio_backend_name
        conn = await duckdb_async_pool.connect()
        cur = conn.cursor()
        await cur.adbc_ingest("drained", _PAYLOAD, mode="create")  # keeps the conn checked out
        assert duckdb_async_pool._pool.checkedout() == 1  # noqa: SLF001
        await conn.invalidate()  # the cancel path's poison-recovery
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
        await conn.close()  # safe no-op after invalidate
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001


async def _drive_execute_partitions(cursor: AsyncCursor) -> None:
    """Run a single `adbc_execute_partitions` (the cancellable unit under test)."""
    await cursor.adbc_execute_partitions("SELECT 1")


async def _drive_read_partition(cursor: AsyncCursor) -> None:
    """Run a single `adbc_read_partition` (the cancellable unit under test)."""
    await cursor.adbc_read_partition(b"part-0")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
