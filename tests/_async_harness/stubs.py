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
- [`BlockingStubReader`][tests._async_harness.stubs.BlockingStubReader] -- the
  Phase-29 streaming sibling, satisfying the `_SyncReader` structural surface
  (`schema` property, blocking `read_next_batch`, `close`) so the async record-batch
  reader can offload onto it. Handed out by `BlockingStubCursor.fetch_record_batch`.
  It reuses the same sticky-release `_block` idiom but has NO `adbc_cancel` of its
  own -- cancellation is fired through the owning cursor (Phase-29 Pitfall 4).

The public attribute names below are a HARD CONTRACT (D-04): later phases read
them by name, so they are locked and must not be renamed.

Dual-`entered` warning (load-bearing -- see the `entered` attribute docstring):
the stub's `entered` is a `threading.Event`, the SYNC signal for pure-threading
self-tests. The loop-facing "worker is inside execute" gate is a SEPARATE
`anyio.Event` passed to
[`run_blocking`][tests._async_harness.gating.run_blocking]. Same name, different
objects -- never await the stub's `threading.Event` on the event loop.

Sticky-release design (load-bearing -- do NOT regress to a bare `Event.set()`):
`close` and `adbc_cancel` are RELEASE signals that can race AHEAD of the worker
reaching `_block`. The dispatch-window cancel tests fire `adbc_cancel` after the
worker is dispatched but before its thread enters `_block`; a real driver's
`adbc_cancel` likewise latches, so a cancel issued before the call enters is
still observed. Because `_block` clears the internal `Event` at entry to re-arm
the gate, a release modelled as a transient `Event.set()` alone is LOST whenever
it lands before that clear -- a thread-scheduling-dependent lost-wakeup that
hangs on slower hosts (it surfaced as a Linux-only CI failure that passed on
macOS). So both terminal releases latch a sticky boolean UNDER THE LOCK
(`_closed`, `_cancelled`) that `_block` checks at entry before the re-arm clear;
`Event.set()` only covers a worker that is already waiting. `release` (the happy
path) stays transient on purpose -- the worker is provably inside `_block`
(the test waits for `entered`), so it cannot race the clear, and keeping it
non-sticky is what preserves per-call re-arm (execute -> release -> fetch on one
cursor). Rule of thumb: a release that can outrun its consumer must latch under
the same lock the wait re-arms under; a bare `set()` paired with an entry-time
`clear()` is a lost-wakeup waiting to happen. (Full diagnosis: PR #32 /
phase-26 LEARNINGS.)
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
        ingest_call_count: Number of `adbc_ingest` calls --- the in-flight gate the
            Phase 30 cancel test polls (`await_inside(... >= 1)`) before cancelling.
        prepare_call_count: Number of `adbc_prepare` calls --- the Phase 35 in-flight
            gate the prepared-statement cancel test polls (`await_inside(... >= 1)`)
            before cancelling. NEVER coupled to `execute_call_count` (the PREP-02
            no-execute proof reads `execute_call_count == 0`).
        execute_schema_call_count: Number of `adbc_execute_schema` calls --- the
            `adbc_prepare` twin, likewise decoupled from `execute_call_count` so the
            no-execute proof holds for either method.
        execute_partitions_call_count: Number of `adbc_execute_partitions` calls --- the
            in-flight gate the v1.5.1 partition cancel test polls
            (`await_inside(... >= 1)`) before cancelling.
        read_partition_call_count: Number of `adbc_read_partition` calls --- the
            in-flight gate for the partition-read cancel leg.
        df_call_count: Number of `fetch_df` calls --- the Phase 31 in-flight gate the
            DataFrame busy/cancel tests poll (`await_inside(... >= 1)`) before
            cancelling or asserting busy.
        polars_call_count: Number of `fetch_polars` calls --- the `fetch_polars` twin
            of `df_call_count`.
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
        fetch_df_raises: BaseException | None = None,
        fetch_polars_raises: BaseException | None = None,
    ) -> None:
        """
        Create a fresh cursor with all counters zeroed.

        Args:
            entered: Optional pre-existing `threading.Event` to use as the
                worker-entry signal. Defaults to a fresh, unset event.
            on_enter: Optional zero-argument callback invoked inside `_block`
                before the worker waits (see the `on_enter` attribute). Defaults
                to `None`; it can also be set later via the public attribute.
            fetch_df_raises: Optional exception the `fetch_df` worker raises AFTER
                `_block` releases, so the error crosses the real
                `to_thread.run_sync` boundary (proving the `_offload.py` EDGE-17
                re-raise). Defaults to `None` (return `None`). Set it to a native
                `ModuleNotFoundError("No module named 'pandas'")` to drive the DF-03
                missing-dependency propagation test. It can also be set later via
                the `_fetch_df_raises` attribute (the zero-arg stub factory does
                this on `cursors[-1]`).
            fetch_polars_raises: The `fetch_polars` twin of `fetch_df_raises`.
        """
        self._event = threading.Event()
        self._lock = threading.Lock()
        self.entered: threading.Event = entered or threading.Event()
        self.on_enter: Callable[[], None] | None = on_enter
        self._on_enter_by_thread: dict[int, Callable[[], None]] = {}
        self.observed_cancel: bool = False
        self.execute_call_count: int = 0
        self.fetch_call_count: int = 0
        self.ingest_call_count: int = 0
        self.prepare_call_count: int = 0
        self.execute_schema_call_count: int = 0
        self.execute_partitions_call_count: int = 0
        self.read_partition_call_count: int = 0
        self.df_call_count: int = 0
        self.polars_call_count: int = 0
        # Optional native exceptions the fetch_df/fetch_polars workers raise AFTER
        # `_block` releases, so the error crosses the real `to_thread.run_sync`
        # boundary (DF-03). `None` = return `None`. Public-settable on `cursors[-1]`.
        self._fetch_df_raises: BaseException | None = fetch_df_raises
        self._fetch_polars_raises: BaseException | None = fetch_polars_raises
        # Injectable results the Phase-35 `adbc_prepare` / `adbc_execute_schema`
        # workers return AFTER `_block` releases (mirrors `_fetch_df_raises` --- a
        # per-cursor public-settable knob on `cursors[-1]`). `adbc_prepare` tolerates
        # a `pyarrow.Schema` OR `None` (D-35-02); `adbc_execute_schema` returns the
        # injected sentinel `pyarrow.Schema` while NEVER touching `execute_call_count`
        # --- the PREP-02 no-execute proof reads that counter as `0`.
        self._prepare_result: object = None
        self._execute_schema_result: object = None
        # Injectable `(partitions, schema)` tuple the `adbc_execute_partitions` worker
        # returns AFTER `_block` releases (mirrors `_execute_schema_result`). No live
        # backend in the matrix implements partitioned execution (DuckDB raises
        # `NotSupportedError`), so the stub carries the positive round-trip value.
        self._execute_partitions_result: object = None
        self.adbc_cancel_call_count: int = 0
        self.close_call_count: int = 0
        self.execute_thread_ids: list[int] = []
        self._in_execute: int = 0
        self.max_concurrent_in_execute: int = 0
        self._closed: bool = False
        # Sticky cancel state, symmetric with `_closed`. A real driver's
        # `adbc_cancel` latches cancellation, so a cancel that arrives BEFORE the
        # worker enters the driver call is still honoured. `_block` checks this at
        # entry (under the lock) so a dispatch-window cancel cannot be lost to the
        # re-arm `clear()` (the cross-platform lost-wakeup the bare `_event.set()`
        # alone allowed -- it surfaced as a Linux-only hang in the EDGE cancel
        # tests where the worker thread reaches `_block` after the cancel fires).
        self._cancelled: bool = False
        # Readers handed out by `fetch_record_batch`. The reader wraps a SEPARATE
        # blocking gate (Pitfall 4: the reader has no `adbc_cancel` of its own --- a
        # cancelled pull fires THIS cursor's `adbc_cancel`), so a cancel/close/release
        # on the cursor must reach through to release any reader blocked in a pull.
        self._readers: list[BlockingStubReader] = []
        # Default batches handed to readers created via the ZERO-ARG
        # `fetch_record_batch()` path (the one the real `AsyncCursor.fetch_record_batch`
        # drives --- it calls the sync method with no args). A test that needs a
        # BLOCKED, cancellable pull through the real async path sets this to a
        # non-empty list BEFORE `await cur.fetch_record_batch()`, so the handed-out
        # reader blocks on its first pull; the default (empty) exhausts immediately.
        self.record_batch_batches: list[object] = []

    @property
    def closed(self) -> bool:
        """Whether `close` has run (terminal). Backed by `_closed`, lock-written."""
        with self._lock:
            return self._closed

    @property
    def in_execute(self) -> int:
        """
        Workers currently inside the blocked section of this cursor (lock-read).

        The instantaneous companion to `max_concurrent_in_execute`: it rises on each
        `_block` entry and falls on exit. Summing it across a flood's cursors yields
        the live cross-cursor concurrency, which a saturation test asserts never
        exceeds the shared limiter's bound (TEST-04 over-admission proof).
        """
        with self._lock:
            return self._in_execute

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

        Clears the internal event at the START so a prior `release` cannot
        pre-satisfy this call -- this is what makes the gate re-armable per
        blocking call (one cursor can block on `execute`, be released, then block
        again on `fetch_arrow_table`). A closed OR cancelled cursor short-circuits
        BEFORE the clear: both `_closed` and `_cancelled` latch sticky under the
        lock, so a `close`/`adbc_cancel` that arrives before the worker reaches
        `_block` is honoured (the worker returns at once) instead of being lost to
        the re-arm clear -- the dispatch-window cancel the EDGE suite exercises.

        Lock-guards the `max_concurrent_in_execute` high-water mark on entry and
        the decrement on exit. The `entered` sync signal and the optional
        `on_enter` loop bridge fire from INSIDE the blocked section (after
        concurrency is recorded, before the wait), so a consumer that awaits the
        bridged event observes a worker that is genuinely inside the block
        (D-CF-01) -- never a worker that merely started.
        """
        with self._lock:
            if self._closed or self._cancelled:
                # Terminal: a closed OR already-cancelled cursor never blocks. The
                # `_cancelled` check (symmetric with `_closed`) honours a cancel
                # that latched BEFORE the worker reached `_block` -- the dispatch
                # window the EDGE tests exercise -- instead of clearing it on
                # re-arm and stranding the non-cancellable worker (the Linux-only
                # lost-wakeup). A cancel that arrives while the worker is already
                # waiting is still handled by `adbc_cancel`'s `_event.set()` below.
                self.entered.set()
                return
            # Re-arm: clear before waiting so a prior release from a FIRST blocking
            # call cannot pre-satisfy this SECOND one. (Cancel/close latch via
            # their own sticky flags above, so they are never lost to this clear.)
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

    def fetch_df(self) -> object:
        """
        Record the call, block until released, then raise or return `None`.

        The `fetch_arrow_table` twin for the pandas materialization path (Phase 31):
        it records the call under the lock (bumping `df_call_count`), parks on the
        same sticky-release `_block` gate, then --- if `_fetch_df_raises` is set ---
        raises that exception. The raise happens AFTER `_block` releases so the error
        crosses the real `to_thread.run_sync` boundary, proving the `_offload.py`
        EDGE-17 re-raise contract (a synchronous raise would not exercise it). The
        error is NOT wrapped, so the DF-03 test observes the exact native
        `ModuleNotFoundError` (`.name == "pandas"`) it injected.

        No cancel wiring lives here: `adbc_cancel` / `close` / `release` already latch
        the sticky `_cancelled` / `_closed` flags that `_block` honours, so a cancel
        fired against this cursor unblocks the parked call through the existing
        machinery.

        Returns:
            `None` when no exception is injected. Later phases may inject a real
            `pandas.DataFrame` where a result is needed; the bare fake returns `None`.

        Raises:
            BaseException: The `_fetch_df_raises` exception, unwrapped, when set ---
                e.g. `ModuleNotFoundError("No module named 'pandas'")` for DF-03.
        """
        with self._lock:
            self.df_call_count += 1
        self._block()
        if self._fetch_df_raises is not None:
            raise self._fetch_df_raises
        return None

    def fetch_polars(self) -> object:
        """
        Record the call, block until released, then raise or return `None`.

        The `fetch_polars` twin of `fetch_df`: records the call under the lock
        (bumping `polars_call_count`), parks on the sticky-release `_block` gate,
        then --- if `_fetch_polars_raises` is set --- raises that exception AFTER
        `_block` releases, so the native error crosses the real `to_thread.run_sync`
        boundary (DF-03). The error is NOT wrapped.

        Returns:
            `None` when no exception is injected.

        Raises:
            BaseException: The `_fetch_polars_raises` exception, unwrapped, when set
                --- e.g. `ModuleNotFoundError("No module named 'polars'")` for DF-03.
        """
        with self._lock:
            self.polars_call_count += 1
        self._block()
        if self._fetch_polars_raises is not None:
            raise self._fetch_polars_raises
        return None

    def adbc_ingest(
        self,
        table_name: str,
        data: object,
        mode: str = "create",
        *,
        catalog_name: str | None = None,
        db_schema_name: str | None = None,
        temporary: bool = False,
    ) -> int:
        """
        Record the ingest call, block until released/cancelled, then return a row count.

        The blocking twin of `fetch_arrow_table` for the write path: it records the
        call under the lock (bumping `ingest_call_count`), then parks on the same
        sticky-release `_block` gate. That gives the Phase 30 INGEST-04 cancel test a
        DETERMINISTIC in-flight window --- the test gates on `ingest_call_count >= 1`
        (the worker is provably inside the blocked ingest) before cancelling, rather
        than racing a real DuckDB ingest that might finish first.

        No cancel wiring lives here: `adbc_cancel` / `close` / `release` already latch
        the sticky `_cancelled` / `_closed` flags that `_block` honours, so a cancel
        fired against this cursor unblocks the parked ingest through the existing
        machinery. `mode` stays positional-or-keyword to match the driver and the
        `_SyncCursor` Protocol; only the public `AsyncCursor.adbc_ingest` tightens it
        to keyword-only.

        Args:
            table_name: The target table (recorded only by the call count; never run).
            data: The Arrow payload to ingest (ignored by the fake).
            mode: The ingest mode (`create` / `append` / `replace` / `create_append`);
                ignored by the fake.
            catalog_name: Optional target catalog (ignored by the fake).
            db_schema_name: Optional target schema (ignored by the fake).
            temporary: Whether the target is a temporary table (ignored by the fake).

        Returns:
            A fixed row count of `3`. Later phases assert only that this reaches the
            caller unchanged; the fake does no real ingest.
        """
        del table_name, data, mode, catalog_name, db_schema_name, temporary
        with self._lock:
            self.ingest_call_count += 1
        self._block()
        return 3

    def adbc_prepare(self, operation: object = None) -> object:
        """
        Record the prepare call, block until released/cancelled, then return the injected result.

        The blocking twin of `adbc_ingest` for the prepared-statement read path
        (Phase 35, PREP-01): it records the call under the lock (bumping
        `prepare_call_count`), parks on the same sticky-release `_block` gate, then
        returns the injectable `_prepare_result`. That gives the Phase 35 cancel test
        a DETERMINISTIC in-flight window --- the test gates on `prepare_call_count >= 1`
        (the worker is provably inside the blocked prepare) before cancelling.

        No cancel wiring lives here: `adbc_cancel` / `close` / `release` already latch
        the sticky `_cancelled` / `_closed` flags that `_block` honours, so a cancel
        fired against this cursor unblocks the parked prepare through the existing
        machinery. This method NEVER touches `execute_call_count` --- the PREP-02
        no-execute proof depends on that counter staying `0`.

        Args:
            operation: The SQL text (recorded only by the call count; never run).

        Returns:
            The injectable `_prepare_result` (a sentinel `pyarrow.Schema` OR `None`,
            mirroring the sync `adbc_prepare` return of `Optional[pyarrow.Schema]`,
            D-35-02). Defaults to `None`.
        """
        del operation
        with self._lock:
            self.prepare_call_count += 1
        self._block()
        return self._prepare_result

    def adbc_execute_schema(self, operation: object = None, parameters: object = None) -> object:
        """
        Record the execute-schema call, block until released, then return the injected result.

        The blocking twin of `adbc_prepare` for the result-schema read path (Phase 35,
        PREP-02): it records the call under the lock (bumping `execute_schema_call_count`),
        parks on the same sticky-release `_block` gate, then returns the injectable
        `_execute_schema_result`. The no-execute proof injects a sentinel
        `pyarrow.Schema` and asserts the awaited value IS that object WHILE
        `execute_call_count == 0` --- proving the schema was resolved without executing
        the query (D-35-06).

        No cancel wiring lives here: `adbc_cancel` / `close` / `release` already latch
        the sticky `_cancelled` / `_closed` flags that `_block` honours. This method
        NEVER touches `execute_call_count`.

        Args:
            operation: The SQL text (recorded only by the call count; never run).
            parameters: Optional bound parameters (ignored by the fake).

        Returns:
            The injectable `_execute_schema_result` (a sentinel `pyarrow.Schema`,
            D-35-03). Defaults to `None`.
        """
        del operation, parameters
        with self._lock:
            self.execute_schema_call_count += 1
        self._block()
        return self._execute_schema_result

    def adbc_execute_partitions(
        self, operation: object = None, parameters: object = None
    ) -> object:
        """
        Record the execute-partitions call, block, then return the injected result.

        The blocking twin of `adbc_ingest` for the partitioned-execution read path
        (v1.5.1): it records the call under the lock (bumping
        `execute_partitions_call_count`), parks on the same sticky-release `_block`
        gate, then returns the injectable `_execute_partitions_result`. That gives the
        partition cancel test a DETERMINISTIC in-flight window --- the test gates on
        `execute_partitions_call_count >= 1` (the worker is provably inside the blocked
        call) before cancelling, rather than racing a real driver.

        No cancel wiring lives here: `adbc_cancel` / `close` / `release` already latch
        the sticky `_cancelled` / `_closed` flags that `_block` honours. Unlike a real
        driver this does NOT touch `execute_call_count`; the round-trip test asserts on
        the returned tuple, not the execute counter.

        Args:
            operation: The SQL text (recorded only by the call count; never run).
            parameters: Optional bound parameters (ignored by the fake).

        Returns:
            The injectable `_execute_partitions_result` (a `(partitions, schema)`
            tuple). Defaults to `None`.
        """
        del operation, parameters
        with self._lock:
            self.execute_partitions_call_count += 1
        self._block()
        return self._execute_partitions_result

    def adbc_read_partition(self, partition: object = None) -> None:
        """
        Record the read-partition call, then block until released/cancelled.

        The blocking twin of `execute` for the partition-read path (v1.5.1): it
        records the call under the lock (bumping `read_partition_call_count`), then
        parks on the sticky-release `_block` gate. Like the real dbapi
        `adbc_read_partition`, it sets up the cursor's result set as a side effect and
        returns `None`; a test drains via the existing `fetch_*` fakes afterwards.

        No cancel wiring lives here: `adbc_cancel` / `close` / `release` already latch
        the sticky `_cancelled` / `_closed` flags that `_block` honours.

        Args:
            partition: The opaque partition descriptor (recorded only by the call
                count; never read).
        """
        del partition
        with self._lock:
            self.read_partition_call_count += 1
        self._block()

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
            # Latch cancellation (sticky, under the lock) so a worker that reaches
            # `_block` AFTER this cancel still aborts instead of re-arming and
            # hanging. The `_event.set()` below covers the worker already waiting.
            self._cancelled = True
            readers = list(self._readers)
        self._event.set()
        # Pitfall 4: a cancelled reader pull fires THIS cursor's `adbc_cancel`, but the
        # worker is blocked on the READER's own gate --- release it here (terminally,
        # via `close`) so the blocked pull returns and the offload can join. Mirrors a
        # real driver where cancelling the cursor unblocks its in-flight reader read.
        for reader in readers:
            reader.close()

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
            readers = list(self._readers)
        self._event.set()
        # Terminal: closing the cursor closes its readers' streams too (a real driver
        # closes the reader when its cursor closes), releasing any blocked pull.
        for reader in readers:
            reader.close()

    def release(self) -> None:
        """
        Test-only: unblock a waiting worker WITHOUT cancelling (happy path).

        Leaves `observed_cancel` `False` -- use this to model a query that
        completes normally, as opposed to `adbc_cancel`. Also releases any reader
        blocked in a pull (the reader's gate is separate from the cursor's), so a
        test that releases the cursor unblocks a gated `read_next_batch` too.
        """
        with self._lock:
            readers = list(self._readers)
        self._event.set()
        for reader in readers:
            reader.release()

    def fetch_record_batch(
        self,
        *,
        batches: list[object] | None = None,
        schema: object = None,
    ) -> BlockingStubReader:
        """
        Return a fresh `BlockingStubReader` (the Phase 29 streaming stub).

        Sync accessor mirroring the real ADBC cursor's `fetch_record_batch`, which
        hands back a `pyarrow.RecordBatchReader`. This fake returns a
        [`BlockingStubReader`][tests._async_harness.stubs.BlockingStubReader]
        structurally satisfying the forthcoming `_SyncReader` surface (a `schema`
        property, a blocking `read_next_batch`, a terminal `close`) so the async
        `AsyncRecordBatchReader` can offload onto it without a live driver. Each call
        makes a new reader with no configured batches (exhausts on the first pull);
        tests that need drainable rows pass a batch sequence + schema directly to
        `BlockingStubReader`.

        The reader has NO `adbc_cancel` of its own (Pitfall 4): a cancelled pull
        fires the OWNING cursor's `adbc_cancel`, so a test drives cancellation
        through this cursor and reads `self.adbc_cancel_call_count`, not the
        reader's. The reader is RETAINED (`self._readers`) so this cursor's
        `adbc_cancel` / `close` / `release` reach through and unblock a reader blocked
        in a pull --- the reader's blocking gate is separate from the cursor's.

        A default (no-batch) reader exhausts on the first pull WITHOUT blocking, so a
        happy-path `async for batch in reader:` drains in one pull with no external
        release. A test that wants a BLOCKED, cancellable pull passes `batches=[...]`
        (or a `schema`): a reader with a pending batch blocks per-pull on its gate,
        so the cancel/timeout tests can gate on `entered` and then cancel.

        Args:
            batches: Optional pending batches for the reader to deliver; passing at
                least one makes the first pull BLOCK (the gated-cancel path). Defaults
                to `None` (an empty reader that exhausts on the first pull).
            schema: Optional schema stand-in for the reader's `schema` property.

        Returns:
            A fresh `BlockingStubReader`, retained in `self._readers` so the cursor's
            release/cancel/close reach it.
        """
        effective_batches = batches if batches is not None else list(self.record_batch_batches)
        reader = BlockingStubReader(batches=effective_batches, schema=schema)
        with self._lock:
            self.fetch_call_count += 1
            self._readers.append(reader)
        return reader


class BlockingStubReader:
    """
    Sync `RecordBatchReader`-shaped fake whose `read_next_batch` blocks until released.

    The streaming sibling of
    [`BlockingStubCursor`][tests._async_harness.stubs.BlockingStubCursor], added in
    Phase 29 (D-29-17) to satisfy the forthcoming `_SyncReader` structural Protocol
    (`schema` property, `read_next_batch`, `close`) WITHOUT importing a concrete
    `pyarrow` class. Kept pure-`threading` (no anyio, D-03) for the same
    framework-neutrality reason as the cursor stub, so it drives both the asyncio
    and trio legs of every Phase-29 reader test.

    It reuses the cursor's **sticky-release** design verbatim (see the module
    docstring): `close` latches `_closed` UNDER THE LOCK and is checked at `_block`
    entry BEFORE the re-arm `clear()`, so a `close` racing ahead of the worker is
    never lost to a Linux-only lost-wakeup. The happy-path `release` stays transient
    (the worker is provably inside `_block` via `entered`, so it cannot race the
    clear). Cancellation is fired via the OWNING cursor's `adbc_cancel` (Pitfall 4),
    so this reader deliberately exposes NO `adbc_cancel` of its own; `_cancelled`
    exists only so `close` (the terminal release) has a single short-circuit path,
    mirroring the cursor's `_closed` check.

    `read_next_batch` pops the next configured batch after unblocking and raises a
    bare `StopIteration` (`args == ()`) once the configured sequence is drained ---
    exactly the end-of-stream signal the real driver raises, so the async layer's
    worker-side `StopIteration`→`_EXHAUSTED` catch (D-29-05) is exercised.

    Attributes:
        entered: A `threading.Event` set the instant a worker is inside the blocked
            `read_next_batch` section --- the SYNC signal for pure-threading
            self-tests (poll or `wait()` it from a thread, NEVER from the event
            loop). Identical dual-`entered` discipline to the cursor stub: the
            loop-facing gate is a DISTINCT `anyio.Event` bridged via `on_enter` in
            `gating.py`. Re-armable: cleared at each `_block` entry so a second pull
            re-fires it.
        on_enter: An optional zero-argument callback invoked INSIDE `_block`, after
            concurrency is recorded and immediately before the worker waits --- the
            worker-entry hook `run_blocking` uses to bridge the loop-facing
            `anyio.Event` (D-CF-01). Stays a plain `Callable` so this module remains
            anyio-free (D-03). Defaults to `None`. The single-worker fallback; a
            per-thread hook registered via `register_on_enter` takes precedence.
        closed: `True` once `close` has run; `False` otherwise. Public terminal
            close-state flag (read it to assert a reader was closed). Written under
            the lock so a loop-thread reader never sees a torn state.
        read_call_count: Number of `read_next_batch` calls (including the one that
            raises `StopIteration` at exhaustion).
        close_call_count: Number of `close` calls.
        read_thread_ids: The `threading.get_ident()` of each `read_next_batch`
            caller, in call order --- lets a test assert pulls ran off the loop
            thread (STREAM-02).

    Example:
        ```python
        import threading

        from tests._async_harness.stubs import BlockingStubReader

        reader = BlockingStubReader(batches=["batch-0"], schema="the-schema")
        worker = threading.Thread(target=reader.read_next_batch)
        worker.start()

        reader.entered.wait()  # block until the worker is inside read_next_batch
        reader.release()  # let the blocked pull return "batch-0"
        worker.join()
        ```
    """

    def __init__(
        self,
        *,
        batches: list[object] | None = None,
        schema: object = None,
        entered: threading.Event | None = None,
        on_enter: Callable[[], None] | None = None,
    ) -> None:
        """
        Create a fresh reader over an optional batch sequence, with counters zeroed.

        Args:
            batches: The batches `read_next_batch` returns in order (one per pull);
                once drained, the next pull raises a bare `StopIteration`. Defaults
                to an empty list (the first pull exhausts). The list is copied so a
                caller's list is not mutated as batches are consumed.
            schema: The object returned by the `schema` property (a stand-in for a
                `pyarrow.Schema`; the fake does no I/O and never inspects it).
                Defaults to `None`.
            entered: Optional pre-existing `threading.Event` to use as the
                worker-entry signal. Defaults to a fresh, unset event.
            on_enter: Optional zero-argument callback invoked inside `_block` before
                the worker waits (see the `on_enter` attribute). Defaults to `None`.
        """
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._schema = schema
        self._batches: list[object] = list(batches) if batches is not None else []
        self.entered: threading.Event = entered or threading.Event()
        self.on_enter: Callable[[], None] | None = on_enter
        self._on_enter_by_thread: dict[int, Callable[[], None]] = {}
        self.read_call_count: int = 0
        self.close_call_count: int = 0
        self.read_thread_ids: list[int] = []
        self._in_read: int = 0
        self.max_concurrent_in_read: int = 0
        self._closed: bool = False
        # Sticky terminal state, symmetric with `BlockingStubCursor._closed`, so a
        # `close` that arrives BEFORE the worker reaches `_block` is honoured at
        # entry instead of being lost to the re-arm `clear()` (the Linux-only
        # lost-wakeup the module docstring warns about). The reader has no
        # `adbc_cancel` (Pitfall 4), so unlike the cursor it needs no `_cancelled`
        # sibling --- `close` is the sole terminal release path.
        self._closed_latched: bool = False

    @property
    def schema(self) -> object:
        """
        The reader's Arrow schema (synchronous passthrough; touches no I/O).

        Mirrors the real `pyarrow.RecordBatchReader.schema` property the async
        reader forwards without offloading. Returns the object handed in at
        construction (a stand-in for a `pyarrow.Schema`); the fake never inspects
        it.

        Returns:
            The caller-supplied schema stand-in (`None` by default).
        """
        return self._schema

    @property
    def closed(self) -> bool:
        """Whether `close` has run (terminal). Backed by `_closed`, lock-written."""
        with self._lock:
            return self._closed

    def register_on_enter(self, callback: Callable[[], None]) -> Callable[[], None]:
        """
        Register a worker-entry hook keyed by the CALLING thread's id.

        Concurrency-safe alternative to the single `on_enter` attribute, identical
        in contract to
        [`BlockingStubCursor.register_on_enter`][tests._async_harness.stubs.BlockingStubCursor.register_on_enter]:
        each worker thread bridges its OWN loop-facing event, so `_block` dispatches
        the hook for the current thread (falling back to `on_enter`). The hook is
        removed by the returned cleanup callable.

        Args:
            callback: Zero-argument hook to invoke inside `_block` for the calling
                thread, before it waits.

        Returns:
            A zero-argument cleanup callable that unregisters this thread's hook;
            call it in a `finally` so a reused reader is never left with a dangling
            per-thread bridge.
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

        A verbatim mirror of
        [`BlockingStubCursor._block`][tests._async_harness.stubs.BlockingStubCursor]
        minus the `_cancelled` tier (the reader has no `adbc_cancel`, Pitfall 4):
        clears the internal event at the START so a prior `release` cannot
        pre-satisfy this pull, but short-circuits BEFORE that clear when `_closed`
        has latched sticky under the lock --- so a `close` racing ahead of the
        worker is honoured (the pull returns at once) instead of being lost to the
        re-arm clear. Lock-guards the concurrency high-water mark on entry and the
        decrement on exit; `entered` and the optional `on_enter` bridge fire from
        INSIDE the blocked section (after concurrency is recorded, before the wait).
        """
        with self._lock:
            if self._closed_latched:
                # Terminal: a closed reader never blocks. The sticky `_closed_latched`
                # check honours a `close` that landed BEFORE the worker reached
                # `_block` instead of clearing it on re-arm and stranding the worker
                # (the Linux-only lost-wakeup). A `close` arriving while the worker
                # already waits is handled by `close`'s `_event.set()` below.
                self.entered.set()
                return
            self._event.clear()
            self.entered.clear()
            self._in_read += 1
            self.max_concurrent_in_read = max(self.max_concurrent_in_read, self._in_read)
            hook = self._on_enter_by_thread.get(threading.get_ident(), self.on_enter)
        try:
            self.entered.set()  # signal "worker is inside the block" (see gating.py)
            if hook is not None:
                hook()  # bridge the loop-facing anyio.Event from inside
            self._event.wait()  # blocks until released / closed
        finally:
            with self._lock:
                self._in_read -= 1

    def read_next_batch(self) -> object:
        """
        Record the call, block until released (only while batches remain), then return one.

        A pull that has a configured batch to deliver blocks on the internal event
        (via `_block`) --- exactly like the cursor stub's `execute`/`fetch_arrow_table`
        --- so a test can gate on `entered` and drive a cancel/close/release before the
        batch is handed back. A pull on an ALREADY-DRAINED reader (no batches left)
        does NOT block: it raises a BARE `StopIteration` (`args == ()`) immediately ---
        the end-of-stream signal the real
        `pyarrow.RecordBatchReader.read_next_batch()` raises, which the async layer's
        worker-side catch converts to its `_EXHAUSTED` sentinel (D-29-05).

        Exhausting without blocking is what lets the default empty reader (handed out
        by `BlockingStubCursor.fetch_record_batch`) drain in one pull, so a
        happy-path `async for batch in reader:` completes with no external release ---
        while a reader configured WITH pending batches still blocks per-pull for the
        gated cancel/close tests.

        Returns:
            The next configured batch object.

        Raises:
            StopIteration: Bare (`args == ()`) once the configured batch sequence is
                exhausted --- the driver's end-of-stream contract. Raised without
                blocking on the drained reader.
        """
        with self._lock:
            self.read_call_count += 1
            self.read_thread_ids.append(threading.get_ident())
            has_batch = bool(self._batches)
        if not has_batch:
            # Drained: exhaust immediately, no block. The default (empty) reader
            # therefore drains in one pull with no external release.
            raise StopIteration  # bare (args == ()): end-of-stream, per the real driver
        self._block()
        with self._lock:
            if self._batches:
                return self._batches.pop(0)
        raise StopIteration  # bare (args == ()): drained while blocked (close/cancel)

    def close(self) -> None:
        """
        Mark the reader closed and release any blocked pull (terminal).

        Increments `close_call_count` and sets the terminal `closed` flag, both
        under the lock (WR-03) so a reader never sees a half-updated state, latches
        the sticky `_closed_latched` so a pull reaching `_block` AFTER this close
        still returns, then releases the internal event to free a worker already
        waiting. Mirrors
        [`BlockingStubCursor.close`][tests._async_harness.stubs.BlockingStubCursor]:
        a closed reader is terminal and never re-arms, guaranteeing no worker is ever
        stranded in the blocked section.
        """
        with self._lock:
            self.close_call_count += 1
            self._closed = True
            self._closed_latched = True
        self._event.set()

    def release(self) -> None:
        """
        Test-only: unblock a waiting pull WITHOUT closing (happy path).

        Lets a blocked `read_next_batch` return its next configured batch, modelling
        a pull that completes normally. Transient on purpose (see the module
        docstring's sticky-release discipline): the worker is provably inside
        `_block` (the test waits for `entered`), so it cannot race the re-arm clear,
        and keeping it non-sticky preserves per-pull re-arm.
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
        invalidate_call_count: Number of `invalidate` calls. The poison-recovery
            signal the cancel EDGE cases (EDGE-02/04/05/29) read by name: it is
            `1` after a cancelled scope drives `AsyncConnection.invalidate()` →
            `self._fairy.invalidate()`, and `0` on the no-cancel paths.
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
        self.invalidate_call_count: int = 0
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

    def invalidate(self) -> None:
        """Increment `invalidate_call_count` (mirrors the fairy's poison-recovery)."""
        with self._lock:
            self.invalidate_call_count += 1

    def adbc_cancel(self) -> None:
        """Increment `adbc_cancel_call_count` and set `observed_cancel` to `True`."""
        with self._lock:
            self.adbc_cancel_call_count += 1
        self.observed_cancel = True
