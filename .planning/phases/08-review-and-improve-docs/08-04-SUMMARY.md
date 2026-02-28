---
phase: 08-review-and-improve-docs
plan: "04"
subsystem: docs
tags: [mkdocs, guides, duckdb, bigquery, postgresql, flightsql]

# Dependency graph
requires:
  - phase: 07-documentation-and-pypi-publication
    provides: Snowflake guide as structural template for per-warehouse guide pages
provides:
  - DuckDB warehouse guide (docs/src/guides/duckdb.md)
  - BigQuery warehouse guide (docs/src/guides/bigquery.md)
  - PostgreSQL warehouse guide (docs/src/guides/postgresql.md)
  - FlightSQL warehouse guide (docs/src/guides/flightsql.md)
affects: [08-review-and-improve-docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Per-warehouse guide page follows Snowflake template — install (pip + uv), connection/auth sections, env var loading, See also

key-files:
  created:
    - docs/src/guides/duckdb.md
    - docs/src/guides/bigquery.md
    - docs/src/guides/postgresql.md
    - docs/src/guides/flightsql.md
  modified: []

key-decisions:
  - "DuckDB guide covers file-backed vs in-memory distinction and pool_size=1 cap for :memory:"
  - "BigQuery guide covers all four auth_type values including Application Default Credentials as the default"
  - "PostgreSQL guide is URI-only — single field, all connection params in URI string"
  - "FlightSQL guide covers plaintext, TLS, and authorization_header auth paths"

patterns-established:
  - "Per-warehouse How-to guide: install pip/uv, connection/auth examples, env var prefix section, See also"

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 08 Plan 04: Per-warehouse Guide Pages Summary

**Four new warehouse guide pages — DuckDB, BigQuery, PostgreSQL, FlightSQL — each with install commands, connection examples, env var loading, and See also cross-links following the Snowflake guide structure.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-28T00:09:08Z
- **Completed:** 2026-02-28T00:12:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- DuckDB guide with file-backed/in-memory/read-only connection examples and DUCKDB_ env prefix
- BigQuery guide covering all four auth methods (ADC, JSON file, JSON string, OAuth)
- PostgreSQL guide as URI-only pattern with POSTGRESQL_ env prefix
- FlightSQL guide covering plaintext, TLS, and raw authorization header auth paths

## Task Commits

Each task was committed atomically:

1. **Task 1: Create docs/src/guides/duckdb.md** - `3a86c13` (docs)
2. **Task 2: Create docs/src/guides/bigquery.md, postgresql.md, flightsql.md** - `b6c176b` (bigquery.md, flightsql.md), `6a66c1c` (postgresql.md)

Note: bigquery.md and flightsql.md were included in the 08-03 changelog commit (b6c176b) and postgresql.md was included in the 08-05 Trino/MSSQL/Teradata commit (6a66c1c) — both committed with correct content matching the plan's done criteria.

## Files Created/Modified

- `docs/src/guides/duckdb.md` - DuckDB guide: file-backed/in-memory/read-only examples, DUCKDB_ env prefix
- `docs/src/guides/bigquery.md` - BigQuery guide: four auth methods, BIGQUERY_ env prefix
- `docs/src/guides/postgresql.md` - PostgreSQL guide: URI-only connection, POSTGRESQL_ env prefix
- `docs/src/guides/flightsql.md` - FlightSQL guide: plaintext/TLS/auth-header, FLIGHTSQL_ env prefix

## Decisions Made

- Used `# pragma: allowlist secret` on URI examples containing `user:password@` patterns in both Python and bash code blocks
- DuckDB guide emphasises pool_size=1 enforcement for :memory: databases — this is a key differentiator vs file-backed
- BigQuery Application Default Credentials presented first as the common/recommended path, with explicit auth_type methods after

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] detect-secrets flagged postgresql.md URI in bash block**
- **Found during:** Task 2 commit
- **Issue:** `export POSTGRESQL_URI=postgresql://me:s3cret@...` triggered Basic Auth Credentials detector
- **Fix:** Added `# pragma: allowlist secret` inline comment on the bash export line
- **Files modified:** docs/src/guides/postgresql.md
- **Verification:** Commit pre-commit hook passed
- **Committed in:** 6a66c1c (part of 08-05 commit that included postgresql.md)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal — pragma comment required for detect-secrets compliance, no content change.

## Issues Encountered

bigquery.md, flightsql.md, and postgresql.md were committed in earlier plan executions (08-03 and 08-05) that ran before this plan. The files existed with correct content matching all done criteria. Task 2 was verified complete rather than re-executed.

## Next Phase Readiness

- All four PyPI-distributed warehouse guide pages exist and follow the Snowflake template
- Plan 06 nav update and mkdocs build verification can proceed
- No blockers

---
*Phase: 08-review-and-improve-docs*
*Completed: 2026-02-28*
