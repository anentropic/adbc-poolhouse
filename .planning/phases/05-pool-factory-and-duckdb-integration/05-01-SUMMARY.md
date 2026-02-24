---
phase: 05-pool-factory-and-duckdb-integration
plan: "01"
subsystem: config
tags: [exceptions, pydantic, validation, duckdb, adbc]

# Dependency graph
requires:
  - phase: 03-config-layer
    provides: BaseWarehouseConfig, DuckDBConfig, WarehouseConfig Protocol
provides:
  - PoolhouseError base exception class in _exceptions.py
  - ConfigurationError dual-inherit (PoolhouseError + ValueError) in _exceptions.py
  - _adbc_entrypoint() method signature on WarehouseConfig Protocol
  - _adbc_entrypoint() concrete method on BaseWarehouseConfig returning None
  - DuckDBConfig._adbc_entrypoint() override returning 'duckdb_adbc_init'
  - Five bounds validators on DuckDBConfig (pool_size, max_overflow, timeout, recycle, database)
  - ConfigurationError replacing bare ValueError in DuckDBConfig validators
affects:
  - 05-02-pool-factory (consumes ConfigurationError, _adbc_entrypoint)
  - 05-03+ (all pool factory tests, public exports)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ConfigurationError dual-inherits PoolhouseError+ValueError for pydantic model_validator compatibility"
    - "_adbc_entrypoint() method on base/Protocol with DuckDB override pattern"
    - "field_validator per-field bounds checking before model_validator cross-field checks"

key-files:
  created:
    - src/adbc_poolhouse/_exceptions.py
  modified:
    - src/adbc_poolhouse/_base_config.py
    - src/adbc_poolhouse/_duckdb_config.py

key-decisions:
  - "ConfigurationError inherits from both PoolhouseError and ValueError — pydantic wraps it in ValidationError which itself inherits ValueError, preserving raises ValueError test expectations"
  - "_adbc_entrypoint() is a concrete (non-abstract) method on BaseWarehouseConfig returning None — only DuckDB overrides it; other drivers have no explicit entry point"
  - "ConfigurationError import in _duckdb_config.py uses # noqa: TC001 — runtime import required inside validators, not TYPE_CHECKING block"
  - "field_validators added before model_validator — bounds checked per-field before cross-field :memory:+pool_size check runs"

patterns-established:
  - "Library error hierarchy: PoolhouseError -> specific errors; consumers use except PoolhouseError to catch all library errors"
  - "Driver entry point override pattern: base returns None, DuckDB returns 'duckdb_adbc_init', future drivers override as needed"
  - "Bounds validators with value in error message: 'pool_size must be > 0, got -1' for debuggability"

requirements-completed: [POOL-05, TEST-02]

# Metrics
duration: 2min
completed: 2026-02-24
---

# Phase 5 Plan 01: Exception Hierarchy and Config Foundation Summary

**PoolhouseError/ConfigurationError exception hierarchy + _adbc_entrypoint() on WarehouseConfig + five DuckDBConfig bounds validators using ConfigurationError**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-24T23:30:23Z
- **Completed:** 2026-02-24T23:32:36Z
- **Tasks:** 3
- **Files modified:** 3 (1 created, 2 updated)

## Accomplishments
- Created `_exceptions.py` with PoolhouseError base and ConfigurationError dual-inherit exception hierarchy
- Added `_adbc_entrypoint()` to WarehouseConfig Protocol and BaseWarehouseConfig (returns None by default)
- Updated DuckDBConfig with five bounds validators, ConfigurationError usage, and `_adbc_entrypoint()` override returning `'duckdb_adbc_init'`

## Task Commits

Each task was committed atomically:

1. **Task 1: Create exception hierarchy (_exceptions.py)** - `4f99ecc` (feat)
2. **Task 2: Add _adbc_entrypoint to BaseWarehouseConfig and WarehouseConfig Protocol** - `8354d0f` (feat)
3. **Task 3: Update DuckDBConfig with ConfigurationError, _adbc_entrypoint, and bounds validators** - `62e531c` (feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified
- `src/adbc_poolhouse/_exceptions.py` - New: PoolhouseError base exception + ConfigurationError(PoolhouseError, ValueError)
- `src/adbc_poolhouse/_base_config.py` - Added _adbc_entrypoint() to WarehouseConfig Protocol and BaseWarehouseConfig
- `src/adbc_poolhouse/_duckdb_config.py` - Five bounds field_validators + ConfigurationError + _adbc_entrypoint() override

## Decisions Made
- ConfigurationError inherits from both PoolhouseError and ValueError so pydantic wraps it in ValidationError (which itself inherits ValueError), preserving existing test expectations that raise ValidationError
- _adbc_entrypoint() is concrete (not abstract) on BaseWarehouseConfig — returns None as the safe default; only DuckDB needs to override it
- ConfigurationError import uses `# noqa: TC001` because it is used at runtime inside field_validators, not TYPE_CHECKING block
- field_validators run before model_validator — per-field bounds checks fire before the cross-field `:memory:` + `pool_size > 1` check

## Deviations from Plan

None - plan executed exactly as written.

One minor deviation: ruff format reformatted `_duckdb_config.py` after initial write (a long line in `validate_database` was auto-collapsed). Fixed immediately before commit; all checks passed.

## Issues Encountered
None — prek hooks passed cleanly on all three commits.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `_exceptions.py` ready for Plan 02 to export `PoolhouseError` and `ConfigurationError` publicly
- `_adbc_entrypoint()` ready for pool factory (Plan 02) to call `config._adbc_entrypoint()` for DuckDB driver resolution
- DuckDBConfig bounds validators ensure clean input before pool creation
- All 70 existing tests remain green after changes

---
*Phase: 05-pool-factory-and-duckdb-integration*
*Completed: 2026-02-24*

## Self-Check: PASSED

- FOUND: src/adbc_poolhouse/_exceptions.py
- FOUND: src/adbc_poolhouse/_base_config.py
- FOUND: src/adbc_poolhouse/_duckdb_config.py
- FOUND: .planning/phases/05-pool-factory-and-duckdb-integration/05-01-SUMMARY.md
- FOUND: 4f99ecc (Task 1 commit)
- FOUND: 8354d0f (Task 2 commit)
- FOUND: 62e531c (Task 3 commit)
