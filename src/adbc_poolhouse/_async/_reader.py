"""
The async record-batch reader: per-pull offloaded Arrow streaming, shielded close.

[`AsyncRecordBatchReader`][adbc_poolhouse._async._reader.AsyncRecordBatchReader]
is the streaming sibling of
[`AsyncCursor`][adbc_poolhouse._async._cursor.AsyncCursor]. It is reached only via
`await cursor.fetch_record_batch()` (never constructed by users, so it stays out of
`_async/__init__.py`'s `__all__`, exactly like `AsyncCursor`) and wraps a single
sync `pyarrow.RecordBatchReader` by **composition** --- it holds the sync reader
rather than subclassing it, so nothing about the concrete Arrow class leaks into
the async surface (D-29-01).

Every blocking call goes through the same offload chokepoint the cursor uses:

- **Per-batch iteration.** `async for batch in reader:` offloads each
  `read_next_batch` individually through
  [`cancellable_offload`][adbc_poolhouse._async._cancel.cancellable_offload], so a
  slow pull never blocks the event loop and a cancelled pull aborts the in-flight C
  call via the owning cursor's `adbc_cancel`. The worker catches the driver's
  end-of-stream `StopIteration` and returns the module-level `_EXHAUSTED` sentinel
  instead --- a bare `StopIteration` crossing `to_thread.run_sync` becomes a
  `RuntimeError` under both asyncio and trio, so it must never leak (D-29-05).
- **Synchronous `schema` (D-29-04).** `schema` is a plain `@property` passthrough of
  the sync reader's schema. It touches no I/O, so it is not offloaded and not
  `async` --- a coroutine property would surface as a "coroutine was never awaited"
  bug.
- **Shielded close (D-29-06).** `close` / `__aexit__` offload the sync reader's
  `close` inside `anyio.CancelScope(shield=True)`, so a cancellation arriving
  mid-close cannot abandon an open C stream. It is idempotent (a `_detached` latch)
  and clears the owning connection's `_reader_open` lock in a `finally`, so a
  failing close still releases the connection and chains the body error via
  `__context__` (EDGE-20).

Two lifetime disciplines make read-after-checkin safe without any bespoke error
type or finalizer machinery (D-29-12):

- **`_reader_open` lifetime lock.** The owning connection stays locked for the
  reader's WHOLE lifetime, not just during a pull, so no foreign op can touch the
  still-open C stream between pulls (STREAM-06). The lock is cleared ONLY by
  `close()` / checkin --- never at drain (D-29-11), so a drained-but-unclosed
  reader keeps the connection locked and `async with` is the canonical usage.
- **Warn-only `__del__` (D-29-15).** An unclosed reader's finalizer emits a single
  `ResourceWarning`; it NEVER calls `self.close()` (an un-awaited coroutine would
  emit the "coroutine was never awaited" `RuntimeWarning` EDGE-22 forbids). The
  real buffer release rides the pool's reset event on checkin.

Worker exceptions are never re-wrapped: a read after the stream is closed surfaces
the driver's native `pyarrow.lib.ArrowInvalid` unchanged (never a poolhouse error,
never a segfault). The single worker-side `StopIteration` catch is a control-flow
sentinel, not error re-wrapping.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Protocol

import anyio

from adbc_poolhouse._async._cancel import cancellable_offload
from adbc_poolhouse._async._offload import offload

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    import pyarrow
    from anyio import CapacityLimiter

    from adbc_poolhouse._async._connection import AsyncConnection


class _SyncReader(Protocol):
    """
    Structural type for the sync `pyarrow.RecordBatchReader` surface the async reader wraps.

    Declared structurally (a `Protocol`) rather than imported from `pyarrow` so the
    async layer stays driver-agnostic and never depends on a concrete Arrow class
    (D-29-17). Any object exposing this surface --- the real
    `pyarrow.RecordBatchReader`, or a test stub --- satisfies it.
    """

    @property
    def schema(self) -> pyarrow.Schema: ...
    def read_next_batch(self) -> pyarrow.RecordBatch: ...
    def close(self) -> None: ...


class _Exhausted:
    """Private end-of-stream marker returned by the worker instead of `StopIteration` (D-29-05)."""


_EXHAUSTED = _Exhausted()


def _pull(sync_reader: _SyncReader) -> pyarrow.RecordBatch | _Exhausted:
    """
    Pull the next batch on a worker thread, converting end-of-stream to a sentinel.

    Runs on the WORKER thread. `read_next_batch()` raises a bare `StopIteration` at
    end-of-stream, which MUST NOT cross `anyio.to_thread.run_sync`: under both
    asyncio and trio it is re-raised as `RuntimeError("coroutine raised
    StopIteration")`. Signal exhaustion by value instead, returning the module-level
    `_EXHAUSTED` singleton so `__anext__` can raise `StopAsyncIteration` on the loop
    thread (D-29-05).

    This is a MODULE-LEVEL function (not a lambda or bound method) so it preserves
    the `cancellable_offload` `TypeVarTuple` arity and keeps the `scan_async_package`
    source guard's matcher clean.

    Args:
        sync_reader: The wrapped sync reader to pull one batch from.

    Returns:
        The next `pyarrow.RecordBatch`, or the `_EXHAUSTED` sentinel once the stream
        is drained.
    """
    try:
        return sync_reader.read_next_batch()
    except StopIteration:
        return _EXHAUSTED


class AsyncRecordBatchReader:
    """
    Async wrapper over a sync `pyarrow.RecordBatchReader`.

    Created by
    [`AsyncCursor.fetch_record_batch`][adbc_poolhouse._async._cursor.AsyncCursor.fetch_record_batch]
    and reached only through `await cursor.fetch_record_batch()`. Holds the sync
    reader by composition (never subclasses it, D-29-01) and offloads each batch pull
    and the final close through the owning pool's limiter, so no blocking Arrow C
    call ever runs on the event loop.

    A live reader locks its owning connection for its WHOLE lifetime, so a foreign op
    on the same connection raises
    [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] while the reader is
    open (STREAM-06). The lock is cleared by `close()` --- NOT at drain (D-29-11) ---
    so the reader must be closed; `async with` is the canonical usage and its
    finalizer only warns.

    `schema` is a synchronous property read (no `await`, no offload). Reading after
    the reader is closed --- or after the connection is checked in, which closes the
    underlying cursor --- surfaces the driver's native `pyarrow.lib.ArrowInvalid`,
    never a poolhouse error and never a segfault (T-29-01).

    Example:
        ```python
        import adbc_poolhouse

        pool = await adbc_poolhouse.create_async_pool(config)
        async with await pool.connect() as conn:
            cursor = conn.cursor()
            await cursor.execute("SELECT * FROM events WHERE day = ?", ["2026-06-27"])
            async with await cursor.fetch_record_batch() as reader:
                async for batch in reader:  # each pull offloaded off-loop
                    process(batch)  # a pyarrow.RecordBatch
        await adbc_poolhouse.close_async_pool(pool)
        ```
    """

    def __init__(
        self,
        sync_reader: _SyncReader,
        limiter: CapacityLimiter,
        owner: AsyncConnection,
        adbc_cancel: Callable[[], None],
        *,
        poison_on_cancel: bool = True,
    ) -> None:
        """
        Bind a sync reader to its limiter, owning connection, and the cursor's cancel.

        Args:
            sync_reader: The underlying sync `pyarrow.RecordBatchReader` to wrap.
            limiter: The owning pool's `anyio.CapacityLimiter`, used to bound every
                offloaded pull and the close. Identical to `owner`'s limiter; held
                directly so the reader never reaches through the connection on the
                hot path.
            owner: The `AsyncConnection` this reader streams from. Each pull brackets
                itself with `owner._offloading(from_reader=True)` (the reentrancy
                exemption, so the reader does not deadlock on its own lifetime lock),
                and `close` clears `owner._reader_open`.
            adbc_cancel: The cancel callback fired to abort an in-flight pull. For a
                cursor-backed reader this is the owning CURSOR's `adbc_cancel` bound
                method (the reader has no `adbc_cancel` of its own, Pitfall 4). For a
                connection-level metadata reader there is no `adbc_cancel` to thread
                in, so a no-op is passed and `poison_on_cancel` is set `False` (see
                below) --- the two go together.
            poison_on_cancel: Whether a cancelled pull invalidates the owning
                connection. `True` (the default, the cursor path) is correct when
                `adbc_cancel` genuinely aborts the in-flight C call: the driver call
                returns poisoned, so poison-recovery must run. `False` (the
                connection-level metadata path) is REQUIRED when `adbc_cancel` is a
                no-op: the worker thread cannot be aborted and stays in the driver's
                `read_next_batch` until it returns on its own, so invalidating here
                would drive `fairy.invalidate()` on a SECOND thread concurrently with
                that still-running read --- the concurrent single-connection access
                ADBC forbids. With `False`, a cancelled pull instead re-raises the
                cancellation once the joined worker finishes, leaving the (never
                poisoned) connection to return to the pool through the normal checkin.
        """
        self._reader = sync_reader
        self._limiter = limiter
        self._owner = owner
        # The CURSOR's cancel, NOT `self._reader.adbc_cancel` (which does not exist
        # --- a pyarrow reader has no cancel hook). See Pitfall 4. May be a no-op for a
        # connection-level metadata reader, in which case `poison_on_cancel` is False.
        self._adbc_cancel = adbc_cancel
        # False for connection-level metadata readers whose `adbc_cancel` is a no-op:
        # the worker cannot be aborted, so invalidating on cancel would race a second
        # thread against the still-running read on the same connection (CR-34-01).
        self._poison_on_cancel = poison_on_cancel
        # Idempotency + finalizer latch: True once closed (or detached via close), so
        # `close` is a safe no-op on a second call and `__del__` warns only when the
        # reader was abandoned unclosed.
        self._detached = False

    @property
    def schema(self) -> pyarrow.Schema:
        """
        The reader's Arrow schema (synchronous; no offload --- touches no I/O).

        Returns:
            The wrapped sync reader's `pyarrow.Schema`. Read directly --- reading a
            schema touches no I/O, so it is not offloaded and not `async` (a
            coroutine property would be the "coroutine was never awaited" footgun).
        """
        return self._reader.schema

    def __aiter__(self) -> AsyncRecordBatchReader:
        """
        Return the async iterator (this reader).

        Returns:
            This `AsyncRecordBatchReader`, so `async for batch in reader:` drives
            `__anext__`.
        """
        return self

    async def __anext__(self) -> pyarrow.RecordBatch:
        """
        Pull the next batch on a worker thread, or stop at end-of-stream.

        Offloads a single `read_next_batch` through the pool limiter while holding
        the parent connection's per-call `_in_use` guard. The pull passes
        `from_reader=True` (the ONLY `from_reader=True` caller in the codebase), which
        exempts it from the connection's `_reader_open` lifetime tier so the reader
        does not deadlock on its own lock while still taking the C-access tier
        (D-29-10).

        The worker converts the driver's end-of-stream `StopIteration` to the
        `_EXHAUSTED` sentinel (`_pull`); on the sentinel this raises
        `StopAsyncIteration`. Exhaustion does NOT clear `_reader_open` --- the reader
        stays open until `close()` (D-29-11).

        If the surrounding scope is cancelled or times out while a pull is in flight,
        behavior depends on whether this reader can actually abort its worker
        (`poison_on_cancel`, set at construction):

        - **Cursor-backed reader (`poison_on_cancel=True`).** The in-flight C call is
          aborted with the owning CURSOR's `adbc_cancel`, the now-poisoned connection
          is invalidated (shielded), and the cancellation is re-raised --- the
          connection never returns to the pool busy (STREAM-05).
        - **Connection-level metadata reader (`poison_on_cancel=False`).** There is no
          `adbc_cancel`, so the worker cannot be aborted --- it finishes its
          `read_next_batch` on its own (the joined worker, `abandon_on_cancel=False`)
          and the cancellation is then re-raised. The connection is NOT invalidated:
          it was never poisoned, and invalidating would race a second thread against
          the still-running read on the same connection (CR-34-01). The dropped batch
          is discarded; the connection returns to the pool through the normal checkin.

        Returns:
            The next `pyarrow.RecordBatch` in the stream.

        Raises:
            StopAsyncIteration: When the stream is exhausted.
            ConnectionBusyError: If a foreign offloaded call on the owning connection
                is already in flight.
        """
        with self._owner._offloading(from_reader=True):  # noqa: SLF001  reader tier: _in_use only
            batch = await cancellable_offload(
                self._adbc_cancel,  # cursor's cancel, or a no-op for metadata readers
                _pull,
                self._reader,
                limiter=self._limiter,
                # Poison-recover only when a real `adbc_cancel` aborted the worker; a
                # no-op-cancel metadata reader must NOT invalidate (CR-34-01).
                on_abort=self._owner.invalidate if self._poison_on_cancel else None,
            )
        if batch is _EXHAUSTED:
            raise StopAsyncIteration  # does NOT clear _reader_open (D-29-11)
        return batch

    async def close(self) -> None:
        """
        Close the underlying sync reader on a worker thread (shielded, idempotent).

        Offloads the sync reader's `close` inside `anyio.CancelScope(shield=True)`, so
        a cancellation arriving mid-close cannot abandon an open C stream (which would
        pin the connection's Arrow allocators). Idempotent via `_detached`: a second
        `close` --- or a `close` after the connection was already checked in --- is a
        safe no-op.

        The owning connection's `_reader_open` lock is cleared in a `finally`, so even
        a `close` whose offloaded `sync_reader.close` raises still releases the
        connection (never stranding it busy) and chains the raised body error via
        `__context__` (EDGE-20 / D-29-16).

        Raises:
            Exception: Whatever the sync reader's `close` raises is propagated
                unchanged, after the lock is released.
        """
        if self._detached:
            return  # idempotent: close-after-close / close-after-checkin no-op
        self._detached = True
        with anyio.CancelScope(shield=True):
            try:
                await offload(self._reader.close, limiter=self._limiter)
            finally:
                # Clear the lifetime lock even if close raised (EDGE-20): a failed
                # cleanup must never leave the connection permanently busy.
                self._owner._reader_open = False  # noqa: SLF001

    async def __aenter__(self) -> AsyncRecordBatchReader:
        """
        Enter the async context.

        Returns:
            This `AsyncRecordBatchReader`.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Close the reader on context exit (shielded close).

        Args:
            exc_type: The exception type if the block raised, else `None`.
            exc: The exception instance if the block raised, else `None`.
            tb: The traceback if the block raised, else `None`.
        """
        await self.close()

    def __del__(self) -> None:
        """
        Warn (only) if the reader was dropped without being closed (D-29-15).

        Emits a single `ResourceWarning` nudging the user toward the canonical
        `async with await cursor.fetch_record_batch() as reader:` usage. It NEVER
        calls `self.close()`: an un-awaited coroutine would emit the "coroutine was
        never awaited" `RuntimeWarning` EDGE-22 forbids. The actual buffer release
        rides the pool's reset event on checkin (D-29-12), so warning is enough.
        """
        if not self._detached:
            warnings.warn(
                f"{type(self).__name__} was not closed; use "
                "'async with await cursor.fetch_record_batch() as reader:'",
                ResourceWarning,
                stacklevel=2,
            )
