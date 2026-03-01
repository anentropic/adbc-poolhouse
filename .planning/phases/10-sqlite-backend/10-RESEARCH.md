# Phase 10: SQLite Backend - Research

**Researched:** 2026-03-01
**Domain:** ADBC SQLite driver integration, PyPI extras, Pydantic BaseSettings, MkDocs documentation
**Confidence:** HIGH (stack and patterns), MEDIUM (entrypoint string — requires implementation-time validation)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SQLT-01 | `SQLiteConfig` — Pydantic `BaseSettings`; `env_prefix="SQLITE_"`; `model_validator` raises `ValueError` for `database=":memory:"` with `pool_size > 1` | DuckDB config pattern; exact same guard; `_base_config.py` + `_duckdb_config.py` are the templates |
| SQLT-02 | `translate_sqlite()` — pure function mapping `SQLiteConfig` fields to `adbc_driver_manager` kwargs | SQLite driver uses `uri` key (not `path`); `_adbc_entrypoint()` returns `"adbc_driver_sqlite_init"` — MEDIUM confidence, verify at implementation time |
| SQLT-03 | `sqlite` optional extra in `pyproject.toml` (`adbc-driver-sqlite>=1.0.0`); included in `[all]` meta-extra; `uv.lock` updated | `pyproject.toml` extras pattern established; add to `_PYPI_PACKAGES` dict in `_drivers.py` |
| SQLT-04 | Unit tests for config validation; translator kwargs; mock-at-`create_adbc_connection` pool-factory wiring; integration test with in-memory SQLite | `test_configs.py`, `test_translators.py`, `test_pool_factory.py` are the templates; SQLite in-memory works without credentials |
| SQLT-05 | `SQLiteConfig` exported from `__init__.py`; SQLite warehouse guide in docs; API reference entry; `uv run mkdocs build --strict` passes | CLAUDE.md docs quality gate applies (phase >= 7); `mkdocs.yml` nav must include `guides/sqlite.md` |
</phase_requirements>

---

## Summary

Phase 10 adds SQLite as a PyPI-backed ADBC warehouse. The implementation follows the same pattern as the existing PyPI drivers (Snowflake, BigQuery, PostgreSQL, FlightSQL), with the closest analog being `DuckDBConfig` for the in-memory pool-size guard. SQLite is the simplest backend to add: the `adbc-driver-sqlite` package is on PyPI, the driver has minimal connection parameters, and integration tests run without any credentials using an in-memory database.

The main technical question is the `_adbc_entrypoint()` return value. The project specification says it must return `"adbc_driver_sqlite_init"`, but the C library exports `AdbcDriverSqliteInit` (PascalCase). DuckDB uses `"duckdb_adbc_init"` (its actual C function name). Whether `"adbc_driver_sqlite_init"` is a valid alias or an incorrect value must be validated at implementation time by running `adbc_driver_manager.dbapi.connect()` with the driver path and `entrypoint="adbc_driver_sqlite_init"` against a real in-memory SQLite database.

The SQLite in-memory isolation behavior differs from DuckDB: SQLite's in-memory database is **shared across all connections** (not isolated per connection like DuckDB). The requirement still mandates the pool-size guard for consistency and to prevent accidental large pool creation. The documentation guide must note this distinction.

**Primary recommendation:** Follow the DuckDB pattern precisely (same file structure, same validator logic, same `_PYPI_PACKAGES` registration), substituting `uri` for `path` as the translator kwarg key, and validate the entrypoint string with a live test before finalizing.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `adbc-driver-sqlite` | 1.10.0 (Jan 2026) | SQLite ADBC driver shared library | Official Apache Arrow ADBC implementation; on PyPI |
| `pydantic-settings` | >=2.0.0 (already in deps) | `BaseSettings` subclass with env var loading | Established project pattern for all configs |
| `adbc-driver-manager` | >=1.8.0 (already in deps) | Manages driver loading and DBAPI connection | Already required; handles path-based driver loading |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | >=8.0.0 (already in dev) | Unit and integration tests | SQLT-04 — all test categories |
| `uv` | project tooling | Lock file update after adding extra | `uv lock` after editing `pyproject.toml` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `adbc-driver-sqlite` | `sqlite3` stdlib + adapter | `sqlite3` is not ADBC; would bypass the entire poolhouse architecture |
| `:memory:` guard (pool_size=1) | No guard | Spec requires consistency with DuckDB guard; in-memory pool_size > 1 is almost always a bug |

