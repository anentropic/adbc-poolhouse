# Phase 18: Registration Removal - Research

**Researched:** 2026-03-15
**Domain:** Python refactoring -- self-describing config classes, registry deletion, Protocol evolution
**Confidence:** HIGH

## Summary

Phase 18 eliminates the backend registry (`_registry.py`) and driver dispatch layer (`_drivers.py`) by making each config class fully self-describing. After this phase, a config instance carries everything `create_pool()` needs: `to_adbc_kwargs()`, `_driver_path()`, `_adbc_entrypoint()`, and `_dbapi_module()`. No external lookup, no lazy registration, no dispatch tables.

The codebase is well-prepared for this refactoring. All 12 config classes already implement `to_adbc_kwargs()` and `_adbc_entrypoint()` (completed in Phase 17.5). The remaining work is adding `_driver_path()` and `_dbapi_module()` to each config, inlining their logic into `create_pool()`, and deleting the registry machinery. The refactoring is purely internal -- no public API surface changes for consumers using config classes.

**Primary recommendation:** Add `_driver_path()` and `_dbapi_module()` to `BaseWarehouseConfig` as concrete defaults (NotImplementedError and None respectively), implement in all 12 configs, rewrite `create_pool()` to call config methods directly, then delete `_registry.py` and `_drivers.py`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Instance method `_driver_path() -> str` on every config class
- Added to `WarehouseConfig` Protocol and `BaseWarehouseConfig` (raises NotImplementedError)
- Consider making `BaseWarehouseConfig` an ABC (abstract base class)
- Shared helper for PyPI/DuckDB driver resolution: takes `method_name` arg so it works for both `_driver_path()` and `driver_path()` conventions across driver packages
- Helper lives in `_base_config.py` as a static/class method
- Manifest fallback preserved: if `find_spec` returns None, return package name string for `adbc_driver_manager` manifest resolution
- DuckDB uses same helper (not special-cased) since `adbc_driver_duckdb.driver_path()` works
- Foundry configs return a static string (e.g., `"databricks"`, `"clickhouse"`)
- Move `_PYPI_PACKAGES` dict logic into config classes as `_dbapi_module() -> str | None`
- Configs that have PyPI drivers return their dbapi module name when installed, None otherwise
- Foundry/DuckDB configs return None
- SQLite excluded (incompatible dbapi signature) -- returns None
- `resolve_dbapi_module()` function eliminated
- Protocol (structural typing) is sufficient -- no subclass requirement
- Minimum contract: `to_adbc_kwargs()` + `_driver_path()` (both required)
- `_adbc_entrypoint()` optional -- returns None by default in BaseWarehouseConfig
- `_dbapi_module()` optional -- returns None by default
- Duck typing validation: no isinstance check in create_pool(), just call the methods
- If a config doesn't implement required methods, Python raises AttributeError naturally (EAFP)
- Delete `_registry.py` entirely -- no backwards compat shim
- Delete `register_backend` from `__init__.py` exports and `__all__`
- Delete all three registry exceptions: `RegistryError`, `BackendAlreadyRegisteredError`, `BackendNotRegisteredError`
- Delete `_drivers.py` -- shared helpers move to `_base_config.py`, dispatch functions inlined into `create_pool()`
- Delete `_setup_lazy_registrations()` and all lazy registration closures
- Delete `tests/test_registry.py` -- rework or replace with config method tests
- Inline `resolve_driver()` into `create_pool()`: call `config._driver_path()` directly
- Inline `resolve_dbapi_module()` into `create_pool()`: call `config._dbapi_module()` directly
- `create_pool()` becomes: `driver_path = config._driver_path()`, `kwargs = config.to_adbc_kwargs()`, `entrypoint = config._adbc_entrypoint()`, `dbapi_module = config._dbapi_module()`
- No wrapper functions -- direct method calls

