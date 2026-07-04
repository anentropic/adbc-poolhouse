# Roadmap: adbc-poolhouse

## Milestones

- 🚧 **v1.5.0 Async Cursor Completion** — Phases 29–35 (in progress)
- ✅ **v1.4.0 Async API** — Phases 22–28 (shipped 2026-07-01)
- ✅ **v1.3.0 Quack Backend** — Phases 21–21.1 (shipped 2026-05-21)
- ✅ **v1.2.0 Plugin/Extensibility API** — Phases 16-20 (shipped 2026-03-15)
- ✅ **v1.0.0 MVP + Backend Expansion** — Phases 1-15 (shipped 2026-03-07)

## Phases

### 🚧 v1.5.0 Async Cursor Completion (In Progress)

**Milestone Goal:** Complete the async cursor surface by offloading the four v1.4.0-deferred ADBC cursor methods (`fetch_record_batch` Arrow streaming, `adbc_ingest` bulk write, `fetch_df`/`fetch_polars` DataFrame convenience) and land the deferred P2 async edge-case hardening suite. Every new method is a pure offload wrapper over a method that already exists on the wrapped sync `dbapi.Cursor`, routed through the existing v1.4.0 `offload`/`cancellable_offload` chokepoint and per-pool `CapacityLimiter` — no new runtime deps, no new extras, no sync-core change. Async methods mirror the underlying sync method's behavior: no invented async-specific error types, no `find_spec` pre-checks, no bespoke wrapping. **Extended (2026-07-04):** the milestone now also closes async/sync parity for the remaining ADBC surface exposed by the sync raw-cursor path — connection-level metadata introspection (Phase 34) and cursor-level prepared statements (Phase 35) — following the same offload-wrapper pattern. Partitioned result sets (`adbc_execute_partitions`/`adbc_read_partition`) remain deferred: they are a niche Flight-SQL-oriented feature that most supported backends return unsupported for.

- [x] **Phase 29: Arrow Streaming** — `await cursor.fetch_record_batch()` → `AsyncRecordBatchReader` with per-batch offloaded `async for`, reader-lifetime bound to checkout, read-after-checkin surfaces the driver's native closed-stream error — completed 2026-07-01
- [x] **Phase 30: Async Bulk Write** — `await cursor.adbc_ingest(table, data, mode=...)`, single whole-op offload, typed `Literal` mode, `on_abort=invalidate` on cancel (2/2 plans) — completed 2026-07-01
- [x] **Phase 31: DataFrame Convenience** — `await cursor.fetch_df()` / `await cursor.fetch_polars()`, single-offload wrappers returning self-owning frames; pandas/polars user-supplied
- [x] **Phase 32: P2 Edge Hardening** — remaining deferred P2 edge cases (contextvars, trio-checkpoint, timeout precision, loop-shutdown) extended across the new streaming/ingest/DataFrame paths; all six EDGE requirements green x20 on macOS + Linux CI, test-only (zero production change) — completed 2026-07-02
- [x] **Phase 33: Documentation** — streaming guide, ingest mode table + replace warning, DataFrame user-supplied note, API reference for the new symbols, `mkdocs build --strict` gate, humanizer pass — completed 2026-07-04
- [ ] **Phase 34: Async Metadata** — the six `adbc_get_*` connection metadata methods as async offload wrappers over the sync `dbapi.Connection` (parity gap named in the docs caveat)
- [ ] **Phase 35: Async Prepared Statements** — `adbc_prepare` + `adbc_execute_schema` as async offload wrappers over the sync `dbapi.Cursor` (second parity gap named in the docs caveat)

<details>
<summary>✅ v1.4.0 Async API (Phases 22-28) — SHIPPED 2026-07-01</summary>

