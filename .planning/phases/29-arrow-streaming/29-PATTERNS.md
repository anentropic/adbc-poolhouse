# Phase 29: Arrow Streaming - Pattern Map

**Mapped:** 2026-07-01
**Files analyzed:** 4 (1 new prod, 2 modified prod, 1+ new/extended test)
**Analogs found:** 4 / 4 (all exact or role-match; no gaps)

The design goal (CONTEXT.md `<specifics>`, D-29-01) is explicit: `_reader.py` must
read like a **sibling of `_cursor.py`**. Almost nothing in this phase is novel —
every method maps onto a line-referenced idiom that already exists in the async
layer. The single new bit of machinery is the two-tier connection guard
(`_reader_open` + `from_reader`) in `_connection.py`. Mirror the analogs verbatim;
do not invent new structure, new error types, or new offload paths.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| **NEW** `src/adbc_poolhouse/_async/_reader.py` | async wrapper (component) | streaming (per-batch pull) | `src/adbc_poolhouse/_async/_cursor.py` (`AsyncCursor` + `_SyncCursor`) | **exact** — deliberate sibling |
| **MODIFY** `src/adbc_poolhouse/_async/_cursor.py` | async wrapper (component) | request-response (offloaded creation) | `AsyncCursor.fetch_arrow_table` + `_SyncCursor` Protocol (same file) | **exact** |
| **MODIFY** `src/adbc_poolhouse/_async/_connection.py` | wrapper / lifetime-guard (provider) | request-response guard | `AsyncConnection._enter_offload` / `_offloading` (same file) | **exact** (in-place extension) |
| **NEW/EXTEND** `tests/_async_harness/stubs.py` (stub reader) | test harness (stub) | streaming | `BlockingStubCursor` (same file) | **role-match** (new class, same sticky-release idiom) |
| **NEW** `tests/async/test_reader_*.py` | test | streaming lifetime | `tests/async/test_edge_resource.py` + `make_stub_async_connection` | **role-match** |

---

## Pattern Assignments

### `src/adbc_poolhouse/_async/_reader.py` (NEW — the sibling of `_cursor.py`)

**Analog:** `src/adbc_poolhouse/_async/_cursor.py` (whole file is the template).

This file is a structural copy of `_cursor.py`: same module docstring density,
same `from __future__ import annotations`, same `TYPE_CHECKING` import block, same
`_Sync*` Protocol, same constructor shape, same `_adbc_cancel` helper, same
sync-property passthrough, same shielded-close idiom.

**Imports + `TYPE_CHECKING` block** — copy `_cursor.py:31-47` shape verbatim:
```python
from __future__ import annotations

import warnings                    # NEW vs _cursor.py — needed for __del__ ResourceWarning
from typing import TYPE_CHECKING, Protocol

import anyio

from adbc_poolhouse._async._cancel import cancellable_offload
from adbc_poolhouse._async._offload import offload

if TYPE_CHECKING:
    import pyarrow
    from anyio import CapacityLimiter

    from adbc_poolhouse._async._connection import AsyncConnection
```

**`_SyncReader` Protocol** — mirror `_SyncCursor` (`_cursor.py:50-74`). Structural,
never imports a concrete pyarrow class (D-29-17). Exactly three members:
```python
class _SyncReader(Protocol):
    """Structural surface of the sync pyarrow.RecordBatchReader the async reader wraps."""

    @property
    def schema(self) -> pyarrow.Schema: ...
    def read_next_batch(self) -> pyarrow.RecordBatch: ...
    def close(self) -> None: ...
```

**Constructor** — identical shape to `AsyncCursor.__init__` (`_cursor.py:107-128`),
plus the reader's own `_detached` flag AND a reference to the owning cursor's
`adbc_cancel` (LANDMINE, Pitfall 4: the reader has no `adbc_cancel` of its own;
the abort must target the **cursor**'s). D-29-02 signature is `(sync_reader,
limiter, owner)` — thread the cursor's cancel hook in as part of construction
(Claude's discretion on exact shape; simplest is to also pass the owning
`AsyncCursor` or its `_adbc_cancel` bound method):
```python
def __init__(
    self,
    sync_reader: _SyncReader,
    limiter: CapacityLimiter,
    owner: AsyncConnection,
    adbc_cancel: Callable[[], None],   # the CURSOR's cancel — see Pitfall 4 below
) -> None:
    self._reader = sync_reader
    self._limiter = limiter
    self._owner = owner
    self._adbc_cancel = adbc_cancel    # NOT self._reader.adbc_cancel (does not exist)
    self._detached = False
