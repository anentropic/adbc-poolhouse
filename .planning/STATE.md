---
gsd_state_version: 1.0
milestone: v1.3.0
milestone_name: Quack Backend
status: shipped
stopped_at: v1.3.0 shipped (Phases 21 + 21.1 complete); preparing v1.3.1 patch — Databricks catalog/schema fix
last_updated: "2026-06-24T20:40:59.998Z"
last_activity: 2026-06-24 -- Quick task 260624-u45: Databricks catalog/schema fix (v1.3.1 prep)
progress:
  total_phases: 2
  completed_phases: 2
  total_plans: 6
  completed_plans: 6
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-19)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 21.1 — adbc-dispatch-uri-positional-fix

## Current Position

Phase: 21.1 (adbc-dispatch-uri-positional-fix) — EXECUTING
Plan: 1 of 3
Status: Executing Phase 21.1
Last activity: 2026-05-19 -- Phase 21.1 execution started

## Accumulated Context

### Decisions

All v1.0.0–v1.2.0 decisions recorded in PROJECT.md Key Decisions table.

v1.3.0 roadmap decisions:

- Single combined Phase 21 (config + tests + docs) rather than splitting into separate implementation and documentation phases — follows v1.0.0 retrospective lesson "Every new backend should update all three doc surfaces in the same plan, not as a separate phase"
- Phase numbering continues from v1.2.0's Phase 20 (monotonic across milestones, per v1.2.0 lesson)
- Mirrors single-phase backend pattern of Phase 10 (SQLite) and Phase 12 (ClickHouse) from v1.0.0

### Roadmap Evolution

- 20 phases completed across v1.0.0 and v1.2.0 milestones
- v1.2.0 underwent architectural pivot: registry → self-describing configs
- v1.3.0 follows established phase-per-backend pattern — single combined phase for the small Quack surface
- Phase 21.1 inserted after Phase 21: ADBC dispatch URI-positional fix (URGENT) — /ultrareview surfaced a `TypeError` in `_driver_api.create_adbc_connection` that breaks `create_pool(QuackConfig(...))` and latently also `create_pool(PostgreSQLConfig(...))` and `create_pool(FlightSQLConfig(...))` when their PyPI drivers are installed; closes the Phase 21 QUACK-08 verification gap and fixes pre-existing bugs from v1.0.0

### Blockers/Concerns

None — adbc-driver-quack is alpha (v0.1.0-alpha.1); document alpha status and pin lower bound carefully.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 10 | Rewrite integration tests to use pool API and wire up conftest fixtures | 2026-03-07 | 7721866 | Verified | [10-rewrite-integration-tests-to-use-pool-ap](./quick/10-rewrite-integration-tests-to-use-pool-ap/) |
| 260624-u45 | Fix DatabricksConfig dropping catalog/schema in to_adbc_kwargs (DBX-02 follow-up) | 2026-06-24 | f72517b | Verified | [260624-u45-databricks-catalog-schema](./quick/260624-u45-databricks-catalog-schema/) |

## Session Continuity

Last session: 2026-06-24
Stopped at: v1.3.0 shipped; Databricks catalog/schema fix landed on branch gsd/quick-260624-databricks-catalog-schema — preparing v1.3.1 patch release
Next step: finalize v1.3.1 (version bump + changelog), then open PR / tag
