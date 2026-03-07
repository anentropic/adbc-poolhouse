# Phase 5: Pool Factory and DuckDB Integration - Research

**Researched:** 2026-02-25
**Domain:** SQLAlchemy QueuePool + ADBC driver integration; custom exception hierarchy; Arrow allocator lifecycle
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**create_pool() signature:**
- Flat keyword args: `create_pool(config, pool_size=5, max_overflow=3, timeout=30, recycle=3600, pre_ping=False)`
- Default values live directly in the function signature (visible in docstring, IDE autocomplete, `help()`)
- Returns `sqlalchemy.pool.QueuePool` — raw, no wrapper
- Return type annotated as `sqlalchemy.pool.QueuePool`

**Validation strategy:**
- Validation lives in `DuckDBConfig.__init__` / `__post_init__` — fail at object construction, earliest possible point
- Raise **custom exceptions**, not built-in exception types directly — e.g. `ConfigurationError`, not `ValueError`
- Exception hierarchy: single base `PoolhouseError(Exception)` → specific errors like `ConfigurationError(PoolhouseError)`
- **Note for planner:** success criteria reference `ValueError` — resolve by making `ConfigurationError` inherit from both `PoolhouseError` and `ValueError`, satisfying both the custom exception rule and the test expectation
- Validated eagerly in `DuckDBConfig`:
  - `database=":memory:"` combined with `pool_size > 1` (the `:memory:` conflict rule)
  - `pool_size > 0` (reject zero or negative)
  - `max_overflow >= 0` (reject negative)
  - `timeout > 0` (reject zero or negative)
  - `recycle > 0` (reject zero or negative)
  - `database` is a non-empty string (reject empty string or None)
- Error messages include the invalid value: e.g. `"pool_size must be > 0, got -1"`

**Arrow context cleanup:**
- Release on **checkin + error/close** — any path that ends a connection lifecycle must release the allocator (no leak possible regardless of failure mode)
- Memory leak validation test: track allocator ref count across N checkout/query/checkin cycles; verify count returns to baseline after all connections checked in
- Cleanup ownership (connection wrapper vs pool event listeners): **Claude's discretion**

**Public API surface:**
- Export from top-level `adbc_poolhouse`: `create_pool`, `DuckDBConfig`, `PoolhouseError`, `ConfigurationError`, and any type aliases/protocols useful for consumer type annotations
- Use explicit `__all__` in `__init__.py` to define the public contract
- Keep surface minimal — nothing beyond the above unless clearly needed
- Pool management helpers (e.g. `dispose_pool()`): **Claude's discretion** — only if they meaningfully improve ergonomics over calling `pool.dispose()` directly

### Claude's Discretion
- Where exactly cleanup is wired (connection wrapper vs event listeners)
- Whether any pool management helpers are added
- Type alias and protocol names and structure

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| POOL-01 | `create_pool(config) -> QueuePool` — accepts any supported config model, returns a ready-to-use `sqlalchemy.pool.QueuePool` | Official ADBC recipe pattern confirmed: `source.adbc_clone` as creator; full end-to-end tested locally |
| POOL-02 | Default pool settings: `pool_size=5`, `max_overflow=3`, `timeout=30`, `pool_pre_ping=False`, `recycle=3600` | `QueuePool.__init__` accepts `pool_size`, `max_overflow`, `timeout`; `recycle` and `pre_ping` pass via `**kw` to `Pool.__init__` — verified |
| POOL-03 | Consumer can override any pool setting by passing kwargs to `create_pool(config, pool_size=10, ...)` | kwargs pattern: override config field values; tested end-to-end |
| POOL-04 | Arrow memory `reset` event listener registered on pool creation — releases Arrow allocator contexts on connection checkin | `sqlalchemy.event.listen(pool, 'reset', fn)` fires before checkin; tested that `_cursors` weakref set on ADBC Connection holds open cursors; cursor.close() releases Arrow stream memory |
| POOL-05 | No global state — the library creates no module-level singletons | Enforced by design: `create_pool` is a function definition, not a call; no module-level pool/connection objects |
| TEST-01 | DuckDB end-to-end integration tests: pool creation, connection checkout, query execution, pool disposal | Tested locally: `DuckDBConfig(database='/tmp/test.db')` → `create_pool()` → `pool.connect()` → `cursor.execute()` → `fetchone()` → `conn.close()` → `pool.dispose()` all work |
| TEST-02 | `DuckDBConfig(database=":memory:", pool_size=2)` raises `ValueError` (isolation validator test) | `pydantic.ValidationError` IS a `ValueError` (confirmed: `issubclass(ValidationError, ValueError)` is True); existing test in `test_configs.py` covers this; Phase 5 test file consolidates it |
| TEST-07 | Memory leak validation test for the Arrow `reset` event listener — confirms Arrow allocator contexts are released on connection checkin | Tested: `_cursors` weakref set is non-empty when cursor not closed before checkin; `reset` event listener closes all open cursors; verify 0 open cursors after N checkout/checkin cycles |
</phase_requirements>

