# Roadmap: adbc-poolhouse

## Milestones

- v1.2.0 **Plugin/Extensibility API** — Phases 16-19 (planned)
- v1.0.0 **MVP + Backend Expansion** — Phases 1-15 (shipped 2026-03-07)

## Phases

<details>
<summary>v1.2.0 Plugin/Extensibility API (Phases 16-19) — PLANNED</summary>

- [x] Phase 16: Driver Import Semi-Integration Tests (2/2 plans) — completed 2026-03-12

  **Goal:** All 12 backend semi-integration tests pass with real driver imports and mocked connections.

  **Requirements:** TEST-01, TEST-02, TEST-03, TEST-04

  Plans:
  - [x] 16-01-PLAN.md — Create tests/imports/ with 12 backend test classes
  - [x] 16-02-PLAN.md — Add install-all-drivers justfile recipe

- [x] Phase 17: Registry Infrastructure (2/2 plans) — completed 2026-03-12

  **Goal:** Backend registry replaces hardcoded isinstance dispatch, enabling runtime registration of new backends.

  **Requirements:** REG-01, REG-02, REG-03, TEST-INFRA-01 (REG-04 deferred)

  Plans:
  - [x] 17-01-PLAN.md — Create registry core + exceptions + test infrastructure
  - [x] 17-02-PLAN.md — Integrate registry with translators/drivers + export APIs

- [x] Phase 17.5: Translator Consolidation (5/5 plans) — completed 2026-03-14

  **Goal:** All 12 config classes have to_adbc_kwargs() method using Pydantic aliases and serializers. Registry stores driver_path only. All existing tests pass.

  **Requirements:** Refactor for plugin interface consistency

  Plans:
  - [x] 17.5-01-PLAN.md — Protocol + Snowflake reference implementation
  - [x] 17.5-02-PLAN.md — DuckDB, BigQuery, SQLite, ClickHouse implementations
  - [x] 17.5-03-PLAN.md — FlightSQL, MSSQL, Trino implementations
  - [x] 17.5-04-PLAN.md — PostgreSQL, MySQL, Databricks, Redshift implementations
  - [x] 17.5-05-PLAN.md — Registry cleanup and driver updates

- [x] Phase 18: Registration Removal (3/3 plans) — completed 2026-03-15

  **Goal:** Make config classes fully self-describing so the backend registry is unnecessary. Each config carries its driver path, kwargs translation, dbapi module, and entrypoint. `create_pool()` calls config methods directly — no registry lookup, no lazy registration, no `_drivers.py` dispatch layer. Delete all registry machinery.

  **Requirements:** Refactor for plugin interface self-description

  Plans:
  - [x] 18-01-PLAN.md — Protocol/ABC evolution + shared driver helper + 12 config implementations
  - [x] 18-02-PLAN.md — Rewrite create_pool() + delete registry/drivers + clean exports
  - [x] 18-03-PLAN.md — Rewrite tests for registry-free architecture

- [ ] Phase 19: Raw create_pool Overload (2/4 plans) (gap closure in progress)

  **Goal:** Add overloaded create_pool() and managed_pool() signatures that accept raw driver args directly (driver_path or dbapi_module), bypassing config objects. Clean up hardcoded driver lists in _driver_api.py.

  **Requirements:** RAW-01, RAW-02, RAW-03, RAW-04, RAW-05, RAW-06, RAW-07, RAW-08, RAW-09, RAW-10

  **Plans:** 4 plans

  Plans:
  - [x] 19-01-PLAN.md — Core implementation: driver cleanup + overloads + unit tests
  - [x] 19-02-PLAN.md — Integration test + documentation
  - [ ] 19-03-PLAN.md — Gap closure: fix dbapi_module connect() signature dispatch
  - [ ] 19-04-PLAN.md — Gap closure: rewrite pool lifecycle guide

</details>

<details>
<summary>v1.0.0 MVP + Backend Expansion (Phases 1-15) — SHIPPED 2026-03-07</summary>

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

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 16. Driver Import Semi-Integration Tests | v1.2.0 | 2/2 | Complete | 2026-03-12 |
| 17. Registry Infrastructure | v1.2.0 | 2/2 | Complete | 2026-03-12 |
| 17.5. Translator Consolidation | v1.2.0 | 5/5 | Complete | 2026-03-14 |
| 18. Registration Removal | v1.2.0 | 3/3 | Complete | 2026-03-15 |
| 19. Raw create_pool Overload | 4/4 | Complete    | 2026-03-15 | - |
|-------|-----------|----------------|--------|-----------|
| 1. Pre-flight Fixes | v1.0.0 | 1/1 | Complete | 2026-02-23 |
| 2. Dependency Declarations | v1.0.0 | 2/2 | Complete | 2026-02-23 |
| 3. Config Layer | v1.0.0 | 7/7 | Complete | 2026-02-24 |
| 4. Translation and Driver Detection | v1.0.0 | 5/5 | Complete | 2026-02-24 |
| 5. Pool Factory and DuckDB Integration | v1.0.0 | 2/2 | Complete | 2026-02-24 |
| 6. Snowflake Integration | v1.0.0 | 1/1 | Complete | 2026-02-24 |
| 7. Documentation and PyPI Publication | v1.0.0 | 5/5 | Complete | 2026-02-27 |
| 8. Review and Improve Docs | v1.0.0 | 6/6 | Complete | 2026-02-28 |
| 9. Infrastructure and Databricks Fix | v1.0.0 | 2/2 | Complete | 2026-03-01 |
| 10. SQLite Backend | v1.0.0 | 4/4 | Complete | 2026-03-01 |
| 11. Foundry Tooling and MySQL Backend | v1.0.0 | 4/4 | Complete | 2026-03-01 |
| 12. ClickHouse Backend | v1.0.0 | 4/4 | Complete | 2026-03-02 |
| 13. Verification and Tracking Fix | v1.0.0 | 2/2 | Complete | 2026-03-02 |
| 14. Homepage Discovery Fix | v1.0.0 | 1/1 | Complete | 2026-03-02 |
| 15. Replace Syrupy with pytest-adbc-replay | v1.0.0 | 5/5 | Complete | 2026-03-07 |