### Claude's Discretion
- Whether BaseWarehouseConfig becomes a formal ABC or just has NotImplementedError defaults
- Exact signature and naming of the shared driver resolution helper
- How to structure `_base_config.py` with the added helper methods
- Whether `_drivers.py` is deleted or kept as an empty module for import compat
- Test restructuring details (what replaces test_registry.py)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SELF-DESC | Config classes fully self-describing (driver path, kwargs, dbapi, entrypoint) | Each config gets `_driver_path()` and `_dbapi_module()` methods; combined with existing `to_adbc_kwargs()` and `_adbc_entrypoint()` |
| REG-DELETE | Delete all registry machinery | Delete `_registry.py`, `_drivers.py`, registry exceptions, lazy registration closures, `register_backend` export |
| POOL-INLINE | `create_pool()` calls config methods directly | Rewrite to `config._driver_path()` / `config._dbapi_module()` instead of `resolve_driver()` / `resolve_dbapi_module()` |
| PROTOCOL-UPDATE | WarehouseConfig Protocol updated with new methods | Add `_driver_path()` to Protocol; `_dbapi_module()` optional via default |
| 3P-CONTRACT | Third-party config contract defined | Protocol structural typing, minimum: `to_adbc_kwargs()` + `_driver_path()`, EAFP error handling |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-settings | >=2.0 | Config class base (BaseSettings) | Already in use for all 12 configs |
| abc (stdlib) | 3.11+ | Abstract base class support | Recommended for `_driver_path()` + `to_adbc_kwargs()` enforcement |
| importlib.util (stdlib) | 3.11+ | find_spec for driver detection | Already used in `_drivers.py`, moves to config helper |
| typing (stdlib) | 3.11+ | Protocol, runtime_checkable | Already used for WarehouseConfig Protocol |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| basedpyright | strict | Type checking | All code must pass strict mode |
| ruff | project config | Linting/formatting | All changed files |

## Architecture Patterns

### Recommended Project Structure After Refactoring
```
src/adbc_poolhouse/
  _base_config.py        # Protocol + BaseWarehouseConfig (ABC) + shared helper
  _pool_factory.py       # create_pool() calls config methods directly
  _driver_api.py         # Unchanged - receives driver_path/kwargs/entrypoint
  _exceptions.py         # Remove RegistryError, BackendAlreadyRegisteredError, BackendNotRegisteredError
  __init__.py            # Remove register_backend, registry exceptions
  _duckdb_config.py      # + _driver_path(), _dbapi_module()
  _snowflake_config.py   # + _driver_path(), _dbapi_module()
  ... (10 more configs)  # + _driver_path(), _dbapi_module()
  # DELETED: _registry.py
  # DELETED: _drivers.py
```

### Pattern 1: Shared Driver Resolution Helper (on BaseWarehouseConfig)
**What:** A static or class method on `BaseWarehouseConfig` that handles PyPI driver path resolution for both `_driver_path()` (Apache drivers) and `driver_path()` (DuckDB) conventions.
**When to use:** Called by PyPI and DuckDB config classes in their `_driver_path()` implementation.
**Example:**
```python
# In _base_config.py
from abc import ABC, abstractmethod
import importlib.util
from typing import Any

class BaseWarehouseConfig(BaseSettings, ABC):
    # ... existing fields ...

    @abstractmethod
    def to_adbc_kwargs(self) -> dict[str, str]:
        """Subclasses must override."""
        ...

    @abstractmethod
    def _driver_path(self) -> str:
        """Return the ADBC driver path or short name."""
        ...

    def _adbc_entrypoint(self) -> str | None:
        return None

    def _dbapi_module(self) -> str | None:
        return None

    @staticmethod
    def _resolve_driver_path(
        pkg_name: str,
        *,
        method_name: str = "_driver_path",
    ) -> str:
        """Resolve driver path from a PyPI ADBC driver package.

        Tries find_spec -> import -> call method_name(). Falls back to
        returning pkg_name for adbc_driver_manager manifest resolution.

        Args:
            pkg_name: Python package name (e.g. "adbc_driver_snowflake").
            method_name: Function name on the package module. Apache drivers
                use "_driver_path", DuckDB uses "driver_path".

        Returns:
            Absolute path to driver shared library, or pkg_name as fallback.
        """
        spec = importlib.util.find_spec(pkg_name)
        if spec is not None:
            pkg: Any = __import__(pkg_name)
            return pkg.__dict__[method_name]()
        return pkg_name
```

