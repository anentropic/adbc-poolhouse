# Requirements: adbc-poolhouse

**Defined:** 2026-02-23
**Core Value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.

## v1 Requirements

### Setup

Pre-implementation fixes and dependency declarations.

- [x] **SETUP-01**: Fix `pythonVersion = "3.14"` to `"3.11"` in `[tool.basedpyright]` section of `pyproject.toml`
- [x] **SETUP-02**: Add runtime dependencies to `pyproject.toml`: `pydantic-settings>=2.0.0`, `sqlalchemy>=2.0.0`, `adbc-driver-manager>=1.0.0` (open lower bounds only — no upper bound caps; tight `<Y` bounds cause unnecessary consumer dep conflicts for common transitive deps)
- [x] **SETUP-03**: Add per-warehouse optional extras for PyPI-available drivers only: `[duckdb]` (via `duckdb>=0.9.1` package — `adbc_driver_duckdb` is bundled inside the `duckdb` wheel since 0.9.1), `[snowflake]`, `[bigquery]`, `[postgresql]`, `[flightsql]`, `[all]`. Foundry-distributed backends (Databricks, Redshift, Trino, MSSQL, Teradata) are NOT given extras in v1 — those drivers are not on PyPI and will be documented in Phase 7.
- [x] **SETUP-04**: Add `syrupy>=4.0` and `coverage[toml]` to dev dependencies (`unittest.mock` is stdlib — no additional mock dependency needed)
- [x] **SETUP-05**: Add `detect-secrets` to `.pre-commit-config.yaml` (must be active before any Snowflake snapshot commits)

### Config Layer

Typed, validated, environment-variable-friendly warehouse configuration models.

- [x] **CFG-01**: `DuckDBConfig` — Pydantic `BaseSettings` subclass covering all DuckDB ADBC connection parameters; `env_prefix="DUCKDB_"`
- [x] **CFG-02**: `DuckDBConfig` `model_validator` raises `ValueError` when `database=":memory:"` and `pool_size > 1` (each pool connection would get an isolated in-memory database — almost certainly a consumer bug)
- [x] **CFG-03**: `SnowflakeConfig` — Pydantic `BaseSettings` subclass covering all auth methods supported by the installed `adbc-driver-snowflake` (verify against driver source, do not guess); `env_prefix="SNOWFLAKE_"`
- [x] **CFG-04**: `SnowflakeConfig` private key: separate `private_key_path: Path | None` and `private_key_pem: SecretStr | None` fields with a mutual exclusivity validator (a plain `str` field is ambiguous between a file path and PEM content)
- [x] **CFG-05**: Config models for all remaining Apache ADBC backends: `BigQueryConfig`, `PostgreSQLConfig`, `FlightSQLConfig` — each a `BaseSettings` subclass with appropriate `env_prefix`, fields verified against driver docs/source
- [x] **CFG-06**: Config models for all Foundry-distributed backends: `DatabricksConfig`, `RedshiftConfig`, `TrinoConfig`, `MSSQLConfig` (covering Fabric/Synapse variants), `TeradataConfig` — each a `BaseSettings` subclass with appropriate `env_prefix`, fields verified against driver docs/source
- [x] **CFG-07**: All config models: consumer can pass pool tuning kwargs (`pool_size`, `max_overflow`, `timeout`, `recycle`) directly on the config model as optional fields with the library's defaults

### Translation Layer

Maps config model fields to ADBC driver kwargs for `adbc_driver_manager.dbapi.connect()`.

- [x] **TRANS-01**: Translator for `DuckDBConfig` → DuckDB ADBC driver kwargs
- [x] **TRANS-02**: Translator for `SnowflakeConfig` → Snowflake ADBC driver kwargs (all auth methods produce correct kwargs)
- [x] **TRANS-03**: Translators for all remaining Apache backends (`BigQueryConfig`, `PostgreSQLConfig`, `FlightSQLConfig`)
- [x] **TRANS-04**: Translators for all Foundry backends (`DatabricksConfig`, `RedshiftConfig`, `TrinoConfig`, `MSSQLConfig`, `TeradataConfig`)
- [x] **TRANS-05**: All translators are pure functions with no ADBC driver imports (importable even when the target driver is not installed)

