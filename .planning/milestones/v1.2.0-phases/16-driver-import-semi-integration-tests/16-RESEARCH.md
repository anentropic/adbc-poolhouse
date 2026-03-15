# Phase 1: Driver Import Semi-Integration Tests - Research

**Researched:** 2026-03-12
**Domain:** Python testing, pytest, ADBC driver mocking, semi-integration testing
**Confidence:** HIGH

## Summary

This phase creates semi-integration tests that verify the full driver import → pool creation → connection attempt flow for all 12 supported ADBC backends. The tests use real driver imports (not mocked) but mock the actual connection to assert correct kwargs without requiring credentials or network access.

**Primary recommendation:** Use pytest with `unittest.mock.patch` at two different targets based on driver type (Foundry/DuckDB vs PyPI), following the established patterns in `test_pool_factory.py` and `test_drivers.py`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Test scope:**
- Full stack verification: driver import, pool creation, connection attempt with exact kwargs
- Real driver imports (not mocked) - all 12 backends must pass, no skipping
- PyPI drivers installed in CI via pip/uv (snowflake, bigquery, postgresql, flightsql, sqlite)
- Foundry drivers installed in CI via dbc CLI (clickhouse, databricks, mssql, mysql, redshift, trino)
- Justfile recipe for local setup: install all drivers (PyPI + Foundry) in one command

**Mocking depth:**
- Two mock points based on driver type:
  - Foundry drivers + DuckDB: mock `adbc_driver_manager.dbapi.connect`
  - PyPI drivers: mock each driver's own `dbapi.connect` (e.g., `adbc_driver_snowflake.dbapi.connect`)
- Mock returns object with `adbc_clone` method (tests pool wiring)
- Assert all args: driver_path, db_kwargs, entrypoint (for DuckDB)

**Test organization:**
- Single file: `tests/imports/test_driver_imports.py`
- One test class per backend (12 classes)
- New `tests/imports/` directory

**Error case coverage:**
- Happy path only - error cases already covered in `test_drivers.py`

**Bug handling strategy:**
- Minor bugs: fix in this phase
- Larger refactoring: separate bug-fix phase
- User consulted when bugs discovered to determine scope

### Claude's Discretion

None explicitly stated - all implementation details were locked.

### Deferred Ideas (OUT OF SCOPE)

None - discussion stayed within phase scope.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TEST-01 | Import All Drivers | `resolve_driver()` and `resolve_dbapi_module()` in `_drivers.py` provide driver resolution; PyPI packages in `_PYPI_PACKAGES`, Foundry in `_FOUNDRY_DRIVERS` |
| TEST-02 | Mock Connection Attempts | Two mock targets identified: `adbc_driver_manager.dbapi.connect` for Foundry/DuckDB, `{driver}.dbapi.connect` for PyPI drivers; mock must return object with `adbc_clone` method |
| TEST-03 | Assert Expected Args | `create_adbc_connection()` signature: `(driver_path, kwargs, entrypoint=..., dbapi_module=...)`; DuckDB uses `entrypoint='duckdb_adbc_init'` |
| TEST-04 | Coverage for All 12 Backends | 12 config classes available: DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, SQLite, MySQL, ClickHouse |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=8.0.0 | Test framework | Already in project, pytest markers configured |
| unittest.mock | stdlib | Patching/mocking | Established pattern in `test_drivers.py` and `test_pool_factory.py` |
| adbc-driver-manager | >=1.8.0 | Mock target for Foundry/DuckDB | Always installed as transitive dep |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-adbc-replay | >=1.0.0a3 | Cassette replay (not used in this phase) | Integration tests only |
| pydantic | (via pydantic-settings) | Config validation | Creating test config instances |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| unittest.mock.patch | pytest-mock | pytest-mock adds unnecessary dependency; stdlib mock is sufficient for this use case |
| Single test function | One class per backend | Classes provide better organization and isolation per backend; matches existing pattern |

**Installation:**
```bash
# Already installed - no new dependencies needed
uv sync --dev
```

## Architecture Patterns

### Recommended Project Structure
```
tests/
├── conftest.py              # Existing: _clear_warehouse_env_vars autouse fixture
├── imports/                 # NEW directory
│   ├── __init__.py          # Empty, makes it a package
│   └── test_driver_imports.py  # NEW: 12 test classes, one per backend
├── integration/             # Existing: cassette-based tests
├── test_drivers.py          # Existing: unit tests for driver resolution
└── test_pool_factory.py     # Existing: pool creation + mock patterns
```