### Pattern 2: PyPI Config _driver_path() Implementation
**What:** Each PyPI config calls the shared helper with its package name.
**When to use:** Snowflake, BigQuery, PostgreSQL, FlightSQL, SQLite configs.
**Example:**
```python
# In _snowflake_config.py
class SnowflakeConfig(BaseWarehouseConfig):
    def _driver_path(self) -> str:
        return self._resolve_driver_path("adbc_driver_snowflake")

    def _dbapi_module(self) -> str | None:
        import importlib.util
        if importlib.util.find_spec("adbc_driver_snowflake") is not None:
            return "adbc_driver_snowflake.dbapi"
        return None
```

### Pattern 3: DuckDB Config _driver_path() Implementation
**What:** DuckDB uses the same shared helper but with `method_name="driver_path"` since `adbc_driver_duckdb` uses that convention. Also has special error handling for missing `_duckdb` extension.
**When to use:** DuckDB config only.
**Example:**
```python
# In _duckdb_config.py
class DuckDBConfig(BaseWarehouseConfig):
    def _driver_path(self) -> str:
        # adbc_driver_duckdb uses driver_path() (no underscore prefix)
        return self._resolve_driver_path(
            "adbc_driver_duckdb", method_name="driver_path"
        )

    def _dbapi_module(self) -> str | None:
        return None  # DuckDB routes through adbc_driver_manager
```

### Pattern 4: Foundry Config _driver_path() Implementation
**What:** Foundry configs return a static short driver name string.
**When to use:** Databricks, Redshift, Trino, MSSQL, MySQL, ClickHouse configs.
**Example:**
```python
# In _databricks_config.py
class DatabricksConfig(BaseWarehouseConfig):
    def _driver_path(self) -> str:
        return "databricks"

    def _dbapi_module(self) -> str | None:
        return None  # Foundry drivers route through adbc_driver_manager
```

### Pattern 5: Rewritten create_pool()
**What:** `create_pool()` calls config methods directly instead of dispatch functions.
**When to use:** The new `_pool_factory.py` implementation.
**Example:**
```python
# In _pool_factory.py -- no more imports from _drivers or _registry
def create_pool(config: WarehouseConfig, ...) -> QueuePool:
    driver_path = config._driver_path()
    kwargs = config.to_adbc_kwargs()
    entrypoint = config._adbc_entrypoint()
    dbapi_module = config._dbapi_module()

    source = create_adbc_connection(
        driver_path, kwargs,
        entrypoint=entrypoint,
        dbapi_module=dbapi_module,
    )
    # ... pool creation unchanged ...
```

