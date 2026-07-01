# Requirements: adbc-poolhouse v1.5.0

**Milestone:** v1.5.0 — Async Cursor Completion
**Defined:** 2026-07-01
**Core Value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.

## v1.5.0 Requirements

Complete the async cursor surface by offloading the four ADBC cursor methods deferred at v1.4.0, plus the deferred P2 async edge-case hardening suite. Every new method is a **pure offload wrapper** over a method that already exists on the wrapped sync `adbc_driver_manager.dbapi.Cursor`, routed through the existing v1.4.0 offload chokepoint (`offload` / `cancellable_offload`) and the per-pool `CapacityLimiter`. anyio (asyncio + trio) neutrality is preserved.

Scope constraints (maintainer-confirmed):

- **Mirror the sync method.** Each async method does whatever the underlying sync `dbapi.Cursor` method already does — same return type, same error behavior. poolhouse does **not** invent async-specific error types, pre-checks, or wrapping beyond the v1.4.0 offload/limiter/cancellation machinery that every async method already routes through.
- **No dependency or extras change.** `pyarrow` is already a core dep; pandas and polars stay **user-supplied runtime deps** (added to the dev group only, to exercise the tests). The sync path stays zero-cost and the PEP 562 lazy-import surface is untouched.
- **No sync-core change.** The async layer wraps the unchanged sync core; only the async package and the internal `_SyncCursor` Protocol are extended.
- **`fetch_record_batch` is the one genuine design.** It returns a live `pyarrow.RecordBatchReader` bound to the open statement. The existing reset-event checkin already closes the reader, so a post-checkin read surfaces the driver's native closed-stream error — a clean Python exception, never a use-after-free. poolhouse's job is only to guarantee that closed-before-checkin ordering, not to add a bespoke error type.

### Arrow Streaming

- [ ] **STREAM-01**: User can `await cursor.fetch_record_batch()` to obtain an `AsyncRecordBatchReader` (reader creation offloaded through the pool limiter)
- [ ] **STREAM-02**: User can `async for batch in reader:` to iterate `pyarrow.RecordBatch` chunks, where each `read_next_batch()` pull is offloaded individually through the limiter
- [ ] **STREAM-03**: `AsyncRecordBatchReader` is an async context manager; `await reader.close()` / `__aexit__` closes the reader offloaded and shielded, freeing Arrow resources before the connection can check in
- [ ] **STREAM-04**: The reader's lifetime is bound to its checked-out connection; the reset-event checkin closes the reader first, so a read after checkin (or after `close`) surfaces the driver's native closed-stream error (as the sync method would) — a clean Python exception, never a use-after-free / segfault. poolhouse adds no bespoke error type
- [ ] **STREAM-05**: Cancelling or timing out a batch pull fires `cursor.adbc_cancel()` once from the loop thread and invalidates the connection, so `pool.checkedout() == 0` and the pool is never poisoned — identical under asyncio and trio
- [ ] **STREAM-06**: A second in-flight operation on the parent cursor/connection while a reader is live raises `ConnectionBusyError` (reuses the `_in_use` guard) — never silent serialization or concurrent C access

### Async Bulk Write

- [ ] **INGEST-01**: User can `await cursor.adbc_ingest(table_name, data, *, mode=..., catalog_name=None, db_schema_name=None, temporary=False)` returning the affected row count (single whole-operation offload)
- [ ] **INGEST-02**: `mode` is a typed `Literal["create", "append", "replace", "create_append"]` forwarded verbatim to the driver; the docs warn explicitly that `replace` **drops** the existing table
- [ ] **INGEST-03**: `data` accepts the Arrow inputs the driver accepts (`pyarrow.Table` / `RecordBatch` / `RecordBatchReader` / Arrow C-stream capsule) without conversion by poolhouse
- [ ] **INGEST-04**: A cancelled or timed-out ingest fires `adbc_cancel` and **invalidates** the connection (a partially-applied write poisons it — `on_abort=invalidate`); `pool.checkedout() == 0`, asyncio and trio parity

### DataFrame Convenience

- [ ] **DF-01**: User can `await cursor.fetch_df()` returning a `pandas.DataFrame` (single whole-operation offload)
- [ ] **DF-02**: User can `await cursor.fetch_polars()` returning a `polars.DataFrame` (single whole-operation offload)
- [ ] **DF-03**: When pandas/polars is not installed, `fetch_df`/`fetch_polars` behave exactly as the underlying sync ADBC cursor method does — the native `ModuleNotFoundError` raised in the worker propagates unchanged through the offload chokepoint. poolhouse adds no `find_spec` pre-check or wrapping; pandas/polars are user-supplied, not poolhouse dependencies
- [ ] **DF-04**: The returned frame is self-owning and valid after checkin (materialized, not bound to the connection) — same guarantee as `fetch_arrow_table` (EDGE-21)

