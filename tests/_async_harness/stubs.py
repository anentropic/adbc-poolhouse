"""
Pure-threading blocking stub fakes for the async harness (Phase 23, D-03/D-04).

This module is deliberately anyio-free: it imports no `anyio`, no event loop,
and no async machinery whatsoever -- only the standard-library `threading`
module. Being sync-only is exactly what makes the stubs framework-neutral, so
the same fakes drive both the asyncio and trio legs of every later EDGE test
(Phases 24/25/27) without ever importing a backend (D-03).

The two classes fake the DBAPI surface the async wrappers will offload onto a
worker thread:

- [`BlockingStubCursor`][tests._async_harness.stubs.BlockingStubCursor] -- a
  cursor whose `execute` / `fetch_arrow_table` block forever on an internal
  `threading.Event` until the test releases them (`release`), cancels them
  (`adbc_cancel`), or closes them (`close`).
- [`BlockingStubConnection`][tests._async_harness.stubs.BlockingStubConnection]
  -- the connection-level mirror, recording the close / cancel / cursor-handle
  contract that EDGE-09..12/15/18 assert against.

The public attribute names below are a HARD CONTRACT (D-04): later phases read
them by name, so they are locked and must not be renamed.

Dual-`entered` warning (load-bearing -- see the `entered` attribute docstring):
the stub's `entered` is a `threading.Event`, the SYNC signal for pure-threading
self-tests. The loop-facing "worker is inside execute" gate is a SEPARATE
`anyio.Event` passed to
[`run_blocking`][tests._async_harness.gating.run_blocking]. Same name, different
objects -- never await the stub's `threading.Event` on the event loop.
"""

from __future__ import annotations

import threading


class BlockingStubCursor:
    """
    Sync DBAPI-shaped cursor fake whose `execute` / `fetch` block until released.

    A pure-`threading` fake (no anyio): `execute` and `fetch_arrow_table` record
    their call and then block forever on an internal `threading.Event`. The test
    releases the worker via `release` (happy path), `adbc_cancel` (cancel path,
    which also flips `observed_cancel`), or `close`. Every counter and signal the
    EDGE table needs is recorded as a public attribute (D-04, LOCKED names).

    Attributes:
        entered: A `threading.Event` set the instant a worker enters the blocked
            section. This is the SYNC signal for pure-threading self-tests: poll
            or `wait()` it from a thread, NEVER from the event loop. The
            loop-facing gate is a DISTINCT `anyio.Event` you pass to
            `run_blocking(..., entered=...)`; the two share a name but are
            different objects. Awaiting this `threading.Event` directly on the
            loop reintroduces the worker-entry race -- async consumers must await
            the `anyio.Event` they handed to `run_blocking` instead.
        observed_cancel: `True` once `adbc_cancel` has run; `False` otherwise.
        execute_call_count: Number of `execute` calls.
        fetch_call_count: Number of `fetch_arrow_table` calls.
        adbc_cancel_call_count: Number of `adbc_cancel` calls.
        close_call_count: Number of `close` calls.
        execute_thread_ids: The `threading.get_ident()` of each `execute` caller,
            in call order -- lets EDGE-25 assert work ran off the loop thread.
        max_concurrent_in_execute: The high-water mark of workers simultaneously
            inside the blocked section (lock-guarded), backing EDGE-12/EDGE-15.

    Example:
        ```python
        import threading

        from tests._async_harness.stubs import BlockingStubCursor

        cursor = BlockingStubCursor()
        worker = threading.Thread(target=lambda: cursor.execute("SELECT 1"))
        worker.start()

        cursor.entered.wait()  # block until the worker is inside execute
        assert cursor.execute_call_count == 1

        cursor.release()  # let the blocked execute return
        worker.join()
        ```
    """

    def __init__(self, *, entered: threading.Event | None = None) -> None:
        """
        Create a fresh cursor with all counters zeroed.

        Args:
            entered: Optional pre-existing `threading.Event` to use as the
                worker-entry signal. Defaults to a fresh, unset event.
        """
        self._event = threading.Event()
        self._lock = threading.Lock()
        self.entered: threading.Event = entered or threading.Event()
        self.observed_cancel: bool = False
        self.execute_call_count: int = 0
        self.fetch_call_count: int = 0
        self.adbc_cancel_call_count: int = 0
        self.close_call_count: int = 0
        self.execute_thread_ids: list[int] = []
        self._in_execute: int = 0
        self.max_concurrent_in_execute: int = 0
        self._closed: bool = False

    def _block(self) -> None:
        """
        Record entry/concurrency, signal `entered`, then block until released.

        Lock-guards the `max_concurrent_in_execute` high-water mark on entry and
        the decrement on exit, sets the `entered` sync signal, and waits on the
        internal event (which is released by `release`, `adbc_cancel`, or
        `close`).
        """
        with self._lock:
            self._in_execute += 1
            self.max_concurrent_in_execute = max(self.max_concurrent_in_execute, self._in_execute)
        try:
            self.entered.set()  # signal "worker is inside execute" (see gating.py)
            self._event.wait()  # blocks FOREVER until released
        finally:
            with self._lock:
                self._in_execute -= 1

    def execute(self, operation: str, parameters: object = None) -> None:
        """
        Record the call, then block until released.

        Args:
            operation: The SQL text (recorded only by the call count; never run).
            parameters: Optional bound parameters (ignored by the fake).
        """
        del operation, parameters
        with self._lock:
            self.execute_call_count += 1
            self.execute_thread_ids.append(threading.get_ident())
        self._block()

    def fetch_arrow_table(self) -> object:
        """
        Record the call, block until released, then return `None`.

        Returns:
            `None`. Later phases inject a real `pyarrow.Table` where a result is
            needed; the bare fake returns `None`.
        """
        with self._lock:
            self.fetch_call_count += 1
        self._block()
        return None

    def adbc_cancel(self) -> None:
        """
        Flip `observed_cancel` and release any blocked `execute` / `fetch`.

        Models the driver-level cancel: increments `adbc_cancel_call_count`, sets
        `observed_cancel` to `True`, and releases the internal event so a blocked
        worker returns.
        """
        with self._lock:
            self.adbc_cancel_call_count += 1
        self.observed_cancel = True
        self._event.set()

    def close(self) -> None:
        """
        Increment `close_call_count` and release any blocked worker.

        Releasing the event on close guarantees no worker is ever stranded in the
        blocked section (T-23-04).
        """
        with self._lock:
            self.close_call_count += 1
        self._closed = True
        self._event.set()

    def release(self) -> None:
        """
        Test-only: unblock a waiting worker WITHOUT cancelling (happy path).

        Leaves `observed_cancel` `False` -- use this to model a query that
        completes normally, as opposed to `adbc_cancel`.
        """
        self._event.set()


