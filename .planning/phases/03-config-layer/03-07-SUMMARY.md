---
phase: 03-config-layer
plan: 07
subsystem: testing
tags: [pytest, pydantic, pydantic-settings, tdd, config-models, validation, secrets]

# Dependency graph
requires:
  - phase: 03-config-layer/03-01 through 03-06
    provides: All 11 concrete warehouse config classes + BaseWarehouseConfig + WarehouseConfig Protocol
provides:
  - 26 unit tests covering all 11 concrete config classes and base class (TEST-04 fulfilled)
  - Validated field validation, SecretStr handling, env_prefix isolation, model_validator behaviour
  - tests/test_configs.py with 5 test classes covering all TEST-04 requirements
affects:
  - 04-driver-detection (tests pattern established for driver layer)
  - 05-pool-factory (tests/test_pool_factory.py should follow same patterns)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - pytest class-based test organisation (TestBaseWarehouseConfig, TestDuckDBConfig, etc.)
    - monkeypatch.setenv for env_prefix isolation tests with pytest.MonkeyPatch type annotation
    - pragma allowlist secret for SecretStr test values to pass detect-secrets
    - type: ignore[call-arg] for SnowflakeConfig() calls that rely on env vars for required fields
    - DuckDB env_prefix tests set DUCKDB_DATABASE to file path to avoid in-memory pool_size > 1 validator

key-files:
  created:
    - tests/test_configs.py
  modified:
    - tests/conftest.py (no content change — file existed with placeholder comment)

key-decisions:
  - "DuckDB env prefix pool_size tests require DUCKDB_DATABASE env var set to file path — in-memory pool_size > 1 raises ValidationError so env tests cannot use default :memory: database"
  - "type: ignore[call-arg] for SnowflakeConfig() calls without account= in env prefix tests — basedpyright cannot see env var-provided required fields at type-check time"
  - "pragma: allowlist secret on variables holding PEM/password strings, not inline — enables ruff to format lines without exceeding 100-char limit while keeping detect-secrets happy"

patterns-established:
  - "Test PEM/key strings via local variable with pragma: allowlist secret, then pass variable to constructor — avoids line-length and detect-secrets conflicts simultaneously"
  - "pytest.MonkeyPatch type annotation required on all monkeypatch fixture parameters — basedpyright reports reportUnknownParameterType otherwise"

requirements-completed: [TEST-04]

# Metrics
duration: 5min
completed: 2026-02-24
---

# Phase 3 Plan 7: Config Model Unit Tests Summary

**26 pytest tests across 5 classes validating all 11 warehouse config models: field validation, SecretStr masking, env_prefix isolation, and model_validator enforcement**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-02-24T08:09:54Z
- **Completed:** 2026-02-24T08:14:39Z
- **Tasks:** 1 (TDD RED+GREEN combined — implementations existed from Plans 01-06)
- **Files modified:** 1 (tests/test_configs.py created)

## Accomplishments

- 26 unit tests created covering all 11 concrete config classes plus BaseWarehouseConfig abstract base
- All TEST-04 requirements satisfied: field validation, SecretStr handling, env_prefix isolation, model_validator behaviour
- Full prek gate passes: ruff, ruff-format, basedpyright, detect-secrets all green
- 27 total tests in suite (26 new + 1 existing test_import), all passing

## Test Breakdown by Class

| Class | Tests | Coverage |
|-------|-------|----------|
| TestBaseWarehouseConfig | 1 | TypeError on direct instantiation |
| TestDuckDBConfig | 7 | defaults, pool_size validator, env_prefix, isolation, Protocol |
| TestSnowflakeConfig | 8 | construction, mutual exclusion, SecretStr masking, env_prefix, Protocol |
| TestApacheBackendConfigs | 4 | BigQuery, PostgreSQL, FlightSQL smoke tests + isolation |
| TestFoundryBackendConfigs | 6 | Databricks, Redshift, Trino, MSSQL, Teradata smoke tests |
| **Total** | **26** | |

