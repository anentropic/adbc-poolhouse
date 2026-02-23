# Architecture Research: adbc-poolhouse

**Research Type:** Project Research — Architecture dimension
**Milestone:** Greenfield
**Date:** 2026-02-23
**Question:** How are Python database driver wrapper/pooling libraries typically structured? What are the major components and how should an ADBC-specific library be layered?

---

## Summary

adbc-poolhouse is a thin translation and wiring library. Its job is: receive a typed warehouse config, translate it to ADBC driver kwargs, resolve the right driver binary, and hand the resulting connection factory to SQLAlchemy QueuePool. Each of the four concerns maps cleanly to one module. The public API is a single function — `create_pool(config)` — that calls through those modules in sequence.

The key architectural insight is that SQLAlchemy QueuePool is designed for exactly this pattern: it takes a zero-argument callable (`creator`) that returns a raw DBAPI connection, and it manages the pool lifecycle around it. ADBC's `adbc_driver_manager.dbapi.connect` is a conforming DBAPI2 factory. The library's job is to build the right `creator` closure and pass it to `QueuePool`.

---

## Q1: How SQLAlchemy QueuePool Works With Custom DBAPI Connections

### The `creator` pattern

`sqlalchemy.pool.QueuePool` (and all SQLAlchemy pool implementations) accept a `creator` keyword argument. `creator` is a zero-argument callable that returns a new raw DBAPI connection. QueuePool calls it whenever it needs to open a new physical connection — it does not call `connect()` on a dialect or engine; it just calls `creator()`.

```python
from sqlalchemy.pool import QueuePool

def my_creator():
    import some_dbapi
    return some_dbapi.connect(host="...", user="...", password="...")

pool = QueuePool(
    creator=my_creator,
    pool_size=5,
    max_overflow=3,
    timeout=30,
    recycle=3600,
    pre_ping=True,
)
```

This is the lowest-level SQLAlchemy pool API — it has no knowledge of dialects, engines, or SQL. It is exactly what a non-SQLAlchemy driver wrapper needs. Importing `sqlalchemy.pool` does not pull in the ORM, dialects, or engine machinery.

### Constructor parameters that matter

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `creator` | `Callable[[], Connection]` | required | Called to open each new physical connection |
| `pool_size` | `int` | 5 | Number of connections kept open in the pool at steady state |
| `max_overflow` | `int` | 10 | Additional connections allowed above `pool_size` under load; destroyed when returned |
| `timeout` | `float` | 30.0 | Seconds to wait for a connection before raising `TimeoutError` |
| `recycle` | `float` | -1 | Seconds after which a connection is closed and recreated; use ~3600 for warehouses with session/token expiry |
| `pre_ping` | `bool` | False | Issue a lightweight query (`SELECT 1`) before returning a connection from the pool; discards stale connections |

### The `recycle` parameter and warehouse auth

This parameter is important for Snowflake (and similar warehouse drivers) that issue short-lived session tokens. Setting `recycle=3600` ensures connections are recreated before their auth tokens expire, rather than surfacing auth errors to query callers. It is not a keepalive — it is a maximum connection age.

### `pre_ping` behaviour

When `pre_ping=True`, QueuePool wraps each checkout with a dialect-level ping. Since we are not using a SQLAlchemy dialect, we need to be aware: QueuePool's `pre_ping` with a custom `creator` uses the pool's `_dialect` attribute to issue the ping. With no dialect attached (raw pool, no engine), `pre_ping` may not function as expected without explicit event hooking.

**The recommended approach for pre-ping without a dialect:** Use SQLAlchemy's `event.listen` on the pool's `checkout` event, or set `pre_ping=False` and rely on `recycle` alone for connection health. Alternatively, wrap the connection in a lightweight validation wrapper. For v1, `recycle=3600` combined with Snowflake's session management provides sufficient health guarantees without the complexity of a custom pre-ping handler.