### Anti-Patterns to Avoid
- **Keeping registry as "optional" layer:** The whole point is elimination. No shim, no deprecation period -- this is internal.
- **isinstance checks in create_pool():** EAFP approach. Call the method; if it doesn't exist, AttributeError is the natural Python error.
- **Special-casing DuckDB driver detection:** Use the shared helper with `method_name="driver_path"` parameter -- DuckDB is just another PyPI driver that happens to use a different method name.
- **Circular imports from _base_config.py:** The shared helper uses only stdlib (`importlib.util`). No config imports in `_base_config.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Abstract method enforcement | Manual NotImplementedError checks | `abc.ABC` + `@abstractmethod` | Python's ABC catches missing implementations at instantiation time, not at call time |
| Driver path resolution | Per-config copy-pasted find_spec logic | Shared `_resolve_driver_path()` static method | 6 PyPI/DuckDB configs would duplicate identical logic |
| Method existence checking | isinstance or hasattr guards in create_pool() | EAFP (just call the method) | Python convention; AttributeError is informative |

**Key insight:** The shared helper in `_base_config.py` prevents 6 configs from duplicating the find_spec -> import -> call -> fallback logic. The `method_name` parameter handles the `_driver_path()` vs `driver_path()` naming split.

## Common Pitfalls

### Pitfall 1: DuckDB driver_path() vs _driver_path() Naming
**What goes wrong:** Calling `adbc_driver_duckdb._driver_path()` fails with `AttributeError` because DuckDB uses `driver_path()` (no underscore).
**Why it happens:** Apache ADBC PyPI drivers (Snowflake, BigQuery, PostgreSQL, FlightSQL, SQLite) expose `_driver_path()`. DuckDB's `adbc_driver_duckdb` package exposes `driver_path()` instead. This is a real naming inconsistency in the ADBC ecosystem.
**How to avoid:** The shared helper takes a `method_name` parameter. DuckDB passes `method_name="driver_path"`.
**Warning signs:** Tests that mock `pkg._driver_path()` for DuckDB will silently pass but fail in production.

Verified (HIGH confidence):
- `adbc_driver_snowflake`: has `_driver_path()`, no `driver_path()`
- `adbc_driver_bigquery`: has `_driver_path()`, no `driver_path()`
- `adbc_driver_postgresql`: has `_driver_path()`, no `driver_path()`
- `adbc_driver_flightsql`: has `_driver_path()`, no `driver_path()`
- `adbc_driver_sqlite`: has `_driver_path()`, no `driver_path()`
- `adbc_driver_duckdb`: has `driver_path()`, no `_driver_path()`

### Pitfall 2: DuckDB Error Handling Change
**What goes wrong:** The current `_resolve_duckdb()` checks `find_spec("_duckdb")` and raises `ImportError` with install instructions. The new shared helper uses `find_spec("adbc_driver_duckdb")` + `driver_path()`, which would return `"adbc_driver_duckdb"` as fallback instead of raising.
**Why it happens:** DuckDB's driver is bundled as `_duckdb` C extension inside the `duckdb` wheel, but `adbc_driver_duckdb` provides `driver_path()` that returns the path to it. If `adbc_driver_duckdb` is not installed, the fallback returns `"adbc_driver_duckdb"` -- which is meaningless to `adbc_driver_manager`.
**How to avoid:** Two options: (a) use `"adbc_driver_duckdb"` as the package name in the shared helper -- if `adbc_driver_duckdb` is installed, `driver_path()` returns the correct path; if not, fallback is fine because `adbc_driver_manager` will raise NOT_FOUND which `_driver_api.py` already handles. (b) Add DuckDB-specific error handling in `_duckdb_config._driver_path()`.
**Warning signs:** DuckDB pool creation silently failing at connection time instead of at driver resolution time.

### Pitfall 3: SQLite _dbapi_module() Must Return None
**What goes wrong:** SQLite's `dbapi.connect()` has an incompatible signature (takes `uri` positionally, no `db_kwargs`). If `_dbapi_module()` returns `"adbc_driver_sqlite.dbapi"`, connections fail.
**Why it happens:** SQLite's ADBC driver DBAPI module doesn't follow the standard `connect(db_kwargs=...)` interface.
**How to avoid:** SQLite's `_dbapi_module()` returns `None` explicitly. Add a comment explaining why.
**Warning signs:** SQLite tests failing with `TypeError` about positional arguments.

### Pitfall 4: Test File Imports of Deleted Modules
**What goes wrong:** Tests that import from `adbc_poolhouse._drivers` or `adbc_poolhouse._registry` will fail with `ModuleNotFoundError`.
**Why it happens:** `test_drivers.py` imports `resolve_driver` from `_drivers`. `test_registry.py` imports from `_registry`. `conftest.py` references `_registry` internals for the `clean_registry` fixture.
**How to avoid:** Systematically update all test imports. Replace `resolve_driver()` tests with `config._driver_path()` tests. Replace registry tests with config method tests. Remove `clean_registry` fixture entirely.
**Warning signs:** `ModuleNotFoundError` at test collection time.

### Pitfall 5: Circular Import Risk in _base_config.py
**What goes wrong:** If the shared helper in `_base_config.py` imports anything from the config modules, it creates circular imports since all config modules import from `_base_config.py`.
**Why it happens:** The helper needs `importlib.util` (stdlib only) -- no risk. But if someone accidentally adds a config-module import, everything breaks.
**How to avoid:** The helper is a `@staticmethod` that uses only stdlib. No imports from within the package.
**Warning signs:** `ImportError: cannot import name...` at module load time.

### Pitfall 6: ABC + Pydantic BaseSettings Compatibility
**What goes wrong:** Some developers worry that `ABC` and `BaseSettings` MRO won't work.
**Why it happens:** Multiple inheritance can cause metaclass conflicts.
**How to avoid:** Verified that `class BaseWarehouseConfig(BaseSettings, ABC)` works correctly. Concrete subclasses that implement all abstract methods instantiate fine. Protocol `isinstance` checks also pass.
**Warning signs:** `TypeError: metaclass conflict` at class definition time (does NOT happen -- verified).

### Pitfall 7: clean_registry Fixture in conftest.py
**What goes wrong:** The shared `clean_registry` fixture in `conftest.py` references `_registry._registry` and `_registry._config_to_name` -- both disappear when `_registry.py` is deleted.
**Why it happens:** Multiple test files (`test_drivers.py`, `test_registry.py`) depend on this fixture.
**How to avoid:** Delete the `clean_registry` fixture from `conftest.py`. It is no longer needed when there is no global registry state to clean. Tests for `_driver_path()` methods that mock `find_spec` don't need registry cleanup because the driver resolution now happens in-method, not in module-level state.
**Warning signs:** `ImportError` in conftest.py at test collection time.

## Code Examples

### Complete BaseWarehouseConfig with ABC and Shared Helper
```python
# Source: Verified by local testing (ABC + BaseSettings + Protocol)
from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from pydantic_settings import BaseSettings


