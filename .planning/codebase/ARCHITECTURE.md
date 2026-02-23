# Architecture

**Analysis Date:** 2026-02-23

## Pattern Overview

**Overall:** Single-responsibility library — typed config in, pooled ADBC connection out.

This is a pre-implementation scaffold. The public API and internal layers are fully designed
(see `_notes/design-discussion.md`) but no production code exists yet beyond the package
skeleton (`src/adbc_poolhouse/__init__.py` with empty `__all__`).

**Key Characteristics:**
- One function per pool: `create_pool(config) -> QueuePool`
- No global state, no multi-warehouse orchestration, no query execution
- Config models are Pydantic BaseSettings (typed, validated, env-var-friendly)
- Pool implementation wraps SQLAlchemy `QueuePool` around ADBC dbapi connections
- Driver detection: try PyPI package import first, fall back to `adbc_driver_manager` (Foundry)

## Intended Layers (from design docs)

**Config Layer:**
- Purpose: Typed, validated per-warehouse configuration models
- Location: `src/adbc_poolhouse/` (to be implemented)
- Contains: Pydantic BaseSettings subclasses per warehouse type (e.g. `SnowflakeConfig`, `DuckDBConfig`)
- Depends on: `pydantic-settings`
- Used by: Parameter translation layer; consumers directly

**Parameter Translation Layer:**
- Purpose: Maps config fields to ADBC driver kwargs
- Location: `src/adbc_poolhouse/` (to be implemented)
- Contains: One translator function per warehouse type
- Example mapping: `SnowflakeConfig.account` → `adbc.snowflake.sql.account`
- Depends on: Config layer
- Used by: Pool factory

**Driver Detection Layer:**
- Purpose: Locate and load the correct ADBC driver for a given warehouse type
- Location: `src/adbc_poolhouse/` (to be implemented)
- Contains: Driver resolution logic; helpful error messages when driver not installed
- Strategy: Try PyPI package import (e.g. `adbc_driver_snowflake`), fall back to `adbc_driver_manager`
- Depends on: Config layer (to know which driver to find)
- Used by: Pool factory

**Pool Factory:**
- Purpose: Assemble a SQLAlchemy QueuePool wrapping ADBC dbapi connections
- Location: `src/adbc_poolhouse/` (to be implemented)
- Contains: `create_pool()` function — the primary public API
- Depends on: Config, parameter translation, driver detection layers
- Used by: Library consumers

## Data Flow

**Pool Creation:**

1. Consumer constructs a typed warehouse config (e.g. `SnowflakeConfig(account="xy123", ...)`)
2. Consumer calls `create_pool(config)`
3. Library translates config fields to ADBC driver kwargs
4. Library detects and loads the appropriate ADBC driver
5. Library constructs a SQLAlchemy `QueuePool` with `adbc_driver_manager.dbapi.connect` as the creator
6. Consumer receives the pool, borrows connections to execute queries

**Consumer usage (from design docs):**

```python
from adbc_poolhouse import SnowflakeConfig, create_pool

config = SnowflakeConfig(account="xy123", warehouse="COMPUTE_WH", ...)
pool = create_pool(config)

# Consumer executes queries:
with pool.connect() as conn:
    conn.execute(...)
```

**State Management:**
- No global state in this library
- Pool object is owned and managed entirely by the consumer
- Multiple warehouses: consumer calls `create_pool()` once per warehouse and manages the resulting dict of pools

## Key Abstractions

**Warehouse Config (planned):**
- Purpose: Typed, validated configuration for a specific warehouse backend
- Examples: `SnowflakeConfig`, `DuckDBConfig`, `BigQueryConfig` (to be created in `src/adbc_poolhouse/`)
- Pattern: Pydantic `BaseSettings` subclass; fields map 1:1 to ADBC driver kwargs after translation

**`create_pool()` (planned):**
- Purpose: Single entry point — takes any supported config, returns a ready-to-use pool
- Location: `src/adbc_poolhouse/__init__.py` (to be exported via `__all__`)
- Pattern: Factory function dispatching on config type

**Pool Configuration (planned):**
- Purpose: Tune SQLAlchemy QueuePool behaviour (size, overflow, pre-ping, recycle)
- Default pool settings from design docs:
  - `pool_size=5`, `max_overflow=3`, `timeout=30`, `pool_pre_ping=True`, `recycle=3600`

## Entry Points

**Public API:**
- Location: `src/adbc_poolhouse/__init__.py`
- Current state: Empty `__all__ = []` — no public symbols yet
- Planned exports: Config model classes + `create_pool` function
- Consumers import directly: `from adbc_poolhouse import SnowflakeConfig, create_pool`

## Error Handling

**Strategy:** Raise informative errors when prerequisites are missing (designed, not yet implemented)

**Patterns:**
- Missing ADBC driver: raise with install instructions (e.g. `pip install adbc-driver-snowflake`)
- Invalid config: Pydantic validation errors surface at construction time

## Cross-Cutting Concerns

**Logging:** Not yet defined
**Validation:** Pydantic at config construction time
**Authentication:** Delegated to ADBC drivers and config field values; no auth logic in this library

## Warehouse Coverage Roadmap

| Warehouse | Driver Source | Priority |
|-----------|--------------|----------|
| DuckDB | Apache (`duckdb`) | v1 — dev/test |
| Snowflake | Apache (`adbc-driver-snowflake`) | v1 — production |
| BigQuery | Apache (`adbc-driver-bigquery`) | Future |
| PostgreSQL | Apache (`adbc-driver-postgresql`) | Future |
| Databricks | Foundry (`dbc install databricks`) | Future |
| Redshift | Foundry | Future |

Adding a new warehouse = one new config model + one new translator function.

---

*Architecture analysis: 2026-02-23*
