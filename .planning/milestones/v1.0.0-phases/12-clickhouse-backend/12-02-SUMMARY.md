---
phase: 12-clickhouse-backend
plan: "02"
subsystem: database
tags: [clickhouse, adbc, foundry, driver-registration, wiring]

# Dependency graph
requires:
  - phase: 12-clickhouse-backend
    plan: "01"
    provides: ClickHouseConfig and translate_clickhouse() domain objects
provides:
  - ClickHouseConfig registered in _FOUNDRY_DRIVERS dict (src/adbc_poolhouse/_drivers.py)
  - translate_clickhouse() dispatch branch in translate_config() (src/adbc_poolhouse/_translators.py)
  - ClickHouseConfig public export in __init__.py and __all__
affects: [12-03, 12-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Foundry driver wiring pattern: module-level import + _FOUNDRY_DRIVERS dict entry (alphabetical)"
    - "Translator dispatcher pattern: isinstance branch inserted alphabetically between existing backends"
    - "__all__ wiring: import + __all__ string entry added in alphabetical position"

key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_drivers.py
    - src/adbc_poolhouse/_translators.py
    - src/adbc_poolhouse/__init__.py

key-decisions:
  - "ClickHouseConfig placed alphabetically first in _FOUNDRY_DRIVERS (before DatabricksConfig)"
  - "Translator dispatch branch inserted between BigQuery and Databricks (alphabetical within the function)"
  - "ruff auto-sorted the import to BigQueryConfig -> ClickHouseConfig -> DatabricksConfig in _drivers.py on first pre-commit run"

patterns-established:
  - "New Foundry backend wiring requires exactly three file changes: _drivers.py (_FOUNDRY_DRIVERS), _translators.py (dispatch), __init__.py (export)"

requirements-completed: [CH-03]

# Metrics
duration: 2min
completed: 2026-03-02
---

# Phase 12 Plan 02: ClickHouseConfig Wiring Summary

**ClickHouseConfig wired into _FOUNDRY_DRIVERS, translate_config() dispatcher, and public __init__.py API — create_pool(ClickHouseConfig(...)) now routes correctly end-to-end**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-02T09:54:21Z
- **Completed:** 2026-03-02T09:56:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- ClickHouseConfig imported at module level in _drivers.py and registered as `("clickhouse", "clickhouse")` in _FOUNDRY_DRIVERS — resolve_driver() now returns "clickhouse" for ClickHouseConfig instances without calling find_spec
- translate_config() dispatch branch added between BigQuery and Databricks — ClickHouseConfig instances route to translate_clickhouse()
- ClickHouseConfig importable from adbc_poolhouse package and present in __all__ — public API complete
- Full test suite: 184 passed, 0 regressions; mkdocs build --strict passes

## Task Commits

Each task was committed atomically:

1. **Task 1: Register ClickHouseConfig in _drivers.py** - `f5b7276` (feat)
2. **Task 2: Add translate_clickhouse dispatch and __init__.py export** - `1243db3` (feat)

## Files Created/Modified

- `src/adbc_poolhouse/_drivers.py` - Added module-level ClickHouseConfig import and _FOUNDRY_DRIVERS entry
- `src/adbc_poolhouse/_translators.py` - Added ClickHouseConfig + translate_clickhouse imports and isinstance dispatch branch
- `src/adbc_poolhouse/__init__.py` - Added ClickHouseConfig import and __all__ entry

## Decisions Made

- ClickHouseConfig sorted alphabetically first in `_FOUNDRY_DRIVERS` (C before D/M/R/T)
- Dispatcher branch inserted between BigQuery and Databricks (consistent alphabetical ordering within the function)
- ruff re-sorted imports alphabetically on pre-commit — BigQueryConfig -> ClickHouseConfig -> DatabricksConfig in _drivers.py; this is the correct final order

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- First commit attempt failed pre-commit: ruff auto-sorted the new ClickHouseConfig import into the correct alphabetical position (after BigQueryConfig, before DatabricksConfig) and fixed one implicit E501 issue. Re-staged after auto-fix and second commit succeeded cleanly.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All three wiring points complete; Plan 12-03 can add driver detection and pool factory tests
- Plan 12-04 can add the ClickHouse warehouse guide and update configuration.md

---
*Phase: 12-clickhouse-backend*
*Completed: 2026-03-02*
