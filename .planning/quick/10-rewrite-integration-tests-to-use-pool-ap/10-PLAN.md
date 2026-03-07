---
phase: 10-rewrite-integration-tests-to-use-pool-ap
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/integration/conftest.py
  - tests/integration/test_databricks.py
  - tests/integration/test_snowflake.py
autonomous: true
requirements: [QUICK-10]

must_haves:
  truths:
    - "Integration tests exercise create_pool/close_pool API, not raw driver connections"
    - "Tests use session-scoped pool fixtures from conftest.py"
    - "Cassette markers are preserved so replay works in CI"
    - "No per-test-file _connect_kwargs / _db_kwargs helpers remain"
  artifacts:
    - path: "tests/integration/conftest.py"
      provides: "Session-scoped snowflake_pool and databricks_pool fixtures"
      contains: "create_pool"
    - path: "tests/integration/test_databricks.py"
      provides: "Pool-based Databricks integration tests"
      contains: "databricks_pool"
    - path: "tests/integration/test_snowflake.py"
      provides: "Pool-based Snowflake integration tests"
      contains: "snowflake_pool"
  key_links:
    - from: "tests/integration/test_databricks.py"
      to: "tests/integration/conftest.py"
      via: "databricks_pool fixture injection"
      pattern: "def test_.*databricks_pool"
    - from: "tests/integration/test_snowflake.py"
      to: "tests/integration/conftest.py"
      via: "snowflake_pool fixture injection"
      pattern: "def test_.*snowflake_pool"
    - from: "tests/integration/conftest.py"
      to: "src/adbc_poolhouse/_pool_factory.py"
      via: "create_pool / close_pool imports"
      pattern: "from adbc_poolhouse import.*create_pool"
---

<objective>
Rewrite Databricks and Snowflake integration tests to use the pool API (create_pool/close_pool) via conftest fixtures instead of raw adbc_driver connections.

Purpose: The conftest.py already defines session-scoped pool fixtures (snowflake_pool, databricks_pool) but the test files bypass them entirely, building raw driver connections with private helper functions. This makes the integration tests exercise low-level driver wiring rather than the library's actual public API.

Output: Two rewritten test files that inject pool fixtures, exercise pool.connect() -> cursor -> execute -> close flow, and remove all raw-driver connection helpers. Cassette markers preserved for CI replay.
</objective>

<execution_context>
@/Users/paul/.claude/get-shit-done/workflows/execute-plan.md
@/Users/paul/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@tests/integration/conftest.py
@tests/integration/test_databricks.py
@tests/integration/test_snowflake.py
@src/adbc_poolhouse/_pool_factory.py

<interfaces>
<!-- Existing conftest fixtures the tests will consume -->

From tests/integration/conftest.py:
```python
@pytest.fixture(scope="session")
def snowflake_pool():
    """Session-scoped Snowflake pool, for recording cassettes locally."""
    config = SnowflakeConfig()
    pool = create_pool(config)
    yield pool
    close_pool(pool)

@pytest.fixture(scope="session")
def databricks_pool():
    """Session-scoped Databricks pool, for recording cassettes locally."""
    config = DatabricksConfig()
    pool = create_pool(config)
    yield pool
    close_pool(pool)
```

<!-- Pool API used in tests (from test_pool_factory.py pattern) -->
```python
# Checkout pattern:
conn = pool.connect()
cur = conn.cursor()
cur.execute("SELECT 42 AS answer")
row = cur.fetchone()
cur.close()
conn.close()
```

