# Project Research Summary

**Project:** adbc-poolhouse
**Domain:** Python library — ADBC connection pooling for data warehouse workloads
**Researched:** 2026-02-23
**Confidence:** MEDIUM-HIGH

## Executive Summary

adbc-poolhouse is a thin translation and wiring library: receive a typed warehouse config, translate it to ADBC driver kwargs, resolve the right driver binary, and hand the resulting connection factory to SQLAlchemy QueuePool. The core architectural insight — that QueuePool's `creator` pattern is a perfect fit for ADBC's `adbc_driver_manager.dbapi.connect()` — means this library does not need to build a pool from scratch. The design decisions already documented in `_notes/design-discussion.md` are correct: pydantic-settings for config, SQLAlchemy QueuePool for pooling, uv for tooling, basedpyright strict for type checking. Research confirms these choices and identifies no direction-reversing issues.

The recommended approach is a strict layered architecture with four modules — config models, parameter translation, driver detection, and pool factory — where each layer depends only on layers below it. The public API surface is a single function `create_pool(config)` plus the config model classes. All driver imports are lazy (deferred to `create_pool()` call time, never at module import). The library's differentiation comes from the Config and Translation layers; the Pool Factory layer is mostly delegation to SQLAlchemy.

The key risks are concentrated in the earliest implementation work: the `pythonVersion = "3.14"` in basedpyright must be corrected to `"3.11"` before any code is written, lazy driver detection architecture must be locked before structuring modules, and the ADBC driver typing facade must be built before the pool factory. An additional cluster of non-obvious risks surrounds the `pre_ping` parameter (it does not function correctly on a standalone QueuePool without a dialect), DuckDB `:memory:` isolation (each pool connection gets a separate empty database), and syrupy snapshot hygiene for Snowflake tests.

## Key Findings

### Recommended Stack

The stack is largely already in place and confirmed correct. Runtime dependencies (`pydantic-settings>=2.7,<3`, `sqlalchemy>=2.0,<3`, `adbc-driver-manager>=1.0,<2`) need to be added to `pyproject.toml` — currently `dependencies = []`. Two dev dependencies are missing: `pytest-mock>=3.14` (needed for mocking `importlib.import_module` in driver detection tests) and `syrupy>=4.0` (required by the Snowflake snapshot test strategy). ADBC driver packages should be optional extras, not hard deps. Two pre-existing config issues must be fixed before implementation: `pythonVersion = "3.14"` in basedpyright (should be `"3.11"`), and `{{ cookiecutter.package_name }}` in `release.yml` line 67 (must become `adbc_poolhouse`).

**Core technologies:**
- `pydantic-settings>=2.7,<3`: typed warehouse config with env-var integration — best-in-class for library config APIs in 2025
- `sqlalchemy>=2.0,<3` (pool submodule only): QueuePool provides battle-tested thread-safe pooling via the `creator` pattern — avoids reinventing 15 years of production hardening
- `adbc-driver-manager>=1.0,<2`: universal ADBC driver loader for both PyPI and Foundry (Databricks, Redshift, Trino) distribution channels — always a required hard dep
- `pytest-mock>=3.14`: mocker fixture for intercepting `importlib.import_module` in driver detection tests — not yet in dev deps, needed
- `syrupy>=4.0`: snapshot testing for Snowflake — explicitly called out in PROJECT.md test strategy

### Expected Features

The feature space for connection pool libraries is well-understood. adbc-poolhouse's differentiation is not in re-implementing pool mechanics (SQLAlchemy handles those) but in the Config and Translation layers that make ADBC + data warehouse access ergonomic.

**Must have (table stakes):**
- Configurable pool size (`pool_size`, `max_overflow`, `timeout`, `recycle`) — delegated to QueuePool
- Connection health via `recycle=3600` default — tuned for warehouse auth token lifetimes, not just server idle timeouts
- Thread-safe checkout/return — QueuePool provides; consumers must not share checked-out connections across threads
- Typed warehouse config models with env-var support — `SnowflakeConfig`, `DuckDBConfig` as Pydantic BaseSettings
- ADBC driver kwargs translation — config fields to driver-specific string kwargs
- Driver detection with dual channel support — try PyPI import, fall back to Foundry shared library path
- Helpful `DriverNotInstalledError` with install instructions — critical DX element
- Pool disposal — `pool.dispose()` for clean teardown; consumer responsibility but must be documented prominently

**Should have (differentiators):**
- `create_pool(config)` one-call API — no DSN string wrangling, no manual kwarg construction
- Explicit `env_prefix` per config model — prevents silent env var collision (e.g. `DATABASE` from Heroku colliding with `DuckDBConfig.database`)
- DuckDB `:memory:` pool_size warning — `UserWarning` when `pool_size > 1` with `:memory:` since connections are isolated
- `login_timeout_seconds` field on `SnowflakeConfig` — prevents indefinite hangs when Snowflake is unreachable
- Public `DriverNotInstalledError` in `__all__` — consumers need to catch it by name
- `BaseWarehouseConfig` exported — consumers and downstream libraries (dbt-open-sl) use it as a type annotation

