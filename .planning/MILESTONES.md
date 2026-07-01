# Milestones

## v1.4.0 Async API (Shipped: 2026-07-01)

**Phases completed:** 7 phases (22-28), 29 plans

**Delivered:** An optional async API surface behind an `[async]` extra — `create_async_pool` / `managed_async_pool` / `close_async_pool` mirroring the sync trio, with awaitable `AsyncPool` / `AsyncConnection` / `AsyncCursor` for all 13 backends. Every blocking ADBC call is offloaded to a worker thread via `anyio.to_thread.run_sync` (real concurrency — ADBC releases the GIL), wrapping the sync core unchanged. anyio gives asyncio + trio neutrality; the sync path is untouched and gains zero async dependency.

**Key accomplishments:**
- Async pool/connection/cursor surface over the unchanged sync core, generic across all 13 backends via the `WarehouseConfig` Protocol (no per-backend async code)
- Single offload chokepoint with a dedicated per-pool `anyio.CapacityLimiter(pool_size + max_overflow)` — never the global 40-token default; AST-lint-enforced
- Cooperative cancellation that never poisons the pool — `adbc_cancel` fired once from the loop thread, shielded checkin, invalidate-on-cancel, identical under asyncio and trio
- `[async]` extra with PEP 562 lazy import — `import adbc_poolhouse` and the full sync suite pass with anyio absent (proven by a `sync-no-anyio` CI job); async public API fully typed under basedpyright strict (PEP 646 `TypeVarTuple`/`Unpack` at the offload boundary)
- Dual-backend test matrix — every async test parametrized over asyncio + trio across DuckDB (in-proc) and a Snowflake cassette, plus Arrow allocator-stability and limiter-saturation stress proofs and no-asyncio meta-guards
- Honest async documentation — usage guide distinguishing I/O-bound wins (~2.77x execute) from materialization-bound limits (~1.67x fetch) per the Phase 22 benchmarks, full API reference, mkdocs `--strict` gate

**Stats:**
- Phases: 7 (22-28), 29 plans; 63/63 requirements satisfied
- Files changed: 214; Commits: 190
- Timeline: 6 days (2026-06-25 → 2026-07-01)
- Tests: 433 passing, 2 skipped
- Git range: v1.3.1 → v1.4.0
- Milestone audit: passed (0 blockers, 4/4 E2E flows wired) — `milestones/v1.4.0-MILESTONE-AUDIT.md`
- Known deferred items at close: 9 stale quick-task tracking artifacts (pre-v1.4.0 cruft, see STATE.md Deferred Items) + one non-functional `_cancel.py` docstring drift

---

## v1.2.0 Plugin/Extensibility API (Shipped: 2026-03-15)

**Phases completed:** 6 phases (16-20), 17 plans

**Delivered:** Self-describing config architecture with Protocol-based third-party contract and raw driver path overloads. Registry built and deliberately removed in favor of simpler design.

**Key accomplishments:**
- Semi-integration tests for all 12 ADBC backends with conditional mock targets
- Self-describing config classes with `_driver_path()`, `_dbapi_module()`, and `to_adbc_kwargs()` methods
- Registry-free architecture — `create_pool()` calls config methods directly, no dispatch layer
- Overloaded `create_pool(driver_path=...)` and `create_pool(dbapi_module=...)` for raw driver usage
- WarehouseConfig Protocol as the sole third-party contract
- Custom backends guide with Protocol reference documentation

**Stats:**
- Lines of code: 2,326 Python (src/)
- Files modified: 123
- Commits: 107
- Timeline: 4 days (2026-03-12 → 2026-03-15)
- Tests: 241 passing
- Git range: 6bc6908 → 1564805

---

## v1.1.0 Backend Expansion + Infrastructure (Shipped: 2026-03-07)

**Phases completed:** 6 phases (phases 9-12, 15), multiple plans

**Key accomplishments:**
- Added 3 new backends: SQLite (PyPI), MySQL (Foundry), ClickHouse (Foundry)
- Databricks configuration fix — URI-first with decomposed-field fallback
- Foundry tooling support — `dbc` CLI integration for driver management
- Migrated from syrupy snapshots to pytest-adbc-replay for CI-safe integration tests
- pytest-adbc-replay cassettes for Snowflake and Databricks testing
- Individual field support for PostgreSQLConfig (host, port, database, user, password)

**Stats:**
- Backends: 9 → 12 total
- Lines of code: ~2,500 Python
- Git range: v1.0.0 → v1.1.0

---

## v1.0.0 MVP + Backend Expansion (Shipped: 2026-02-28 → 2026-03-07)

**Phases completed:** 15 phases, 51 plans, 0 tasks

**Key accomplishments:**
- Typed config + translation layer for 12 ADBC warehouses (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, SQLite, MySQL, ClickHouse)
- `create_pool()` / `close_pool()` / `managed_pool()` public API — one config in, one pool out
- Lazy driver detection for both PyPI and Foundry-distributed ADBC backends
- Complete documentation site with auto-generated API reference, quickstart, and per-warehouse guides
- Published to PyPI via OIDC trusted publisher (`pip install adbc-poolhouse`)
- VCR-style integration tests via pytest-adbc-replay cassettes (Snowflake + Databricks, CI-safe)

**Stats:**
- Lines of code: 2,373 Python (src/)
- Files modified: 276
- Commits: 267
- Timeline: 13 days (2026-02-23 → 2026-03-07)
- Requirements: 66/66 satisfied (44 v0.1 + 22 v1.1)
- Git range: Initial commit → v1.0.0

---
