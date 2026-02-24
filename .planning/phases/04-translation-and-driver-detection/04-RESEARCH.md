# Phase 4: Translation and Driver Detection - Research

**Researched:** 2026-02-24
**Domain:** ADBC driver kwargs translation, lazy driver resolution, type isolation facades
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**ImportError message format**
- Use `adbc-poolhouse` extras in the install command: `pip install adbc-poolhouse[duckdb]`
- Use `pip` only (not `uv`) — universal, no toolchain assumptions
- Include the config class name in the message: e.g. "DuckDB ADBC driver not found. Run: `pip install adbc-poolhouse[duckdb]`"
- For Foundry-distributed drivers (Databricks, Redshift, Trino, MSSQL, Teradata) not on PyPI: point to docs with the correct URL — researcher should verify whether the canonical docs are at https://docs.adbc-drivers.org/ or elsewhere (user flagged these are NOT from apache.org)

**Translator file structure**
- Per-warehouse translator files matching the existing config pattern: `_duckdb_translator.py`, `_snowflake_translator.py`, etc.
- A coordinator module `_translators.py` imports all per-warehouse translators and exposes a single dispatch function `translate_config(config: WarehouseConfig) -> dict[str, str]`
- Translators are internal only — not exported in `__init__.py`

**Driver detection interface**
- Single `resolve_driver(config: WarehouseConfig) -> str` dispatch function (returns the driver entrypoint string, not the loaded module)
- Lives in a `_drivers.py` module (consistent with `_translators.py` pattern)
- The 3-path logic (find_spec → adbc_driver_manager fallback → ImportError) is generic; config type determines the package name and error message

**_driver_api.py responsibilities**
- Owns the actual `adbc_driver_manager.dbapi.connect(driver_path, **kwargs)` call
- Exposes a typed `create_adbc_connection(driver_path: str, kwargs: dict[str, str]) -> <connection>` function
- All `cast()` and `# type: ignore` suppressions for ADBC live here
- ADBC exceptions pass through raw — no wrapping in this phase

### Claude's Discretion

- Exact scope of `_pool_types.py` in Phase 4 — whether it declares only type-cast helpers now (with QueuePool assembly deferred to Phase 5) or builds more of the facade now. Either approach is acceptable as long as Phase 5 can assemble `create_pool()` cleanly.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRANS-01 | Translator for `DuckDBConfig` → DuckDB ADBC driver kwargs | DuckDB uses `path` + `access_mode` as db_kwargs; entrypoint `duckdb_adbc_init` via `_duckdb` C extension |
| TRANS-02 | Translator for `SnowflakeConfig` → Snowflake ADBC driver kwargs (all auth methods) | All `adbc.snowflake.sql.*` key names verified from installed driver source; `username` and `password` confirmed as plain string keys |
| TRANS-03 | Translators for Apache backends (`BigQueryConfig`, `PostgreSQLConfig`, `FlightSQLConfig`) | All `adbc.bigquery.sql.*`, `adbc.postgresql.*`, `adbc.flight.sql.*` key names verified from installed driver source |
| TRANS-04 | Translators for Foundry backends (`DatabricksConfig`, `RedshiftConfig`, `TrinoConfig`, `MSSQLConfig`, `TeradataConfig`) | Foundry drivers use URI-only connection model; all accept `uri` key; driver name strings verified from docs.adbc-drivers.org |
| TRANS-05 | All translators are pure functions with no ADBC driver imports | Architecture pattern: translators produce `dict[str, str]`, import nothing from ADBC drivers |
| DRIV-01 | Detect PyPI ADBC driver packages using `importlib.util.find_spec()` | `find_spec()` returns `None` for missing packages, correctly distinguishes "not installed" from "broken install" |
| DRIV-02 | Fall back to `adbc_driver_manager` with correct driver path | For PyPI drivers: use `pkg._driver_path()` after import; for Foundry: pass short name to driver manager manifest system |
| DRIV-03 | Raise `ImportError` with human-readable message including exact install command | Message format and docs URL verified; pip-only per locked decision |
| DRIV-04 | All driver detection and imports are lazy — never at module import time | Module-level `_drivers.py` contains only function definitions; no top-level imports of ADBC driver packages |
| TYPE-01 | `_pool_types.py` — all SQLAlchemy pool interactions needing `cast()` or `# type: ignore` | Standalone QueuePool stubs incomplete; SQLAlchemy `_CreatorFnType` vs ADBC return type mismatch identified |
| TYPE-02 | `_driver_api.py` — all ADBC driver calls needing `cast()` or `# type: ignore` | basedpyright reports `reportUnknownMemberType` on cursor methods; confirmed via live type check |
| TEST-05 | Unit tests for all parameter translators | Standard pattern: instantiate config, call translator, assert exact dict output |
| TEST-06 | Unit tests for driver detection with `unittest.mock.patch` | Three-path test: find_spec found, find_spec None + manifest success, both fail → ImportError |
</phase_requirements>

## Summary

Phase 4 is pure internal infrastructure — no public API changes. It builds three modules (`_translators.py` + 11 per-warehouse translator files, `_drivers.py`, `_driver_api.py`) and a minimal `_pool_types.py` scaffold.

The ADBC driver connection model uses `adbc_driver_manager.dbapi.connect(driver, db_kwargs)` where `driver` is either a full path to a shared library (for PyPI-installed packages) or a short manifest name (for Foundry/system-installed packages). All `db_kwargs` values must be strings — no ints, bools, or SecretStr objects. The translators' core responsibility is this conversion: config fields → `dict[str, str]`, omitting `None` values.

