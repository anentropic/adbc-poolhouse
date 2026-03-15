---
phase: 19-raw-create-pool
plan: 01
subsystem: api
tags: [typing-overload, pool-factory, adbc, sqlalchemy-queuepool]

# Dependency graph
requires:
  - phase: 18-registration-removal
    provides: EAFP-based create_pool() with config methods, no registry
provides:
  - Overloaded create_pool() with 3 call patterns (config, driver_path, dbapi_module)
  - Overloaded managed_pool() with 3 call patterns
  - _create_pool_impl() shared implementation helper
  - Simplified NOT_FOUND error in _driver_api.py
affects: [19-02-docs, plugin-documentation]

# Tech tracking
tech-stack:
  added: []
  patterns: [typing.overload with basedpyright strict, shared _impl helper for overload dispatch]

key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_pool_factory.py
    - src/adbc_poolhouse/_driver_api.py
    - tests/test_pool_factory.py
    - tests/test_drivers.py

key-decisions:
  - "_create_pool_impl() shared helper avoids overload forwarding issues between managed_pool() and create_pool()"
  - "Mutual exclusivity check (driver_path vs dbapi_module) placed first in _create_pool_impl for early fail"
  - "Empty string passed as driver_path for dbapi_module path (unused by create_adbc_connection when dbapi_module is set)"
  - "TDD RED+GREEN combined in single commit due to basedpyright pre-commit hook blocking type-invalid test code"

patterns-established:
  - "Overload pattern: 3 @overload stubs (config positional, driver_path keyword-only, dbapi_module keyword-only) + implementation with all-None defaults"
  - "Context manager overload return type: contextlib.AbstractContextManager[T] in stubs, Iterator[T] in implementation"

requirements-completed: [RAW-01, RAW-02, RAW-03, RAW-04, RAW-05, RAW-06, RAW-07, RAW-08]

# Metrics
duration: 5min
completed: 2026-03-15
---

# Phase 19 Plan 01: Raw create_pool Overload Summary

**Overloaded create_pool()/managed_pool() with 3 call patterns (config, driver_path, dbapi_module) and simplified NOT_FOUND error**

## Performance

- **Duration:** 4m 35s
- **Started:** 2026-03-15T12:10:06Z
- **Completed:** 2026-03-15T12:14:41Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Removed redundant `_foundry_name_to_install` dict and generalized NOT_FOUND error message
- Added `_create_pool_impl()` shared helper with 3-way dispatch (config/driver_path/dbapi_module)
- Added 3 `@overload` stubs each for `create_pool()` and `managed_pool()` -- all type-checked by basedpyright strict
- Added 10 new unit tests covering raw driver_path, raw dbapi_module, managed_pool raw variants, and 5 TypeError edge cases

## Task Commits

Each task was committed atomically:

1. **Task 1: Clean up _driver_api.py** - `7ebb332` (fix)
2. **Task 2: Add overloaded create_pool() and managed_pool()** - `7a234c6` (feat, TDD RED+GREEN)
3. **Task 3: Add unit tests for raw paths and errors** - `e279936` (test)

## Files Created/Modified
- `src/adbc_poolhouse/_driver_api.py` - Removed `_foundry_name_to_install`, simplified NOT_FOUND error message
- `src/adbc_poolhouse/_pool_factory.py` - Added `_create_pool_impl()`, 3 overloads for `create_pool()`, 3 overloads for `managed_pool()`
- `tests/test_pool_factory.py` - Added TestRawDriverPath, TestRawDbApiModule, TestManagedPoolRaw, TestRawCreatePoolErrors
- `tests/test_drivers.py` - Renamed and updated NOT_FOUND test to match new generic error format

## Decisions Made
- `_create_pool_impl()` shared helper chosen to avoid overload forwarding issues between `managed_pool()` and `create_pool()` (basedpyright overload resolution complaint)
- Mutual exclusivity check placed first in `_create_pool_impl()` for early fail before any config extraction
- Empty string `""` passed as `driver_path` for dbapi_module path (unused by `create_adbc_connection` when `dbapi_module` is set)
- TDD RED and GREEN phases combined in single commit because basedpyright pre-commit hook prevents committing type-invalid test code

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- basedpyright pre-commit hook blocks commits with type errors, preventing separate TDD RED commits for overload tests. Combined RED+GREEN into single commit for Task 2.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All overloaded signatures ready for documentation in Plan 02
- Docstrings have brief descriptions of three call patterns; full Google-style rewrite deferred to Plan 02
- All 237 tests green, basedpyright strict: 0 errors

## Self-Check: PASSED

- FOUND: 19-01-SUMMARY.md
- FOUND: 7ebb332 (Task 1)
- FOUND: 7a234c6 (Task 2)
- FOUND: e279936 (Task 3)
- FOUND: all 4 modified files

---
*Phase: 19-raw-create-pool*
*Completed: 2026-03-15*
