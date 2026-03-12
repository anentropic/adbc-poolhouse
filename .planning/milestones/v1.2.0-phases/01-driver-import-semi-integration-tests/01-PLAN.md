# Phase 1: Driver Import Semi-Integration Tests

**Status:** Not Started  
**Milestone:** v1.2.0 Plugin/Extensibility API

## Goal

Create semi-integration tests that import every supported driver library and attempt create_pool with it, using mocking to assert we got as far as trying to connect with expected args (no replay cassettes).

## Requirements

- TEST-01: Import All Drivers
- TEST-02: Mock Connection Attempts
- TEST-03: Assert Expected Args
- TEST-04: Coverage for All 12 Backends

## Success Criteria

1. Test imports each driver package (adbc_driver_snowflake, adbc_driver_bigquery, etc.)
2. Test creates a pool with each backend config
3. Mock asserts connection was attempted with correct kwargs
4. All 12 backends covered: DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, SQLite, MySQL, ClickHouse
5. Tests run fast without credentials or cassettes

## Quality Gates

- [ ] All 12 backends have semi-integration tests
- [ ] Tests verify driver import and pool creation flow
- [ ] `uv run basedpyright` passes
- [ ] `uv run ruff check` passes
- [ ] `uv run ruff format --check` passes
- [ ] `uv run pytest` passes

## Plans

- [ ] Plan 1: TBD
- [ ] Plan 2: TBD
