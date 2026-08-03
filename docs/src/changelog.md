# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.6.2] - 2026-08-02

### Fixed

- Cancelling an in-flight async query no longer risks hanging the cancelling task forever. The cancellation path fired the driver's `adbc_cancel` and then immediately invalidated the connection, which closes it — without waiting for the aborted worker thread to come back out of the driver call. Closing a connection while a thread is still inside a call on it is the concurrent access ADBC forbids, and DuckDB deadlocked on it, wedging that worker permanently. Because the offload is deliberately non-abandoning, the awaiting task could then never complete: an enclosing `move_on_after` could not rescue it, so a client disconnect during a query hung that request task and leaked a thread plus a connection. The poison-recovery now waits for the aborted worker to return before it drops the connection.

  Affects `AsyncCursor.execute`, `executemany`, the `fetch_*` methods, `adbc_ingest`, `adbc_execute_partitions`, `adbc_read_partition`, and streaming pulls on `AsyncRecordBatchReader` — every path that invalidates on abort. The non-poisoning paths (`adbc_prepare`, `adbc_execute_schema`, metadata readers) never invalidated and were never affected. No API change.

- A cancellation that arrived just after its query finished no longer evicts a healthy connection. The watcher could not distinguish "the worker is still in the driver" from "the worker just finished", so it fired `adbc_cancel` at a completed statement and ran the poison-recovery on a connection nothing had poisoned, dropping it from the pool. It now checks whether the worker is already out and leaves a finished call alone. The cancellation still propagates as before, so the only visible change is that the pool keeps a connection it used to discard.

### Documentation

The guides were audited against a live database, and the corrections below are behavioural rather than editorial. If you followed any of these, your code was affected.

- `pre_ping` was documented as an inert no-op on the standalone `QueuePool`. It is not inert: `pre_ping=True` raises `NotImplementedError` on the first re-checkout of a pooled connection. The first checkout succeeds, so this passes a smoke test and fails on the second request. Leave it at its `False` default and use `recycle`.
- Nothing said that pooled ADBC connections are not in autocommit mode. A write you never commit is rolled back when the connection checks in, silently and with the driver's row count already reported back to you. The async bulk-ingest example claimed "6 total" rows and then lost them. A new [Committing writes](guides/pool-lifecycle.md#committing-writes) section covers what to call and when.
- The SQLAlchemy ORM pattern has been removed rather than fixed. `creator=pool.connect` cannot work with any dialect, because a dialect is written against one specific DBAPI and calls that driver's own extras on every connection. It is replaced by a working FastAPI lifespan example and an explanation of the limitation.
- `adbc_execute_schema` was said to raise `NotSupportedError` on DuckDB. DuckDB implements it and returns a schema.
- Several config fields were named wrongly: `SnowflakeConfig` has `oauth_token` and `auth_type` (not `token` / `authenticator`), `BigQueryConfig` has `auth_credentials` (not `auth_credentials_path`), and the Snowflake schema keyword is `schema`, which its own alias requires — `schema_=` is rejected. `MySQLConfig.database` was documented as optional and is required.
- The raw `driver_path` example raised `ImportError`. A driver installed from PyPI ships no ADBC manifest, so a short name does not resolve to it; pass the package's own path helper, such as `adbc_driver_duckdb.driver_path()`.
- Config validation errors surface as Pydantic's `ValidationError`, not as `ConfigurationError` or `PoolhouseError`, because the validators run inside Pydantic. `except PoolhouseError` never fired there. Corrected across the ClickHouse, MySQL, Databricks and Databricks Python guides.

New coverage: async pool saturation and limiter sizing, choosing a `recycle` value against a warehouse idle timeout, FastAPI lifespan examples for both pools, a warning against calling the sync pool from an `async def` handler, and a note that non-ADBC connectors are not a supported extension point.

## [1.6.1] - 2026-07-08

### Added

- `pre_ping` is now a field on `BaseWarehouseConfig` (default `False`), so it can be set on any config or loaded from the `{PREFIX}_PRE_PING` environment variable — previously it was only a `create_pool` keyword. This completes the set of config-tunable pool fields.

### Fixed

- `create_pool`, `managed_pool`, and their async counterparts now honor a config's pool-tuning fields (`pool_size`, `max_overflow`, `timeout`, `recycle`, `pre_ping`). Previously these were read off the config but never forwarded, so `create_pool(SnowflakeConfig(pool_size=10))` and the documented `SNOWFLAKE_POOL_SIZE` environment override both silently produced a default-sized pool. Precedence is now: an explicit `create_pool` keyword overrides the config field, which overrides the built-in default used by the raw driver paths.
- Closed a related data-loss hazard: `create_pool(DuckDBConfig())` (in-memory) previously built a 5-connection pool, giving each connection an isolated empty database. It now honors the config's `pool_size=1`.

### Changed

- `DuckDBConfig` and `SQLiteConfig` now default `pool_size` conditionally: `1` for an in-memory database (the only safe value for their per-connection isolation / shared-state semantics) and `5` for a file-backed database, matching the other backends. An explicitly set `pool_size` (keyword or environment) is respected as before. File-backed pools are unaffected in size; in-memory pools now correctly stay at 1 end to end.

## [1.6.0] - 2026-07-08

### Features

