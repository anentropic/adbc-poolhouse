---
status: resolved
trigger: "Investigate documentation issues in pool lifecycle guide"
created: 2026-03-15T00:00:00Z
updated: 2026-03-15T00:00:00Z
---

## Current Focus

hypothesis: Pool lifecycle guide has stale "plugin" references, missing "Create a pool" section, and incomplete raw driver argument documentation
test: Read guide, source code, and config classes to compare
expecting: Confirmed documentation gaps
next_action: Return structured diagnosis

## Symptoms

expected: Guide should explain all three create_pool paths (config, driver_path, dbapi_module) with accurate terminology
actual: Guide references non-existent "plugin development", jumps to checkout without explaining pool creation, and raw driver section lacks detail
errors: n/a (documentation issue)
reproduction: Read docs/src/guides/pool-lifecycle.md
started: Existing content, likely from before plugin concept was removed

## Evidence

- timestamp: 2026-03-15
  checked: grep for "plugin" in entire src/ directory
  found: Zero matches -- "plugin" concept does not exist in codebase
  implication: Line 82 reference to "plugin development" is stale/incorrect

- timestamp: 2026-03-15
  checked: Guide structure (sections)
  found: Sections are: "Checking out and returning connections" -> "Disposing the pool" -> "Pytest fixture pattern" -> "Tuning the pool" -> "Raw driver arguments" -> "Common mistakes" -> "See also". No "Create a pool" section.
  implication: Reader jumps from intro directly to checkout with no explanation of how to create a pool

- timestamp: 2026-03-15
  checked: Config classes in src/adbc_poolhouse/
  found: 12 config classes exported: DuckDBConfig, SQLiteConfig, SnowflakeConfig, BigQueryConfig, PostgreSQLConfig, FlightSQLConfig, DatabricksConfig, RedshiftConfig, TrinoConfig, MSSQLConfig, ClickHouseConfig, MySQLConfig
  implication: Guide should mention pre-defined configs exist for most warehouse backends

- timestamp: 2026-03-15
  checked: create_pool() overloads in _pool_factory.py
  found: Three overloads: (1) config positional, (2) driver_path+db_kwargs, (3) dbapi_module+db_kwargs. driver_path typed as `str`. Docstring says "Path to a native ADBC driver shared library, or a short driver name for manifest-based resolution"
  implication: Guide line 88 says driver_path is "path to a shared library or a short driver name" but doesn't explain what "short driver name" means or link to ADBC docs

- timestamp: 2026-03-15
  checked: _driver_api.py create_adbc_connection
  found: When dbapi_module is provided, it calls importlib.import_module(dbapi_module).connect(db_kwargs=...). When driver_path is provided, it calls adbc_driver_manager.dbapi.connect(driver=driver_path, entrypoint=..., db_kwargs=...). dbapi_module docstring says "e.g. adbc_driver_snowflake.dbapi"
  implication: dbapi_module must be a dotted Python module path that exposes connect(db_kwargs=...). Guide line 120 says "must expose a connect(db_kwargs=...) function" which is correct but could be more specific about examples

- timestamp: 2026-03-15
  checked: How configs use _driver_path() vs _dbapi_module()
  found: PyPI drivers (Snowflake, FlightSQL, BigQuery, etc.) return both a resolved shared library path AND a dbapi_module string. Foundry drivers (Trino, MSSQL, etc.) return only a short name like "trino" for driver_path and None for dbapi_module
  implication: driver_path accepts two kinds of values -- (1) absolute filesystem path to .so/.dylib, (2) short name for ADBC driver manager manifest lookup. Guide should distinguish these

## Resolution

root_cause: Pool lifecycle guide has three documentation gaps -- stale "plugin" reference, missing introductory "Create a pool" section, and insufficient detail in the raw driver arguments section about driver_path value types and dbapi_module expectations
fix: not applied (diagnosis only)
verification: n/a
files_changed: []
