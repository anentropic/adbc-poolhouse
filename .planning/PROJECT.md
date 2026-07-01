# adbc-poolhouse

## What This Is

A focused Python library that takes a typed warehouse configuration and returns a pooled ADBC connection. Supports 13 warehouse backends (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, SQLite, MySQL, ClickHouse, Quack) with both PyPI and Foundry driver detection. Published to PyPI as `adbc-poolhouse`.

## Current State

**Shipped:** v1.4.0 Async API (2026-07-01) — an optional async surface behind an `[async]` extra. `create_async_pool` / `managed_async_pool` / `close_async_pool` mirror the sync trio; awaitable `AsyncPool` / `AsyncConnection` / `AsyncCursor` cover all 13 backends by offloading the unchanged sync core to worker threads via anyio (asyncio + trio). ADBC releases the GIL, so the offload delivers real concurrency, and the sync path is untouched with zero added async dependency.

**Next milestone:** TBD — run `/gsd-new-milestone`. Candidate v1.4.x hardening (deferred at v1.4.0): Arrow streaming (`fetch_record_batch`), async bulk write (`adbc_ingest`), DataFrame convenience (`fetch_df`/`fetch_polars`), and the P2 async edge-case suite. See `milestones/v1.4.0-REQUIREMENTS.md` Future Requirements.

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
- ✓ `QuackConfig` backend for `adbc-driver-quack` (URI + decomposed host/port + token + tls), plus guide, configuration table, index listing, mkdocs nav — v1.3.0 (Phase 21, 2026-05-19)
- ✓ Optional async API (`[async]` extra): `create_async_pool` / `managed_async_pool` / `close_async_pool` + `AsyncPool` / `AsyncConnection` / `AsyncCursor` for all 13 backends via anyio thread-offload (asyncio + trio), dedicated per-pool `CapacityLimiter`, cooperative cancellation that never poisons the pool, PEP 562 zero-cost sync path, dual-backend test matrix, honest concurrency docs — v1.4.0 (Phases 22–28, 2026-07-01)

### Active

_No active milestone — planning the next one. Run `/gsd-new-milestone`._

**Carried (externally blocked):**
- [ ] Verify Teradata field names against real Columnar ADBC Teradata driver
- [ ] Live integration tests for non-DuckDB, non-Snowflake backends (blocked on test account availability)

**Deferred to v1.4.x (P1 async core now validated):**
- [ ] Arrow streaming — `await cursor.fetch_record_batch()` + `async for batch in ...`
- [ ] Async bulk write — `await cursor.adbc_ingest(...)`
- [ ] DataFrame convenience — `await cursor.fetch_df()` / `fetch_polars()`
- [ ] P2 async edge-case test suite (designs in `.planning/research/ASYNC-EDGE-CASES.md`)

### Out of Scope

- Multi-pool management — consumers call `create_pool()` per warehouse and manage the dict themselves
- Query execution — pool gives a connection, consumers execute
- Knowledge of dbt, profiles.yml, semantic layers, or MetricFlow
- REST/HTTP/Flight SQL serving
- OAuth / SSO auth logic — delegated entirely to ADBC drivers
- ~~Async connection pools — ADBC dbapi is synchronous~~ — **reversed in v1.4.0**: ADBC releases the GIL, so anyio thread-offload delivers real async concurrency without a native async ADBC driver
- Native async ADBC driver — not required; async is achieved by offloading the sync driver to threads
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

433 tests passing, 2 skipped (v1.4.0 added the async layer plus a dual-backend asyncio/trio matrix over DuckDB + Snowflake cassette). The `[async]` extra adds only anyio; the shipped sync wheel gains no async dependency.

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
| Async layer wraps the sync core unchanged | Reuse `_create_pool_impl`, config dispatch, Protocol, reset event — no fork | ✓ Good — one code path, generic over 13 backends (v1.4.0) |
| anyio over asyncio-native | asyncio + trio neutrality; ADBC GIL-release makes thread-offload real concurrency | ✓ Good — dual-backend matrix green on Linux CI (v1.4.0) |
| Dedicated per-pool `CapacityLimiter` | The global 40-token anyio default over-admits; bound = `pool_size + max_overflow` | ✓ Good — in-flight concurrency strictly bounded (v1.4.0) |
| Cancellation invalidates, never returns busy | A cancelled in-flight C call can poison the connection | ✓ Good — `checkedout()==0` after cancel, asyncio/trio parity (v1.4.0) |
| `[async]` extra + PEP 562 lazy import | Sync users pay nothing; anyio stays optional | ✓ Good — sync suite green with anyio absent (v1.4.0) |
| TypeVarTuple/Unpack at offload boundary (not ParamSpec) | ParamSpec can't type keyword-only params after `*args` | ✓ Good — basedpyright strict, 0 errors (v1.4.0) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-01 — v1.4.0 Async API milestone shipped and archived (phases 22–28, 29 plans, 63/63 requirements, audit passed). Full milestone review applied: async requirements moved to Validated, v1.4.0 design decisions logged, context refreshed to 433 tests. Next: `/gsd-new-milestone`.*
