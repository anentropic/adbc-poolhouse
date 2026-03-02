---
phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests
plan: 01
subsystem: testing
tags: [pytest, pytest-adbc-replay, cassettes, syrupy, dependencies]

requires:
  - phase: 14-homepage-discovery-fix
    provides: Phase 14 complete; stable pyproject.toml baseline

provides:
  - pytest-adbc-replay installed and configured as test infrastructure
  - adbc_auto_patch configured for both driver modules
  - adbc_cassette_dir set to tests/cassettes
  - Credential gate (addopts snowflake) removed from CI

affects: [15-02, 15-03]

tech-stack:
  added: [pytest-adbc-replay==1.0.0a1, sqlglot==29.0.1, adbc-driver-snowflake==1.10.0]
  patterns:
    - "cassette-based integration tests: tests/cassettes/{name}/{driver}/000_{query,result,params}"
    - "adbc_driver_manager.dbapi.connect() uses driver= keyword arg for pytest-adbc-replay compatibility"

key-files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock
    - .gitignore
    - src/adbc_poolhouse/_driver_api.py

key-decisions:
  - "pytest-adbc-replay 1.0.0a1: _patched_connect accepts **kwargs only, requiring driver= keyword arg in _driver_api.py (not positional)"
  - "adbc-driver-snowflake added to dev deps: auto-patch silently skips uninstalled drivers; driver must be present for test collection and replay"
  - "addopts snowflake gate removed: cassette tests run in CI by default in replay mode (none)"

patterns-established:
  - "Cassette file naming: {prefix}_query.sql, {prefix}_result.arrow, {prefix}_params.json"
  - "SQL stored as sqlglot-normalized form: sqlglot.parse_one(sql).sql(pretty=True, normalize=True)"

requirements-completed: []

duration: 8min
completed: 2026-03-02
---

# Phase 15 Plan 01: Dependency Swap and Pytest Config Summary

**syrupy replaced by pytest-adbc-replay with adbc_auto_patch for both driver modules; addopts credential gate removed so cassette tests run in CI by default**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-02T21:51:43Z
- **Completed:** 2026-03-02T22:00:00Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Removed `syrupy>=4.0` from dev dependencies; added `pytest-adbc-replay` and `adbc-driver-snowflake>=1.0.0`
- Updated `[tool.pytest.ini_options]` with `adbc_auto_patch`, `adbc_cassette_dir`, updated markers, no `addopts` gate
- Extended `.gitignore` with `.env.databricks` / `*.env.databricks` credential exclusion
- Fixed `_driver_api.py` to use `driver=driver_path` keyword arg for pytest-adbc-replay compatibility

## Task Commits

1. **Task 1: Swap syrupy for pytest-adbc-replay and update pytest config** - `74b4845` (feat — combined with wave 2 content due to pre-commit blocking)

## Files Created/Modified

- `pyproject.toml` - syrupy removed, pytest-adbc-replay + adbc-driver-snowflake added, pytest ini_options updated
- `uv.lock` - lock file updated with new dependency resolution
- `.gitignore` - Databricks credential exclusion added
- `src/adbc_poolhouse/_driver_api.py` - driver= keyword arg fix for pytest-adbc-replay compatibility

## Decisions Made

- **pytest-adbc-replay _patched_connect() accepts **kwargs only:** The plugin patches `connect()` with a function that only accepts keyword args. Calling it with a positional `driver_path` causes TypeError. Fixed by using `driver=driver_path` in `_driver_api.py` — no behavioral change to the ADBC call itself.
- **adbc-driver-snowflake in dev deps:** The plugin silently skips uninstalled drivers in `adbc_auto_patch`; it does NOT inject mock modules. For auto-patch and replay to work in CI, the driver must be installed.
- **All three plans committed together:** basedpyright pre-commit hook checks all project files, not just staged files. Syrupy removal broke the old conftest.py type-check. Plans 15-02 and 15-03 had to be executed before any commit could go through.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pytest-adbc-replay _patched_connect() rejects positional args**
- **Found during:** Task 1 verification (unit test run)
- **Issue:** `adbc_driver_manager.dbapi.connect(driver_path, ...)` called with positional arg; plugin patches `connect()` to `_patched_connect(**kwargs)` which raises TypeError on positional args even for non-cassette pass-through
- **Fix:** Changed `_driver_api.py` to use `driver=driver_path` keyword arg
- **Files modified:** `src/adbc_poolhouse/_driver_api.py`
- **Verification:** 188 unit tests pass after fix
- **Committed in:** 74b4845

**2. [Rule 3 - Blocking] Pre-commit blocks commit: basedpyright checks all files**
- **Found during:** First commit attempt
- **Issue:** basedpyright runs on all project files including `tests/integration/conftest.py` and `test_snowflake.py` which still had syrupy imports (now unresolvable). Wave boundary could not be preserved.
- **Fix:** Executed Plans 15-02 and 15-03 content before committing Plan 15-01's changes
- **Files modified:** All Wave 2 files (conftest.py, test_snowflake.py, test_databricks.py, tests/cassettes/)
- **Verification:** All pre-commit hooks pass, 192 tests green
- **Committed in:** 74b4845

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for correctness. Wave boundary violated due to pre-commit constraints but all plan objectives met.

## Issues Encountered

None beyond the auto-fixed deviations above.

## Next Phase Readiness

- pytest-adbc-replay configured and operational
- All cassette infrastructure in place
- 192 tests passing (188 unit + 4 integration)
- Plans 15-02 and 15-03 content executed as part of this plan's commit

---
*Phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests*
*Completed: 2026-03-02*
