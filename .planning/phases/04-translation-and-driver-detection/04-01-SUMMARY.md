---
phase: 04-translation-and-driver-detection
plan: "01"
subsystem: api
tags: [adbc, duckdb, bigquery, postgresql, flightsql, translator, pure-function]

# Dependency graph
requires:
  - phase: 03-config-layer
    provides: DuckDBConfig, BigQueryConfig, PostgreSQLConfig, FlightSQLConfig typed config classes

provides:
  - translate_duckdb() pure function mapping DuckDBConfig to ADBC driver kwargs dict
  - translate_postgresql() pure function mapping PostgreSQLConfig to ADBC driver kwargs dict
  - translate_bigquery() pure function mapping BigQueryConfig to ADBC driver kwargs dict
  - translate_flightsql() pure function mapping FlightSQLConfig to ADBC driver kwargs dict

affects:
  - 04-translation-and-driver-detection (remaining plans: _translators.py coordinator)
  - 05-pool-assembly (uses translator output as db_kwargs for dbapi.connect())

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure translator functions: config class in -> dict[str, str] out, zero ADBC driver imports"
    - "TYPE_CHECKING guard for config imports: from __future__ import annotations + TYPE_CHECKING block satisfies ruff TC001"
    - "SecretStr extraction: always use .get_secret_value(), never str() on SecretStr"
    - "Bool to string: str(bool_val).lower() produces 'true'/'false' for ADBC kwargs"

key-files:
  created:
    - src/adbc_poolhouse/_duckdb_translator.py
    - src/adbc_poolhouse/_postgresql_translator.py
    - src/adbc_poolhouse/_bigquery_translator.py
    - src/adbc_poolhouse/_flightsql_translator.py
    - src/adbc_poolhouse/_snowflake_translator.py
  modified: []

key-decisions:
  - "TRANS-05: no ADBC driver imports in translator files — config imports go in TYPE_CHECKING block per ruff TC001"
  - "translate_postgresql omits use_copy: adbc.postgresql.use_copy is a StatementOptions key not a db_kwarg; Phase 5 must handle at cursor level"
  - "translate_flightsql always includes tls_skip_verify and with_cookie_middleware: bool fields with defaults (never None) so always output as 'true'/'false' strings"
  - "FlightSQL connect_timeout uses raw string key 'adbc.flight.sql.rpc.timeout_seconds.connect': documented in ADBC docs but absent from Python DatabaseOptions enum"

patterns-established:
  - "Translator pattern: kwargs: dict[str, str] = {...required...}; if config.field is not None: kwargs[key] = str(val)"
  - "Bool kwargs: str(config.bool_field).lower() — not bool directly; ADBC AdbcDatabase rejects non-string values"

requirements-completed: [TRANS-01, TRANS-03, TRANS-05]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 4 Plan 01: Translation Layer Summary

**Four pure translator functions (DuckDB, PostgreSQL, BigQuery, FlightSQL) mapping typed config instances to ADBC dict[str, str] driver kwargs with no ADBC driver imports at module level**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-02-24T12:17:15Z
- **Completed:** 2026-02-24T12:21:16Z
- **Tasks:** 2
- **Files modified:** 5 (4 created + 1 fixed pre-existing)

## Accomplishments

- Created `translate_duckdb`: maps `database` -> `"path"`, `read_only=True` -> `"access_mode": "READ_ONLY"`
- Created `translate_postgresql`: maps `uri` -> `"uri"`, intentionally omits `use_copy` (StatementOptions key)
- Created `translate_bigquery`: maps all 7 BigQueryConfig fields to `adbc.bigquery.sql.*` keys
- Created `translate_flightsql`: maps all 16 FlightSQLConfig fields to verified ADBC key strings
- Fixed pre-existing `_snowflake_translator.py`: moved config import to TYPE_CHECKING block (TC001), fixed E501 line lengths

## Task Commits

Each task was committed atomically:

1. **Task 1: DuckDB and PostgreSQL translators** - `9e2376a` (feat)
2. **Task 2: BigQuery and FlightSQL translators** - `710261e` (feat)

## Files Created/Modified

- `src/adbc_poolhouse/_duckdb_translator.py` - translate_duckdb() pure function
- `src/adbc_poolhouse/_postgresql_translator.py` - translate_postgresql() pure function
- `src/adbc_poolhouse/_bigquery_translator.py` - translate_bigquery() pure function
- `src/adbc_poolhouse/_flightsql_translator.py` - translate_flightsql() pure function
- `src/adbc_poolhouse/_snowflake_translator.py` - fixed TC001 + E501 violations (pre-existing)

## Decisions Made

- Config class imports placed in `TYPE_CHECKING` block in all translator files. With `from __future__ import annotations`, function parameter type annotations are lazy-evaluated strings, so the import is only needed at type-check time — not at runtime. ruff TC001 enforces this correctly.
- `translate_postgresql` intentionally omits `use_copy`. The `adbc.postgresql.use_copy` key is a `StatementOptions` key (per-statement, not per-database). Passing it to `dbapi.connect()` is incorrect. Phase 5 will need to apply it at the cursor level.
- `translate_flightsql` always emits `tls_skip_verify` and `with_cookie_middleware` as `"false"` by default. These fields have `bool = False` defaults — they are never `None` — so they always appear in the output dict.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Config imports moved to TYPE_CHECKING blocks**
- **Found during:** Task 1 (DuckDB and PostgreSQL translators — commit attempt)
- **Issue:** ruff TC001 flagged `from adbc_poolhouse._duckdb_config import DuckDBConfig` and `from adbc_poolhouse._postgresql_config import PostgreSQLConfig` as imports that should be in TYPE_CHECKING blocks
- **Fix:** Added `from typing import TYPE_CHECKING` and wrapped config imports in `if TYPE_CHECKING:` blocks in all four translator files
- **Files modified:** `_duckdb_translator.py`, `_postgresql_translator.py`, `_bigquery_translator.py`, `_flightsql_translator.py`
- **Verification:** ruff check passes, prek passes, translators still importable and functional at runtime
- **Committed in:** `9e2376a` (Task 1), `710261e` (Task 2)

**2. [Rule 1 - Bug] Fixed pre-existing _snowflake_translator.py ruff violations**
- **Found during:** Task 2 commit attempt (pre-commit hook scanned staged files including snowflake translator)
- **Issue:** `_snowflake_translator.py` (created in prior Phase 04 session) had TC001 violation and multiple E501 (line too long) violations
- **Fix:** Moved SnowflakeConfig import to TYPE_CHECKING block; wrapped long bool-to-string lines with parentheses
- **Files modified:** `_snowflake_translator.py`
- **Verification:** ruff check and ruff format pass; prek passes
- **Committed in:** `710261e` (Task 2)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - ruff linting bugs)
**Impact on plan:** Required for green prek. No behavioral change — TYPE_CHECKING imports are equivalent at runtime when `from __future__ import annotations` is present. No scope creep.

## Issues Encountered

- ruff TC001 rule was not anticipated in plan. With `from __future__ import annotations`, Pydantic config class imports in type annotations are purely for type-checking (not needed at runtime), so ruff correctly flags them as TYPE_CHECKING candidates. This differs from Pydantic config files where `SecretStr` must be at module level due to runtime annotation resolution.
- ruff-format pre-commit hook had stash/conflict issues when hook modified files that also had unstaged working-tree changes. Resolved by running `ruff format` manually and re-staging before commit.

## Next Phase Readiness

- All four translator functions are importable and return correct `dict[str, str]` with no ADBC driver imports
- Ready for Phase 4 Plan 02 (Snowflake translator — already partially created, needs verification) and _translators.py coordinator
- `translate_postgresql` omits `use_copy`: Phase 5 must apply `adbc.postgresql.use_copy` at cursor level, not at pool creation time

---
*Phase: 04-translation-and-driver-detection*
*Completed: 2026-02-24*
