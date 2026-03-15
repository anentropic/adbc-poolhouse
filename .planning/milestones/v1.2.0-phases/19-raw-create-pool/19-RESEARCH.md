# Phase 19: Raw create_pool Overload - Research

**Researched:** 2026-03-15
**Domain:** Python typing overloads, ADBC driver API, pool factory refactoring
**Confidence:** HIGH

## Summary

Phase 19 adds three overloaded signatures to `create_pool()` and `managed_pool()`, enabling advanced users to bypass config objects and pass raw driver arguments directly. The two raw paths (native `driver_path` and Python `dbapi_module`) map directly to the two existing branches in `create_adbc_connection()`, so no new driver plumbing is needed. The phase also cleans up a redundant `_foundry_name_to_install` dict and generalizes the NOT_FOUND error message.

The `@overload` pattern has been validated against basedpyright strict mode. The key architectural finding is that `create_pool()` and `managed_pool()` should share a private `_create_pool_impl()` function to avoid type-ignore noise when `managed_pool()` forwards to `create_pool()` through overloaded signatures. All four invalid-call patterns (no args, both raw paths, config + raw, pool-tuning-only) are caught at type-check time by basedpyright's overload resolution.

**Primary recommendation:** Extract pool creation logic into `_create_pool_impl()`, add three `@overload` signatures to both `create_pool()` and `managed_pool()`, remove `_foundry_name_to_install`, and update docs/docstrings per CLAUDE.md quality gate.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Single `create_pool()` with `@overload` -- three overloads:
  1. `create_pool(config: WarehouseConfig, *, pool_size=5, ...)` -- existing config path, config is positional
  2. `create_pool(*, driver_path: str, db_kwargs: dict[str, str], entrypoint: str | None = None, pool_size=5, ...)` -- native ADBC driver, all keyword-only
  3. `create_pool(*, dbapi_module: str, db_kwargs: dict[str, str], pool_size=5, ...)` -- Python dbapi module, all keyword-only
