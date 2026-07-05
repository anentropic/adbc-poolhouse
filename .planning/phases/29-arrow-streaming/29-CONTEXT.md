# Phase 29: Arrow Streaming - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver `await cursor.fetch_record_batch()` → `AsyncRecordBatchReader`, an async
iterator + async context manager that streams `pyarrow.RecordBatch` chunks with
each `read_next_batch()` pull offloaded individually through the pool limiter. The
reader's lifetime is bound to its checked-out connection so read-after-checkin (or
read-after-close) surfaces the driver's native closed-stream error — a clean
Python exception, never a use-after-free. Cancel/timeout on a pull fires
`adbc_cancel` once and invalidates the connection.

Every new method is a pure offload wrapper over a method that already exists on
the wrapped sync `dbapi.Cursor` / `pyarrow.RecordBatchReader`, routed through the
existing v1.4.0 `offload` / `cancellable_offload` chokepoint and per-pool
`CapacityLimiter`. No new runtime deps, no new extras, no sync-core change.

This is the milestone's headline design risk, front-loaded: the reader-lifetime
patterns established here (`__aexit__`, `__del__`, `_detached` guard, per-pull
`cancellable_offload`, two-tier connection guard) are copied by Phases 30–31.

**Requirements:** STREAM-01..06, EDGE-33, EDGE-20, EDGE-22, EDGE-23, PKG-01, PKG-03

</domain>

<decisions>
## Implementation Decisions

### Wrapper structure (STREAM-01, STREAM-02, STREAM-03)
- **D-29-01:** New class `AsyncRecordBatchReader` in a new file
  `src/adbc_poolhouse/_async/_reader.py`, mirroring `_cursor.py`. **Composition,
  not subclassing** — it holds a reference to the sync `pyarrow.RecordBatchReader`;
  it does NOT subclass it. Subclassing would leak pyarrow's synchronous
  `read_next_batch` / `__iter__` straight through, bypassing the limiter, the
  lifetime lock, and cancel-safety.
- **D-29-02:** Constructor signature `(sync_reader, limiter, owner)` — identical
  shape to `AsyncCursor.__init__(sync_cursor, limiter, owner)`. `owner` is the
  `AsyncConnection`, needed for the `_reader_open` guard and `invalidate`.
- **D-29-03:** `AsyncCursor.fetch_record_batch()` offloads reader *creation*
  through `cancellable_offload` (holding `self._owner._offloading()`, `on_abort=
  self._owner.invalidate`), exactly like `fetch_arrow_table`, then wraps the
  returned sync reader in `AsyncRecordBatchReader(...)`.

### Reader surface — additive, blocking members re-fronted (phase scope)
- **D-29-04:** The rule is "hide nothing safe to expose; replace every blocking
  member with its async twin, never leave it raw." Two treatments:
  - **No-I/O members pass through unchanged** — `schema` is exposed as a plain
    sync `@property` passthrough (no `await`), following the `description` /
    `rowcount` / `arraysize` precedent in `AsyncCursor`.
  - **Blocking I/O members are replaced by async twins** — `read_next_batch` →
    `__anext__`; sync `__iter__`/`__next__` → `__aiter__`/`__anext__`; sync
    `close`/`__enter__`/`__exit__` → async `close`/`__aenter__`/`__aexit__`.
    Leaving a raw sync blocking method reachable on the loop is a footgun (blocks
    the loop, bypasses limiter + `_reader_open` + cancel-safety).
- **D-29-05:** `__anext__` offloads one `read_next_batch()` pull via
  `cancellable_offload` (`on_abort=owner.invalidate`) and translates
  `StopIteration` → `StopAsyncIteration`. `StopIteration` must NOT cross the async
  boundary (it becomes a `RuntimeError`), so the worker catches it and signals
  exhaustion via a sentinel; `__anext__` raises `StopAsyncIteration` on the
  sentinel. (Confirm exact mechanism in RESEARCH.)
- **D-29-06:** `close()` offloads `sync_reader.close()` inside
  `anyio.CancelScope(shield=True)`, mirroring `AsyncCursor.close`.
- **D-29-07:** **Phase scope = iterate + close + schema only.** Do NOT add
  `await reader.read_all()` or `await reader.read_pandas()` async twins — out of
  scope (not in STREAM-01..06; `read_pandas` overlaps Phase 31 `fetch_df`).

### Connection lifetime lock — STREAM-06 = Model B (lifetime-held)
- **D-29-08:** A live reader locks the parent connection for its **whole
  lifetime**, not just during an in-flight pull ("Model B"). The per-call
  `_in_use` flag alone is insufficient: between pulls it reads False, so a
  concurrent op in that gap would interleave with a still-open Arrow stream on the
  same connection — the exact "concurrent C access" STREAM-06 forbids.
