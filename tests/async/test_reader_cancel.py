"""
Reader cancel-safety (STREAM-05) --- Wave-0 RED scaffolding.

Cancelling or timing out a batch pull must fire the OWNING cursor's `adbc_cancel`
exactly once (the reader has none of its own, Pitfall 4), invalidate the poisoned
connection so it drops out of the pool (`on_abort=owner.invalidate`), and leave the
pool drained. The observables (from `29-VALIDATION.md`):

- `stub_cursor.adbc_cancel_call_count == 1` --- the cursor's cancel fired once;
- `stub_conn.invalidate_call_count == 1` --- poison-recovery ran once;
- `pool.checkedout() == 0` --- on the real DuckDB drain leg.

The stub legs use the same gating discipline as `test_edge_cancel_depth.py`:
`await_inside` (event-gated, no sleeps) to wait until the worker is inside the
blocked pull, `real_clock_watchdog` (a wall-clock side thread --- NOT
`anyio.fail_after`, which autojumps under the trio `MockClock`) to fail fast on a
hang, and `concurrency_marks` (x-loop + timeout) so a ~33% deadlock cannot hide
behind one lucky pass (MEMORY loop-flaky-concurrency lesson). Both backends.

Wave-0 status: `AsyncCursor.fetch_record_batch` / `AsyncRecordBatchReader` do not
exist yet, so these FAIL (RED).
"""

from __future__ import annotations

# Wave-0 RED scaffolding: `AsyncCursor.fetch_record_batch` and
# `adbc_poolhouse._async._reader.AsyncRecordBatchReader` do not exist until plans
# 02/03 land, so every reference to them is statically "unknown" / "unresolved".
# These pragmas suppress ONLY the errors that are a direct consequence of those
# not-yet-existing symbols; delete this block once the production symbols land and
# the file type-checks cleanly under the strict whole-project gate (PKG-01).
# pyright: reportMissingImports=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import functools
import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import anyio
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
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


class TestStream05CancelPull:
    """STREAM-05: cancelling a pull fires the cursor's abort + invalidates once."""

    @pytest.mark.anyio
    async def test_cancel_during_pull_aborts_and_invalidates(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A cancel while a pull is blocked fires the cursor's `adbc_cancel` + invalidate once.

        The reader's pull is gated inside the blocking stub reader; the surrounding
        scope is then cancelled. The offload watcher fires the OWNING cursor's
        `adbc_cancel` exactly once (the reader has none) and drives the owner's
        `invalidate` once. Dual-backend, looped.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            reader = await cur.fetch_record_batch()
            stub_cursor = stub_conn.cursors[-1]
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drain_one, reader))
                try:
                    await await_inside(lambda: _pull_started(reader))
                    tg.cancel_scope.cancel()
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert stub_cursor.adbc_cancel_call_count == 1  # the CURSOR's cancel fired once
        assert stub_conn.invalidate_call_count == 1  # poison-recovery once

    @pytest.mark.anyio
    async def test_timeout_during_pull_aborts_and_invalidates(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A `fail_after` deadline on a blocked pull aborts identically (fires once).

        Uses `virtual_clock` + `anyio.fail_after` ONLY as the cancellation trigger
        under test (the watchdog stays `real_clock_watchdog`): the deadline fires in
        the dispatch/pull window, the abort runs, and the caller sees `TimeoutError`.
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
            reader = await cur.fetch_record_batch()
            stub_cursor = stub_conn.cursors[-1]
            try:
                with anyio.fail_after(5):
                    await _drain_one(reader)
            except TimeoutError:
                timed_out = True
        assert tripped[0] is False
        assert timed_out is True
        assert stub_cursor.adbc_cancel_call_count == 1
        assert stub_conn.invalidate_call_count == 1


class TestStream05CancelDrainsPool:
    """STREAM-05 real-driver end: a cancelled reader leaves the pool drained."""

    @pytest.mark.anyio
    async def test_invalidate_drains_pool_duckdb(
        self,
        duckdb_async_pool: AsyncPool,
        anyio_backend_name: str,
    ) -> None:
        """
        The cancel path's `invalidate` drops a reader-held connection to `checkedout() == 0`.

        Mirrors `test_edge_cancel_depth.py::...drains_pool_duckdb`: rather than race a
        live `adbc_cancel` against an in-flight DuckDB reader (best-effort per the
        ADBC spec, and it can wedge the worker --- violating the zero-hang gate),
        this drives the same `AsyncConnection.invalidate()` the reader's cancel path
        drives, proving the real-pool drainage deterministically. A live reader holds
        the connection checked out; invalidate drops it straight to 0.
        """
        del anyio_backend_name
        conn = await duckdb_async_pool.connect()
        cur = conn.cursor()
        await cur.execute("SELECT * FROM range(4) AS t(n)")
        reader = await cur.fetch_record_batch()
        await reader.__anext__()  # a live reader keeps the connection checked out
        assert duckdb_async_pool._pool.checkedout() == 1  # noqa: SLF001
        await conn.invalidate()  # the cancel path's poison-recovery
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
        await conn.close()  # safe no-op after invalidate
        assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001


async def _drain_one(reader: object) -> None:
    """Pull a single batch from the reader (the cancellable unit under test)."""
    await reader.__anext__()


def _pull_started(reader: object) -> bool:
    """Whether the reader's stub has recorded at least one blocked pull."""
    stub = getattr(reader, "_reader", None)
    read_calls = getattr(stub, "read_call_count", 0)
    return read_calls >= 1