**Note:** This is a known nuance when using QueuePool standalone (without `create_engine`). The `pre_ping` flag is intended for use with engine-bound pools that have a dialect. A standalone `QueuePool` with `pre_ping=True` will attempt to call `dialect.do_ping(dbapi_connection)` — if no dialect is set, this silently no-ops in most SQLAlchemy versions. Setting `pre_ping=False` and using `recycle` is the safer default for this usage pattern.

### Connection checkout and return

Consumers call `pool.connect()` to get a `_ConnectionFairy` (a proxied connection). The context manager protocol is supported: `with pool.connect() as conn:` returns the connection to the pool on exit. The connection object itself is the raw DBAPI connection wrapped in a proxy that intercepts `close()` to return it to the pool instead.

### What QueuePool does NOT do

- It does not parse SQL.
- It does not know about transactions beyond what the DBAPI connection exposes.
- It does not retry failed connections (retries are a consumer responsibility, or can be added via event hooks).
- It does not log or observe queries.

---

## Q2: How ADBC's `adbc_driver_manager.dbapi` Interface Works

### The ADBC abstraction layers

ADBC has two Python-facing layers:

1. **`adbc_driver_manager` (C extension)** — the low-level layer. Wraps the C ADBC API. Provides `AdbcDatabase`, `AdbcConnection`, and `AdbcStatement` classes.
2. **`adbc_driver_manager.dbapi`** — the DBAPI2 shim over the low-level layer. Provides `connect()`, `Connection`, `Cursor` objects conforming to PEP 249.

The `dbapi` module is what we care about. It is the standard DBAPI2 interface.

### `adbc_driver_manager.dbapi.connect()`

```python
import adbc_driver_manager.dbapi as adbc_dbapi

conn = adbc_dbapi.connect(
    driver="adbc_driver_snowflake",       # Python module name (PyPI driver)
    # OR
    driver="/path/to/libadbc_driver.so",  # shared library path (Foundry driver)
    entrypoint="AdbcDriverInit",          # C entry point (optional, has a default)
    db_kwargs={
        "adbc.snowflake.sql.account":  "xy12345",
        "adbc.snowflake.sql.user":     "myuser",
        "adbc.snowflake.sql.password": "secret",
    },
    conn_kwargs={},  # connection-level kwargs (usually empty; most config is at db level)
)
```

Key behaviour:
- `driver` is either a Python module name (for PyPI-installed drivers like `adbc_driver_snowflake`) or a filesystem path to a compiled shared library (for Foundry-installed drivers).
- `db_kwargs` is a `dict[str, str]` — all values must be strings. This is where warehouse-specific parameters go. The parameter names are driver-defined namespaced strings (e.g. `adbc.snowflake.sql.account`).
- `conn_kwargs` is rarely needed; most drivers accept all parameters at the database level.
- Returns a DBAPI2-conforming `Connection` object.

### Driver module vs. shared library path

**PyPI drivers** (e.g. `adbc-driver-snowflake`) install a Python package that exposes a top-level function `_init_fn` (or similar). When you pass `driver="adbc_driver_snowflake"`, `adbc_driver_manager` imports the module and calls the init function to get the C driver handle.

**Foundry drivers** (e.g. `dbc install databricks`) install a shared library (`.so`/`.dylib`/`.dll`) to a known path. When you pass a filesystem path as `driver`, `adbc_driver_manager` `dlopen`s the library directly.

Both paths converge at the C ADBC interface — from Python's perspective, the connect call is identical except for what you pass as `driver`.

### DuckDB special case

DuckDB's ADBC support comes through the `duckdb` package itself — there is no separate `adbc-driver-duckdb` package. The DuckDB package ships its own `adbc_driver_duckdb` module. The connect call uses:

```python
conn = adbc_dbapi.connect(
    driver="adbc_driver_duckdb",
    db_kwargs={
        "path": "/tmp/my.db",  # or ":memory:"
    },
)
```