- Add `DatabricksPythonConfig`, a Databricks backend built on the `databricks-sql-connector` package rather than the ADBC driver. It connects over the connector's Statement Execution ("kernel") path instead of Thrift, which is what **Lakehouse//RT** requires — RT rejects the Thrift protocol that the ADBC and ODBC drivers use. Reach for it only when you need that non-Thrift path; `DatabricksConfig` (the ADBC driver) stays the default for ordinary SQL warehouses.
- Install it with the new `databricks-python` extra (`pip install "adbc-poolhouse[databricks-python]"`), which pulls in `databricks-sql-connector[pyarrow]`. OAuth machine-to-machine auth also needs `databricks-sdk`; install the `databricks-python-m2m` extra for that, which layers the SDK on top of the base extra.
- Supports the same auth methods as `DatabricksConfig`: personal access token, OAuth U2M (browser), OAuth M2M (service principal), or a bring-your-own `credentials_provider` callable. Fields load from `DATABRICKS_PYTHON_*` environment variables, a separate namespace from the `DATABRICKS_*` prefix `DatabricksConfig` uses. Selecting OAuth M2M without `databricks-sdk` installed fails when the pool opens its first connection, with an error that points you at the `databricks-python-m2m` extra.
- Pooled connections present the ADBC DBAPI cursor surface, so downstream query code is unchanged, and the backend works with both the sync pool and the async surface. The ADBC-only methods the connector has no equivalent for (`adbc_ingest`, `adbc_prepare`, `adbc_execute_partitions`, the `adbc_get_*` metadata methods, and raw `fetch_arrow`) raise `NotSupportedError`.

The existing ADBC backends and public API are unchanged; this release only adds the new backend, so upgrading from 1.5.x needs no code changes.

## [1.5.1] - 2026-07-07

### Features

- Add `adbc_execute_partitions()` and `adbc_read_partition()` to `AsyncCursor`, closing the last gap in async/sync parity for the ADBC methods the sync raw-cursor path exposes. Both are thread-offloaded wrappers over the sync cursor:
  - `adbc_execute_partitions(operation, parameters=None)` executes a query and returns `(partitions, schema)` — a list of opaque partition descriptors plus the result-set schema (or `None`).
  - `adbc_read_partition(partition)` reads one descriptor into the cursor's result set; drain it afterwards with the existing async `fetch_*` methods.
- Both are cancellable and, like `execute`, invalidate the connection on abort (partitioned execution runs the query, so it is poisoning — unlike the non-poisoning `adbc_prepare` / `adbc_execute_schema`). Partitioned execution is a distributed/Flight-SQL extension; backends that do not implement it (DuckDB, etc.) surface the driver's native `NotSupportedError` unchanged through the offload chokepoint.

The async API stays behind the `[async]` extra and is still experimental. The sync path is unchanged.

## [1.5.0] - 2026-07-05

### Features

- Complete the async cursor surface. The four cursor methods deferred in 1.4.0 are now available on `AsyncCursor`, each a thread-offloaded wrapper over the underlying sync ADBC cursor:
  - `fetch_record_batch()` returns an `AsyncRecordBatchReader` for lazy Arrow streaming (`async for batch in reader:`), with each batch pull offloaded individually. The reader's lifetime is bound to its checked-out connection; reading after checkin surfaces the driver's native closed-stream error.
  - `adbc_ingest(table_name, data, mode=...)` bulk-writes Arrow data and returns the affected row count. `mode` is a typed `Literal`; note that `mode="replace"` **drops** the existing table.
  - `fetch_df()` and `fetch_polars()` return a `pandas.DataFrame` / `polars.DataFrame`. pandas and polars stay user-supplied — a missing dependency raises the native `ModuleNotFoundError` unchanged.
- Add the six `adbc_get_*` connection metadata methods (`adbc_get_info`, `adbc_get_objects`, `adbc_get_table_schema`, `adbc_get_table_types`, `adbc_get_statistics`, `adbc_get_statistic_names`) on `AsyncConnection` as offload wrappers; the streaming ones surface their native `RecordBatchReader`.
- Add `adbc_prepare()` and `adbc_execute_schema()` on `AsyncCursor`; `adbc_execute_schema()` returns the result Arrow schema without executing the query.
- Cancelling or timing out any of these calls fires `adbc_cancel` once and, for the stateful `adbc_ingest`, invalidates the connection so the pool is never left poisoned. Reads and schema resolutions are cancellable but non-poisoning.

This completes async/sync parity for the ADBC methods the sync raw-cursor path exposes (partitioned result sets remain deferred). The async API stays behind the `[async]` extra and is still experimental. The sync path is unchanged.

## [1.4.0] - 2026-07-01

### Features

- Add an optional `[async]` extra providing an anyio-based async surface (asyncio + trio). The async API is **experimental**: its surface may change between minor releases, and several features are not yet available.
- Add the async entry points `create_async_pool`, `managed_async_pool`, and `close_async_pool`, mirroring the sync `create_pool` / `managed_pool` / `close_pool` signatures.
- Add `AsyncPool`, `AsyncConnection`, and `AsyncCursor` wrappers exposing the awaited DBAPI surface, including `fetch_arrow_table`. Each blocking ADBC call runs on a worker thread.
- Size each async pool with a per-pool `CapacityLimiter` of `pool_size + max_overflow`, capping concurrent offloaded calls.
- Shield connection checkin so a cancelled task returns its connection cleanly, and route query cancellation through `adbc_cancel`.

The sync path is unchanged and gains no async dependency: installing without the `[async]` extra pulls in no anyio or trio.

## [1.3.1] - 2026-06-24

### Bug Fixes

- Propagate `catalog` and `schema` to the Databricks connection (DBX-02). `DatabricksConfig.to_adbc_kwargs()` now appends URL-encoded `?catalog=...&schema=...` to the DSN in decomposed mode, so unqualified table and view names resolve against the configured default namespace instead of failing with `TABLE_OR_VIEW_NOT_FOUND`. URI mode is unchanged. Matches how `SnowflakeConfig` and `TrinoConfig` already wire their namespace through.

## [1.3.0] - 2026-05-21

### Refactoring

- Route PyPI drivers through their own DBAPI module so pytest-adbc-replay monkeypatches intercept at the correct location

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