---

## Summary

Phase 5 wires together all the components built in Phases 1-4 (config, translator, driver detection) into the public `create_pool(config)` factory function. The core architecture follows the official ADBC recipe: a "source" connection is created using `create_adbc_connection()`, then `source.adbc_clone` is passed as the `creator` callable to `sqlalchemy.pool.QueuePool`. Each pool checkout calls `adbc_clone()` which creates a new connection sharing the same underlying `_SharedDatabase` (via reference counting), meaning the source connection must stay alive while the pool may still create new connections.

Arrow memory management is handled by registering a `reset` event listener on the pool. The ADBC `Connection` object holds open cursors in a `_cursors: weakref.WeakSet[Cursor]` attribute. Consumers who call `cursor.execute()` and return the connection to the pool without closing the cursor would accumulate open Arrow record batch readers. The `reset` event fires before `checkin` on every connection return path; the listener iterates `dbapi_conn._cursors` and closes any unclosed cursors, releasing their Arrow streams. Tested end-to-end with DuckDB.

The custom exception hierarchy (`PoolhouseError → ConfigurationError`) is straightforward: `ConfigurationError(PoolhouseError, ValueError)` satisfies the custom exception rule AND the `raises ValueError` test expectation simultaneously because pydantic's `ValidationError` itself inherits from `ValueError`, and pydantic wraps any `ValueError` subclass raised inside a `model_validator` in `ValidationError`. Existing `DuckDBConfig` validation (`:memory:` + `pool_size > 1`) already raises pydantic `ValidationError` which is a `ValueError`, so TEST-02 is already satisfied by the existing code — Phase 5 only needs to change the inner exception type from bare `ValueError` to `ConfigurationError`.

**Primary recommendation:** Implement `create_pool()` in `src/adbc_poolhouse/_pool_factory.py` using the `source.adbc_clone` pattern; add `_adbc_entrypoint()` method to `BaseWarehouseConfig` (returns `None`) with `DuckDBConfig` overriding to return `'duckdb_adbc_init'`; register `reset` event listener for cursor cleanup; add `_exceptions.py` with `PoolhouseError` and `ConfigurationError`; update `DuckDBConfig.check_memory_pool_size` to raise `ConfigurationError`; update `__init__.py` `__all__`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlalchemy` | `>=2.0.0` (already in deps) | `QueuePool` class and pool event system | Already a project dependency; the only stable standalone pool implementation with ADBC support |
| `adbc-driver-manager` | `>=1.0.0` (already in deps) | `adbc_driver_manager.dbapi.Connection.adbc_clone()` — the pool creator callable | Required for ADBC connections; `adbc_clone()` is the official ADBC-to-pool bridge method |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sqlalchemy.event` | (bundled with sqlalchemy) | `event.listen(pool, 'reset', fn)` — register cleanup listeners | For Arrow allocator cleanup on checkin (POOL-04) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `source.adbc_clone` as creator | `functools.partial(create_adbc_connection, ...)` | `adbc_clone` shares `_SharedDatabase` (ref-counted, avoids re-init overhead); `partial` would create fresh connections each time — loses resource sharing |
| `reset` event for cleanup | `checkin` event for cleanup | `reset` fires before `checkin` and also on invalidation/error paths; `checkin` can receive `None` conn on invalidation; `reset` is more complete |
| `ConfigurationError(PoolhouseError, ValueError)` | `ValueError` directly | Custom exception satisfies library rule; dual inheritance means `isinstance(e, ValueError)` is True for backward compat |

