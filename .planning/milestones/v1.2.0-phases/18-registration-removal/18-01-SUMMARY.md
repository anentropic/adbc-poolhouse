---
phase: 18-registration-removal
plan: 01
subsystem: config
tags: [abc, protocol, driver-resolution, pydantic-settings, importlib]

# Dependency graph
requires:
  - phase: 17.5-translator-consolidation
    provides: to_adbc_kwargs() on all 12 config classes
provides:
  - _driver_path() method on all 12 config classes
  - _dbapi_module() method on all 12 config classes
  - _resolve_driver_path() shared static helper on BaseWarehouseConfig
  - WarehouseConfig Protocol with _driver_path() and _dbapi_module()
  - BaseWarehouseConfig as ABC with abstract _driver_path() and to_adbc_kwargs()
affects: [18-02, 18-03, create_pool-rewrite, registry-deletion]

# Tech tracking
tech-stack:
  added: [abc.ABC, abc.abstractmethod]
  patterns: [self-describing-configs, shared-driver-resolution-helper]

key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_base_config.py
    - src/adbc_poolhouse/_duckdb_config.py
    - src/adbc_poolhouse/_snowflake_config.py
    - src/adbc_poolhouse/_bigquery_config.py
    - src/adbc_poolhouse/_postgresql_config.py
    - src/adbc_poolhouse/_flightsql_config.py
    - src/adbc_poolhouse/_sqlite_config.py
    - src/adbc_poolhouse/_databricks_config.py
    - src/adbc_poolhouse/_redshift_config.py
    - src/adbc_poolhouse/_trino_config.py
    - src/adbc_poolhouse/_mssql_config.py
    - src/adbc_poolhouse/_mysql_config.py
    - src/adbc_poolhouse/_clickhouse_config.py
    - tests/conftest.py
    - tests/test_base_config.py

key-decisions:
  - "BaseWarehouseConfig uses formal ABC (not NotImplementedError defaults) for _driver_path() and to_adbc_kwargs()"
  - "_resolve_driver_path() uses pkg.__dict__[method_name]() to avoid false matches from inherited attrs"
  - "Tasks 1 and 2 committed atomically since ABC enforcement requires implementations to coexist"

patterns-established:
  - "Self-describing configs: each config carries its own driver resolution via _driver_path()"
  - "Shared driver helper: _resolve_driver_path(pkg_name, method_name) on BaseWarehouseConfig"
  - "PyPI driver dbapi: find_spec check before returning dbapi module name"
  - "Foundry driver path: static string return (no find_spec needed)"

requirements-completed: [SELF-DESC, PROTOCOL-UPDATE, 3P-CONTRACT]

# Metrics
duration: 5min
completed: 2026-03-15
---

# Phase 18 Plan 01: Self-Describing Configs Summary

**ABC-based BaseWarehouseConfig with _driver_path() and _dbapi_module() on all 12 config classes, enabling registry-free driver resolution**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-15T08:41:21Z
- **Completed:** 2026-03-15T08:46:30Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Converted BaseWarehouseConfig to formal ABC with abstract _driver_path() and to_adbc_kwargs()
- Added _resolve_driver_path() shared static helper handling both _driver_path() and driver_path() naming conventions
- All 12 config classes now carry their own driver resolution logic
- Updated WarehouseConfig Protocol with _driver_path() and _dbapi_module() for third-party config contract
- All 227 tests pass, basedpyright clean

## Task Commits

Tasks 1 and 2 committed atomically (ABC requires implementations to coexist for type checking):

1. **Tasks 1+2: ABC evolution + all 12 config implementations** - `765bf52` (feat)

## Files Created/Modified
- `src/adbc_poolhouse/_base_config.py` - ABC base class, _resolve_driver_path() helper, Protocol updates
- `src/adbc_poolhouse/_duckdb_config.py` - _driver_path() with method_name="driver_path"
- `src/adbc_poolhouse/_snowflake_config.py` - _driver_path() + _dbapi_module() with find_spec
- `src/adbc_poolhouse/_bigquery_config.py` - _driver_path() + _dbapi_module() with find_spec
- `src/adbc_poolhouse/_postgresql_config.py` - _driver_path() + _dbapi_module() with find_spec
- `src/adbc_poolhouse/_flightsql_config.py` - _driver_path() + _dbapi_module() with find_spec
- `src/adbc_poolhouse/_sqlite_config.py` - _driver_path() (no dbapi, incompatible signature)
- `src/adbc_poolhouse/_databricks_config.py` - _driver_path() returns "databricks"
- `src/adbc_poolhouse/_redshift_config.py` - _driver_path() returns "redshift"
- `src/adbc_poolhouse/_trino_config.py` - _driver_path() returns "trino"
- `src/adbc_poolhouse/_mssql_config.py` - _driver_path() returns "mssql"
- `src/adbc_poolhouse/_mysql_config.py` - _driver_path() returns "mysql"
- `src/adbc_poolhouse/_clickhouse_config.py` - _driver_path() returns "clickhouse"
- `tests/conftest.py` - DummyConfig updated with _driver_path() and to_adbc_kwargs()
- `tests/test_base_config.py` - Tests updated for ABC (cannot instantiate, abstract method checks)

## Decisions Made
- Used formal ABC with @abstractmethod rather than NotImplementedError defaults. ABC catches missing implementations at instantiation time, which is better developer experience.
- Used pkg.__dict__[method_name]() in _resolve_driver_path() rather than getattr() to avoid false matches from inherited attributes (per research recommendation).
- Committed Tasks 1 and 2 atomically because the type checker (basedpyright) requires abstract method implementations to exist when the ABC is defined. Separate commits would fail pre-commit hooks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated DummyConfig in conftest.py for ABC compatibility**
- **Found during:** Task 1+2 (pre-commit type check)
- **Issue:** DummyConfig subclasses BaseWarehouseConfig but didn't implement _driver_path() or to_adbc_kwargs(), causing basedpyright "Cannot instantiate abstract class" errors
- **Fix:** Added _driver_path() returning "dummy" and to_adbc_kwargs() returning dummy dict
- **Files modified:** tests/conftest.py
- **Verification:** basedpyright passes, all tests pass
- **Committed in:** 765bf52

**2. [Rule 3 - Blocking] Updated test_base_config.py for ABC compatibility**
- **Found during:** Task 1+2 (pre-commit type check)
- **Issue:** Test tried to instantiate BaseWarehouseConfig() directly, which now raises TypeError (ABC). Also Protocol tests didn't cover new methods.
- **Fix:** Replaced NotImplementedError test with ABC instantiation test. Added Protocol tests for _driver_path and _dbapi_module. Updated ConcreteConfig in test to implement all required methods.
- **Files modified:** tests/test_base_config.py
- **Verification:** All tests pass including new ABC and Protocol tests
- **Committed in:** 765bf52

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both fixes were direct consequences of the ABC conversion. No scope creep.

## Issues Encountered
None - implementation matched research and plan specifications exactly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 12 configs are self-describing with _driver_path() and _dbapi_module()
- Ready for Plan 02: inline driver resolution into create_pool() and delete _registry.py/_drivers.py
- Registry and drivers modules still exist and function (no behavioral change yet)

## Self-Check: PASSED

- All 15 modified files exist on disk
- Commit 765bf52 exists in git log
- 227 tests pass
- basedpyright reports 0 errors

---
*Phase: 18-registration-removal*
*Completed: 2026-03-15*