- [x] **Phase 22: Feasibility Spike** — Benchmark GIL release for concurrent execute vs `fetch_arrow_table`; go/no-go gating the milestone (2/2 plans) — completed 2026-06-27
- [x] **Phase 23: Test Harness Foundation** — `BlockingStubCursor` harness, event-gating/virtual-clock helpers, import-lint guard (4/4 plans) — completed 2026-06-27
- [x] **Phase 24: Core Async Wrapper** — offload helper, per-pool `CapacityLimiter`, `AsyncPool`/`AsyncConnection`/`AsyncCursor`, full DBAPI surface + structural EDGE coverage (5/5 plans) — completed 2026-06-27
- [x] **Phase 25: Cancellation** — `adbc_cancel` wiring, shielded checkin, invalidate-on-cancel, no-leak under asyncio + trio (5/5 plans) — completed 2026-06-28
- [x] **Phase 26: Packaging & Extra Scoping** — `[async]` extra, PEP 562 lazy import, zero-cost sync path, basedpyright-strict async typing (4/4 plans) — completed 2026-06-28
- [x] **Phase 27: Dual-Backend Test Matrix** — asyncio+trio × DuckDB + Snowflake cassette; Arrow-stability and limiter-stress proofs; meta-guards (5/5 plans) — completed 2026-06-28
- [x] **Phase 28: Documentation** — async usage guide, API reference, configuration/index updates, docs quality gate (4/4 plans) — completed 2026-06-29

Full detail: `milestones/v1.4.0-ROADMAP.md` · Audit: `milestones/v1.4.0-MILESTONE-AUDIT.md`

</details>

<details>
<summary>✅ v1.3.0 Quack Backend (Phases 21-21.1) — SHIPPED 2026-05-21</summary>

- [x] **Phase 21: Quack Backend** — Add `QuackConfig` (config + tests + docs) for `adbc-driver-quack` — completed 2026-05-19
- [x] **Phase 21.1: ADBC dispatch URI-positional fix** — Fix `create_pool()` dispatch for Quack/Postgres/FlightSQL — completed 2026-05-20

</details>

<details>
<summary>✅ v1.2.0 Plugin/Extensibility API (Phases 16-20) — SHIPPED 2026-03-15</summary>

- [x] Phase 16: Driver Import Semi-Integration Tests (2/2 plans) — completed 2026-03-12
- [x] Phase 17: Registry Infrastructure (2/2 plans) — completed 2026-03-12
- [x] Phase 17.5: Translator Consolidation (5/5 plans) — completed 2026-03-14
- [x] Phase 18: Registration Removal (3/3 plans) — completed 2026-03-15
- [x] Phase 19: Raw create_pool Overload (4/4 plans) — completed 2026-03-15
- [x] Phase 20: Protocol Documentation (1/1 plan) — completed 2026-03-15

</details>

<details>
<summary>✅ v1.0.0 MVP + Backend Expansion (Phases 1-15) — SHIPPED 2026-03-07</summary>

- [x] Phase 1: Pre-flight Fixes (1/1 plans) — completed 2026-02-23
- [x] Phase 2: Dependency Declarations (2/2 plans) — completed 2026-02-23
- [x] Phase 3: Config Layer (7/7 plans) — completed 2026-02-24
- [x] Phase 4: Translation and Driver Detection (5/5 plans) — completed 2026-02-24
- [x] Phase 5: Pool Factory and DuckDB Integration (2/2 plans) — completed 2026-02-24
- [x] Phase 6: Snowflake Integration (1/1 plan) — superseded by Phase 15
- [x] Phase 7: Documentation and PyPI Publication (5/5 plans) — completed 2026-02-27
- [x] Phase 8: Review and Improve Docs (6/6 plans) — completed 2026-02-28
- [x] Phase 9: Infrastructure and Databricks Fix (2/2 plans) — completed 2026-03-01
- [x] Phase 10: SQLite Backend (4/4 plans) — completed 2026-03-01
- [x] Phase 11: Foundry Tooling and MySQL Backend (4/4 plans) — completed 2026-03-01
- [x] Phase 12: ClickHouse Backend (4/4 plans) — completed 2026-03-02
- [x] Phase 13: Verification and Tracking Fix (2/2 plans) — completed 2026-03-02
- [x] Phase 14: Homepage Discovery Fix (1/1 plan) — completed 2026-03-02
- [x] Phase 15: Replace Syrupy with pytest-adbc-replay (5/5 plans) — completed 2026-03-07