This means the `duckdb` package must be installed — not a separate `adbc-driver-duckdb`.

### The creator closure for QueuePool

Because `adbc_driver_manager.dbapi.connect()` takes the driver name and db_kwargs at call time, the QueuePool creator closure is straightforward:

```python
def _make_creator(driver: str, db_kwargs: dict[str, str]) -> Callable[[], Connection]:
    def creator() -> Connection:
        return adbc_dbapi.connect(driver=driver, db_kwargs=db_kwargs)
    return creator
```

The `driver` string and `db_kwargs` dict are captured in the closure — they are computed once during pool creation and reused for every new connection opened by the pool.

### DBAPI2 conformance

`adbc_driver_manager.dbapi` provides:
- `connect()` — returns a `Connection`
- `Connection.cursor()` — returns a `Cursor` with `execute()`, `fetchall()`, `fetchmany()`, `fetchone()`
- `Connection.commit()`, `Connection.rollback()`, `Connection.close()`
- Exception hierarchy: `Warning`, `Error`, `InterfaceError`, `DatabaseError`, etc.
- Thread safety level: `threadsafety = 1` — connections are not thread-safe, but the module-level connect function is. This aligns with QueuePool's model of one connection per checkout.

---

## Q3: Module Structure

### Recommended layout

```
src/adbc_poolhouse/
    __init__.py            # Public API: exports create_pool + all config models
    _types.py              # Shared type aliases and protocols (WarehouseConfig protocol)
    config/
        __init__.py        # Re-exports all config models for flat import convenience
        base.py            # BaseWarehouseConfig (shared Pydantic BaseSettings base class)
        duckdb.py          # DuckDBConfig
        snowflake.py       # SnowflakeConfig
    _translators.py        # Internal: translate(config) -> (driver_str, db_kwargs dict)
    _drivers.py            # Internal: resolve_driver(config) -> str (module name or path)
    _pool.py               # Internal: _build_pool(driver, db_kwargs, **pool_kwargs) -> QueuePool
    _exceptions.py         # DriverNotInstalledError and related helpful errors
    factory.py             # Public: create_pool(config, **pool_kwargs) -> QueuePool
    py.typed               # PEP 561 marker
```

**Alternative (simpler, flat):**

```
src/adbc_poolhouse/
    __init__.py            # Public API
    _types.py              # Protocols and type aliases
    _config_base.py        # Shared BaseWarehouseConfig
    config_duckdb.py       # DuckDBConfig
    config_snowflake.py    # SnowflakeConfig
    _translators.py        # Config → ADBC kwargs
    _drivers.py            # Driver resolution
    _exceptions.py         # DriverNotInstalledError
    factory.py             # create_pool()
    py.typed
```

### Recommendation: flat layout

For a library this size (two config models at launch, each small), the flat layout is preferable. The `config/` sub-package is premature until there are 5+ warehouse configs. Flat modules are easier to import, easier to navigate, and have less indirection.

The only sub-package that makes sense is if config models grow complex enough to warrant per-warehouse modules that are clearly grouped. Revisit if/when BigQuery, PostgreSQL, and Databricks are added.

### Module responsibilities and boundaries

**`_config_base.py`** — `BaseWarehouseConfig`
- Contains the abstract Pydantic `BaseSettings` base class
- Defines only fields common to all warehouses (none currently — may add `pool_size` override fields here later)
- No imports from other library modules

**`config_duckdb.py`** — `DuckDBConfig`
- Imports from `_config_base`
- Fields: `database` (path string, default `":memory:"`), `read_only` (bool, default False)
- No auth fields needed for DuckDB in-process usage
- No imports from driver or pool modules

**`config_snowflake.py`** — `SnowflakeConfig`
- Imports from `_config_base`
- Fields: `account`, `user`, `password` or `private_key`/`private_key_passphrase`, `warehouse`, `database`, `schema_`, `role`
- Auth method fields should be `SecretStr` (Pydantic) so passwords are not logged
- Pydantic `model_validator` to enforce that at least one auth method is present
- No imports from driver or pool modules

