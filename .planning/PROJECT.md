# adbc-poolhouse

## What This Is

A focused Python library that takes a typed warehouse configuration and returns a pooled ADBC connection. Supports 13 warehouse backends (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, SQLite, MySQL, ClickHouse, Quack) with both PyPI and Foundry driver detection. Published to PyPI as `adbc-poolhouse`.

## Current Milestone: v1.4.0 Async API

**Goal:** Add an optional async API surface (behind an `[async]` extra) that wraps the sync ADBC pool/connection/cursor methods with anyio thread-offload, exposing awaitable versions of the full poolhouse API for all 13 backends.

**Target features:**
- Parallel async functions — `create_async_pool()`, `managed_async_pool()`, `close_async_pool()` mirroring the sync trio
- Async connection wrapper — `await pool.connect()` returns an async connection
- Async cursor wrapper — `execute` / `executemany` / `fetch*` / `fetch_arrow_table` offloaded via `anyio.to_thread.run_sync`
- Cooperative cancellation — `adbc_cancel` wired to anyio cancellation scopes
- `[async]` optional extra (adds anyio); sync API completely unchanged
- Generic machinery — one async layer covers every `WarehouseConfig` via the Protocol
- Documentation — async usage guide + configuration/index/API-reference updates

**Feasibility basis:** ADBC releases the GIL in its C calls, so offloading the sync methods to a thread pool yields real concurrency — no native async ADBC driver required. This reverses the prior "ADBC dbapi is synchronous" out-of-scope decision.

**Open design decision (settled in research):** checkout-wait strategy — plain sync `QueuePool` with anyio-offloaded checkout-and-execute vs. an anyio-native checkout limiter (trio-safe). SQLAlchemy's `AsyncAdaptedQueuePool` is asyncio-bound and does not replace the thread-offload, so it is a reference, not a foundation.

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

### Active

**Milestone v1.4.0 — Async API:** Complete (all phases 22–28 done; async surface for all 13 backends behind an `[async]` extra). Phases 22–25: async pool/connection/cursor surface, dedicated per-pool limiter, and cooperative cancellation (cancel/timeout never poisons the pool — `adbc_cancel` fired once from the loop thread, shielded invalidate, identical under asyncio + trio; CANCEL-01..04, EDGE-01..07/19/28/29). Phase 26 (packaging/`[async]` extra) and Phase 27 (dual-backend test matrix) complete. Phase 28 (Documentation) complete: honest async usage guide, async API reference, configuration/index/changelog updates, docs quality gate passing (DOCS-01..04). Milestone ready for `/gsd-complete-milestone`.

**Carried (externally blocked):**
- [ ] Verify Teradata field names against real Columnar ADBC Teradata driver
- [ ] Live integration tests for non-DuckDB, non-Snowflake backends (blocked on test account availability)

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

265 tests passing (241 from v1.2.0 baseline + 24 new in Phase 21 for QuackConfig).

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
*Last updated: 2026-06-29 — Phase 28 (Documentation) complete, closing out the v1.4.0 Async API milestone (phases 22–28). Ships an honest async usage guide distinguishing I/O-bound wins (~2.77x execute) from materialization-bound limits per the Phase 22 benchmarks, an API reference rendering `AsyncPool`/`AsyncConnection`/`AsyncCursor` plus the three entry points, configuration/index/changelog updates flagging the async API experimental, and a passing `mkdocs build --strict` + humanizer gate (DOCS-01..04). Next: `/gsd-complete-milestone` to archive v1.4.0.*