```
> **Pitfall 4 (RESEARCH §Common Pitfalls / Landmine 6):** copying
> `AsyncCursor._adbc_cancel` (`_cursor.py:130-143`) verbatim would point at
> `self._cursor` — but the reader wraps a *reader*, which has no `adbc_cancel`.
> The abort hook MUST fire the owning **cursor's** `adbc_cancel`. Pass it in at
> construction (from `AsyncCursor.fetch_record_batch`, where `self._adbc_cancel`
> is in scope).

**`schema` sync-property passthrough** — mirror `AsyncCursor.description`
(`_cursor.py:145-155`). No `await`, no offload, no `async` (a coroutine property
is the "coroutine was never awaited" footgun):
```python
@property
def schema(self) -> pyarrow.Schema:
    """The reader's Arrow schema (synchronous; no offload — touches no I/O)."""
    return self._reader.schema
```

**`__anext__` per-pull offload** — the streaming analog of `fetch_arrow_table`
(`_cursor.py:325-353`), but with `from_reader=True` on the guard and a worker-side
`StopIteration`→sentinel catch (D-29-05, RESEARCH Pattern 2). The `_pull` helper
is a **module-level function**, not a lambda/bound method, to preserve the
`cancellable_offload` `TypeVarTuple` arity and keep the source guard's matcher
clean:
```python
# module level
class _Exhausted:
    """Private end-of-stream marker returned by the worker (D-29-05, Q1)."""


_EXHAUSTED = _Exhausted()


def _pull(sync_reader: _SyncReader) -> "pyarrow.RecordBatch | _Exhausted":
    # Runs on the WORKER thread. read_next_batch() raises a bare StopIteration at
    # end-of-stream (probed: args=()). StopIteration MUST NOT cross to_thread.run_sync
    # — it becomes RuntimeError("coroutine raised StopIteration") under asyncio AND
    # trio (probed). Signal exhaustion by value instead.
    try:
        return sync_reader.read_next_batch()
    except StopIteration:
        return _EXHAUSTED


# in class
async def __anext__(self) -> pyarrow.RecordBatch:
    with self._owner._offloading(from_reader=True):  # noqa: SLF001  reader tier: _in_use only
        batch = await cancellable_offload(
            self._adbc_cancel,               # the CURSOR's cancel (see __init__)
            _pull,
            self._reader,
            limiter=self._limiter,
            on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
        )
    if batch is _EXHAUSTED:
        raise StopAsyncIteration  # does NOT close / clear _reader_open (D-29-11)
    return batch

def __aiter__(self) -> AsyncRecordBatchReader:
    return self
```
> The `with self._owner._offloading(from_reader=True):` line is the ONLY caller
> in the codebase that passes `from_reader=True` (the reentrancy exemption,
> D-29-10). Every other `_offloading()` call site keeps the default `False`.

**`close()` shielded** — copy `AsyncCursor.close` (`_cursor.py:355-372`) exactly,
but use the NON-cancellable `offload` (not `cancellable_offload`), make it
idempotent via `_detached`, and clear `_reader_open` in a `finally` so an
exception during shielded cleanup still releases the lock and chains the body
error via `__context__` (D-29-16 / EDGE-20):
```python
async def close(self) -> None:
    if self._detached:
        return                      # idempotent: close-after-close / close-after-checkin no-op
    self._detached = True
    with anyio.CancelScope(shield=True):
        try:
            await offload(self._reader.close, limiter=self._limiter)
        finally:
            self._owner._reader_open = False  # noqa: SLF001 — clear even if close raised (EDGE-20)