**`_exceptions.py`** — error types
- `DriverNotInstalledError(ImportError)` with helpful message template
- `DriverResolutionError(RuntimeError)` for unexpected detection failures
- No imports from other library modules

**`_translators.py`** — config to ADBC kwargs
- `translate(config: BaseWarehouseConfig) -> dict[str, str]`
- One private function per warehouse type: `_translate_duckdb`, `_translate_snowflake`
- Uses `isinstance` dispatch or a registry pattern
- Returns a `dict[str, str]` of ADBC driver kwargs (`db_kwargs`)
- Imports config models, `_exceptions`; no imports from `_drivers` or pool modules

**`_drivers.py`** — driver resolution
- `resolve_driver(config: BaseWarehouseConfig) -> str`
- Returns the driver identifier string to pass to `adbc_driver_manager.dbapi.connect(driver=...)`
- Strategy: `try: importlib.import_module(pypi_module_name)` — if it succeeds, return the module name. If `ImportError`, try `adbc_driver_manager` lookup for the Foundry path. If neither works, raise `DriverNotInstalledError` with install instructions.
- Does NOT import any ADBC driver packages at module load time — only inside the resolution function
- Imports `_exceptions`; no imports from translators or pool modules

**`factory.py`** — `create_pool()`
- The only module that imports `sqlalchemy.pool`
- Calls `_translators.translate(config)` to get `db_kwargs`
- Calls `_drivers.resolve_driver(config)` to get the driver string
- Builds the creator closure
- Constructs `QueuePool(creator=creator, pool_size=..., max_overflow=..., timeout=..., recycle=..., pre_ping=False)` (see Q1 notes on pre_ping)
- Accepts `**pool_kwargs` to allow consumer overrides of all pool parameters
- Returns `QueuePool`

**`__init__.py`** — public API surface
- `from adbc_poolhouse.factory import create_pool`
- `from adbc_poolhouse.config_duckdb import DuckDBConfig`
- `from adbc_poolhouse.config_snowflake import SnowflakeConfig`
- `__all__ = ["create_pool", "DuckDBConfig", "SnowflakeConfig"]`
- Does NOT import `_translators`, `_drivers`, `_exceptions`, `_config_base` — those are internal

---

## Q4: Public API Design for Multiple Backends Without Requiring All Drivers

### The core problem

If `create_pool(config)` had warehouse-specific code at the top level, importing the library would fail if optional driver packages were not installed. The solution is deferred import — driver packages are imported only when a connection is actually requested, not at library import time.

### Pattern: lazy imports inside the creator closure

```python
# In _drivers.py
def resolve_driver(config: BaseWarehouseConfig) -> str:
    if isinstance(config, DuckDBConfig):
        return _resolve_duckdb_driver()
    elif isinstance(config, SnowflakeConfig):
        return _resolve_snowflake_driver()
    raise DriverResolutionError(f"No driver known for {type(config).__name__}")

def _resolve_duckdb_driver() -> str:
    try:
        import adbc_driver_duckdb  # noqa: F401
        return "adbc_driver_duckdb"
    except ImportError:
        raise DriverNotInstalledError(
            "DuckDB ADBC driver not found. Install it with: pip install duckdb"
        ) from None

def _resolve_snowflake_driver() -> str:
    try:
        import adbc_driver_snowflake  # noqa: F401
        return "adbc_driver_snowflake"
    except ImportError:
        pass
    # Foundry fallback
    foundry_path = _find_foundry_driver("snowflake")
    if foundry_path:
        return foundry_path
    raise DriverNotInstalledError(
        "Snowflake ADBC driver not found. "
        "Install it with: pip install adbc-driver-snowflake\n"
        "Or via ADBC Driver Foundry: dbc install snowflake"
    )
```

