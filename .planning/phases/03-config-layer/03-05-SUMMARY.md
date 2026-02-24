---
phase: 03-config-layer
plan: 05
subsystem: config
tags: [pydantic-settings, pydantic, mssql, teradata, config, azure, foundry]

# Dependency graph
requires:
  - phase: 03-config-layer
    plan: 01
    provides: BaseWarehouseConfig abstract base class and WarehouseConfig Protocol

provides:
  - MSSQLConfig for all Microsoft SQL variants (SQL Server, Azure SQL, Azure Fabric, Synapse Analytics)
  - TeradataConfig for Teradata with LOW-confidence triangulated fields and source attribution docstrings

affects:
  - 04-driver-detection (MSSQLConfig._adbc_driver_key='mssql', TeradataConfig._adbc_driver_key='teradata')
  - 05-pool-factory (both accept WarehouseConfig Protocol parameter)
  - 07-foundry-installation (both drivers are Foundry-distributed, not on PyPI)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - MSSQLConfig covers all Microsoft SQL variants in one class via optional variant-specific fields (fedauth for Azure)
    - TeradataConfig fields carry "Source: ... Verify against Columnar ADBC driver." attribution in every docstring
    - Module-level TODO comment + class-level .. warning:: RST directive for LOW-confidence Foundry driver fields
    - SecretStr with # noqa: TC002 — kept as runtime import (not TYPE_CHECKING) since Pydantic resolves at class-creation time

key-files:
  created:
    - src/adbc_poolhouse/_mssql_config.py
    - src/adbc_poolhouse/_teradata_config.py
  modified: []

key-decisions:
  - "MSSQLConfig is one class covering SQL Server, Azure SQL, Azure Fabric, and Synapse Analytics — not separate classes per variant (locked CONTEXT.md decision)"
  - "TeradataConfig fields are LOW confidence — triangulated from Teradata JDBC and teradatasql Python driver docs because Columnar ADBC Teradata driver docs returned 404; each field has source attribution docstring"
  - "SecretStr import uses # noqa: TC002 rather than TYPE_CHECKING block — Pydantic BaseSettings resolves field annotations at class-creation time making runtime import necessary"
  - "fedauth docstring notes MEDIUM confidence for specific value names (ActiveDirectoryPassword, etc.) sourced from deepwiki.com/columnar-tech/adbc-quickstarts"

patterns-established:
  - "LOW-confidence driver fields use module-level # TODO comment + class-level .. warning:: RST directive to signal verification required before production use"
  - "URI docstring examples with embedded credentials use # pragma: allowlist secret to bypass detect-secrets false positives"

requirements-completed: [CFG-06]

# Metrics
duration: 5min
completed: 2026-02-24
---

# Phase 3 Plan 05: MSSQL and Teradata Config Summary

**MSSQLConfig (HIGH confidence, one class for all SQL Server/Azure variants) and TeradataConfig (LOW confidence, triangulated fields with source attribution) completing CFG-06**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-02-24T~
- **Completed:** 2026-02-24
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `MSSQLConfig` covers SQL Server, Azure SQL, Azure Fabric, and Synapse Analytics in a single class — locked CONTEXT.md decision honored; `fedauth` field enables Entra ID / Azure AD authentication for Azure variants
- `TeradataConfig` with all 9 fields carrying per-field source attribution ("Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.") — module-level TODO and class-level `.. warning::` document LOW confidence status
- Both configs: all fields optional, `password` is `SecretStr` from env var (`MSSQL_PASSWORD` / `TERADATA_PASSWORD`), `pool_size=5` default inherited from base, `isinstance(obj, WarehouseConfig)` passes Protocol check

## Task Commits

Each task was committed atomically:

1. **Task 1: Create _mssql_config.py** - `2799961` (feat)
2. **Task 2: Create _teradata_config.py with source attribution docstrings** - `4c09d34` (feat)

## Files Created/Modified

- `src/adbc_poolhouse/_mssql_config.py` - MSSQLConfig(BaseWarehouseConfig) with MSSQL_ env_prefix; covers SQL Server/Azure SQL via host+port+instance, Azure Fabric/Synapse via fedauth; trust_server_certificate defaults False
- `src/adbc_poolhouse/_teradata_config.py` - TeradataConfig(BaseWarehouseConfig) with TERADATA_ env_prefix; 9 triangulated fields (host, user, password, database, port, logmech, tmode, sslmode, uri); module-level TODO + class warning