- **D-29-09:** Add a **persistent `_reader_open` guard on `AsyncConnection`**,
  distinct from the per-call `_in_use`. Set True when `fetch_record_batch()` hands
  back a live reader; cleared on `reader.close()` / `__aexit__`.
- **D-29-10:** **Two-tier entry guard** (the one genuinely new bit of production
  machinery this phase adds):
  - **Foreign callers** (`execute`, another cursor, `commit`, ...): reject with
    `ConnectionBusyError` if `_in_use` **OR** `_reader_open`.
  - **The reader's own pulls**: reject on `_in_use` only, **exempt** from
    `_reader_open` (reentrancy exemption — else the reader deadlocks itself). Each
    pull still brackets the per-call `_in_use` C-access guard.

### Done signal & lifetime binding (STREAM-04, EDGE-33)
- **D-29-11:** The reader's "done" signal is **explicit `close()`** (via
  `async with`), NOT iteration exhaustion. In pyarrow, drained ≠ freed: after
  `StopIteration` the reader/C-stream still sits on the dbapi cursor until
  `close()`. Releasing the lock at exhaustion would re-open the concurrent-C-access
  hazard. So `async for` alone does NOT auto-close and does NOT clear
  `_reader_open`.
- **D-29-12:** **Reader-lifetime binding is mostly free** — the existing sync
  `reset` event handler `_release_arrow_allocators` (`_pool_factory.py:407`)
  closes the underlying dbapi cursor on every checkin path, which closes the
  reader. A read-after-checkin therefore surfaces the driver's native
  closed-stream error naturally (STREAM-04 / EDGE-33). The async reader adds only
  a thin `_detached` guard to convert a post-close/post-checkin read into a clean
  error path — NO weakref/registration machinery of its own.
- **D-29-13:** A stale `_reader_open == True` is harmless: it lives on the
  `AsyncConnection`, which is thrown away at checkin (each `pool.connect()` wraps a
  fresh fairy in a fresh `AsyncConnection`). Checkin is the backstop eraser; close
  is the only clear. Consequence, accepted: a drained-but-never-closed reader keeps
  the connection locked until checkin — which is why `async with reader:` is the
  documented canonical usage.

### Cancel-safety (STREAM-05)
- **D-29-14:** Cancel/timeout on a batch pull fires `cursor.adbc_cancel()` once
  from the loop thread and invalidates the connection (`on_abort=owner.invalidate`)
  so `pool.checkedout() == 0`, identical under asyncio and trio — reusing the
  Phase 25 `cancellable_offload` machinery unchanged.

### Finalizers & typing (EDGE-20, EDGE-22, EDGE-23, PKG-01, PKG-03)
- **D-29-15:** `__del__` on an un-closed reader emits a `ResourceWarning` (never a
  "coroutine was never awaited" `RuntimeWarning`); the happy path (closed via
  context manager) emits neither (EDGE-22, EDGE-23). `__del__` cannot `await`, so
  it is warn-only; actual release rides the reset event.
- **D-29-16:** An exception during shielded reader cleanup chains the body error
  via `__context__` and still releases/invalidates the connection (EDGE-20) —
  mirror the existing shielded-cleanup discipline.
- **D-29-17:** Add a `_SyncReader` structural `Protocol` alongside `_SyncCursor`
  (`schema` property, `read_next_batch`, `close`) so the async reader types against
  the structural surface (real pyarrow reader OR the test stub reader satisfies
  it) rather than importing a concrete pyarrow class. Extend `_SyncCursor` with
  `fetch_record_batch` (PKG-01). All new async public API basedpyright-strict-clean
  (0 errors); the AST import-lint guard still passes over `_async/` — no
  `import asyncio`, no bare `to_thread`, everything routes through the offload
  chokepoint (PKG-03).

### Canonical usage
- **D-29-18:** Document canonical usage as
  `async with await cursor.fetch_record_batch() as reader:` then
  `async for batch in reader:`. This is the one true path (guarantees close fires
  under errors, cancellation, and early `break`).

### Claude's Discretion
- Exact `StopIteration`→`StopAsyncIteration` sentinel mechanism (worker-side catch
  vs. driver end-of-stream) — pick the cleanest, prove it under asyncio + trio.
- Precise placement of the `_detached` guard and how `_reader_open` reentrancy
  exemption is threaded (e.g. a `from_reader=True` param on the entry guard vs. a
  reader-aware entry method).
