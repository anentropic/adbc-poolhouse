"""
EDGE-08: a cancel set before a NEW-method offload is delivered at the offload boundary.

This is the `adbc_ingest` sibling of
[`test_cancel_before_offload_is_clean`][tests.async.test_edge_cancel_depth]
(EDGE-01, which pins the same guarantee on `execute`). It asserts an anyio
guarantee, not poolhouse behaviour: when a `CancelScope` is already cancelled and
no checkpoint intervenes, the `async with limiter` acquire inside
[`offload`][adbc_poolhouse._async._offload] --- the single chokepoint every new
method routes through --- is the delivery point, so the worker `fn` never runs.
The load-bearing assertion is `ingest_call_count == 0`: the stub's ingest worker
was never entered because the cancel landed at the checkpoint ahead of it.

The trio leg is the DISCRIMINATOR (RESEARCH §Pattern-1): trio guarantees every
`await` is a checkpoint, so if the cancel could ever slip past the offload
boundary and reach the driver call it would surface under trio first. asyncio's
checkpoint semantics are looser, so a green asyncio run alone would not prove the
guarantee.

Cancel-form note (load-bearing): the pre-cancelled `anyio.CancelScope()` swallows
the cancellation at scope exit, so the awaited `adbc_ingest` is NOT wrapped in
`pytest.raises` (per PATTERNS §EDGE-08). The abort machinery is proven never to
fire on this path by the four negative assertions (`adbc_cancel_call_count == 0`,
`invalidate_call_count == 0`, `observed_cancel is False`) --- the offloaded `fn`
never started, so there was nothing to abort. The watchdog is
`real_clock_watchdog`, NEVER `anyio.fail_after` (which autojumps under the trio
`MockClock` and would trip every run).
"""

from __future__ import annotations

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
real_clock_watchdog = _helpers.real_clock_watchdog
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = _helpers.concurrency_marks

# The factory the `make_stub_async_connection` conftest fixture hands back.
_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


@pytest.mark.anyio
async def test_cancel_before_ingest_is_clean(
    make_stub_async_connection: _StubFactory,
    anyio_backend_name: str,
) -> None:
    """
    EDGE-08: a cancel delivered BEFORE the `adbc_ingest` offload touches nothing.

    Clones EDGE-01's `test_cancel_before_offload_is_clean` choreography verbatim,
    swapping the offloaded `execute` for `adbc_ingest` and the counter assertion for
    `ingest_call_count`. The cancel scope is already cancelled when `adbc_ingest` is
    awaited, so the cancellation is delivered at the offload's `async with limiter`
    checkpoint before the worker starts: the stub's ingest worker never runs
    (`ingest_call_count == 0`), no `adbc_cancel` and no `invalidate` fire, and the
    connection stays clean. Runs under both backends; the trio leg discriminates
    (every `await` is a checkpoint there).
    """
    del anyio_backend_name
    async_conn, stub_conn = make_stub_async_connection()
    cur = async_conn.cursor()
    sc = stub_conn.cursors[0]
    with real_clock_watchdog(stub_conn.cursors) as tripped:
        with anyio.CancelScope() as scope:
            scope.cancel()  # cancel BEFORE entering the offload; no intervening await
            await cur.adbc_ingest("t", object())
    assert tripped[0] is False
    assert sc.ingest_call_count == 0  # the driver was never touched — delivered at the checkpoint
    assert sc.adbc_cancel_call_count == 0  # nothing to abort — fn never started
    assert stub_conn.invalidate_call_count == 0
    assert sc.observed_cancel is False
