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

# Wave-0 RED scaffolding: `AsyncCursor.fetch_df` / `fetch_polars` do not exist until
# Plan 31-02 lands, so every reference to them is statically "unknown". These pragmas
# suppress ONLY the errors that are a direct consequence of those not-yet-existing
# methods; delete them once the production methods land and the file type-checks
# cleanly under the strict whole-project gate (matches the Phase 29/30 RED precedent).
# pyright: reportAttributeAccessIssue=false
# pyright: reportUnknownMemberType=false
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from adbc_poolhouse import PoolhouseError

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from tests._async_harness.stubs import BlockingStubConnection

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


class TestDf03MissingDependencyPropagates:
    """DF-03: the native `ModuleNotFoundError` reaches the caller unwrapped."""

    @pytest.mark.anyio
    async def test_fetch_df_missing_pandas_propagates_unchanged(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """
        A worker `ModuleNotFoundError('...pandas')` reaches the caller as-is (not wrapped).

        The stub's `fetch_df` worker raises the injected native error AFTER `_block`
        releases, so it crosses the real `to_thread.run_sync` boundary. The caller
        must observe the exact native `ModuleNotFoundError` with `.name == "pandas"`
        and NOT a `PoolhouseError` --- proving poolhouse neither pre-checks nor wraps
        (D-31-05).
        """
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        # Zero-arg factory: inject the raise on the freshly built stub cursor.
        stub_conn.cursors[-1]._fetch_df_raises = ModuleNotFoundError(  # noqa: SLF001
            "No module named 'pandas'", name="pandas"
        )
        with pytest.raises(ModuleNotFoundError) as ei:
            await cur.fetch_df()
        assert ei.value.name == "pandas"  # exact native error
        assert not isinstance(ei.value, PoolhouseError)  # no wrapping (DF-03)

    @pytest.mark.anyio
    async def test_fetch_polars_missing_polars_propagates_unchanged(
        self, make_stub_async_connection: _StubFactory
    ) -> None:
        """
        A worker `ModuleNotFoundError('...polars')` reaches the caller as-is (not wrapped).

        The `fetch_polars` twin of the pandas propagation proof: the injected native
        error crosses the real `to_thread` boundary and reaches the caller with
        `.name == "polars"`, not a `PoolhouseError` (D-31-05).
        """
        async_conn, stub_conn = make_stub_async_connection()
        cur = async_conn.cursor()
        stub_conn.cursors[-1]._fetch_polars_raises = ModuleNotFoundError(  # noqa: SLF001
            "No module named 'polars'", name="polars"
        )
        with pytest.raises(ModuleNotFoundError) as ei:
            await cur.fetch_polars()
        assert ei.value.name == "polars"  # exact native error
        assert not isinstance(ei.value, PoolhouseError)  # no wrapping (DF-03)