**Installation:** All dependencies already declared in `pyproject.toml`. No new runtime deps for this phase.

---

## Architecture Patterns

### Recommended Project Structure

New files for Phase 5:
```
src/adbc_poolhouse/
├── _exceptions.py          # PoolhouseError, ConfigurationError (NEW)
├── _pool_factory.py        # create_pool() implementation (NEW)
├── _base_config.py         # add _adbc_entrypoint() method (MODIFY)
├── _duckdb_config.py       # raise ConfigurationError, add _adbc_entrypoint() (MODIFY)
├── __init__.py             # export create_pool, PoolhouseError, ConfigurationError (MODIFY)
└── ... (existing files unchanged)

tests/
├── test_pool_factory.py    # TEST-01, TEST-07 (NEW)
└── test_configs.py         # TEST-02 already covered; minor update if needed (MODIFY)
```

### Pattern 1: ADBC Source + adbc_clone Creator
**What:** Create one "source" ADBC connection, then use `source.adbc_clone` as the `QueuePool` creator callable. Each pool checkout calls `adbc_clone()` which opens a new `AdbcConnection` sharing the same underlying `AdbcDatabase` via `_SharedDatabase` reference counting.
**When to use:** Always — this is the official ADBC pattern for connection pooling.

```python
# Source: https://github.com/apache/arrow-adbc/blob/main/docs/source/python/recipe/postgresql_pool.py
# Verified working with DuckDB locally (2026-02-25)

source = create_adbc_connection(driver_path, kwargs, entrypoint=entrypoint)
pool = sqlalchemy.pool.QueuePool(
    source.adbc_clone,          # creator callable — each call opens a new cloned connection
    pool_size=pool_size,
    max_overflow=max_overflow,
    timeout=timeout,
    recycle=recycle,            # passed via **kw to Pool.__init__
    pre_ping=pre_ping,          # passed via **kw to Pool.__init__
)
pool._adbc_source = source      # keep source alive; attach for lifecycle management
```

**Critical:** `source` must stay alive as long as the pool may create new connections. The pool is lazy — connections are created on first checkout. If `source.close()` is called before any checkout, the `_SharedDatabase` refcount drops to 0, closing the underlying `AdbcDatabase`; subsequent checkouts fail with `INVALID_ARGUMENT: Database is not initialized`. Store `source` as `pool._adbc_source` and close it after `pool.dispose()`.

### Pattern 2: Reset Event for Arrow Allocator Cleanup
**What:** Register a `reset` event listener on the pool that closes any open cursors on the returning ADBC connection. Open cursors hold Arrow record batch readers in memory.
**When to use:** Always — register during `create_pool()`.

```python
# Source: Verified pattern from local testing (2026-02-25)
# sqlalchemy docs: https://docs.sqlalchemy.org/en/20/core/pooling.html#pool-events

from sqlalchemy import event

def _release_arrow_allocators(
    dbapi_conn: object,
    connection_record: object,
    reset_state: object,
) -> None:
    """Close any open cursors to release Arrow record batch readers."""
    if dbapi_conn is None:
        return
    for cur in list(getattr(dbapi_conn, '_cursors', [])):
        if not getattr(cur, '_closed', True):
            try:
                cur.close()
            except Exception:
                pass

event.listen(pool, 'reset', _release_arrow_allocators)
```

**Why `reset` not `checkin`:** The `reset` event fires on ALL connection return paths (normal checkin, invalidation, error). The `checkin` event receives `None` as `dbapi_conn` when the connection is invalidated. `reset` is the correct hook for pre-checkin cleanup.

### Pattern 3: DuckDB Entrypoint Resolution
**What:** DuckDB requires `entrypoint='duckdb_adbc_init'` in `create_adbc_connection()`. No other driver needs an entrypoint. Add `_adbc_entrypoint()` method to config classes.
**When to use:** During `create_pool()` execution.