class BlockingStubConnection:
    """
    Sync connection fake recording the close / cancel / cursor-handle contract.

    The connection-level mirror of
    [`BlockingStubCursor`][tests._async_harness.stubs.BlockingStubCursor], kept
    pure-`threading` (no anyio) for the same framework-neutrality reason (D-03).
    Its public attributes are made EXPLICIT so the D-04 hard contract is
    unambiguous for the connection-level EDGE cases (EDGE-09..12/15/18) in Phases
    24/25.

    Attributes:
        cursors: Every `BlockingStubCursor` handed out by `cursor`, in creation
            order.
        close_call_count: Number of `close` calls.
        adbc_cancel_call_count: Number of `adbc_cancel` calls.
        observed_cancel: `True` once `adbc_cancel` has run; `False` otherwise.

    Example:
        ```python
        from tests._async_harness.stubs import BlockingStubConnection

        conn = BlockingStubConnection()
        cursor = conn.cursor()
        assert conn.cursors == [cursor]

        conn.close()
        assert conn.close_call_count == 1
        ```
    """

    def __init__(self) -> None:
        """Create a fresh connection with zeroed counters and no cursors."""
        self._lock = threading.Lock()
        self.cursors: list[BlockingStubCursor] = []
        self.close_call_count: int = 0
        self.adbc_cancel_call_count: int = 0
        self.observed_cancel: bool = False

    def cursor(self) -> BlockingStubCursor:
        """
        Create a `BlockingStubCursor`, append it to `cursors`, and return it.

        Returns:
            The newly created cursor, also retained in `cursors` so a test can
            assert against the connection's handed-out cursor handles.
        """
        cursor = BlockingStubCursor()
        with self._lock:
            self.cursors.append(cursor)
        return cursor

    def close(self) -> None:
        """Increment `close_call_count`."""
        with self._lock:
            self.close_call_count += 1

    def adbc_cancel(self) -> None:
        """Increment `adbc_cancel_call_count` and set `observed_cancel` to `True`."""
        with self._lock:
            self.adbc_cancel_call_count += 1
        self.observed_cancel = True