### Packaging & Type Safety

- [ ] **PKG-01**: The internal `_SyncCursor` structural Protocol gains signatures for `fetch_record_batch`, `adbc_ingest`, `fetch_df`, and `fetch_polars`; all new async public API is fully typed under basedpyright strict (0 errors)
- [ ] **PKG-02**: pandas and polars are added to the **dev dependency group only** (positive tests guarded by `importorskip`); `[project.dependencies]`, `[project.optional-dependencies]`, and the `__init__.py` lazy-import surface are unchanged — `import adbc_poolhouse` with pandas/polars absent is unaffected
- [ ] **PKG-03**: The AST import-lint guard still passes over `_async/` — the four new methods route through the offload chokepoint with the pool limiter, no `import asyncio`, no bare `to_thread`

### Async Edge-Case Hardening (deferred P2 suite)

Deterministic arrange/trigger/assert tests, each run under **both** asyncio and trio, extending coverage to the new streaming/ingest/DataFrame paths. Full designs in `.planning/research/ASYNC-EDGE-CASES.md`. No new production machinery beyond the `AsyncRecordBatchReader` `__aexit__`/`__del__` surface.

- [ ] **EDGE-08**: A trio checkpoint is delivered at the offload boundary even with no intervening checkpoint — no starvation, no missing cancellation point
- [ ] **EDGE-13**: contextvars set before an offload are visible to the worker thread (copied in), asserted on a new-method offload
- [ ] **EDGE-14**: Mutations a worker makes to contextvars do not leak back to the calling task after the offload returns
- [ ] **EDGE-20**: An exception during shielded cleanup does not mask the body error — the body exception is chained via `__context__` and the connection is still released/invalidated
- [ ] **EDGE-22**: `__del__` of an un-closed `AsyncCursor` / `AsyncRecordBatchReader` emits a `ResourceWarning`, never a "coroutine was never awaited" `RuntimeWarning`
- [ ] **EDGE-23**: The happy path (properly closed via context manager) emits no `ResourceWarning` and no `RuntimeWarning`
- [ ] **EDGE-24**: An open pool or a pending offload at event-loop shutdown raises no library-attributable exception
- [ ] **EDGE-31**: `move_on_after(0)` still cancels a blocked `execute`/streaming pull cleanly — `adbc_cancel` fires, connection invalidates
- [ ] **EDGE-32**: An operation that completes at deadline−ε is not over-cancelled — no spurious `adbc_cancel`, no invalidate, connection returns clean
- [ ] **EDGE-33**: (extends EDGE-21) On an `AsyncRecordBatchReader`, a read after checkin surfaces the driver's native closed-stream error (a clean exception, not a crash); drain-then-checkin yields the correct rows — proven on both DuckDB and the Snowflake cassette

### Documentation

- [ ] **DOCS-01**: The async guide documents Arrow streaming (`fetch_record_batch` → `async for` → close), including the reader-lifetime contract and honest concurrency framing (per-batch offload; GIL re-acquired during materialization)
- [ ] **DOCS-02**: The async guide and API reference document `adbc_ingest` with the `mode` Literal table and an explicit "`replace` drops the table" warning
- [ ] **DOCS-03**: `fetch_df` / `fetch_polars` are documented, noting pandas/polars are user-supplied (install-it-yourself) and that a missing dep surfaces a native `ModuleNotFoundError`
- [ ] **DOCS-04**: API reference renders `AsyncRecordBatchReader` and the four new `AsyncCursor` methods with Google-style docstrings (Args/Returns/Raises + Example); `uv run mkdocs build --strict` passes; humanizer pass applied to all new or substantially rewritten prose

## Out of Scope

Explicit exclusions for this milestone (with reasoning):