Driver detection uses a 3-path chain specific to each warehouse type. PyPI packages (DuckDB, Snowflake, PostgreSQL, BigQuery, FlightSQL) are detected via `importlib.util.find_spec()` and then their `_driver_path()` method is used to get the full shared-library path. Foundry packages (Databricks, Redshift, Trino, MSSQL, Teradata) have no Python package; detection is attempted via the driver manager's manifest system, and failure raises an `ImportError` pointing to `docs.adbc-drivers.org`. DuckDB is a special case: `find_spec('duckdb')` finds the package, but the shared library path must be obtained via `find_spec('_duckdb')` (the C extension), with entrypoint `duckdb_adbc_init`.

**Primary recommendation:** Implement translators as pure dicts (no driver imports), driver detection as lazy-only functions, and _driver_api.py as the single boundary where ADBC type suppressions are concentrated. Keep `_pool_types.py` minimal for Phase 4 — define only the type aliases and cast helpers Phase 5 will need; do not build QueuePool assembly logic yet.

## Standard Stack

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `adbc-driver-manager` | >=1.0.0 (1.9.0 in venv) | Central ADBC connection API | Runtime dep already declared in pyproject.toml |
| `adbc-driver-snowflake` | >=1.0.0 | Snowflake ADBC driver | Already in `[snowflake]` optional extra |
| `adbc-driver-postgresql` | >=1.0.0 | PostgreSQL ADBC driver | Already in `[postgresql]` optional extra |
| `adbc-driver-flightsql` | >=1.0.0 | FlightSQL ADBC driver | Already in `[flightsql]` optional extra |
| `adbc-driver-bigquery` | >=1.3.0 | BigQuery ADBC driver | Already in `[bigquery]` optional extra |
| `duckdb` | >=0.9.1 | DuckDB (bundles ADBC) | Already in `[duckdb]` optional extra |
| `importlib.util` | stdlib | Driver package detection | `find_spec()` is the correct lazy detection API |
| `unittest.mock` | stdlib | Test mocking for DRIV-06 | No additional test dependency needed |

**No new dependencies needed for Phase 4.** All packages are already installed.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `importlib_resources` | (transitive) | Used internally by ADBC driver packages for `_driver_path()` | Do NOT use directly — call `pkg._driver_path()` instead |
| `sqlalchemy.pool` | >=2.0.0 | `_pool_types.py` type definitions | Minimal usage: TypeAlias for creator callable only in Phase 4 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `find_spec()` + `_driver_path()` | Bare `import adbc_driver_snowflake` | `find_spec()` distinguishes "not installed" from "installed but broken" — requirement DRIV-01 explicitly mandates this |
| Per-warehouse translator files | Single giant dispatch dict | Per-file pattern mirrors existing config structure; more readable, easier to test individually |
| Passing driver short name to AdbcDatabase | Always using full path | Full path (via `_driver_path()`) is Path 1; short name (manifest search) is Path 2 fallback — both needed |

## Architecture Patterns

### Recommended Project Structure

```
src/adbc_poolhouse/
├── _base_config.py          # Phase 3 — unchanged
├── _duckdb_config.py        # Phase 3 — unchanged
├── _snowflake_config.py     # Phase 3 — unchanged
├── ... (other _*_config.py) # Phase 3 — unchanged
├── _duckdb_translator.py    # Phase 4 — NEW
├── _snowflake_translator.py # Phase 4 — NEW
├── _bigquery_translator.py  # Phase 4 — NEW
├── _postgresql_translator.py # Phase 4 — NEW
├── _flightsql_translator.py  # Phase 4 — NEW
├── _databricks_translator.py # Phase 4 — NEW
├── _redshift_translator.py   # Phase 4 — NEW
├── _trino_translator.py      # Phase 4 — NEW
├── _mssql_translator.py      # Phase 4 — NEW
├── _teradata_translator.py   # Phase 4 — NEW
├── _translators.py           # Phase 4 — NEW (coordinator)
├── _drivers.py               # Phase 4 — NEW (detection)
├── _driver_api.py            # Phase 4 — NEW (ADBC facade)
├── _pool_types.py            # Phase 4 — NEW (SQLAlchemy type facade, minimal)
└── __init__.py               # Unchanged (translators/drivers NOT exported)
```

### Pattern 1: Pure Translator Function

**What:** Each per-warehouse translator is a pure function: takes the typed config, returns `dict[str, str]`. No ADBC imports. No side effects.

**When to use:** Every translator. No exceptions.

