---
phase: 04-translation-and-driver-detection
plan: "02"
subsystem: translator
tags: [adbc, snowflake, databricks, redshift, trino, mssql, teradata, translator, pure-function]

# Dependency graph
requires:
  - phase: 03-config-layer
    provides: "SnowflakeConfig, DatabricksConfig, RedshiftConfig, TrinoConfig, MSSQLConfig, TeradataConfig typed models"
provides:
  - "translate_snowflake() pure function mapping 28 SnowflakeConfig fields to verified ADBC key strings"
  - "translate_databricks() pure function (URI-only, SecretStr extraction)"
  - "translate_redshift() pure function (URI-only, plain str)"
  - "translate_trino() pure function (URI-first, decomposed field fallback)"
  - "translate_mssql() pure function (URI-first, decomposed field fallback)"
  - "translate_teradata() pure function (URI-first, LOW confidence field names)"
affects:
  - _translators.py coordinator (04-03 or later)
  - Phase 5 create_pool() pool assembly
  - TEST-05 translator unit tests

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure translator pattern: TYPE_CHECKING import block, no ADBC driver imports, return dict[str, str]"
    - "URI-first pattern for Foundry backends: if uri set, return early; else map individual fields"
    - "SecretStr extraction: .get_secret_value() for sensitive fields, pragma allowlist secret on those lines"
    - "bool -> str conversion: str(val).lower() produces 'true'/'false' strings for ADBC"
    - "schema_ trailing underscore: config.schema_ attribute -> ADBC key without underscore"

key-files:
  created:
    - src/adbc_poolhouse/_snowflake_translator.py
    - src/adbc_poolhouse/_databricks_translator.py
    - src/adbc_poolhouse/_redshift_translator.py
    - src/adbc_poolhouse/_trino_translator.py
    - src/adbc_poolhouse/_mssql_translator.py
    - src/adbc_poolhouse/_teradata_translator.py
  modified: []

key-decisions:
  - "TYPE_CHECKING block for config imports in translators — safe because translators are not Pydantic models (unlike Phase 3 config files where runtime import was needed)"
  - "Trino and MSSQL include decomposed field mappings with URI-first pattern — plan said URI-only but configs have full decomposed field sets"
  - "Teradata translator uses URI-first with decomposed field fallback (host/user/password/database/port/logmech/tmode/sslmode) — all LOW confidence; dbs_port key from teradatasql naming"
  - "Snowflake translator already committed in plan 04-01 run (included in BigQuery/FlightSQL commit as fix for TC001/E501)"

patterns-established:
  - "Pattern: module docstrings use D213 format (summary on second line after opening quotes)"
  - "Pattern: pragma allowlist secret on comment line above the actual secret usage (not inline after long lines)"

requirements-completed: [TRANS-02, TRANS-04, TRANS-05]

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 04 Plan 02: Snowflake and Foundry Translators Summary

**Six pure translator functions (Snowflake 28-field ADBC key mapping + URI-based Databricks/Redshift/Trino/MSSQL/Teradata) with no driver imports, all values as strings**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-02-24T13:57:25Z
- **Completed:** 2026-02-24T14:04:33Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Implemented `translate_snowflake()` mapping all 28 SnowflakeConfig fields to verified ADBC key strings (plain `"username"`/`"password"` keys, not prefixed; `schema_` attribute to `"adbc.snowflake.sql.schema"` key; six boolean flags always included as `"true"`/`"false"` strings)
- Implemented five Foundry backend translators (Databricks, Redshift, Trino, MSSQL, Teradata) — all return `dict[str, str]`, no ADBC driver imports, URI-first pattern with decomposed field fallback for Trino/MSSQL/Teradata
- All six translators pass ruff, basedpyright, and import cleanly without ADBC drivers installed

## Task Commits

Each task was committed atomically:

1. **Task 1: Snowflake translator** - `710261e` (feat) — Note: committed during 04-01 run as "Also fix _snowflake_translator.py"
2. **Task 2: Foundry backend translators** - `96806c8` (feat)

**Plan metadata:** (see final commit below)

## Files Created/Modified

- `src/adbc_poolhouse/_snowflake_translator.py` - translate_snowflake() with all 28 field mappings, verified ADBC keys
- `src/adbc_poolhouse/_databricks_translator.py` - translate_databricks() URI-only, SecretStr extraction
- `src/adbc_poolhouse/_redshift_translator.py` - translate_redshift() URI-only, plain str
- `src/adbc_poolhouse/_trino_translator.py` - translate_trino() URI-first with decomposed fallback (ssl booleans)
- `src/adbc_poolhouse/_mssql_translator.py` - translate_mssql() URI-first with decomposed fallback (trustServerCertificate bool)
- `src/adbc_poolhouse/_teradata_translator.py` - translate_teradata() URI-first with decomposed fallback, LOW confidence TODO comment

## Decisions Made

- **TYPE_CHECKING block for config imports**: translators are not Pydantic models so annotations are resolved at type-check time only; no runtime import needed. Unlike Phase 3 config files (which needed `# noqa: TC003`), translators safely use `if TYPE_CHECKING:` block.
- **Trino and MSSQL use URI-first with decomposed fields**: The plan described them as "URI-only" but the actual configs have full decomposed field sets (host, port, user, password, catalog, schema_, ssl, etc.). Implemented URI-first pattern (returns early if uri set) with individual field mapping as fallback — more complete implementation aligned with the config model.
- **Teradata `dbs_port` key**: teradatasql Python driver uses `dbs_port` (not `port`) for the connection port parameter. Used this as the most likely correct key name with LOW confidence comment.
- **Snowflake translator in TYPE_CHECKING block**: ruff TC001 rule requires application imports in TYPE_CHECKING block when `from __future__ import annotations` is used. Fixed during pre-commit hook in plan 04-01.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] Trino and MSSQL decomposed field mapping**
- **Found during:** Task 2 (Foundry backend translators)
- **Issue:** Plan said these backends are "URI-only" but the actual TrinoConfig and MSSQLConfig have full decomposed field sets (host, port, user, password, catalog, schema_, ssl flags, etc.)
- **Fix:** Implemented URI-first pattern returning early if uri is set, then full decomposed field mapping as fallback. This ensures the translator is complete and usable without a prebuilt URI.
- **Files modified:** _trino_translator.py, _mssql_translator.py
- **Verification:** All fields correctly typed as strings; ruff passes; verification script passes
- **Committed in:** 96806c8

---

**Total deviations:** 1 auto-fixed (Rule 2 - missing functionality for decomposed field support)
**Impact on plan:** No scope creep — the fix makes translators more complete and consistent with the config model. URI-first ensures backward compatibility with pure URI usage.

## Issues Encountered

- Pre-commit hooks reformatted translator files (TC001, D213, E501 ruff violations). Fixed by: using TYPE_CHECKING block for imports, wrapping long bool conversion lines, D213-compliant module docstring format (opening `"""` on its own line for multi-line docstrings).
- Snowflake translator was already committed in plan 04-01 run (included as a fix in the BigQuery/FlightSQL commit `710261e`). No re-commit needed for Task 1.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All six translator files ready for use by `_translators.py` coordinator (dispatch function)
- Foundry translator key names for Trino, MSSQL, Teradata are LOW confidence — verify against installed Foundry driver before production use
- TEST-05 (translator unit tests) can now be implemented against these translator functions
- Phase 5 create_pool() can use translate_snowflake() output as db_kwargs for adbc_driver_manager.dbapi.connect()

---
*Phase: 04-translation-and-driver-detection*
*Completed: 2026-02-24*
