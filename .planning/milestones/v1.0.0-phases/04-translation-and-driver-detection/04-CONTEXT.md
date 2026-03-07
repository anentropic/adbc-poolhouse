# Phase 4: Translation and Driver Detection - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Build pure translator functions (config → ADBC kwargs dict), lazy driver resolution, and type isolation facades. Internal library infrastructure — no public API additions. This layer is consumed by `create_pool()` in Phase 5.

</domain>

<decisions>
## Implementation Decisions

### ImportError message format
- Use `adbc-poolhouse` extras in the install command: `pip install adbc-poolhouse[duckdb]`
- Use `pip` only (not `uv`) — universal, no toolchain assumptions
- Include the config class name in the message: e.g. "DuckDB ADBC driver not found. Run: `pip install adbc-poolhouse[duckdb]`"
- For Foundry-distributed drivers (Databricks, Redshift, Trino, MSSQL, Teradata) not on PyPI: point to docs with the correct URL — researcher should verify whether the canonical docs are at https://docs.adbc-drivers.org/ or elsewhere (user flagged these are NOT from apache.org)

### Translator file structure
- Per-warehouse translator files matching the existing config pattern: `_duckdb_translator.py`, `_snowflake_translator.py`, etc.
- A coordinator module `_translators.py` imports all per-warehouse translators and exposes a single dispatch function `translate_config(config: WarehouseConfig) -> dict[str, str]`
- Translators are internal only — not exported in `__init__.py`

### Driver detection interface
- Single `resolve_driver(config: WarehouseConfig) -> str` dispatch function (returns the driver entrypoint string, not the loaded module)
- Lives in a `_drivers.py` module (consistent with `_translators.py` pattern)
- The 3-path logic (find_spec → adbc_driver_manager fallback → ImportError) is generic; config type determines the package name and error message

### _driver_api.py responsibilities
- Owns the actual `adbc_driver_manager.dbapi.connect(driver_path, **kwargs)` call
- Exposes a typed `create_adbc_connection(driver_path: str, kwargs: dict[str, str]) -> <connection>` function
- All `cast()` and `# type: ignore` suppressions for ADBC live here
- ADBC exceptions pass through raw — no wrapping in this phase

### Claude's Discretion
- Exact scope of `_pool_types.py` in Phase 4 — whether it declares only type-cast helpers now (with QueuePool assembly deferred to Phase 5) or builds more of the facade now. Either approach is acceptable as long as Phase 5 can assemble `create_pool()` cleanly.

</decisions>

<specifics>
## Specific Ideas

- Foundry driver docs URL needs researcher verification — user believes it is https://docs.adbc-drivers.org/ but is not certain. Do NOT hardcode the apache.org URL.
- The module naming pattern is established: per-warehouse `_<warehouse>_translator.py` files + a coordinator `_translators.py`. Same pattern for drivers: `_drivers.py` holds the dispatch + 3-path resolution logic.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-translation-and-driver-detection*
*Context gathered: 2026-02-24*
