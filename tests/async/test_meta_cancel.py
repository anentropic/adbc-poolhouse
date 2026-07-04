"""
Streaming-metadata reader cancel-safety (CR-34-01) --- regression guard.

The three streaming metadata methods (`adbc_get_objects` / `adbc_get_statistics` /
`adbc_get_statistic_names`) reuse the cursor's
[`AsyncRecordBatchReader`][adbc_poolhouse._async._reader.AsyncRecordBatchReader] but
have no `adbc_cancel` (a connection exposes none), so they build it with a no-op
cancel hook and `poison_on_cancel=False`.

The hazard this suite pins (found in code review, CR-34-01): if such a reader still
invalidated the connection on a cancelled pull, the no-op cancel would leave the
worker thread blocked inside the driver's `read_next_batch` on the connection while
`fairy.invalidate()` ran on a SECOND thread against that same connection --- the
concurrent single-connection access ADBC forbids, plus a needless drop of a
never-poisoned connection. The contract:

- On a cancelled pull the connection's `invalidate` is **not** driven
  (`invalidate_call_count == 0`), unlike the cursor reader's poison path;
- the no-op cancel hook fires no cursor-level abort;
- the cancellation still surfaces and nothing hangs (dual-backend, looped).

Contrast `test_reader_cancel.py`, where the cursor reader's REAL `adbc_cancel`
genuinely aborts the worker, so invalidating once is correct.
"""

from __future__ import annotations

import functools
import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import anyio
import pytest

from adbc_poolhouse._async._connection import _noop_cancel
from adbc_poolhouse._async._reader import AsyncRecordBatchReader

if TYPE_CHECKING:
    from adbc_poolhouse._async._connection import AsyncConnection
    from tests._async_harness.stubs import BlockingStubConnection

# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib --- same shim the
# other cancel suites use.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate so a rare deadlock
# cannot hide behind one lucky pass (MEMORY loop-flaky-concurrency lesson).
pytestmark = _helpers.concurrency_marks

_StubFactory = Callable[[], "tuple[AsyncConnection, BlockingStubConnection]"]


class TestCr3401MetadataReaderCancel:
    """CR-34-01: a cancelled metadata-reader pull must NOT invalidate the connection."""

    @pytest.mark.anyio
    async def test_cancel_during_metadata_pull_does_not_invalidate(
        self,
        make_stub_async_connection: _StubFactory,
        anyio_backend_name: str,
    ) -> None:
        """
        Cancelling a blocked metadata pull re-raises WITHOUT driving `invalidate`.

        Builds a metadata-style reader (`_noop_cancel`, `poison_on_cancel=False`) over
        a blocking stub reader with one pending batch, so its first pull blocks. The
        surrounding scope is then cancelled while the worker is inside the pull. Because
        the cancel hook is a no-op and poison-recovery is disabled, the connection's
        `invalidate` is never called (`invalidate_call_count == 0`) --- no second thread
        races the still-blocked read. The worker is released in `finally` so it can
        finish; the real-clock watchdog fails fast on a hang. Dual-backend, looped.
        """
        del anyio_backend_name
        async_conn, stub_conn = make_stub_async_connection()
        # Source a blocking sync reader from a stub cursor (retained by the cursor, so
        # its `release()` reaches through to unblock the pull). One pending batch makes
        # the first pull BLOCK --- the cancellable window.
        async_conn.cursor()
        stub_cursor = stub_conn.cursors[-1]
        sync_reader = stub_cursor.fetch_record_batch(batches=[object()])
        # Build the reader exactly as the streaming metadata methods do.
        reader = AsyncRecordBatchReader(
            sync_reader,
            async_conn._limiter,  # noqa: SLF001
            async_conn,
            _noop_cancel,
            poison_on_cancel=False,
        )
        async_conn._reader_open = True  # noqa: SLF001  the lifetime lock the method sets

        with real_clock_watchdog(stub_conn.cursors) as tripped:
            async with anyio.create_task_group() as tg:
                tg.start_soon(functools.partial(_drain_one, reader))
                try:
                    await await_inside(lambda: _pull_started(reader))
                    tg.cancel_scope.cancel()
                finally:
                    for c in stub_conn.cursors:
                        c.release()
        assert tripped[0] is False
        # CR-34-01: a no-op-cancel metadata reader must NOT poison the connection.
        assert stub_conn.invalidate_call_count == 0
        # And nothing aborted a (non-existent) cursor cancel on this reader.
        assert stub_cursor.adbc_cancel_call_count == 0


async def _drain_one(reader: AsyncRecordBatchReader) -> None:
    """Pull a single batch from the reader (the cancellable unit under test)."""
    await reader.__anext__()


def _pull_started(reader: object) -> bool:
    """Whether the reader's stub has recorded at least one blocked pull."""
    stub = getattr(reader, "_reader", None)
    read_calls = getattr(stub, "read_call_count", 0)
    return read_calls >= 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
