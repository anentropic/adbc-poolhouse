"""
Async partitioned-execution value pass-through (PART-01) --- regression coverage.

`await cursor.adbc_execute_partitions(operation, parameters=None)` returns the
driver's `(partitions, schema)` tuple, and `await cursor.adbc_read_partition(descriptor)`
forwards the descriptor and returns `None` (the cursor's result set is set up as a
side effect, drained afterwards by the usual `fetch_*` methods).

No live backend in the matrix implements partitioned execution --- DuckDB raises
`NotSupportedError` for both (that native-error passthrough is
`test_partitions_unsupported.py`'s job) --- so this suite pins the positive
pass-through on the blocking stub cursor (`tests/_async_harness/stubs.py`), which:

- returns an injectable `(partitions, schema)` tuple from `adbc_execute_partitions`,
  so the test asserts the awaited value IS that object (unchanged through the offload
  chokepoint), AND
- bumps `read_partition_call_count` from `adbc_read_partition` and returns `None`.

Harness discipline (event-gated, no sleeps): `await_inside` waits until the worker is
provably inside the blocked call before releasing it; `real_clock_watchdog` (a
wall-clock side thread) fails fast on a hang. Both backends.
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
    from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
pytestmark = _helpers.concurrency_marks

_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


class TestPart01Roundtrip:
    """PART-01: the partition methods pass their driver values through unchanged."""

    @pytest.mark.anyio
    async def test_execute_partitions_returns_injected_tuple(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        The awaited value IS the injected `(partitions, schema)` tuple, unchanged.

        Injects a sentinel `(list[bytes], pyarrow.Schema)` as the stub cursor's
        `_execute_partitions_result`, drives `adbc_execute_partitions` inside a task
        group, waits until the worker is provably inside the blocked call, then
        releases the gate. Asserts the awaited value IS the sentinel tuple ---
        pass-through through the offload chokepoint. Dual-backend, looped.
        """
        del anyio_backend_name
        schema = pyarrow.schema([("id", pyarrow.int64())])
        sentinel: tuple[list[bytes], pyarrow.Schema] = ([b"part-0", b"part-1"], schema)
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        result_holder: list[object] = []
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            stub_cursor = stub_conn.cursors[-1]
            stub_cursor._execute_partitions_result = sentinel  # noqa: SLF001  injectable knob
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_execute_partitions, cur, result_holder))
                try:
                    await await_inside(
                        lambda: stub_conn.cursors[-1].execute_partitions_call_count >= 1
                    )
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert result_holder == [sentinel]
        assert result_holder[0] is sentinel  # the tuple passed through unchanged

    @pytest.mark.anyio
    async def test_read_partition_forwards_and_returns_none(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        `adbc_read_partition` forwards the descriptor, records the call, returns `None`.

        Drives `adbc_read_partition` inside a task group, waits until the worker is
        inside the blocked call (`read_partition_call_count >= 1`), then releases the
        gate. Asserts the call completed with a `None` result (like `execute`) and the
        stub recorded exactly one read. Dual-backend, looped.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        result_holder: list[object] = []
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            stub_cursor = stub_conn.cursors[-1]
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_read_partition, cur, result_holder))
                try:
                    await await_inside(lambda: stub_conn.cursors[-1].read_partition_call_count >= 1)
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert result_holder == [None]
        assert stub_cursor.read_partition_call_count == 1


async def _drive_execute_partitions(cursor: AsyncCursor, sink: list[object]) -> None:
    """Run a single `adbc_execute_partitions`, recording its result (the unit under test)."""
    sink.append(await cursor.adbc_execute_partitions("SELECT 1"))


async def _drive_read_partition(cursor: AsyncCursor, sink: list[object]) -> None:
    """Run a single `adbc_read_partition`, recording its (None) result."""
    sink.append(await cursor.adbc_read_partition(b"part-0"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