@runtime_checkable
class WarehouseConfig(Protocol):
    pool_size: int
    max_overflow: int
    timeout: int
    recycle: int

    def _adbc_entrypoint(self) -> str | None: ...
    def _driver_path(self) -> str: ...
    def _dbapi_module(self) -> str | None: ...
    def to_adbc_kwargs(self) -> dict[str, str]: ...


class BaseWarehouseConfig(BaseSettings, ABC):
    pool_size: int = 5
    max_overflow: int = 3
    timeout: int = 30
    recycle: int = 3600

    @abstractmethod
    def to_adbc_kwargs(self) -> dict[str, str]: ...

    @abstractmethod
    def _driver_path(self) -> str: ...

    def _adbc_entrypoint(self) -> str | None:
        return None

    def _dbapi_module(self) -> str | None:
        return None

    @staticmethod
    def _resolve_driver_path(
        pkg_name: str,
        *,
        method_name: str = "_driver_path",
    ) -> str:
        spec = importlib.util.find_spec(pkg_name)
        if spec is not None:
            pkg: Any = __import__(pkg_name)
            return pkg.__dict__[method_name]()
        return pkg_name
```

### Complete create_pool() After Refactoring
```python
# Source: Current _pool_factory.py, simplified
from adbc_poolhouse._driver_api import create_adbc_connection
# No more imports from _drivers or _registry

def create_pool(config: WarehouseConfig, ...) -> QueuePool:
    driver_path = config._driver_path()
    kwargs = config.to_adbc_kwargs()
    entrypoint = config._adbc_entrypoint()
    dbapi_module = config._dbapi_module()

    source = create_adbc_connection(
        driver_path, kwargs,
        entrypoint=entrypoint,
        dbapi_module=dbapi_module,
    )
    # ... rest unchanged ...
