"""
Loop-shutdown cleanliness on the v1.5.0 new-method offload paths (EDGE-24).

A pending offload at loop / task-group teardown --- mid-stream (a blocked
`read_next_batch`) and mid-ingest (a blocked `adbc_ingest`) --- must raise NO
library-attributable exception: no "coroutine was never awaited" `RuntimeWarning`,
no "Task was destroyed but it is pending". trio's stricter nursery teardown is the
discriminating canary (RESEARCH §Pattern-3); both backends run.

Harness discipline (RESEARCH §Pattern-3, Pitfall 3):

- `offload()` is `abandon_on_cancel=False`, so a genuinely UN-released blocked
  worker turns teardown into a join-HANG (not a clean shutdown) --- which under the
  x20 loop gate is itself a hang, not the property under test. The deterministic
  proof RELEASES every stub worker in the teardown window (`c.release()` /
  `reader.release()`) so the worker joins cleanly, then asserts on the ABSENCE of
  stray exceptions/warnings. A genuinely-wedged worker is never raced (RESEARCH
  A3): the release-in-teardown / drained-close discipline is the deterministic
  substitute.
- Warnings are captured with `warnings.catch_warnings(record=True)` +
  `simplefilter("always")` (the `test_reader_resource.py` idiom), then filtered to
  the two shutdown strings.
- `real_clock_watchdog` (a wall-clock side thread, NOT `anyio.fail_after`, which
  autojumps under the trio `MockClock`) guards every stub leg against a hang;
  each leg asserts `tripped[0] is False`.

The real leg drives a `duckdb_async_pool` with a drained-but-open connection and
asserts `pool.close()` raises nothing with `checkedout() == 0`.

`concurrency_marks` (x-loop repeat + timeout) codify the "0-hang" gate so a ~33%
deadlock cannot hide behind one lucky pass (MEMORY loop-flaky lesson).
"""

from __future__ import annotations

import functools
import importlib
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING

import anyio
import pyarrow
import pytest

if TYPE_CHECKING:
    from warnings import WarningMessage

    from adbc_poolhouse._async._connection import AsyncConnection
    from adbc_poolhouse._async._pool import AsyncPool
    from adbc_poolhouse._async._reader import AsyncRecordBatchReader
    from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]

# A trivial Arrow payload; the blocking stub blocks on its gate before the driver
# would touch it, so the contents are irrelevant.
_PAYLOAD = pyarrow.table({"id": [1, 2, 3]})

# The two shutdown-attributable warning fragments that must NEVER appear: an
# un-awaited coroutine and a destroyed-pending task. trio's nursery strictness is
# the canary that would surface either at teardown.
_SHUTDOWN_STRINGS = ("was never awaited", "Task was destroyed")


def _offending(caught: list[WarningMessage]) -> list[WarningMessage]:
    """Filter captured warnings to the library-attributable shutdown ones (must be [])."""
    return [w for w in caught if any(s in str(w.message) for s in _SHUTDOWN_STRINGS)]


async def _drain_one(reader: AsyncRecordBatchReader) -> None:
    """Pull a single batch (the mid-stream pending offload under test)."""
    await reader.__anext__()


def _pull_started(reader: AsyncRecordBatchReader) -> bool:
    """Whether the reader's blocking stub has recorded at least one blocked pull."""
    stub = getattr(reader, "_reader", None)
    read_calls = getattr(stub, "read_call_count", 0)
    return read_calls >= 1


class TestEdge24ShutdownCleanliness:
    """EDGE-24: a pending new-method offload at teardown raises nothing library-attributable."""

    @pytest.mark.anyio
    async def test_pending_ingest_at_shutdown_raises_nothing(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A pending `adbc_ingest` at task-group teardown surfaces no stray exception/warning.

        The ingest is started in a task group and gated inside the blocking stub; the
        stub worker is then RELEASED in the teardown window (Pitfall 3 --- an
        un-released `abandon_on_cancel=False` worker would turn teardown into a
        join-hang, not a clean shutdown), so the group joins cleanly. Capturing all
        warnings, the library-attributable shutdown set (`was never awaited` /
        `Task was destroyed`) must be empty. trio's nursery teardown is the canary.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        with (
            real_clock_watchdog(stub_conn.cursors) as tripped,
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(cur.adbc_ingest, "t", _PAYLOAD, mode="create"))
                await await_inside(lambda: stub_conn.cursors[0].ingest_call_count == 1)
                for c in stub_conn.cursors:  # release so teardown JOINS the worker
                    c.release()
        assert tripped[0] is False
        assert _offending(caught) == []

    @pytest.mark.anyio
    async def test_pending_stream_pull_at_shutdown_raises_nothing(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        A pending streaming pull at task-group teardown surfaces no stray exception/warning.

        Mid-stream twin of the ingest leg. Pitfall 5: a pending batch is armed BEFORE
        `fetch_record_batch()` so the pull genuinely BLOCKS; `_drain_one` is started
        in the task group, gated on `read_call_count >= 1`, then every stub worker is
        RELEASED in the teardown window so the group joins cleanly (Pitfall 3). The
        library-attributable shutdown warning set must be empty; trio nursery canary.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        # Pitfall 5: a pending batch → the first pull blocks on the reader gate.
        stub_conn.cursors[-1].record_batch_batches = [object()]
        with (
            real_clock_watchdog(stub_conn.cursors) as tripped,
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            reader = await cur.fetch_record_batch()
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drain_one, reader))
                await await_inside(lambda: _pull_started(reader))
                for c in stub_conn.cursors:  # reaches through to the reader gate too
                    c.release()
        assert tripped[0] is False
        assert _offending(caught) == []


class TestEdge24RealDrainedClose:
    """EDGE-24 real-driver end: a drained-but-open connection closes at teardown raising nothing."""

    @pytest.mark.anyio
    async def test_real_drained_close_raises_nothing(
        self,
        duckdb_async_pool: AsyncPool,
        anyio_backend_name: str,
    ) -> None:
        """
        A real `duckdb_async_pool` closes a drained-but-open connection raising nothing.

        The deterministic real leg (RESEARCH A3 --- do NOT race a genuinely-wedged
        worker at shutdown). A connection is checked out, a real streaming op is run
        to completion and fully DRAINED, then `pool.close()` is asserted to raise
        nothing with `checkedout() == 0`. Capturing all warnings, the
        library-attributable shutdown set stays empty.
        """
        del anyio_backend_name
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            conn = await duckdb_async_pool.connect()
            cur = conn.cursor()
            await cur.execute("SELECT * FROM range(4) AS t(n)")
            async with await cur.fetch_record_batch() as reader:
                async for _batch in reader:  # drain fully so nothing is pending
                    pass
            assert duckdb_async_pool._pool.checkedout() == 1  # noqa: SLF001
            await conn.close()  # return the drained connection to the pool
            assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
            await duckdb_async_pool.close()  # closes the pool + ADBC source; must raise nothing
            assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
        assert _offending(caught) == []
