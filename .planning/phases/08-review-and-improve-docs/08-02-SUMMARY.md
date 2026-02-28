---
phase: 08-review-and-improve-docs
plan: "02"
subsystem: documentation
tags: [docs, close_pool, managed_pool, api-update]
dependency_graph:
  requires: [08-01]
  provides: [updated-user-facing-docs]
  affects: [docs/src/index.md, docs/src/guides/pool-lifecycle.md, docs/src/guides/configuration.md, docs/src/guides/consumer-patterns.md]
tech_stack:
  added: []
  patterns: [close_pool, managed_pool, mkdocs-strict]
key_files:
  created: []
  modified:
    - docs/src/index.md
    - docs/src/guides/pool-lifecycle.md
    - docs/src/guides/configuration.md
    - docs/src/guides/consumer-patterns.md
decisions:
  - "max_overflow default corrected from 10 to 3 in configuration.md (aligns with code)"
metrics:
  duration: 106s
  completed: "2026-02-28"
  tasks_completed: 3
  files_modified: 4
---

# Phase 8 Plan 02: Update Docs to use close_pool API Summary

Eliminated all `pool._adbc_source` references from user-facing docs and added ADBC driver install section, config class list, and pool tuning kwargs table.

## What Was Built

All four user-facing documentation pages updated to use the new `close_pool`/`managed_pool` public API introduced in plan 08-01. Two content gaps identified in the review phase filled: ADBC driver installation instructions and a full pool tuning kwargs table.

### docs/src/index.md

- Added ADBC drivers section with per-warehouse install command table (pip extras for PyPI drivers, Foundry installation links for off-PyPI drivers)
- Added typed config class list (`DuckDBConfig` through `MSSQLConfig`) before the quickstart example
- Replaced `pool.dispose()` + `pool._adbc_source.close()` with `close_pool(pool)` in the code example
- Updated import line to include `close_pool`
- Rewrote dispose prose to describe `close_pool` semantics
- Added warehouse guides link to What's next

### docs/src/guides/pool-lifecycle.md

- Replaced all `pool._adbc_source.close()` references with `close_pool()` throughout
- Rewrote Disposing section: single-call `close_pool` replaces the two-step pattern
- Updated pytest fixture teardown to use `close_pool`
- Added `managed_pool` context manager alternative after the fixture example
- Added Tuning the pool section with 5-row kwargs table (`pool_size`, `max_overflow`, `timeout`, `recycle`, `pre_ping`)
- Rewrote Common mistakes section: removed `_adbc_source` item, added `pool.dispose()` without `close_pool()` item

### docs/src/guides/configuration.md

- Added `pre_ping` row to pool tuning table
- Corrected `max_overflow` default from `10` to `3` (matching the actual code default)

### docs/src/guides/consumer-patterns.md

- Updated FastAPI lifespan import to include `close_pool`
- Replaced `pool.dispose()` + `pool._adbc_source.close()` with `close_pool(pool)`

## Verification

```
grep -rn "_adbc_source" docs/src/ | wc -l  → 0
uv run mkdocs build --strict               → exit 0
```

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 — index.md | 73c6344 | ADBC driver section, config class list, close_pool |
| 2 — pool-lifecycle.md | d907569 | close_pool API and tuning section |
| 3 — configuration.md + consumer-patterns.md | e59d1db | pre_ping row, max_overflow fix, close_pool |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed max_overflow default mismatch in configuration.md**
- **Found during:** Task 3
- **Issue:** configuration.md showed `max_overflow` default as `10`; actual code default is `3`
- **Fix:** Updated table row to show `3`
- **Files modified:** docs/src/guides/configuration.md
- **Commit:** e59d1db

## Self-Check: PASSED