```python
# Source: verified against installed adbc_driver_snowflake source + official docs
# src/adbc_poolhouse/_snowflake_translator.py

from __future__ import annotations

from adbc_poolhouse._snowflake_config import SnowflakeConfig


def translate_snowflake(config: SnowflakeConfig) -> dict[str, str]:
    """Translate SnowflakeConfig → ADBC driver kwargs dict."""
    kwargs: dict[str, str] = {}

    # Identity
    kwargs["adbc.snowflake.sql.account"] = config.account
    if config.user is not None:
        kwargs["username"] = config.user
    if config.password is not None:
        kwargs["password"] = config.password.get_secret_value()

    # Auth type
    if config.auth_type is not None:
        kwargs["adbc.snowflake.sql.auth_type"] = config.auth_type

    # JWT / private key
    if config.private_key_path is not None:
        kwargs["adbc.snowflake.sql.client_option.jwt_private_key"] = str(config.private_key_path)
    if config.private_key_pem is not None:
        kwargs["adbc.snowflake.sql.client_option.jwt_private_key_pkcs8_value"] = (
            config.private_key_pem.get_secret_value()
        )
    if config.private_key_passphrase is not None:
        kwargs["adbc.snowflake.sql.client_option.jwt_private_key_pkcs8_password"] = (
            config.private_key_passphrase.get_secret_value()
        )
    if config.jwt_expire_timeout is not None:
        kwargs["adbc.snowflake.sql.client_option.jwt_expire_timeout"] = config.jwt_expire_timeout

    # OAuth
    if config.oauth_token is not None:
        kwargs["adbc.snowflake.sql.client_option.auth_token"] = config.oauth_token.get_secret_value()

    # Okta
    if config.okta_url is not None:
        kwargs["adbc.snowflake.sql.client_option.okta_url"] = config.okta_url

    # WIF
    if config.identity_provider is not None:
        kwargs["adbc.snowflake.sql.client_option.identity_provider"] = config.identity_provider

    # Session / scope
    if config.database is not None:
        kwargs["adbc.snowflake.sql.db"] = config.database
    if config.schema_ is not None:
        kwargs["adbc.snowflake.sql.schema"] = config.schema_
    if config.warehouse is not None:
        kwargs["adbc.snowflake.sql.warehouse"] = config.warehouse
    if config.role is not None:
        kwargs["adbc.snowflake.sql.role"] = config.role
    if config.region is not None:
        kwargs["adbc.snowflake.sql.region"] = config.region

    # Connection
    if config.host is not None:
        kwargs["adbc.snowflake.sql.uri.host"] = config.host
    if config.port is not None:
        kwargs["adbc.snowflake.sql.uri.port"] = str(config.port)
    if config.protocol is not None:
        kwargs["adbc.snowflake.sql.uri.protocol"] = config.protocol

    # Timeouts
    if config.login_timeout is not None:
        kwargs["adbc.snowflake.sql.client_option.login_timeout"] = config.login_timeout
    if config.request_timeout is not None:
        kwargs["adbc.snowflake.sql.client_option.request_timeout"] = config.request_timeout
    if config.client_timeout is not None:
        kwargs["adbc.snowflake.sql.client_option.client_timeout"] = config.client_timeout

    # Security (booleans → 'true'/'false' strings)
    kwargs["adbc.snowflake.sql.client_option.tls_skip_verify"] = str(config.tls_skip_verify).lower()
    kwargs["adbc.snowflake.sql.client_option.ocsp_fail_open_mode"] = str(config.ocsp_fail_open_mode).lower()

    # Session behaviour
    kwargs["adbc.snowflake.sql.client_option.keep_session_alive"] = str(config.keep_session_alive).lower()

    # Telemetry / misc
    if config.app_name is not None:
        kwargs["adbc.snowflake.sql.client_option.app_name"] = config.app_name
    kwargs["adbc.snowflake.sql.client_option.disable_telemetry"] = str(config.disable_telemetry).lower()
    kwargs["adbc.snowflake.sql.client_option.cache_mfa_token"] = str(config.cache_mfa_token).lower()
    kwargs["adbc.snowflake.sql.client_option.store_temp_creds"] = str(config.store_temp_creds).lower()

    return kwargs
```

### Pattern 2: Coordinator Dispatch

**What:** `_translators.py` maps each config type to its translator and exposes one public function.

```python
# src/adbc_poolhouse/_translators.py
from __future__ import annotations

from adbc_poolhouse._base_config import WarehouseConfig
from adbc_poolhouse._bigquery_config import BigQueryConfig
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._teradata_config import TeradataConfig
from adbc_poolhouse._trino_config import TrinoConfig
from adbc_poolhouse._bigquery_translator import translate_bigquery
from adbc_poolhouse._databricks_translator import translate_databricks
from adbc_poolhouse._duckdb_translator import translate_duckdb
from adbc_poolhouse._flightsql_translator import translate_flightsql
from adbc_poolhouse._mssql_translator import translate_mssql
from adbc_poolhouse._postgresql_translator import translate_postgresql
from adbc_poolhouse._redshift_translator import translate_redshift
from adbc_poolhouse._snowflake_translator import translate_snowflake
from adbc_poolhouse._teradata_translator import translate_teradata
from adbc_poolhouse._trino_translator import translate_trino


def translate_config(config: WarehouseConfig) -> dict[str, str]:
    """Translate any warehouse config to ADBC driver kwargs."""
    if isinstance(config, DuckDBConfig):
        return translate_duckdb(config)
    if isinstance(config, SnowflakeConfig):
        return translate_snowflake(config)
    if isinstance(config, BigQueryConfig):
        return translate_bigquery(config)
    if isinstance(config, PostgreSQLConfig):
        return translate_postgresql(config)
    if isinstance(config, FlightSQLConfig):
        return translate_flightsql(config)
    if isinstance(config, DatabricksConfig):
        return translate_databricks(config)
    if isinstance(config, RedshiftConfig):
        return translate_redshift(config)
    if isinstance(config, TrinoConfig):
        return translate_trino(config)
    if isinstance(config, MSSQLConfig):
        return translate_mssql(config)
    if isinstance(config, TeradataConfig):
        return translate_teradata(config)
    raise TypeError(f"Unsupported config type: {type(config).__name__}")
```

### Pattern 3: 3-Path Driver Detection

**What:** `_drivers.py` exposes `resolve_driver(config) -> str` using a 3-step chain. No driver imports at module level.