```python
# In _base_config.py (BaseWarehouseConfig):
def _adbc_entrypoint(self) -> str | None:
    """Return the ADBC entry-point symbol, or None if not required."""
    return None

# In _duckdb_config.py (DuckDBConfig):
def _adbc_entrypoint(self) -> str | None:
    return "duckdb_adbc_init"
```

Then in `_pool_factory.py`:
```python
entrypoint = config._adbc_entrypoint()  # None for all except DuckDB
source = create_adbc_connection(driver_path, kwargs, entrypoint=entrypoint)
```

### Pattern 4: Custom Exception Hierarchy
**What:** Define `PoolhouseError(Exception)` as the library base, `ConfigurationError(PoolhouseError, ValueError)` for config validation failures.
**When to use:** All library-raised exceptions must be `PoolhouseError` subclasses.

```python
# Source: CONTEXT.md decision; verified pydantic behavior 2026-02-25

# src/adbc_poolhouse/_exceptions.py
class PoolhouseError(Exception):
    """Base exception for all adbc-poolhouse errors."""

class ConfigurationError(PoolhouseError, ValueError):
    """
    Raised when a config model has invalid field values.

    Inherits from both PoolhouseError (library hierarchy) and ValueError
    (pydantic model_validator compatibility). When raised inside a pydantic
    @model_validator, pydantic wraps it in ValidationError (which itself
    inherits from ValueError), satisfying 'raises ValueError' test expectations.
    """
```

Then update `DuckDBConfig.check_memory_pool_size` to raise `ConfigurationError` instead of bare `ValueError`.

### Pattern 5: create_pool() Parameter Precedence
**What:** `create_pool()` kwargs override config field values. When no kwarg is given, the config's field value is used (which already reflects env var loading, pydantic defaults, and per-config overrides like `DuckDBConfig.pool_size=1`).

```python
def create_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> QueuePool:
    ...
```

**Important nuance:** The function signature defaults (`pool_size=5`, etc.) are the create_pool defaults. When the user passes `DuckDBConfig()` (which has `pool_size=1`), the create_pool default of 5 is used unless the user also passes `pool_size=...` to create_pool. This is the CONTEXT.md locked decision — "Default pool settings: pool_size=5, max_overflow=3, ..." live in the function signature.

This is a behavior change from "use config.pool_size": the create_pool function defaults always apply when no kwarg is given, regardless of config field values. The config's pool_size field is only used if the consumer explicitly reads it and passes it: `create_pool(cfg, pool_size=cfg.pool_size)`.

**Re-read CONTEXT.md locked decision:** "Default values live directly in the function signature" — this means create_pool has its OWN defaults, independent of config defaults. Config pool fields (from BaseWarehouseConfig) remain for consumers who use them, but create_pool ignores them unless passed explicitly.

### Anti-Patterns to Avoid
- **Module-level pool/connection creation:** Never call `create_pool()` or `create_adbc_connection()` at module import time — violates POOL-05
- **Closing source before pool is fully populated:** Source must stay alive; close only after `pool.dispose()`
- **Using `checkin` event instead of `reset`:** `checkin` receives `None` for invalidated connections; `reset` is safer
- **Passing `pre_ping=True`:** Pre-ping silently no-ops on standalone `QueuePool` without a SQLAlchemy dialect (locked decision from prior phases)
- **Bare `except Exception` swallowing in cleanup:** Use `try/except Exception: pass` ONLY in the cursor cleanup listener (swallowing errors during cleanup is intentional)

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Connection pool lifecycle | Custom thread-safe pool class | `sqlalchemy.pool.QueuePool` | SQLAlchemy handles thread safety, overflow, timeouts, recycle, events — all edge cases handled |
| Cursor cleanup on checkin | Custom `__del__` on wrapped connections | `event.listen(pool, 'reset', fn)` | Pool event fires synchronously on every return path; `__del__` timing is non-deterministic |
| Connection ref-counting | Manual reference counting | `adbc_driver_manager._SharedDatabase` | Already implemented in ADBC; `adbc_clone()` handles increment/decrement automatically |

**Key insight:** `sqlalchemy.pool.QueuePool` combined with `adbc_clone` is the complete solution. The only custom code needed is the `reset` event listener (7 lines) and the `create_pool` factory (25-30 lines). Everything else is already built.

---

## Common Pitfalls

