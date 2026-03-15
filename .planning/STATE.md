---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: milestone
status: completed
stopped_at: Completed 19-03-PLAN.md
last_updated: "2026-03-15T21:43:13.528Z"
last_activity: 2026-03-15 — Completed Plan 19-04 (Pool Lifecycle Guide Rewrite)
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-07)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Milestone v1.2.0 — Plugin/Extensibility API (IN PROGRESS)

## Current Position

Milestone: v1.2.0 — Plugin/Extensibility API (IN PROGRESS)
Phase: 19-raw-create-pool (Plan 4/4 complete -- PHASE COMPLETE)
Status: Phase 19 complete (including gap closure plans 03, 04)
Last activity: 2026-03-15 — Completed Plan 19-04 (Pool Lifecycle Guide Rewrite)

Progress: [██████████] 100% (4/4 plans complete)

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
All decisions from v1.0.0 have been reviewed and marked with outcomes.

**Phase 16 decisions:**
- Install PyPI drivers in single uv pip command for efficiency — Reduces installation time and ensures atomic installation of all PyPI extras together
- Install Foundry drivers one at a time (dbc doesn't support multiple args) — dbc CLI documentation doesn't confirm support for multiple package arguments, so separate calls ensure reliability
- ClickHouse requires --pre flag (only alpha version published) — Only alpha version v0.1.0-alpha.1 is currently published on PyPI, requiring --pre flag for installation

**Plan 16-01 decisions:**
- PyPI drivers use conditional mock target: driver's own dbapi.connect when installed, adbc_driver_manager.dbapi.connect when not
- All 12 backend tests must pass - no skipping for missing drivers
- [Phase 16]: PyPI drivers use conditional mock target based on driver installation status — When driver is installed, mock its own dbapi.connect; when not installed, fall back to adbc_driver_manager.dbapi.connect

**Phase 17 decisions:**
- Use module-level dicts for registry storage (simple, no external deps)
- Dual lookup: _registry (name → data) and _config_to_name (config_class → name)
- Lazy registration via _lazy_registrations dict for built-in backends
- Runtime validation of config_class and translator
- Registry-based dispatch replacing isinstance chains in translate_config() and resolve_driver()
- Driver path resolved at registration time (not deferred)
- clean_registry fixture for test isolation when mocking importlib.util.find_spec

**Phase 17.5 Plan 01 decisions:**
- Direct method implementation (not model_dump aliases) for Snowflake to_adbc_kwargs() -- complex field-to-key mappings make aliases impractical
- Transitional fallback in translate_config() to registry get_translator() for unmigrated backends -- prevents regressions while migrating one backend at a time

**Phase 17.5 Plan 02 decisions:**
- Direct method implementation for all 4 simple backends (no model_dump aliases) -- field-to-key mappings too divergent for alias approach

**Phase 17.5 Plan 03 decisions:**
- Direct method implementation for all 3 boolean-default backends (FlightSQL, MSSQL, Trino) -- follows established pattern from plans 01/02

**Phase 17.5 Plan 04 decisions:**
- Direct method implementation for all 4 URI-construction backends -- follows established pattern from plans 01-03
- Redshift _build_uri() as private method to keep to_adbc_kwargs() readable -- mirrors translator module's helper pattern

**Phase 17.5 Plan 05 decisions:**
- Removed TranslatorFunc type alias and get_translator() entirely rather than deprecating -- both are internal symbols not exported from __init__.py
- Removed transitional fallback in translate_config() since all 12 backends have to_adbc_kwargs()

**Phase 18 Plan 03 decisions:**
- Parametrized Foundry _dbapi_module() test covers all 6 backends in one test
- DummyConfig removed from conftest -- no longer needed without registry

**Phase 18 Plan 02 decisions:**
- EAFP approach for create_pool(): no TypeError raise, AttributeError is the natural error for configs missing methods
- Deleted _registry.py and _drivers.py entirely, no backwards compat shim (both internal modules)
- Rewrote test_drivers.py to test config._driver_path() directly instead of resolve_driver()

**Phase 18 Plan 01 decisions:**
- BaseWarehouseConfig uses formal ABC (not NotImplementedError defaults) for _driver_path() and to_adbc_kwargs() -- catches missing implementations at instantiation time
- _resolve_driver_path() uses pkg.__dict__[method_name]() to avoid false matches from inherited attrs
- Tasks 1 and 2 committed atomically since ABC enforcement requires implementations to coexist for type checking
- [Phase 18]: BaseWarehouseConfig uses formal ABC for _driver_path() and to_adbc_kwargs()

**Phase 19 Plan 01 decisions:**
- _create_pool_impl() shared helper avoids overload forwarding issues between managed_pool() and create_pool()
- Mutual exclusivity check (driver_path vs dbapi_module) placed first in _create_pool_impl for early fail
- Empty string passed as driver_path for dbapi_module path (unused by create_adbc_connection when dbapi_module is set)
- TDD RED+GREEN combined in single commit due to basedpyright pre-commit hook blocking type-invalid test code
- [Phase 19-raw-create-pool]: _create_pool_impl() shared helper avoids overload forwarding issues between managed_pool() and create_pool()

**Phase 19 Plan 02 decisions:**
- type: ignore[reportMissingTypeStubs] for adbc_driver_duckdb import in integration test (no type stubs published)
- [Phase 19]: TDD RED+GREEN combined in single commit due to basedpyright pre-commit hook blocking type-invalid test code
- [Phase 19]: Semi-integration tests updated to assert config keys instead of db_kwargs presence (mock signature differs from real function)

### Roadmap Evolution

- 15 phases completed across v1.0.0 milestone
- Phase 6 (syrupy) superseded by Phase 15 (pytest-adbc-replay cassettes)
- Gap closure phases (13-14) added after milestone audit
- v1.2.0 phases renumbered: Phase 16 (Driver Import Tests) inserted, Registry Infrastructure → Phase 17, Entry Point Discovery → Phase 18, Plugin Author Documentation → Phase 19
- Phase 17.5 (Translator Consolidation) inserted after Phase 17 (2026-03-14) — Required before Entry Point Discovery to consolidate translator interface for plugin consistency
- v1.2.0 phases corrected to monotonic numbering (2026-03-14): phases 1-4 → 16-19, continuing from v1.0.0's last phase (15)

### Blockers/Concerns

None — execution proceeding normally.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 10 | Rewrite integration tests to use pool API and wire up conftest fixtures | 2026-03-07 | 7721866 | Verified | [10-rewrite-integration-tests-to-use-pool-ap](./quick/10-rewrite-integration-tests-to-use-pool-ap/) |

## Session Continuity

Last session: 2026-03-15T21:25:09.264Z
Stopped at: Completed 19-03-PLAN.md
Next step: Phase 19 gap closure complete. All UAT documentation issues resolved.
