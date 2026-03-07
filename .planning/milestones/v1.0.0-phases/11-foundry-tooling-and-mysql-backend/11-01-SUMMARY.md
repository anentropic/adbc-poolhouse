---
phase: 11-foundry-tooling-and-mysql-backend
plan: 01
subsystem: infra
tags: [dbc, foundry, justfile, developer-tooling]

requires: []
provides:
  - just install-dbc recipe with command -v guard
  - just install-foundry-drivers recipe with two separate dbc install calls
  - Foundry Driver Management section in DEVELOP.md covering install/verify/uninstall
affects:
  - 11-03-PLAN (MySQL driver available in virtualenv for testing)
  - 11-04-PLAN (DEVELOP.md reference from MySQL guide)

tech-stack:
  added: [dbc CLI (Columnar ADBC Driver Foundry)]
  patterns: [POSIX command -v guard for CLI availability checks in justfile]

key-files:
  created: []
  modified:
    - justfile
    - DEVELOP.md

key-decisions:
  - "command -v dbc used (not which) — POSIX portable in just's shell context"
  - "Two separate dbc install calls — multi-driver syntax unconfirmed by official docs"
  - "No --level flag — dbc detects VIRTUAL_ENV automatically; --level env does not exist"

requirements-completed:
  - DBC-01
  - DBC-02
  - DBC-03

duration: 1min
completed: 2026-03-01
---

# Phase 11 Plan 01: Foundry Tooling Summary

**Two justfile recipes (install-dbc, install-foundry-drivers) and DEVELOP.md Foundry Driver Management section covering the full dbc CLI lifecycle for MySQL/ClickHouse Foundry drivers**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-01T17:18:13Z
- **Completed:** 2026-03-01T17:19:06Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `install-dbc` recipe guards with `command -v dbc` (POSIX, not `which`) before running the curl installer
- `install-foundry-drivers` uses two separate `dbc install mysql` and `dbc install clickhouse` calls
- DEVELOP.md section documents install, verify (`dbc info`), and uninstall with direct bash examples

## Task Commits

Each task was committed atomically:

1. **Task 1: Add install-dbc and install-foundry-drivers recipes** - `2d10590` (feat)
2. **Task 2: Add Foundry Driver Management section to DEVELOP.md** - `f9f84cf` (docs)

## Files Created/Modified
- `justfile` - Added install-dbc and install-foundry-drivers recipes
- `DEVELOP.md` - Added Foundry Driver Management section before Questions?

## Decisions Made
- Used `command -v dbc` not `which dbc` — POSIX portable and correct in just's sh context
- Two separate `dbc install` calls because multi-driver install syntax is unconfirmed
- No `--level env` flag — only `user` and `system` are valid; virtualenv scoping is automatic via VIRTUAL_ENV

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness
- Developers can now install the dbc CLI and Foundry drivers with two just commands
- DEVELOP.md section provides context referenced by the MySQL warehouse guide (Plan 11-04)
- Ready for Plan 11-02: MySQLConfig and translate_mysql() implementation

---
*Phase: 11-foundry-tooling-and-mysql-backend*
*Completed: 2026-03-01*