</details>

## Phase Details (v1.5.0)

### Phase 29: Arrow Streaming

**Goal**: Users can stream Arrow query results lazily via `await cursor.fetch_record_batch()` → `async for batch in reader:`, with the reader's lifetime safely bound to the checked-out connection so read-after-checkin surfaces a clean driver error rather than a use-after-free. This is the milestone's headline and only genuine design risk, front-loaded because the reader-lifetime patterns (`__aexit__`, `__del__`, `_detached` guard, per-batch `cancellable_offload`) are copied by later phases.
**Depends on**: Phase 28 (v1.4.0 async layer shipped)
**Requirements**: STREAM-01, STREAM-02, STREAM-03, STREAM-04, STREAM-05, STREAM-06, EDGE-33, EDGE-20, EDGE-22, EDGE-23, PKG-01, PKG-03
**Success Criteria** (what must be TRUE):

  1. `await cursor.fetch_record_batch()` returns an `AsyncRecordBatchReader`; `async for batch in reader:` yields `pyarrow.RecordBatch` chunks with each `read_next_batch()` pull offloaded individually through the pool limiter (STREAM-01, STREAM-02)
  2. The reader is an async context manager (`await reader.close()` / `__aexit__` closes it offloaded-and-shielded), and reading after checkin or after close surfaces the driver's native closed-stream error — a clean Python exception, never a segfault — proven on DuckDB and the Snowflake cassette under asyncio and trio; drain-then-checkin yields correct rows (STREAM-03, STREAM-04, EDGE-33)
  3. Cancelling or timing out a batch pull fires `adbc_cancel` once and invalidates the connection so `pool.checkedout() == 0`, identical under asyncio and trio; a second in-flight operation on the parent cursor while a reader is live raises `ConnectionBusyError` (STREAM-05, STREAM-06)
  4. An unclosed reader's `__del__` emits a `ResourceWarning` (never a "coroutine was never awaited" `RuntimeWarning`); the happy path emits neither; an exception during shielded reader cleanup chains the body error via `__context__` and still releases/invalidates the connection (EDGE-22, EDGE-23, EDGE-20)
  5. The `_SyncCursor` Protocol gains a `fetch_record_batch` signature and all new async public API is basedpyright-strict-clean (0 errors); the AST import-lint guard still passes over `_async/` with no `import asyncio` and no bare `to_thread` (PKG-01, PKG-03)**Plans**: 4 plans

**Wave 1**

- [x] 29-01-PLAN.md — Wave-0 test scaffolding: stub reader + six RED reader test files + Snowflake cassette A1 smoke (A1 resolved: no streaming cassette replay; Snowflake legs manual-only) — completed 2026-07-01
- [x] 29-02-PLAN.md — AsyncConnection two-tier `_reader_open` lifetime guard (`from_reader` reentrancy) — completed 2026-07-01

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 29-03-PLAN.md — `AsyncRecordBatchReader` + `AsyncCursor.fetch_record_batch` + `_SyncReader`/`_SyncCursor` Protocols — completed 2026-07-01

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 29-04-PLAN.md — Arrow-streaming docs (async guide streaming section + AsyncRecordBatchReader/fetch_record_batch API reference + strict build + humanizer; human-verify checkpoint auto-approved under --auto) — completed 2026-07-01

**UI hint**: no

### Phase 30: Async Bulk Write