| Feature | Reason |
|---------|--------|
| New `[pandas]` / `[polars]` poolhouse extras | pandas/polars are user-supplied runtime deps; ADBC's own methods raise a clear error if absent, exactly how poolhouse treats ADBC drivers. Adding extras would grow the dependency surface for no benefit |
| `find_spec` pre-check wrapping the missing-dep error | Async mirrors the sync method: pass the native `ModuleNotFoundError` through unchanged (DF-03); a poolhouse-framed re-raise would diverge from sync behavior for marginal UX gain |
| Bespoke async-only error types (e.g. `ReaderClosedError`) | Async mirrors the sync method's native errors; the reset-event checkin already makes read-after-checkin a clean driver exception (STREAM-04), so no new error class is warranted |
| Sync-core cursor abstraction | The sync library stays pool-only; `AsyncCursor` remains the only cursor abstraction. These methods extend the async surface, not the sync one |
| Write-side GIL micro-benchmark for `adbc_ingest` | SPIKE-02 (v1.4.0) already measured read materialization; docs disclaim write-throughput parallelism rather than re-spike. Revisit only if a consumer reports an ingest bottleneck |
| Async ADBC metadata (`adbc_get_objects`, `adbc_get_table_schema`, `adbc_get_info`) | Deferred to v2+ per v1.4.0 Future Requirements; not part of the "deferred cursor methods" scope |
| Async prepared statements (`adbc_prepare`, `adbc_execute_schema`) | Deferred to v2+ per v1.4.0 Future Requirements |
| anyio-native checkout limiter | v1.4.0 deferral; only if offloaded checkout proves a measured bottleneck |

## Traceability

Every v1.5.0 requirement maps to exactly one phase (Phases 29–33). PKG-* are cross-cutting gates enforced in every phase but assigned to a single phase each for coverage: PKG-01 (first Protocol extension) and PKG-03 (import-lint guard, owned early) → Phase 29; PKG-02 (pandas/polars first needed in tests) → Phase 31.

| Requirement | Phase | Status |
|-------------|-------|--------|
| STREAM-01 | Phase 29 | RED-pinned (29-01) |
| STREAM-02 | Phase 29 | RED-pinned (29-01) |
| STREAM-03 | Phase 29 | RED-pinned (29-01) |
| STREAM-04 | Phase 29 | RED-pinned (29-01) |
| STREAM-05 | Phase 29 | RED-pinned (29-01) |
| STREAM-06 | Phase 29 | Guard GREEN (29-02: two-tier `_reader_open`/`from_reader`); e2e pending 29-03 |
| INGEST-01 | Phase 30 | Pending |
| INGEST-02 | Phase 30 | Pending |
| INGEST-03 | Phase 30 | Pending |
| INGEST-04 | Phase 30 | Pending |
| DF-01 | Phase 31 | Pending |
| DF-02 | Phase 31 | Pending |
| DF-03 | Phase 31 | Pending |
| DF-04 | Phase 31 | Pending |
| PKG-01 | Phase 29 | Pending |
| PKG-02 | Phase 31 | Pending |
| PKG-03 | Phase 29 | Guard passes over `_async/` (29-02); re-verified each phase |
| EDGE-08 | Phase 32 | Pending |
| EDGE-13 | Phase 32 | Pending |
| EDGE-14 | Phase 32 | Pending |
| EDGE-20 | Phase 29 | RED-pinned (29-01) |
| EDGE-22 | Phase 29 | RED-pinned (29-01) |
| EDGE-23 | Phase 29 | RED-pinned (29-01) |
| EDGE-24 | Phase 32 | Pending |
| EDGE-31 | Phase 32 | Pending |
| EDGE-32 | Phase 32 | Pending |
| EDGE-33 | Phase 29 | RED-pinned (29-01, DuckDB; Snowflake leg manual-only per A1) |
| DOCS-01 | Phase 33 | Pending |
| DOCS-02 | Phase 33 | Pending |
| DOCS-03 | Phase 33 | Pending |
| DOCS-04 | Phase 33 | Pending |

**Coverage:**
- v1.5.0 requirements: 31 total
- Mapped to phases: 31 (100%) ✓
- Unmapped: 0 ✓

**Per-phase counts:**
- Phase 29 (Arrow Streaming): 12 — STREAM-01..06, EDGE-20, EDGE-22, EDGE-23, EDGE-33, PKG-01, PKG-03
- Phase 30 (Async Bulk Write): 4 — INGEST-01..04
- Phase 31 (DataFrame Convenience): 5 — DF-01..04, PKG-02
- Phase 32 (P2 Edge Hardening): 6 — EDGE-08, EDGE-13, EDGE-14, EDGE-24, EDGE-31, EDGE-32
- Phase 33 (Documentation): 4 — DOCS-01..04

---
*Requirements defined: 2026-07-01*
*Last updated: 2026-07-01 — traceability populated during roadmap creation (Phases 29–33, 100% coverage)*