### Pitfall 1: Source Connection Closed Too Early
**What goes wrong:** `source.close()` called before pool checkouts occur; subsequent `adbc_clone()` calls fail with `INVALID_ARGUMENT: Database is not initialized`
**Why it happens:** `_SharedDatabase` refcount drops to 0 when source closes before any clone is made (pool is lazy — no checkouts yet)
**How to avoid:** Attach source to pool: `pool._adbc_source = source`. Never close source until after `pool.dispose()`.
**Warning signs:** `ProgrammingError: INVALID_ARGUMENT: [Driver Manager] Database is not initialized` on first `pool.connect()` call

### Pitfall 2: Using `checkin` Event Instead of `reset`
**What goes wrong:** `checkin` listener receives `dbapi_conn=None` when connection is invalidated; `None._cursors` raises `AttributeError`
**Why it happens:** Pool invalidates connections on errors; `checkin` fires with `None` for invalidated connections
**How to avoid:** Use `reset` event; guard with `if dbapi_conn is None: return`
**Warning signs:** `AttributeError: 'NoneType' object has no attribute '_cursors'` in checkin listener

### Pitfall 3: pydantic ValidationError Wrapping
**What goes wrong:** `ConfigurationError` raised inside `@model_validator` gets wrapped in `pydantic.ValidationError`; tests that check `isinstance(e, ConfigurationError)` fail
**Why it happens:** pydantic catches `ValueError` subclasses inside validators and wraps them in `ValidationError`
**How to avoid:** Tests should use `pytest.raises(ValueError)` (works because `ValidationError` IS a `ValueError`); or use `pytest.raises(ValidationError)`. Do NOT use `pytest.raises(ConfigurationError)` when the validator is inside pydantic
**Warning signs:** Test `pytest.raises(ConfigurationError)` fails even though `ConfigurationError` was raised

### Pitfall 4: recycle and pre_ping Not on QueuePool Directly
**What goes wrong:** `QueuePool(creator, recycle=3600, pre_ping=False)` — these are NOT `QueuePool.__init__` params; they're `Pool.__init__` params
**Why it happens:** `QueuePool.__init__` signature is `(creator, pool_size, max_overflow, timeout, use_lifo, **kw)`; `recycle` and `pre_ping` live in `Pool.__init__`
**How to avoid:** Pass as `**kw` to `QueuePool()` — they flow through correctly (verified locally)
**Warning signs:** `TypeError: QueuePool.__init__() got an unexpected keyword argument` — this does NOT happen (tested); but be aware they are `**kw`, not direct params

### Pitfall 5: DuckDB Entrypoint Missing
**What goes wrong:** `create_adbc_connection(driver_path, kwargs)` without `entrypoint='duckdb_adbc_init'` — DuckDB connections fail
**Why it happens:** DuckDB's shared library requires the `duckdb_adbc_init` init function to be called; without the entrypoint kwarg, ADBC can't initialize the driver
**How to avoid:** Always pass `entrypoint=config._adbc_entrypoint()` in create_pool
**Warning signs:** Driver loading error or silent failure when connecting to DuckDB

### Pitfall 6: ruff TCH001 on Config Import in _pool_factory.py
**What goes wrong:** `from adbc_poolhouse._base_config import WarehouseConfig` at module level triggers ruff TCH001 (move to TYPE_CHECKING block)
**Why it happens:** `WarehouseConfig` is a Protocol used only as type annotation; ruff correctly suggests lazy import
**How to avoid:** Use `from __future__ import annotations` + move config imports to `TYPE_CHECKING` block (same pattern as `_translators.py`)
**Warning signs:** ruff TCH001 error on pre-commit; basedpyright errors if moved incorrectly

---

## Code Examples

### Complete create_pool() Implementation Skeleton