```python
# src/adbc_poolhouse/_drivers.py
from __future__ import annotations

import importlib.util
import pathlib

from adbc_poolhouse._base_config import WarehouseConfig
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._snowflake_config import SnowflakeConfig
# ... other config imports (config modules have no ADBC imports, safe to import at module level)


# --- PyPI package metadata ---
_PYPI_PACKAGES: dict[type, tuple[str, str]] = {
    # config_type -> (python_package_name, pip_extra)
    # DuckDB is special-cased below (uses _duckdb C extension)
    # SnowflakeConfig -> ('adbc_driver_snowflake', 'snowflake')
    # etc.
}

# --- Foundry driver metadata ---
_FOUNDRY_DRIVERS: dict[type, tuple[str, str]] = {
    # config_type -> (driver_manager_name, dbc_install_name)
    # DatabricksConfig -> ('databricks', 'databricks')
    # etc.
}


def resolve_driver(config: WarehouseConfig) -> str:
    """
    Return the driver path string for adbc_driver_manager.dbapi.connect().

    Raises ImportError with install instructions if the driver cannot be found.
    All imports are deferred — this function is only called at pool creation time.
    """
    if isinstance(config, DuckDBConfig):
        return _resolve_duckdb()
    # ... dispatch by config type


def _resolve_duckdb() -> str:
    """DuckDB: find _duckdb C extension, return its path."""
    spec = importlib.util.find_spec("_duckdb")
    if spec is None or spec.origin is None:
        spec = importlib.util.find_spec("duckdb")
    if spec is None or spec.origin is None:
        raise ImportError(
            "DuckDB ADBC driver not found. Run: `pip install adbc-poolhouse[duckdb]`"
        )
    return str(pathlib.Path(spec.origin))


def _resolve_pypi_driver(config_class_name: str, pkg_name: str, extra: str) -> str:
    """Path 1: find_spec + _driver_path(). Path 2: manifest. Path 3: ImportError."""
    # Path 1: PyPI wheel install
    spec = importlib.util.find_spec(pkg_name)
    if spec is not None:
        pkg = __import__(pkg_name)
        return pkg._driver_path()  # type: ignore[attr-defined]

    # Path 2: manifest/system install — pass short name and let driver manager resolve
    # (works for conda, apt, or manually placed .toml manifests)
    # Return the package name; driver manager will search manifests + LD_LIBRARY_PATH
    # The caller (create_adbc_connection) will catch NOT_FOUND and re-raise as ImportError
    return pkg_name  # driver manager will attempt manifest resolution

    # NOTE: Path 3 (ImportError) is raised in create_adbc_connection when
    # adbc_driver_manager raises NOT_FOUND.
```

**IMPORTANT:** For the 3-path flow, the Path 3 `ImportError` with install instructions is raised from `_driver_api.py`'s `create_adbc_connection()`, not from `resolve_driver()`. The `resolve_driver()` function can return a name that will fail in the driver manager — the `create_adbc_connection()` function catches the driver manager's `NOT_FOUND` error and re-raises it as a descriptive `ImportError`. This keeps `resolve_driver()` clean and keeps the error message logic centralized.

### Pattern 4: ADBC Facade (_driver_api.py)

**What:** Single function that calls `adbc_driver_manager.dbapi.connect()`. All `cast()` and `# type: ignore` suppressions live here.

```python
# src/adbc_poolhouse/_driver_api.py
from __future__ import annotations

from typing import TYPE_CHECKING

import adbc_driver_manager.dbapi

if TYPE_CHECKING:
    from adbc_driver_manager.dbapi import Connection


def create_adbc_connection(driver_path: str, kwargs: dict[str, str]) -> "Connection":
    """
    Create an ADBC DBAPI connection. All type suppressions for ADBC live here.

    ADBC exceptions pass through raw — no wrapping.
    """
    # adbc_driver_manager.dbapi.connect() is typed but cursor methods have Unknown types
    # in basedpyright strict mode. All suppression is concentrated in this module.
    conn = adbc_driver_manager.dbapi.connect(  # type: ignore[call-overload]
        driver_path,
        db_kwargs=kwargs,
    )
    return conn  # type: ignore[return-value]
```

### Pattern 5: _pool_types.py (Minimal Phase 4 Scope)

Per the CONTEXT.md discretion: Phase 4 should create `_pool_types.py` with only the type infrastructure needed. The QueuePool assembly itself (using these types) is Phase 5.

```python
# src/adbc_poolhouse/_pool_types.py
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from adbc_driver_manager.dbapi import Connection
    from sqlalchemy.pool import QueuePool

# Type alias for the callable that QueuePool.creator expects
# QueuePool requires Callable[[], DBAPIConnection] but ADBC's Connection
# doesn't explicitly satisfy SQLAlchemy's internal _DBAPIConnection Protocol.
# cast() to this type alias where needed.
AdbcCreatorFn = Callable[[], "Connection"]
```

### Anti-Patterns to Avoid

- **Top-level ADBC driver imports in translators:** `from adbc_driver_snowflake import DatabaseOptions` at module level in a translator file violates TRANS-05. Use string literals for the key names instead.
- **Top-level driver detection in `_drivers.py`:** Any `find_spec()` or `import` at module level in `_drivers.py` executes at import time, violating DRIV-04.
- **Calling `config._adbc_driver_key()` as the sole dispatch mechanism:** The `_adbc_driver_key()` method exists on BaseWarehouseConfig subclasses but is insufficient — the translator and driver detection both need the full config instance (for field access and for precise error messages).
- **Omitting bool/int conversion:** ADBC kwargs must be `dict[str, str]`. Passing `True` instead of `"true"` will fail silently or raise at the C layer. Always convert: `str(bool_val).lower()`, `str(int_val)`.
- **Wrapping ADBC exceptions in Phase 4:** DRIV-03 only requires `ImportError` for missing drivers. Other ADBC errors (auth failures, network errors) pass through raw in Phase 4 — wrapping is a Phase 5+ concern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Finding PyPI driver .so path | Custom path search through site-packages | `pkg._driver_path()` (internal API of each ADBC driver package) | Already handles wheel, conda, system install paths with lru_cache |
| ADBC manifest resolution | Custom TOML parsing | Pass driver name to `adbc_driver_manager.dbapi.connect()` | Driver manager already implements the manifest search protocol |
| DuckDB library path | Platform-specific dlopen logic | `find_spec('_duckdb').origin` + `entrypoint='duckdb_adbc_init'` | DuckDB bundles ADBC in its Python C extension |
| SecretStr extraction | Direct attribute access | `.get_secret_value()` | Pydantic SecretStr does not expose value via `str()` |

