# Milestones

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
