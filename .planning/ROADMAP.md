# Roadmap: adbc-poolhouse

## Overview

Starting from a complete scaffold with zero production code, seven phases build the library from pre-flight fixes through PyPI publication. Each phase completes one coherent capability before the next begins: fix the broken toolchain config, declare dependencies, build typed config models, wire translation and driver detection, assemble the pool factory with DuckDB integration tests, add Snowflake snapshot tests, then publish. The public API — `create_pool(config)` — is delivered in Phase 4 and validated end-to-end before any documentation or publication work begins.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Pre-flight Fixes** - Correct broken toolchain config and add detect-secrets before any implementation begins
- [x] **Phase 2: Dependency Declarations** - Declare runtime deps, optional warehouse extras, and missing dev deps in pyproject.toml (completed 2026-02-23)
- [x] **Phase 3: Config Layer** - Build typed Pydantic BaseSettings config models for all warehouses plus exceptions (completed 2026-02-24)
- [x] **Phase 4: Translation and Driver Detection** - Pure translation functions, lazy driver resolution, and typed facades isolating type suppressions (completed 2026-02-24)
- [x] **Phase 5: Pool Factory and DuckDB Integration** - Assemble the public `create_pool()` API and validate it end-to-end with DuckDB tests (completed 2026-02-24)
- [ ] **Phase 6: Snowflake Integration** - Add syrupy snapshot tests for Snowflake with a custom serializer stripping non-deterministic fields
- [ ] **Phase 7: Documentation and PyPI Publication** - Write docs skill, author all guides, and publish to PyPI via OIDC trusted publisher

## Phase Details

### Phase 1: Pre-flight Fixes
**Goal**: The toolchain is correctly configured and no pre-existing config errors will silently corrupt any implementation work that follows
**Depends on**: Nothing (first phase)
**Requirements**: SETUP-01, SETUP-05
**Success Criteria** (what must be TRUE):
  1. `basedpyright` reports `pythonVersion = "3.11"` in `pyproject.toml` — no 3.13+ type features pass silently
  2. `detect-secrets` is active in `.pre-commit-config.yaml` and runs on every commit
  3. `prek` passes with zero violations on the unchanged codebase after both fixes
**Plans**: 1 plan

Plans:
- [x] 01-01-PLAN.md — Fix basedpyright pythonVersion, add detect-secrets hook + baseline, verify prek gate

### Phase 2: Dependency Declarations
**Goal**: All runtime and dev dependencies are declared in `pyproject.toml`, version-resolved with `uv`, and the lock file reflects the complete dependency graph
**Depends on**: Phase 1
**Requirements**: SETUP-02, SETUP-03, SETUP-04
**Success Criteria** (what must be TRUE):
  1. `uv sync` succeeds with the new lock file — pydantic-settings, sqlalchemy, adbc-driver-manager, syrupy, and coverage are all resolvable
  2. `pip install adbc-poolhouse[duckdb]` installs only the DuckDB optional extra (no other warehouse driver pulled in)
  3. `pip install adbc-poolhouse[snowflake]` installs only the Snowflake optional extra
  4. `pip install adbc-poolhouse[all]` installs all warehouse extras
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — Add runtime deps, optional extras, dev deps to pyproject.toml; update REQUIREMENTS.md
- [x] 02-02-PLAN.md — Validate uv resolution, commit uv.lock, verify prek gate

### Phase 3: Config Layer
**Goal**: Consumers can construct typed, validated, environment-variable-friendly warehouse config objects for every supported backend without importing any ADBC or SQLAlchemy code
**Depends on**: Phase 2
**Requirements**: CFG-01, CFG-02, CFG-03, CFG-04, CFG-05, CFG-06, CFG-07, TEST-04
**Success Criteria** (what must be TRUE):
  1. `DuckDBConfig(database=":memory:")` constructs successfully; `DuckDBConfig(database=":memory:", pool_size=2)` raises `ValueError`
  2. `SnowflakeConfig` accepts `private_key_path` or `private_key_pem` but not both simultaneously; ambiguous string field is absent
  3. All config models load values from environment variables using their correct `env_prefix` (e.g. `SNOWFLAKE_ACCOUNT` populates `SnowflakeConfig.account`)
  4. `from adbc_poolhouse import DuckDBConfig, SnowflakeConfig` succeeds in a Python environment with only pydantic-settings installed — no ADBC driver required at import time
  5. All config model unit tests pass (field validation, SecretStr handling, env_prefix isolation, model_validator behaviour)
