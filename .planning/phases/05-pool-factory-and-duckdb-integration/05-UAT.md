---
status: complete
phase: 05-pool-factory-and-duckdb-integration
source: [05-01-SUMMARY.md, 05-02-SUMMARY.md]
started: 2026-02-25T00:00:00Z
updated: 2026-02-25T00:10:00Z
---

## Current Test

## Current Test

[testing complete]

## Tests

### 1. Import public API
expected: `from adbc_poolhouse import create_pool, PoolhouseError, ConfigurationError, DuckDBConfig` succeeds and prints "OK"
result: pass

### 2. Create pool with DuckDB and run a query
expected: |
  Run:
    python -c "
    import tempfile, pathlib
    from adbc_poolhouse import create_pool, DuckDBConfig
    with tempfile.TemporaryDirectory() as d:
        cfg = DuckDBConfig(database=str(pathlib.Path(d) / 'test.db'))
        pool = create_pool(cfg)
        conn = pool.connect()
        cur = conn.cursor()
        cur.execute('SELECT 42 AS answer')
        row = cur.fetchone()
        print('row:', row)
        cur.close()
        conn.close()
        pool.dispose()
        pool._adbc_source.close()
    "
  Expected: prints "row: (42,)" — connection checkout, query execution, checkin, and dispose all succeed.
result: pass

### 3. Default pool settings
expected: |
  Run:
    python -c "
    import tempfile, pathlib
    from adbc_poolhouse import create_pool, DuckDBConfig
    with tempfile.TemporaryDirectory() as d:
        cfg = DuckDBConfig(database=str(pathlib.Path(d) / 'test.db'))
        pool = create_pool(cfg)
        print('size:', pool.size())
        print('max_overflow:', pool._max_overflow)
        print('timeout:', pool._timeout)
        pool.dispose()
        pool._adbc_source.close()
    "
  Expected: prints size: 5, max_overflow: 3, timeout: 30
result: pass

### 4. Pool size override
expected: |
  Run:
    python -c "
    import tempfile, pathlib
    from adbc_poolhouse import create_pool, DuckDBConfig
    with tempfile.TemporaryDirectory() as d:
        cfg = DuckDBConfig(database=str(pathlib.Path(d) / 'test.db'))
        pool = create_pool(cfg, pool_size=10, recycle=7200)
        print('size:', pool.size())
        pool.dispose()
        pool._adbc_source.close()
    "
  Expected: prints size: 10
result: pass

### 5. Invalid config raises ValidationError
expected: |
  Run:
    python -c "
    from pydantic import ValidationError
    from adbc_poolhouse import DuckDBConfig
    try:
        DuckDBConfig(pool_size=0)
        print('ERROR: should have raised')
    except ValidationError as e:
        print('OK — raised ValidationError:', str(e)[:80])
    "
  Expected: prints "OK — raised ValidationError:" followed by error text mentioning "pool_size" and "0"
result: pass

### 6. Exception hierarchy
expected: |
  Run:
    python -c "
    from adbc_poolhouse import PoolhouseError, ConfigurationError
    print('ConfigurationError is PoolhouseError:', issubclass(ConfigurationError, PoolhouseError))
    print('ConfigurationError is ValueError:', issubclass(ConfigurationError, ValueError))
    "
  Expected: prints both True
result: pass

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