### Pattern 1: Mock Pool Factory Wiring
**What:** Mock `create_adbc_connection` to return a connection with `adbc_clone` method, then assert kwargs.
**When to use:** Testing that config → kwargs translation is correct without real connections.
**Example:**
```python
# Source: tests/test_pool_factory.py (TestDatabricksPoolFactory)
from unittest.mock import MagicMock, patch

config = DatabricksConfig(host="host", http_path="/sql/1.0/warehouses/abc", token=SecretStr("token"))
mock_conn = MagicMock()
mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

with patch(
    "adbc_poolhouse._pool_factory.create_adbc_connection",
    return_value=mock_conn,
) as mock_factory:
    pool = create_pool(config)
    pool.dispose()

mock_factory.assert_called_once()
call_args = mock_factory.call_args
actual_kwargs = call_args.args[1]
assert actual_kwargs.get("uri") == "expected_uri"
```

### Pattern 2: Mock adbc_driver_manager.dbapi.connect
**What:** Mock the ADBC driver manager's connect function directly.
**When to use:** Testing Foundry drivers or DuckDB where connection goes through `adbc_driver_manager.dbapi.connect`.
**Example:**
```python
# Source: tests/test_drivers.py (TestCreateAdbcConnectionFoundryNotFound)
from unittest.mock import patch

with patch("adbc_driver_manager.dbapi.connect", side_effect=not_found_exc):
    create_adbc_connection("databricks", {})
```

### Pattern 3: PyPI Driver DBAPI Mock
**What:** Mock the driver's own `dbapi.connect` instead of the manager.
**When to use:** PyPI drivers (Snowflake, BigQuery, etc.) where `resolve_dbapi_module()` returns the driver's own dbapi.
**Example:**
```python
# For PyPI drivers, mock at the driver's dbapi module
with patch("adbc_driver_snowflake.dbapi.connect", return_value=mock_conn) as mock_connect:
    pool = create_pool(SnowflakeConfig(account="test"))
    # mock_connect called with db_kwargs=kwargs
```

### Anti-Patterns to Avoid
- **Mocking driver imports:** Don't mock `find_spec` or `__import__` for these tests — the goal is to verify real driver imports work.
- **Skipping backends:** All 12 backends must pass; no `pytest.mark.skip` on missing drivers.
- **Mocking at wrong level:** PyPI drivers go through their own `dbapi.connect`, not `adbc_driver_manager.dbapi.connect`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mock connection object | Custom class with adbc_clone | `MagicMock(adbc_clone=MagicMock(return_value=MagicMock()))` | MagicMock is sufficient; no need for custom mock class |
| Test organization | Custom test runner | pytest with class-based organization | pytest discovery + classes per backend is standard and maintainable |

**Key insight:** The mock patterns are already established in `test_pool_factory.py`. Reuse those patterns directly.

## Common Pitfalls

### Pitfall 1: Wrong Mock Target for PyPI Drivers
**What goes wrong:** Mocking `adbc_driver_manager.dbapi.connect` when the driver uses its own dbapi.
**Why it happens:** `resolve_dbapi_module()` returns `"adbc_driver_snowflake.dbapi"` for installed PyPI drivers, so the connection goes through that module.
**How to avoid:** Check `resolve_dbapi_module(config)` — if it returns a string, mock that module's `connect`; if `None`, mock `adbc_driver_manager.dbapi.connect`.
**Warning signs:** Mock's `assert_called` fails; connection attempt goes to real driver.

### Pitfall 2: Forgetting DuckDB Entrypoint
**What goes wrong:** DuckDB tests fail because `entrypoint='duckdb_adbc_init'` is not asserted.
**Why it happens:** DuckDB is the only driver that requires an entrypoint.
**How to avoid:** DuckDB test must assert `entrypoint='duckdb_adbc_init'` in the mock call.
**Warning signs:** DuckDB-specific test passes but real DuckDB connections would fail.

### Pitfall 3: Env Var Contamination
**What goes wrong:** Tests fail inconsistently due to env vars from `.env` or CI secrets.
**Why it happens:** pydantic-settings reads env vars at `__init__` time, overriding explicit kwargs.
**How to avoid:** The existing `_clear_warehouse_env_vars` autouse fixture in `conftest.py` handles this automatically.
**Warning signs:** Tests pass locally but fail in CI (or vice versa).