**Defer to v2+:**
- BigQuery, PostgreSQL, Databricks, Redshift, Trino, MSSQL backends — adding before DuckDB + Snowflake are solid increases test burden
- Async pool — ADBC dbapi is synchronous; correct async requires asyncio-native DBAPI which does not exist yet
- Built-in metrics/stats — SQLAlchemy events let consumers instrument themselves
- Multi-pool registry / warehouse router — consumer business logic, not library concern
- Background connection prefill — complexity without clear benefit for batch/warehouse workloads

### Architecture Approach

adbc-poolhouse is structured as four strictly layered modules with a unidirectional dependency graph. The public API (`create_pool` + config models) is re-exported from `__init__.py`; internal modules use underscore prefixes. Config models are leaf nodes (only pydantic-settings, no driver imports). The factory is the only module that imports SQLAlchemy. All ADBC driver imports are lazy (inside functions, guarded by try/except), never at module scope. A typed driver facade (`_driver_api.py`) isolates all `type: ignore` suppressions needed to bridge ADBC's untyped packages with basedpyright strict mode.

**Major components:**
1. `_config_base.py` + `config_duckdb.py` + `config_snowflake.py` — Pydantic BaseSettings config models; leaf nodes, no ADBC or SQLAlchemy imports; Pydantic validates fields at construction time before any network call
2. `_translators.py` — pure Python dict construction mapping config fields to ADBC driver-specific string kwargs (`adbc.snowflake.sql.account` etc.); no external deps beyond config models
3. `_drivers.py` — lazy driver resolution: `importlib.util.find_spec()` check before import attempt (to distinguish "not installed" from "installed but broken"), then Foundry shared library fallback, then `DriverNotInstalledError` with actionable install message
4. `factory.py` — wires translator + driver resolver into a `creator` closure, constructs `QueuePool` with `pre_ping=False` (pre_ping requires a SQLAlchemy dialect; standalone QueuePool silently no-ops it), returns the pool to the consumer
5. `_exceptions.py` — leaf node; `DriverNotInstalledError(ImportError)` and `DriverResolutionError(RuntimeError)` with no internal imports

### Critical Pitfalls

1. **`pre_ping=True` silently no-ops on standalone QueuePool** — `pre_ping` requires a SQLAlchemy dialect to call `dialect.do_ping()`; without an engine, it does nothing. Use `pre_ping=False` and rely on `recycle=3600` for connection health. This is a hard default change from the design notes.

2. **`pythonVersion = "3.14"` in basedpyright passes 3.13+ features silently** — code using `TypeVar(default=)` (PEP 696, 3.13+) or `typing.override` (3.12+) will pass type checking but fail at runtime on Python 3.11. Fix to `"3.11"` before writing a single line.

3. **Bare `except ImportError` on driver detection hides broken installations** — if `adbc_driver_snowflake` is installed but has an ABI mismatch, the ImportError is swallowed and falls through to "driver not found," giving a misleading error. Use `importlib.util.find_spec()` first: if the spec exists, import and let the error propagate; if the spec is absent, use the Foundry fallback.

4. **DuckDB `:memory:` is connection-scoped** — each pool connection gets its own isolated empty database. Tests using `pool_size=1` pass; tests using `pool_size=2` fail with "table not found." Always use a named temp file for multi-connection DuckDB pool tests. Add a `model_validator` warning when `database=":memory:"` and `pool_size > 1`.

5. **Syrupy snapshots will contain non-deterministic Snowflake metadata** — `queryId`, `creationTime`, `elapsedTime` fields change on every run. Build a custom `SnowflakeArrowSnapshotSerializer` that strips these before serialization. Also audit snapshot files for credential residue (account identifier, username) before any commit.

## Implications for Roadmap

Based on research, the dependency graph dictates a clear build order. Each layer can be tested in isolation before the next is built. No phase requires reversing an earlier decision.

### Phase 1: Pre-flight Fixes
**Rationale:** Two pre-existing config issues block all subsequent work. Must be resolved before any implementation code is written — they affect every downstream phase.
**Delivers:** Correct basedpyright config targeting the minimum supported Python version; a release workflow free of cookiecutter artifacts.
**Addresses:** PITFALL-21 (`pythonVersion = "3.11"`); `release.yml` cookiecutter placeholder.
**Avoids:** Silent 3.13+ type feature acceptance that fails at runtime on 3.11; a broken first release.

