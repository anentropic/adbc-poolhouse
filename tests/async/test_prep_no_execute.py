"""
Async `adbc_execute_schema` value + no-execute proof (PREP-02, D-35-06) --- regression coverage.

Phase 35's `await cursor.adbc_execute_schema(operation, parameters=None)` returns
the RESULT-set schema WITHOUT executing the query. The load-bearing PREP-02 proof
is exactly that "without executing" clause: a query whose schema is resolved must
never run. This suite pins it deterministically on the blocking stub cursor
(`tests/_async_harness/stubs.py`), which:

- returns an injectable sentinel `pyarrow.Schema` from `adbc_execute_schema`, so the
  test asserts the awaited value IS that object (the value passes through the offload
  chokepoint unchanged), AND
- bumps `execute_schema_call_count` but NEVER `execute_call_count` --- so
  `stub_cursor.execute_call_count == 0` is the no-execute proof.

DuckDB CANNOT host this leg: it raises `NotSupportedError` for `adbc_execute_schema`
(that native-error passthrough is `test_prep_unsupported.py`'s job), which is exactly
why the stub carries the positive value here (RESEARCH Open Question 1).

Harness discipline (event-gated, no sleeps): `await_inside` waits until the worker is
provably inside the blocked call before releasing it; `real_clock_watchdog` (a
wall-clock side thread --- NOT `anyio.fail_after`, which autojumps under the trio
`MockClock`) fails fast on a hang. Both backends.

Status: `AsyncCursor.adbc_execute_schema` is implemented (Plan 35-02); this file is
passing regression coverage proving the awaited schema passes through unchanged and
the query is never executed.
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
# keyword), so the sibling helper module is loaded via importlib --- same shim the
# other stub-driven suites use.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks

_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


class TestPrep02NoExecute:
    """PREP-02: `adbc_execute_schema` returns the schema WITHOUT executing the query."""

    @pytest.mark.anyio
    async def test_execute_schema_returns_value_without_executing(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        The awaited value IS the injected sentinel schema AND `execute_call_count == 0`.

        Injects a sentinel `pyarrow.Schema` as the stub cursor's
        `_execute_schema_result`, drives `adbc_execute_schema` inside a task group,
        waits until the worker is provably inside the blocked call
        (`execute_schema_call_count >= 1`), then releases the gate so the call returns.
        Asserts the awaited value IS the sentinel object (pass-through through the
        offload chokepoint) AND `stub_cursor.execute_call_count == 0` --- the PREP-02
        no-execute proof. Dual-backend, looped, real-clock watchdog.
        """
        del anyio_backend_name
        sentinel = pyarrow.schema([("id", pyarrow.int64())])
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        result_holder: list[object] = []
        with real_clock_watchdog(stub_conn.cursors) as tripped:
            stub_cursor = stub_conn.cursors[-1]
            stub_cursor._execute_schema_result = sentinel  # noqa: SLF001  injectable knob
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drive_execute_schema, cur, result_holder))
                try:
                    await await_inside(lambda: stub_conn.cursors[-1].execute_schema_call_count >= 1)
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        assert result_holder == [sentinel]  # the sentinel passed through unchanged
        assert result_holder[0] is sentinel
        assert stub_cursor.execute_call_count == 0  # the no-execute proof (PREP-02)


async def _drive_execute_schema(cursor: AsyncCursor, sink: list[object]) -> None:
    """Run a single `adbc_execute_schema`, recording its result (the unit under test)."""
    sink.append(await cursor.adbc_execute_schema("SELECT 1"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