<!-- Pool type returned by create_pool -->
From src/adbc_poolhouse/_pool_factory.py:
```python
def create_pool(config: WarehouseConfig, ...) -> sqlalchemy.pool.QueuePool: ...
def close_pool(pool: sqlalchemy.pool.QueuePool) -> None: ...
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite test_databricks.py to use pool fixture</name>
  <files>tests/integration/test_databricks.py</files>
  <action>
Rewrite tests/integration/test_databricks.py to use the databricks_pool fixture from conftest instead of raw adbc_driver_manager.dbapi.connect() calls.

Changes:
1. Remove the _databricks_connect_kwargs() helper function entirely.
2. Remove the `import adbc_driver_manager.dbapi` import.
3. Remove the `from adbc_poolhouse import DatabricksConfig` import.
4. Remove the `from adbc_poolhouse._drivers import resolve_driver` import.
5. Remove the `from adbc_poolhouse._translators import translate_config` import.
6. Remove the `from dotenv import load_dotenv` import and the `from pathlib import Path` import (dotenv loading is handled by conftest.py).
7. Keep `from __future__ import annotations` and `from typing import Any`.
8. Keep `import pytest`.

For each test function, add `databricks_pool` as a parameter (fixture injection) and rewrite the body to use pool.connect():

test_connection_health(databricks_pool):
  - conn = databricks_pool.connect()
  - cur = conn.cursor()
  - cur.execute("SELECT 1")
  - row = cur.fetchone()
  - assert row is not None
  - assert row[0] == 1
  - cur.close()
  - conn.close()

test_arrow_round_trip(databricks_pool):
  - conn = databricks_pool.connect()
  - cur = conn.cursor()
  - cur.execute("SELECT 1 AS n, 'hello' AS s")
  - table = cur.fetch_arrow_table()
  - cur.close()
  - conn.close()
  - assert table is not None
  - assert table.num_rows == 1

Keep all existing decorators (@pytest.mark.databricks, @pytest.mark.adbc_cassette) and docstrings intact. Update docstrings to reflect pool-based approach (mention "via pool API" instead of "via adbc_driver_manager"). Keep the "In CI" / "To record" doc blocks.

Note per user decision: tests will be broken until pytest-adbc-replay adds adbc_clone() support -- that is expected and acceptable.
  </action>
  <verify>
    <automated>cd /Users/paul/Documents/Dev/Personal/adbc-poolhouse && python -c "import ast; ast.parse(open('tests/integration/test_databricks.py').read()); print('syntax ok')" && python -c "
import ast, sys
tree = ast.parse(open('tests/integration/test_databricks.py').read())
fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
for fn in fns:
    args = [a.arg for a in fn.args.args]
    assert 'databricks_pool' in args, f'{fn.name} missing databricks_pool fixture'
    print(f'{fn.name}: OK (has databricks_pool)')
# Ensure no raw connect helper remains
src = open('tests/integration/test_databricks.py').read()
assert '_databricks_connect_kwargs' not in src, 'old helper still present'
assert 'adbc_driver_manager.dbapi' not in src, 'raw driver import still present'
print('All checks passed')
"</automated>
  </verify>
  <done>test_databricks.py uses databricks_pool fixture for all tests; no raw driver imports or _databricks_connect_kwargs helper remain; cassette markers preserved.</done>
</task>

<task type="auto">
  <name>Task 2: Rewrite test_snowflake.py to use pool fixture</name>
  <files>tests/integration/test_snowflake.py</files>
  <action>
Rewrite tests/integration/test_snowflake.py to use the snowflake_pool fixture from conftest instead of raw adbc_driver_snowflake.dbapi.connect() calls.

Changes:
1. Remove the _snowflake_db_kwargs() helper function entirely.
2. Remove the `import adbc_driver_snowflake.dbapi` import.
3. Remove the `from adbc_poolhouse import SnowflakeConfig` import.
4. Remove the `from adbc_poolhouse._translators import translate_config` import.
5. Remove the `from dotenv import load_dotenv` import and the `from pathlib import Path` import (dotenv loading is handled by conftest.py).
6. Keep `from __future__ import annotations` and `from typing import Any`.
7. Keep `import pytest`.

For each test function, add `snowflake_pool` as a parameter (fixture injection) and rewrite the body to use pool.connect():

test_connection_health(snowflake_pool):
  - conn = snowflake_pool.connect()
  - cur = conn.cursor()
  - cur.execute("SELECT 1")
  - row = cur.fetchone()
  - assert row is not None
  - assert row[0] == 1
  - cur.close()
  - conn.close()

test_arrow_round_trip(snowflake_pool):
  - conn = snowflake_pool.connect()
  - cur = conn.cursor()
  - cur.execute("SELECT 1 AS n, 'hello' AS s")
  - table = cur.fetch_arrow_table()
  - cur.close()
  - conn.close()
  - assert table is not None
  - assert table.num_rows == 1

Keep all existing decorators (@pytest.mark.snowflake, @pytest.mark.adbc_cassette) and docstrings intact. Update docstrings to reflect pool-based approach (mention "via pool API" instead of "via adbc_driver_snowflake"). Keep the "In CI" / "To record" doc blocks.

Note per user decision: tests will be broken until pytest-adbc-replay adds adbc_clone() support -- that is expected and acceptable.
  </action>
  <verify>
    <automated>cd /Users/paul/Documents/Dev/Personal/adbc-poolhouse && python -c "import ast; ast.parse(open('tests/integration/test_snowflake.py').read()); print('syntax ok')" && python -c "
import ast, sys
tree = ast.parse(open('tests/integration/test_snowflake.py').read())
fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
for fn in fns:
    args = [a.arg for a in fn.args.args]
    assert 'snowflake_pool' in args, f'{fn.name} missing snowflake_pool fixture'
    print(f'{fn.name}: OK (has snowflake_pool)')
# Ensure no raw connect helper remains
src = open('tests/integration/test_snowflake.py').read()
assert '_snowflake_db_kwargs' not in src, 'old helper still present'
assert 'adbc_driver_snowflake.dbapi' not in src, 'raw driver import still present'
print('All checks passed')
"</automated>
  </verify>
  <done>test_snowflake.py uses snowflake_pool fixture for all tests; no raw driver imports or _snowflake_db_kwargs helper remain; cassette markers preserved.</done>
</task>

</tasks>

<verification>
1. Both test files parse as valid Python (syntax check).
2. Every test function accepts its respective pool fixture as a parameter.
3. No raw driver imports (adbc_driver_manager.dbapi, adbc_driver_snowflake.dbapi) remain in test files.
4. No private helper functions (_databricks_connect_kwargs, _snowflake_db_kwargs) remain.
5. conftest.py is unchanged (already correct).
6. All @pytest.mark.databricks, @pytest.mark.snowflake, and @pytest.mark.adbc_cassette decorators preserved.
7. Ruff lint passes: `uv run ruff check tests/integration/`
</verification>

<success_criteria>
- Integration tests use pool fixtures (snowflake_pool, databricks_pool) for all database interactions
- Raw driver connection code fully removed from test files
- Cassette markers preserved for CI replay compatibility
- conftest.py remains unchanged
- `uv run ruff check tests/integration/` passes
</success_criteria>

<output>
After completion, create `.planning/quick/10-rewrite-integration-tests-to-use-pool-ap/10-SUMMARY.md`
</output>