## Decisions Made

- **One class for all SQL Server variants:** Honored the locked CONTEXT.md decision — `MSSQLConfig` covers SQL Server, Azure SQL, Azure Fabric, and Synapse Analytics via optional variant-specific fields rather than separate classes.
- **TeradataConfig field confidence:** Fields are triangulated from Teradata JDBC and teradatasql Python driver docs because the Columnar ADBC Teradata driver documentation returned 404 at research time. Every field has explicit source attribution and "Verify against Columnar ADBC driver" note.
- **SecretStr `# noqa: TC002`:** Ruff's TC002 rule flags SecretStr as a type-only import that should go in `TYPE_CHECKING` block. However, Pydantic BaseSettings resolves field annotations at class-creation time (not lazily), making runtime import necessary. Used `# noqa: TC002` suppression to keep it as a runtime import.
- **fedauth value confidence:** Values like `'ActiveDirectoryPassword'`, `'ActiveDirectoryMsi'` are MEDIUM confidence sourced from deepwiki.com/columnar-tech/adbc-quickstarts/4.1-microsoft-sql-server — noted in docstring for future verification.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added # noqa: TC002 to SecretStr import in both files**
- **Found during:** Task 1 and Task 2 (pre-commit hook execution)
- **Issue:** Ruff TC002 rule flagged `from pydantic import SecretStr` as a type-only import requiring placement in `TYPE_CHECKING` block. However, Pydantic resolves BaseSettings field annotations at class-creation time (not lazily), so moving it to TYPE_CHECKING would break runtime field resolution.
- **Fix:** Added `# noqa: TC002` to the `SecretStr` import line in both files to suppress the ruff warning while preserving correct runtime behavior.
- **Files modified:** `src/adbc_poolhouse/_mssql_config.py`, `src/adbc_poolhouse/_teradata_config.py`
- **Verification:** Both `MSSQLConfig()` and `TeradataConfig()` construct without errors; `password` field correctly typed as `SecretStr | None`
- **Committed in:** `2799961` (Task 1) and `4c09d34` (Task 2)

**2. [Rule 2 - Missing Critical] Added # pragma: allowlist secret to MSSQL URI docstring**
- **Found during:** Task 1 (pre-commit hook execution)
- **Issue:** detect-secrets flagged the URI docstring example `mssql://user:pass@host[:port]...` as a potential "Basic Auth Credentials" secret — false positive on documentation example.
- **Fix:** Added `# pragma: allowlist secret` inline comment to the URI docstring line and rephrased the example slightly to avoid the triggering pattern.
- **Files modified:** `src/adbc_poolhouse/_mssql_config.py`
- **Verification:** detect-secrets hook passes
- **Committed in:** `2799961` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 2 — linter/security tooling compliance for correctness)
**Impact on plan:** Both fixes necessary for pre-commit hook compliance. No scope creep; no behavioral change.

## Issues Encountered

- Pre-commit hooks modified files during commit attempts (ruff reformatted docstrings from inline to triple-quoted style). Required re-staging and re-committing on both tasks — standard pattern per 03-01-SUMMARY.md Issue notes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All five Phase 3 config classes are now complete: `DuckDBConfig`, `SnowflakeConfig`, `PostgreSQLConfig`, `BigQueryConfig`, `DatabricksConfig`/`RedshiftConfig`/`TrinoConfig` (Plans 02-04), `MSSQLConfig`, `TeradataConfig`
- Phase 4 (driver detection) can use `_adbc_driver_key()` from all configs
- Phase 5 (pool factory) can accept all configs via `WarehouseConfig` Protocol
- TeradataConfig fields should be verified against the Columnar ADBC driver when available (Phase 7)

---
## Self-Check

- FOUND: src/adbc_poolhouse/_mssql_config.py
- FOUND: src/adbc_poolhouse/_teradata_config.py
- FOUND: .planning/phases/03-config-layer/03-05-SUMMARY.md (this file)

## Self-Check: PASSED

---
*Phase: 03-config-layer*
*Completed: 2026-02-24*
