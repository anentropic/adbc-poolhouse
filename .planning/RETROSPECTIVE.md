# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0.0 — MVP + Backend Expansion

**Shipped:** 2026-03-07
**Phases:** 15 | **Plans:** 51

### What Was Built
- Typed config + translation layer for 12 ADBC warehouses
- `create_pool()` / `close_pool()` / `managed_pool()` public API
- Lazy driver detection for PyPI and Foundry backends
- Complete documentation site with per-warehouse guides
- PyPI publication via OIDC trusted publisher
- VCR-style integration tests via pytest-adbc-replay cassettes

### What Worked
- Phase-per-backend pattern made adding SQLite, MySQL, and ClickHouse mechanical after the first 9 warehouses
- URI-first decomposed-field fallback pattern established in Databricks fix (Phase 9) cleanly reused for MySQL and ClickHouse
- docs-author skill + CLAUDE.md quality gate kept documentation current from Phase 7 onwards without separate doc phases
- Audit → gap closure → re-audit cycle (Phases 13-14) caught integration gaps that phases missed individually
- pytest-adbc-replay cassettes replaced fragile syrupy snapshots with deterministic, CI-safe replay

### What Was Inefficient
- Phase 6 (Snowflake syrupy snapshots) was built then entirely replaced by Phase 15 (cassette replay) — could have skipped syrupy
- Requirements numbering split (v0.1 + v1.1) within a single milestone created confusion — a single flat list would have been cleaner
- Three doc surfaces per backend (warehouse guide, configuration.md table, index.md listing) were easy to miss — human checkpoints caught gaps but it took two extra phases (13-14) to close them all
- PROJECT.md had stale milestone header ("v1.1.0") that didn't match the actual milestone version ("v1.0")

### Patterns Established
- URI-first with decomposed-field fallback for all non-trivial config classes
- Per-backend phase structure: config + translator → wiring → tests → docs
- docs-author skill as quality gate in CLAUDE.md for all phases ≥ 7
- `dbc install --pre` flag for alpha Foundry drivers (ClickHouse)
- `monkeypatch.delenv` over `os.environ.pop` for test env var cleanup

### Key Lessons
1. Build the test infrastructure you actually need first — syrupy was a detour that got replaced
2. Audit before milestone completion catches integration gaps that per-phase verification misses
3. Every new backend should update all three doc surfaces in the same plan, not as a separate phase
4. Open lower bounds only (no `<Y` caps) prevented all dependency conflicts reported by consumers

### Cost Observations
- Model mix: primarily opus for planning/execution, sonnet for research, haiku for quick tasks
- 267 commits over 13 days
- Notable: backend expansion phases (10-12) were highly mechanical after patterns established in phases 3-5

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0.0 | 15 | 51 | Full GSD workflow: research → plan → execute → verify → audit |

### Cumulative Quality

| Milestone | Tests | Backends | Requirements |
|-----------|-------|----------|-------------|
| v1.0.0 | 192 | 12 | 66/66 |

### Top Lessons (Verified Across Milestones)

1. Audit before archiving — catches gaps that phase-level verification misses
2. Establish patterns early, then replicate mechanically for each new backend
