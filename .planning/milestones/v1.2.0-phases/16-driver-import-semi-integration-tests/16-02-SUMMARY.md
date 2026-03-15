---
phase: 16-driver-import-semi-integration-tests
plan: 02
subsystem: testing
tags: [justfile, drivers, installation, developer-experience]

# Dependency graph
requires: []
provides:
  - Single-command installation of all 12 ADBC drivers for semi-integration tests
affects: [developer-setup, testing-infrastructure]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Justfile recipes for driver installation orchestration
    - Dependency chaining (install-dbc → install-all-drivers)

key-files:
  created: []
  modified:
    - justfile - Added install-all-drivers recipe

key-decisions:
  - "Install PyPI drivers in single uv pip command for efficiency"
  - "Install Foundry drivers one at a time (dbc doesn't support multiple args)"
  - "ClickHouse requires --pre flag (only alpha version published)"

patterns-established:
  - "Recipe dependency: install-all-drivers depends on install-dbc for CLI setup"
  - "Single command for complete environment setup"

requirements-completed: [TEST-01]

# Metrics
duration: 1 min
completed: 2026-03-12
---

# Phase 01 Plan 02: Install All Drivers Recipe Summary

**Added install-all-drivers justfile recipe for single-command installation of all 12 ADBC drivers (6 PyPI + 6 Foundry)**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-12T08:55:55Z
- **Completed:** 2026-03-12T08:57:29Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Added `install-all-drivers` recipe to justfile for developer convenience
- Recipe installs 6 PyPI driver extras (duckdb, snowflake, bigquery, postgresql, flightsql, sqlite) in single uv pip command
- Recipe installs 6 Foundry drivers (databricks, redshift, trino, mssql, mysql, clickhouse) via dbc CLI
- Recipe depends on `install-dbc` to ensure CLI is available before driver installation

## Task Commits

Each task was committed atomically:

1. **Task 1: Add install-all-drivers recipe to justfile** - `23ff661` (feat)

## Files Created/Modified

- `justfile` - Added install-all-drivers recipe with dependency on install-dbc, installs all 12 drivers for semi-integration tests

## Decisions Made

- Install PyPI drivers in single `uv pip install -e ".[...]"` command for efficiency rather than separate commands per driver
- Install Foundry drivers one at a time because dbc CLI doesn't support multiple package arguments per installation call
- Include ClickHouse with `--pre` flag because only alpha version (v0.1.0-alpha.1) is currently published

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - straightforward justfile modification completed without issues.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for next plan in Phase 01. The install-all-drivers recipe enables developers to set up their environment with a single command for running semi-integration tests.

---
*Phase: 01-driver-import-semi-integration-tests*
*Completed: 2026-03-12*

## Self-Check: PASSED

All verification checks passed:
- ✓ justfile exists
- ✓ Commit 23ff661 exists
- ✓ SUMMARY.md created
