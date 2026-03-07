# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-03-07

### Bug Fixes

- Correct SQLite ADBC entrypoint to AdbcDriverSqliteInit
- Add --pre flag to ClickHouse dbc install; backfill SUMMARY requirements-completed
- Mark SQLT-01–05 and DBC-02 complete in REQUIREMENTS.md; fix traceability table
- Fix cassette test connect kwargs for recording
- Revise plan 04 per checker feedback
- Add autouse fixture clearing warehouse env vars before each test
- Use per-warehouse dotenv files in integration tests
- Resolve all v1.0 tech debt items
- Add version headers and filter noise from changelog

### Features

- Add model_validator to DatabricksConfig (DBX-01)
- Implement decomposed-field URI in translate_databricks() (DBX-02)
- Add SQLiteConfig and translate_sqlite()
- Register SQLiteConfig in _PYPI_PACKAGES and translate_config
- Export SQLiteConfig and add sqlite optional extra
- Add install-dbc and install-foundry-drivers just recipes
- Create MySQLConfig Pydantic BaseSettings class
- Create translate_mysql() pure function
- Wire MySQLConfig into driver registry, translator dispatch, and public API
- Add individual field support to PostgreSQLConfig
- Add individual field support + full backend test coverage
- Implement ClickHouseConfig Pydantic BaseSettings model
- Implement translate_clickhouse() pure translator function
- Register ClickHouseConfig in _FOUNDRY_DRIVERS
- Wire ClickHouseConfig into translators and public API
- Add ClickHouse warehouse guide and update doc surfaces
- Add MySQL and ClickHouse to homepage table and config class list
- Migrate Snowflake/Databricks tests to pytest-adbc-replay cassettes
- Record Snowflake cassettes and unify dotenv loading

### Miscellaneous

- Bump adbc-driver-manager floor to >=1.8.0
- Add duckdb extra to dev dependency group
- Pass --group docs to uv run in Justfile build/serve recipes
- Close Phase 10 — update roadmap, state, and planning artifacts
- Remove synthetic cassette files
- Bump version to 1.1.0

### Testing

- Add SQLite config, translator, and pool-factory tests
- Add MySQLConfig, translate_mysql(), and pool-factory wiring tests
- Add TestPostgreSQLConfig for individual field support
- Add TestClickHouseConfig, TestClickHouseTranslator, and dispatch test
- Add test_clickhouse_returns_short_name and TestClickHousePoolFactory

## [1.0.1] - 2026-02-28

### Features

- Rewrite README.md as a consumer-facing landing page

### Miscellaneous

- Add [project.urls] to pyproject.toml
- Bump version to 1.0.1 and update docs/README

## [1.0.0] - 2026-02-28

### Bug Fixes

- Set basedpyright pythonVersion to 3.11
- Add Foundry NOT_FOUND catch-and-reraise to _driver_api.py (DRIV-03)
- Revise plans based on checker feedback
- Revise plans based on checker feedback
- Add duckdb extra to CI sync and pin mkdocs-material<9.7.0
- Call main() unconditionally in gen_ref_pages.py
- Add --extra duckdb to pr workflow sync step
- Fix git-cliff install and config path in release workflow
- Use orhun/git-cliff-action instead of manual binary install
- Remove deploy-docs from release workflow

### Features

- Declare runtime deps, optional extras, and dev deps
- Commit lock file covering all optional warehouse driver deps
- Add BaseWarehouseConfig abstract base and WarehouseConfig Protocol
- Add DuckDBConfig with in-memory pool_size validator
- Implement MSSQLConfig for SQL Server/Azure SQL/Fabric/Synapse
- Implement TeradataConfig with LOW-confidence source-attributed fields
- Add DatabricksConfig and RedshiftConfig
- Add TrinoConfig
- Add BigQueryConfig and PostgreSQLConfig
- Add FlightSQLConfig with gRPC, auth, TLS, and timeout fields
- Wire all config models into public API via __init__.py
- Add DuckDB and PostgreSQL translator functions
- Add BigQuery and FlightSQL translator functions
- Implement Foundry backend translators (Databricks, Redshift, Trino, MSSQL, Teradata)
- Add translate_config() dispatch coordinator (_translators.py)
- Add driver detection, ADBC facade, and type scaffold
- All driver detection tests pass
- Create exception hierarchy (_exceptions.py)
- Add _adbc_entrypoint to WarehouseConfig Protocol and BaseWarehouseConfig
- Update DuckDBConfig with ConfigurationError, _adbc_entrypoint, and bounds validators
- Add Snowflake snapshot test infrastructure
- Add Snowflake integration tests and CONTRIBUTING.md
- Create adbc-poolhouse-docs-author skill (TOOL-01)
- Create CLAUDE.md documentation quality gate (TOOL-02)
- Extend release.yml with TestPyPI, smoke test, and docs deploy jobs
- Complete config class docstrings with attribute docstrings
- Restructure mkdocs.yml nav and fix reference generation
- Add Databricks and Redshift warehouse guide pages
- Add Trino, MSSQL, and Teradata warehouse guide pages
- Export close_pool and managed_pool from __init__.py
- Add Warehouse Guides sub-section to mkdocs.yml nav

### Miscellaneous

- Initial project structure from cookiecutter
- Add detect-secrets hook and generate baseline
- Resolve 8 audit items from v1.0 milestone
- Add docs/src/reference/ to gitignore
- Add justfile with build and serve recipes
- Bump the github-actions group with 5 updates
- Add --dirtyreload to justfile serve recipe
- Use --livereload flag in justfile serve recipe
- Add mkdocs watch paths for src and docs
- Bump version to 1.0.0

### Testing

- Add config model unit tests for all 11 warehouse configs (TEST-04)
- Add failing translator unit tests
- Add failing tests for create_pool factory (RED)
- Complete UAT - 6 passed, 0 issues
- Complete UAT - 5 passed, 1 issue
- Diagnose UAT gap - addopts behavior, update marker docs

### Ci

- Gate release on quality checks passing

### Remove

- Drop TeradataConfig — no ADBC driver exists