```

### Classification of All 12 Configs

| Config | Driver Type | `_driver_path()` Implementation | `_dbapi_module()` |
|--------|------------|-------------------------------|-------------------|
| DuckDBConfig | PyPI (special) | `_resolve_driver_path("adbc_driver_duckdb", method_name="driver_path")` | `None` |
| SnowflakeConfig | PyPI | `_resolve_driver_path("adbc_driver_snowflake")` | `"adbc_driver_snowflake.dbapi"` if installed, else `None` |
| BigQueryConfig | PyPI | `_resolve_driver_path("adbc_driver_bigquery")` | `"adbc_driver_bigquery.dbapi"` if installed, else `None` |
| PostgreSQLConfig | PyPI | `_resolve_driver_path("adbc_driver_postgresql")` | `"adbc_driver_postgresql.dbapi"` if installed, else `None` |
| FlightSQLConfig | PyPI | `_resolve_driver_path("adbc_driver_flightsql")` | `"adbc_driver_flightsql.dbapi"` if installed, else `None` |
| SQLiteConfig | PyPI (special) | `_resolve_driver_path("adbc_driver_sqlite")` | `None` (incompatible dbapi signature) |
| DatabricksConfig | Foundry | `return "databricks"` | `None` |
| RedshiftConfig | Foundry | `return "redshift"` | `None` |
| TrinoConfig | Foundry | `return "trino"` | `None` |
| MSSQLConfig | Foundry | `return "mssql"` | `None` |
| MySQLConfig | Foundry | `return "mysql"` | `None` |
| ClickHouseConfig | Foundry | `return "clickhouse"` | `None` |

### Files to Delete
| File | Reason |
|------|--------|
| `src/adbc_poolhouse/_registry.py` | All registry functions replaced by config methods |
| `src/adbc_poolhouse/_drivers.py` | resolve_driver/resolve_dbapi_module inlined, helpers moved to _base_config |
| `tests/test_registry.py` | Tests registry that no longer exists |

### Files to Modify
| File | Changes |
|------|---------|
| `src/adbc_poolhouse/_base_config.py` | Add ABC, abstractmethod, `_driver_path()`, `_dbapi_module()`, `_resolve_driver_path()` |
| `src/adbc_poolhouse/_pool_factory.py` | Remove _drivers imports, inline to direct config method calls |
| `src/adbc_poolhouse/__init__.py` | Remove `register_backend`, `RegistryError`, `BackendAlreadyRegisteredError`, `BackendNotRegisteredError` |
| `src/adbc_poolhouse/_exceptions.py` | Remove `RegistryError`, `BackendAlreadyRegisteredError`, `BackendNotRegisteredError` |
| `src/adbc_poolhouse/_duckdb_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_snowflake_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_bigquery_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_postgresql_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_flightsql_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_sqlite_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_databricks_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_redshift_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_trino_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_mssql_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_mysql_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `src/adbc_poolhouse/_clickhouse_config.py` | Add `_driver_path()`, `_dbapi_module()` |
| `tests/conftest.py` | Remove `clean_registry` fixture, `DummyConfig`, `dummy_backend`, `dummy_translator` |
| `tests/test_drivers.py` | Rewrite: test config._driver_path() instead of resolve_driver() |
| `tests/test_driver_imports.py` | Update: mock targets may change slightly (no registry to clear) |
| `tests/test_pool_factory.py` | Remove any registry-related assertions |

## State of the Art