- `driver_path` and `dbapi_module` are mutually exclusive -- different overloads, not co-existing kwargs
- Pool tuning params (pool_size, max_overflow, timeout, recycle, pre_ping) shared across all three overloads with same defaults
- `entrypoint` only available on `driver_path` overload (it's a native ADBC concept)
- `managed_pool()` gets the same three overloads as `create_pool()`; it forwards args to `create_pool()` -- minimal extra code
- Pure EAFP for argument values -- if driver_path is wrong, ADBC raises; if db_kwargs has bad keys, the driver raises
- TypeError if both `driver_path` and `dbapi_module` provided (mutual exclusivity enforcement)
- TypeError if none of config / driver_path / dbapi_module provided
- Remove `_foundry_name_to_install` dict from `_driver_api.py` -- it's a pure 1:1 mapping, completely redundant
- Generalize the NOT_FOUND error handling in `create_adbc_connection()`: any NOT_FOUND from adbc_driver_manager gets a clear ImportError regardless of whether the driver_path is a Foundry short name or a file path
- Error message: `"ADBC driver '{driver_path}' not found. See: https://docs.adbc-drivers.org/"` -- no Foundry-specific `dbc install` hint

### Claude's Discretion
- Implementation of the `@overload` dispatch in the actual function body (how to distinguish which overload was called at runtime)
- Whether `create_adbc_connection()` signature needs updating to reflect mutual exclusivity or stays as-is internally
- Test structure for the new overloads

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `typing.overload` | stdlib | Static overload signatures | Only way to express multiple call signatures for basedpyright strict |
| `sqlalchemy.pool.QueuePool` | >=2.0.0 | Return type of all create_pool overloads | Already used -- no change |
| `adbc_driver_manager.dbapi` | >=1.8.0 | Connection creation for both raw paths | Already used in `_driver_api.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `contextlib` | stdlib | `@contextmanager` for `managed_pool()` | Already used -- no change |
| `importlib` | stdlib | Dynamic module import for `dbapi_module` path | Already used in `create_adbc_connection()` |

No new dependencies are needed for this phase.

## Architecture Patterns

### Recommended Refactoring Structure

```
src/adbc_poolhouse/
├── _pool_factory.py     # Modified: overloads + _create_pool_impl()
├── _driver_api.py       # Modified: remove _foundry_name_to_install, simplify NOT_FOUND
├── _base_config.py      # No changes
└── __init__.py           # No changes (create_pool/managed_pool already exported)
```

### Pattern 1: Shared Implementation Helper

**What:** Extract the actual pool creation logic into a private `_create_pool_impl()` that accepts all parameters explicitly (no overloading). Both `create_pool()` and `managed_pool()` call this helper.

**Why:** When `managed_pool()` needs to forward to `create_pool()`, the overloaded call can't satisfy basedpyright because the implementation's `None`-defaulted parameters don't match any single overload. A shared private helper avoids this entirely.

**Validated with basedpyright strict:** 0 errors with this pattern.

**Example:**
```python
# Source: validated via basedpyright strict on this project
from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, overload

import sqlalchemy.pool
from sqlalchemy import event

from adbc_poolhouse._driver_api import create_adbc_connection

if TYPE_CHECKING:
    import collections.abc
    from adbc_poolhouse._base_config import WarehouseConfig


def _create_pool_impl(
    config: WarehouseConfig | None,
    driver_path: str | None,
    db_kwargs: dict[str, str] | None,
    entrypoint: str | None,
    dbapi_module: str | None,
    pool_size: int,
    max_overflow: int,
    timeout: int,
    recycle: int,
    pre_ping: bool,
) -> sqlalchemy.pool.QueuePool:
    """Internal: create pool from either config or raw driver args."""
    if config is not None:
        # Config path -- extract driver info from config methods
        resolved_driver_path = config._driver_path()
        resolved_kwargs = config.to_adbc_kwargs()
        resolved_entrypoint = config._adbc_entrypoint()
        resolved_dbapi_module = config._dbapi_module()
    elif driver_path is not None:
        # Native ADBC driver path
        if db_kwargs is None:
            raise TypeError("db_kwargs is required with driver_path")
        resolved_driver_path = driver_path
        resolved_kwargs = db_kwargs
        resolved_entrypoint = entrypoint
        resolved_dbapi_module = None
    elif dbapi_module is not None:
        # Python dbapi module path
        if db_kwargs is None:
            raise TypeError("db_kwargs is required with dbapi_module")
        resolved_driver_path = ""  # not used by dbapi_module path
        resolved_kwargs = db_kwargs
        resolved_entrypoint = None
        resolved_dbapi_module = dbapi_module
    else:
        raise TypeError(
            "create_pool() requires one of: config (positional), "
            "driver_path=..., or dbapi_module=..."
        )

    source = create_adbc_connection(
        resolved_driver_path,
        resolved_kwargs,
        entrypoint=resolved_entrypoint,
        dbapi_module=resolved_dbapi_module,
    )
    # ... QueuePool creation, event listener, return
```

### Pattern 2: Three @overload Signatures

**What:** Each public function (`create_pool`, `managed_pool`) gets three `@overload` decorators followed by the implementation.

**Key disambiguation:** Overload 1 has a positional `config` parameter. Overloads 2 and 3 are keyword-only with mutually exclusive required args (`driver_path` vs `dbapi_module`).

**basedpyright resolution:** Basedpyright eliminates overloads by argument count and keyword names. Since `driver_path` and `dbapi_module` are required in their respective overloads (no default), the type checker can distinguish them. All four invalid patterns are caught at type-check time:
- `create_pool()` -- no overload matches (no args)
- `create_pool(config, driver_path=...)` -- no overload matches (positional + keyword)
- `create_pool(driver_path=..., dbapi_module=...)` -- no overload matches (both exclusive)
- `create_pool(pool_size=10)` -- no overload matches (only pool tuning)

**Example:**
```python
@overload
def create_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool: ...


@overload
def create_pool(
    *,
    driver_path: str,
    db_kwargs: dict[str, str],
    entrypoint: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool: ...


@overload
def create_pool(
    *,
    dbapi_module: str,
    db_kwargs: dict[str, str],
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool: ...


def create_pool(
    config: WarehouseConfig | None = None,
    *,
    driver_path: str | None = None,
    db_kwargs: dict[str, str] | None = None,
    entrypoint: str | None = None,
    dbapi_module: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> sqlalchemy.pool.QueuePool:
    return _create_pool_impl(
        config, driver_path, db_kwargs, entrypoint, dbapi_module,
        pool_size, max_overflow, timeout, recycle, pre_ping,
    )
```

### Pattern 3: managed_pool Overload Return Type

**What:** The `@overload` stubs for `managed_pool()` use `contextlib.AbstractContextManager[sqlalchemy.pool.QueuePool]` as return type, while the implementation uses `@contextlib.contextmanager` decorator which returns `Iterator[QueuePool]`.

**Example:**
```python
@overload
def managed_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    # ... same pool tuning kwargs ...
) -> contextlib.AbstractContextManager[sqlalchemy.pool.QueuePool]: ...

# ... (overloads 2 and 3 identical except for raw-path kwargs) ...

@contextlib.contextmanager
def managed_pool(
    config: WarehouseConfig | None = None,
    *,
    # ... all kwargs with None defaults ...
) -> collections.abc.Iterator[sqlalchemy.pool.QueuePool]:
    pool = _create_pool_impl(...)
    try:
        yield pool
    finally:
        close_pool(pool)
```

### Pattern 4: NOT_FOUND Error Generalization

**What:** Remove `_foundry_name_to_install` dict. Simplify the ImportError message to use the `driver_path` value directly without a "dbc install" hint.

**Before (current):**
```python
_foundry_name_to_install: dict[str, str] = {
    "clickhouse": "clickhouse",
    "databricks": "databricks",
    ...
}
# ...
install_name = _foundry_name_to_install.get(driver_path, driver_path)
raise ImportError(
    f"ADBC driver '{driver_path}' not found. "
    f"Install it with: dbc install {install_name}\n"
    f"See: https://docs.adbc-drivers.org/"
) from exc
```

**After:**
```python
raise ImportError(
    f"ADBC driver '{driver_path}' not found. "
    f"See: https://docs.adbc-drivers.org/"
) from exc
```

### Anti-Patterns to Avoid

- **Don't forward overloaded calls through overloaded functions:** `managed_pool()` calling `create_pool()` directly with `None`-defaulted args triggers basedpyright overload resolution failures. Use the shared `_create_pool_impl()` helper instead.
- **Don't add runtime isinstance checks for dispatch:** The CONTEXT.md explicitly specifies EAFP. Check `config is not None` / `driver_path is not None` / `dbapi_module is not None` -- don't isinstance-check the config parameter.
- **Don't set `driver_path=""` as a sentinel in the dbapi_module path:** The `create_adbc_connection()` function ignores `driver_path` when `dbapi_module` is provided (it calls `mod.connect(db_kwargs=kwargs)` directly). Any string is fine; an empty string is acceptable for this unused parameter.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Overload dispatch | Custom decorator or dispatch registry | `typing.overload` + if/elif on `None` checks | basedpyright validates at type-check time; runtime is just `is not None` checks |
| Mutual exclusivity enforcement | Custom validator class | TypeError in impl body + basedpyright overload resolution | Type checker catches it statically; TypeError catches it at runtime |
| ADBC connection creation | Custom connect logic | `create_adbc_connection()` (already exists) | Already handles both native and dbapi_module paths |

## Common Pitfalls

### Pitfall 1: Overload Return Type for Context Managers
**What goes wrong:** Using `collections.abc.Iterator[T]` as the return type in `@overload` stubs for `managed_pool()` causes basedpyright to infer `Iterator` (not a context manager) at call sites, breaking `with` statements.
**Why it happens:** `@contextlib.contextmanager` wraps the generator into a `_GeneratorContextManager`, but the overload stubs need to declare the public-facing type.
**How to avoid:** Use `contextlib.AbstractContextManager[QueuePool]` in the `@overload` stubs. The `@contextlib.contextmanager` implementation stub uses `Iterator[QueuePool]` as always.
**Warning signs:** `with managed_pool(...) as pool:` shows a type error about Iterator not being a context manager.

### Pitfall 2: Existing Tests Assert "dbc install" in Error Message
**What goes wrong:** `test_foundry_not_found_message_contains_install_command` in `tests/test_drivers.py` (line 260-274) explicitly asserts `match=r"dbc install databricks"` in the ImportError message. The simplified error message removes this.
**Why it happens:** The test was written for the old Foundry-specific error message.
**How to avoid:** Update the test to match the new generic error message format: `"ADBC driver 'databricks' not found. See: https://docs.adbc-drivers.org/"`.
**Warning signs:** Test failure in `TestCreateAdbcConnectionFoundryNotFound`.

### Pitfall 3: dbapi_module Path Passes Empty driver_path to create_adbc_connection
**What goes wrong:** When using the `dbapi_module` overload, `create_adbc_connection()` still requires a `driver_path` positional arg even though it won't use it (the `if dbapi_module is not None` branch runs first).
**Why it happens:** `create_adbc_connection()` signature has `driver_path` as a required positional parameter.
**How to avoid:** Pass an empty string `""` as `driver_path` when the `dbapi_module` path is taken. This is safe because `create_adbc_connection()` never touches `driver_path` when `dbapi_module` is provided. Alternatively, make `driver_path` optional in `create_adbc_connection()` -- but this is an internal function and the empty-string approach is simpler.
**Warning signs:** None at runtime, but consider documenting the convention in a code comment.

### Pitfall 4: Documentation Quality Gate
**What goes wrong:** Phase is incomplete because new public API surface (overloaded signatures, new parameters) lacks docstrings or guide updates.
**Why it happens:** CLAUDE.md requires Google-style docstrings, Examples blocks on key entry points, guide updates, and `uv run mkdocs build --strict` passing for all phases >= 7.
**How to avoid:** Update docstrings for `create_pool()` and `managed_pool()` to document all three call patterns. Update the pool-lifecycle guide with raw driver examples. Run `uv run mkdocs build --strict` before marking complete.
**Warning signs:** Missing Args/Returns/Raises for new parameters; mkdocs build failure.

### Pitfall 5: Backward Compatibility
**What goes wrong:** Existing code calling `create_pool(config)` or `create_pool(config, pool_size=10)` stops working.
**Why it happens:** The overload implementation changes the function signature.
**How to avoid:** The first overload preserves the exact current signature. `config` remains the first positional parameter with all pool tuning as keyword-only. Existing calls match overload 1 exactly. No breaking change.
**Warning signs:** Existing tests fail.

## Code Examples

### Raw Driver Path (Native ADBC)
```python
# Source: derived from adbc_driver_manager.dbapi.connect() signature
from adbc_poolhouse import create_pool, close_pool

# DuckDB via raw driver path -- bypasses DuckDBConfig entirely
pool = create_pool(
    driver_path="/path/to/libduckdb.dylib",
    db_kwargs={"path": "/tmp/my.db"},
    entrypoint="duckdb_adbc_init",
    pool_size=3,
)
# ... use pool ...
close_pool(pool)
```

### Raw Driver Path (Python dbapi Module)
```python
# Source: derived from existing _driver_api.py dbapi_module branch
from adbc_poolhouse import create_pool, close_pool

# Custom Python "driver" implementing ADBC dbapi interface
pool = create_pool(
    dbapi_module="my_custom_driver.dbapi",
    db_kwargs={"host": "localhost", "port": "5432"},
)
# ... use pool ...
close_pool(pool)
```

### managed_pool with Raw Args
```python
from adbc_poolhouse import managed_pool

with managed_pool(
    driver_path="databricks",
    db_kwargs={"uri": "databricks://token:xxx@host:443/path"},
) as pool:
    with pool.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
```

### Runtime Dispatch Logic
```python
# Source: validated via basedpyright strict on this project
def _create_pool_impl(
    config: WarehouseConfig | None,
    driver_path: str | None,
    db_kwargs: dict[str, str] | None,
    entrypoint: str | None,
    dbapi_module: str | None,
    pool_size: int,
    max_overflow: int,
    timeout: int,
    recycle: int,
    pre_ping: bool,
) -> sqlalchemy.pool.QueuePool:
    # Dispatch: exactly one of config/driver_path/dbapi_module must be non-None
    if config is not None:
        actual_driver_path = config._driver_path()
        actual_kwargs = config.to_adbc_kwargs()
        actual_entrypoint = config._adbc_entrypoint()
        actual_dbapi_module = config._dbapi_module()
    elif driver_path is not None:
        if db_kwargs is None:
            raise TypeError("db_kwargs is required when using driver_path")
        actual_driver_path = driver_path
        actual_kwargs = db_kwargs
        actual_entrypoint = entrypoint
        actual_dbapi_module = None  # native path never uses dbapi_module
    elif dbapi_module is not None:
        if db_kwargs is None:
            raise TypeError("db_kwargs is required when using dbapi_module")
        actual_driver_path = ""  # unused by dbapi_module branch
        actual_kwargs = db_kwargs
        actual_entrypoint = None  # dbapi modules handle their own loading
        actual_dbapi_module = dbapi_module
    else:
        raise TypeError(
            "create_pool() requires one of: a config object (positional), "
            "driver_path=..., or dbapi_module=..."
        )

    source = create_adbc_connection(
        actual_driver_path,
        actual_kwargs,
        entrypoint=actual_entrypoint,
        dbapi_module=actual_dbapi_module,
    )
    # ... pool creation continues as before ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Config-only `create_pool(config)` | Overloaded `create_pool(config)` / `create_pool(driver_path=...)` / `create_pool(dbapi_module=...)` | Phase 19 | Advanced users bypass config objects |
| Foundry-specific NOT_FOUND error with `dbc install` hint | Generic NOT_FOUND error pointing to docs URL | Phase 19 | Works for any driver, not just Foundry short names |
| `_foundry_name_to_install` reverse lookup dict | Removed (1:1 mapping was redundant) | Phase 19 | Simpler `_driver_api.py` |

## Open Questions

1. **Should `create_adbc_connection()` signature change?**
   - What we know: The function currently requires `driver_path` as positional. When `dbapi_module` is provided, `driver_path` is unused.
   - What's unclear: Whether making `driver_path` optional (with a default of `""`) is cleaner than always passing an empty string.
   - Recommendation: Leave `create_adbc_connection()` signature unchanged. It is an internal function (`_driver_api.py`), and passing `""` as the unused `driver_path` is simpler than changing its signature and all existing callers. Document with a code comment.

2. **Should `db_kwargs` allow `dict[str, str | Path]`?**
   - What we know: `adbc_driver_manager.dbapi.connect()` accepts `dict[str, str | Path]` for `db_kwargs`. All existing configs produce `dict[str, str]`.
   - What's unclear: Whether raw path users might want to pass Path values.
   - Recommendation: Keep `dict[str, str]` for consistency with existing config interface. Users can `str(path)` if needed. Widening the type later is non-breaking.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_pool_factory.py tests/test_drivers.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RAW-01 | `create_pool(driver_path=..., db_kwargs=...)` creates pool via native ADBC path | unit (mock) | `uv run pytest tests/test_pool_factory.py -k "raw_driver_path" -x` | Wave 0 |
| RAW-02 | `create_pool(dbapi_module=..., db_kwargs=...)` creates pool via Python dbapi path | unit (mock) | `uv run pytest tests/test_pool_factory.py -k "raw_dbapi_module" -x` | Wave 0 |
| RAW-03 | `managed_pool(driver_path=...)` and `managed_pool(dbapi_module=...)` work | unit (mock) | `uv run pytest tests/test_pool_factory.py -k "managed_raw" -x` | Wave 0 |
| RAW-04 | TypeError when none of config/driver_path/dbapi_module provided | unit | `uv run pytest tests/test_pool_factory.py -k "missing_args" -x` | Wave 0 |
| RAW-05 | TypeError when both driver_path and dbapi_module provided (runtime check) | unit | `uv run pytest tests/test_pool_factory.py -k "mutual_exclusive" -x` | Wave 0 |
| RAW-06 | Existing config path unchanged -- all existing tests still pass | regression | `uv run pytest tests/ -x` | Existing |
| RAW-07 | `_foundry_name_to_install` removed, NOT_FOUND error message simplified | unit | `uv run pytest tests/test_drivers.py -k "not_found" -x` | Existing (needs update) |
| RAW-08 | basedpyright strict passes with overloaded signatures | type-check | `uv run basedpyright` | N/A (type-check) |
| RAW-09 | DuckDB integration test with raw driver_path (end-to-end, real driver) | integration | `uv run pytest tests/test_pool_factory.py -k "raw_duckdb_integration" -x` | Wave 0 |
| RAW-10 | Docstrings updated, mkdocs build passes | docs | `uv run mkdocs build --strict` | N/A (manual) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_pool_factory.py tests/test_drivers.py -x && uv run basedpyright`
- **Per wave merge:** `uv run pytest tests/ -x && uv run basedpyright`
- **Phase gate:** Full suite green + basedpyright clean + `uv run mkdocs build --strict` before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] New test cases in `tests/test_pool_factory.py` for raw driver_path, raw dbapi_module, managed_pool raw variants, TypeError cases
- [ ] Update `tests/test_drivers.py::TestCreateAdbcConnectionFoundryNotFound::test_foundry_not_found_message_contains_install_command` to match new error format
- [ ] Integration test for raw DuckDB driver_path in `tests/test_pool_factory.py`

## Sources

### Primary (HIGH confidence)
- Project source: `src/adbc_poolhouse/_pool_factory.py` -- current `create_pool()` and `managed_pool()` implementation
- Project source: `src/adbc_poolhouse/_driver_api.py` -- current `create_adbc_connection()` with `_foundry_name_to_install`
- Project source: `src/adbc_poolhouse/_base_config.py` -- `WarehouseConfig` Protocol definition
- `adbc_driver_manager.dbapi.connect()` help text -- verified signature: `connect(driver, uri, *, entrypoint, db_kwargs, conn_kwargs, autocommit)`
- basedpyright validation -- all overload patterns tested locally with 0 errors on valid calls, 4 errors on invalid calls

### Secondary (MEDIUM confidence)
- [Python typing overload spec](https://typing.python.org/en/latest/spec/overload.html) -- overload resolution algorithm (Step 1-6)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, just typing.overload from stdlib
- Architecture: HIGH -- overload pattern validated against basedpyright strict, shared impl helper pattern confirmed clean
- Pitfalls: HIGH -- all five pitfalls identified from direct codebase analysis and type-checker testing

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable domain, no external dependencies changing)
