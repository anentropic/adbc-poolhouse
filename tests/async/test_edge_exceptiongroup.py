"""
EDGE-19: a genuine ADBC error survives the task group as a BARE `AdbcError`.

`cancellable_offload` runs the blocking driver call inside a two-task anyio task
group (watcher + worker). On Python 3.11+/anyio 4.x a task group ALWAYS bundles a
child exception, so a lone worker `AdbcError` escapes wrapped in a single-member
`ExceptionGroup`. The 25-02/25-03 rewire unwraps that group (`eg.exceptions[0]`)
on the NON-cancel path, so the caller sees the bare `AdbcError` with its exact
type --- preserving the Phase 24 EDGE-17 `pytest.raises(AdbcError)` contract after
the cancellable rewire.

This module pins both halves of that contract on a REAL DuckDB pool:

- The unwrap: a bad-query round-trip raises a bare `AdbcError`, explicitly NOT a
  `BaseExceptionGroup` (probe E --- the single-member group is collapsed).
- The check-in path: after a NON-cancel error the connection returns via the
  reset path (`_pool.checkedout() == 0`), it is NOT invalidated. This is the
  invalidate-only-on-cancel guardrail (Pitfall 6 / EDGE-18): a healthy-but-errored
  connection must not be falsely poisoned. Repeating the errored round-trip in a
  small loop proves no connection leaks across repeated failures.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest
from adbc_driver_manager import Error as AdbcError

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib --- mirrored from
# the limiter suite to keep the loop-count constant in one conceptual place.
_helpers = importlib.import_module("tests.async.test_edge_limiter")
_ACCOUNTING_LOOPS = _helpers._ACCOUNTING_LOOPS  # noqa: SLF001 (shared loop count)
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = importlib.import_module("tests.async._edge_helpers").concurrency_marks


class TestEdge19BareAdbcError:
    """EDGE-19: a real ADBC error escapes the task group bare, connection returns."""

    @pytest.mark.anyio
    async def test_real_adbc_error_unwrapped(self, duckdb_async_pool: AsyncPool) -> None:
        """
        A bad query raises a bare `AdbcError` and the connection returns (not invalidated).

        Runs `SELECT * FROM does_not_exist` on a real DuckDB pool inside a checked-out
        connection. The driver raises a genuine `AdbcError`; `cancellable_offload`
        unwraps the single-member `ExceptionGroup` so the caller sees the bare error
        with its exact type (`pytest.raises(AdbcError)` AND `not
        isinstance(..., BaseExceptionGroup)`). After the errored block the sync pool's
        `checkedout()` is 0 --- the connection returned via the reset path and was NOT
        invalidated (the non-cancel branch fires the reset, never the invalidate;
        Pitfall 6 / EDGE-18 preserved). Repeated across a x50 loop so no errored
        round-trip ever leaks a connection.
        """
        for _ in range(_ACCOUNTING_LOOPS):
            with pytest.raises(AdbcError) as excinfo:
                async with await duckdb_async_pool.connect() as conn:
                    cur = conn.cursor()
                    await cur.execute("SELECT * FROM does_not_exist")
            # The single-member ExceptionGroup was unwrapped: a BARE AdbcError, not
            # a group (probe E --- the 25-02 unwrap preserved the EDGE-17 contract).
            assert not isinstance(excinfo.value, BaseExceptionGroup)
            # The errored connection returned via the reset path (checkedout drains
            # to 0), NOT invalidated --- the invalidate path fires only on cancel.
            assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
