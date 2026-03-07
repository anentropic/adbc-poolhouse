---
phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests
plan: 05
subsystem: testing
tags: [snowflake, cassette, adbc-replay, integration-tests, dotenv]

# Dependency graph
requires:
  - phase: 15-04
    provides: "Env var isolation autouse fixture; per-warehouse dotenv loading"
  - phase: 15-03
    provides: "pytest-adbc-replay plugin with cassette recording/replay"
provides:
  - "6 real Snowflake cassette files for CI replay without credentials"
  - "Unified .env loading across all integration tests"
  - "Complete cassette-based integration test suite (4 tests, 2 warehouses)"
affects: [ci, snowflake, databricks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "db_kwargs= parameter passing for adbc_driver_snowflake.dbapi.connect()"
    - "Single .env file for all warehouse credentials (replaces per-warehouse .env.* files)"

key-files:
  created:
    - tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_query.sql
    - tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_result.arrow
    - tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_params.json
    - tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_query.sql
    - tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_result.arrow
    - tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_params.json
  modified:
    - tests/integration/test_snowflake.py
    - tests/integration/test_databricks.py
    - tests/integration/conftest.py

key-decisions:
  - "Unified .env file replaces per-warehouse .env.snowflake/.env.databricks files"
  - "Snowflake connect() must use db_kwargs= named parameter (not **kwargs spreading) for compatibility with pytest-adbc-replay plugin interception"

patterns-established:
  - "db_kwargs= passing: ADBC Snowflake driver.connect(db_kwargs={...}) ensures plugin interception correctly forwards connection parameters to the real driver during recording"

requirements-completed: []

# Metrics
duration: 9min
completed: 2026-03-07
---

# Phase 15 Plan 05: Record Snowflake Cassettes Summary

**Real Snowflake cassettes recorded from live connection; 4 integration tests (Snowflake + Databricks) replay in CI without credentials; 192 tests pass**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-07T11:13:44Z
- **Completed:** 2026-03-07T11:23:10Z
- **Tasks:** 2 (1 human-action checkpoint + 1 auto)
- **Files modified:** 9

## Accomplishments
- Recorded 6 real Snowflake cassette files from a live Snowflake connection, replacing synthetic ones removed in commit 6333ade
- Unified dotenv loading to use a single `.env` file for all warehouse credentials instead of per-warehouse `.env.snowflake` / `.env.databricks`
- Fixed Snowflake connect() kwargs passing to work correctly with pytest-adbc-replay plugin interception
- Full test suite passes: 192 tests (188 unit + 4 integration) with 0 failures

## Task Commits

Each task was committed atomically:

1. **Task 1: User provides Snowflake credentials** - human-action checkpoint (no commit)
2. **Task 2: Record Snowflake cassettes and verify full test suite** - `bb81d8e` (feat)

## Files Created/Modified
- `tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_query.sql` - Normalized SQL: `SELECT 1`
- `tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_result.arrow` - Arrow IPC: 1 row, column `1` = Decimal('1')
- `tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_params.json` - null params
- `tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_query.sql` - Normalized SQL: `SELECT 1 AS n, 'hello' AS s`
- `tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_result.arrow` - Arrow IPC: 1 row, N=Decimal('1'), S='hello'
- `tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_params.json` - null params
- `tests/integration/test_snowflake.py` - Updated dotenv path (.env), renamed helper to `_snowflake_db_kwargs()`, use `db_kwargs=` parameter
- `tests/integration/test_databricks.py` - Updated dotenv path (.env), updated docstrings
- `tests/integration/conftest.py` - Updated both pool fixtures to load from `.env`

## Decisions Made
- **Unified .env file:** User chose to use a single `.env` file for all warehouse credentials instead of per-warehouse files. Updated all integration tests and conftest fixtures accordingly.
- **db_kwargs= parameter passing:** The `adbc_driver_snowflake.dbapi.connect()` function requires translated config to be passed as `db_kwargs={...}` (named parameter), not spread as `**kwargs`. The pytest-adbc-replay plugin's `_patched_connect(**kwargs)` intercepts the call and passes `dict(kwargs)` to `ReplayConnection.__init__`, which then calls `connect_fn(**db_kwargs)`. Using `connect(db_kwargs=translated)` ensures the kwargs nest correctly through this chain: plugin receives `{'db_kwargs': {...}}`, re-spreads as `connect_fn(db_kwargs={...})`, and the Snowflake driver correctly routes the dict to `adbc_driver_snowflake.connect(db_kwargs=...)`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Snowflake connect() kwargs passing**
- **Found during:** Task 2 (Recording cassettes)
- **Issue:** Test called `adbc_driver_snowflake.dbapi.connect(**translated_config)` which spread ADBC-specific keys (e.g., `adbc.snowflake.sql.account`) as `**kwargs`. The Snowflake driver passes `**kwargs` to the DBAPI Connection wrapper, not to database init, causing "account is empty" errors.
- **Fix:** Changed to `connect(db_kwargs=translated_config)` so the Snowflake driver correctly passes the config dict to `adbc_driver_snowflake.connect(db_kwargs=...)`.
- **Files modified:** `tests/integration/test_snowflake.py`
- **Verification:** Both tests pass in record mode and replay mode
- **Committed in:** bb81d8e (Task 2 commit)

**2. [Rule 3 - Blocking] Updated dotenv paths from per-warehouse to unified .env**
- **Found during:** Task 2 (Pre-recording setup)
- **Issue:** Tests referenced `.env.snowflake` and `.env.databricks` but user populated credentials in a single `.env` file
- **Fix:** Updated all `load_dotenv()` calls and docstrings to reference `.env`
- **Files modified:** `tests/integration/test_snowflake.py`, `tests/integration/test_databricks.py`, `tests/integration/conftest.py`
- **Verification:** Recording succeeds, all tests pass
- **Committed in:** bb81d8e (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for correct operation. The kwargs bug would have prevented recording entirely. The dotenv path change was directed by user preference. No scope creep.

## Issues Encountered
- Pre-commit `end-of-file-fixer` hook added trailing newlines to `000_params.json` files on first attempt. Re-staged and committed successfully on second attempt.

## Auth Gates
- **Task 1 (human-action):** User provided Snowflake credentials in `.env` file. Resolved before continuation.

## User Setup Required
None - cassette files are committed to git. CI replay requires no credentials.

## Next Phase Readiness
- Phase 15 is now fully complete: all 5 plans executed
- All integration tests (Snowflake + Databricks) are cassette-based and CI-safe
- pytest-adbc-replay plugin handles recording and replay transparently
- No blockers for future phases

## Self-Check: PASSED

- 6/6 cassette files: FOUND
- Commit bb81d8e: FOUND
- 15-05-SUMMARY.md: FOUND

---
*Phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests*
*Completed: 2026-03-07*
