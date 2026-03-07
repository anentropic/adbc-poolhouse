# Milestones

## v1.0.0 MVP + Backend Expansion (Shipped: 2026-03-07)

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

