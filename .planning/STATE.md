# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 3 — Package Structure

## Current Position

Phase: 3 of 7 (Config Layer) - Complete
Plan: 5 of 5 in phase 3 complete
Status: Phase Complete
Last activity: 2026-02-24 — Plan 03-05 executed

Progress: [██████░░░░] 60%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: ~2 min
- Total execution time: ~11 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-pre-flight-fixes | 1 | ~1 min | ~1 min |
| 02-dependency-declarations | 2 | ~2 min | ~1 min |
| 03-config-layer | 5 | ~20 min | ~4 min |

**Recent Trend:**
- Last 5 plans: 1-8 min
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
- [03-01]: DuckDBConfig.pool_size defaults to 1 (not inherited base default of 5) — in-memory DuckDB isolates each connection to a different empty DB; pool_size > 1 with :memory: raises ValidationError
- [03-01]: typing.Self from stdlib (not typing_extensions) — ruff upgraded per Python 3.14 project target
- [03-02]: Path import kept at module level with # noqa: TC003 — Pydantic resolves field type annotations at runtime even with from __future__ import annotations; moving to TYPE_CHECKING block causes PydanticUndefinedAnnotation
- [03-02]: schema_ field alias approach: Field(validation_alias='schema', alias='schema') maps SNOWFLAKE_SCHEMA env var to schema_ Python attribute without trailing underscore in env var name
- [03-05]: MSSQLConfig is one class covering SQL Server, Azure SQL, Azure Fabric, and Synapse Analytics — not separate classes per variant (locked CONTEXT.md decision)
- [03-05]: TeradataConfig fields are LOW confidence — triangulated from Teradata JDBC and teradatasql Python driver docs because Columnar ADBC Teradata driver docs returned 404; each field has source attribution docstring
- [03-05]: SecretStr import uses # noqa: TC002 (not TYPE_CHECKING block) — Pydantic BaseSettings resolves field annotations at class-creation time making runtime import necessary

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 4 (Driver Detection): Foundry driver path discovery mechanism in `adbc_driver_manager` is sparsely documented — needs implementation-time research against actual Foundry-installed driver paths (ADBC Driver Foundry launched Oct 2025)
- Phase 6 (Snowflake Snapshots): Custom syrupy serializer design needs validation against real Snowflake ADBC driver response format — metadata field names and Arrow schema structure must be verified before finalising serializer

## Session Continuity

Last session: 2026-02-24
Stopped at: Completed 03-04-PLAN.md — _databricks_config.py (DatabricksConfig with PAT/OAuth fields), _redshift_config.py (RedshiftConfig provisioned/serverless), _trino_config.py (TrinoConfig with ssl=True default) created; prek green; schema_ alias pattern and # noqa: TC002 for sole SecretStr imports established
Resume file: None
