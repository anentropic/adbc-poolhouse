# Roadmap: adbc-poolhouse

## Milestones

- v1.2.0 **Plugin/Extensibility API** — Phases 1-4 (planned)
- v1.0.0 **MVP + Backend Expansion** — Phases 1-15 (shipped 2026-03-07)

## Phases

<details>
<summary>v1.2.0 Plugin/Extensibility API (Phases 1-4) — PLANNED</summary>

- [x] Phase 1: Driver Import Semi-Integration Tests (2/2 plans) — completed 2026-03-12

  **Goal:** All 12 backend semi-integration tests pass with real driver imports and mocked connections.

  **Requirements:** TEST-01, TEST-02, TEST-03, TEST-04

  Plans:
  - [x] 01-01-PLAN.md — Create tests/imports/ with 12 backend test classes
  - [x] 01-02-PLAN.md — Add install-all-drivers justfile recipe

- [x] Phase 2: Registry Infrastructure (2/2 plans) — completed 2026-03-12

  **Goal:** Backend registry replaces hardcoded isinstance dispatch, enabling runtime registration of new backends.

  **Requirements:** REG-01, REG-02, REG-03, TEST-INFRA-01 (REG-04 deferred)

  Plans:
  - [x] 02-01-PLAN.md — Create registry core + exceptions + test infrastructure
  - [x] 02-02-PLAN.md — Integrate registry with translators/drivers + export APIs

- [ ] Phase 3: Entry Point Discovery (0/2 plans)
- [ ] Phase 4: Plugin Author Documentation (0/2 plans)

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
| 1. Driver Import Semi-Integration Tests | v1.2.0 | 2/2 | Complete | 2026-03-12 |
| 2. Registry Infrastructure | v1.2.0 | 2/2 | Complete | 2026-03-12 |
| 3. Entry Point Discovery | v1.2.0 | 0/2 | Not started | - |
| 4. Plugin Author Documentation | v1.2.0 | 0/2 | Not started | - |
|-------|-----------|----------------|--------|-----------|
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
