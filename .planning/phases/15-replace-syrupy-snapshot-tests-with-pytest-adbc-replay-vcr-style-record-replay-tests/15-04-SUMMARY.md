---
phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests
plan: 04
subsystem: testing
tags: [pytest, pydantic-settings, env-vars, dotenv, monkeypatch, conftest]

# Dependency graph
requires:
  - phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests
    provides: cassette-based integration tests (15-03)
provides:
  - autouse fixture clearing all 13 warehouse env prefixes before each test
  - per-warehouse dotenv file loading in integration tests (.env.snowflake, .env.databricks)
affects: [integration-tests, unit-tests, ci]

# Tech tracking
tech-stack:
  added: []
  patterns: [autouse-env-clearing-fixture, per-warehouse-dotenv-isolation]

key-files:
  created: []
  modified:
    - tests/conftest.py
    - tests/integration/conftest.py
    - tests/integration/test_snowflake.py
    - tests/integration/test_databricks.py

key-decisions:
  - "monkeypatch.delenv over os.environ.pop: monkeypatch auto-restores on teardown, no manual cleanup needed"
  - "pyright: ignore[reportUnusedFunction] on autouse fixture: basedpyright strict mode flags underscore-prefixed conftest fixtures as unused; suppression required for autouse convention"

patterns-established:
  - "Autouse env clearing: _clear_warehouse_env_vars fixture in tests/conftest.py clears all warehouse-prefixed env vars before every test"
  - "Per-warehouse dotenv: each integration test module loads its own .env.{warehouse} file, never the shared .env"

requirements-completed: []

# Metrics
duration: 5min
completed: 2026-03-07
---

# Phase 15 Plan 04: Env Var Isolation Summary

**Autouse monkeypatch fixture clears 13 warehouse env prefixes before each test; integration tests load per-warehouse dotenv files (.env.snowflake, .env.databricks)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-07T09:57:08Z
- **Completed:** 2026-03-07T10:02:06Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Unit tests (test_configs, test_translators) now pass regardless of warehouse env vars in os.environ
- Integration tests isolated: Snowflake tests load .env.snowflake, Databricks tests load .env.databricks
- No single .env file needs to contain credentials for multiple warehouses simultaneously

## Task Commits

Each task was committed atomically:

1. **Task 1: Add autouse fixture to clear warehouse env vars** - `e553eb1` (fix)
2. **Task 2: Fix integration test dotenv loading to use per-warehouse files** - `c205ceb` (fix)

## Files Created/Modified
- `tests/conftest.py` - Autouse fixture clearing all 13 warehouse env prefixes via monkeypatch before each test
- `tests/integration/conftest.py` - Pool fixtures load .env.snowflake and .env.databricks instead of .env
- `tests/integration/test_snowflake.py` - Helper and docstrings reference .env.snowflake
- `tests/integration/test_databricks.py` - Helper and docstrings reference .env.databricks

## Decisions Made
- Used `monkeypatch.delenv` over `os.environ.pop` because monkeypatch auto-restores environment on test teardown
- Added `pyright: ignore[reportUnusedFunction]` on the autouse fixture because basedpyright strict mode flags underscore-prefixed conftest fixtures as unused functions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-commit basedpyright flagged `_clear_warehouse_env_vars` as unused (reportUnusedFunction) since it is an autouse conftest fixture discovered by pytest convention, not called directly. Fixed with inline pyright suppression comment.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All unit tests immune to env var contamination (147 pass)
- Integration tests properly isolated per warehouse
- Ready for 15-05 (Snowflake cassette recording with per-warehouse dotenv)

## Self-Check: PASSED

- All 4 modified files exist on disk
- Both task commits (e553eb1, c205ceb) verified in git log
- 147 unit tests pass
- No bare .env loading remains in integration tests

---
*Phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests*
*Completed: 2026-03-07*