```

**`__aenter__` / `__aexit__`** — copy `AsyncCursor.__aenter__/__aexit__`
(`_cursor.py:374-397`) verbatim; `__aexit__` just calls `await self.close()`.

**`__del__` warn-only** — NEW discipline (no analog; the only genuinely new
reader-local machinery besides the guard). NEVER call `self.close()` (creates an
un-awaited coroutine → the `RuntimeWarning` EDGE-22 forbids). Warn only when
`_detached is False` (RESEARCH Pattern 4):
```python
def __del__(self) -> None:
    if not self._detached:
        warnings.warn(
            f"{type(self).__name__} was not closed; use "
            "'async with await cursor.fetch_record_batch() as reader:'",
            ResourceWarning,
            stacklevel=2,
        )
```

**Docstrings:** match `_cursor.py`'s Google-style density (Args/Returns/Raises),
Markdown (never RST `:role:`), `Example:` singular with a fenced ```python block
for the class-level canonical-usage example (D-29-18). Phase ≥ 7 → docs gate
applies (see Shared Patterns → Docs).

**Do NOT export in `__all__`.** `AsyncCursor` is intentionally absent from
`_async/__init__.py:21-25` (`__all__` lists only the three factory functions).
`AsyncRecordBatchReader` is reached via `await cursor.fetch_record_batch()`, never
constructed by users, so it follows `AsyncCursor` and stays out of `__all__`.

---

### `src/adbc_poolhouse/_async/_cursor.py` (MODIFY — add `fetch_record_batch` + extend Protocol)

**Analog:** `AsyncCursor.fetch_arrow_table` (`_cursor.py:325-353`) — the closest
existing offload shape; `fetch_record_batch` differs only in wrapping the result
and setting `_reader_open` AFTER the `_offloading()` span exits.

**Extend `_SyncCursor` Protocol** (`_cursor.py:50-74`) — add one line (PKG-01),
adjacent to the existing `fetch_arrow_table` declaration at `_cursor.py:72`:
```python
    def fetch_record_batch(self) -> pyarrow.RecordBatch: ...  # actually returns RecordBatchReader; see note
```
(RESEARCH §Code Examples types it as `pyarrow.RecordBatchReader`; use that
concrete return in the Protocol line.)

**New `fetch_record_batch` method** — mirror `fetch_arrow_table` (`_cursor.py:347-353`)
for the offloaded creation, then set the lifetime lock OUTSIDE the span and wrap
(RESEARCH Pattern 1, D-29-03):
```python
async def fetch_record_batch(self) -> AsyncRecordBatchReader:
    with self._owner._offloading():  # noqa: SLF001  foreign-tier guard: _in_use OR _reader_open
        sync_reader = await cancellable_offload(
            self._adbc_cancel,
            self._cursor.fetch_record_batch,
            limiter=self._limiter,
            on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
        )
    # Lock the connection for the reader's WHOLE lifetime (D-29-08/09). Set AFTER
    # the _offloading() span exits (it already cleared _in_use) and ONLY on success,
    # so a cancelled/failed creation leaves _reader_open False (Pitfall 5).
    self._owner._reader_open = True  # noqa: SLF001
    return AsyncRecordBatchReader(
        sync_reader, self._limiter, self._owner, self._adbc_cancel
    )
```
> **Pitfall 5 (RESEARCH):** do NOT set `_reader_open = True` inside the
> `with self._owner._offloading():` block — if creation is cancelled it strands
> `_reader_open` True and the connection is permanently `ConnectionBusyError`.
> Set it after the block, success-only.

Import `AsyncRecordBatchReader` under `TYPE_CHECKING` (for the annotation) and at
runtime where the constructor is called — mirror how `_connection.py:42` imports
`AsyncCursor` at module top for its `cursor()` factory. Watch for a circular
import (`_reader.py` imports `AsyncConnection` only under `TYPE_CHECKING`;
`_cursor.py` importing `_reader.py` at runtime is fine since `_reader.py` does not
import `_cursor.py` at runtime).

---

### `src/adbc_poolhouse/_async/_connection.py` (MODIFY — two-tier guard, the one new bit)

**Analog:** `AsyncConnection._enter_offload` / `_offloading` (`_connection.py:124-170`)
— extended in place, NOT replaced. This is the only genuinely novel production
code in the phase (~6 lines).

