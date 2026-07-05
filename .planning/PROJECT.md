# adbc-poolhouse

## What This Is

A focused Python library that takes a typed warehouse configuration and returns a pooled ADBC connection. Supports 13 warehouse backends (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, SQLite, MySQL, ClickHouse, Quack) with both PyPI and Foundry driver detection. Published to PyPI as `adbc-poolhouse`.

## Current State

**Shipped:** v1.5.0 Async Cursor Completion (2026-07-05) — completed the async cursor surface. The four v1.4.0-deferred ADBC cursor methods (`fetch_record_batch` Arrow streaming, `adbc_ingest` bulk write, `fetch_df`/`fetch_polars` DataFrame convenience) plus connection-level metadata (`adbc_get_*`) and prepared statements (`adbc_prepare`/`adbc_execute_schema`) now ship as pure offload wrappers over the unchanged sync core, routed through the existing v1.4.0 `offload`/`cancellable_offload` chokepoint. Async/sync parity now covers every ADBC method the sync raw-cursor path exposes (partitioned result sets excepted, deferred as niche Flight-SQL-only). The deferred P2 async edge-case hardening suite landed as well (test-only). No new runtime deps, no new extras, no sync-core change.

**Previously shipped:** v1.4.0 Async API (2026-07-01) — the optional `[async]` extra: `create_async_pool` / `managed_async_pool` / `close_async_pool` plus awaitable `AsyncPool` / `AsyncConnection` / `AsyncCursor` for all 13 backends, offloading the sync core to worker threads via anyio (asyncio + trio) with zero added async dependency on the sync path.

**Current milestone:** Planning the next milestone — v1.5.0 completed async/sync parity for the cursor surface; the async API is feature-complete against the sync raw-cursor path.

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
- ✓ Async cursor completion — Arrow streaming (`fetch_record_batch` → `AsyncRecordBatchReader`, reader lifetime bound to checkout), bulk write (`adbc_ingest`, `on_abort=invalidate`), DataFrame convenience (`fetch_df`/`fetch_polars`, user-supplied pandas/polars), connection metadata (`adbc_get_*`), and prepared statements (`adbc_prepare`/`adbc_execute_schema`), all pure offload wrappers over the unchanged sync core; plus the deferred P2 async edge-case hardening suite (test-only). Async/sync parity complete for the raw-cursor surface — v1.5.0 (Phases 29–35, 2026-07-05)

### Active

No active milestone — v1.5.0 completed async/sync parity for the cursor surface. Candidates for the next milestone (choose at `/gsd-new-milestone`):

- [ ] Async partitioned result sets (`adbc_execute_partitions` / `adbc_read_partition`) — the one deferred async surface; niche Flight-SQL/BigQuery-oriented, revisit only if a consumer needs it
- [ ] Re-record the Snowflake streaming cassette once `pytest-adbc-replay` supports `fetch_record_batch` (currently the reader legs are DuckDB-only / manual)

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

As of v1.5.0: ~5,360 LOC Python in `src/` and 489 test functions across the sync + async suites (async tests run under both asyncio and trio over DuckDB in-proc + a Snowflake cassette; cancellation/concurrency legs looped ×20, 0 hangs, on macOS and Linux CI). The `[async]` extra adds only anyio; the shipped sync wheel gains no async dependency. Package version is 1.5.0 (`pyproject.toml`).

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
| Reader lifetime bound to the checked-out connection | `fetch_record_batch` returns a live reader; binding it to checkout + closing on the reset-event checkin makes read-after-checkin a clean driver error, not a use-after-free | ✓ Good — no bespoke error type; DuckDB-pinned ordering (v1.5.0, Phase 29) |
| No bespoke async error types, no `find_spec` pre-checks | Async methods mirror the sync method's native errors (closed-stream `ArrowInvalid`, `ModuleNotFoundError`, `NotSupportedError`) — the offload chokepoint passes them through unchanged | ✓ Good — smaller surface, sync/async behavioral parity (v1.5.0) |
| `on_abort` omitted for prepare / metadata offloads | A prepare / `execute_schema` / metadata read writes no state, so a cancelled call returns a clean connection with no `invalidate` (cancellable but non-poisoning); only stateful writes (`adbc_ingest`) invalidate | ✓ Good — proven by cancel tests (`adbc_cancel`==1, `invalidate`==0); fixed CR-34-01 (v1.5.0, Phases 34/35) |

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
*Last updated: 2026-07-05 after v1.5.0 milestone — Async Cursor Completion shipped (Phases 29–35): Arrow streaming, bulk write, DataFrame convenience, connection metadata, and prepared statements all landed as pure offload wrappers over the unchanged sync core, plus the deferred P2 async edge-case suite. Async/sync parity complete for the raw-cursor surface (partitioned result sets excepted). Package bumped to 1.5.0. Next: `/gsd-new-milestone`.*
