# Phase 19: Raw create_pool Overload - Context

**Gathered:** 2026-03-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Add overloaded `create_pool()` and `managed_pool()` signatures that accept raw driver args directly, bypassing config objects. Two raw paths: native ADBC driver (driver_path) and Python dbapi module (dbapi_module), mutually exclusive. Clean up hardcoded driver lists in `_driver_api.py`. For advanced users, custom drivers, plugin authors, and testing.

</domain>

<decisions>
## Implementation Decisions

### API shape
- Single `create_pool()` with `@overload` — three overloads:
  1. `create_pool(config: WarehouseConfig, *, pool_size=5, ...)` — existing config path, config is positional
  2. `create_pool(*, driver_path: str, db_kwargs: dict[str, str], entrypoint: str | None = None, pool_size=5, ...)` — native ADBC driver, all keyword-only
  3. `create_pool(*, dbapi_module: str, db_kwargs: dict[str, str], pool_size=5, ...)` — Python dbapi module, all keyword-only
- `driver_path` and `dbapi_module` are mutually exclusive — different overloads, not co-existing kwargs
- Pool tuning params (pool_size, max_overflow, timeout, recycle, pre_ping) shared across all three overloads with same defaults
- `entrypoint` only available on `driver_path` overload (it's a native ADBC concept — Python dbapi modules handle their own loading)

### driver_path vs dbapi_module mutual exclusivity
- These represent genuinely different connection mechanisms:
  - `driver_path` → native C/C++ ADBC driver loaded via `adbc_driver_manager.dbapi.connect(driver=...)`
  - `dbapi_module` → Python module implementing ADBC dbapi interface, loaded via `module.connect(db_kwargs=...)`
- Existing configs that provide both `_driver_path()` and `_dbapi_module()` (Snowflake, BigQuery, PostgreSQL, FlightSQL) already ignore driver_path when dbapi_module is set — this makes the implicit exclusivity explicit
- The distinction opens `dbapi_module` path to any Python "driver" implementing the ADBC dbapi interface, not just Apache PyPI packages

### managed_pool parity
- `managed_pool()` gets the same three overloads as `create_pool()`
- It just forwards args to `create_pool()` — minimal extra code

### Validation stance
- Pure EAFP for argument values — if driver_path is wrong, ADBC raises; if db_kwargs has bad keys, the driver raises
- TypeError if both `driver_path` and `dbapi_module` provided (mutual exclusivity enforcement)
- TypeError if none of config / driver_path / dbapi_module provided (catches misuse like `create_pool(pool_size=10)`)

### Hardcoded driver list cleanup
- Remove `_foundry_name_to_install` dict from `_driver_api.py` — it's a pure 1:1 mapping (every key equals its value), completely redundant
- Generalize the NOT_FOUND error handling in `create_adbc_connection()`: any NOT_FOUND from adbc_driver_manager gets a clear ImportError regardless of whether the driver_path is a Foundry short name or a file path
- Error message: `"ADBC driver '{driver_path}' not found. See: https://docs.adbc-drivers.org/"` — no Foundry-specific `dbc install` hint

### Claude's Discretion
- Implementation of the `@overload` dispatch in the actual function body (how to distinguish which overload was called at runtime)
- Whether `create_adbc_connection()` signature needs updating to reflect mutual exclusivity or stays as-is internally
- Test structure for the new overloads

</decisions>

<specifics>
## Specific Ideas

- "I was building a Python-based 'ADBC driver' that is not a true ADBC driver, but just exposed the ADBC dbapi2-style Python interface returning Arrow" — the `dbapi_module` path should explicitly support this use case, not just Apache PyPI packages
- The mutual exclusivity makes the mental model cleaner: you either have a native driver (C/C++ shared library) or a Python dbapi module — not both

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `create_adbc_connection()` in `_driver_api.py` already accepts `(driver_path, kwargs, entrypoint, dbapi_module)` — the internal plumbing is ready for both paths
- `_release_arrow_allocators()` reset listener works regardless of how the pool was created
- `close_pool()` works on any QueuePool with `_adbc_source` — no changes needed

### Established Patterns
- `@overload` with basedpyright strict — must produce valid overload resolution (no ambiguous signatures)
- Phase 18 EAFP pattern — no isinstance checks, let Python raise naturally
- Config path uses positional first arg — raw paths use keyword-only to disambiguate

### Integration Points
- `_pool_factory.py:create_pool()` — add overloads and dispatch logic
- `_pool_factory.py:managed_pool()` — mirror overloads, forward to create_pool()
- `_driver_api.py:create_adbc_connection()` — remove `_foundry_name_to_install`, generalize NOT_FOUND error
- `__init__.py` — exports unchanged (create_pool and managed_pool already exported)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 19-raw-create-pool*
*Context gathered: 2026-03-15*