**`__init__`** — add `_reader_open` beside `_in_use` (`_connection.py:115`):
```python
self._in_use = False
self._reader_open = False  # D-29-09: a live reader locks the connection for its lifetime
```
Document `_reader_open` in the class `Attributes:` block (`_connection.py:74-83`),
in the same style as the existing `_in_use` / `_teardown_limiter` entries.

**`_enter_offload`** — extend (`_connection.py:124-141`) with the `from_reader`
tier (RESEARCH Pattern 3, D-29-10). `_reader_open` reentrancy resolved as a
`from_reader: bool = False` keyword (RESEARCH §Claude's Discretion resolution):
```python
def _enter_offload(self, *, from_reader: bool = False) -> None:
    if self._in_use:
        raise ConnectionBusyError
    # Foreign callers (execute, commit, another cursor, a NEW fetch_record_batch)
    # are rejected while a reader is live. The reader's own pulls pass
    # from_reader=True to exempt ONLY this tier (D-29-10 reentrancy exemption).
    if self._reader_open and not from_reader:
        raise ConnectionBusyError
    self._in_use = True
```

**`_offloading`** — thread `from_reader` through (`_connection.py:147-170`);
`_exit_offload` (`_connection.py:143-145`) is UNCHANGED (clears `_in_use` only,
never `_reader_open`):
```python
@contextlib.contextmanager
def _offloading(self, *, from_reader: bool = False) -> Generator[None]:
    self._enter_offload(from_reader=from_reader)
    try:
        yield
    finally:
        self._exit_offload()
```
> Every existing `_offloading()` call site (`execute`, `fetch*`, `commit`,
> `rollback`, `close` in `_cursor.py`/`_connection.py`) is UNAFFECTED —
> `from_reader` defaults False, preserving current foreign-tier semantics with no
> edit. `_reader_open` is cleared ONLY by `reader.close()`; checkin is the
> backstop (a fresh `AsyncConnection` per `connect()`, `_pool.py:101-102`, so a
> stale `_reader_open=True` never survives to the next checkout — D-29-13).

**`invalidate` / `__aexit__`** (`_connection.py:249-311`) — UNCHANGED. They
already bypass `_in_use`; they need no `_reader_open` handling because checkin
throws away the whole `AsyncConnection`.

---

### `tests/_async_harness/stubs.py` (EXTEND — add a stub reader)

**Analog:** `BlockingStubCursor` (`stubs.py:61-337`) — reuse its **sticky-release**
design (`_closed` / `_cancelled` latch under the lock, checked at `_block` entry
BEFORE the re-arm `clear()`; happy-path `release()` stays transient). This is
load-bearing: the module docstring (`stubs.py:31-49`) and MEMORY
"platform-dependent lost-wakeup" both warn that a bare `Event.set()` paired with an
entry-time `clear()` is a Linux-only lost-wakeup. Keep the stub reader anyio-free
(D-03) — `threading` only.

Two additions (RESEARCH §Wave 0 Gaps):
1. A `fetch_record_batch()` on `BlockingStubCursor` returning a new stub reader.
2. A `BlockingStubReader` class satisfying `_SyncReader`:
   - a `schema` `@property` (no-I/O passthrough),
   - a `read_next_batch()` that **blocks-then-returns-a-batch** using the same
     `_block()` gate idiom (`stubs.py:219-267`), and **raises `StopIteration`** on
     exhaustion (so `_pull`'s worker-side catch is exercised),
   - a `close()` mirroring `BlockingStubCursor.close` (`stubs.py:315-328`,
     terminal `_closed` latch + `_event.set()`).
   - Public counter/flag attributes as a HARD CONTRACT (D-04, LOCKED names),
     e.g. `read_call_count`, `adbc_cancel_call_count` (fired via the owning
     cursor), `close_call_count`, `entered`, `on_enter` — mirror the
     `BlockingStubCursor` attribute table (`stubs.py:99-111`).
   - Reuse `entered` / `on_enter` / `register_on_enter` (`stubs.py:188-217`) so
     cancel/aliasing tests stay deterministic (the loop-facing `anyio.Event` is
     bridged in `gating.py`, never awaited on the stub's `threading.Event`).

Copy `BlockingStubCursor.__init__` (`stubs.py:130-167`), `_block` (`stubs.py:219-267`),
`adbc_cancel` (`stubs.py:296-313`), `close` (`stubs.py:315-328`), `release`
(`stubs.py:330-337`) as the template; swap `execute`/`fetch_arrow_table` for
`read_next_batch`.

---

### `tests/async/test_reader_*.py` (NEW — six files per RESEARCH test map)

**Analogs:**
- **Lifetime / read-after-checkin** → `tests/async/test_edge_resource.py` (whole
  file). Copy its `_LIFETIME_LOOPS` + `concurrency_marks` pattern
  (`test_edge_resource.py:24-28`) and the fetch-inside-scope / assert-outside-scope
  structure (`test_edge_resource.py:45-56`), asserting `checkedout() == 0` and a
  native `pyarrow.lib.ArrowInvalid` ("stream that has already been closed") on
  read-after-checkin — NOT a poolhouse error type.
- **Stub-backed busy / cancel / resource** → `make_stub_async_connection`
  (`conftest.py:156-194`) which wraps a `BlockingStubConnection` behind a real
  `AsyncConnection`. Assert `stub.adbc_cancel_call_count == 1`,
  `stub_conn.invalidate_call_count == 1` on cancel; `ConnectionBusyError` on a
  foreign op while `_reader_open`.
- **Fixtures:** `duckdb_async_pool` (`conftest.py:88`), `snowflake_async_pool`
  cassette (`conftest.py:110`, `importorskip`s cleanly — see Open Q / A1),
  `anyio_backend` dual-param `["asyncio","trio"]` (`conftest.py:59`).

Files to create (RESEARCH §Wave 0 Gaps): `test_reader_stream.py` (STREAM-01/02),
`test_reader_close.py` (STREAM-03 + EDGE-20), `test_reader_lifetime.py`
(STREAM-04/EDGE-33, DuckDB + Snowflake cassette), `test_reader_cancel.py`
(STREAM-05), `test_reader_busy.py` (STREAM-06), `test_reader_resource.py`
(EDGE-22/23).

---

## Shared Patterns

### Offload chokepoint (routes EVERYTHING off-loop)
**Source:** `src/adbc_poolhouse/_async/_offload.py:41-109` (`offload`) and
`src/adbc_poolhouse/_async/_cancel.py:41-247` (`cancellable_offload`).
**Apply to:** every blocking call in `_reader.py` (creation via the cursor,
each `__anext__` pull, `close`).
- Blocking + cancellable (creation, `__anext__`): `cancellable_offload(adbc_cancel,
  fn, *args, limiter=..., on_abort=owner.invalidate)`.
- Blocking + shielded, non-cancellable (`close`): `offload(fn, limiter=...)` inside
  `anyio.CancelScope(shield=True)`.
- NEVER call `anyio.to_thread.run_sync` directly (PKG-03 guard bans it); the single
  audited site is `_offload.py:105`. `_pull` stays a plain module function so the
  guard's arity/attribute matcher stays clean (RESEARCH Anti-Patterns).

### Single-task guard (`_offloading` bracketing)
**Source:** `src/adbc_poolhouse/_async/_connection.py:147-170`.
**Apply to:** every offloaded reader method. Foreign-tier for creation
(`_offloading()`); reader-tier for pulls (`_offloading(from_reader=True)`).

### Shielded teardown + `__context__` chaining (EDGE-20)
**Source:** `AsyncCursor.close` (`_cursor.py:355-372`) and
`AsyncConnection.close` (`_connection.py:232-247`).
**Apply to:** `reader.close()`. Wrap the offloaded `close` in
`anyio.CancelScope(shield=True)`; clear `_reader_open` in a `finally` so a body
error already on the stack chains via `__context__` automatically and the lock is
never left stuck.

### No bespoke async-only error types
**Source:** REQUIREMENTS non-goal; `_cursor.py` module docstring lines 26-28
(worker exceptions never re-wrapped, EDGE-17).
**Apply to:** all of `_reader.py`. Read-after-checkin surfaces the driver's native
`pyarrow.lib.ArrowInvalid`; do NOT introduce a `ReaderClosedError`. The single
offload chokepoint re-raises native errors with exact type/traceback; the reader
must not catch or wrap them (the sole exception is the worker-side `StopIteration`
catch, which is a control-flow sentinel, not error re-wrapping).

### Reader-lifetime backstop (free, no new machinery)
**Source:** `_release_arrow_allocators` (`src/adbc_poolhouse/_pool_factory.py:407-428`),
fired on the pool `reset` event on every checkin path.
**Apply to:** STREAM-04 / EDGE-33 reasoning. The reset handler closes the dbapi
cursor (`cur.close()`), which closes the reader's C-stream — a later read raises
the native `ArrowInvalid`. The async reader adds ONLY the thin `_detached` bool
for `__del__`/idempotency; NO weakref / `finalize` / registration (D-29-12).

### Docs gate (CLAUDE.md, phase ≥ 7)
**Source:** `CLAUDE.md` + MEMORY docstring-style notes.
**Apply to:** `_reader.py` public symbols (`AsyncRecordBatchReader`, `schema`,
`fetch_record_batch`) and any consumer-facing guide.
- Google-style docstrings (Args/Returns/Raises), **Markdown** not RST (`` `create_pool` ``
  not `:func:`), `Example:` singular for the admonition + fenced ```python.
- `.venv/bin/mkdocs build --strict` must pass (prefer `.venv/bin/mkdocs` over
  `uv run` under sandbox — MEMORY uv-sandbox note).
- Document canonical usage `async with await cursor.fetch_record_batch() as reader:`
  then `async for batch in reader:` (D-29-18).

---

## No Analog Found

None. Every file this phase touches maps to an existing analog. Two members have
**no direct method analog** but are small, well-specified additions rather than
gaps (both fully templated in RESEARCH):

| Member | Role | Why no direct analog | Template |
|--------|------|----------------------|----------|
| `AsyncRecordBatchReader.__del__` | warn-only finalizer | no `__del__` exists elsewhere in `_async/` | RESEARCH Pattern 4 (verbatim) |
| `_enter_offload(from_reader=...)` reentrancy tier | lifetime guard | genuinely new (~6 lines) | RESEARCH Pattern 3 (verbatim); extends `_connection.py:124-141` |

---

## Landmines Carried Forward (from RESEARCH — the planner MUST relay these)

1. **`StopIteration` must be caught worker-side** → becomes `RuntimeError` across
   `to_thread.run_sync` under both backends (probed). `_pull` catches it → `_EXHAUSTED`.
2. **`_reader_open` is cleared ONLY by `close()`/checkin, NEVER at drain**
   (D-29-11) — clearing it at `StopAsyncIteration` re-opens the STREAM-06 hazard.
3. **`__del__` never calls `self.close()`** — un-awaited coroutine → `RuntimeWarning`
   (EDGE-22 violation). Warn-only.
4. **The reader's abort fires the CURSOR's `adbc_cancel`**, not the reader's (the
   reader has none). Thread it in at construction.
5. **Set `_reader_open = True` OUTSIDE the creation `_offloading()` span,
   success-only** — else a cancelled creation strands the connection busy.
6. **`_pull` stays a module-level function** — preserves `cancellable_offload`
   `TypeVarTuple` arity and the source-guard matcher.

---

## Metadata

**Analog search scope:** `src/adbc_poolhouse/_async/` (all modules),
`src/adbc_poolhouse/_pool_factory.py`, `src/adbc_poolhouse/_exceptions.py`,
`tests/_async_harness/`, `tests/async/`.
**Files scanned (read in full or targeted):** `_cursor.py`, `_connection.py`,
`_cancel.py`, `_offload.py`, `_async/__init__.py`, `stubs.py`,
`conftest.py` (fixture section), `test_edge_resource.py` (head),
`_pool_factory.py:407-428`.
**Pattern extraction date:** 2026-07-01

## PATTERN MAPPING COMPLETE
