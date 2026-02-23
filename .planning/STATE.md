# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 2 — Dependency Declarations

## Current Position

Phase: 2 of 7 (Dependency Declarations)
Plan: 1 of 1 in current phase
Status: Plan complete
Last activity: 2026-02-24 — Plan 02-01 executed

Progress: [██░░░░░░░░] 28%

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: ~1 min
- Total execution time: ~2 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-pre-flight-fixes | 1 | ~1 min | ~1 min |
| 02-dependency-declarations | 1 | ~1 min | ~1 min |

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

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 4 (Driver Detection): Foundry driver path discovery mechanism in `adbc_driver_manager` is sparsely documented — needs implementation-time research against actual Foundry-installed driver paths (ADBC Driver Foundry launched Oct 2025)
- Phase 6 (Snowflake Snapshots): Custom syrupy serializer design needs validation against real Snowflake ADBC driver response format — metadata field names and Arrow schema structure must be verified before finalising serializer

## Session Continuity

Last session: 2026-02-24
Stopped at: Completed 02-01-PLAN.md — runtime deps, optional extras, dev deps declared; REQUIREMENTS.md corrected
Resume file: None