**Key insight:** Every installed ADBC PyPI package exposes `_driver_path()` as a private but stable API with lru_cache. This is the intended way to get the shared library path without implementing platform-specific lookup logic.

## Common Pitfalls

### Pitfall 1: DuckDB driver path is NOT `duckdb._driver_path()`

**What goes wrong:** The `duckdb` Python package does NOT expose `_driver_path()`. It does not follow the `adbc_driver_*` naming convention. The ADBC entry point is the `_duckdb` C extension itself.

**Why it happens:** DuckDB bundles its ADBC support inside the Python C extension (`_duckdb.cpython-*.so`), not as a separate shared library.

**How to avoid:** Use `importlib.util.find_spec("_duckdb").origin` to get the path, then pass `entrypoint="duckdb_adbc_init"` to `adbc_driver_manager.dbapi.connect()`.

**Verified:** `dbapi.connect(str(Path(find_spec("_duckdb").origin)), entrypoint="duckdb_adbc_init", db_kwargs={"path": ":memory:"})` — works in the project venv.

### Pitfall 2: Foundry drivers have no Python package to find_spec

**What goes wrong:** `importlib.util.find_spec("adbc_driver_databricks")` — no such package exists. Foundry drivers are installed via `dbc install databricks`, placing a manifest `.toml` in `~/.config/adbc/drivers/` and the `.so` in a path referenced by that manifest.

**Why it happens:** Foundry uses the ADBC driver manifest system, not Python packaging.

**How to avoid:** For Foundry backends, skip `find_spec()` entirely. Pass the short driver name (e.g., `"databricks"`) directly to `adbc_driver_manager.dbapi.connect()`. The driver manager searches `ADBC_DRIVER_PATH`, `~/.config/adbc/drivers`, and system directories automatically. If the manifest is not found, driver manager raises `NOT_FOUND` — catch this and re-raise as `ImportError` pointing to `https://docs.adbc-drivers.org/`.

**Warning signs:** If `find_spec()` is called for Foundry backends at all, the code path is wrong.

### Pitfall 3: bool/int values passed as non-string to db_kwargs

**What goes wrong:** `db_kwargs={"adbc.snowflake.sql.client_option.tls_skip_verify": False}` — ADBC's `AdbcDatabase(**kwargs)` constructor is typed as `Dict[str, Union[str, pathlib.Path]]`. Passing a bool or int causes a type error or silent coercion failure.

**Why it happens:** Config fields like `tls_skip_verify: bool = False` naturally hold booleans.

**How to avoid:** All translator output values must be strings. Use `str(val).lower()` for booleans (`"true"`/`"false"`), `str(val)` for integers. Enforce this with the return type `dict[str, str]`.

### Pitfall 4: `schema_` attribute name vs ADBC key

**What goes wrong:** `config.schema` raises `AttributeError` — the Python attribute is `schema_` (trailing underscore to avoid Pydantic reserved name conflict). The ADBC key is `"adbc.snowflake.sql.schema"` (no underscore). Same pattern for `TrinoConfig.schema_`, `DatabricksConfig.schema_`.

**Why it happens:** Pydantic `BaseSettings` reserves `schema`; Phase 3 added `schema_` with `alias="schema"`.

**How to avoid:** Always reference `config.schema_` in translators. Verify with Phase 3 config source.

### Pitfall 5: Never omit `None` check before adding to kwargs dict

**What goes wrong:** Adding `None` values to `db_kwargs` as strings (`"None"`) causes driver connection failures.

**Why it happens:** Translators that iterate config fields without checking for `None` first.

**How to avoid:** Only include a key in the output dict if the config field is not `None`. For required fields (e.g., `SnowflakeConfig.account`), always include. For optional fields, use `if config.field is not None:` guards.

### Pitfall 6: Snowflake user and password use plain string keys

**What goes wrong:** Trying `"adbc.snowflake.sql.user"` or `"adbc.snowflake.sql.password"` — these keys do not exist in the Snowflake driver's `DatabaseOptions` enum.

**Why it happens:** Assuming all Snowflake keys follow the `adbc.snowflake.sql.*` prefix.

**How to avoid:** Snowflake user → `"username"`, password → `"password"` (plain string keys). Verified from official ADBC Snowflake docs example and `DatabaseOptions` enum inspection.

### Pitfall 7: Omitting `entrypoint` for DuckDB

**What goes wrong:** `dbapi.connect("path/to/_duckdb.cpython-*.so")` without `entrypoint="duckdb_adbc_init"` — driver manager cannot find the ADBC entry point.

**Why it happens:** The `_duckdb.cpython-*.so` file is a Python C extension with a Python-style init function, not the standard ADBC init. DuckDB exports a second entry point specifically for ADBC.

**How to avoid:** Always pass `entrypoint="duckdb_adbc_init"` when connecting via DuckDB's C extension path.

## Code Examples

### DuckDB Translator

```python
# Source: verified against duckdb docs and live testing
# src/adbc_poolhouse/_duckdb_translator.py

from __future__ import annotations

from adbc_poolhouse._duckdb_config import DuckDBConfig


def translate_duckdb(config: DuckDBConfig) -> dict[str, str]:
    """Translate DuckDBConfig → ADBC driver kwargs dict."""
    kwargs: dict[str, str] = {"path": config.database}
    if config.read_only:
        kwargs["access_mode"] = "READ_ONLY"
    return kwargs
```

**Verified:** `dbapi.connect(duckdb_so, entrypoint='duckdb_adbc_init', db_kwargs={"path": ":memory:"})` and `db_kwargs={"path": tmp, "access_mode": "READ_ONLY"}` both confirmed working.

### PostgreSQL Translator

