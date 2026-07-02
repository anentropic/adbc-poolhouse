"""
Async DataFrame missing-dependency propagation (DF-03) --- Wave-0 RED scaffolding.

pandas/polars stay user-supplied runtime deps: poolhouse never imports them and
adds NO `find_spec` pre-check and NO wrapping (D-31-05). A missing dependency raises
the NATIVE `ModuleNotFoundError` inside the worker thread, which the single
`to_thread.run_sync` offload chokepoint re-raises UNCHANGED --- exact type and
`.name` --- exactly as poolhouse already surfaces a missing ADBC driver (EDGE-17).

These tests prove that contract with the deterministic, env-independent mechanism
(RESEARCH "DF-03 mechanism decision"): a `BlockingStubCursor` whose `fetch_df` /
`fetch_polars` worker raises the injected `ModuleNotFoundError` AFTER `_block`
releases, so the error crosses the REAL `to_thread` boundary (not a synchronous
raise). The assertion is the exact native surface --- `ei.value.name ==
"pandas"`/`"polars"` AND `not isinstance(ei.value, PoolhouseError)` --- so any
spurious `find_spec` / `try-except` wrapping in the production method would FAIL
here. The two flavours carry `pandas` / `polars` in their names for `-k` selection.

Wave-0 status: `AsyncCursor.fetch_df` / `fetch_polars` do NOT exist yet, so these
FAIL (RED) --- the acceptance signal. Both backends via `anyio_backend`. Closes the
worker-thread -> caller exception-path boundary once GREEN.
"""

from __future__ import annotations

import importlib

import anyio
import pytest

from adbc_poolhouse import PoolhouseError
from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside


class TestDf03MissingDependencyPropagates:
    """DF-03: the native `ModuleNotFoundError` reaches the caller unwrapped."""

    @pytest.mark.anyio
    async def test_fetch_df_missing_pandas_propagates_unchanged(
        self, anyio_backend_name: str
    ) -> None:
        """
        A worker `ModuleNotFoundError('...pandas')` reaches the caller as-is (not wrapped).

        The stub's `fetch_df` worker raises the injected native error AFTER `_block`
        releases, so it crosses the real `to_thread.run_sync` boundary. Once the
        worker is inside the block (`df_call_count >= 1`), the test releases the gate
        so the injected raise fires and propagates. The caller must observe the exact
        native `ModuleNotFoundError` with `.name == "pandas"` and NOT a
        `PoolhouseError` --- proving poolhouse neither pre-checks nor wraps (D-31-05).
        """
        del anyio_backend_name
        limiter = anyio.CapacityLimiter(4)
        stub_conn = BlockingStubConnection()
        async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
        cur = async_conn.cursor()
        stub = stub_conn.cursors[-1]
        stub._fetch_df_raises = ModuleNotFoundError(  # noqa: SLF001
            "No module named 'pandas'", name="pandas"
        )
        captured: list[BaseException] = []

        async def _drive() -> None:
            try:
                await cur.fetch_df()
            except BaseException as exc:  # noqa: BLE001  (assert the exact type below)
                captured.append(exc)

        async with anyio.create_task_group() as tg:
            tg.start_soon(_drive)
            # Release only once the worker is genuinely inside `_block`, so the raise
            # crosses the real `to_thread.run_sync` boundary (not a synchronous raise).
            await await_inside(lambda: stub.df_call_count >= 1)
            stub.release()

        assert len(captured) == 1
        exc = captured[0]
        assert isinstance(exc, ModuleNotFoundError)
        assert exc.name == "pandas"  # exact native error
        assert not isinstance(exc, PoolhouseError)  # no wrapping (DF-03)

    @pytest.mark.anyio
    async def test_fetch_polars_missing_polars_propagates_unchanged(
        self, anyio_backend_name: str
    ) -> None:
        """
        A worker `ModuleNotFoundError('...polars')` reaches the caller as-is (not wrapped).

        The `fetch_polars` twin of the pandas propagation proof: once the worker is
        inside the block (`polars_call_count >= 1`) the gate is released, the injected
        native error crosses the real `to_thread` boundary, and it reaches the caller
        with `.name == "polars"`, not a `PoolhouseError` (D-31-05).
        """
        del anyio_backend_name
        limiter = anyio.CapacityLimiter(4)
        stub_conn = BlockingStubConnection()
        async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
        cur = async_conn.cursor()
        stub = stub_conn.cursors[-1]
        stub._fetch_polars_raises = ModuleNotFoundError(  # noqa: SLF001
            "No module named 'polars'", name="polars"
        )
        captured: list[BaseException] = []

        async def _drive() -> None:
            try:
                await cur.fetch_polars()
            except BaseException as exc:  # noqa: BLE001  (assert the exact type below)
                captured.append(exc)

        async with anyio.create_task_group() as tg:
            tg.start_soon(_drive)
            await await_inside(lambda: stub.polars_call_count >= 1)
            stub.release()

        assert len(captured) == 1
        exc = captured[0]
        assert isinstance(exc, ModuleNotFoundError)
        assert exc.name == "polars"  # exact native error
        assert not isinstance(exc, PoolhouseError)  # no wrapping (DF-03)