### Phase 2: Dependency Declarations
**Rationale:** `pyproject.toml` currently has `dependencies = []`. All subsequent implementation requires these runtime deps to be installable. Adding them now also confirms version resolution with `uv`.
**Delivers:** Updated `pyproject.toml` with runtime deps, optional extras per warehouse, and the two missing dev deps (`pytest-mock`, `syrupy`). A passing `uv sync` with the new lock file.
**Uses:** Stack recommendations from STACK.md — exact version ranges confirmed.
**Avoids:** PITFALL-14 (document SQLAlchemy full-package dependency in README).

### Phase 3: Config Layer
**Rationale:** Config models are the input to every other component. They have zero external ADBC or SQLAlchemy dependencies, making them the fastest to build and test. All downstream layers take config objects as input.
**Delivers:** `_config_base.py`, `config_duckdb.py`, `config_snowflake.py`, `_exceptions.py` — all with unit tests covering valid construction, env var overrides, validation errors, and immutability.
**Implements:** Config layer architecture component.
**Avoids:** PITFALL-9 (SecretStr None handling), PITFALL-10 (env_prefix collision), PITFALL-11 (Snowflake private key PEM vs Path), PITFALL-12 (model_config inheritance), PITFALL-24 (DuckDB :memory: warning).

### Phase 4: Driver Detection and Translation
**Rationale:** These two layers are independent of each other and of SQLAlchemy — both depend only on the config layer. Driver detection uses `importlib.util.find_spec()` + lazy imports; translation is pure dict construction. Both are fully testable with mocks and no real drivers.
**Delivers:** `_translators.py` (config → ADBC kwargs), `_drivers.py` (PyPI + Foundry driver resolution), `_driver_api.py` (typed facade isolating `type: ignore`), with unit tests using `pytest-mock`.
**Implements:** Translation and Driver Detection architecture components.
**Avoids:** PITFALL-6 (bare ImportError swallowing), PITFALL-7 (driver module path vs package name), PITFALL-8 (lazy import enforcement), PITFALL-23 (ADBC typing facade).

### Phase 5: Pool Factory and DuckDB Integration
**Rationale:** With config, translation, and driver detection solid, the factory layer only needs to wire them together and pass the result to QueuePool. DuckDB requires no credentials and tests the full end-to-end flow without CI secrets.
**Delivers:** `factory.py` with `create_pool()`, updated `__init__.py`, DuckDB integration tests verifying pool construction, connection checkout, basic query execution, and pool disposal.
**Uses:** SQLAlchemy QueuePool `creator` pattern; `pre_ping=False` default (PITFALL-3 / PITFALL-22).
**Avoids:** PITFALL-1 (zero-arg creator closure), PITFALL-2 (connection thread safety docs), PITFALL-4 (Arrow memory release on checkin), PITFALL-5 (pool checkout timeout vs driver connect timeout), PITFALL-25 (pool.dispose() fixture teardown pattern).

### Phase 6: Snowflake Integration and Snapshot Tests
**Rationale:** Snowflake requires real credentials (CI secrets) and more complex auth config. Building it after DuckDB means the full pool machinery is validated before adding the credential and snapshot complexity.
**Delivers:** Snowflake connection tests, syrupy snapshot infrastructure with `SnowflakeArrowSnapshotSerializer` (strips non-deterministic metadata), snapshot update workflow documentation, CI Snowflake test job.
**Uses:** `syrupy>=4.0`; GitHub Actions secrets for Snowflake credentials.
**Avoids:** PITFALL-17 (non-deterministic snapshot fields), PITFALL-18 (snapshot update workflow hygiene), PITFALL-19 (credential residue in snapshots), PITFALL-20 (Linux-only CI for Snowflake).

### Phase 7: PyPI Publication
**Rationale:** Publication is deferred until the library is functionally complete and tested. Several publication-specific checks must be added to the release workflow.
**Delivers:** First PyPI release with verified wheel contents, `py.typed` marker included, OIDC trusted publisher configured, release workflow cookiecutter artifact resolved.
**Avoids:** PITFALL-13 (optional extras Python version validation), PITFALL-15 (py.typed in wheel), PITFALL-16 (OIDC trusted publisher registration).

### Phase Ordering Rationale