| Old Approach (current) | New Approach (Phase 18) | Impact |
|------------------------|------------------------|--------|
| `_registry.py` with global dicts | Config methods on each class | No global mutable state for driver resolution |
| `_drivers.py` with lazy registration closures | `_base_config.py` shared helper | Single helper, no closures, no module-level side effects |
| `resolve_driver(config)` dispatch | `config._driver_path()` direct call | Zero indirection |
| `resolve_dbapi_module(config)` with `_PYPI_PACKAGES` dict | `config._dbapi_module()` direct call | Each config owns its dbapi knowledge |
| `register_backend()` public API | Config Protocol (structural typing) | Third-party configs just implement the methods |
| `ensure_registered()` + `_lazy_registrations` | No registration needed | Config is self-describing |

## Discretionary Decisions (Claude's Recommendations)

### ABC vs NotImplementedError for BaseWarehouseConfig
**Recommendation: Use ABC with @abstractmethod**

Reasons:
1. Verified that `BaseSettings` + `ABC` coexist without metaclass conflicts (tested locally)
2. ABC catches missing implementations at instantiation time, not at call time -- better DX
3. Follows the same pattern as the existing `to_adbc_kwargs()` which already raises `NotImplementedError` -- ABC makes this formal
4. Third-party configs using Protocol (structural typing) are unaffected -- they don't need to subclass

Implementation: `class BaseWarehouseConfig(BaseSettings, ABC)` with `@abstractmethod` on `to_adbc_kwargs()` and `_driver_path()`.

### Shared Helper Naming and Signature
**Recommendation: `_resolve_driver_path(pkg_name, *, method_name="_driver_path") -> str`**

- `@staticmethod` on `BaseWarehouseConfig`
- `method_name` defaults to `"_driver_path"` (Apache convention)
- DuckDB overrides with `method_name="driver_path"`
- Uses `pkg.__dict__[method_name]()` rather than `getattr()` to avoid false matches from inherited attributes

### _drivers.py Deletion vs Empty Module
**Recommendation: Delete entirely**

Reasons:
1. `_drivers.py` is internal (underscore prefix, not in `__init__.py.__all__`)
2. No external consumer should import from `_drivers` -- it's never been part of the public API
3. `test_drivers.py` imports `resolve_driver` from it, but those tests will be rewritten anyway
4. Leaving an empty module creates false hope that it might be restored

### Test Restructuring
**Recommendation:**

1. **Delete `tests/test_registry.py`** entirely -- all tests are for registry functions that no longer exist
2. **Rewrite `tests/test_drivers.py`** as tests for `config._driver_path()`:
   - Test PyPI configs with mocked `find_spec` (path 1: found, path 2: fallback)
   - Test DuckDB config with mocked `find_spec` (uses `driver_path` method name)
   - Test Foundry configs return static strings (no find_spec call)
   - Test `_dbapi_module()` returns correct values