### Pitfall 4: Missing adbc_clone on Mock
**What goes wrong:** `create_pool()` fails with AttributeError when calling `source.adbc_clone`.
**Why it happens:** The pool factory calls `source.adbc_clone` to create the pool creator function.
**How to avoid:** Mock connection must have `adbc_clone` method: `mock_conn.adbc_clone = MagicMock(return_value=MagicMock())`.
**Warning signs:** Test fails at `create_pool()` call, not at assertion.

## Code Examples

Verified patterns from existing test files:

### Mock Connection with adbc_clone (from test_pool_factory.py)
```python
# Source: tests/test_pool_factory.py:140-142
mock_conn = MagicMock()
mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

with patch(
    "adbc_poolhouse._pool_factory.create_adbc_connection",
    return_value=mock_conn,
) as mock_factory:
    pool = create_pool(config)
    pool.dispose()
```

### Asserting Kwargs on Mock Call (from test_pool_factory.py)
```python
# Source: tests/test_pool_factory.py:151-156
mock_factory.assert_called_once()
call_args = mock_factory.call_args
# create_adbc_connection(driver_path, kwargs, entrypoint=entrypoint)
# kwargs is the second positional argument (index 1)
actual_kwargs = call_args.args[1]
assert actual_kwargs.get("uri") == expected_uri
```

### Foundry/DuckDB Mock Target (from test_drivers.py)
```python
# Source: tests/test_drivers.py:193
with patch("adbc_driver_manager.dbapi.connect", side_effect=not_found_exc):
    create_adbc_connection("databricks", {})
```