- Whether `_reader_open` lives as a bare bool or a small counter (only one reader
  per connection is possible, so a bool is expected to suffice).

</decisions>

<specifics>
## Specific Ideas

- Mirror `AsyncCursor` / `AsyncConnection` idioms exactly — same constructor shape,
  same `_offloading()` bracketing, same shielded-close pattern, same
  Google-style-docstring density. The reader should read like a sibling of
  `_cursor.py`, not a novel component.
- Prove STREAM-04 / EDGE-33 (read-after-checkin → native closed-stream error) on
  **both DuckDB and the Snowflake cassette**, under **asyncio and trio**.
- Carry forward the v1.4.0 pitfall discipline: no bespoke async-only error types
  (no `ReaderClosedError`); async mirrors the sync method's native errors.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — STREAM-01..06, EDGE-20, EDGE-22, EDGE-23, EDGE-33,
  PKG-01, PKG-03 definitions; the "no bespoke async-only error types" non-goal
- `.planning/ROADMAP.md` §"Phase 29: Arrow Streaming" — goal, success criteria,
  dependency on Phase 28

### Existing async layer (the patterns this phase copies)
- `src/adbc_poolhouse/_async/_cursor.py` — `AsyncCursor` structure, `_SyncCursor`
  Protocol, per-call `_offloading()` bracketing, shielded `close`, the
  `fetch_arrow_table` offload shape (closest analog to `fetch_record_batch`)
- `src/adbc_poolhouse/_async/_connection.py` — `_in_use` guard,
  `_enter_offload`/`_exit_offload`/`_offloading`, `invalidate` (dedicated teardown
  limiter), shielded check-in; the file to extend with `_reader_open` + two-tier
  guard
- `src/adbc_poolhouse/_async/_cancel.py` — `cancellable_offload` signature and the
  `adbc_cancel`/`on_abort`/`worker_started` cancel contract (reused verbatim)
- `src/adbc_poolhouse/_async/_offload.py` — the single `to_thread.run_sync`
  chokepoint and `on_dispatch` hook the import-lint guard audits
- `src/adbc_poolhouse/_pool_factory.py:407` — `_release_arrow_allocators`, the sync
  `reset`-event handler that closes open cursors on checkin (the free
  reader-lifetime backstop for STREAM-04 / EDGE-33)

### Test harness
- Phase 23 `BlockingStubCursor` harness (see `milestones/v1.4.0-phases/23-*`) —
  extend with a stub `fetch_record_batch` / stub reader satisfying `_SyncReader`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cancellable_offload` (`_cancel.py`): per-pull offload with `adbc_cancel` +
  `on_abort=invalidate` — used unchanged for reader creation and each `__anext__`
  pull.
- `offload` + `CancelScope(shield=True)` (`_cursor.close`, `_connection.close`):
  the shielded-close idiom copied for `reader.close()`.
- `_offloading()` / `_in_use` (`_connection.py`): per-call C-access guard, extended
  (not replaced) by the new `_reader_open` lifetime guard.
- `_release_arrow_allocators` (`_pool_factory.py:407`): closes the dbapi cursor on
  the reset event — gives STREAM-04 / EDGE-33 for free.

### Established Patterns
- Sync-property passthrough for no-I/O members (`description`/`rowcount`/
  `arraysize`) → `schema` follows it.
- `_SyncCursor` structural Protocol → `_SyncReader` follows it; keeps the async
  layer driver-agnostic and stub-testable.
- No worker-exception re-wrapping (EDGE-17): the single offload chokepoint
  re-raises native errors; the reader must not catch/wrap.

### Integration Points
- `AsyncCursor.fetch_record_batch()` is the new entry point (extend `_cursor.py`).
- `AsyncConnection` gains `_reader_open` + the two-tier entry guard (extend
  `_connection.py`).
- New `_async/_reader.py` houses `AsyncRecordBatchReader` + `_SyncReader`.

</code_context>

<deferred>
## Deferred Ideas

- `await reader.read_all()` / `await reader.read_pandas()` async twins — out of
  Phase 29 scope (not in STREAM-01..06; `read_pandas` overlaps Phase 31 `fetch_df`).
- `adbc_ingest` bulk write — Phase 30 (reuses this phase's cancel/offload patterns).
- `fetch_df` / `fetch_polars` — Phase 31.
- P2 edge-hardening matrix (contextvars, trio-checkpoint, timeout precision,
  loop-shutdown) extended across streaming — Phase 32.

</deferred>

---

*Phase: 29-arrow-streaming*
*Context gathered: 2026-07-01*
