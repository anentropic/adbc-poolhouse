---
phase: 03-config-layer
plan: 01
subsystem: config
tags: [pydantic-settings, pydantic, abc, protocol, duckdb, config]

# Dependency graph
requires:
  - phase: 02-dependency-declarations
    provides: pydantic-settings runtime dependency declared in pyproject.toml
provides:
  - BaseWarehouseConfig abstract base class with pool tuning fields
  - WarehouseConfig runtime_checkable Protocol for downstream type annotations
  - DuckDBConfig concrete config with in-memory pool_size=1 validator
affects:
  - 03-config-layer (all remaining plans use BaseWarehouseConfig)
  - 04-driver-detection (translates config fields to ADBC kwargs)
  - 05-pool-factory (accepts WarehouseConfig Protocol, creates QueuePool)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - BaseWarehouseConfig(BaseSettings, abc.ABC) with pool tuning defaults
    - WarehouseConfig @runtime_checkable Protocol for structural typing
    - DuckDBConfig env_prefix='DUCKDB_' applies to all inherited fields
    - model_validator(mode='after') raises ValueError wrapped into ValidationError

key-files:
  created:
    - src/adbc_poolhouse/_base_config.py
    - src/adbc_poolhouse/_duckdb_config.py
  modified: []

key-decisions:
  - "DuckDBConfig.pool_size defaults to 1 (not base default of 5) — in-memory DuckDB isolates each connection to a different empty DB; pool_size=1 is the only correct default"
  - "typing_extensions.Self replaced by stdlib typing.Self by ruff (Python 3.14 project target)"

patterns-established:
  - "Concrete config declares model_config = SettingsConfigDict(env_prefix='WAREHOUSE_') — env_prefix applies to all fields including inherited pool tuning fields"
  - "Abstract sentinel _adbc_driver_key() on base prevents direct instantiation without exposing public interface"

requirements-completed: [CFG-01, CFG-02, CFG-07]

# Metrics
duration: 8min
completed: 2026-02-24
---

# Phase 3 Plan 01: Config Layer Foundation Summary

**BaseWarehouseConfig abstract base + WarehouseConfig Protocol + DuckDBConfig with in-memory pool isolation validator using pydantic-settings v2**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-24T06:07:48Z
- **Completed:** 2026-02-24T06:15:48Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `BaseWarehouseConfig(BaseSettings, abc.ABC)` with pool tuning fields (pool_size=5, max_overflow=3, timeout=30, recycle=3600) — cannot be instantiated directly
- `WarehouseConfig` @runtime_checkable Protocol with the four pool tuning field signatures — enables downstream `config: WarehouseConfig` type annotations without importing concrete classes
- `DuckDBConfig` inheriting `BaseWarehouseConfig` with DUCKDB_ env_prefix — env prefix applies to inherited pool tuning fields automatically
- `check_memory_pool_size` model_validator prevents pool_size > 1 with in-memory DuckDB, where each connection would see an isolated empty database

## Task Commits

Each task was committed atomically:

1. **Task 1: Create _base_config.py with BaseWarehouseConfig and WarehouseConfig Protocol** - `e4822e2` (feat)
2. **Task 2: Create _duckdb_config.py with DuckDBConfig and in-memory pool_size validator** - `cc76ab7` (feat)

## Files Created/Modified

- `src/adbc_poolhouse/_base_config.py` - BaseWarehouseConfig(BaseSettings, abc.ABC) + WarehouseConfig Protocol; exports both symbols
- `src/adbc_poolhouse/_duckdb_config.py` - DuckDBConfig with DUCKDB_ env_prefix, database/read_only fields, pool_size=1 default, and check_memory_pool_size validator

## Decisions Made

- **DuckDBConfig.pool_size defaults to 1:** The plan's must_have stated pool_size=5 (base default) but the validator rejects pool_size > 1 with database=':memory:'. These are contradictory since DuckDB defaults to in-memory. The design intent (validator enforces pool_size=1 for in-memory) takes precedence — DuckDB overrides pool_size default to 1. This is the only consistent interpretation given the validator semantics and the docstring hint "in-memory, pool_size=1 enforced by validator" in the plan.
- **typing.Self from stdlib:** ruff upgraded `typing_extensions.Self` to `typing.Self` since the project targets Python 3.14 where it is available in stdlib.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DuckDBConfig.pool_size default changed from 5 (base) to 1**
- **Found during:** Task 2 (DuckDBConfig implementation and verification)
- **Issue:** Plan must_have stated `DuckDBConfig()` constructs with `pool_size=5`, but the `check_memory_pool_size` validator rejects `pool_size > 1` when `database=':memory:'`. With `database=':memory:'` as default and `pool_size=5` as inherited default, `DuckDBConfig()` always raises `ValidationError`. The must_have was internally contradictory.
- **Fix:** Overrode `pool_size: int = 1` in `DuckDBConfig` — in-memory DuckDB connections are isolated (each sees a different empty DB), so pool_size=1 is the only valid default. Field docstring explains the design rationale.
- **Files modified:** `src/adbc_poolhouse/_duckdb_config.py`
- **Verification:** `DuckDBConfig()` constructs successfully; `DuckDBConfig(database=':memory:', pool_size=2)` raises `ValidationError`; `DuckDBConfig(database='/tmp/x.db', pool_size=5)` succeeds
- **Committed in:** `cc76ab7` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — planning error in must_have)
**Impact on plan:** Fix was necessary for correctness — the plan's default values were self-contradictory. No scope creep; core design intent preserved.

## Issues Encountered

- Ruff auto-fixed docstring formatting and upgraded `typing_extensions.Self` → `typing.Self` on both files during pre-commit. Required re-staging and re-committing twice. No functional impact.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `BaseWarehouseConfig` and `WarehouseConfig` available for all remaining Phase 3 plans (Plans 02-05 for remaining warehouse configs)
- `DuckDBConfig` validates the end-to-end pattern: env_prefix inheritance, abstract base enforcement, Protocol isinstance check
- Phase 4 (driver detection) can rely on `_adbc_driver_key()` interface and `WarehouseConfig` Protocol
- Phase 5 (pool factory) can accept `config: WarehouseConfig` parameter

---
*Phase: 03-config-layer*
*Completed: 2026-02-24*
