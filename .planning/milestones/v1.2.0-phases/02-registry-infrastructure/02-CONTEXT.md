# Phase 2: Registry Infrastructure - Context

**Gathered:** 2026-03-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a backend registry and manual registration API that allows runtime registration of new backends, replacing the current hardcoded architecture with an extensible plugin system. Built-in backends remain supported without user registration calls.

</domain>

<decisions>
## Implementation Decisions

### Registration API signature
- `register_backend(name, config_class, translator, driver_path)` — all parameters explicit
- `driver_path` passed directly to `adbc_driver_manager.dbapi.connect(driver=driver_path, ...)`
- ADBC handles resolution (shared library path, manifest path, or driver name)
- Registered backends always use `adbc_driver_manager.dbapi` path (no dbapi module selection)
- Built-in backends retain their richer behavior (PyPI drivers use their own dbapi when installed)

### Backend naming
- Built-in PyPI drivers: use PyPI package name → `"adbc_driver_snowflake"`, `"adbc_driver_bigquery"`, etc.
- Built-in Foundry drivers: prefix with `__dbc__` → `"__dbc__databricks"`, `"__dbc__clickhouse"`, etc.
- Auto-discovered plugins (Phase 3): use PyPI package name (already unique in ecosystem)
- Manual registrations: user chooses any name, but error if already registered
- No format validation — only duplicate checking at registration time

### Registry integration
- Registry replaces hardcoded dispatch entirely
- `_translators.py`: `translate_config()` queries registry for all backends
- `_drivers.py`: `resolve_driver()` queries registry for driver_path
- All 12 built-in backends go through registry
- Built-ins registered lazily per-backend (when config class first used in `create_pool()`)

### Error handling
- `BackendAlreadyRegisteredError` — duplicate registration attempt
- `BackendNotRegisteredError` — lookup of unregistered backend (message includes name and hint to call `register_backend()`)
- `TypeError` — invalid parameters (None config_class, non-callable translator, etc.) with clear message
- Exception hierarchy:
  - `RegistryError(PoolhouseError)` — base for all registry errors
  - `BackendAlreadyRegisteredError(RegistryError)`
  - `BackendNotRegisteredError(RegistryError)`

### Testing approach
- 5 core test scenarios:
  1. Manual registration works — `register_backend()` with valid params succeeds
  2. Duplicate detection — registering same name twice raises `BackendAlreadyRegisteredError`
  3. Invalid params — passing None config_class raises `TypeError` with clear message
  4. Unregistered backend — `create_pool()` with unregistered config raises `BackendNotRegisteredError`
  5. Built-ins work without registration — observable behavior that built-in configs work out of the box
- Entry point simulation tests deferred to Phase 3
- Dummy backend fixture: minimal (config class + no-op translator returning empty dict)

### Claude's Discretion
- Exact registry module structure and internal APIs
- Import ordering strategy for lazy built-in registration
- Whether to expose registry internals for advanced use cases

</decisions>

<specifics>
## Specific Ideas

- "If never use BigQuery, BigQuery backend never registered" — true lazy per-backend registration
- "Manual registrations are registered last" — built-ins and auto-discovered take priority, manual registrations error on duplicate names

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_exceptions.py`: `PoolhouseError` base class, `ConfigurationError` pattern (inherits from both PoolhouseError and ValueError)
- `_base_config.py`: `WarehouseConfig` Protocol and `BaseWarehouseConfig` base class
- `_translators.py`: 12 translator functions with consistent `translate_<name>(config) -> dict[str, str]` signature
- `_driver_api.py`: `create_adbc_connection()` handles ADBC connection creation

### Established Patterns
- `_translators.py`: `isinstance` dispatch across 12 config types (to be replaced with registry lookup)
- `_drivers.py`: `_PYPI_PACKAGES` and `_FOUNDRY_DRIVERS` dicts map config types to driver metadata (to be replaced with registry)
- `_pool_factory.py`: calls `resolve_driver()`, `translate_config()`, `resolve_dbapi_module()` in sequence
- All 12 config classes explicitly imported and exported in `__init__.py`

### Integration Points
- `create_pool()` entry point — must work with both built-in and registered backends
- `translate_config()` — dispatch to translator based on config class
- `resolve_driver()` — return driver_path for connection creation
- Lazy registration trigger — occurs in `create_pool()` when config class not found in registry

</code_context>

<deferred>
## Deferred Ideas

- `list_backends()` utility — removed from requirements (no clear use case, can add later if needed)
- Entry point discovery tests — Phase 3 responsibility
- Rich driver metadata for registered backends (pip_extra, driver_type) — simplified to just driver_path

</deferred>

---

*Phase: 02-registry-infrastructure*
*Context gathered: 2026-03-12*
