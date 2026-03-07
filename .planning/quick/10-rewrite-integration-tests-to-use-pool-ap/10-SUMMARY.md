---
phase: quick-10
plan: 01
subsystem: testing
tags: [pytest, integration-tests, pool-api, fixtures]

# Dependency graph
requires:
  - phase: 15-cassette-tests
    provides: "conftest.py pool fixtures and cassette replay infrastructure"
provides:
  - "Pool-based integration tests for Databricks and Snowflake"
affects: [integration-tests, cassette-replay]

# Tech tracking
tech-stack:
  added: []
  patterns: ["pool fixture injection for integration tests"]

key-files:
  created: []
  modified:
    - tests/integration/test_databricks.py
    - tests/integration/test_snowflake.py

key-decisions:
  - "Kept typing.Any annotations for pool/conn/cur since pool type comes from SQLAlchemy internals"

patterns-established:
  - "Pool fixture pattern: inject session-scoped pool fixture, call pool.connect() for each test"

requirements-completed: [QUICK-10]

# Metrics
duration: 2min
completed: 2026-03-07
---

# Quick Task 10: Rewrite Integration Tests to Use Pool API Summary

**Integration tests rewritten from raw ADBC driver connections to pool fixture injection via create_pool/close_pool API**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-07T14:07:05Z
- **Completed:** 2026-03-07T14:08:32Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Removed all raw driver connection code from test_databricks.py (adbc_driver_manager.dbapi.connect, _databricks_connect_kwargs helper)
- Removed all raw driver connection code from test_snowflake.py (adbc_driver_snowflake.dbapi.connect, _snowflake_db_kwargs helper)
- Both test files now inject session-scoped pool fixtures and use pool.connect() for database access
- All cassette markers (@pytest.mark.adbc_cassette) preserved for CI replay

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite test_databricks.py to use pool fixture** - `60964c5` (refactor)
2. **Task 2: Rewrite test_snowflake.py to use pool fixture** - `66b5fa7` (refactor)

## Files Created/Modified
- `tests/integration/test_databricks.py` - Rewritten to use databricks_pool fixture; removed 6 imports and helper function
- `tests/integration/test_snowflake.py` - Rewritten to use snowflake_pool fixture; removed 5 imports and helper function

## Decisions Made
- Kept `typing.Any` annotations for pool, connection, and cursor objects since the pool type is `sqlalchemy.pool.QueuePool` and the connection/cursor types vary by driver

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Steps
- Tests will be broken until pytest-adbc-replay adds adbc_clone() support (expected per plan)
- conftest.py has pre-existing unstaged changes that should be reviewed and committed separately

## Self-Check: PASSED

All files exist, all commits verified.

---
*Quick Task: 10-rewrite-integration-tests-to-use-pool-ap*
*Completed: 2026-03-07*
