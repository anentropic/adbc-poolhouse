"""
Pure-threading self-tests for the blocking stub fakes (Phase 23, D-03/D-04).

These tests exercise `BlockingStubCursor` / `BlockingStubConnection` on plain
threads only -- no anyio, no event loop, no `anyio_backend` fixture, and no
wall-clock sleeps. A worker thread is gated by the stub's own
`threading.Event entered`, then released by the test (`release`), by
`adbc_cancel`, or by `close`. This pins the D-04 attribute contract that
Phases 24/25/27 consume.

The loop-facing dual-backend assertions (offload via `run_blocking`, the
`anyio.Event` bridge) live in Plan 04's `test_harness.py`; this file is the
sync half only.
"""

from __future__ import annotations

import threading

from tests._async_harness.stubs import BlockingStubConnection, BlockingStubCursor


def _run_blocked(target: object) -> tuple[threading.Thread, threading.Event]:
    """Start `target` on a daemon thread and return it plus a done flag."""
    done = threading.Event()

    def _runner() -> None:
        target()  # type: ignore[operator]
        done.set()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return thread, done


class TestBlockingStubCursor:
    """The pure-threading cursor fake's D-04 recording contract."""

    def test_fresh_cursor_has_zeroed_counters(self) -> None:
        """A fresh cursor starts with every counter at 0 and flags False."""
        cursor = BlockingStubCursor()
        assert cursor.execute_call_count == 0
        assert cursor.fetch_call_count == 0
        assert cursor.adbc_cancel_call_count == 0
        assert cursor.close_call_count == 0
        assert cursor.execute_thread_ids == []
        assert cursor.max_concurrent_in_execute == 0
        assert cursor.observed_cancel is False
        assert not cursor.entered.is_set()

    def test_execute_records_then_blocks_until_released(self) -> None:
        """Execute records thread-id + count, sets entered, blocks until release."""
        cursor = BlockingStubCursor()
        thread, done = _run_blocked(lambda: cursor.execute("SELECT 1"))

        assert cursor.entered.wait(timeout=5), "worker never entered execute"
        assert done.wait(timeout=0.05) is False, "execute returned before release"
        assert cursor.execute_call_count == 1
        assert cursor.execute_thread_ids == [thread.ident]
        assert cursor.observed_cancel is False

        cursor.release()
        assert done.wait(timeout=5), "execute did not return after release"
        assert cursor.observed_cancel is False

    def test_adbc_cancel_releases_and_flips_observed_cancel(self) -> None:
        """adbc_cancel unblocks a waiting execute and sets observed_cancel True."""
        cursor = BlockingStubCursor()
        _, done = _run_blocked(lambda: cursor.execute("SELECT 1"))
        assert cursor.entered.wait(timeout=5)

        cursor.adbc_cancel()
        assert done.wait(timeout=5), "adbc_cancel did not release the worker"
        assert cursor.adbc_cancel_call_count == 1
        assert cursor.observed_cancel is True

    def test_close_releases_blocked_worker(self) -> None:
        """Close unblocks a waiting worker and bumps close_call_count."""
        cursor = BlockingStubCursor()
        _, done = _run_blocked(lambda: cursor.execute("SELECT 1"))
        assert cursor.entered.wait(timeout=5)

        cursor.close()
        assert done.wait(timeout=5), "close did not release the worker"
        assert cursor.close_call_count == 1

    def test_fetch_arrow_table_blocks_until_released(self) -> None:
        """fetch_arrow_table records its count and blocks until released."""
        cursor = BlockingStubCursor()
        _, done = _run_blocked(cursor.fetch_arrow_table)
        assert cursor.entered.wait(timeout=5)
        assert cursor.fetch_call_count == 1

        cursor.release()
        assert done.wait(timeout=5)

    def test_two_concurrent_executes_raise_max_concurrent(self) -> None:
        """Two simultaneous executes lift max_concurrent_in_execute to 2."""
        cursor = BlockingStubCursor()

        def _watch() -> None:
            cursor.execute("SELECT 1")

        t1, d1 = _run_blocked(_watch)
        t2, d2 = _run_blocked(_watch)

        # Both workers converge inside _block; the lock-guarded max reaches 2.
        poll = threading.Event()
        for _ in range(500):
            if cursor.max_concurrent_in_execute >= 2:
                break
            poll.wait(timeout=0.01)
        assert cursor.max_concurrent_in_execute == 2

        cursor.release()
        assert d1.wait(timeout=5)
        assert d2.wait(timeout=5)
        assert not t1.is_alive()
        assert not t2.is_alive()


class TestBlockingStubConnection:
    """The connection-level D-04 contract EDGE-09..12/15/18 assert against."""

    def test_fresh_connection_has_zeroed_state(self) -> None:
        """A fresh connection has zeroed counters and no cursors."""
        conn = BlockingStubConnection()
        assert conn.close_call_count == 0
        assert conn.adbc_cancel_call_count == 0
        assert conn.observed_cancel is False
        assert conn.cursors == []

    def test_cursor_appends_and_returns(self) -> None:
        """cursor() returns a BlockingStubCursor and appends it to cursors."""
        conn = BlockingStubConnection()
        cursor = conn.cursor()
        assert isinstance(cursor, BlockingStubCursor)
        assert conn.cursors == [cursor]

    def test_close_increments_count(self) -> None:
        """close() increments close_call_count."""
        conn = BlockingStubConnection()
        conn.close()
        assert conn.close_call_count == 1

    def test_adbc_cancel_increments_and_flips_observed_cancel(self) -> None:
        """adbc_cancel() bumps its counter and sets observed_cancel True."""
        conn = BlockingStubConnection()
        conn.adbc_cancel()
        assert conn.adbc_cancel_call_count == 1
        assert conn.observed_cancel is True

    def test_fresh_connection_has_zeroed_invalidate_count(self) -> None:
        """A fresh connection starts with invalidate_call_count == 0."""
        conn = BlockingStubConnection()
        assert conn.invalidate_call_count == 0

    def test_invalidate_increments_count(self) -> None:
        """One invalidate() call lifts invalidate_call_count to 1."""
        conn = BlockingStubConnection()
        conn.invalidate()
        assert conn.invalidate_call_count == 1

    def test_invalidate_count_never_resets(self) -> None:
        """Two invalidate() calls accumulate to 2 (the counter never resets)."""
        conn = BlockingStubConnection()
        conn.invalidate()
        conn.invalidate()
        assert conn.invalidate_call_count == 2
