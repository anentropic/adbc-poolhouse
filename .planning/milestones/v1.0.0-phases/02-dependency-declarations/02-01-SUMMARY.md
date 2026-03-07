---
phase: 02-dependency-declarations
plan: 01
subsystem: infra
tags: [pyproject.toml, uv, pydantic-settings, sqlalchemy, adbc-driver-manager, duckdb, snowflake, postgresql, flightsql, bigquery, syrupy, coverage]

# Dependency graph
requires:
  - phase: 01-pre-flight-fixes
    provides: pythonVersion fix in pyproject.toml, pre-commit toolchain green
provides:
  - pyproject.toml runtime deps (pydantic-settings, sqlalchemy, adbc-driver-manager) with open lower bounds
  - five optional PyPI extras (duckdb, snowflake, postgresql, flightsql, bigquery) plus [all] meta-extra
  - dev deps: syrupy>=4.0 and coverage[toml] added to [dependency-groups] dev
  - corrected REQUIREMENTS.md SETUP-02 and SETUP-03 descriptions reflecting actual decisions
affects: [03-config-layer, 05-pool-factory, 06-snowflake-snapshots, phase-lock-file]

# Tech tracking
tech-stack:
  added:
    - pydantic-settings>=2.0.0 (runtime)
    - sqlalchemy>=2.0.0 (runtime)
    - adbc-driver-manager>=1.0.0 (runtime)
    - duckdb>=0.9.1 (optional extra)
    - adbc-driver-snowflake>=1.0.0 (optional extra)
    - adbc-driver-postgresql>=1.0.0 (optional extra)
    - adbc-driver-flightsql>=1.0.0 (optional extra)
    - adbc-driver-bigquery>=1.3.0 (optional extra)
    - syrupy>=4.0 (dev)
    - coverage[toml] (dev)
  patterns:
    - Open lower bounds only (>=X, no <Y upper cap) for all runtime and optional deps
    - Self-referencing [all] meta-extra using adbc-poolhouse[extra] pattern
    - PyPI-available drivers only for optional extras; Foundry backends deferred to Phase 7

key-files:
  created: []
  modified:
    - pyproject.toml
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Open lower bounds only (>=X) for runtime deps — tight <Y bounds cause unnecessary consumer dep conflicts for common transitive deps like pydantic-settings and sqlalchemy"
  - "duckdb extra uses duckdb>=0.9.1 package (not adbc-driver-duckdb which does not exist on PyPI — adbc_driver_duckdb is bundled inside the duckdb wheel since 0.9.1)"
  - "[all] meta-extra uses self-referencing adbc-poolhouse[extra] syntax — standard pip/uv pattern for meta-extras"
  - "Foundry-distributed backends (Databricks, Redshift, Trino, MSSQL, Teradata) excluded from optional extras — not on PyPI; deferred to Phase 7 documentation"
  - "bigquery extra included as adbc-driver-bigquery>=1.3.0 — confirmed PyPI-available"

patterns-established:
  - "Open lower bounds: all dep constraints in this project use >=X style with no upper bound cap"
  - "Self-referencing extras: [all] composes individual extras via adbc-poolhouse[extra] references"

requirements-completed: [SETUP-02, SETUP-03, SETUP-04]

# Metrics
duration: 1min
completed: 2026-02-24
---

# Phase 2 Plan 01: Dependency Declarations Summary

**pyproject.toml updated with three runtime deps, five PyPI warehouse extras plus [all] meta-extra, and two dev dep additions (syrupy, coverage) using open-lower-bound constraints throughout**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-02-23T23:34:48Z
- **Completed:** 2026-02-23T23:36:10Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Declared `pydantic-settings>=2.0.0`, `sqlalchemy>=2.0.0`, `adbc-driver-manager>=1.0.0` as runtime dependencies with open lower bounds
- Added five optional warehouse extras (`[duckdb]`, `[snowflake]`, `[postgresql]`, `[flightsql]`, `[bigquery]`) plus `[all]` meta-extra using self-referencing pattern; Foundry backends explicitly deferred
- Added `syrupy>=4.0` and `coverage[toml]` to `[dependency-groups] dev` in alphabetical order
- Corrected REQUIREMENTS.md SETUP-02 (open-lower-bound rationale) and SETUP-03 (PyPI-only extras, Foundry deferred to Phase 7)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add runtime deps, optional extras, and dev deps to pyproject.toml** - `3b93eb2` (feat)
2. **Task 2: Update REQUIREMENTS.md SETUP-02 and SETUP-03 descriptions** - `795e656` (docs)

**Plan metadata:** _(docs commit below)_

## Files Created/Modified

- `pyproject.toml` - Added runtime deps, [project.optional-dependencies] section with five extras + [all], and two dev dep entries
- `.planning/REQUIREMENTS.md` - Updated SETUP-02 description (open lower bounds + rationale), SETUP-03 description (PyPI-only extras, Foundry deferred to Phase 7)

## Decisions Made

- Open lower bounds only (`>=X`, no `<Y` cap) for all deps — avoids consumer dependency conflicts for common transitive deps
- `duckdb>=0.9.1` used (not `adbc-driver-duckdb` which does not exist on PyPI; `adbc_driver_duckdb` is bundled inside the `duckdb` wheel since 0.9.1)
- `[all]` meta-extra uses self-referencing `adbc-poolhouse[extra]` syntax (standard pip/uv pattern)
- Foundry-distributed backends excluded from extras in v1; deferred to Phase 7

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 3 (Config Layer): `pydantic-settings>=2.0.0` and `sqlalchemy>=2.0.0` are now declared, unblocking config model implementation
- Phase 6 (Snowflake Snapshots): `syrupy>=4.0` is now in dev deps, unblocking snapshot test infrastructure
- `uv.lock` is untracked (updated by pre-commit uv-lock hook during Task 1 commit) — should be committed as part of Phase 2 lock file plan if one exists

---
*Phase: 02-dependency-declarations*
*Completed: 2026-02-24*
