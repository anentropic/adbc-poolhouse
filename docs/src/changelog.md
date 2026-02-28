# Changelog

All notable changes to this project will be documented in this file.


### Bug Fixes

- Set basedpyright pythonVersion to 3.11
- Add Foundry NOT_FOUND catch-and-reraise to _driver_api.py (DRIV-03)
- Revise plans based on checker feedback
- Revise plans based on checker feedback
- Add duckdb extra to CI sync and pin mkdocs-material<9.7.0
- Call main() unconditionally in gen_ref_pages.py

### Documentation

- Map existing codebase
- Initialize project
- Complete project research
- Define v1 requirements
- Create roadmap (7 phases)
- Capture phase context
- Research phase domain
- Create phase plan
- Complete pre-flight-fixes plan
- Mark SETUP-01 and SETUP-05 complete in requirements
- Complete phase execution
- Capture phase context
- Research phase dependencies
- Create phase plan
- Update REQUIREMENTS.md SETUP-02 and SETUP-03 descriptions
- Complete dependency declarations plan
- Complete dependency validation plan
- Complete phase execution
- Capture phase context
- Research config layer phase
- Create phase plan
- Complete config layer foundation plan
- Add self-check result to SUMMARY.md
- Complete MSSQL and Teradata config plan
- Complete Foundry backend configs plan (Databricks/Redshift/Trino)
- Complete BigQuery/PostgreSQL/FlightSQL config plan
- Complete public API wiring plan
- Complete config model unit tests plan
- Complete phase execution
- Capture phase context
- Research phase domain
- Create phase plan
- Complete translator plan — DuckDB, PostgreSQL, BigQuery, FlightSQL translators
- Complete Snowflake and Foundry translators plan
- Complete translation and driver wiring plan
- Append self-check PASSED to SUMMARY.md
- Complete driver detection unit tests plan
- Complete translator unit tests plan
- Complete phase execution
- Capture phase context
- Research pool factory and DuckDB integration
- Add validation strategy and research
- Create phase plan
- Complete exception hierarchy and config foundation plan
- Complete pool factory plan
- Complete phase execution
- Rename milestone v1.0 → v0.1
- Capture phase context
- Research snowflake integration phase
- Create phase plan
- Complete snowflake snapshot test plan
- Complete phase execution
- Capture phase context
- Research documentation and pypi publication phase
- Create phase plan
- Complete docs-author skill and quality gate plan
- Complete release pipeline extension plan
- Complete config class docstrings plan
- Write guide pages and quickstart
- Complete guide pages and nav restructure plan
- Integration verification complete, awaiting trusted publisher registration
- Complete plan — OIDC trusted publishers registered, DIST-01 satisfied
- Complete phase execution
- Complete CI fix plan summary
- Check (with gh run list and related commands) and fix CI failures
- Capture phase context and implement discussion fixes
- Research phase — docs improvement, close_pool API, git-cliff changelog
- Create phase plan
- Create DuckDB warehouse guide

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

### Miscellaneous

- Initial project structure from cookiecutter
- Add detect-secrets hook and generate baseline
- Resolve 8 audit items from v1.0 milestone
- Add docs/src/reference/ to gitignore

### Testing

- Add config model unit tests for all 11 warehouse configs (TEST-04)
- Add failing translator unit tests
- Add failing tests for create_pool factory (RED)
- Complete UAT - 6 passed, 0 issues
- Complete UAT - 5 passed, 1 issue
- Diagnose UAT gap - addopts behavior, update marker docs

### Remove

- Drop TeradataConfig — no ADBC driver exists

### Wip

- Complete-milestone v0.1 paused at task 1/8