### SQLite Mock Pattern (from test_pool_factory.py)
```python
# Source: tests/test_pool_factory.py:330-344
config = SQLiteConfig()  # database=":memory:", pool_size=1
mock_conn = MagicMock()
mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

with patch(
    "adbc_poolhouse._pool_factory.create_adbc_connection",
    return_value=mock_conn,
) as mock_factory:
    pool = create_pool(config)
    pool.dispose()

mock_factory.assert_called_once()
call_args = mock_factory.call_args
actual_kwargs = call_args.args[1]
assert actual_kwargs == {"uri": ":memory:"}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Mock at adbc_driver_manager for all | Two-path mocking based on driver type | Current design | PyPI drivers use their own dbapi for tooling compatibility (pytest-adbc-replay) |

**Deprecated/outdated:**
- N/A — patterns are current

## Mock Target Reference

| Backend | Config Class | Driver Type | Mock Target | Notes |
|---------|-------------|-------------|-------------|-------|
| DuckDB | `DuckDBConfig` | Special | `adbc_driver_manager.dbapi.connect` | Requires `entrypoint='duckdb_adbc_init'` |
| Snowflake | `SnowflakeConfig` | PyPI | `adbc_driver_snowflake.dbapi.connect` | If driver installed; else `adbc_driver_manager.dbapi.connect` |
| BigQuery | `BigQueryConfig` | PyPI | `adbc_driver_bigquery.dbapi.connect` | If driver installed |
| PostgreSQL | `PostgreSQLConfig` | PyPI | `adbc_driver_postgresql.dbapi.connect` | If driver installed |
| FlightSQL | `FlightSQLConfig` | PyPI | `adbc_driver_flightsql.dbapi.connect` | If driver installed |
| SQLite | `SQLiteConfig` | PyPI (special) | `adbc_driver_manager.dbapi.connect` | SQLite dbapi has incompatible signature, always uses manager |
| Databricks | `DatabricksConfig` | Foundry | `adbc_driver_manager.dbapi.connect` | |
| Redshift | `RedshiftConfig` | Foundry | `adbc_driver_manager.dbapi.connect` | |
| Trino | `TrinoConfig` | Foundry | `adbc_driver_manager.dbapi.connect` | |
| MSSQL | `MSSQLConfig` | Foundry | `adbc_driver_manager.dbapi.connect` | |
| MySQL | `MySQLConfig` | Foundry | `adbc_driver_manager.dbapi.connect` | |
| ClickHouse | `ClickHouseConfig` | Foundry | `adbc_driver_manager.dbapi.connect` | |

## Driver Installation Reference

| Backend | Source | Install Command | CI Location |
|---------|--------|-----------------|-------------|
| DuckDB | PyPI | `pip install adbc-poolhouse[duckdb]` | dev dependencies |
| Snowflake | PyPI | `pip install adbc-poolhouse[snowflake]` | dev dependencies |
| BigQuery | PyPI | `pip install adbc-poolhouse[bigquery]` | CI only |
| PostgreSQL | PyPI | `pip install adbc-poolhouse[postgresql]` | CI only |
| FlightSQL | PyPI | `pip install adbc-poolhouse[flightsql]` | CI only |
| SQLite | PyPI | `pip install adbc-poolhouse[sqlite]` | dev dependencies |
| Databricks | Foundry | `dbc install databricks` | CI + local |
| Redshift | Foundry | `dbc install redshift` | CI + local |
| Trino | Foundry | `dbc install trino` | CI + local |
| MSSQL | Foundry | `dbc install mssql` | CI + local |
| MySQL | Foundry | `dbc install mysql` | CI + local |
| ClickHouse | Foundry | `dbc install --pre clickhouse` | CI + local (alpha only) |

## Open Questions

1. **Should tests use `create_adbc_connection` mock or the driver-level mock?**
   - What we know: CONTEXT.md specifies two mock points based on driver type
   - What's unclear: Whether to mock at `_pool_factory.create_adbc_connection` level or at the actual driver `dbapi.connect` level
   - Recommendation: Mock at `_pool_factory.create_adbc_connection` level for simplicity — this is the established pattern in `test_pool_factory.py` and avoids needing to know which dbapi module to target. The key assertion is on kwargs passed to `create_adbc_connection`.

2. **Minimum viable config for each backend?**
   - What we know: Each config class has different required fields
   - What's unclear: Exact minimal config for each backend that passes validation
   - Recommendation: Use configs that pass Pydantic validation with minimal fields:
     - `DuckDBConfig()` — defaults to `:memory:`
     - `SnowflakeConfig(account="test")` — only `account` is required
     - `BigQueryConfig()` — no required fields
     - `PostgreSQLConfig()` — no required fields (but would fail real connection)
     - `FlightSQLConfig()` — has required `uri` field
     - `SQLiteConfig()` — defaults to `:memory:`
     - `DatabricksConfig(uri=SecretStr("databricks://..."))` — requires uri or decomposed fields
     - `RedshiftConfig()` — no required fields
     - `TrinoConfig()` — no required fields
     - `MSSQLConfig()` — no required fields
     - `MySQLConfig(host="h", user="u", database="db")` — has required fields
     - `ClickHouseConfig(host="h", username="u")` — has required fields

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/imports/test_driver_imports.py -v` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | Import all drivers | semi-integration | `uv run pytest tests/imports/test_driver_imports.py -v` | ❌ Wave 0 |
| TEST-02 | Mock connection attempts | semi-integration | `uv run pytest tests/imports/test_driver_imports.py -v` | ❌ Wave 0 |
| TEST-03 | Assert expected args | semi-integration | `uv run pytest tests/imports/test_driver_imports.py -v` | ❌ Wave 0 |
| TEST-04 | Coverage for all 12 backends | semi-integration | `uv run pytest tests/imports/test_driver_imports.py -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/imports/test_driver_imports.py -v`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/imports/__init__.py` — makes imports a package
- [ ] `tests/imports/test_driver_imports.py` — 12 test classes for all backends
- [ ] Justfile recipe: `install-all-drivers` — combines PyPI + Foundry driver installation

*(Existing test infrastructure: `conftest.py` with `_clear_warehouse_env_vars` autouse fixture, pytest configured in pyproject.toml)*

## Sources

### Primary (HIGH confidence)
- Project source code: `src/adbc_poolhouse/_drivers.py`, `_driver_api.py`, `_pool_factory.py`
- Existing tests: `tests/test_drivers.py`, `tests/test_pool_factory.py`, `tests/conftest.py`
- CONTEXT.md: User decisions and code context

### Secondary (MEDIUM confidence)
- pyproject.toml: Dependencies and test configuration
- justfile: Existing install patterns for Foundry drivers

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All dependencies already in project; patterns established in existing tests
- Architecture: HIGH - Clear patterns from CONTEXT.md and existing test files
- Pitfalls: HIGH - Derived from actual code analysis and existing test patterns

**Research date:** 2026-03-12
**Valid until:** 30 days (stable Python testing patterns)