**Plans**: 7 plans

Plans:
- [x] 03-01-PLAN.md — Base config (BaseWarehouseConfig + WarehouseConfig Protocol) + DuckDBConfig with in-memory validator
- [x] 03-02-PLAN.md — SnowflakeConfig with full Snowflake ADBC parameter set and private key mutual exclusion
- [x] 03-03-PLAN.md — Apache backends: BigQueryConfig, PostgreSQLConfig, FlightSQLConfig
- [x] 03-04-PLAN.md — Foundry backends part 1: DatabricksConfig, RedshiftConfig, TrinoConfig
- [x] 03-05-PLAN.md — Foundry backends part 2: MSSQLConfig, TeradataConfig (LOW confidence fields)
- [x] 03-06-PLAN.md — Public API: update __init__.py with all config model re-exports
- [x] 03-07-PLAN.md — TDD unit tests for all config models (TEST-04)

### Phase 4: Translation and Driver Detection
**Goal**: Given a config object, the library can produce exact ADBC driver kwargs and resolve the correct driver binary — all without executing any driver code at module import time
**Depends on**: Phase 3
**Requirements**: TRANS-01, TRANS-02, TRANS-03, TRANS-04, TRANS-05, DRIV-01, DRIV-02, DRIV-03, DRIV-04, TYPE-01, TYPE-02, TEST-05, TEST-06
**Success Criteria** (what must be TRUE):
  1. Translator unit tests pass: given a config instance, each translator returns the exact expected `dict[str, str]` of ADBC kwargs with no ADBC driver installed
  2. Driver detection unit tests pass all three paths: (a) PyPI package found via `find_spec`, (b) PyPI absent but Foundry path loads via `adbc_driver_manager`, (c) both absent raises `ImportError` with the exact install command
  3. `import adbc_poolhouse` in a bare environment (no warehouse drivers installed) raises no error — all driver imports are lazy
  4. All `cast()` and `# type: ignore` suppressions are contained exclusively in `_pool_types.py` and `_driver_api.py` — zero suppressions in public modules
**Plans**: 5 plans

Plans:
- [x] 04-01-PLAN.md — DuckDB + Apache translators (translate_duckdb, translate_bigquery, translate_postgresql, translate_flightsql)
- [x] 04-02-PLAN.md — Snowflake + Foundry translators (translate_snowflake, translate_databricks, translate_redshift, translate_trino, translate_mssql, translate_teradata)
- [x] 04-03-PLAN.md — Wiring layer: _translators.py coordinator, _drivers.py detection, _driver_api.py ADBC facade, _pool_types.py type scaffold
- [x] 04-04-PLAN.md — TDD: translator unit tests (TEST-05)
- [x] 04-05-PLAN.md — TDD: driver detection unit tests (TEST-06)

### Phase 5: Pool Factory and DuckDB Integration
**Goal**: `create_pool(config)` is the complete, working public API — consumers can call it with a DuckDB config and get back a functional QueuePool
**Depends on**: Phase 4
**Requirements**: POOL-01, POOL-02, POOL-03, POOL-04, POOL-05, TEST-01, TEST-02, TEST-07
**Success Criteria** (what must be TRUE):
  1. `pool = create_pool(DuckDBConfig(database="/tmp/test.db"))` returns a `sqlalchemy.pool.QueuePool` — connection checkout, query execution, and pool disposal all work end-to-end
  2. `create_pool(config, pool_size=10, recycle=7200)` overrides defaults; default pool is `pool_size=5, max_overflow=3, timeout=30, pre_ping=False, recycle=3600`
  3. Arrow allocator contexts are released on connection checkin — memory leak validation test passes with no accumulation after repeated checkin cycles
  4. No module-level singletons exist — importing `adbc_poolhouse` does not create any pool or connection object
  5. `DuckDBConfig(database=":memory:", pool_size=2)` raises `ValueError` before `create_pool()` is ever called
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md — Exception hierarchy (_exceptions.py) + config layer updates (_base_config.py, _duckdb_config.py)
- [x] 05-02-PLAN.md — TDD: pool factory implementation (_pool_factory.py) + public API exports (__init__.py)

