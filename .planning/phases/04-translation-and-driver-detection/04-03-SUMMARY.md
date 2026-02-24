---
phase: 04-translation-and-driver-detection
plan: "03"
subsystem: database
tags: [adbc, driver-detection, importlib, type-aliases]

# Dependency graph
requires:
  - phase: 04-01
    provides: "4 PyPI translator functions (DuckDB, PostgreSQL, BigQuery, FlightSQL)"
  - phase: 04-02
    provides: "6 Foundry translator functions (Snowflake + Databricks, Redshift, Trino, MSSQL, Teradata)"
provides:
  - "translate_config() dispatch coordinator over all 10 warehouse translators"
  - "resolve_driver() 3-path detection (find_spec / manifest / ImportError)"
  - "create_adbc_connection() ADBC facade with NOT_FOUND catch-and-reraise (DRIV-03)"
  - "AdbcCreatorFn type alias for Phase 5 pool assembly"
affects:
  - phase-05-pool-assembly
  - phase-07-foundry-drivers

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "WarehouseConfig Protocol import deferred to TYPE_CHECKING (TC001) in dispatcher modules"
    - "All ADBC type: ignore suppressions concentrated in _driver_api.py and _pool_types.py only"
    - "Foundry drivers use short name pass-through (no find_spec); PyPI drivers use find_spec + _driver_path()"
    - "DuckDB uses find_spec('_duckdb') C extension; immediate ImportError on miss (no manifest fallback)"
    - "adbc_driver_manager.Error.status_code == AdbcStatusCode.NOT_FOUND for reliable NOT_FOUND detection"

key-files:
  created:
    - src/adbc_poolhouse/_translators.py
    - src/adbc_poolhouse/_drivers.py
    - src/adbc_poolhouse/_driver_api.py
    - src/adbc_poolhouse/_pool_types.py
  modified: []

key-decisions:
  - "WarehouseConfig Protocol import uses TYPE_CHECKING block in _translators.py and _drivers.py — ruff TC001 correctly flags runtime Protocol import when isinstance dispatch uses concrete subclasses, not Protocol itself"
  - "adbc_driver_manager.Error.status_code compared to AdbcStatusCode.NOT_FOUND (int-enum 3) — more reliable than string matching; also kept 'NOT_FOUND' in str(exc) as secondary fallback for forward compatibility"
  - "create_adbc_connection uses explicit keyword args (entrypoint=, db_kwargs=) with type: ignore rather than **kwargs spread — basedpyright cannot infer dict[str, object] assignment to typed overload parameters"
  - "_PYPI_PACKAGES and _FOUNDRY_DRIVERS dicts in _drivers.py imported by _driver_api.py for NOT_FOUND error message construction — avoids duplicating driver name mappings"

patterns-established:
  - "Phase 4 wiring pattern: dispatch coordinator (_translators.py) + resolver (_drivers.py) + facade (_driver_api.py) + type aliases (_pool_types.py)"
  - "All ADBC suppressions in one file (_driver_api.py) — easy to audit, grep shows all ADBC type workarounds in one place"

requirements-completed: [DRIV-01, DRIV-02, DRIV-03, DRIV-04, TYPE-01, TYPE-02]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 4 Plan 03: Translation and Driver Detection Wiring Summary

**Four-module wiring layer: translate_config() dispatcher, resolve_driver() 3-path detection, create_adbc_connection() ADBC facade with NOT_FOUND reraise, and AdbcCreatorFn type alias**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T12:28:01Z
- **Completed:** 2026-02-24T12:32:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `translate_config()` dispatches all 10 warehouse configs to their per-warehouse translators via isinstance checks; raises TypeError for unknown types
- `resolve_driver()` implements 3-path detection: DuckDB via `find_spec("_duckdb")`, PyPI drivers via `find_spec` + `_driver_path()` with manifest fallback, Foundry drivers via short name pass-through
- `create_adbc_connection()` concentrates all ADBC type: ignore suppressions and catches `adbc_driver_manager.Error` with `status_code == NOT_FOUND`, re-raising as `ImportError` with `https://docs.adbc-drivers.org/` URL
- `AdbcCreatorFn = Callable[[], Connection]` type alias established for Phase 5 QueuePool assembly

## Task Commits

Each task was committed atomically:

1. **Task 1: Translator coordinator** - `47b5bdc` (feat)
2. **Task 2: Driver detection, ADBC facade, type scaffold** - `02c7f5a` (feat)

**Plan metadata:** (pending — this commit)

## Files Created/Modified