### Key design principles

1. **No top-level driver imports.** Neither `adbc_driver_snowflake` nor `adbc_driver_duckdb` appears at module scope anywhere in the library. All driver imports are guarded by `try/except ImportError` inside functions.

2. **Optional extras in `pyproject.toml`.** Declare driver packages as optional extras so consumers can install exactly what they need:

   ```toml
   [project.optional-dependencies]
   duckdb = ["duckdb>=0.10"]
   snowflake = ["adbc-driver-snowflake>=1.0"]
   all = ["duckdb>=0.10", "adbc-driver-snowflake>=1.0"]
   ```

   Consumers then do `pip install adbc-poolhouse[snowflake]`. The library itself has `adbc-driver-manager` as a required dependency (it is the common substrate for all drivers).

3. **`adbc_driver_manager` is always required.** This is the one ADBC package that must be installed regardless of warehouse. It is the C extension that manages driver loading. List it as a required dependency in `[project.dependencies]`.

4. **`sqlalchemy` is always required.** It provides `QueuePool`. List it as a required dependency. The import cost is low — importing `sqlalchemy.pool` does not load the ORM.

5. **Config model registration, not driver imports.** The factory dispatches on config type (`isinstance` check or a `__adbc_driver_module__` class variable on each config). Adding a new warehouse means adding a new config class and a new entry in the resolver — the factory itself does not change.

### `create_pool` signature

```python
from sqlalchemy.pool import QueuePool

def create_pool(
    config: BaseWarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: float = 30.0,
    recycle: float = 3600.0,
    pre_ping: bool = False,
) -> QueuePool:
    """Create a SQLAlchemy QueuePool wrapping ADBC connections for the given warehouse.

    Args:
        config: Typed warehouse configuration (DuckDBConfig, SnowflakeConfig, etc.)
        pool_size: Number of connections to keep open at steady state.
        max_overflow: Additional connections allowed above pool_size under burst load.
        timeout: Seconds to wait for a connection when the pool is exhausted.
        recycle: Seconds after which connections are recreated (prevents auth token expiry).
        pre_ping: Whether to issue a health-check before returning pooled connections.
            Note: when using QueuePool standalone (without SQLAlchemy engine), pre_ping
            requires a dialect. Leave False and rely on recycle for connection health.

    Returns:
        A configured QueuePool ready for use.

    Raises:
        DriverNotInstalledError: If the required ADBC driver package is not installed.
        pydantic.ValidationError: If config fields fail validation.
    """
```

The keyword-only arguments (`*,`) enforce that pool settings are always passed by name, not position. This is important for readability and for future-proofing if parameter order ever changes.

---

## Component Boundaries

```
Consumer
    |
    | SnowflakeConfig(account=..., ...)
    v
[config_snowflake.py]  <-- Pydantic validation happens here
    |
    | config object (typed, validated)
    v
[factory.py: create_pool(config)]
    |
    +---> [_translators.py: translate(config)]
    |          |
    |          v
    |     dict[str, str]  (ADBC db_kwargs)
    |
    +---> [_drivers.py: resolve_driver(config)]
    |          |
    |          +--> try: import adbc_driver_snowflake  (PyPI path)
    |          |         |
    |          |         v (if ImportError)
    |          +--> try: adbc_driver_manager Foundry path
    |          |         |
    |          |         v (if not found)
    |          +--> raise DriverNotInstalledError
    |          |
    |          v
    |     str  ("adbc_driver_snowflake" or "/path/to/lib.so")
    |
    v
[_pool.py / factory.py]
    |
    | QueuePool(
    |     creator=lambda: adbc_driver_manager.dbapi.connect(
    |         driver=driver_str,
    |         db_kwargs=db_kwargs,
    |     ),
    |     pool_size=5, max_overflow=3, ...
    | )
    |
    v
QueuePool  (returned to consumer)
```

