---
phase: 04-translation-and-driver-detection
plan: "04"
subsystem: testing
tags: [adbc, translators, tdd, pytest, pure-functions]

# Dependency graph
requires:
  - phase: 04-01
    provides: "4 PyPI translator functions (DuckDB, PostgreSQL, BigQuery, FlightSQL)"
  - phase: 04-02
    provides: "6 Foundry translator functions (Snowflake + Databricks, Redshift, Trino, MSSQL, Teradata)"
  - phase: 04-03
    provides: "translate_config() coordinator + resolve_driver() + create_adbc_connection()"
provides:
  - "tests/test_translators.py: 32 unit tests asserting exact dict[str,str] output for all 10 warehouse translators"
  - "tests/test_drivers.py: 11 unit tests for resolve_driver() 3-path detection and DRIV-03 NOT_FOUND reraise"
affects:
  - phase-05-pool-assembly
  - phase-06-snowflake-snapshots
  - phase-07-foundry-drivers

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SnowflakeConfig.schema_ must be constructed via model_validate({'schema': 'X'}) not schema_='X' kwarg (validation_alias='schema')"
    - "# pragma: allowlist secret on variable lines holding credential-like strings, not inline in constructor calls"
    - "FlightSQLConfig empty-dict case: tls_skip_verify and with_cookie_middleware always emitted as bool defaults"

key-files:
  created:
    - tests/test_translators.py
    - tests/test_drivers.py
  modified: []

key-decisions:
  - "SnowflakeConfig.schema_ passed via model_validate() — validation_alias='schema' means keyword arg schema_='X' raises extra_forbidden ValidationError; test uses model_validate({'account': 'a', 'schema': 'PUBLIC'})"
  - "FlightSQLConfig() empty result contains 2 keys (tls_skip_verify and with_cookie_middleware bool defaults) — not an empty dict; tests assert exact expected set"

patterns-established:
  - "Pure function translators require no mocking — instantiate config directly and call translator, assert exact dict output"
  - "detect-secrets # pragma: allowlist secret on variable assignment lines for credential-like test strings"

requirements-completed: [TEST-05]

# Metrics
duration: 5min
completed: 2026-02-24
---

# Phase 4 Plan 04: Translator Unit Tests Summary

**32 pytest tests asserting exact dict[str,str] output for all 10 warehouse ADBC parameter translators plus coordinator dispatch — zero mocking, no driver install required**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-24T12:34:46Z
- **Completed:** 2026-02-24T12:40:00Z
- **Tasks:** 1 (TDD: RED + GREEN in single round; translators pre-existed)
- **Files modified:** 1 created (test_translators.py)

## Accomplishments

- `tests/test_translators.py` with 32 tests across all 10 warehouse translators (DuckDB 4, Snowflake 5, BigQuery 3, PostgreSQL 3, FlightSQL 3, Databricks 2, Redshift 2, Trino 3, MSSQL 2, Teradata 2) plus coordinator dispatch (3)
- All tests assert exact `dict[str, str]` output — no subset checks, no "contains" checks except where keys are always-present booleans
- Tests document ADBC key naming contracts: `schema_` vs `adbc.snowflake.sql.schema`, `path` vs `database`, `access_mode` = `"READ_ONLY"`, etc.
- No ADBC warehouse driver install needed — pure function translators imported directly

## Task Commits

1. **RED: Add failing translator unit tests** - `53c55b1` (test)

(GREEN: All tests already passed — translators pre-existed from plans 04-01 and 04-02. No GREEN commit needed.)

**Plan metadata:** (pending — this commit)

## Files Created/Modified

- `tests/test_translators.py` - 32 unit tests for all 10 warehouse ADBC parameter translators plus translate_config() coordinator dispatch
- `tests/test_drivers.py` - 11 unit tests for resolve_driver() 3-path detection (included from prior work, committed as `3e5b516`)

## Decisions Made

- **SnowflakeConfig.schema_ requires model_validate():** `schema_` has `validation_alias="schema"` — Pydantic rejects `schema_="PUBLIC"` as a keyword arg (extra_forbidden). Tests use `SnowflakeConfig.model_validate({"account": "a", "schema": "PUBLIC"})` for correctness. This is now the established pattern for testing any config field with a validation_alias.

- **FlightSQLConfig() is NOT empty dict:** Two bool fields (`tls_skip_verify=False`, `with_cookie_middleware=False`) always emit as `'false'`/`'false'` strings. The test for `FlightSQLConfig()` asserts exactly `{"adbc.flight.sql.client_option.tls_skip_verify": "false", "adbc.flight.sql.rpc.with_cookie_middleware": "false"}`, not `{}`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SnowflakeConfig schema_ keyword arg raises ValidationError**
- **Found during:** RED phase (first pytest run)
- **Issue:** `SnowflakeConfig(account="a", schema_="PUBLIC")` raises `pydantic_core.ValidationError: Extra inputs are not permitted` — `schema_` has `validation_alias="schema"` so the field name at construction is `schema`, not `schema_`
- **Fix:** Changed test to use `SnowflakeConfig.model_validate({"account": "a", "schema": "PUBLIC"})` — the correct pattern for fields with validation aliases
- **Files modified:** tests/test_translators.py
- **Verification:** 32 tests pass after fix; prek passes with zero violations
- **Committed in:** `53c55b1` (test RED commit, after fix)

**2. [Rule 1 - Bug] ruff auto-fixed 16 style issues in test_translators.py**
- **Found during:** First commit attempt (prek/ruff hook)
- **Issue:** ruff auto-fixed 16 errors (import ordering, docstring style) and reformatted 1 file
- **Fix:** Re-staged auto-fixed file and committed on second attempt
- **Files modified:** tests/test_translators.py
- **Verification:** prek passes cleanly on second commit
- **Committed in:** `53c55b1` (second attempt)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — test construction error + ruff formatting)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered

- `test_drivers.py` was found untracked in the working tree, committed as part of a separate prior operation (`3e5b516 feat(04-05): all driver detection tests pass`). This file was left uncommitted from plan 04-03 execution and was picked up during this plan's execution.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 10 warehouse parameter translators have regression tests asserting exact ADBC key mapping contracts
- `tests/test_drivers.py` covers `resolve_driver()` and `create_adbc_connection()` DRIV-03 behavior
- Phase 5 (pool assembly) can proceed with confidence that translator + driver detection layer is tested
- Phase 6 (Snowflake snapshots) — syrupy serializer design still needs validation against real driver

---
*Phase: 04-translation-and-driver-detection*
*Completed: 2026-02-24*

## Self-Check: PASSED

- FOUND: tests/test_translators.py
- FOUND: .planning/phases/04-translation-and-driver-detection/04-04-SUMMARY.md
- FOUND commit: 53c55b1 (RED: test_translators.py — 32 tests)
