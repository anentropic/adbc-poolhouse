# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 3 — Package Structure

## Current Position

Phase: 2 of 7 (Dependency Declarations) - Complete
Plan: 2 of 2 in phase 2 complete; advancing to Phase 3
Status: Phase complete
Last activity: 2026-02-24 — Plan 02-02 executed

Progress: [███░░░░░░░] 35%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: ~1 min
- Total execution time: ~3 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-pre-flight-fixes | 1 | ~1 min | ~1 min |
| 02-dependency-declarations | 2 | ~2 min | ~1 min |

**Recent Trend:**
- Last 5 plans: 1 min
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Pre-roadmap]: `pre_ping=False` default (not True) — pre_ping silently no-ops on standalone QueuePool without a SQLAlchemy dialect; recycle=3600 is the connection health mechanism
- [Pre-roadmap]: Syrupy snapshots for Snowflake CI — real credentials used locally for recording; snapshots committed and replayed in CI without creds
- [Pre-roadmap]: `importlib.util.find_spec()` for driver detection — bare `except ImportError` swallows broken native extensions; find_spec distinguishes "not installed" from "installed but broken"
- [01-01]: detect-secrets fetched by prek from GitHub hook entry — NOT added to pyproject.toml dev dependencies
- [01-01]: Baseline generated with --exclude-files "^.planning/" to embed exclusion in filters_used and produce clean results: {} output
- [01-01]: exclude: .secrets.baseline mandatory in hook entry — SHA-256 hashes in baseline JSON trigger HexHighEntropyString/SecretKeyword detectors
- [02-01]: Open lower bounds only (>=X, no <Y cap) for runtime deps — tight upper bounds cause unnecessary consumer dep conflicts for common transitive deps
- [02-01]: duckdb extra uses duckdb>=0.9.1 (not adbc-driver-duckdb which does not exist on PyPI — adbc_driver_duckdb is bundled inside duckdb wheel since 0.9.1)
- [02-01]: [all] meta-extra uses self-referencing adbc-poolhouse[extra] syntax — standard pip/uv pattern for meta-extras
- [02-01]: Foundry backends (Databricks, Redshift, Trino, MSSQL, Teradata) excluded from optional extras — not on PyPI; deferred to Phase 7
- [Phase 02-02]: uv.lock committed to git enabling CI to enforce reproducible builds via uv sync --frozen
- [Phase 02-02]: Extras isolation verified: each warehouse driver extra installs only its own driver without cross-contamination

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 4 (Driver Detection): Foundry driver path discovery mechanism in `adbc_driver_manager` is sparsely documented — needs implementation-time research against actual Foundry-installed driver paths (ADBC Driver Foundry launched Oct 2025)
- Phase 6 (Snowflake Snapshots): Custom syrupy serializer design needs validation against real Snowflake ADBC driver response format — metadata field names and Arrow schema structure must be verified before finalising serializer

## Session Continuity

Last session: 2026-02-24
Stopped at: Completed 02-02-PLAN.md — uv.lock committed (1603 lines, 82 packages), extras isolation verified, prek gate green, CI frozen sync confirmed
Resume file: None