**Installation (for consumers):**
```bash
pip install adbc-poolhouse[sqlite]
# or with uv:
uv add "adbc-poolhouse[sqlite]"
```

**Dev environment update (pyproject.toml + uv.lock):**
```bash
uv lock  # regenerate lock after editing pyproject.toml extras
```

---

## Architecture Patterns

### Where Each New File Goes

```
src/adbc_poolhouse/
├── _sqlite_config.py        # NEW — SQLiteConfig class (mirrors _duckdb_config.py)
├── _sqlite_translator.py    # NEW — translate_sqlite() pure function
├── _drivers.py              # EDIT — add SQLiteConfig to _PYPI_PACKAGES
├── _translators.py          # EDIT — add SQLiteConfig branch and translate_sqlite import
└── __init__.py              # EDIT — add SQLiteConfig to imports and __all__

tests/
├── test_configs.py          # EDIT — add TestSQLiteConfig class
├── test_translators.py      # EDIT — add TestSQLiteTranslator class
└── test_pool_factory.py     # EDIT — add TestSQLitePoolFactory mock wiring test
                             #        and integration test with in-memory SQLite

docs/src/guides/
└── sqlite.md                # NEW — SQLite warehouse guide (mirrors duckdb.md)

docs/mkdocs.yml              # EDIT — add SQLite to Warehouse Guides nav section

pyproject.toml               # EDIT — add sqlite extra, add to [all] meta-extra
```

### Pattern 1: SQLiteConfig class (mirrors DuckDBConfig exactly)

**What:** `BaseWarehouseConfig` subclass with `env_prefix="SQLITE_"`, `database` field defaulting to `":memory:"`, `pool_size` defaulting to `1` for in-memory, and a `model_validator` that raises `ConfigurationError`/`ValueError` when `database=":memory:"` and `pool_size > 1`.

**When to use:** This is the only config pattern for SQLite.

**Template to follow** (from `_duckdb_config.py`):
```python
# Source: src/adbc_poolhouse/_duckdb_config.py (established pattern)
from __future__ import annotations

from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class SQLiteConfig(BaseWarehouseConfig):
    """
    SQLite warehouse configuration.

    Covers all SQLite ADBC connection parameters. Pool tuning fields
    (pool_size, max_overflow, timeout, recycle) are inherited from
    BaseWarehouseConfig and loaded from SQLITE_* environment variables.

    Example:
        SQLiteConfig(database='/data/warehouse.db', pool_size=5)
        SQLiteConfig()  # in-memory, pool_size=1 enforced by validator
    """

    model_config = SettingsConfigDict(env_prefix="SQLITE_")

    database: str = ":memory:"
    """File path or ':memory:'. Env: SQLITE_DATABASE."""

    pool_size: int = 1
    """Number of connections in the pool. Default 1 for in-memory SQLite.
    Env: SQLITE_POOL_SIZE.
    """

    def _adbc_entrypoint(self) -> str | None:
        # IMPORTANT: verify this string is the correct C function name
        # exported from libadbc_driver_sqlite at implementation time.
        # The C source exports 'AdbcDriverSqliteInit' (PascalCase).
        # 'adbc_driver_sqlite_init' is the project spec value — validate
        # it works before finalising.
        return "adbc_driver_sqlite_init"

    @model_validator(mode="after")
    def check_memory_pool_size(self) -> Self:
        if self.database == ":memory:" and self.pool_size > 1:
            raise ConfigurationError(
                'pool_size > 1 with database=":memory:" is almost always '
                "unintentional. Use pool_size=1 for in-memory SQLite, or set "
                "database to a file path if you need multiple connections."
            )
        return self
```

