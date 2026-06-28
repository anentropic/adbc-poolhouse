"""
EDGE-29 backend parity: the cancel-signal tuple is identical under asyncio and trio.

CANCEL-04 demands the cancellation machinery behave the same on both anyio
backends. This proves it at the signal level: the canonical EDGE-02 cancel (a
worker gated inside the stub's `execute`, then the scope cancelled) is run once per
backend with byte-identical setup, and each leg records the
`(adbc_cancel_count, invalidate_count, checkedout_after)` tuple into a
session-scoped dict keyed by `anyio_backend_name`. A final, non-parametrized reader
test asserts `tuple["asyncio"] == tuple["trio"]`.

The load-bearing assertion is tuple EQUALITY, not the individual values (those are
pinned by `test_edge_cancel_depth.py`). `checkedout_after` is read from the stub
path: the stub connection has no real pool, so the invalidate-driven drainage is
represented by `0` exactly when the poison-recovery fired (`invalidate_count == 1`),
the same `0` the real `duckdb` leg asserts via `pool.checkedout()`. Both legs run
under `real_clock_watchdog` (the autojump-immune wall-clock watchdog, NOT
`anyio.fail_after`) and gate with `await_inside` (no positive-duration sleeps), so
the parity proof is itself x20-loop-stable.
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
    from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]

# The signal tuple EDGE-29 compares across backends.
_CancelTuple = tuple[int, int, int]


@pytest.fixture(scope="session")
def record_cancel_tuple() -> dict[str, _CancelTuple]:
    """
    Session-scoped store both backend legs write their cancel-signal tuple into.

    Keyed by `anyio_backend_name` (`"asyncio"` / `"trio"`). Session-scoped so the
    asyncio and trio legs of the parametrized EDGE-29 test (which run as separate
    function-scoped invocations) accumulate into ONE dict that the non-parametrized
    reader test can compare after both have populated it.

    Returns:
        The shared dict mapping a backend name to its
        `(adbc_cancel_count, invalidate_count, checkedout_after)` tuple.
    """
    return {}


class TestEdge29BackendParity:
    """EDGE-29 / CANCEL-04: the cancel-signal tuple is equal under asyncio and trio."""

    @pytest.mark.anyio
    async def test_records_cancel_tuple_per_backend(
        self,
        record_cancel_tuple: dict[str, _CancelTuple],
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        Run the canonical EDGE-02 cancel and store its signal tuple for this backend.

        The choreography is byte-identical to `test_edge_cancel_depth.py`'s EDGE-02
        `during` leg (worker gated inside `execute`, scope cancelled, workers
        released in a `finally`) --- the only variable across the two invocations of
        this test is the backend. After the cancelled scope, the tuple
        `(adbc_cancel_count, invalidate_count, checkedout_after)` is recorded; the
        stub has no real pool, so `checkedout_after` is `0` exactly when the
        poison-recovery fired (`invalidate_count == 1`), mirroring the real pool's
        `checkedout() == 0`.
        """
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
        assert tripped[0] is False, "EDGE-29 watchdog tripped: a worker hung"
        adbc_cancel_count = sc.adbc_cancel_call_count
        invalidate_count = stub_conn.invalidate_call_count
        # The stub has no pool; the invalidate-driven drainage is `0` iff the
        # poison-recovery ran --- the same `0` the real pool reports via checkedout().
        checkedout_after = 0 if invalidate_count == 1 else 1
        record_cancel_tuple[anyio_backend_name] = (
            adbc_cancel_count,
            invalidate_count,
            checkedout_after,
        )

    def test_tuple_equal_across_backends(
        self,
        record_cancel_tuple: dict[str, _CancelTuple],
    ) -> None:
        """
        Assert both backend legs recorded the SAME cancel-signal tuple (EDGE-29).

        Non-parametrized and ordered AFTER the parametrized recorder (pytest runs
        the two recorder invocations first), so both `"asyncio"` and `"trio"` keys
        are present. The load-bearing assertion is tuple EQUALITY: the individual
        values are pinned by `test_edge_cancel_depth.py`; here the only claim is that
        the cancel machinery is backend-symmetric (CANCEL-04).
        """
        assert "asyncio" in record_cancel_tuple, "the asyncio leg did not record its tuple"
        assert "trio" in record_cancel_tuple, "the trio leg did not record its tuple"
        assert record_cancel_tuple["asyncio"] == record_cancel_tuple["trio"], (
            "cancel-signal tuple differs across backends: "
            f"asyncio={record_cancel_tuple['asyncio']} trio={record_cancel_tuple['trio']}"
        )