```python
# src/adbc_poolhouse/_pool_factory.py
# Source: Verified pattern - Apache ADBC recipe + local testing 2026-02-25

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy.pool
from sqlalchemy import event

from adbc_poolhouse._driver_api import create_adbc_connection
from adbc_poolhouse._drivers import resolve_driver
from adbc_poolhouse._translators import translate_config

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig


def create_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool:
    """
    Create a SQLAlchemy QueuePool backed by an ADBC warehouse driver.
    ...
    """
    driver_path = resolve_driver(config)
    kwargs = translate_config(config)
    entrypoint = config._adbc_entrypoint()

    source = create_adbc_connection(driver_path, kwargs, entrypoint=entrypoint)

    pool = sqlalchemy.pool.QueuePool(
        source.adbc_clone,  # type: ignore[arg-type]  -- ADBC Connection satisfies DBAPIConnection structurally
        pool_size=pool_size,
        max_overflow=max_overflow,
        timeout=timeout,
        recycle=recycle,
        pre_ping=pre_ping,
    )

    pool._adbc_source = source  # type: ignore[attr-defined]  -- keep source alive

    event.listen(pool, 'reset', _release_arrow_allocators)

    return pool


def _release_arrow_allocators(
    dbapi_conn: object,
    connection_record: object,
    reset_state: object,
) -> None:
    """Release Arrow allocator contexts by closing open cursors on connection return."""
    if dbapi_conn is None:
        return
    for cur in list(getattr(dbapi_conn, '_cursors', [])):
        if not getattr(cur, '_closed', True):
            try:
                cur.close()
            except Exception:  # noqa: BLE001
                pass
```

### Exception Hierarchy

```python
# src/adbc_poolhouse/_exceptions.py

class PoolhouseError(Exception):
    """
    Base exception for all adbc-poolhouse errors.

    All library-specific exceptions inherit from this class.
    """


class ConfigurationError(PoolhouseError, ValueError):
    """
    Raised when a config model contains invalid field values.

    Inherits from both PoolhouseError (library hierarchy) and ValueError
    (pydantic model_validator compatibility). When raised inside a pydantic
    @model_validator, pydantic wraps it in ValidationError — which itself
    inherits from ValueError — satisfying 'raises ValueError' test expectations.

    Example:
        DuckDBConfig(database=":memory:", pool_size=2)
        # raises ConfigurationError (wrapped in pydantic ValidationError)
    """
```

### DuckDBConfig Update

```python
# In _duckdb_config.py — update check_memory_pool_size and add _adbc_entrypoint

from adbc_poolhouse._exceptions import ConfigurationError

@model_validator(mode="after")
def check_memory_pool_size(self) -> Self:
    if self.database == ":memory:" and self.pool_size > 1:
        raise ConfigurationError(
            'pool_size > 1 with database=":memory:" will give each pool '
            "connection an isolated in-memory database ..."
        )
    return self

def _adbc_entrypoint(self) -> str | None:
    return "duckdb_adbc_init"
```

### Test Pattern: DuckDB End-to-End (TEST-01)

```python
# tests/test_pool_factory.py

import pytest
import sqlalchemy.pool

from adbc_poolhouse import create_pool, DuckDBConfig


class TestCreatePoolDuckDB:
    def test_create_pool_returns_queuepool(self, tmp_path) -> None:
        cfg = DuckDBConfig(database=str(tmp_path / "test.db"))
        pool = create_pool(cfg)
        assert isinstance(pool, sqlalchemy.pool.QueuePool)
        pool.dispose()
        pool._adbc_source.close()

    def test_checkout_query_checkin_dispose(self, tmp_path) -> None:
        cfg = DuckDBConfig(database=str(tmp_path / "test.db"))
        pool = create_pool(cfg)
        conn = pool.connect()
        cur = conn.cursor()
        cur.execute("SELECT 42 AS answer")
        row = cur.fetchone()
        assert row == (42,)
        conn.close()
        assert pool.checkedin() == 1
        pool.dispose()
        pool._adbc_source.close()

    def test_pool_size_override(self, tmp_path) -> None:
        cfg = DuckDBConfig(database=str(tmp_path / "test.db"))
        pool = create_pool(cfg, pool_size=10, recycle=7200)
        assert pool.size() == 10
        pool.dispose()
        pool._adbc_source.close()
```

### Test Pattern: Memory Leak Validation (TEST-07)