## Task Commits

1. **Task 1: Write and verify config model unit tests** - `777bc80` (test)

**Plan metadata:** (added after final commit)

## Files Created/Modified

- `tests/test_configs.py` - 26 unit tests for all config models, prek-compliant with type annotations and detect-secrets pragmas

## Decisions Made

- DuckDB env_prefix pool_size tests set `DUCKDB_DATABASE` to a file path via monkeypatch — necessary because the `check_memory_pool_size` validator rejects pool_size > 1 with `:memory:`, so env var tests setting pool_size=8 cannot use the default in-memory database.
- `type: ignore[call-arg]` on `SnowflakeConfig()` calls in env prefix tests — basedpyright enforces that `account` (required field with no default) must be provided at the call site; it cannot see that monkeypatch sets `SNOWFLAKE_ACCOUNT` before construction.
- Secret string test values extracted to local variables with `# pragma: allowlist secret` on the variable assignment line — this satisfies both ruff's 100-char line limit (the constructor call line stays short) and detect-secrets' requirement that the pragma be on the same line as the secret text.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed env_prefix pool_size test logic for DuckDB in-memory constraint**
- **Found during:** Task 1 (writing tests + running pytest)
- **Issue:** Plan template tests set `DUCKDB_POOL_SIZE=8` with default `:memory:` database — DuckDB's `check_memory_pool_size` model_validator raises `ValidationError` when pool_size > 1 with `:memory:`, so the tests would always fail at construction, not at the assertion.
- **Fix:** Added `monkeypatch.setenv("DUCKDB_DATABASE", "/tmp/test.duckdb")` to env prefix tests so the file database path bypasses the in-memory constraint.
- **Files modified:** tests/test_configs.py
- **Verification:** `uv run pytest tests/test_configs.py -v` — 26/26 passed
- **Committed in:** `777bc80` (task commit)

**2. [Rule 2 - Missing Critical] Added type annotations, detect-secrets pragmas, and type: ignore comments for prek compliance**
- **Found during:** Task 1 (running prek gate)
- **Issue:** basedpyright reported `reportUnknownParameterType` for untyped `monkeypatch` parameters; detect-secrets flagged `-----BEGIN PRIVATE KEY-----` string; ruff E501 line-length violations from long inline pragma comments.
- **Fix:** Added `pytest.MonkeyPatch` type annotations to all monkeypatch parameters; extracted secret strings to variables with `# pragma: allowlist secret`; added `# type: ignore[call-arg]` for env-var-provided required fields; wrapped long lines to stay under 100 chars.
- **Files modified:** tests/test_configs.py
- **Verification:** `uv run prek` — all hooks passed
- **Committed in:** `777bc80` (task commit)

---

**Total deviations:** 2 auto-fixed (1 test logic bug, 1 missing prek compliance)
**Impact on plan:** Both auto-fixes necessary for correctness and prek compliance. No scope creep — all fixes are within the test file for the planned functionality.

## Issues Encountered

- detect-secrets requires `# pragma: allowlist secret` to be on the same line as the secret text. When ruff formats multi-line constructors, the comment moves to the closing paren line which is not the secret-containing line. Solution: extract secret to a local variable where the pragma sits on the same line as the value assignment.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TEST-04 requirement fully satisfied: all 11 concrete config classes have at least one construction test
- Phase 3 (Config Layer) is now complete — all 7 plans executed
- Phase 4 (Driver Detection) can proceed: config model API is fully tested and verified correct
- Pattern established: pytest class-based tests with monkeypatch, pragma allowlist secret, and type annotations — follow same pattern for Phase 4/5 tests

## Self-Check: PASSED

- FOUND: tests/test_configs.py
- FOUND: commit 777bc80 (test(03-07): add config model unit tests...)
- FOUND: .planning/phases/03-config-layer/03-07-SUMMARY.md

---
*Phase: 03-config-layer*
*Completed: 2026-02-24*