### Driver Detection

Locates and loads the correct ADBC driver; all imports are lazy.

- [x] **DRIV-01**: Detect PyPI ADBC driver packages using `importlib.util.find_spec()` (not bare `except ImportError`, which swallows broken native extensions)
- [x] **DRIV-02**: Fall back to `adbc_driver_manager` with the correct `.lib` suffix driver path (e.g. `adbc_driver_snowflake.lib`, not `adbc_driver_snowflake`)
- [x] **DRIV-03**: When neither path succeeds: raise `ImportError` with a human-readable message including the exact install command for the missing driver
- [x] **DRIV-04**: All driver detection and imports are lazy — deferred to `create_pool()` call, never executed at module import time

### Pool Factory

Assembles the `QueuePool`; primary public API.

- [x] **POOL-01**: `create_pool(config) -> QueuePool` — accepts any supported config model, returns a ready-to-use `sqlalchemy.pool.QueuePool`
- [x] **POOL-02**: Default pool settings: `pool_size=5`, `max_overflow=3`, `timeout=30`, `pool_pre_ping=False`, `recycle=3600` (pre-ping disabled — it does not function correctly on a standalone `QueuePool` without a SQLAlchemy dialect; `recycle=3600` is the connection health mechanism)
- [x] **POOL-03**: Consumer can override any pool setting by passing kwargs to `create_pool(config, pool_size=10, ...)`
- [x] **POOL-04**: Arrow memory `reset_agent` event listener registered on pool creation — releases Arrow allocator contexts on connection checkin to prevent memory accumulation in long-running servers
- [x] **POOL-05**: No global state — the library creates no module-level singletons; all pool instances are owned and managed by the consumer

### Type Infrastructure

Isolates all type suppressions to dedicated internal modules.

- [x] **TYPE-01**: `_pool_types.py` internal module — all SQLAlchemy pool interactions that require `cast()` or `# type: ignore` are routed through this single facade (SQLAlchemy pool stubs are incomplete for standalone QueuePool usage)
- [x] **TYPE-02**: `_driver_api.py` internal module — all ADBC driver calls that require `cast()` or `# type: ignore` are routed through this single facade (ADBC driver packages have absent or partial type stubs)

### Testing

- [x] **TEST-01**: DuckDB end-to-end integration tests: pool creation, connection checkout, query execution, pool disposal (no credentials required)
- [x] **TEST-02**: `DuckDBConfig(database=":memory:", pool_size=2)` raises `ValueError` (isolation validator test)
- [ ] **TEST-03**: Snowflake `syrupy` snapshot tests with a custom `SnowflakeArrowSnapshotSerializer` that strips non-deterministic fields (`queryId`, timestamps, `elapsedTime`) before serialization — recorded locally with real credentials, replayed in CI against committed snapshots
- [x] **TEST-04**: Unit tests for all config models: field validation, `SecretStr` handling, `env_prefix` isolation, `model_validator` behaviour
- [x] **TEST-05**: Unit tests for all parameter translators: given a config instance, assert the exact ADBC kwargs dict produced
- [x] **TEST-06**: Unit tests for driver detection with `unittest.mock.patch`: three paths — (a) PyPI package found via `find_spec`, (b) PyPI missing, Foundry path loaded via `adbc_driver_manager`, (c) both missing, correct `ImportError` with install instructions raised
- [x] **TEST-07**: Memory leak validation test for the Arrow `reset_agent` event listener — confirms Arrow allocator contexts are released on connection checkin

### Documentation

- [ ] **DOCS-01**: API reference auto-generated via `mkdocstrings` — all public symbols documented with Google-style docstrings
- [ ] **DOCS-02**: Quickstart guide — install + first working pool in under 5 minutes
- [ ] **DOCS-03**: Consumer patterns — two complete examples: (a) Semantic ORM direct config pattern, (b) dbt-open-sl profiles.yml shim pattern
- [ ] **DOCS-04**: Pool lifecycle guide — when and how to call `pool.dispose()`, fixture teardown pattern for tests, common mistake examples

### Distribution