```python
class TestArrowAllocatorCleanup:
    def test_no_cursor_accumulation_after_checkin_cycles(self, tmp_path) -> None:
        cfg = DuckDBConfig(database=str(tmp_path / "leak_test.db"))
        pool = create_pool(cfg)

        N = 10
        for i in range(N):
            conn = pool.connect()
            cur = conn.cursor()
            cur.execute(f"SELECT {i} AS val")
            # Intentionally do NOT close cursor before checkin
            conn.close()  # reset event listener should close cursor

        # Verify pool is healthy (no leaked cursors blocked connections)
        conn = pool.connect()
        cur = conn.cursor()
        cur.execute("SELECT 999")
        assert cur.fetchone() == (999,)
        conn.close()

        pool.dispose()
        pool._adbc_source.close()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual connection lifecycle | `adbc_clone` + `QueuePool` | ADBC recipe documented mid-2024 | Official pattern confirmed; no need to subclass QueuePool |
| `checkin` event for cleanup | `reset` event for cleanup | SQLAlchemy 2.0 | `reset` fires on all return paths including invalidation |
| Module-level singleton pools | Per-call `create_pool()` factory | Library design (Phase 5) | Consumer owns pool lifetime; no global state |

**Deprecated/outdated:**
- `reset_agent` concept: was an internal SQLAlchemy mechanism (removed in SQLAlchemy 2.x) that is no longer relevant — the `reset` pool event is the correct modern mechanism

---

## Open Questions

1. **Source connection disposal ergonomics**
   - What we know: `pool._adbc_source` must be closed after `pool.dispose()`. Attaching source as a pool attribute is functional but uses a private attribute name.
   - What's unclear: Should `create_pool` subclass `QueuePool` to add a proper `dispose()` override that also closes source? Or is storing on the pool attribute sufficient given POOL-05 (no wrapper type)?
   - Recommendation: Store as `pool._adbc_source` (per Claude's discretion in CONTEXT.md). Document the lifecycle in `create_pool()` docstring. Avoid subclassing — CONTEXT.md says "Returns `sqlalchemy.pool.QueuePool` — raw, no wrapper".

2. **Additional DuckDBConfig validators (ConfigurationError for pool_size, timeout, etc.)**
   - What we know: CONTEXT.md says validate `pool_size > 0`, `max_overflow >= 0`, `timeout > 0`, `recycle > 0`, `database` non-empty in DuckDBConfig
   - What's unclear: Do other config classes also need these validators? `BaseWarehouseConfig` could host them, or each config can have them.
   - Recommendation: Add to `BaseWarehouseConfig` as `@field_validator` for each pool tuning field — they apply uniformly across all config types. This is more DRY than repeating in each subclass.

3. **`_adbc_entrypoint()` on WarehouseConfig Protocol**
   - What we know: `WarehouseConfig` Protocol currently has `pool_size`, `max_overflow`, `timeout`, `recycle` only
   - What's unclear: Should `_adbc_entrypoint()` be added to the Protocol? It's an internal method (underscore prefix), so it may not belong in the public-facing Protocol.
   - Recommendation: Add `_adbc_entrypoint` to `WarehouseConfig` Protocol as a method signature (it's already internal-prefixed and used internally by create_pool). This allows `create_pool(config: WarehouseConfig)` to call `config._adbc_entrypoint()` without type errors.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` (no `[tool.pytest.ini_options]` section — uses defaults) |
