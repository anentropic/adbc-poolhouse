# Phase 1: Driver Import Semi-Integration Tests - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Create semi-integration tests that import every supported driver library and attempt `create_pool()` with it, using mocking to assert we got as far as trying to connect with expected args (no replay cassettes). All 12 backends must pass: DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, SQLite, MySQL, ClickHouse.

</domain>

<decisions>
## Implementation Decisions

### Test scope
- Full stack verification: driver import, pool creation, connection attempt with exact kwargs
- Real driver imports (not mocked) - all 12 backends must pass, no skipping
- PyPI drivers installed in CI via pip/uv (snowflake, bigquery, postgresql, flightsql, sqlite)
- Foundry drivers installed in CI via dbc CLI (clickhouse, databricks, mssql, mysql, redshift, trino)
- Justfile recipe for local setup: install all drivers (PyPI + Foundry) in one command

### Mocking depth
- Two mock points based on driver type:
  - Foundry drivers + DuckDB: mock `adbc_driver_manager.dbapi.connect`
  - PyPI drivers: mock each driver's own `dbapi.connect` (e.g., `adbc_driver_snowflake.dbapi.connect`)
- Mock returns object with `adbc_clone` method (tests pool wiring)
- Assert all args: driver_path, db_kwargs, entrypoint (for DuckDB)

### Test organization
- Single file: `tests/imports/test_driver_imports.py`
- One test class per backend (12 classes)
- New `tests/imports/` directory

### Error case coverage
- Happy path only - error cases already covered in `test_drivers.py`

### Bug handling strategy
- Minor bugs: fix in this phase
- Larger refactoring: separate bug-fix phase
- User consulted when bugs discovered to determine scope

</decisions>

<specifics>
## Specific Ideas

- "Don't skip any tests" - all 12 backends must pass
- "Same for running tests locally" - dbc CLI for Foundry drivers locally too

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/conftest.py`: `_clear_warehouse_env_vars` autouse fixture - prevents env var contamination
- `tests/test_drivers.py`: Mocking patterns for `find_spec`, `__import__`, `adbc_driver_manager.dbapi.connect`
- `tests/test_pool_factory.py`: Mocking pattern for `create_adbc_connection` with `adbc_clone` return value

### Established Patterns
- `_drivers.py`: 3-path detection (PyPI Path 1/2, Foundry skip find_spec)
- `_driver_api.py`: Two connection paths - PyPI drivers use their own dbapi, Foundry/DuckDB use adbc_driver_manager
- `resolve_dbapi_module()`: Returns `"adbc_driver_snowflake.dbapi"` for PyPI drivers, `None` for Foundry/DuckDB

### Integration Points
- `create_pool()` calls: `resolve_driver()`, `translate_config()`, `resolve_dbapi_module()`, `create_adbc_connection()`
- PyPI drivers: `adbc_driver_snowflake.dbapi.connect(db_kwargs=kwargs)`
- Foundry drivers: `adbc_driver_manager.dbapi.connect(driver=driver_path, db_kwargs=kwargs)`
- DuckDB: `adbc_driver_manager.dbapi.connect(driver=path, entrypoint='duckdb_adbc_init', db_kwargs=kwargs)`

</code_context>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope

</deferred>

---

*Phase: 01-driver-import-semi-integration-tests*
*Context gathered: 2026-03-12*