### Dependency graph (who imports what)

```
__init__.py
    imports: factory.py, config_duckdb.py, config_snowflake.py

factory.py
    imports: _translators.py, _drivers.py, _config_base.py
    imports: sqlalchemy.pool (QueuePool)
    imports: adbc_driver_manager.dbapi (inside creator closure)

_translators.py
    imports: config_duckdb.py, config_snowflake.py, _config_base.py, _exceptions.py

_drivers.py
    imports: _config_base.py, _exceptions.py
    imports: adbc_driver_manager (for Foundry path lookup)
    lazy imports: adbc_driver_duckdb, adbc_driver_snowflake (guarded try/except)

config_duckdb.py
    imports: _config_base.py

config_snowflake.py
    imports: _config_base.py

_config_base.py
    imports: pydantic_settings (BaseSettings)

_exceptions.py
    imports: nothing from this library
```

**Rule:** No circular imports. The dependency direction is strictly: `__init__` → `factory` → `translators`/`drivers` → `config` → `config_base`. Exceptions is a leaf node that nothing depends on (except translators and drivers).

---

## Data Flow

### Pool creation (the happy path)

```
1. Consumer constructs: config = SnowflakeConfig(account="xy12345", user="me", password="...")
   - Pydantic BaseSettings validates fields
   - Environment variable overrides applied (SNOWFLAKE_ACCOUNT etc.)
   - ValidationError raised here if required fields missing

2. Consumer calls: pool = create_pool(config, pool_size=10)
   - factory.py receives config

3. factory.py calls: db_kwargs = translate(config)
   - _translators.py maps config.account → "adbc.snowflake.sql.account"
   - Returns dict[str, str] of ADBC driver parameters

4. factory.py calls: driver_str = resolve_driver(config)
   - _drivers.py attempts: import adbc_driver_snowflake
   - Succeeds: returns "adbc_driver_snowflake"
   - (Failure path: raises DriverNotInstalledError with install instructions)

5. factory.py builds creator closure:
   driver_str and db_kwargs are captured in the closure
   creator = lambda: adbc_dbapi.connect(driver=driver_str, db_kwargs=db_kwargs)

6. factory.py constructs:
   pool = QueuePool(creator=creator, pool_size=10, max_overflow=3, timeout=30, recycle=3600)

7. pool is returned to consumer — no connections opened yet

8. Consumer calls: with pool.connect() as conn:
   - QueuePool opens a physical connection by calling creator()
   - creator() calls adbc_dbapi.connect(...) → opens ADBC connection
   - Returns connection wrapped in _ConnectionFairy proxy

9. Consumer uses conn to execute queries
   - Consumer calls conn.cursor() → ADBC Cursor
   - Consumer calls cursor.execute(sql, params)

10. Context manager exits: conn is returned to pool (not closed)
    - Pool keeps the connection open for reuse
    - If pool.size == pool_size + max_overflow, excess connection is closed

11. On recycle timeout: next checkout after recycle seconds creates a new ADBC connection
```

### Error flow (driver not installed)

```
1. Consumer: pool = create_pool(SnowflakeConfig(...))
2. factory.py → _drivers.py: resolve_driver(config)
3. _drivers.py: import adbc_driver_snowflake → ImportError
4. _drivers.py: check Foundry path → not found
5. _drivers.py: raise DriverNotInstalledError(
     "Snowflake ADBC driver not found.\n"
     "Install with: pip install adbc-driver-snowflake\n"
     "Or via ADBC Driver Foundry: dbc install snowflake"
   )
6. Exception propagates to consumer with actionable message
```

### Error flow (invalid config)

```
1. Consumer: SnowflakeConfig(account="xy12345")  # missing user and all auth
2. Pydantic model_validator fires → ValidationError raised immediately
3. create_pool() is never called
4. Consumer sees structured Pydantic error with field names and reasons
```

---

## Suggested Build Order

