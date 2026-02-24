# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-23)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 5 — Pool Factory and DuckDB Integration

## Current Position

Phase: 5 of 7 (Pool Factory and DuckDB Integration) - Complete
Plan: 2 of 2 in phase 5 complete
Status: Phase 5 Complete — Plan 05-02 complete (create_pool() factory; Arrow cleanup; public exports)
Last activity: 2026-02-24 — Plan 05-02 executed (create_pool() with ADBC source+clone pattern; Arrow cursor cleanup on reset event; public API exports; 16 new tests; 86 total tests green)

Progress: [██████████] 87%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: ~3 min
- Total execution time: ~24 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-pre-flight-fixes | 1 | ~1 min | ~1 min |
| 02-dependency-declarations | 2 | ~2 min | ~1 min |
| 03-config-layer | 7 | ~28 min | ~4 min |
| 04-translation-and-driver-detection | 5 | ~19 min | ~4 min |
| 05-pool-factory-and-duckdb-integration | 2 | ~6 min | ~3 min |

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
- [03-06]: __all__ uses 12 names (11 config classes + WarehouseConfig Protocol); all imports from _-prefixed internal modules ensuring no ADBC driver needed at import time
- [Phase 03-config-layer]: DuckDB env prefix pool_size tests require DUCKDB_DATABASE env var set to file path — in-memory pool_size > 1 raises ValidationError
- [Phase 03-config-layer]: type: ignore[call-arg] for SnowflakeConfig() calls without account= in env prefix tests — basedpyright cannot see env var-provided required fields at type-check time
- [Phase 03-config-layer]: pragma: allowlist secret on variables holding PEM/password strings, not inline in constructor — avoids ruff line-length and detect-secrets conflicts simultaneously
- [04-01]: Translator config imports in TYPE_CHECKING block — with from __future__ import annotations, config class imports are only needed at type-check time (not runtime), so ruff TC001 correctly flags them; differs from Pydantic config files where SecretStr must stay at module level
- [04-01]: translate_postgresql omits use_copy — adbc.postgresql.use_copy is a StatementOptions key (per-statement), not a DatabaseOptions key (per-connection); passing to dbapi.connect() is incorrect; Phase 5 must apply at cursor level
- [04-01]: translate_flightsql always emits tls_skip_verify and with_cookie_middleware — bool fields with defaults (never None), so always included as 'true'/'false' strings in output dict
- [04-01]: FlightSQL connect_timeout uses raw string key 'adbc.flight.sql.rpc.timeout_seconds.connect' — documented in ADBC FlightSQL docs but absent from Python DatabaseOptions enum; included as raw string
- [04-02]: TYPE_CHECKING block for translator config imports — translator functions (not Pydantic models) safely use TYPE_CHECKING; ruff TC001 correctly flags runtime imports in this context unlike Pydantic field annotations
- [04-02]: Trino and MSSQL use URI-first with decomposed field fallback — plan said URI-only but configs have full field sets; URI-first pattern is more complete and backward-compatible
- [04-02]: Teradata dbs_port key — teradatasql Python driver uses dbs_port (not port) for the port parameter; LOW confidence, needs verification against Foundry driver
- [Phase 04-03]: WarehouseConfig Protocol uses TYPE_CHECKING block in dispatcher modules — ruff TC001 correctly flags runtime import of Protocol used only as annotation with __future__ annotations active
- [Phase 04-03]: NOT_FOUND detection via adbc_driver_manager.Error.status_code == AdbcStatusCode.NOT_FOUND (int-enum 3) — more reliable than string matching; secondary 'NOT_FOUND' in str(exc) fallback kept for forward compatibility
- [Phase 04-03]: create_adbc_connection uses explicit keyword args (entrypoint=, db_kwargs=) with type: ignore[arg-type] rather than **dict spread — basedpyright cannot assign dict[str, object] to typed overload parameters
- [Phase 04]: Patch target 'importlib.util.find_spec' (global) — _drivers.py uses module-level import style; plain Exception() bypasses except adbc_driver_manager.Error; SIM117 requires combined with statements
- [04-04]: SnowflakeConfig.schema_ requires model_validate({'schema': 'X'}) in tests — validation_alias='schema' means kwarg schema_='X' raises extra_forbidden ValidationError; established pattern for all validation_alias fields
- [04-04]: FlightSQLConfig() is not empty dict — tls_skip_verify and with_cookie_middleware bool defaults always emit as 'false'/'false' strings; tests assert exact 2-key dict not empty dict
- [05-01]: ConfigurationError dual-inherits PoolhouseError+ValueError — pydantic wraps it in ValidationError (which inherits ValueError), preserving raises ValueError test expectations
- [05-01]: _adbc_entrypoint() is concrete (not abstract) on BaseWarehouseConfig returning None — only DuckDB overrides it; other drivers have no explicit entry point
- [05-01]: ConfigurationError import in _duckdb_config.py uses # noqa: TC001 — runtime import required inside field_validators, not TYPE_CHECKING block
- [05-01]: field_validators added before model_validator — per-field bounds checks fire before cross-field :memory:+pool_size check
- [Phase 05]: ADBC source+clone pattern: create_adbc_connection opens source connection, QueuePool uses source.adbc_clone as factory
- [Phase 05]: pool._adbc_source attached dynamically so callers can close source after pool.dispose()
- [Phase 05]: reset event (not checkin) for Arrow cleanup — reset fires on all return paths including invalidation; checkin receives None on invalidation
- [Phase 05]: TDD RED+GREEN combined in one commit — basedpyright strict mode (includes tests/) fails on unknown imports; RED-only commit blocked by pre-commit hooks

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 4 (Driver Detection): Foundry driver path discovery mechanism in `adbc_driver_manager` is sparsely documented — needs implementation-time research against actual Foundry-installed driver paths (ADBC Driver Foundry launched Oct 2025)
- Phase 6 (Snowflake Snapshots): Custom syrupy serializer design needs validation against real Snowflake ADBC driver response format — metadata field names and Arrow schema structure must be verified before finalising serializer

## Session Continuity

Last session: 2026-02-24
Stopped at: Completed 05-02-PLAN.md — create_pool() factory with ADBC source+clone pattern; Arrow cursor cleanup on reset event; public API exports (create_pool, PoolhouseError, ConfigurationError); 16 new tests; 86 total tests green; Phase 5 complete
Resume file: None
