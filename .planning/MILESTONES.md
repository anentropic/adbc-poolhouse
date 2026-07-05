# Milestones

## v1.5.0 Async Cursor Completion (Shipped: 2026-07-05)

**Phases completed:** 7 phases (29-35), 19 plans, 36 tasks

**Delivered:** Completed the async cursor surface. The four ADBC cursor methods deferred at v1.4.0 (`fetch_record_batch` Arrow streaming, `adbc_ingest` bulk write, `fetch_df`/`fetch_polars` DataFrame convenience) plus connection-level metadata (`adbc_get_*`) and prepared statements (`adbc_prepare` / `adbc_execute_schema`) now ship as pure offload wrappers over the unchanged sync core, routed through the existing v1.4.0 `offload`/`cancellable_offload` chokepoint and per-pool `CapacityLimiter`. This closes async/sync parity for every ADBC method the sync raw-cursor path exposes (partitioned result sets excepted, deferred as niche Flight-SQL-only). No new runtime deps, no new extras, no sync-core change.

**Key accomplishments:**

- Arrow streaming — `await cursor.fetch_record_batch()` returns an `AsyncRecordBatchReader` with per-batch offloaded `async for`, its lifetime bound to the checked-out connection; the reset-event checkin closes the reader first so read-after-checkin surfaces the driver's native closed-stream error (a clean exception, never a use-after-free), with a warn-only `__del__` (STREAM-01..06, EDGE-33)
- Async bulk write — `await cursor.adbc_ingest(table, data, mode=...)` as a single whole-op offload with a typed `Literal` mode (and an explicit `replace`-drops-the-table warning); a cancelled or timed-out ingest fires `adbc_cancel` once and invalidates the connection, holding `checkedout() == 0` under asyncio + trio (INGEST-01..04)
- DataFrame convenience — `fetch_df` / `fetch_polars` as `fetch_arrow_table` offload clones returning self-owning frames valid after checkin; pandas/polars stay user-supplied (native `ModuleNotFoundError` passes through unchanged, dev-group-only, `__init__` surface untouched) (DF-01..04, PKG-02)
- P2 async edge hardening — six deferred EDGE assertions (trio checkpoint at the offload boundary, contextvar copy-in / no-leak-back, `move_on_after` deadline precision, event-loop-shutdown cleanliness) pinned by deterministic dual-backend tests, green ×20 on macOS (2702 passed, 0 hangs) and authoritatively on Linux CI (Py 3.11 + 3.14); test-only, zero production change (EDGE-08/13/14/24/31/32)
- Async/sync parity extension — the six `adbc_get_*` metadata methods (streaming ones surfacing their native `RecordBatchReader`, non-poisoning on cancel per CR-34-01) and `adbc_prepare` / `adbc_execute_schema` (the latter returns the result schema without executing; cancellable but non-poisoning, `on_abort` omitted), each a clone of the established offload pattern (META-01..04, PREP-01..03)
- Documentation + type safety — the async guide gains streaming, ingest (mode table + destructive-`replace` warning), DataFrame, connection-metadata, and prepared-statement how-tos; the API reference auto-renders the whole new surface with Google-style Args/Returns/Raises + Example; `mkdocs build --strict` gate + humanizer pass, basedpyright-strict 0 errors, AST import-lint clean over `_async/` (DOCS-01..04, PKG-01/03)

**Stats:**

- Phases: 7 (29-35), 19 plans, 36 tasks; 38/38 requirements satisfied
- Files changed: 246; Commits: 133
- Timeline: 4 days (2026-07-01 → 2026-07-05)
- Tests: 489 test functions (async suite dual-backend asyncio + trio; cancellation/concurrency legs looped ×20, 0 hangs)
- Git range: v1.4.0 → v1.5.0
- Milestone audit: passed (38/38 requirements, 7/7 phases, integration clean, 5/5 E2E flows) — `milestones/v1.5.0-MILESTONE-AUDIT.md`
- Known deferred items at close: 8 quick-task tracking artifacts acknowledged (all complete on disk; audit could not parse their status frontmatter — see STATE.md Deferred Items)

---

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

## v1.3.0 Quack Backend (Shipped: 2026-05-21)

**Phases completed:** 2 phases (21, 21.1), 6 plans

**Delivered:** `QuackConfig` backend for the `adbc-driver-quack` remote DuckDB protocol, following the v1.2.0 self-describing Protocol pattern, plus a dispatch fix (Phase 21.1) correcting `create_pool()` for every PyPI driver that takes a required-positional `uri` (Quack, PostgreSQL, FlightSQL).

**Key accomplishments:**

- `QuackConfig` accepting either `uri="quack://host:port"` or decomposed `host`/`port`, with optional `token` (SecretStr) and `tls`, mutual-exclusion validated at construction
- `create_pool(QuackConfig(...))` works via the existing self-describing dispatch — no `_pool_factory` changes; `pip install adbc-poolhouse[quack]` installs the driver
- Per-warehouse Quack guide (mkdocs nav + configuration table + index listing) with alpha-status warning and external project link
- Phase 21.1: fixed `TypeError: connect() missing 1 required positional argument: 'uri'` for uri-positional drivers — repaired the documented quickstart for Quack and latent v1.0.0 dispatch bugs in PostgreSQL and FlightSQL
- Signature-preserving import stubs so this regression class is caught by CI in future

**Stats:**

- Phases: 2 (21, 21.1), 6 plans; 29 requirements (QUACK-01..18, DISP-01..11)
- Files changed: 43; Commits: 77
- Shipped: 2026-05-21 (git range v1.2.0 → v1.3.0)
- Tests: ~265 passing
- Backends: 12 → 13 (added Quack)
- Follow-up patch: v1.3.1 (2026-06-24) — DatabricksConfig catalog/schema fix

_Retroactively archived 2026-07-01 — v1.3.0 shipped and was tagged but never formally closed via `/gsd-complete-milestone`._

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
