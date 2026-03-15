---
phase: 18-registration-removal
plan: 02
subsystem: pool-factory
tags: [create_pool, registry-deletion, drivers-deletion, exceptions-cleanup, EAFP]

# Dependency graph
requires:
  - phase: 18-registration-removal
    plan: 01
    provides: _driver_path() and _dbapi_module() on all 12 config classes
provides:
  - create_pool() calling config._driver_path() and config._dbapi_module() directly
  - Clean __init__.py without registry symbols
  - Simplified _exceptions.py with only PoolhouseError and ConfigurationError
  - Deleted _registry.py and _drivers.py
affects: [18-03, test-suite, public-api]

# Tech tracking
tech-stack:
  added: []
  patterns: [direct-config-method-calls, EAFP-error-handling]

key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_pool_factory.py
    - src/adbc_poolhouse/__init__.py
    - src/adbc_poolhouse/_exceptions.py
    - tests/test_drivers.py
    - tests/conftest.py
  deleted:
    - src/adbc_poolhouse/_registry.py
    - src/adbc_poolhouse/_drivers.py
    - tests/test_registry.py

key-decisions:
  - "EAFP approach for create_pool(): no TypeError raise, AttributeError is the natural error for configs missing methods"
  - "Deleted _registry.py and _drivers.py entirely, no backwards compat shim"
  - "Rewrote test_drivers.py to test config._driver_path() directly instead of resolve_driver()"

patterns-established:
  - "Direct method dispatch: create_pool() calls config._driver_path(), config._dbapi_module() with zero indirection"
  - "No global mutable state: driver resolution happens in config instance methods, not module-level dicts"

requirements-completed: [REG-DELETE, POOL-INLINE]

# Metrics
duration: 6min
completed: 2026-03-15
---

# Phase 18 Plan 02: Inline create_pool and Delete Registry Summary

**create_pool() calls config methods directly; _registry.py, _drivers.py deleted; 217 tests pass with zero registry references**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-15T08:49:56Z
- **Completed:** 2026-03-15T08:55:33Z
- **Tasks:** 2
- **Files modified/deleted:** 8

## Accomplishments
- Rewrote create_pool() to call config._driver_path() and config._dbapi_module() directly, eliminating the resolve_driver/resolve_dbapi_module dispatch layer
- Deleted _registry.py (register_backend, ensure_registered, lazy registration closures) and _drivers.py (resolve_driver, resolve_dbapi_module, _PYPI_PACKAGES dict)
- Removed 4 registry symbols from __init__.py: register_backend, RegistryError, BackendAlreadyRegisteredError, BackendNotRegisteredError
- Removed 3 exception classes from _exceptions.py (RegistryError hierarchy)
- Rewrote test_drivers.py to test config._driver_path() and config._dbapi_module() directly
- Deleted test_registry.py and removed clean_registry/dummy_backend/dummy_translator from conftest.py
- All 217 tests pass, basedpyright clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite create_pool() to call config methods directly** - `a8766e1` (feat)
2. **Task 2: Delete registry/drivers modules and clean exports** - `c2751de` (feat)

## Files Created/Modified
- `src/adbc_poolhouse/_pool_factory.py` - create_pool() calls config._driver_path(), config._dbapi_module() directly; removed _drivers import; updated module docstring
- `src/adbc_poolhouse/__init__.py` - Removed register_backend import, removed RegistryError/BackendAlreadyRegisteredError/BackendNotRegisteredError from imports and __all__
- `src/adbc_poolhouse/_exceptions.py` - Removed RegistryError, BackendAlreadyRegisteredError, BackendNotRegisteredError classes
- `src/adbc_poolhouse/_registry.py` - DELETED
- `src/adbc_poolhouse/_drivers.py` - DELETED
- `tests/test_drivers.py` - Rewrote to test config._driver_path() and config._dbapi_module() instead of resolve_driver()
- `tests/test_registry.py` - DELETED (all tests were for deleted registry code)
- `tests/conftest.py` - Removed clean_registry fixture, dummy_backend fixture, dummy_translator function

## Decisions Made
- Used EAFP approach for create_pool(): removed TypeError from Raises docstring. If a config lacks _driver_path(), Python raises AttributeError naturally. This matches the 3P-CONTRACT design from Phase 18 context.
- Deleted _registry.py and _drivers.py entirely with no backwards compat shim -- both are internal modules (underscore prefix, never in __all__).
- Rewrote test_drivers.py to test config._driver_path() directly. DuckDB tests now mock find_spec for "adbc_driver_duckdb" (matching the _resolve_driver_path helper) instead of the old "find_spec('_duckdb')" pattern.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed test imports referencing deleted modules**
- **Found during:** Task 2
- **Issue:** test_registry.py imports from _registry, test_drivers.py imports resolve_driver from _drivers, conftest.py references _registry internals -- all of which were deleted
- **Fix:** Deleted test_registry.py entirely, rewrote test_drivers.py to test config._driver_path() and config._dbapi_module() directly, removed clean_registry/dummy_backend/dummy_translator from conftest.py
- **Files modified:** tests/test_drivers.py, tests/conftest.py; tests/test_registry.py deleted
- **Verification:** uv run pytest -x -q passes with 217 tests, basedpyright clean
- **Committed in:** c2751de

**2. [Rule 1 - Bug] Construct config before patching builtins.__import__**
- **Found during:** Task 2 (test rewrite)
- **Issue:** DuckDB and Snowflake "path 1 found" tests patched builtins.__import__ globally, which broke pydantic-settings BaseSettings.__init__ (it imports AliasChoices at init time)
- **Fix:** Moved config construction before the mock context managers so pydantic imports are not intercepted
- **Files modified:** tests/test_drivers.py
- **Verification:** Both tests pass
- **Committed in:** c2751de

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes were direct consequences of deleting the registry/drivers modules. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- create_pool() now calls config methods directly with zero indirection
- No registry state, no lazy registration, no dispatch tables remain
- Ready for Plan 03: test cleanup and verification
- 217 tests pass (down from 227 due to deleted registry tests, up with new _driver_path/_dbapi_module tests)

## Self-Check: PASSED

- All 5 modified files exist on disk
- All 3 deleted files confirmed absent
- Commit a8766e1 exists in git log
- Commit c2751de exists in git log
- 217 tests pass
- basedpyright reports 0 errors

---
*Phase: 18-registration-removal*
*Completed: 2026-03-15*
