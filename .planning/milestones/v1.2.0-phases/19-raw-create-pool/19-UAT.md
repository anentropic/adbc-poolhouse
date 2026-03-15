---
status: resolved
phase: 19-raw-create-pool
source: [19-01-SUMMARY.md, 19-02-SUMMARY.md]
started: 2026-03-15T12:30:00Z
updated: 2026-03-15T12:55:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Test suite passes
expected: Run `uv run pytest`. All 238 tests pass with no failures or errors.
result: pass

### 2. Type checking passes
expected: Run `uv run basedpyright`. Zero errors reported under strict mode.
result: pass

### 3. Raw driver_path create_pool works
expected: `create_pool(driver_path=adbc_driver_duckdb.driver_path(), db_kwargs={"path": ":memory:"}, entrypoint="duckdb_adbc_init")` returns a working QueuePool.
result: pass

### 4. Raw dbapi_module managed_pool works
expected: `managed_pool(dbapi_module="adbc_driver_duckdb.dbapi", db_kwargs={"path": ":memory:"})` works as a context manager, yields a pool, and cleans up on exit.
result: issue
reported: "mod.connect(db_kwargs=kwargs) crashes — TypeError: Connection.__init__() got an unexpected keyword argument 'db_kwargs'. The dbapi connect() function doesn't accept db_kwargs as a keyword argument."
severity: blocker

### 5. Mutual exclusivity error
expected: Calling `create_pool(driver_path="x", dbapi_module="y", db_kwargs={})` raises `TypeError` with a clear message about not passing both arguments.
result: pass

### 6. Docs build cleanly
expected: Run `uv run mkdocs build --strict`. Builds with no warnings or errors.
result: pass

### 7. Pool lifecycle guide has raw driver section
expected: Open `docs/src/guides/pool-lifecycle.md`. There is a "Raw driver arguments" section with tabbed examples showing both native ADBC and Python dbapi usage patterns.
result: issue
reported: "References 'plugin development' which no longer exists. Page needs a new 'Create a pool' section before 'Checking out and returning connections' explaining pre-defined config classes for most warehouse backends OR raw driver arguments. 'Raw driver arguments' section needs: distinction between driver_path and dbapi_module, possible value types for driver_path with linked reference to ADBC docs, and expected dbapi_module value explained."
severity: major

## Summary

total: 7
passed: 5
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "managed_pool(dbapi_module=...) works as a context manager"
  status: resolved
  reason: "User reported: mod.connect(db_kwargs=kwargs) crashes — TypeError: Connection.__init__() got an unexpected keyword argument 'db_kwargs'"
  severity: blocker
  test: 4
  root_cause: "_driver_api.py line 80 calls mod.connect(db_kwargs=kwargs) assuming all ADBC dbapi modules accept db_kwargs. DuckDB/SQLite drivers have incompatible connect() signatures — DuckDB takes (path, **kwargs), SQLite takes (uri, **kwargs). The db_kwargs keyword flows through **kwargs into Connection.__init__() which raises TypeError."
  artifacts:
    - path: "src/adbc_poolhouse/_driver_api.py"
      issue: "Line 80: mod.connect(db_kwargs=kwargs) assumes uniform db_kwargs parameter across all PyPI ADBC driver dbapi modules"
    - path: "src/adbc_poolhouse/_pool_factory.py"
      issue: "dbapi_module branch passes db_kwargs through without signature adaptation"
  missing:
    - "Handle two distinct connect() signature families: Family A (Snowflake, PostgreSQL, BigQuery) accepts db_kwargs=, Family B (DuckDB, SQLite) does not"
    - "Either introspect mod.connect signature, or document that DuckDB/SQLite should use driver_path instead"
  debug_session: ".planning/debug/dbapi-module-connect-kwargs.md"

- truth: "Pool lifecycle guide has correct content with raw driver section"
  status: resolved
  reason: "User reported: References 'plugin development' which no longer exists. Missing 'Create a pool' section. Raw driver arguments section lacks detail."
  severity: major
  test: 7
  root_cause: "Guide has stale 'plugin development' reference (no plugin concept in codebase), missing introductory 'Create a pool' section, and insufficient detail in 'Raw driver arguments' about driver_path value types and dbapi_module expectations."
  artifacts:
    - path: "docs/src/guides/pool-lifecycle.md"
      issue: "Line 82: stale 'plugin development' reference; missing 'Create a pool' section; raw driver section lacks driver_path/dbapi_module distinction"
  missing:
    - "Remove 'plugin development' reference"
    - "Add 'Create a pool' section before 'Checking out and returning connections' covering 12 config classes and raw driver alternative"
    - "Expand driver_path to distinguish native library path vs short name for manifest resolution, with link to ADBC docs"
    - "Explain dbapi_module expects dotted module path like 'adbc_driver_snowflake.dbapi'"
  debug_session: ".planning/debug/pool-lifecycle-guide-issues.md"
