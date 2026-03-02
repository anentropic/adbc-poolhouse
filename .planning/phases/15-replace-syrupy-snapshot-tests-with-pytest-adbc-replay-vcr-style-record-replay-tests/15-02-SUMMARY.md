---
phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests
plan: 02
subsystem: testing
tags: [pytest, conftest, fixtures, databricks, snowflake]

requires:
  - phase: 15-01
    provides: pytest-adbc-replay installed, pyproject.toml updated

provides:
  - Syrupy-free conftest.py with snowflake_pool and databricks_pool fixtures
  - DatabricksConfig import added to conftest.py

affects: [15-03]

tech-stack:
  added: []
  patterns:
    - "Session-scoped pool fixtures for recording only; cassette tests do not request them"
    - "Credential guard pattern: check URI OR all three decomposed fields for Databricks"

key-files:
  created: []
  modified:
    - tests/integration/conftest.py

key-decisions:
  - "Pool fixtures retained for recording workflow only; cassette tests call ADBC drivers directly"
  - "Databricks credential guard checks DATABRICKS_URI OR (DATABRICKS_HOST + DATABRICKS_HTTP_PATH + DATABRICKS_TOKEN)"

patterns-established:
  - "Pool fixture skip message updated to mention cassette replay as the alternative"

requirements-completed: []

duration: 0min
completed: 2026-03-02
---

# Phase 15 Plan 02: Conftest Cleanup Summary

**conftest.py rewritten: all Syrupy code removed, databricks_pool session fixture added, both pool fixtures updated with cassette replay context in docstrings**

## Performance

- **Duration:** 0 min (executed together with Plan 15-01 due to pre-commit constraint)
- **Started:** 2026-03-02T21:51:43Z
- **Completed:** 2026-03-02T22:00:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Removed all Syrupy imports (`JSONSnapshotExtension`, `SnapshotAssertion`, `syrupy.*`)
- Deleted `SnowflakeArrowSnapshotSerializer` class entirely
- Deleted `snowflake_snapshot` fixture
- Updated `snowflake_pool` docstring to note cassette replay alternative
- Added `databricks_pool` session-scoped fixture mirroring `snowflake_pool` structure

## Task Commits

1. **Task 1: Rewrite conftest.py** - `74b4845` (combined commit with 15-01 due to pre-commit blocking)

## Files Created/Modified

- `tests/integration/conftest.py` - Complete rewrite; Syrupy-free; databricks_pool added

## Decisions Made

- None beyond plan specification.

## Deviations from Plan

**[Rule 3 - Blocking] Executed together with Plan 15-01 due to pre-commit wave constraint.**

Wave boundary could not be preserved — see Plan 15-01 SUMMARY for details.

---

**Total deviations:** 0 from Plan 15-02 scope (the wave collapse was a Plan 15-01 deviation)
**Impact on plan:** All Plan 15-02 objectives met exactly as specified.

## Issues Encountered

None.

## Next Phase Readiness

- conftest.py is Syrupy-free with both pool fixtures
- Ready for cassette test files and cassette generation (Plan 15-03)

---
*Phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests*
*Completed: 2026-03-02*