**Goal**: Users can bulk-write Arrow data via `await cursor.adbc_ingest(table_name, data, mode=...)` as a single whole-operation offload that returns the affected row count, with a typed `Literal` mode forwarded verbatim to the driver and cancel-safety that invalidates the connection on a partially-applied write. This phase exercises the write path and the keyword-only-arg-arity concern in isolation, reusing the Phase 29 cancel/offload patterns.
**Depends on**: Phase 29
**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04
**Success Criteria** (what must be TRUE):

  1. `await cursor.adbc_ingest(table_name, data, *, mode=..., catalog_name=None, db_schema_name=None, temporary=False)` returns the affected row count as an `int` from a single whole-operation offload; a round-trip ingest → query on DuckDB returns the ingested rows (INGEST-01)
  2. `mode` is typed as `Literal["create", "append", "replace", "create_append"]`, defaults to `"create"`, and is forwarded verbatim to the driver (INGEST-02)
  3. `data` accepts the Arrow inputs the driver accepts (`pyarrow.Table` / `RecordBatch` / `RecordBatchReader` / Arrow C-stream capsule) with no conversion by poolhouse (INGEST-03)
  4. A cancelled or timed-out ingest fires `adbc_cancel` and invalidates the connection (`on_abort=invalidate`), leaving `pool.checkedout() == 0` with asyncio and trio parity (INGEST-04)

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 30-01-PLAN.md — Wave 0 RED scaffolding: BlockingStubCursor.adbc_ingest stub + four failing tests (round-trip, modes, cancel/parity, signature) pinning INGEST-01..04

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 30-02-PLAN.md — GREEN: AsyncCursor.adbc_ingest (fetch_arrow_table clone + functools.partial arg binding) + _SyncCursor Protocol member + docs quality gate — completed 2026-07-01

**UI hint**: no

### Phase 31: DataFrame Convenience

**Goal**: Users can materialize query results directly into a `pandas.DataFrame` (`await cursor.fetch_df()`) or `polars.DataFrame` (`await cursor.fetch_polars()`) via trivial single-offload wrappers, with pandas/polars remaining user-supplied runtime deps (a missing dep raises the native `ModuleNotFoundError` unchanged, exactly as the sync method does). The frames are self-owning and valid after checkin.
**Depends on**: Phase 30
**Requirements**: DF-01, DF-02, DF-03, DF-04, PKG-02
**Success Criteria** (what must be TRUE):

  1. `await cursor.fetch_df()` returns a `pandas.DataFrame` and `await cursor.fetch_polars()` returns a `polars.DataFrame`, each from a single whole-operation offload (DF-01, DF-02)
  2. When pandas/polars is not installed, `fetch_df`/`fetch_polars` propagate the native `ModuleNotFoundError` raised in the worker unchanged through the offload chokepoint — no `find_spec` pre-check, no poolhouse wrapping (DF-03)
  3. The returned frame is self-owning and valid after checkin (materialized in the worker, not bound to the connection) — same guarantee as `fetch_arrow_table` (EDGE-21) (DF-04)
  4. pandas and polars are added to the dev dependency group only; `[project.dependencies]`, `[project.optional-dependencies]`, and the `__init__.py` lazy-import surface are unchanged, and `import adbc_poolhouse` with pandas/polars absent is unaffected (positive tests guarded by `importorskip`) (PKG-02)

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 31-01-PLAN.md — Wave 0 RED scaffolding: pandas/polars dev-group deps + BlockingStubCursor fetch_df/fetch_polars stubs (counters + raise-injection) + six failing test files (round-trip, lifetime, missing-dep, busy, cancel, signature) pinning DF-01..04/PKG-02 ✅ 30 failed / 1 passed (import_surface), all failing solely on the missing methods

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 31-02-PLAN.md — Wave 2 GREEN: AsyncCursor.fetch_df/fetch_polars (fetch_arrow_table clones) + _SyncCursor Protocol members + TYPE_CHECKING pandas/polars imports + docs section ✅ 18 DF tests GREEN, cancel/busy 20/20 looped, full async suite 193 passed/4 skipped, basedpyright 0 errors, mkdocs --strict green

**UI hint**: no

### Phase 32: P2 Edge Hardening