| Quick run command | `uv run pytest tests/test_pool_factory.py -x` |
| Full suite command | `uv run pytest tests/ -x` |
| Estimated runtime | ~1-2 seconds (DuckDB in-memory; no network) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| POOL-01 | `create_pool(DuckDBConfig(...))` returns `QueuePool` instance | integration | `uv run pytest tests/test_pool_factory.py::TestCreatePoolDuckDB::test_create_pool_returns_queuepool -x` | ❌ Wave 0 gap |
| POOL-02 | Default pool settings applied (pool_size=5, max_overflow=3, timeout=30, pre_ping=False, recycle=3600) | integration | `uv run pytest tests/test_pool_factory.py::TestCreatePoolDuckDB::test_default_pool_settings -x` | ❌ Wave 0 gap |
| POOL-03 | `create_pool(cfg, pool_size=10, recycle=7200)` overrides correctly | integration | `uv run pytest tests/test_pool_factory.py::TestCreatePoolDuckDB::test_pool_size_override -x` | ❌ Wave 0 gap |
| POOL-04 | Arrow allocator released on checkin (reset event fires, cursors closed) | integration | `uv run pytest tests/test_pool_factory.py::TestArrowAllocatorCleanup -x` | ❌ Wave 0 gap |
| POOL-05 | `import adbc_poolhouse` creates no pool or connection | unit | `uv run pytest tests/test_pool_factory.py::TestNoGlobalState -x` | ❌ Wave 0 gap |
| TEST-01 | DuckDB end-to-end: checkout → query → checkin → dispose | integration | `uv run pytest tests/test_pool_factory.py::TestCreatePoolDuckDB -x` | ❌ Wave 0 gap |
| TEST-02 | `DuckDBConfig(database=":memory:", pool_size=2)` raises `ValueError` | unit | `uv run pytest tests/test_configs.py::TestDuckDBConfig::test_memory_pool_size_validator_fires -x` | ✅ yes (existing test; may need `ConfigurationError` update) |
| TEST-07 | N checkout/checkin cycles with unclosed cursors: no cursor accumulation | integration | `uv run pytest tests/test_pool_factory.py::TestArrowAllocatorCleanup::test_no_cursor_accumulation_after_checkin_cycles -x` | ❌ Wave 0 gap |

### Nyquist Sampling Rate
- **Minimum sample interval:** After every committed task → run: `uv run pytest tests/test_pool_factory.py -x`
- **Full suite trigger:** Before merging final task of any plan wave
- **Phase-complete gate:** Full suite green before `/gsd:verify-work` runs
- **Estimated feedback latency per task:** ~1-2 seconds

### Wave 0 Gaps (must be created before implementation)
- [ ] `tests/test_pool_factory.py` — covers POOL-01, POOL-02, POOL-03, POOL-04, POOL-05, TEST-01, TEST-07 (does not exist; must be created in Wave 0)

*(TEST-02 existing coverage: `tests/test_configs.py::TestDuckDBConfig::test_memory_pool_size_validator_fires` already tests this behavior — Wave 0 should update the assertion to match the `ConfigurationError` hierarchy if needed, but the test still passes because `ValidationError(ValueError)` satisfies `pytest.raises(ValidationError)`)*

---

## Sources

### Primary (HIGH confidence)
- Official ADBC recipe: https://github.com/apache/arrow-adbc/blob/main/docs/source/python/recipe/postgresql_pool.py — `adbc_clone` as QueuePool creator (confirmed working with DuckDB locally)
- SQLAlchemy pool events: https://docs.sqlalchemy.org/en/20/core/pooling.html — `reset` vs `checkin` event behavior, `checkin` receives None on invalidation
- `adbc_driver_manager.dbapi` source (local): `Connection.adbc_clone()` implementation, `_SharedDatabase` reference counting, `_cursors: WeakSet` on Connection — all verified by reading source via `inspect.getsource()`
- `sqlalchemy.pool.QueuePool.__init__` source (local): `pool_size`, `max_overflow`, `timeout` are direct params; `recycle`, `pre_ping` pass as `**kw` to `Pool.__init__` — verified
- pydantic 2.x behavior: `ValidationError` inherits from `ValueError` (`issubclass(ValidationError, ValueError)` is True) — verified locally

### Secondary (MEDIUM confidence)
- ADBC issue #2079: https://github.com/apache/arrow-adbc/issues/2079 — SQLAlchemy integration discussion; confirms full dialect required for ORM; standalone QueuePool works for non-ORM use
- ADBC issue #1893: https://github.com/apache/arrow-adbc/issues/1893 — cursor lifetime and Arrow record batch reader; confirms cursors must stay alive during batch consumption; closing cursor releases stream

### Tertiary (LOW confidence)
- None — all critical claims verified against source code or official docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `adbc_clone` + `QueuePool` pattern verified against official ADBC recipe and tested locally with DuckDB
- Architecture: HIGH — `reset` event, `_cursors` cleanup, source lifecycle all verified by reading ADBC source and running live tests
- Pitfalls: HIGH — each pitfall was discovered by testing (e.g., source closed too early, `checkin` vs `reset`, pydantic wrapping)

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable libraries; ADBC and SQLAlchemy APIs unlikely to change)
