# adbc-poolhouse

## What This Is

A focused Python library that takes a typed warehouse configuration and returns a pooled ADBC connection. Supports 12 warehouse backends (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, SQLite, MySQL, ClickHouse) with both PyPI and Foundry driver detection. Published to PyPI as `adbc-poolhouse`.

## Core Value

One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.

## Requirements

### Validated

- ✓ Package scaffold at `src/adbc_poolhouse/` with PEP 561 marker — existing
- ✓ Toolchain: uv, ruff, basedpyright strict, prek pre-commit — existing
- ✓ Docs infrastructure: mkdocs-material + mkdocstrings — existing
- ✓ CI: GitHub Actions, Python 3.11 + 3.14 matrix — existing
- ✓ Cliff.toml changelog generation — existing
- ✓ Full config + translation layer for 12 warehouses — v1.0.0
- ✓ `create_pool()`, `close_pool()`, `managed_pool()` public API — v1.0.0
- ✓ Driver detection: PyPI path (find_spec) + Foundry path (adbc_driver_manager) — v1.0.0
- ✓ Full documentation site with per-warehouse guides — v1.0.0
- ✓ PyPI publication via OIDC trusted publisher — v1.0.0
- ✓ DatabricksConfig decomposed-field fix (URI-first pattern) — v1.0.0
- ✓ Foundry tooling: justfile recipes for `dbc` CLI + driver management — v1.0.0
- ✓ SQLite, MySQL, ClickHouse backends — v1.0.0
- ✓ VCR-style integration tests via pytest-adbc-replay cassettes — v1.0.0
- ✓ Self-describing config classes with `to_adbc_kwargs()`, `_driver_path()`, `_dbapi_module()` — v1.2.0
- ✓ Registry-free architecture — `create_pool()` calls config methods directly — v1.2.0
- ✓ Raw `create_pool(driver_path=...)` and `create_pool(dbapi_module=...)` overloads — v1.2.0
- ✓ WarehouseConfig Protocol as third-party contract — v1.2.0
- ✓ Custom backends guide with Protocol reference — v1.2.0
- ✓ Semi-integration tests for all 12 backends — v1.2.0

### Active

- [ ] Verify Teradata field names against real Columnar ADBC Teradata driver
- [ ] Live integration tests for non-DuckDB, non-Snowflake backends (blocked on test account availability)
- [ ] Async pool support (blocked on ADBC adding async dbapi interface)

### Out of Scope

- Multi-pool management — consumers call `create_pool()` per warehouse and manage the dict themselves
- Query execution — pool gives a connection, consumers execute
- Knowledge of dbt, profiles.yml, semantic layers, or MetricFlow
- REST/HTTP/Flight SQL serving
- OAuth / SSO auth logic — delegated entirely to ADBC drivers
- Async connection pools — ADBC dbapi is synchronous
- Teradata — private Foundry registry (requires paid Columnar access)
- Oracle — private Foundry registry
- ClickHouse via Apache ADBC — github.com/ClickHouse/adbc_clickhouse is WIP with many NotImplemented stubs
- Plugin registry / entry point discovery — architectural pivot chose Protocol-based contract over registry system
- Backend enumeration (list_backends) — no registry; consumers know which configs they use

## Context

Shipped v1.2.0 with 2,326 LOC Python across 12 warehouse backends.
Tech stack: Pydantic BaseSettings, SQLAlchemy QueuePool, ADBC Driver Manager, mkdocs-material.
Published to PyPI: `pip install adbc-poolhouse`.

v1.2.0 pivoted from a registry-based plugin system to a simpler Protocol-based contract. Config classes are self-describing — each carries its driver path, kwargs translation, and dbapi module. Third-party backends implement the WarehouseConfig Protocol and pass directly to `create_pool()`.

Two concrete consumers:
1. **dbt-open-sl** — provides a `translate_to_poolhouse_config()` shim from `profiles.yml` to this lib's config models
2. **Semantic ORM** (planned) — uses the config models directly as its own user-facing config

Integration tests use pytest-adbc-replay cassettes (VCR-style record/replay) for Snowflake and Databricks — CI runs without credentials.

241 tests passing.

## Constraints

- **Python**: ≥3.11 (`requires-python = ">=3.11"` in pyproject.toml)
- **Type safety**: basedpyright strict mode — all public API must be fully typed
- **SQLAlchemy**: pool submodule only (`sqlalchemy.pool`, `sqlalchemy.event`) — NOT the ORM
- **No global state**: library has no module-level singletons; consumers own all pool instances
- **License**: Apache 2.0

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Pydantic BaseSettings for config | Typed, validated, env-var support comes free | ✓ Good — 12 warehouse configs with zero boilerplate |
| SQLAlchemy QueuePool (not hand-rolled) | Battle-tested thread-safe pool; imports only pool submodule | ✓ Good — stable, Arrow cleanup via reset event |
| One pool per call, no multi-warehouse routing | Keep lib simple; routing is consumer business logic | ✓ Good — simple API, no global state |
| Config + pool only, no execution | Execution semantics differ per consumer | ✓ Good — clean separation |
| Support PyPI and Foundry drivers | Apache drivers on PyPI; Foundry drivers via `adbc_driver_manager` | ✓ Good — both paths tested and working |
| Syrupy → pytest-adbc-replay | Syrupy snapshots fragile; cassette replay is deterministic and CI-safe | ✓ Good — 4 integration tests in 0.03s replay |
| URI-first with decomposed-field fallback | Databricks, MySQL, ClickHouse need both modes | ✓ Good — consistent pattern across all backends |
| Open lower bounds only (no upper caps) | Tight bounds cause unnecessary consumer dep conflicts | ✓ Good — no reports of dep conflicts |
| `pre_ping=False` default | pre_ping silently no-ops on standalone QueuePool without a dialect; `recycle=3600` is the health mechanism | ✓ Good — correct for standalone pool |
| Registry built then removed | Self-describing configs are simpler than registry dispatch | ✓ Good — no global state, no lazy registration, no dispatch layer |
| Protocol over plugin system | WarehouseConfig Protocol lets third parties implement backends without registration | ✓ Good — zero ceremony for custom backends |
| ABC for BaseWarehouseConfig | Catches missing `_driver_path()` / `to_adbc_kwargs()` at instantiation time | ✓ Good — fail fast on incomplete implementations |
| EAFP in create_pool() | AttributeError is natural error for configs missing methods; no TypeError raise | ✓ Good — simpler, Pythonic |
| `_create_pool_impl()` shared helper | Avoids overload forwarding issues between `managed_pool()` and `create_pool()` | ✓ Good — single implementation, three call patterns |
| Direct `to_adbc_kwargs()` over aliases | Field-to-key mappings too divergent for Pydantic alias approach | ✓ Good — explicit, readable, correct |

---
*Last updated: 2026-03-15 after v1.2.0 milestone*