- Config before translation and drivers: all downstream modules take config objects as input; testing them in isolation is fast and requires only pydantic-settings.
- Translation and drivers before factory: factory is a wiring layer; its integration tests catch wiring mistakes, not component mistakes. Build components first.
- DuckDB before Snowflake: DuckDB requires no credentials; validates the full pool machinery before adding auth complexity.
- Publication last: ensures all pre-publication checks (py.typed, OIDC registration, cookiecutter cleanup) happen after the library is functionally stable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Driver Detection):** The ADBC Foundry driver path discovery mechanism (`adbc_driver_manager` Foundry lookup) needs implementation-time research against actual Foundry-installed driver paths. The ADBC Driver Foundry launched October 2025; exact API for programmatic path discovery may require consulting the `adbc_driver_manager` C extension documentation directly.
- **Phase 6 (Snowflake Snapshots):** The custom syrupy serializer for Arrow RecordBatch results needs experimentation with the actual Snowflake ADBC driver response format. Metadata field names and Arrow schema structure should be verified against a real connection before finalizing the serializer design.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Pre-flight Fixes):** Mechanical config file changes; no research needed.
- **Phase 2 (Dependency Declarations):** Version ranges are confirmed; `uv add` and `uv sync` are sufficient.
- **Phase 3 (Config Layer):** Pydantic BaseSettings patterns are well-documented and confirmed. The pitfalls (SecretStr, env_prefix, model_config inheritance) are understood and solvable with known Pydantic patterns.
- **Phase 5 (Pool Factory):** SQLAlchemy QueuePool `creator` pattern is extensively documented. The `pre_ping=False` decision is made. DuckDB integration tests are straightforward.
- **Phase 7 (PyPI Publication):** OIDC trusted publishing, wheel validation, and release workflow patterns are standard and documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All core stack choices are confirmed from `uv.lock` resolved at research date plus direct PyPI version knowledge. Two additions (pytest-mock, syrupy) are MEDIUM — versions are well-known, no compatibility concerns. |
| Features | HIGH | Feature taxonomy derived from SQLAlchemy, psycopg3, asyncpg pool documentation plus ADBC-specific analysis. The table stakes / differentiator / anti-feature split is well-supported. |
| Architecture | HIGH | The `creator` pattern is a first-class SQLAlchemy API. The layered module design is consistent with the existing codebase skeleton. The `pre_ping=False` recommendation is a documented SQLAlchemy behaviour, not an inference. |
| Pitfalls | MEDIUM | Critical pitfalls (pre_ping, pythonVersion, ImportError swallowing, DuckDB :memory: isolation) are well-grounded. The Foundry driver path discovery mechanism and syrupy Arrow serializer design are less certain — these require implementation-time validation. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Foundry driver path discovery:** How `adbc_driver_manager` programmatically locates Foundry-installed shared libraries is not fully specified in public documentation. The `_drivers.py` Foundry fallback path needs to be validated against an actual Foundry-installed driver during Phase 4.
- **ADBC `db_kwargs` type constraint:** Research notes that all `db_kwargs` values must be `str`. Some ADBC driver parameters (booleans, integers) may technically accept non-string types. The translator's return type (`dict[str, str]`) should be verified against driver documentation for DuckDB and Snowflake before finalizing the translation layer.
- **Snowflake private key format:** The ADBC Snowflake driver's expected format for the private key field (PEM string, DER bytes, or file path) needs verification against `adbc-driver-snowflake` documentation during Phase 3/6. Research recommends separate `private_key_path` and `private_key_pem` fields as the safe approach pending this verification.
- **Arrow memory release on pool checkin:** PITFALL-4 identifies that ADBC connections hold Arrow allocators that may not be released on QueuePool checkin. A custom reset event listener may be needed. The correct approach should be prototyped during Phase 5 and validated with a memory-usage test before declaring the pool factory complete.

## Sources

### Primary (HIGH confidence)
- `uv.lock` (resolved 2026-02-23) — confirmed versions: pytest 9.0.2, pytest-cov 7.0.0, basedpyright 1.38.1, ruff 0.15.2
- `pyproject.toml`, `_notes/design-discussion.md`, `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md` — project design constraints and existing decisions
- SQLAlchemy pool documentation (`sqlalchemy.pool.QueuePool`, `sqlalchemy.pool.events`) — QueuePool creator pattern, pre_ping behaviour
- psycopg3 / psycopg-pool documentation — `ConnectionPool`, `stats()`, background prefill patterns
- asyncpg documentation — `asyncpg.create_pool`, pool-as-executor pattern (deliberately not adopted)

### Secondary (MEDIUM confidence)
- Apache Arrow ADBC documentation and driver packages — `adbc_driver_manager.dbapi.connect()` call patterns, db_kwargs structure, PyPI vs Foundry driver paths
- ADBC Driver Foundry documentation (launched Oct 2025) — dual-channel driver distribution model
- PyPI state at research date — version numbers for pydantic-settings, sqlalchemy, adbc-driver-manager, adbc-driver-snowflake, syrupy

### Tertiary (LOW confidence)
- ADBC Foundry programmatic path discovery — sparse documentation; needs implementation-time validation
- `adbc-driver-snowflake` Windows wheel availability — reported as historically incomplete; current state unconfirmed

---
*Research completed: 2026-02-23*
*Ready for roadmap: yes*