- `src/adbc_poolhouse/_translators.py` - translate_config() dispatch over all 10 warehouse translator functions
- `src/adbc_poolhouse/_drivers.py` - resolve_driver() 3-path detection; _PYPI_PACKAGES and _FOUNDRY_DRIVERS dicts
- `src/adbc_poolhouse/_driver_api.py` - create_adbc_connection() ADBC facade; all type: ignore; NOT_FOUND catch-and-reraise
- `src/adbc_poolhouse/_pool_types.py` - AdbcCreatorFn type alias for Phase 5

## Decisions Made

- **WarehouseConfig Protocol in TYPE_CHECKING blocks:** `_translators.py` and `_drivers.py` use `WarehouseConfig` only as a function annotation — with `from __future__ import annotations`, the Protocol is not needed at runtime. ruff TC001 correctly flags it; moved to TYPE_CHECKING block. Concrete config classes (used in isinstance) remain at module level.

- **NOT_FOUND detection via status_code:** `adbc_driver_manager.Error` has a `status_code: AdbcStatusCode` attribute (confirmed by inspection). Comparing `exc.status_code == AdbcStatusCode.NOT_FOUND` is more reliable than string matching. Kept `"NOT_FOUND" in str(exc)` as a secondary fallback. Actual exception type is `ProgrammingError` (inherits `DatabaseError` inherits `Error`); catching `Error` is sufficient.

- **Explicit connect kwargs instead of ** spread:** `create_adbc_connection` calls `adbc_driver_manager.dbapi.connect(driver_path, entrypoint=entrypoint, db_kwargs=kwargs)` with explicit keyword args rather than `**connect_kwargs: dict[str, object]`. basedpyright cannot match `object` values to the typed overload parameters; explicit args with `type: ignore[arg-type]` is cleaner than suppressing the entire call.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] WarehouseConfig Protocol moved to TYPE_CHECKING in _translators.py**
- **Found during:** Task 1 commit (prek/ruff hook)
- **Issue:** ruff TC001 flagged runtime import of `WarehouseConfig` Protocol — with `from __future__ import annotations` active, the Protocol annotation is only needed at type-check time, not runtime
- **Fix:** Added `TYPE_CHECKING` block and moved `WarehouseConfig` import inside it; concrete config classes (needed for isinstance) remain at module level
- **Files modified:** src/adbc_poolhouse/_translators.py
- **Verification:** prek passes, translate_config() still works correctly
- **Committed in:** `47b5bdc` (Task 1 commit, second attempt)

**2. [Rule 1 - Bug] basedpyright error: dict[str, object] not assignable to connect() typed params**
- **Found during:** Task 2 commit (prek/basedpyright hook)
- **Issue:** `connect_kwargs: dict[str, object]` spread via `**connect_kwargs` caused 5 basedpyright errors — `object` is not assignable to `str | None`, `Dict[str, str | Path]`, etc.
- **Fix:** Replaced `**connect_kwargs` spread with explicit `entrypoint=entrypoint, db_kwargs=kwargs` keyword args; added `# type: ignore[arg-type]` on each argument
- **Files modified:** src/adbc_poolhouse/_driver_api.py
- **Verification:** prek passes with zero violations
- **Committed in:** `02c7f5a` (Task 2 commit, second attempt)

**3. [Rule 1 - Bug] ruff/format auto-fixed 9 style issues in Task 2 files**
- **Found during:** Task 2 first commit attempt (prek hooks)
- **Issue:** ruff auto-fixed 9 errors (including `Callable` import from `collections.abc` instead of `typing` in _pool_types.py) and reformatted 2 files
- **Fix:** Re-staged auto-fixed files and committed on second attempt
- **Files modified:** src/adbc_poolhouse/_drivers.py, src/adbc_poolhouse/_pool_types.py
- **Verification:** prek passes cleanly on second commit
- **Committed in:** `02c7f5a` (Task 2 commit, second attempt)

---

**Total deviations:** 3 auto-fixed (all Rule 1 — linting/type enforcement)
**Impact on plan:** All fixes required by prek hooks (ruff + basedpyright). No scope creep.

## Issues Encountered

- `adbc_driver_manager.Error` exception subclass hierarchy confirmed by live inspection: `ProgrammingError → DatabaseError → Error → Exception`. The `status_code` attribute on `Error` holds an `AdbcStatusCode` int-enum; `NOT_FOUND == 3` confirmed by running `print(adbc_driver_manager.AdbcStatusCode.NOT_FOUND)`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 4 wiring layer complete — all four modules ready for Phase 5 to call `translate_config()` and `resolve_driver()`
- Phase 5 `create_pool()` can use `AdbcCreatorFn` type alias from `_pool_types.py`
- Foundry driver discovery mechanism (Phase 7) still needs research against actual `adbc_driver_manager` manifest search paths

---
*Phase: 04-translation-and-driver-detection*
*Completed: 2026-02-24*
