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

## Milestone: v1.2.0 — Plugin/Extensibility API

**Shipped:** 2026-03-15
**Phases:** 6 | **Plans:** 17

### What Was Built
- Self-describing config classes with `to_adbc_kwargs()`, `_driver_path()`, `_dbapi_module()` on all 12 backends
- Registry-free architecture — `create_pool()` calls config methods directly
- Overloaded `create_pool(driver_path=...)` and `create_pool(dbapi_module=...)` for raw driver usage
- WarehouseConfig Protocol as the third-party integration contract
- Custom backends guide with Protocol reference documentation
- Semi-integration tests for all 12 backends with conditional mock targets

### What Worked
- Architectural pivot (registry → self-describing configs) mid-milestone produced a simpler, better design than the original plan
- Phase 17.5 insertion for translator consolidation before registry removal meant each subsequent phase built on clean foundations
- Direct method implementation pattern for `to_adbc_kwargs()` scaled cleanly across all 12 backends once Snowflake reference was established
- Milestone audit caught the DOC-03 gap, which was then closed by Phase 20 gap closure
- ABC enforcement on BaseWarehouseConfig catches missing implementations at instantiation rather than at pool creation time

### What Was Inefficient
- Registry was built in Phase 17, then entirely deleted in Phase 18 — the pivot was correct but the registry work was throwaway
- Original requirements (REG-*, EP-*, DOC-01/02) were largely invalidated — 12 of 13 requirements superseded by the architectural change
- Phase numbering required correction mid-milestone (originally 01-04, renumbered to 16-20 for monotonic sequencing across milestones)

### Patterns Established
- Protocol-based contract over registry/plugin systems — simpler for both library and third-party authors
- `_create_pool_impl()` shared helper pattern for multi-overload functions
- ABC with `_driver_path()` and `to_adbc_kwargs()` as abstract methods on BaseWarehouseConfig
- Gap closure phases from milestone audit as standard practice

### Key Lessons
1. Build the simple thing first (self-describing configs) rather than the complex thing (plugin registry) — the registry was unnecessary complexity
2. When requirements become stale mid-milestone due to an architectural pivot, supersede them explicitly rather than forcing completion
3. Monotonic phase numbering across milestones (don't restart at 01) prevents confusion in commit messages and planning documents
4. `to_adbc_kwargs()` as a method on each config class is better than external translator functions — keeps translation logic with the data it operates on

### Cost Observations
- Model mix: primarily opus for planning/execution, sonnet for research, haiku for quick tasks
- 107 commits over 4 days
- Notable: 4-day milestone vs 13-day v1.0.0 — patterns from v1.0.0 made v1.2.0 execution highly efficient

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0.0 | 15 | 51 | Full GSD workflow: research → plan → execute → verify → audit |
| v1.2.0 | 6 | 17 | Architectural pivot mid-milestone; gap closure from audit |

### Cumulative Quality

| Milestone | Tests | Backends | Requirements |
|-----------|-------|----------|-------------|
| v1.0.0 | 192 | 12 | 66/66 |
| v1.2.0 | 241 | 12 | 1/13 satisfied, 12/13 superseded |

### Top Lessons (Verified Across Milestones)

1. Audit before archiving — catches gaps that phase-level verification misses (confirmed v1.0.0 + v1.2.0)
2. Establish patterns early, then replicate mechanically — translator consolidation scaled to all 12 backends (confirmed v1.0.0 + v1.2.0)
3. Build the simplest solution that works — registry was unnecessary complexity, self-describing configs are better (v1.2.0)
