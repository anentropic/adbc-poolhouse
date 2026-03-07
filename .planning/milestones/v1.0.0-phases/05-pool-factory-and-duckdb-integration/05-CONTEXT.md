# Phase 5: Pool Factory and DuckDB Integration - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Build `create_pool(config)` — the complete public factory function that accepts a `DuckDBConfig` and returns a working `sqlalchemy.pool.QueuePool`. This is the primary entry point of the library. Connection wrapping, ADBC dialect, and translation layers are from previous phases; this phase wires them together and ships the public API.

</domain>

<decisions>
## Implementation Decisions

### create_pool() signature
- Flat keyword args: `create_pool(config, pool_size=5, max_overflow=3, timeout=30, recycle=3600, pre_ping=False)`
- Default values live directly in the function signature (visible in docstring, IDE autocomplete, `help()`)
- Returns `sqlalchemy.pool.QueuePool` — raw, no wrapper
- Return type annotated as `sqlalchemy.pool.QueuePool`

### Validation strategy
- Validation lives in `DuckDBConfig.__init__` / `__post_init__` — fail at object construction, earliest possible point
- Raise **custom exceptions**, not built-in exceptions — e.g. `ConfigurationError`, not `ValueError`
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

### Arrow context cleanup
- Release on **checkin + error/close** — any path that ends a connection lifecycle must release the allocator (no leak possible regardless of failure mode)
- Memory leak validation test: track allocator ref count across N checkout/query/checkin cycles; verify count returns to baseline after all connections checked in
- Cleanup ownership (connection wrapper vs pool event listeners): **Claude's discretion**

### Public API surface
- Export from top-level `adbc_poolhouse`: `create_pool`, `DuckDBConfig`, `PoolhouseError`, `ConfigurationError`, and any type aliases/protocols useful for consumer type annotations
- Use explicit `__all__` in `__init__.py` to define the public contract
- Keep surface minimal — nothing beyond the above unless clearly needed
- Pool management helpers (e.g. `dispose_pool()`): **Claude's discretion** — only if they meaningfully improve ergonomics over calling `pool.dispose()` directly

### Claude's Discretion
- Where exactly cleanup is wired (connection wrapper vs event listeners)
- Whether any pool management helpers are added
- Type alias and protocol names and structure

</decisions>

<specifics>
## Specific Ideas

- Custom exceptions as a general library rule — don't use built-in exception types directly; define a `PoolhouseError` base and subtypes
- `ConfigurationError` should satisfy both custom exception rule and `ValueError` compatibility (dual inheritance)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-pool-factory-and-duckdb-integration*
*Context gathered: 2026-02-25*