**Goal**: The remaining deferred P2 async edge cases are pinned by deterministic arrange/trigger/assert tests — each run under both asyncio and trio — extending existing chokepoint coverage across the new streaming, ingest, and DataFrame paths plus the `__del__` finalizer surface. No new production machinery beyond the finalizers; tests reuse the Phase 23 `BlockingStubCursor` harness, now that all four new methods exist.
**Depends on**: Phase 31
**Requirements**: EDGE-08, EDGE-13, EDGE-14, EDGE-24, EDGE-31, EDGE-32
**Success Criteria** (what must be TRUE):

  1. A trio checkpoint is delivered at the offload boundary even with no intervening checkpoint — no starvation, no missing cancellation point — asserted on a new-method offload (EDGE-08)
  2. contextvars set before an offload are visible to the worker thread (copied in), and worker mutations do not leak back to the calling task after the offload returns — asserted on a new-method offload (EDGE-13, EDGE-14)
  3. `move_on_after(0)` still cancels a blocked streaming pull / ingest cleanly (`adbc_cancel` fires, connection invalidates), while an operation completing at deadline−ε is not over-cancelled (no spurious `adbc_cancel`, no invalidate, connection returns clean) (EDGE-31, EDGE-32)
  4. An open pool or a pending offload at event-loop shutdown — extended to mid-stream and mid-ingest scenarios — raises no library-attributable exception, with trio's nursery strictness as the canary (EDGE-24)

**Plans**: 3 plans
Plans:
**Wave 1** *(parallel RED — no file overlap)*

- [x] 32-01-PLAN.md — EDGE-08 (cancel-at-offload on adbc_ingest) + EDGE-13/14 (contextvar copy-in / no-leak-back on fetch_df); deterministic, dual-backend
- [x] 32-02-PLAN.md — EDGE-31/32 (blocked-op cancel via move_on_after under autojumping virtual_clock / deadline−ε not over-cancelled on streaming pull + ingest) + EDGE-24 (loop-shutdown cleanliness mid-stream/mid-ingest + real drained-close); looped x20

**Wave 2** *(blocked on Wave 1)*

- [x] 32-03-PLAN.md — Full-suite x20 loop gate (macOS 2702 passed, 0 hangs) + Linux-CI x20 confirmation (run 28622475955, Py 3.11+3.14, 0 hangs, authoritative) + import-lint + basedpyright-strict + mkdocs --strict; contingency NOT fired (test-only, zero production change)

**UI hint**: no

### Phase 33: Documentation

**Goal**: The new async surface is fully documented — Arrow streaming guide, ingest mode table with the explicit `replace`-drops-the-table warning, DataFrame user-supplied note, and API-reference entries for `AsyncRecordBatchReader` and the four new `AsyncCursor` methods — with honest concurrency framing throughout. This is the consolidation point for the docs gate: per-method Google-style docstrings are already a completion requirement in every earlier phase, and this phase closes `mkdocs build --strict` plus a humanizer pass.
**Depends on**: Phase 32
**Requirements**: DOCS-01, DOCS-02, DOCS-03, DOCS-04
**Success Criteria** (what must be TRUE):

  1. The async guide documents Arrow streaming (`fetch_record_batch` → `async for` → close) including the reader-lifetime contract and honest concurrency framing (per-batch offload; GIL re-acquired during materialization) (DOCS-01)
  2. The async guide and API reference document `adbc_ingest` with the `mode` Literal table and an explicit "`replace` drops the table" warning (DOCS-02)
  3. `fetch_df` / `fetch_polars` are documented, noting pandas/polars are user-supplied (install-it-yourself) and that a missing dep surfaces a native `ModuleNotFoundError` (DOCS-03)
  4. The API reference renders `AsyncRecordBatchReader` and the four new `AsyncCursor` methods with Google-style docstrings (Args/Returns/Raises + Example); `mkdocs build --strict` passes; a humanizer pass is applied to all new or substantially rewritten prose (DOCS-04)

**Plans**: 2 plansPlans:
**Wave 1**

- [x] 33-01-PLAN.md — Reconcile + humanize async guide/index prose (DOCS-01/02/03; fix index.md DataFrame-availability contradiction) — completed 2026-07-04

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 33-02-PLAN.md — API-reference render-fidelity audit + strict-build completion gate (DOCS-04, DOCS-02 reference half) — completed 2026-07-04

**UI hint**: no

### Phase 34: Async Metadata