3. **Update `tests/conftest.py`**: Remove `clean_registry` fixture, `DummyConfig` (or update DummyConfig to implement `_driver_path()`), `dummy_backend` fixture, `dummy_translator`
4. **Update `tests/test_driver_imports.py`**: Should work with minimal changes since it tests `create_pool()` end-to-end, but remove any `clean_registry` usage
5. **Update `tests/test_pool_factory.py`**: Should work with minimal changes since it tests `create_pool()` end-to-end

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest -x -q` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SELF-DESC-01 | DuckDB _driver_path() returns correct path | unit | `uv run pytest tests/test_drivers.py -x -k duckdb` | Rewrite needed |
| SELF-DESC-02 | PyPI configs _driver_path() with find_spec mock | unit | `uv run pytest tests/test_drivers.py -x -k pypi` | Rewrite needed |
| SELF-DESC-03 | Foundry configs _driver_path() returns static string | unit | `uv run pytest tests/test_drivers.py -x -k foundry` | Rewrite needed |
| SELF-DESC-04 | _dbapi_module() returns correct values per config | unit | `uv run pytest tests/test_drivers.py -x -k dbapi_module` | New |
| SELF-DESC-05 | SQLite _dbapi_module() returns None | unit | `uv run pytest tests/test_drivers.py -x -k sqlite_dbapi` | New |
| REG-DELETE-01 | _registry.py deleted, no import errors | smoke | `uv run pytest --co -q` (collection succeeds) | N/A |
| REG-DELETE-02 | _drivers.py deleted, no import errors | smoke | `uv run pytest --co -q` (collection succeeds) | N/A |
| REG-DELETE-03 | Registry exceptions removed from __init__.py | unit | `uv run pytest tests/test_pool_factory.py -x -k exception` | Existing |
| POOL-INLINE-01 | create_pool() calls config._driver_path() directly | unit | `uv run pytest tests/test_pool_factory.py -x` | Existing (update) |
| POOL-INLINE-02 | create_pool() calls config._dbapi_module() directly | unit | `uv run pytest tests/test_driver_imports.py -x` | Existing (update) |
| 3P-CONTRACT-01 | Custom config with _driver_path() + to_adbc_kwargs() works | unit | `uv run pytest tests/test_drivers.py -x -k custom` | Rewrite needed |
| FULL-SUITE | All 224+ tests pass (minus deleted registry tests, plus new) | full | `uv run pytest` | Existing + new |

### Sampling Rate
- **Per task commit:** `uv run pytest -x -q`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green + `uv run basedpyright` + `uv run ruff check`

### Wave 0 Gaps
- [ ] Rewrite `tests/test_drivers.py` -- test config._driver_path() and _dbapi_module() instead of resolve_driver()
- [ ] Delete `tests/test_registry.py` -- all tests are for deleted code
- [ ] Update `tests/conftest.py` -- remove clean_registry fixture and related helpers

## Open Questions

1. **DummyConfig in conftest.py**
   - What we know: DummyConfig currently has `to_adbc_kwargs()` returning `NotImplementedError` (inherited) and `_adbc_entrypoint()` returning `None`. It's used by `dummy_backend` fixture which is only used by `test_registry.py`.
   - What's unclear: Whether any other tests reference `dummy_backend` indirectly.
   - Recommendation: Delete both `DummyConfig` and `dummy_backend` since `test_registry.py` is being deleted. If any test needs a mock config, create a minimal one locally with `_driver_path()` implemented. Verify with grep that no other test uses `dummy_backend`.

2. **DuckDB driver_path() fallback behavior**
   - What we know: `adbc_driver_duckdb.driver_path()` locates `_duckdb.cpython-*.so`. The current `_resolve_duckdb()` in `_drivers.py` uses `find_spec("_duckdb")` directly with a custom ImportError.
   - What's unclear: Whether `adbc_driver_duckdb` is always installed when DuckDB is available (it's a separate package from `duckdb`).
   - Recommendation: Use `_resolve_driver_path("adbc_driver_duckdb", method_name="driver_path")`. If `adbc_driver_duckdb` is not installed, the fallback string `"adbc_driver_duckdb"` will cause `adbc_driver_manager` to raise NOT_FOUND, which `_driver_api.py` already handles gracefully with ImportError. Verify in pyproject.toml that the `[duckdb]` extra includes `adbc-driver-duckdb`.

## Sources

### Primary (HIGH confidence)
- Local codebase inspection: all source files in `src/adbc_poolhouse/` and `tests/`
- Local runtime verification: ABC + BaseSettings compatibility, driver method naming, Protocol isinstance checks
- ADBC driver packages installed locally: verified `_driver_path()` vs `driver_path()` naming for all 6 PyPI drivers

### Secondary (MEDIUM confidence)
- Python abc module documentation (stdlib, stable API)
- Pydantic BaseSettings documentation (well-known library)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies
- Architecture: HIGH -- refactoring existing patterns, no new architecture decisions
- Pitfalls: HIGH -- verified all driver method names locally, tested ABC compatibility
- Test restructuring: HIGH -- all affected test files read and analyzed

**Research date:** 2026-03-15
**Valid until:** No expiry -- this is a project-internal refactoring with no external dependency risk
