---
phase: quick-9
plan: 1
subsystem: documentation
tags: [docs, develop, readme, syrupy, cassettes, warehouses]

# Dependency graph
requires:
  - phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests
    provides: cassette-based test workflow replacing syrupy snapshots
provides:
  - Accurate DEVELOP.md Snowflake integration test instructions
  - Complete 12-backend README.md warehouse listing
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - DEVELOP.md
    - README.md

key-decisions:
  - "Alphabetical ordering of PyPI extras list to match docs/src/index.md table order"
  - "PyPI vs Foundry grouping in README.md supported warehouses section to match docs/src/index.md structure"

patterns-established: []

requirements-completed: [DOC-FIX]

# Metrics
duration: 1min
completed: 2026-03-07
---

# Quick Task 9: Fix Docs Gaps Summary

**Replaced stale syrupy snapshot references with cassette workflow in DEVELOP.md and expanded README.md to list all 12 supported backends**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-07T11:55:24Z
- **Completed:** 2026-03-07T11:56:27Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Replaced `--snapshot-update` with `--adbc-record=once` in DEVELOP.md Snowflake section
- Updated "snapshots" to "cassettes" terminology throughout DEVELOP.md
- Added SQLite to README.md PyPI extras parenthetical (now 6 backends)
- Replaced 9-item bullet list with grouped 12-backend format (6 PyPI + 6 Foundry)

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix stale syrupy references in DEVELOP.md and missing backends in README.md** - `7bf1d0d` (docs)

## Files Created/Modified
- `DEVELOP.md` - Updated Snowflake integration tests subsection: cassette recording commands and terminology
- `README.md` - Updated PyPI extras list (added SQLite) and expanded supported warehouses to all 12 backends

## Decisions Made
- Alphabetical ordering of PyPI extras list to match docs/src/index.md table order
- PyPI vs Foundry grouping in README.md supported warehouses section to match docs/src/index.md structure

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Self-Check: PASSED

- [x] DEVELOP.md exists and contains `--adbc-record=once`
- [x] README.md exists and contains SQLite, ClickHouse, MySQL
- [x] 9-SUMMARY.md created
- [x] Commit 7bf1d0d verified in git log
- [x] No stale syrupy/snapshot-update references in DEVELOP.md

---
*Quick Task: 9-fix-docs-gaps-develop-md-stale-syrupy-re*
*Completed: 2026-03-07*