**Goal**: The six ADBC connection-level metadata methods (`adbc_get_info`, `adbc_get_objects`, `adbc_get_table_schema`, `adbc_get_table_types`, `adbc_get_statistics`, `adbc_get_statistic_names`) are available on the async connection as pure offload wrappers over the wrapped sync `dbapi.Connection`, routed through the existing v1.4.0 `offload`/`cancellable_offload` chokepoint and per-pool `CapacityLimiter`. Behavior mirrors the underlying sync method — Arrow-returning metadata surfaces its native reader/schema — with no invented async-specific error types and no `find_spec` pre-checks. Closes the async/sync parity gap for metadata introspection named in the v1.5.0 docs caveat.
**Depends on**: Phase 33
**Requirements**: META-01, META-02, META-03, META-04
**Success Criteria** (what must be TRUE):

  1. All six `adbc_get_*` methods are awaitable on the async connection, each offloading its sync counterpart through the established chokepoint (META-01)
  2. Return types mirror the sync methods; Arrow-returning metadata (`adbc_get_objects`, `adbc_get_info`, `adbc_get_statistics`) surfaces its native reader without eager materialization; no async-specific error types invented (META-02)
  3. A backend that does not implement a metadata method surfaces the driver's native error unchanged (META-03)
  4. The async guide + API reference document the async metadata methods and the v1.5.0 caveat shrinks accordingly; `mkdocs build --strict` passes; humanizer pass applied (META-04)

**Plans**: TBD
**UI hint**: no

### Phase 35: Async Prepared Statements

**Goal**: `adbc_prepare` and `adbc_execute_schema` are available on the async cursor as pure offload wrappers over the wrapped sync `dbapi.Cursor`, routed through the existing `offload`/`cancellable_offload` chokepoint and per-pool `CapacityLimiter`. Behavior mirrors the sync statement lifecycle — `adbc_execute_schema` returns the result Arrow schema without executing the query — with no invented async-specific error types. Closes the second async/sync parity gap named in the v1.5.0 docs caveat.
**Depends on**: Phase 34
**Requirements**: PREP-01, PREP-02, PREP-03
**Success Criteria** (what must be TRUE):

  1. `adbc_prepare` and `adbc_execute_schema` are awaitable on the async cursor, each offloading its sync counterpart through the established chokepoint (PREP-01)
  2. Behavior mirrors the sync methods — `adbc_execute_schema` returns the result Arrow schema without executing; no async-specific error types invented (PREP-02)
  3. The async guide + API reference document the async prepared-statement methods and remove the corresponding caveat line; `mkdocs build --strict` passes; humanizer pass applied (PREP-03)

**Plans**: TBD
**UI hint**: no

## Progress

**Execution Order:**
Phases execute in numeric order: 29 → 30 → 31 → 32 → 33 → 34 → 35

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 29. Arrow Streaming | v1.5.0 | 4/4 | Complete    | 2026-07-01 |
| 30. Async Bulk Write | v1.5.0 | 2/2 | Complete    | 2026-07-01 |
| 31. DataFrame Convenience | v1.5.0 | 2/2 | Complete    | 2026-07-02 |
| 32. P2 Edge Hardening | v1.5.0 | 3/3 | Complete    | 2026-07-02 |
| 33. Documentation | v1.5.0 | 2/2 | Complete    | 2026-07-04 |
| 34. Async Metadata | v1.5.0 | 0/TBD | Not started | - |
| 35. Async Prepared Statements | v1.5.0 | 0/TBD | Not started | - |
| 22-28. Async API | v1.4.0 | 29/29 | Complete | 2026-07-01 |
| 21.1. ADBC dispatch URI-positional fix | v1.3.0 | 3/3 | Complete | 2026-05-20 |
| 21. Quack Backend | v1.3.0 | 3/3 | Complete | 2026-05-19 |
| 16-20. Plugin/Extensibility API | v1.2.0 | 17/17 | Complete | 2026-03-15 |
| 1-15. MVP + Backend Expansion | v1.0.0 | 51/51 | Complete | 2026-03-07 |
</content>