### Phase 6: Snowflake Integration
**Goal**: Snowflake connection tests are committed as syrupy snapshots that CI can replay without credentials — real credentials used only for local snapshot recording
**Depends on**: Phase 5
**Requirements**: TEST-03
**Success Criteria** (what must be TRUE):
  1. Snowflake integration tests pass in CI by replaying committed snapshots — no Snowflake credentials required in CI
  2. Snapshot files contain no credential residue (no account identifiers, usernames, or tokens visible in committed snapshot data)
  3. `SnowflakeArrowSnapshotSerializer` strips `queryId`, timestamps, and `elapsedTime` before serialization — snapshot update with a new Snowflake account produces identical snapshot content (non-deterministic fields absent)
**Plans**: 1 plan

Plans:
- [ ] 06-01-PLAN.md — SnowflakeArrowSnapshotSerializer + conftest fixtures + integration tests + CONTRIBUTING.md recording workflow

### Phase 7: Documentation and PyPI Publication
**Goal**: The library is documented, pip-installable, and live on PyPI — and the docs-author skill + CLAUDE.md quality gate are in place so all future phases keep documentation current as a completion requirement
**Depends on**: Phase 6
**Requirements**: TOOL-01, TOOL-02, DOCS-01, DOCS-02, DOCS-03, DOCS-04, DIST-01, DIST-02, DIST-03
**Success Criteria** (what must be TRUE):
  1. `pip install adbc-poolhouse` succeeds from PyPI; the installed wheel contains `py.typed`
  2. `mkdocs serve` builds the docs site without errors — all public symbols have API reference entries generated from Google-style docstrings
  3. The quickstart guide produces a working DuckDB pool in a fresh virtualenv following the documented steps exactly
  4. The release workflow generates a changelog via `git-cliff` and validates `py.typed` presence in the wheel before publishing
  5. The docs-author skill exists at `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` and `CLAUDE.md` instructs plan-phase to include it for all plans in phases ≥ 7 (documentation is a quality gate, not an optional task)
**Plans**: TBD

## Quality Gates

**Applies from Phase 7 onwards (including all future milestones):**

Every phase from Phase 7 onward must include documentation as a completion requirement. A phase is not complete until:
- All new public symbols have Google-style docstrings and appear in the API reference
- Any new consumer-facing behaviour is reflected in the relevant guide (quickstart, consumer patterns, pool lifecycle)
- `mkdocs serve` builds without errors after the phase's changes

This gate is enforced via `CLAUDE.md`: plan-phase includes `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>` for all plans in phases ≥ 7 (not only plans explicitly labelled as documentation tasks).

The docs-author skill and CLAUDE.md instruction are established in Phase 7 (TOOL-01, TOOL-02).

---

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Pre-flight Fixes | 1/1 | Complete | 2026-02-23 |
| 2. Dependency Declarations | 2/2 | Complete   | 2026-02-23 |
| 3. Config Layer | 7/7 | Complete   | 2026-02-24 |
| 4. Translation and Driver Detection | 5/5 | Complete   | 2026-02-24 |
| 5. Pool Factory and DuckDB Integration | 2/2 | Complete   | 2026-02-24 |
| 6. Snowflake Integration | 0/1 | Not started | - |
| 7. Documentation and PyPI Publication | 0/TBD | Not started | - |