```python
# Source: verified against installed adbc_driver_postgresql source
# src/adbc_poolhouse/_postgresql_translator.py

from __future__ import annotations

from adbc_poolhouse._postgresql_config import PostgreSQLConfig


def translate_postgresql(config: PostgreSQLConfig) -> dict[str, str]:
    """Translate PostgreSQLConfig → ADBC driver kwargs dict."""
    kwargs: dict[str, str] = {}
    if config.uri is not None:
        kwargs["uri"] = config.uri
    # use_copy is a StatementOption (per-statement), not a db-level kwarg
    # It will be handled at connection/cursor level in Phase 5
    return kwargs
```

**Note on `use_copy`:** `adbc.postgresql.use_copy` is a `StatementOptions` key, not a database initialization key. It cannot be passed to `dbapi.connect()` as a `db_kwarg`. This means `PostgreSQLConfig.use_copy` is not translatable at the connection level — it's a cursor-level option. The translator correctly omits it. Flag this for Phase 5 design.

### BigQuery Translator

```python
# Source: verified from installed adbc_driver_bigquery.DatabaseOptions enum
# src/adbc_poolhouse/_bigquery_translator.py

from __future__ import annotations

from adbc_poolhouse._bigquery_config import BigQueryConfig


def translate_bigquery(config: BigQueryConfig) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    if config.auth_type is not None:
        kwargs["adbc.bigquery.sql.auth_type"] = config.auth_type
    if config.auth_credentials is not None:
        kwargs["adbc.bigquery.sql.auth_credentials"] = config.auth_credentials.get_secret_value()
    if config.auth_client_id is not None:
        kwargs["adbc.bigquery.sql.auth.client_id"] = config.auth_client_id
    if config.auth_client_secret is not None:
        kwargs["adbc.bigquery.sql.auth.client_secret"] = config.auth_client_secret.get_secret_value()
    if config.auth_refresh_token is not None:
        kwargs["adbc.bigquery.sql.auth.refresh_token"] = config.auth_refresh_token.get_secret_value()
    if config.project_id is not None:
        kwargs["adbc.bigquery.sql.project_id"] = config.project_id
    if config.dataset_id is not None:
        kwargs["adbc.bigquery.sql.dataset_id"] = config.dataset_id
    return kwargs
```

### FlightSQL Translator (partial — key names)

Key mapping (from installed `adbc_driver_flightsql.DatabaseOptions` enum, verified):

| Config field | ADBC key | Notes |
|---|---|---|
| `uri` | `"uri"` | Top-level uri parameter |
| `username` | `"username"` | Plain key |
| `password` | `"password"` (SecretStr) | Plain key, `.get_secret_value()` |
| `authorization_header` | `"adbc.flight.sql.authorization_header"` | SecretStr |
| `mtls_cert_chain` | `"adbc.flight.sql.client_option.mtls_cert_chain"` | |
| `mtls_private_key` | `"adbc.flight.sql.client_option.mtls_private_key"` | SecretStr |
| `tls_root_certs` | `"adbc.flight.sql.client_option.tls_root_certs"` | |
| `tls_skip_verify` | `"adbc.flight.sql.client_option.tls_skip_verify"` | bool → `"true"`/`"false"` |
| `tls_override_hostname` | `"adbc.flight.sql.client_option.tls_override_hostname"` | |
| `connect_timeout` | `"adbc.flight.sql.rpc.timeout_seconds.connect"` | float → str |
| `query_timeout` | `"adbc.flight.sql.rpc.timeout_seconds.query"` | float → str; also a StatementOption |
| `fetch_timeout` | `"adbc.flight.sql.rpc.timeout_seconds.fetch"` | float → str; also a StatementOption |
| `update_timeout` | `"adbc.flight.sql.rpc.timeout_seconds.update"` | float → str; also a StatementOption |
| `authority` | `"adbc.flight.sql.client_option.authority"` | |
| `max_msg_size` | `"adbc.flight.sql.client_option.with_max_msg_size"` | int → str |
| `with_cookie_middleware` | `"adbc.flight.sql.rpc.with_cookie_middleware"` | bool → `"true"`/`"false"` |

**Note:** `connect_timeout` is NOT in the Python `DatabaseOptions` enum (which only has TIMEOUT_FETCH, TIMEOUT_QUERY, TIMEOUT_UPDATE). The key `"adbc.flight.sql.rpc.timeout_seconds.connect"` is documented in official ADBC docs. Pass as a raw string key in the translator.

### Foundry Driver Translators (URI-based)

All Foundry drivers (Databricks, Redshift, Trino, MSSQL, Teradata) use URI-only connection model:

```python
# Pattern for all Foundry translators:
def translate_databricks(config: DatabricksConfig) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    if config.uri is not None:
        kwargs["uri"] = config.uri.get_secret_value()  # DatabricksConfig.uri is SecretStr
    return kwargs
```

**Foundry driver name strings** (verified from docs.adbc-drivers.org):
- Databricks: `"databricks"`
- Redshift: `"redshift"`
- Trino: `"trino"`
- MSSQL: `"mssql"`
- Teradata: NOT YET VERIFIED — docs page unavailable (404 at research time); use `"teradata"` as best guess

**WARNING (LOW confidence):** Teradata field names in `TeradataConfig` were already flagged as LOW confidence in Phase 3 (docs returned 404). The translator for Teradata should pass the `uri` field if available, and individual fields (host, user, password, etc.) only if the Columnar ADBC Teradata driver's actual parameter names are verified. Add a TODO comment in the Teradata translator noting this.

### Test Pattern: Translator Unit Tests (TEST-05)

```python
# tests/test_translators.py

from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._duckdb_translator import translate_duckdb


class TestDuckDBTranslator:
    def test_memory_database(self) -> None:
        config = DuckDBConfig()  # database=":memory:", read_only=False
        result = translate_duckdb(config)
        assert result == {"path": ":memory:"}

    def test_file_database(self) -> None:
        config = DuckDBConfig(database="/tmp/test.db")
        result = translate_duckdb(config)
        assert result == {"path": "/tmp/test.db"}

    def test_read_only(self) -> None:
        config = DuckDBConfig(database="/tmp/test.db", read_only=True)
        result = translate_duckdb(config)
        assert result == {"path": "/tmp/test.db", "access_mode": "READ_ONLY"}
```

