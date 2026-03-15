# Phase 18: Registration Removal - Context

**Gathered:** 2026-03-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Make config classes fully self-describing so the backend registry is unnecessary.
Each config carries its driver path, kwargs translation, dbapi module, and entrypoint.
`create_pool()` calls config methods directly — no registry lookup, no lazy registration,
no `_drivers.py` dispatch layer. Delete all registry machinery.

</domain>

<decisions>
## Implementation Decisions

### Driver path method
- Instance method `_driver_path() -> str` on every config class
- Added to `WarehouseConfig` Protocol and `BaseWarehouseConfig` (raises NotImplementedError)
- Consider making `BaseWarehouseConfig` an ABC (abstract base class)
- Shared helper for PyPI/DuckDB driver resolution: takes `method_name` arg so it works for both `_driver_path()` and `driver_path()` conventions across driver packages
- Helper lives in `_base_config.py` as a static/class method
- Manifest fallback preserved: if `find_spec` returns None, return package name string for `adbc_driver_manager` manifest resolution
- DuckDB uses same helper (not special-cased) since `adbc_driver_duckdb.driver_path()` works
- Foundry configs return a static string (e.g., `"databricks"`, `"clickhouse"`)

### Dbapi module on configs
- Move `_PYPI_PACKAGES` dict logic into config classes as `_dbapi_module() -> str | None`
- Configs that have PyPI drivers return their dbapi module name when installed, None otherwise
- Foundry/DuckDB configs return None
- SQLite excluded (incompatible dbapi signature) — returns None
- `resolve_dbapi_module()` function eliminated

### 3rd-party config contract
- Protocol (structural typing) is sufficient — no subclass requirement
- Minimum contract: `to_adbc_kwargs()` + `_driver_path()` (both required)
- `_adbc_entrypoint()` optional — returns None by default in BaseWarehouseConfig
- `_dbapi_module()` optional — returns None by default
- Duck typing validation: no isinstance check in create_pool(), just call the methods
- If a config doesn't implement required methods, Python raises AttributeError naturally (EAFP)

### Deletion scope
- Delete `_registry.py` entirely — no backwards compat shim
- Delete `register_backend` from `__init__.py` exports and `__all__`
- Delete all three registry exceptions: `RegistryError`, `BackendAlreadyRegisteredError`, `BackendNotRegisteredError`
- Delete `_drivers.py` — shared helpers move to `_base_config.py`, dispatch functions inlined into `create_pool()`
- Delete `_setup_lazy_registrations()` and all lazy registration closures
- Delete `tests/test_registry.py` — rework or replace with config method tests

### resolve_driver rewrite
- Inline `resolve_driver()` into `create_pool()`: call `config._driver_path()` directly
- Inline `resolve_dbapi_module()` into `create_pool()`: call `config._dbapi_module()` directly
- `create_pool()` becomes: `driver_path = config._driver_path()`, `kwargs = config.to_adbc_kwargs()`, `entrypoint = config._adbc_entrypoint()`, `dbapi_module = config._dbapi_module()`
- No wrapper functions — direct method calls

### Claude's Discretion
- Whether BaseWarehouseConfig becomes a formal ABC or just has NotImplementedError defaults
- Exact signature and naming of the shared driver resolution helper
- How to structure `_base_config.py` with the added helper methods
- Whether `_drivers.py` is deleted or kept as an empty module for import compat
- Test restructuring details (what replaces test_registry.py)

</decisions>

<specifics>
## Specific Ideas

- "pkg._driver_path() is ad hoc, not ADBC spec" — the helper should accept a `method_name` parameter to handle both `_driver_path()` and `driver_path()` conventions across different driver packages
- "adbc_driver_duckdb.driver_path() works" — DuckDB can use the same PyPI resolution path as other drivers, not a special case
- Fully self-describing configs: after this phase, a config class is the only thing needed to create a pool — no external registration, no dispatch tables, no module-level dicts

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_base_config.py`: Protocol + BaseWarehouseConfig — destination for shared helpers
- `_resolve_pypi_driver()` in `_drivers.py`: core logic to reuse (find_spec + import + call driver method)
- `_resolve_duckdb()` in `_drivers.py`: can be unified with PyPI helper
- All 12 config classes already have `to_adbc_kwargs()` and `_adbc_entrypoint()` — adding `_driver_path()` completes the picture

### Established Patterns
- `_adbc_entrypoint()`: instance method on BaseWarehouseConfig, returns None by default, DuckDB overrides — `_driver_path()` follows same pattern
- `to_adbc_kwargs()`: instance method, raises NotImplementedError in base — same for `_driver_path()`
- Config classes are Pydantic BaseSettings subclasses with `model_config = SettingsConfigDict(env_prefix=...)`

### Integration Points
- `_pool_factory.py:create_pool()` — currently calls `resolve_driver(config)` and `resolve_dbapi_module(config)`, will call config methods directly
- `__init__.py` — remove `register_backend` export, remove registry exception exports
- `tests/conftest.py` — `dummy_backend` fixture may need updating (currently uses register_backend)
- `_driver_api.py:create_adbc_connection()` — unchanged, still receives driver_path/kwargs/entrypoint

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 18-registration-removal*
*Context gathered: 2026-03-15*