**Key differences from DuckDBConfig:**
- No `read_only` field (SQLite driver does not expose a read-only ADBC option)
- The field validators for `pool_size`, `max_overflow`, `timeout`, `recycle` are optional — DuckDB has them, but they are not required by SQLT-01. Omit them to keep the class minimal; add only if tests require them.
- Docstring must note that SQLite in-memory is shared across connections (unlike DuckDB's isolated-per-connection behaviour)

### Pattern 2: translate_sqlite() pure function

**What:** Returns `dict[str, str]` with `"uri"` key pointing to the database path. SQLite uses `uri` (not `path` like DuckDB).

```python
# Source: verified against adbc_driver_sqlite source (github.com/apache/arrow-adbc)
# AdbcDatabase is initialized as: adbc_driver_manager.AdbcDatabase(driver=..., uri=uri)
# So the key that goes into db_kwargs is "uri"

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._sqlite_config import SQLiteConfig


def translate_sqlite(config: SQLiteConfig) -> dict[str, str]:
    """
    Translate SQLiteConfig to ADBC driver kwargs.

    Returns:
        Dict with 'uri' key containing the database path or ':memory:'.
        All values are strings.

    Note:
        SQLite driver uses 'uri' (not 'path'). The entrypoint
        'adbc_driver_sqlite_init' is handled separately by _adbc_entrypoint().
    """
    return {"uri": config.database}
```

**Important:** The translator only emits `{"uri": ...}`. There are no boolean defaults to always include (unlike FlightSQL). All other SQLite options (`LOAD_EXTENSION_*`, `BATCH_ROWS`) are not surfaced in SQLiteConfig and not needed for Phase 10.

### Pattern 3: Driver registration in _drivers.py

SQLite is a **PyPI driver** (not a Foundry driver). It goes in `_PYPI_PACKAGES`:

```python
# src/adbc_poolhouse/_drivers.py — add to _PYPI_PACKAGES dict
from adbc_poolhouse._sqlite_config import SQLiteConfig

_PYPI_PACKAGES: dict[type, tuple[str, str]] = {
    # ... existing entries ...
    SQLiteConfig: ("adbc_driver_sqlite", "sqlite"),
}
```

The `resolve_driver()` function will then automatically:
1. Call `find_spec("adbc_driver_sqlite")` — if found, call `adbc_driver_sqlite._driver_path()` to get the .so/.dylib path
2. If not found, return `"adbc_driver_sqlite"` for manifest fallback
3. If manifest also fails, `create_adbc_connection()` catches `NOT_FOUND` and raises `ImportError` with install instructions

### Pattern 4: Dispatch in _translators.py

Add import and `isinstance` branch:

```python
from adbc_poolhouse._sqlite_config import SQLiteConfig
from adbc_poolhouse._sqlite_translator import translate_sqlite

# In translate_config():
if isinstance(config, SQLiteConfig):
    return translate_sqlite(config)
```

### Pattern 5: __init__.py export

Add `SQLiteConfig` to imports and `__all__`, maintaining alphabetical order:

```python
from adbc_poolhouse._sqlite_config import SQLiteConfig

__all__ = [
    # ... existing entries (alphabetical) ...
    # "SnowflakeConfig" comes before "SQLiteConfig" in the current list
    # Insert "SQLiteConfig" after "SnowflakeConfig"
    "SQLiteConfig",
    # ...
    "TrinoConfig",
    "create_pool",
]
```

### Pattern 6: pyproject.toml extras

```toml
[project.optional-dependencies]
# Add after bigquery entry:
sqlite = ["adbc-driver-sqlite>=1.0.0"]
all = [
    "adbc-poolhouse[duckdb]",
    "adbc-poolhouse[snowflake]",
    "adbc-poolhouse[postgresql]",
    "adbc-poolhouse[flightsql]",
    "adbc-poolhouse[bigquery]",
    "adbc-poolhouse[sqlite]",  # ADD THIS
]
```

After editing `pyproject.toml`, run `uv lock` to regenerate `uv.lock`.

### Pattern 7: mkdocs.yml nav

Add to the Warehouse Guides section (alphabetically by convention, though current list is not strictly alpha):

```yaml
- Warehouse Guides:
    - Snowflake: guides/snowflake.md
    - DuckDB: guides/duckdb.md
    - BigQuery: guides/bigquery.md
    - PostgreSQL: guides/postgresql.md
    - FlightSQL: guides/flightsql.md
    - Databricks: guides/databricks.md
    - Redshift: guides/redshift.md
    - Trino: guides/trino.md
    - MSSQL: guides/mssql.md
    - Teradata: guides/teradata.md
    - SQLite: guides/sqlite.md   # ADD THIS
```

### Anti-Patterns to Avoid

- **Using `path` as the db_kwargs key:** DuckDB uses `path`. SQLite uses `uri`. Mixing them up causes a silent connection failure (wrong key is ignored by the driver manager).
- **Using `read_only` field:** The ADBC SQLite driver does not expose a read-only connection option in `db_kwargs`. Do not add this field.
- **Putting SQLiteConfig in `_FOUNDRY_DRIVERS`:** SQLite is on PyPI. It must go in `_PYPI_PACKAGES`.
- **Entrypoint returning `None`:** Other PyPI drivers return `None` from `_adbc_entrypoint()` because they use `_driver_path()` internally. SQLite, like DuckDB, requires an explicit entrypoint when connecting via the path-based approach. The spec says `"adbc_driver_sqlite_init"` — validate this at implementation time.
- **Skipping `uv lock`:** Adding an optional extra to `pyproject.toml` without updating `uv.lock` breaks CI reproducible builds.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Loading the SQLite shared library | Custom `ctypes` or `dlopen` | `adbc_driver_sqlite._driver_path()` + `adbc_driver_manager.dbapi.connect()` | `_driver_path()` handles wheel bundles, Conda paths, and system paths correctly |
| In-memory pool guard | Custom logic | Direct copy of DuckDB's `check_memory_pool_size` model_validator | Same guard is already battle-tested and spec-mandated |
| Env var loading | Custom `os.environ.get()` | `pydantic-settings` `BaseSettings` with `env_prefix="SQLITE_"` | Already the universal pattern for all warehouse configs |
| Driver path resolution | Custom `find_spec` branch | Extend `_PYPI_PACKAGES` dict | `resolve_driver()` already handles all cases correctly |

**Key insight:** SQLite is the simplest backend to add. Every piece of infrastructure (config base class, translator dispatch, driver detection, pool factory) already exists. This phase is 90% wiring, 10% new code.

---

## Common Pitfalls

### Pitfall 1: Wrong db_kwargs key (`path` instead of `uri`)
**What goes wrong:** Translator returns `{"path": ":memory:"}` following the DuckDB pattern. The SQLite driver ignores the unknown key and either fails or opens a default unnamed database.
**Why it happens:** DuckDB uses `path`. SQLite uses `uri`. Tempting to copy-paste the DuckDB translator without checking.
**How to avoid:** The translator test asserts `result == {"uri": ":memory:"}` (not `{"path": ...}`). The integration test with in-memory SQLite will catch this at runtime.
**Warning signs:** Integration test runs without error but `SELECT` returns unexpected results, or `adbc_driver_manager` raises a schema/type error.

### Pitfall 2: Entrypoint string is wrong
**What goes wrong:** `_adbc_entrypoint()` returns `"adbc_driver_sqlite_init"` but the C library exports `AdbcDriverSqliteInit`. `adbc_driver_manager` raises a symbol-not-found error.
**Why it happens:** The project spec says `"adbc_driver_sqlite_init"` but the C source uses PascalCase. DuckDB's C function is `duckdb_adbc_init` (lowercase) — pattern is inconsistent across drivers.
**How to avoid:** The integration test must exercise the real driver path (not just a mock). If `create_pool(SQLiteConfig(database=":memory:"))` raises `adbc_driver_manager.Error` about symbol lookup, the entrypoint string is wrong. Try `"AdbcDriverSqliteInit"` as the alternative.
**Warning signs:** Error message contains "symbol not found" or "undefined symbol".

### Pitfall 3: SQLiteConfig added to `_FOUNDRY_DRIVERS` instead of `_PYPI_PACKAGES`
**What goes wrong:** Driver resolution tries to use manifest-based Foundry resolution. `resolve_driver()` returns `"sqlite"` as a short name. `adbc_driver_manager` gets `NOT_FOUND` because there is no Foundry manifest for SQLite. `ImportError` fires telling the user to `dbc install sqlite`.
**Why it happens:** Template confusion between Foundry and PyPI registration dicts.
**How to avoid:** SQLite is on PyPI. It goes in `_PYPI_PACKAGES` with tuple `("adbc_driver_sqlite", "sqlite")`.

### Pitfall 4: `uv.lock` not updated after adding extras
**What goes wrong:** CI runs `uv sync --frozen` and fails because `uv.lock` does not include `adbc-driver-sqlite`.
**Why it happens:** `uv.lock` is a committed artifact representing the frozen dependency graph. Editing `pyproject.toml` without running `uv lock` produces a divergence.
**How to avoid:** After editing `pyproject.toml` to add the `sqlite` extra, always run `uv lock` and commit the updated lock file alongside `pyproject.toml`.

### Pitfall 5: docs/mkdocs.yml nav not updated
**What goes wrong:** `uv run mkdocs build --strict` fails because `docs/src/guides/sqlite.md` exists but is not listed in `mkdocs.yml`, or vice versa.
**Why it happens:** MkDocs strict mode requires every file in `docs/src/` to appear in the nav (with literate-nav plugin).
**How to avoid:** Add `- SQLite: guides/sqlite.md` under Warehouse Guides in `mkdocs.yml` at the same time as creating `docs/src/guides/sqlite.md`.

### Pitfall 6: In-memory pool-size guard docs omit SQLite's different isolation behavior
**What goes wrong:** Docs copy-paste DuckDB wording ("each pool connection gets an isolated in-memory database"). SQLite in-memory actually shares state across all connections. The error message and guide become misleading.
**Why it happens:** SQLite and DuckDB both reject pool_size > 1 with `:memory:` but for different reasons.
**How to avoid:** SQLite error message and guide should say "in-memory SQLite is shared across connections; pool_size=1 is the required value for `:memory:` mode." Do NOT say "each connection gets an isolated database" (that is the DuckDB behaviour).

---

## Code Examples

### SQLite in-memory connection (verified against adbc_driver_sqlite source)

```python
# Source: arrow.apache.org/adbc/current/python/api/adbc_driver_sqlite.html
import adbc_driver_sqlite.dbapi

with adbc_driver_sqlite.dbapi.connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT 42 AS answer")
        print(cur.fetchone())  # (42,)
```

### How adbc_driver_manager loads the SQLite driver (driver-manager level)

```python
# Source: arrow.apache.org/adbc/current/python/driver_manager.html
# driver= is the path from adbc_driver_sqlite._driver_path()
# entrypoint= is the C-level symbol (validate "adbc_driver_sqlite_init" works)
import adbc_driver_manager.dbapi

conn = adbc_driver_manager.dbapi.connect(
    driver="/path/to/libadbc_driver_sqlite.so",  # from _driver_path()
    entrypoint="adbc_driver_sqlite_init",         # MEDIUM confidence — validate
    db_kwargs={"uri": ":memory:"},
)
```

### Mock pool-factory wiring test (follows TestDatabricksPoolFactory pattern)

```python
# Source: tests/test_pool_factory.py (established mock pattern)
from unittest.mock import MagicMock, patch
from adbc_poolhouse import SQLiteConfig, create_pool

def test_sqlite_pool_factory_wiring() -> None:
    config = SQLiteConfig()  # in-memory, pool_size=1
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

### In-memory integration test (no credentials — runs in CI)

```python
# Pattern: mirrors DuckDB integration tests in test_pool_factory.py
from adbc_poolhouse import SQLiteConfig, create_pool

def test_sqlite_in_memory_query() -> None:
    cfg = SQLiteConfig(database=":memory:", pool_size=1)
    pool = create_pool(cfg)
    try:
        conn = pool.connect()
        cur = conn.cursor()
        cur.execute("SELECT 42 AS answer")
        row = cur.fetchone()
        assert row == (42,)
        cur.close()
        conn.close()
    finally:
        pool.dispose()
        pool._adbc_source.close()
```

### SQLite warehouse guide structure (mirrors duckdb.md)

```markdown
# SQLite guide

Install the SQLite extra:

```bash
pip install adbc-poolhouse[sqlite]
```

## Connection

`SQLiteConfig` supports file-backed and in-memory databases.

For a pool, use a file path. In-memory mode (`pool_size=1` required) connects
to a single shared in-memory database — all connections share the same state,
unlike DuckDB where each connection gets its own empty database.

### File-backed

```python
from adbc_poolhouse import SQLiteConfig, create_pool

config = SQLiteConfig(database="/tmp/warehouse.db")
pool = create_pool(config)
```

### In-memory

`pool_size=1` is required for in-memory databases.

```python
config = SQLiteConfig(database=":memory:")
pool = create_pool(config)
```

## Loading from environment variables

`SQLiteConfig` reads all fields from environment variables with the `SQLITE_` prefix.

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Direct `sqlite3` stdlib | ADBC `adbc-driver-sqlite` | ADBC 0.3.0 (2023) | Type-safe Arrow results; poolable via adbc_driver_manager |
| Separate `adbc_driver_duckdb` package | `duckdb` wheel bundles the ADBC driver | duckdb 0.9.1 | DuckDB handled differently from other PyPI drivers |
| `adbc-driver-sqlite` was conda-forge only | Now on PyPI | mid-2023 | Can install via `pip install adbc-driver-sqlite` |

**Current version:** `adbc-driver-sqlite` 1.10.0 (released January 9, 2026). Minimum requirement spec is `>=1.0.0` to match the pattern of other driver extras.

---

## Open Questions

1. **Entrypoint string: `"adbc_driver_sqlite_init"` vs `"AdbcDriverSqliteInit"`**
   - What we know: The C source exports `AdbcDriverSqliteInit` (PascalCase). The project spec says `"adbc_driver_sqlite_init"` (lowercase snake_case). DuckDB's C function is `duckdb_adbc_init` (lowercase).
   - What's unclear: Whether `adbc_driver_sqlite_init` is a valid alias exported by the SQLite shared library, or whether the spec value is incorrect.
   - Recommendation: Implement as `"adbc_driver_sqlite_init"` per the spec. The integration test `test_sqlite_in_memory_query` MUST exercise the real driver (not mocked). If it raises a symbol error, update to `"AdbcDriverSqliteInit"` and add a code comment explaining the discrepancy. This must be resolved before the plan is closed.

2. **Does SQLite require `_adbc_entrypoint()` at all?**
   - What we know: Other PyPI drivers (Snowflake, BigQuery, PostgreSQL, FlightSQL) return `None` from `_adbc_entrypoint()` and rely entirely on `_driver_path()`. The success criteria explicitly says SQLite must return a non-None value.
   - What's unclear: Whether `adbc_driver_sqlite._driver_path()` + `entrypoint=None` would actually work (it may, if `adbc_driver_manager` can resolve the symbol automatically).
   - Recommendation: Follow the spec. Return `"adbc_driver_sqlite_init"` and validate with a real integration test. If the integration test passes with `None`, the spec may be overly strict — but follow the spec until proven otherwise.

3. **`adbc-driver-sqlite` in `dev` dependency group?**
   - What we know: The `dev` dependency group currently includes `adbc-poolhouse[duckdb]`. Integration tests for SQLite require the driver installed.
   - What's unclear: The requirement says the `sqlite` extra must be in `pyproject.toml` optional-dependencies, but does `dev` need to reference it?
   - Recommendation: Add `adbc-poolhouse[sqlite]` to the `dev` dependency group so integration tests run in the development environment. Run `uv lock` after.

---

## Sources

### Primary (HIGH confidence)
- `src/adbc_poolhouse/_duckdb_config.py` — authoritative template for SQLiteConfig
- `src/adbc_poolhouse/_duckdb_translator.py` — authoritative template for translate_sqlite()
- `src/adbc_poolhouse/_drivers.py` — authoritative `_PYPI_PACKAGES` registration pattern
- `src/adbc_poolhouse/_translators.py` — authoritative dispatch pattern
- `src/adbc_poolhouse/__init__.py` — authoritative export pattern
- `pyproject.toml` — authoritative extras pattern
- `mkdocs.yml` — authoritative nav structure for guides
- `tests/test_pool_factory.py` — authoritative mock wiring test pattern (`TestDatabricksPoolFactory`)
- `tests/test_configs.py` — authoritative config test pattern (`TestDuckDBConfig`)
- `tests/test_translators.py` — authoritative translator test pattern (`TestDuckDBTranslator`)
- [adbc-driver-sqlite on PyPI](https://pypi.org/project/adbc-driver-sqlite/) — version 1.10.0, Jan 2026

### Secondary (MEDIUM confidence)
- [ADBC SQLite Driver docs (current)](https://arrow.apache.org/adbc/current/driver/sqlite.html) — connection parameter `uri`, in-memory shared behaviour
- [adbc_driver_sqlite API reference](https://arrow.apache.org/adbc/current/python/api/adbc_driver_sqlite.html) — `connect(uri=None)` signature, `ConnectionOptions`, `StatementOptions`
- [arrow-adbc GitHub: adbc_driver_sqlite/__init__.py](https://github.com/apache/arrow-adbc/blob/main/python/adbc_driver_sqlite/adbc_driver_sqlite/__init__.py) — `_driver_path()` cascading search; `AdbcDatabase(driver=..., uri=...)` construction; no explicit entrypoint constant

### Tertiary (LOW confidence — requires implementation-time validation)
- [arrow-adbc GitHub: c/driver/sqlite/sqlite.cc](https://github.com/apache/arrow-adbc/tree/main/c/driver/sqlite) — C source exports `AdbcDriverSqliteInit` and `SqliteDriverInit`; `"adbc_driver_sqlite_init"` (spec value) not confirmed as exported symbol

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `adbc-driver-sqlite` is the obvious and only PyPI SQLite ADBC driver; version confirmed
- Architecture patterns: HIGH — all patterns (config, translator, driver registration, dispatch, export) are established in codebase and directly applicable
- Translator kwargs: HIGH — `uri` key confirmed from official ADBC driver source
- Entrypoint string: MEDIUM — spec says `"adbc_driver_sqlite_init"`, C exports `AdbcDriverSqliteInit`; requires integration-time validation
- Pitfalls: HIGH — derived directly from existing codebase patterns and driver documentation
- Docs pattern: HIGH — `duckdb.md` guide is the exact template; mkdocs.yml pattern is clear

**Research date:** 2026-03-01
**Valid until:** 2026-04-01 (stable library; entrypoint question resolved at implementation time)