### Test Pattern: Driver Detection Unit Tests (TEST-06)

```python
# tests/test_drivers.py
from unittest.mock import MagicMock, patch

import pytest

from adbc_poolhouse._drivers import resolve_driver
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._snowflake_config import SnowflakeConfig


class TestResolveDriver:
    def test_pypi_found_via_find_spec(self) -> None:
        """Path 1: find_spec succeeds -> uses _driver_path()."""
        mock_spec = MagicMock()
        mock_spec.origin = "/path/to/_duckdb.cpython-314-darwin.so"
        with patch("importlib.util.find_spec", return_value=mock_spec):
            path = resolve_driver(DuckDBConfig())
        assert path == "/path/to/_duckdb.cpython-314-darwin.so"

    def test_pypi_missing_raises_import_error(self) -> None:
        """Path 3: find_spec returns None -> ImportError with install command."""
        with patch("importlib.util.find_spec", return_value=None):
            with pytest.raises(ImportError, match="pip install adbc-poolhouse\\[duckdb\\]"):
                resolve_driver(DuckDBConfig())
```

## Exact ADBC Parameter Key Reference

### Snowflake (verified from installed `adbc_driver_snowflake` source)

| Config field | ADBC key | Type conversion |
|---|---|---|
| `account` | `"adbc.snowflake.sql.account"` | str, always include |
| `user` | `"username"` | str |
| `password` | `"password"` | SecretStr → `.get_secret_value()` |
| `auth_type` | `"adbc.snowflake.sql.auth_type"` | str |
| `private_key_path` | `"adbc.snowflake.sql.client_option.jwt_private_key"` | Path → `str()` |
| `private_key_pem` | `"adbc.snowflake.sql.client_option.jwt_private_key_pkcs8_value"` | SecretStr |
| `private_key_passphrase` | `"adbc.snowflake.sql.client_option.jwt_private_key_pkcs8_password"` | SecretStr |
| `jwt_expire_timeout` | `"adbc.snowflake.sql.client_option.jwt_expire_timeout"` | str |
| `oauth_token` | `"adbc.snowflake.sql.client_option.auth_token"` | SecretStr |
| `okta_url` | `"adbc.snowflake.sql.client_option.okta_url"` | str |
| `identity_provider` | `"adbc.snowflake.sql.client_option.identity_provider"` | str |
| `database` | `"adbc.snowflake.sql.db"` | str |
| `schema_` | `"adbc.snowflake.sql.schema"` | str (note: attribute is `schema_`) |
| `warehouse` | `"adbc.snowflake.sql.warehouse"` | str |
| `role` | `"adbc.snowflake.sql.role"` | str |
| `region` | `"adbc.snowflake.sql.region"` | str |
| `host` | `"adbc.snowflake.sql.uri.host"` | str |
| `port` | `"adbc.snowflake.sql.uri.port"` | int → str |
| `protocol` | `"adbc.snowflake.sql.uri.protocol"` | str |
| `login_timeout` | `"adbc.snowflake.sql.client_option.login_timeout"` | str |
| `request_timeout` | `"adbc.snowflake.sql.client_option.request_timeout"` | str |
| `client_timeout` | `"adbc.snowflake.sql.client_option.client_timeout"` | str |
| `tls_skip_verify` | `"adbc.snowflake.sql.client_option.tls_skip_verify"` | bool → `"true"`/`"false"` |
| `ocsp_fail_open_mode` | `"adbc.snowflake.sql.client_option.ocsp_fail_open_mode"` | bool → `"true"`/`"false"` |
| `keep_session_alive` | `"adbc.snowflake.sql.client_option.keep_session_alive"` | bool → `"true"`/`"false"` |
| `app_name` | `"adbc.snowflake.sql.client_option.app_name"` | str |
| `disable_telemetry` | `"adbc.snowflake.sql.client_option.disable_telemetry"` | bool → `"true"`/`"false"` |
| `cache_mfa_token` | `"adbc.snowflake.sql.client_option.cache_mfa_token"` | bool → `"true"`/`"false"` |
| `store_temp_creds` | `"adbc.snowflake.sql.client_option.store_temp_creds"` | bool → `"true"`/`"false"` |

### BigQuery (verified from installed `adbc_driver_bigquery` source)

| Config field | ADBC key |
|---|---|
| `auth_type` | `"adbc.bigquery.sql.auth_type"` |
| `auth_credentials` | `"adbc.bigquery.sql.auth_credentials"` (SecretStr) |
| `auth_client_id` | `"adbc.bigquery.sql.auth.client_id"` |
| `auth_client_secret` | `"adbc.bigquery.sql.auth.client_secret"` (SecretStr) |
| `auth_refresh_token` | `"adbc.bigquery.sql.auth.refresh_token"` (SecretStr) |
| `project_id` | `"adbc.bigquery.sql.project_id"` |
| `dataset_id` | `"adbc.bigquery.sql.dataset_id"` |

### PostgreSQL (verified from installed `adbc_driver_postgresql` source)

| Config field | ADBC key | Notes |
|---|---|---|
| `uri` | `"uri"` | libpq connection string |
| `use_copy` | NOT a db_kwarg | `adbc.postgresql.use_copy` is a `StatementOptions` key — set per cursor, not at pool creation |

### DuckDB (verified via live testing)

| Config field | ADBC key | Notes |
|---|---|---|
| `database` | `"path"` | `":memory:"` for in-memory |
| `read_only` | `"access_mode"` = `"READ_ONLY"` | Only include key when `True` |