- [ ] **DIST-01**: PyPI publication via OIDC trusted publisher — register on PyPI before first release using exact workflow filename
- [ ] **DIST-02**: Release workflow validates `py.typed` presence in built wheel (`zipinfo dist/*.whl | grep py.typed`)
- [ ] **DIST-03**: Release workflow generates changelog via `git-cliff` (`.cliff.toml` already present)

### Project Tooling

- [ ] **TOOL-01**: Project-specific docs writing skill at `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — adapted from the cubano docs author skill (content TBD before docs phase begins)
- [ ] **TOOL-02**: `CLAUDE.md` instruction: for all plans in phases ≥ 7 (not only plans labelled as documentation tasks), include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>` — documentation is a quality gate for every phase from Phase 7 onwards

---

## v2 Requirements

### Testing

- **TEST-V2-01**: Live integration tests for non-DuckDB, non-Snowflake backends — blocked on test account availability
- **TEST-V2-02**: Async pool support — blocked on ADBC adding async dbapi interface

### Warehouses

- **WARE-V2-01**: BigQuery Foundry driver variant (currently available as both Apache and Foundry; Apache in v1, Foundry variant deferred)

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-pool management | Consumers call `create_pool()` per warehouse and manage the dict themselves |
| Query execution | Pool gives a connection; consumers decide what to execute |
| dbt / profiles.yml knowledge | dbt-open-sl provides its own translation shim |
| REST / HTTP / Flight SQL serving | Not a connection pool concern |
| OAuth / SSO auth logic | Delegated entirely to ADBC drivers |
| Async connection pools | ADBC DBAPI is synchronous; async pool requires async DBAPI |
| Automatic pool discovery / registry | Out of scope — no global state |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SETUP-01 | Phase 1 | Complete |
| SETUP-05 | Phase 1 | Complete |
| SETUP-02 | Phase 2 | Complete |
| SETUP-03 | Phase 2 | Complete |
| SETUP-04 | Phase 2 | Complete |
| CFG-01 | Phase 3 | Complete |
| CFG-02 | Phase 3 | Complete |
| CFG-03 | Phase 3 | Complete |
| CFG-04 | Phase 3 | Complete |
| CFG-05 | Phase 3 | Complete |
| CFG-06 | Phase 3 | Complete |
| CFG-07 | Phase 3 | Complete |
| TEST-04 | Phase 3 | Complete |
| TRANS-01 | Phase 4 | Complete |
| TRANS-02 | Phase 4 | Complete |
| TRANS-03 | Phase 4 | Complete |
| TRANS-04 | Phase 4 | Complete |
| TRANS-05 | Phase 4 | Complete |
| DRIV-01 | Phase 4 | Complete |
| DRIV-02 | Phase 4 | Complete |
| DRIV-03 | Phase 4 | Complete |
| DRIV-04 | Phase 4 | Complete |
| TYPE-01 | Phase 4 | Complete |
| TYPE-02 | Phase 4 | Complete |
| TEST-05 | Phase 4 | Complete |
| TEST-06 | Phase 4 | Complete |
| POOL-01 | Phase 5 | Complete |
| POOL-02 | Phase 5 | Complete |
| POOL-03 | Phase 5 | Complete |
| POOL-04 | Phase 5 | Complete |
| POOL-05 | Phase 5 | Complete |
| TEST-01 | Phase 5 | Complete |
| TEST-02 | Phase 5 | Complete |
| TEST-07 | Phase 5 | Complete |
| TEST-03 | Phase 6 | Pending |
| TOOL-01 | Phase 7 | Pending |
| TOOL-02 | Phase 7 | Pending |
| DOCS-01 | Phase 7 | Pending |
| DOCS-02 | Phase 7 | Pending |
| DOCS-03 | Phase 7 | Pending |
| DOCS-04 | Phase 7 | Pending |
| DIST-01 | Phase 7 | Pending |
| DIST-02 | Phase 7 | Pending |
| DIST-03 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 44 total
- Mapped to phases: 44
- Unmapped: 0

---
*Requirements defined: 2026-02-23*
*Last updated: 2026-02-23 — traceability populated after roadmap creation*
