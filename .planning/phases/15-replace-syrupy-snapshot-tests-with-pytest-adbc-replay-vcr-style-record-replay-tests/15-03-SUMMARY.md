---
phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests
plan: 03
subsystem: testing
tags: [pytest, cassettes, arrow, snowflake, databricks, integration-tests]

requires:
  - phase: 15-01
    provides: pytest-adbc-replay configured; adbc_cassette_dir = tests/cassettes
  - phase: 15-02
    provides: conftest.py Syrupy-free; pool fixtures present

provides:
  - 4 cassette-based integration tests (2 Snowflake, 2 Databricks) passing in CI without credentials
  - 12 synthetic cassette files under tests/cassettes/
  - test_databricks.py new test module

affects: []

tech-stack:
  added: []
  patterns:
    - "Arrow IPC File format (ipc.new_file) for cassette result storage"
    - "sqlglot.parse_one(sql).sql(pretty=True, normalize=True) for canonical SQL in cassette keys"
    - "Any type annotation + type: ignore[union-attr] for untyped ADBC driver APIs in strict basedpyright"

key-files:
  created:
    - tests/integration/test_databricks.py
    - tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_query.sql
    - tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_result.arrow
    - tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/000_params.json
    - tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_query.sql
    - tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_result.arrow
    - tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_params.json
    - tests/cassettes/databricks_health/adbc_driver_manager.dbapi/000_query.sql
    - tests/cassettes/databricks_health/adbc_driver_manager.dbapi/000_result.arrow
    - tests/cassettes/databricks_health/adbc_driver_manager.dbapi/000_params.json
    - tests/cassettes/databricks_arrow_round_trip/adbc_driver_manager.dbapi/000_query.sql
    - tests/cassettes/databricks_arrow_round_trip/adbc_driver_manager.dbapi/000_result.arrow
    - tests/cassettes/databricks_arrow_round_trip/adbc_driver_manager.dbapi/000_params.json
  modified:
    - tests/integration/test_snowflake.py

key-decisions:
  - "Cassette file naming: {prefix}_query.sql / {prefix}_result.arrow / {prefix}_params.json (not 000.sql/arrow/json as initially drafted)"
  - "SQL in cassette must be sqlglot-normalized: SELECT 1 → SELECT\\n  1 (pretty=True, normalize=True)"
  - "Arrow IPC File format (ipc.new_file) not Stream format — matches plugin's read_arrow_table() implementation"
  - "Any type + type: ignore[union-attr] used for ADBC connection/cursor in strict basedpyright to avoid reportUnknownMemberType"
  - "params.json trailing newline required by end-of-file-fixer pre-commit hook"

patterns-established:
  - "Cassette generation script: use sqlglot.parse_one(sql).sql(pretty=True, normalize=True) for SQL key"
  - "Cassette Arrow files: ipc.new_file() (IPC File format, seekable, with footer)"
  - "Integration tests: conn: Any = driver.connect() # type: ignore[union-attr] pattern for type safety"

requirements-completed: []

duration: 0min
completed: 2026-03-02
---

# Phase 15 Plan 03: Test Files and Cassettes Summary

**4 cassette-based integration tests (2 Snowflake + 2 Databricks) with 12 synthetic cassette files; all pass in CI without credentials; full suite 192 tests green**

## Performance

- **Duration:** 0 min (executed together with Plan 15-01 due to pre-commit constraint)
- **Started:** 2026-03-02T21:51:43Z
- **Completed:** 2026-03-02T22:00:00Z
- **Tasks:** 2
- **Files modified:** 2 (+ 12 created)

## Accomplishments

- Rewrote `test_snowflake.py` using `@pytest.mark.adbc_cassette`; no pool fixture dependency
- Created `test_databricks.py` with `test_connection_health` and `test_arrow_round_trip`
- Generated 12 synthetic cassette files with correct naming convention
- All 4 integration tests pass in replay mode without credentials
- Full test suite: 192 passed (188 unit + 4 integration)

## Task Commits

1. **Task 1: Generate cassette files** - `74b4845`
2. **Task 2: Rewrite test_snowflake.py, create test_databricks.py** - `74b4845`

## Files Created/Modified

- `tests/integration/test_snowflake.py` - Rewritten with @pytest.mark.adbc_cassette, Any type annotations
- `tests/integration/test_databricks.py` - New file with 2 cassette tests
- `tests/cassettes/` - 12 synthetic cassette files across 4 test directories

## Decisions Made

- **Cassette file naming:** Plugin uses `{prefix}_query.sql`, `{prefix}_result.arrow`, `{prefix}_params.json` — not `000.sql/arrow/json` as the plan initially assumed. Discovered by reading plugin source `_cassette_io.py`.
- **SQL normalization required:** The cassette lookup key is the sqlglot-normalized SQL. `SELECT 1` becomes `SELECT\n  1` via `sqlglot.parse_one(sql).sql(pretty=True, normalize=True)`. Initial cassettes with raw SQL caused `CassetteMissError`.
- **Arrow IPC File format:** Plugin uses `ipc.open_file()` (file format, not stream). Cassettes must use `ipc.new_file()`.
- **params.json trailing newline:** end-of-file-fixer pre-commit hook requires trailing newlines; `json.dumps(None) + '\n'` used.
- **Any type + type: ignore:** basedpyright strict mode requires type annotations for all variables. ADBC driver types are untyped; using `conn: Any = driver.connect() # type: ignore[union-attr]` pattern.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Cassette file naming incorrect**
- **Found during:** Task 1 — first integration test run with initial cassettes
- **Issue:** Generated `000.sql`, `000.arrow`, `000.json`; plugin expects `000_query.sql`, `000_result.arrow`, `000_params.json`
- **Fix:** Deleted and regenerated all 12 cassette files with correct naming
- **Verification:** All 4 tests passed after regeneration
- **Committed in:** 74b4845

**2. [Rule 1 - Bug] SQL in cassettes must be sqlglot-normalized**
- **Found during:** Task 1 — `CassetteMissError` despite cassette directory existing
- **Issue:** Plugin normalizes SQL before cassette lookup; raw `SELECT 1` != normalized `SELECT\n  1`
- **Fix:** Used `sqlglot.parse_one(sql).sql(pretty=True, normalize=True)` in cassette generation script
- **Verification:** All 4 tests passed; CassetteMissError resolved
- **Committed in:** 74b4845

**3. [Rule 1 - Bug] basedpyright strict: ADBC APIs are untyped**
- **Found during:** Task 2 — pre-commit basedpyright check
- **Issue:** `reportUnknownMemberType` and `reportUnknownVariableType` for connection/cursor objects
- **Fix:** Added `Any` type annotations and `# type: ignore[union-attr]` on connect() calls
- **Verification:** basedpyright reports 0 errors
- **Committed in:** 74b4845

---

**Total deviations:** 3 auto-fixed (all bugs in external API understanding)
**Impact on plan:** All fixes necessary for correctness. No scope creep.

## Issues Encountered

None beyond the auto-fixed deviations above.

## Next Phase Readiness

- Phase 15 complete
- All 192 tests green (188 unit + 4 integration)
- pytest-adbc-replay cassette workflow fully operational
- Snowflake and Databricks tests run in CI without credentials
- mkdocs build --strict passes

---
*Phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests*
*Completed: 2026-03-02*