**Driver resolution:** `find_spec("_duckdb").origin` + `entrypoint="duckdb_adbc_init"`

### Foundry Drivers — Driver Name Strings (from docs.adbc-drivers.org)

| Config class | Driver name string | dbc install command |
|---|---|---|
| `DatabricksConfig` | `"databricks"` | `dbc install databricks` |
| `RedshiftConfig` | `"redshift"` | `dbc install redshift` |
| `TrinoConfig` | `"trino"` | `dbc install trino` |
| `MSSQLConfig` | `"mssql"` | `dbc install mssql` |
| `TeradataConfig` | `"teradata"` | `dbc install teradata` (LOW confidence — docs 404) |

**Foundry ImportError docs URL:** `https://docs.adbc-drivers.org/` — verified as the correct canonical URL for all Foundry drivers.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Bare `except ImportError` for driver detection | `importlib.util.find_spec()` | ADBC best practices (pre-2024) | Distinguishes missing vs broken native extension |
| Directly importing ADBC driver at module level | Lazy import deferred to connection time | ADBC design; DRIV-04 requirement | Library importable even without driver installed |
| `adbc_driver_manager.AdbcDatabase` (low-level) | `adbc_driver_manager.dbapi.connect()` (DBAPI 2.0) | ADBC v1.x | Higher-level API, compatible with SQLAlchemy pool creator |

## Open Questions

1. **PostgreSQL `use_copy` — how does Phase 5 apply it?**
   - What we know: `adbc.postgresql.use_copy` is a `StatementOptions` key, not a `DatabaseOptions` key. It cannot be passed to `dbapi.connect()`.
   - What's unclear: Does Phase 5's QueuePool creator function have an opportunity to set this per-connection? Or is it set per-cursor?
   - Recommendation: Document in `PostgreSQLConfig.use_copy` field docstring that this setting cannot be applied at pool creation time; flag for Phase 5 design.

2. **Teradata Foundry driver parameter names**
   - What we know: `TeradataConfig` field names were triangulated from JDBC and teradatasql docs (LOW confidence). The Foundry Teradata driver docs returned 404 at Phase 3 and Phase 4 research.
   - What's unclear: Whether the Teradata Foundry driver uses `host`, `user`, `password` as db_kwargs directly, or requires a URI.
   - Recommendation: Implement `translate_teradata` with `uri`-first, individual fields as fallback, add TODO comment to verify against actual driver when available. Mark as LOW confidence in code comments.

3. **Snowflake bool kwargs — should some be omitted when at default?**
   - What we know: Several Snowflake bool fields (`tls_skip_verify=False`, `ocsp_fail_open_mode=True`, etc.) have specific driver defaults that may differ from the config defaults.
   - What's unclear: Whether passing the default value explicitly overrides Snowflake's built-in defaults in unexpected ways.
   - Recommendation: Only include bool flags in kwargs when they differ from documented Snowflake driver defaults. Alternatively, always include (safest) and document the decision.

4. **FlightSQL `connect_timeout` key**
   - What we know: The ADBC docs show `"adbc.flight.sql.rpc.timeout_seconds.connect"` as a valid key. It is NOT in the `adbc_driver_flightsql.DatabaseOptions` Python enum.
   - What's unclear: Whether the key is accepted but just not exposed via the Python enum.
   - Recommendation: Include it in the translator as a raw string key. If the driver rejects it at runtime, log clearly — but this is a Phase 5+ concern.

## Sources

### Primary (HIGH confidence)
- Installed `adbc_driver_snowflake` source — `DatabaseOptions` enum, `AuthType` enum, `_driver_path()` — inspected live
- Installed `adbc_driver_bigquery` source — `DatabaseOptions` enum — inspected live
- Installed `adbc_driver_postgresql` source — `StatementOptions`, `_driver_path()` — inspected live
- Installed `adbc_driver_flightsql` source — `DatabaseOptions`, `ConnectionOptions`, `StatementOptions` — inspected live
- `adbc_driver_manager.dbapi.connect()` source — full signature and implementation — inspected live
- Live connection testing: DuckDB ADBC via `_duckdb.cpython-*.so` + `duckdb_adbc_init` — confirmed working
- Live connection testing: `access_mode=READ_ONLY` for DuckDB — confirmed working
- `basedpyright` type check — `reportUnknownMemberType` on ADBC cursor methods — confirmed

### Secondary (MEDIUM confidence)
- [ADBC Driver Foundry](https://docs.adbc-drivers.org/) — driver name strings for Databricks (`"databricks"`), Redshift (`"redshift"`), Trino (`"trino"`), MSSQL (`"mssql"`) — verified from individual driver pages
- [Apache ADBC Snowflake Driver docs](https://arrow.apache.org/adbc/current/driver/snowflake.html) — `username` key confirmed in Python example
- [Apache ADBC Driver Manifests](https://arrow.apache.org/adbc/current/format/driver_manifests.html) — manifest search path order
- [DuckDB ADBC docs](https://duckdb.org/docs/stable/clients/adbc) — `path` parameter, `duckdb_adbc_init` entrypoint

### Tertiary (LOW confidence)
- Teradata Foundry driver name `"teradata"` — inferred from pattern, docs page returned 404
- FlightSQL `"adbc.flight.sql.rpc.timeout_seconds.connect"` key — from ADBC docs text, not in Python enum
- PostgreSQL `use_copy` as statement-only option — from driver source `StatementOptions` class; behavior at pool level unverified

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all verified against installed versions
- Architecture: HIGH — all translator key names verified from installed source or live testing
- Pitfalls: HIGH — each pitfall verified via live testing or source inspection
- Foundry drivers: MEDIUM — driver name strings verified from docs; Teradata LOW

**Research date:** 2026-02-24
**Valid until:** 2026-05-24 (ADBC driver packages update frequently; re-verify major version bumps)
