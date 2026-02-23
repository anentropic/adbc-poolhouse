# adbc-poolhouse

## What This Is

A focused Python library that takes a typed warehouse configuration and returns a pooled ADBC connection. Extracted from `dbt-open-sl` as shared infrastructure needed by two consumers: `dbt-open-sl` (profiles.yml → ADBC) and a planned Semantic ORM (direct config). Published to PyPI for pip-installable use.

## Core Value

One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.

## Requirements

### Validated

- ✓ Package scaffold at `src/adbc_poolhouse/` with PEP 561 marker — existing
- ✓ Toolchain: uv, ruff, basedpyright strict, prek pre-commit — existing
- ✓ Docs infrastructure: mkdocs-material + mkdocstrings — existing
- ✓ CI: GitHub Actions, Python 3.11 + 3.14 matrix — existing
- ✓ Cliff.toml changelog generation — existing

### Active

- [ ] Pydantic BaseSettings config models for DuckDB and Snowflake
- [ ] Parameter translation layer (config fields → ADBC driver kwargs) for DuckDB and Snowflake
- [ ] Driver detection: try PyPI package import, fall back to `adbc_driver_manager`
- [ ] Helpful error messages when required ADBC driver is not installed
- [ ] `create_pool(config, **pool_kwargs)` factory function as primary public API
- [ ] Pool defaults: size=5, max_overflow=3, timeout=30s, pre_ping=True, recycle=3600s
- [ ] Overridable pool settings via kwargs to `create_pool()`
- [ ] DuckDB integration tests (in-process, no credentials needed)
- [ ] Snowflake snapshot tests via syrupy (recorded locally with real creds, replayed in CI)
- [ ] Full API reference via mkdocstrings (auto-generated from Google-style docstrings)
- [ ] Usage guide: quickstart + both consumer patterns (Semantic ORM and dbt-open-sl shim)
- [ ] PyPI publication at `pip install adbc-poolhouse`

### Out of Scope

- Multi-pool management — consumers call `create_pool()` per warehouse and manage the dict themselves
- Query execution — pool gives a connection, consumers execute
- Knowledge of dbt, profiles.yml, semantic layers, or MetricFlow
- REST/HTTP/Flight SQL serving
- BigQuery, PostgreSQL, Databricks, Redshift, Trino, MSSQL — all Future warehouses
- OAuth / SSO auth logic — delegated entirely to ADBC drivers
- Async connection pools — ADBC dbapi is synchronous; async is out of scope for v1

## Context

Extracted from `dbt-open-sl` during initialization (2026-02-23) when it became clear two consumers needed the same ADBC config + pool layer. The codebase has a full scaffold (tooling, CI, docs infra) but zero production code — all implementation is greenfield within the existing structure.

Two concrete consumers waiting:
1. **dbt-open-sl** — provides a `translate_to_poolhouse_config()` shim from `profiles.yml` to this lib's config models
2. **Semantic ORM** (planned) — uses the config models directly as its own user-facing config

ADBC Driver Foundry (launched Oct 2025) provides drivers for warehouses not on PyPI (Databricks, Redshift, Trino, etc.) via `dbc` CLI + `adbc_driver_manager`. v1 targets only the two Apache ADBC drivers (`duckdb`, `adbc-driver-snowflake`); the Foundry detection path is implemented but exercised by future warehouse additions.

Snowflake integration tests use syrupy snapshots: recorded locally against a real Snowflake account, committed to the repo, replayed in CI without credentials.

## Constraints

- **Python**: ≥3.11 (`requires-python = ">=3.11"` in pyproject.toml)
- **Type safety**: basedpyright strict mode — all public API must be fully typed
- **SQLAlchemy**: pool submodule only (`sqlalchemy.pool`, `sqlalchemy.event`) — NOT the ORM
- **No global state**: library has no module-level singletons; consumers own all pool instances
- **License**: Apache 2.0

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Pydantic BaseSettings for config | Typed, validated, env-var support comes free | — Pending |
| SQLAlchemy QueuePool (not hand-rolled) | Battle-tested thread-safe pool; imports only pool submodule | — Pending |
| One pool per call, no multi-warehouse routing | Keep lib simple; routing is consumer business logic | — Pending |
| Config + pool only, no execution | Execution semantics differ per consumer | — Pending |
| Support PyPI and Foundry drivers | Apache drivers on PyPI; Foundry drivers via `adbc_driver_manager` | — Pending |
| Syrupy snapshot tests for Snowflake | Real-credential recording locally; snapshot replay in CI avoids creds in CI | — Pending |
| v1 = DuckDB + Snowflake only | DuckDB for dev/test (no creds); Snowflake for first production consumer | — Pending |
| PyPI as v1 "done" bar | Library is only useful when consumers can install it | — Pending |

---
*Last updated: 2026-02-23 after initialization*
