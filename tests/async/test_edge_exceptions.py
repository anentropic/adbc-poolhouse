"""
Exception-propagation + no-leak EDGE coverage (EDGE-17/18).

EDGE-17: a worker exception reaches the awaiting task with its EXACT type and a
traceback that still includes the off-loop worker frame --- the single `offload`
chokepoint never catches or re-wraps it (ACUR-06). EDGE-18: an exception raised
inside a checked-out scope still returns the connection to the pool, with no
cumulative leak across many iterations.

Both run under BOTH backends and drive the REAL DuckDB driver (a bad query is the
most faithful source of a genuine `AdbcError`).
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

import pytest
from adbc_driver_manager import Error as AdbcError

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

# EDGE-18 leak loop: a per-iteration checkout leak compounds across this many runs.
_LEAK_LOOPS = 20


class TestEdge17ExceptionFidelity:
    """A worker `AdbcError` propagates with its exact type and the worker frame."""

    @pytest.mark.anyio
    async def test_exact_type_and_worker_frame_in_traceback(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        A bad query raises the precise `AdbcError` subclass with the worker frame.

        The offload chokepoint re-raises the worker's exception verbatim, so the
        caller sees the genuine `adbc_driver_manager` error type (not a wrapped
        library error) AND a traceback that still passes through the off-loop
        `_offload` worker frame --- proving nothing swallowed or re-tagged it.
        """
        with pytest.raises(AdbcError) as exc_info:
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT * FROM table_that_does_not_exist")
        exc = exc_info.value
        # Exact type: a concrete adbc_driver_manager.Error subclass, not a re-wrap.
        assert type(exc).__module__.startswith("adbc_driver_manager")
        assert isinstance(exc, AdbcError)
        rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        # The off-loop worker frame is still in the traceback (the offload
        # chokepoint that ran the blocking call on the worker thread).
        assert "_offload" in rendered
        assert "execute" in rendered


class TestEdge18NoLeakOnError:
    """An exception inside a checked-out scope leaks no connection (across N runs)."""

    @pytest.mark.anyio
    async def test_no_cumulative_leak_over_iterations(self, duckdb_async_pool: AsyncPool) -> None:
        """
        Forcing an error in the body N times always returns `checkedout()` to 0.

        Each iteration checks out a connection, raises inside the `async with`
        body, and relies on `__aexit__`'s shielded reclaim to return the connection
        --- so `checkedout()` is 0 after every iteration and never climbs, proving
        no connection is stranded by an error path (EDGE-18).
        """
        for _ in range(_LEAK_LOOPS):
            with pytest.raises(AdbcError):
                async with await duckdb_async_pool.connect() as conn:
                    cur = conn.cursor()
                    # Raise AFTER checkout, inside the managed scope.
                    await cur.execute("SELECT * FROM still_does_not_exist")
            assert duckdb_async_pool._pool.checkedout() == 0
        # Final state: nothing accumulated across all iterations.
        assert duckdb_async_pool._pool.checkedout() == 0
