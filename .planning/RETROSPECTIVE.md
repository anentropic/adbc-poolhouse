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

## Milestone: v1.4.0 — Async API

**Shipped:** 2026-07-01
**Phases:** 7 (22-28) | **Plans:** 29

### What Was Built
- Optional async API behind an `[async]` extra — `create_async_pool`/`managed_async_pool`/`close_async_pool` + `AsyncPool`/`AsyncConnection`/`AsyncCursor` for all 13 backends
- Thread-offload over the unchanged sync core via a single `anyio.to_thread.run_sync` chokepoint with a dedicated per-pool `CapacityLimiter`
- Cooperative cancellation (`adbc_cancel` + shielded invalidate) that never poisons the pool, identical under asyncio and trio
- Zero-cost sync path (PEP 562 lazy import; sync suite green with anyio absent) and basedpyright-strict async typing
- Dual-backend (asyncio/trio × DuckDB/Snowflake cassette) test matrix + Arrow-stability and limiter-stress proofs

### What Worked
- Front-loading a feasibility spike (Phase 22) to measure GIL release BEFORE building — set honest concurrency claims and gated the milestone
- Building the deterministic test harness (Phase 23) before the code it exercises — event-gating/virtual-clock over real sleeps kept the EDGE suite fast and non-flaky
- Isolating cancellation as its own phase (25) — the #1 industry-wide async-DB leak risk got focused design and explicit no-leak assertions
- Enforcing async hygiene (no asyncio, no bare `to_thread`) with AST guards co-located with the behaviour they test
- Linux CI as the real cross-platform gate — the documented "passes on macOS, hangs on Linux" race class

### What Was Inefficient
- ROADMAP checkboxes for 26-03/26-04 drifted out of sync (work done, boxes unchecked) because this build's gsd-tools lacks the mutation handlers — hand reconciliation at close
- Two verifications + one UAT sat in `human_needed`/`testing` waiting on a CI observation that had already gone green — the close had to discharge them manually
- Nyquist VALIDATION.md files mostly left `draft`/non-compliant despite the work being done — validation formalization lagged execution

### Patterns Established
- Feasibility spike as a gating Phase-0 for any milestone resting on an unproven premise
- Deterministic async test harness (blocking stub + virtual clock + AST hygiene guards) before the async code
- Single offload chokepoint + dedicated per-pool limiter as the concurrency-bounding pattern
- Cancellation-invalidates-never-returns-busy as the pool-safety invariant
- Optional feature behind an extra + PEP 562 lazy import for zero-cost-to-non-users surfaces

### Key Lessons
1. Measure the premise before building on it — the spike turned a MEDIUM-confidence GIL assumption into honest, documented concurrency claims
2. For async correctness, Linux CI is the gate, not local loops — macOS can hide lost-wakeup/cancel races
3. Keep tracking artifacts (ROADMAP checkboxes, VALIDATION status) in sync as you go; reconciling at close is avoidable friction

### Cost Observations
- Model mix: primarily opus for planning/execution and cancellation design; sonnet for research/harness
- 190 commits over 6 days
- Notable: the hardest correctness work (cancellation, limiter, trio/asyncio parity) concentrated in Phases 24-25; docs + packaging were comparatively mechanical

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0.0 | 15 | 51 | Full GSD workflow: research → plan → execute → verify → audit |
| v1.2.0 | 6 | 17 | Architectural pivot mid-milestone; gap closure from audit |
| v1.4.0 | 7 | 29 | Feasibility-spike gate + deterministic async harness before code; Linux CI as async gate |

### Cumulative Quality

| Milestone | Tests | Backends | Requirements |
|-----------|-------|----------|-------------|
| v1.0.0 | 192 | 12 | 66/66 |
| v1.2.0 | 241 | 12 | 1/13 satisfied, 12/13 superseded |
| v1.4.0 | 433 | 13 (async for all) | 63/63 |

### Top Lessons (Verified Across Milestones)

1. Audit before archiving — catches gaps that phase-level verification misses (confirmed v1.0.0 + v1.2.0)
2. Establish patterns early, then replicate mechanically — translator consolidation scaled to all 12 backends (confirmed v1.0.0 + v1.2.0)
3. Build the simplest solution that works — registry was unnecessary complexity, self-describing configs are better (v1.2.0)
