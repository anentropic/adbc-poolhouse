# Roadmap: adbc-poolhouse

## Milestones

- ✅ **v1.5.0 Async Cursor Completion** — Phases 29–35 (shipped 2026-07-05)
- ✅ **v1.4.0 Async API** — Phases 22–28 (shipped 2026-07-01)
- ✅ **v1.3.0 Quack Backend** — Phases 21–21.1 (shipped 2026-05-21)
- ✅ **v1.2.0 Plugin/Extensibility API** — Phases 16-20 (shipped 2026-03-15)
- ✅ **v1.0.0 MVP + Backend Expansion** — Phases 1-15 (shipped 2026-03-07)

## Phases

<details>
<summary>✅ v1.5.0 Async Cursor Completion (Phases 29-35) — SHIPPED 2026-07-05</summary>

- [x] **Phase 29: Arrow Streaming** — `await cursor.fetch_record_batch()` → `AsyncRecordBatchReader` with per-batch offloaded `async for`, reader-lifetime bound to checkout, read-after-checkin surfaces the driver's native closed-stream error (4/4 plans) — completed 2026-07-01
- [x] **Phase 30: Async Bulk Write** — `await cursor.adbc_ingest(table, data, mode=...)`, single whole-op offload, typed `Literal` mode, `on_abort=invalidate` on cancel (2/2 plans) — completed 2026-07-01
- [x] **Phase 31: DataFrame Convenience** — `await cursor.fetch_df()` / `await cursor.fetch_polars()`, single-offload wrappers returning self-owning frames; pandas/polars user-supplied (2/2 plans) — completed 2026-07-02
- [x] **Phase 32: P2 Edge Hardening** — remaining deferred P2 edge cases (contextvars, trio-checkpoint, timeout precision, loop-shutdown) extended across the new streaming/ingest/DataFrame paths; all six EDGE requirements green x20 on macOS + Linux CI, test-only (zero production change) (3/3 plans) — completed 2026-07-02
- [x] **Phase 33: Documentation** — streaming guide, ingest mode table + replace warning, DataFrame user-supplied note, API reference for the new symbols, `mkdocs build --strict` gate, humanizer pass (2/2 plans) — completed 2026-07-04
- [x] **Phase 34: Async Metadata** — the six `adbc_get_*` connection metadata methods as async offload wrappers over the sync `dbapi.Connection`; streaming trio wrapped in `AsyncRecordBatchReader` (code review fixed CR-34-01: metadata readers are non-poisoning on cancel) (3/3 plans) — completed 2026-07-04
- [x] **Phase 35: Async Prepared Statements** — `adbc_prepare` + `adbc_execute_schema` as async offload wrappers over the sync `dbapi.Cursor` (second parity gap named in the docs caveat) (3/3 plans) — completed 2026-07-04

Full detail: `milestones/v1.5.0-ROADMAP.md` · Audit: `milestones/v1.5.0-MILESTONE-AUDIT.md`

</details>

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
| 34. Async Metadata | v1.5.0 | 3/3 | Complete    | 2026-07-04 |
| 35. Async Prepared Statements | v1.5.0 | 3/3 | Complete    | 2026-07-04 |
| 22-28. Async API | v1.4.0 | 29/29 | Complete | 2026-07-01 |
| 21.1. ADBC dispatch URI-positional fix | v1.3.0 | 3/3 | Complete | 2026-05-20 |
| 21. Quack Backend | v1.3.0 | 3/3 | Complete | 2026-05-19 |
| 16-20. Plugin/Extensibility API | v1.2.0 | 17/17 | Complete | 2026-03-15 |
| 1-15. MVP + Backend Expansion | v1.0.0 | 51/51 | Complete | 2026-03-07 |
