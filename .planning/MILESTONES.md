# Milestones

## v1.2.0 Plugin/Extensibility API (Planned)

**Status:** In progress (1 phase remaining)
**Phases:** 5 completed (16-19), 1 pending (20)

**Goals:**
- Self-describing config classes (no registry indirection)
- Raw create_pool overload for advanced/custom use
- Documentation for custom backend authors

**Completed phases:**
16. Driver Import Semi-Integration Tests — semi-integration tests for all 12 backends
17. Registry Infrastructure — backend registry (later removed in Phase 18)
17.5. Translator Consolidation — consolidate translator interface for plugin consistency
18. Registration Removal — configs self-describe driver path, delete registry machinery
19. Raw create_pool Overload — `create_pool()` accepts raw `(driver_path, db_kwargs)` directly

**Pending phases:**
20. Protocol Documentation — WarehouseConfig Protocol reference + custom backends guide (DOC-03)

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
