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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class BlockingStubCursor:
    """
    Sync DBAPI-shaped cursor fake whose `execute` / `fetch` block until released.

    A pure-`threading` fake (no anyio): `execute` and `fetch_arrow_table` record
    their call and then block on an internal `threading.Event`. The test releases
    the worker via `release` (happy path), `adbc_cancel` (cancel path, which also
    flips `observed_cancel`), or `close`. Every counter and signal the EDGE table
    needs is recorded as a public attribute (D-04, LOCKED names).

    The gate is RE-ARMABLE per blocking call: `_block` clears the internal event
    before waiting, so one cursor can block on `execute`, be released, then block
    AGAIN on `fetch_arrow_table` without the prior release pre-satisfying the
    second wait. `close` is terminal -- a closed cursor releases immediately and
    never re-arms.

    Attributes:
        entered: A `threading.Event` set the instant a worker is inside the
            blocked section. This is the SYNC signal for pure-threading
            self-tests: poll or `wait()` it from a thread, NEVER from the event
            loop. The loop-facing gate is a DISTINCT `anyio.Event` bridged via the
            `on_enter` hook by `run_blocking(..., entered=...)`; the two share a
            name but are different objects. Awaiting this `threading.Event`
            directly on the loop reintroduces the worker-entry race -- async
            consumers must await the `anyio.Event` they handed to `run_blocking`
            instead. Because the gate re-arms, `entered` is also re-armable: it is
            cleared at the start of each `_block` so a second blocking call on the
            same cursor re-fires it from inside the new blocked section.
        on_enter: An optional zero-argument callback invoked INSIDE `_block`,
            after concurrency is recorded and immediately before the worker waits.
            It is the worker-entry hook `run_blocking` uses to bridge the
            loop-facing `anyio.Event` so `await entered.wait()` becomes a true
            "the worker is inside the blocked call" signal (D-CF-01). Stays a
            plain `Callable` so this module remains anyio-free (D-03) -- the anyio
            bridge lives only in `gating.py`. Defaults to `None` (no hook). This
            is the SINGLE-worker fallback hook; for concurrent workers on ONE
            cursor (e.g. `max_concurrent`), each worker registers its own hook via
            `register_on_enter` keyed by its thread id, which takes precedence.
        closed: `True` once `close` has run; `False` otherwise. Public terminal
            close-state flag (read it to assert a cursor was closed). Written
            under the lock so a loop-thread reader never sees a torn state.
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

    def __init__(
        self,
        *,
        entered: threading.Event | None = None,
        on_enter: Callable[[], None] | None = None,
    ) -> None:
        """
        Create a fresh cursor with all counters zeroed.

        Args:
            entered: Optional pre-existing `threading.Event` to use as the
                worker-entry signal. Defaults to a fresh, unset event.
            on_enter: Optional zero-argument callback invoked inside `_block`
                before the worker waits (see the `on_enter` attribute). Defaults
                to `None`; it can also be set later via the public attribute.
        """
        self._event = threading.Event()
        self._lock = threading.Lock()
        self.entered: threading.Event = entered or threading.Event()
        self.on_enter: Callable[[], None] | None = on_enter
        self._on_enter_by_thread: dict[int, Callable[[], None]] = {}
        self.observed_cancel: bool = False
        self.execute_call_count: int = 0
        self.fetch_call_count: int = 0
        self.adbc_cancel_call_count: int = 0
        self.close_call_count: int = 0
        self.execute_thread_ids: list[int] = []
        self._in_execute: int = 0
        self.max_concurrent_in_execute: int = 0
        self._closed: bool = False

    @property
    def closed(self) -> bool:
        """Whether `close` has run (terminal). Backed by `_closed`, lock-written."""
        with self._lock:
            return self._closed

    def register_on_enter(self, callback: Callable[[], None]) -> Callable[[], None]:
        """
        Register a worker-entry hook keyed by the CALLING thread's id.

        Concurrency-safe alternative to the single `on_enter` attribute: when two
        workers block on the SAME cursor at once (e.g. the max-concurrent EDGE
        path), each must bridge its OWN loop-facing event, but a single shared
        attribute would let the last writer clobber the first. Each worker thread
        instead calls this from inside its own offload, so `_block` dispatches the
        hook for the current thread (falling back to `on_enter` if none is
        registered). The hook is removed by the returned cleanup callable.

        Args:
            callback: Zero-argument hook to invoke inside `_block` for the calling
                thread, before it waits.

        Returns:
            A zero-argument cleanup callable that unregisters this thread's hook;
            call it in a `finally` so a reused cursor is never left with a
            dangling per-thread bridge.
        """
        thread_id = threading.get_ident()
        with self._lock:
            self._on_enter_by_thread[thread_id] = callback

        def _cleanup() -> None:
            with self._lock:
                self._on_enter_by_thread.pop(thread_id, None)

        return _cleanup

    def _block(self) -> None:
        """
        Re-arm the gate, record entry, fire `on_enter`/`entered`, then wait.

        Clears the internal event at the START so a prior `release`/`adbc_cancel`
        cannot pre-satisfy this call -- this is what makes the gate re-armable per
        blocking call (one cursor can block on `execute`, be released, then block
        again on `fetch_arrow_table`). A closed cursor short-circuits: it never
        re-arms and returns immediately so no worker is stranded after teardown.

        Lock-guards the `max_concurrent_in_execute` high-water mark on entry and
        the decrement on exit. The `entered` sync signal and the optional
        `on_enter` loop bridge fire from INSIDE the blocked section (after
        concurrency is recorded, before the wait), so a consumer that awaits the
        bridged event observes a worker that is genuinely inside the block
        (D-CF-01) -- never a worker that merely started.
        """
        with self._lock:
            if self._closed:
                # Terminal: a closed cursor never blocks again.
                self.entered.set()
                return
            # Re-arm: clear before waiting so a prior release/cancel/close from a
            # FIRST blocking call cannot pre-satisfy this SECOND one.
            self._event.clear()
            self.entered.clear()
            self._in_execute += 1
            self.max_concurrent_in_execute = max(self.max_concurrent_in_execute, self._in_execute)
            # Prefer this thread's registered hook (concurrent workers on one
            # cursor); fall back to the shared single-worker attribute.
            hook = self._on_enter_by_thread.get(threading.get_ident(), self.on_enter)
        try:
            self.entered.set()  # signal "worker is inside the block" (see gating.py)
            if hook is not None:
                hook()  # bridge the loop-facing anyio.Event from inside
            self._event.wait()  # blocks until released / cancelled / closed
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
        worker returns. The counter and the flag are written together UNDER the
        lock (WR-03) so a loop-thread reader of the cancel path never observes a
        torn `(adbc_cancel_call_count, observed_cancel)` pair.
        """
        with self._lock:
            self.adbc_cancel_call_count += 1
            self.observed_cancel = True
        self._event.set()

    def close(self) -> None:
        """
        Mark the cursor closed and release any blocked worker (terminal).

        Increments `close_call_count` and sets the terminal `closed` flag, both
        under the lock (WR-03) so a reader never sees a half-updated state, then
        releases the internal event. A closed cursor is terminal: `_block`
        short-circuits and never re-arms, so releasing on close guarantees no
        worker is ever stranded in the blocked section (T-23-04).
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