The dependency graph above implies a natural build order. Each phase can be tested and verified before the next phase begins.

### Phase 1: Config models (no external dependencies except pydantic-settings)

Build:
- `_config_base.py` — `BaseWarehouseConfig(BaseSettings)`
- `config_duckdb.py` — `DuckDBConfig`
- `config_snowflake.py` — `SnowflakeConfig`
- `_exceptions.py` — `DriverNotInstalledError`

Test:
- Unit tests for each config model: valid construction, env var overrides, validation errors
- No ADBC or SQLAlchemy needed at this phase

Why first: Config models are pure data structures. They are the input to every other component. All downstream code depends on them. Testing them in isolation is fast and requires only pydantic-settings.

### Phase 2: Parameter translation (depends on Phase 1)

Build:
- `_translators.py` — `translate(config)` dispatch + per-warehouse translators

Test:
- Unit tests: `translate(DuckDBConfig(database=":memory:"))` returns expected `db_kwargs` dict
- `translate(SnowflakeConfig(account="xy12345", ...))` maps all fields correctly
- No ADBC, no SQLAlchemy

Why second: Translation is pure Python — dict construction. It can be tested without any external services or drivers. Its correctness is easy to verify by inspection against ADBC driver documentation.

### Phase 3: Driver detection (depends on Phase 1, Phase 2 not needed)

Build:
- `_drivers.py` — `resolve_driver(config)` with PyPI and Foundry detection

Test:
- Unit tests with mocked `importlib.import_module`: test PyPI found path, PyPI not found + Foundry found path, neither found → `DriverNotInstalledError`
- Integration test (CI only, with DuckDB installed): `resolve_driver(DuckDBConfig())` returns `"adbc_driver_duckdb"`

Why third: Driver resolution logic is independent of translation. It can be developed and tested in parallel with Phase 2. The mocking strategy for import detection is straightforward with `unittest.mock.patch("builtins.__import__")` or by temporarily manipulating `sys.modules`.

### Phase 4: Pool factory (depends on Phases 1, 2, 3)

Build:
- `factory.py` — `create_pool(config, **pool_kwargs) -> QueuePool`
- Add `sqlalchemy` and `adbc-driver-manager` to `[project.dependencies]` in `pyproject.toml`
- Add optional extras for driver packages

Test (DuckDB, no credentials):
- Integration test: `create_pool(DuckDBConfig())` returns a `QueuePool`
- Integration test: `with pool.connect() as conn: conn.cursor().execute("SELECT 1")`
- Test pool configuration is applied (verify `pool.size()`, `pool.overflow()`)
- Test error propagation: missing driver raises `DriverNotInstalledError`

Test (Snowflake, with credentials):
- Syrupy snapshot tests: record locally, replay in CI
- Test connection opens, basic query works, pool recycles correctly

Why last: The factory wires everything together. It is the last piece, not the first. Building and testing it before the components it depends on (especially config and translation) are solid leads to integration tests that catch configuration mistakes, not structural issues.

### Phase 5: Public API and `__init__.py` cleanup

Build:
- Update `__init__.py` `__all__` with all public symbols
- Update `pyproject.toml` with proper dependency declarations
- Add Google-style docstrings to all public APIs

This is not a separate implementation phase — it happens incrementally during Phases 1–4 — but a final audit ensures everything is exported correctly and the public API is complete.

---

## Module Layout Recommendation (Final)

```
src/adbc_poolhouse/
    __init__.py            # Public exports: create_pool, DuckDBConfig, SnowflakeConfig
    py.typed               # PEP 561 marker
    _exceptions.py         # DriverNotInstalledError (leaf — no internal imports)
    _config_base.py        # BaseWarehouseConfig(BaseSettings) (leaf — only pydantic-settings)
    config_duckdb.py       # DuckDBConfig (imports _config_base)
    config_snowflake.py    # SnowflakeConfig (imports _config_base)
    _translators.py        # translate(config) → dict[str,str] (imports configs, _exceptions)
    _drivers.py            # resolve_driver(config) → str (imports _config_base, _exceptions)
    factory.py             # create_pool(...) → QueuePool (imports all internal modules)
```

