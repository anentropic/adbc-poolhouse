# Phase 12: ClickHouse Backend - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Add ClickHouse as a Foundry-distributed ADBC backend. Deliverables: `ClickHouseConfig` model,
`translate_clickhouse()` translator, registration in `_FOUNDRY_DRIVERS`, unit tests, and a
warehouse guide page in the docs. Follows the established Foundry backend pattern.

</domain>

<decisions>
## Implementation Decisions

### Connection mode
- Support both URI passthrough and individual fields — consistent with MySQL, Redshift, PostgreSQL
- Individual fields (`host`, `port`, `username`, `password`, `database`, and any additional
  driver-supported fields) are translated as **direct driver kwargs** — not assembled into a URI
- This is driven by the phase spec: `translate_clickhouse()` must emit `username` as a kwarg key
  (not `user`, and not wrapped inside a URI)

### Field coverage
- Expose **all fields the Columnar ClickHouse driver supports as driver kwargs** — nothing more
- Researcher must verify the complete list of supported kwargs from the driver source/docs
  (public docs at docs.adbc-drivers.org only document `uri` for v0.1.0-alpha; check upstream)
- Minimum confirmed fields (from CH-01 + success criteria): `host`, `port`, `username`,
  `password`, `database`
- The `username` field on the config maps to the `username` driver kwarg (not `user`) — this is
  the key naming difference from MySQL and other backends
- If the driver has ClickHouse-specific params (e.g. `secure`, `compress`, protocol variant),
  expose them — researcher to confirm exact kwarg names

### Validation guard
- Apply a `@model_validator(mode="after")` guard — same pattern as MySQL
- `ConfigurationError` if neither `uri` nor at minimum `host` + `username` is provided
- This matches the fail-fast approach established by MySQL

### Tests
- Config construction and field validation (including `ConfigurationError` on missing required fields)
- Translator kwargs — assert exact dict output for both URI mode and individual fields mode
- Mock-at-`create_adbc_connection` test for full pool-factory wiring
- Match coverage depth of Redshift and MySQL test files

### Docs
- Standard warehouse guide page: Foundry installation note, usage examples, field reference,
  env var table (`CLICKHOUSE_*`)
- Equivalent depth to existing guides (mysql.md, redshift.md)
- `uv run mkdocs build --strict` must pass

### Claude's Discretion
- Exact set of ClickHouse-specific kwargs beyond the minimum confirmed fields (researcher verifies)
- Whether `secure` translates to a boolean kwarg or a port convention
- Default port value (ClickHouse native: 9000; HTTPS: 8443; HTTP: 8123 — researcher to confirm
  which port the Foundry driver uses as its default)

</decisions>

<specifics>
## Specific Ideas

- User instruction: "Make it consistent with the other backends — equivalent tests and docs etc."
- "Everything that the driver supports, but nothing else"
- The `username` vs `user` distinction is the key quirk — must be preserved in both the config
  field name and the translated kwarg key

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BaseWarehouseConfig` (`_base_config.py`): base class for all config models; inherit directly
- `ConfigurationError` (`_exceptions.py`): use for the validation guard error
- `SettingsConfigDict` from pydantic-settings: already used by all backends; apply with
  `env_prefix="CLICKHOUSE_"`
- `model_validator(mode="after")` pattern from `_mysql_config.py`: copy for the validation guard
- `_FOUNDRY_DRIVERS` dict in `_drivers.py`: add `ClickHouseConfig: ("clickhouse", "clickhouse")`

### Established Patterns
- Translator pattern: `translate_<warehouse>(config: <Warehouse>Config) -> dict[str, str]`
- Config file naming: `_clickhouse_config.py` and `_clickhouse_translator.py`
- Test file: `tests/test_clickhouse.py` (or `test_clickhouse_config.py` — follow existing naming)
- All warehouse config imports in `_drivers.py` must be at module level (not inside functions)
- Export via `__all__` in `__init__.py`

### Integration Points
- `_drivers.py` — import `ClickHouseConfig` at module level; add entry to `_FOUNDRY_DRIVERS`
- `__init__.py` — add `ClickHouseConfig` to `__all__`
- `mkdocs.yml` — add `clickhouse.md` to warehouse guides nav section
- `docs/src/guides/clickhouse.md` — new warehouse guide page

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 12-clickhouse-backend*
*Context gathered: 2026-03-01*
