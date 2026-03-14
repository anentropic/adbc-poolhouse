# Phase 3: Entry Point Discovery - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Auto-discover 3rd party backends via Python entry points. Plugin packages declare backends in their `pyproject.toml`, adbc-poolhouse discovers and registers them lazily on first use. After Translator Consolidation (Phase 2.5) refactors translators into config classes.

</domain>

<decisions>
## Implementation Decisions

### Translator Interface
- Translator consolidates into config class method `to_adbc_kwargs()`
- Uses Pydantic v2: field aliases for ADBC key prefixes, `@field_serializer` for bool→string and SecretStr→string, `@model_validator` for URI construction
- `model_dump(exclude_none=True, by_alias=True)` as base, custom serializers for transformations
- **Phase 2.5 refactor required first** — all 12 built-in backends migrate translators into config classes

### Driver Path Registration
- Built-in backends: `register_backend(config_class, driver_path="adbc_driver_snowflake")`
- Plugins: driver path inferred from PyPI package name via `entry_point.dist.name`
- Driver path is NOT a config class attribute — registered separately

### Entry Point Format
- Group: `adbc_poolhouse.backends`
- Name = backend name (e.g., `clickhouse`, `my_backend`)
- Value = config class (e.g., `adbc_driver_clickhouse:ClickHouseConfig`)
- Driver path = distribution name from entry point (e.g., `adbc_driver_clickhouse`)

```toml
# Example plugin pyproject.toml
[project]
name = "adbc_driver_mybackend"

[project.entry-points."adbc_poolhouse.backends"]
my_backend = "adbc_driver_mybackend:MyBackendConfig"
```

### Discovery Timing
- Lazy scan on first `create_pool()` call with unrecognized config class
- Scan happens once per Python process
- `force_discover()` utility for testing only — clears flag and rescans
- No rescan on `BackendNotRegisteredError` — call `force_discover()` explicitly

### Error Handling
All 6 malformed entry point cases have test fixtures:

1. **Module not found** — Entry point references non-existent module
2. **Attribute not found** — Module exists but class doesn't exist
3. **Not a config class** — Class doesn't implement `WarehouseConfig` protocol
4. **No to_adbc_kwargs method** — Config class missing required method (after refactor)
5. **Driver metadata missing** — Entry point missing driver path (inferred from dist name, so this would be rare)
6. **Duplicate name** — Two packages register same backend name

Error behavior:
- Import errors during entry point load → raise `BackendLoadError` with package name
- Malformed entry points (wrong type, missing method) → log warning, skip, continue
- Duplicate names → raise `BackendAlreadyRegisteredError` (first wins)

### force_discover API
- Test utility only, not for production use
- Signature: `force_discover() -> None`
- Behavior: Clear `_entry_points_scanned` flag, rescan all entry points, register discovered backends
- No return value, no parameters

### Claude's Discretion
- Exact scan implementation (where `_entry_points_scanned` flag lives)
- Error message formatting for `BackendLoadError`
- Logging level and format for malformed entry point warnings
- Whether to expose `_entry_points_scanned` for advanced testing scenarios

</decisions>

<specifics>
## Specific Ideas

- "Package name as driver path" — plugin's PyPI package name becomes the driver path, simple and predictable
- "Scan once" — no complex TTL or filesystem change detection, just a single scan per process

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_registry.py`: `register_backend()`, `ensure_registered()`, `_registry` and `_config_to_name` dicts
- `_base_config.py`: `WarehouseConfig` Protocol — defines `to_adbc_kwargs()` after refactor
- `_exceptions.py`: `BackendAlreadyRegisteredError`, `BackendNotRegisteredError`, `PoolhouseError` base

### Established Patterns
- Built-in backends: lazy registration via `_lazy_registrations` dict
- Registry-based dispatch: `translate_config()` and `resolve_driver()` query registry
- Error hierarchy: `PoolhouseError` → `RegistryError` → `BackendAlreadyRegisteredError`/`BackendNotRegisteredError`

### Integration Points
- `create_pool()` calls `ensure_registered()` before looking up translator/driver
- Entry point scan happens BEFORE checking `_lazy_registrations` (plugins discovered before built-ins)
- Discovery adds to `_registry` and `_config_to_name` just like manual registration

### Deferred from Phase 2
- Entry point simulation tests (Phase 3 responsibility)
- Dummy backend fixture for integration testing (TEST-INFRA-01, part of Phase 1)

</code_context>

<deferred>
## Deferred Ideas

- **Phase 2.5: Translator Consolidation** — Insert before this phase. Refactors all 12 built-in translators into config class `to_adbc_kwargs()` methods using Pydantic aliases and serializers.
- Backend versioning / conflict resolution (out of scope per REQUIREMENTS.md)
- Backend unregistration (out of scope per REQUIREMENTS.md)

</deferred>

---

*Phase: 03-entry-point-discovery*
*Context gathered: 2026-03-14*