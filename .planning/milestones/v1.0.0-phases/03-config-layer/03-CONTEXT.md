# Phase 3: Config Layer - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Typed, validated, environment-variable-friendly config models for every supported warehouse backend (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, Teradata). ADBC and SQLAlchemy code is explicitly out of scope — configs must be constructible with only pydantic-settings installed.

</domain>

<decisions>
## Implementation Decisions

### Module layout
- Internal implementation: per-warehouse files (`_duckdb_config.py`, `_snowflake_config.py`, `_bigquery_config.py`, etc.) — one file per warehouse backend
- Public API: all config models re-exported from `adbc_poolhouse.__init__` — consumers use `from adbc_poolhouse import DuckDBConfig, SnowflakeConfig`
- A `WarehouseConfig` Protocol exported publicly from `adbc_poolhouse` — downstream code (e.g. Semantic ORM lib) type-annotates against it without importing every concrete class

### Inheritance structure
- `BaseWarehouseConfig(BaseSettings)` — public, abstract (cannot be instantiated directly), holds the shared pool tuning fields with library defaults
- Pool tuning fields on base: `pool_size`, `max_overflow`, `timeout`, `recycle` — all optional with defaults from POOL-02
- All concrete warehouse configs inherit from `BaseWarehouseConfig` — flat field layout, no nested composition
- This design means `DUCKDB_POOL_SIZE`, `SNOWFLAKE_POOL_SIZE` etc. all work naturally via env_prefix without custom delimiter config
- `BaseWarehouseConfig` is part of the public API (exported from `__init__`)

### Validation error messages
- Error messages are descriptive with diagnosis: explain WHAT went wrong and WHY it's a problem
- Mutual exclusivity errors include a fix hint (e.g. "use private_key_path for a file path or private_key_pem for PEM content, not both")
- Let Pydantic's `ValidationError` bubble through naturally — do NOT catch and re-raise as plain `ValueError`; our message appears inside the `ValidationError` context

### Foundry backend depth (CFG-06)
- Researcher investigates BOTH the ADBC driver source/docs AND upstream warehouse docs (e.g. Databricks connection params, Teradata JDBC field names) to triangulate accurate field lists
- `MSSQLConfig`: one class covering SQL Server, Azure SQL, Fabric, and Synapse Analytics variants via optional variant-specific fields — NOT separate classes per variant
- When driver docs are sparse or ambiguous, include the field with a docstring note indicating the source of verification

### Claude's Discretion
- Exact field defaults for non-pool fields (e.g. default port values, optional vs required determination for lesser-used fields)
- Docstring style and content beyond what's captured in decisions above
- Field ordering within each config model

</decisions>

<specifics>
## Specific Ideas

- Configs are part of the public API and will be imported by downstream libraries (e.g. a Semantic ORM lib that instantiates configs and passes them to `create_pool`)
- The `WarehouseConfig` Protocol design mirrors how downstream consumers will want to accept "any warehouse config" in typed function signatures

</specifics>

<deferred>
## Deferred Ideas

- Dev tooling for installing Foundry-distributed drivers locally (Databricks, Redshift, Trino, MSSQL, Teradata are not on PyPI) — noted for a future phase or standalone tooling task. Phase 3 uses doc research only; actual driver installation tooling is out of scope here.

</deferred>

---

*Phase: 03-config-layer*
*Context gathered: 2026-02-24*