**Naming rationale:**
- `config_*.py` files are public (no underscore prefix) because the config classes they define (`DuckDBConfig`, `SnowflakeConfig`) are part of the public API.
- `_translators.py`, `_drivers.py`, `_config_base.py` have underscore prefixes because they are implementation details — consumers never import them directly.
- `factory.py` has no underscore prefix because `create_pool` could logically be imported from there directly, though `__init__.py` will re-export it.
- `_exceptions.py` — `DriverNotInstalledError` may be part of the public API (consumers catching it), so this is debatable. Start private, promote to public if consumers need to catch it by name.

---

## Validation Against Design Documents

The architecture above is consistent with `_notes/design-discussion.md` and `.planning/codebase/ARCHITECTURE.md`. Key validated decisions:

| Design decision | Confirmed |
|----------------|-----------|
| Pydantic BaseSettings for config | Yes — leaf modules, no circular deps |
| SQLAlchemy QueuePool only (not ORM) | Yes — only `sqlalchemy.pool` imported |
| One pool per call | Yes — `create_pool()` is stateless, returns a new pool each time |
| No global state | Yes — all state in the returned `QueuePool` object, owned by consumer |
| PyPI + Foundry driver support | Yes — handled in `_drivers.py` lazy import + path lookup |
| Helpful errors on missing driver | Yes — `DriverNotInstalledError` with install instructions |
| DuckDB first (no credentials needed) | Yes — Phase 4 integration tests use DuckDB |

### Issues found in existing design docs

1. **`pre_ping=True` default needs reconsideration.** The design notes list `pool_pre_ping=True` as a default. As documented in Q1 above, `pre_ping` with a standalone `QueuePool` (no dialect) does not function as expected. The safer default is `pre_ping=False` with `recycle=3600`. This should be updated in the design notes.

2. **DuckDB driver package name.** The design notes list `adbc-driver-duckdb` as the DuckDB driver package name, but the correct package is `duckdb` — DuckDB ships its ADBC support in the main `duckdb` package as `adbc_driver_duckdb`. The Foundry/install instructions should reflect this.

3. **`adbc_driver_manager` as required vs. optional.** The design describes both PyPI and Foundry paths. `adbc_driver_manager` should be a required dependency (it is always needed as the underlying C extension, including for PyPI drivers). It is not optional — even `adbc_driver_snowflake` uses it under the hood.

---

## Open Questions for Implementation

1. **`DriverNotInstalledError` visibility.** Should it be public (in `__all__`) so consumers can catch it specifically, or remain `_exceptions.DriverNotInstalledError` and be documented but not re-exported? Recommendation: export it — consumers will want to catch it.

2. **`BaseWarehouseConfig` visibility.** Should `BaseWarehouseConfig` be exported? The Semantic ORM consumer could want to use it as a type annotation. Recommendation: export it as part of the public API for typing purposes.

3. **`translate()` return type.** The translator returns `dict[str, str]`. Some ADBC parameters may technically accept non-string values (e.g. booleans, integers). Verify against driver documentation whether string coercion is always safe, or if the type should be `dict[str, str | int | bool]`.

4. **Snowflake private key handling.** Private key auth for Snowflake involves reading a PEM file and potentially decrypting with a passphrase. This is a non-trivial field in `SnowflakeConfig` — the config model should accept a `Path` (file path) or `str` (PEM content), and the translator handles serialization to what the driver expects. This is a known complexity item.

5. **Pool `connection_class` parameter.** SQLAlchemy QueuePool accepts a `_ConnectionRecord` subclass for custom checkout/checkin behaviour. Not needed for v1 but useful for future observability hooks.

---

*Research complete: 2026-02-23*
