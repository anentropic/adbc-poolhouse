---
phase: 09-infrastructure-and-databricks-fix
plan: "02"
subsystem: database
tags: [databricks, adbc, pydantic, model_validator, url-encoding, urllib]

# Dependency graph
requires:
  - phase: 09-01
    provides: adbc-driver-manager floor bump to >=1.8.0

provides:
  - DatabricksConfig model_validator that raises ConfigurationError when no connection spec provided
  - decomposed-field URI construction in translate_databricks() with URL-encoded token
  - Updated test suite: 9 Databricks-specific tests covering both connection modes
  - Updated databricks.md guide reflecting decomposed-field mode requirements

affects:
  - Phase 11 (MySQL): URI-first decomposed-field pattern template established here
  - Phase 12 (ClickHouse): same decomposed-field pattern applies

# Tech tracking
tech-stack:
  added: [urllib.parse.quote]
  patterns:
    - "model_validator(mode='after') raising ConfigurationError for missing connection spec"
    - "URL-encoding via urllib.parse.quote(safe='') for PAT tokens with special chars"
    - "URI construction: databricks://token:{encoded}@{host}:443{http_path}"

key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_databricks_config.py
    - src/adbc_poolhouse/_databricks_translator.py
    - tests/test_configs.py
    - tests/test_translators.py
    - tests/test_pool_factory.py
    - tests/test_drivers.py
    - docs/src/guides/databricks.md

key-decisions:
  - "DatabricksConfig validator uses model_validator(mode='after') matching DuckDB precedent — same # noqa: TC001 import pattern"
  - "urllib.parse.quote(safe='') not quote_plus — quote_plus encodes spaces as '+' not '%20'; safe='' ensures +, =, / all percent-encoded"
  - "Decomposed-field URI format: databricks://token:{encoded}@{host}:443{http_path} — http_path always has leading slash from stored value"
  - "assert statements for decomposed field non-None checks — model_validator guarantees all three are set when uri is None; asserts document the invariant"
  - "doctest output uses result['uri'].startswith() not full URI — avoids long lines that detect-secrets flags as Basic Auth credentials"

patterns-established:
  - "URI-first decomposed-field pattern: check config.uri first, else build from host/http_path/token — template for MySQL (Phase 11) and ClickHouse (Phase 12)"
  - "URL-encode tokens with urllib.parse.quote(safe='') before embedding in URIs"
  - "model_validator for connection spec validation: has_uri or (host and http_path and token)"

requirements-completed: [DBX-01, DBX-02]

# Metrics
duration: 8min
completed: 2026-03-01
---

# Phase 09 Plan 02: Databricks Fix Summary

**DatabricksConfig() now raises ValidationError when no connection spec is given; translate_databricks() constructs a percent-encoded URI from decomposed host/http_path/token fields**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-01T02:12:12Z
- **Completed:** 2026-03-01T02:19:30Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Added `check_connection_spec` model_validator to DatabricksConfig that raises ConfigurationError when neither uri nor all three of host/http_path/token are provided
- Implemented decomposed-field URI construction in translate_databricks() using urllib.parse.quote(safe="") to percent-encode PAT tokens — tokens with +, =, /, @ now survive as %2B, %3D, %2F, %40
- Updated databricks.md guide: corrected decomposed-field example (was plain string token, now SecretStr), added env var all-three-required note

## Task Commits

Each task was committed atomically:

1. **Task 1: Add model_validator to DatabricksConfig (DBX-01)** - `07ebac0` (feat)
2. **Task 2: Implement decomposed-field URI in translate_databricks() (DBX-02)** - `aed826b` (feat)
3. **Task 3: Update Databricks guide and verify mkdocs build** - `ca30683` (docs)

## Files Created/Modified

- `src/adbc_poolhouse/_databricks_config.py` — Added model_validator, updated docstring to describe both connection modes, added ConfigurationError import with # noqa: TC001
- `src/adbc_poolhouse/_databricks_translator.py` — Added urllib.parse.quote(safe="") URL-encoding, implemented decomposed-field URI construction, added full Google-style docstring
- `tests/test_configs.py` — Replaced test_databricks_default_construction with test_databricks_no_args_raises and test_databricks_uri_constructs; updated test_databricks_token_is_secret_str to set all three env vars
- `tests/test_translators.py` — Replaced test_no_uri_empty with four new tests (URI mode, decomposed + special chars, decomposed + plain token, no-args raises)
- `tests/test_pool_factory.py` — Added TestDatabricksPoolFactory with test_decomposed_fields_wiring mocking create_adbc_connection and asserting URL-encoded URI
- `tests/test_drivers.py` — Updated test_databricks_returns_short_name_without_find_spec to construct a valid DatabricksConfig (uri mode) instead of calling no-args constructor
- `docs/src/guides/databricks.md` — Updated decomposed fields example (SecretStr), added env var all-three-required note, added DATABRICKS_URI alternative note

## Decisions Made

- urllib.parse.quote(safe="") chosen over quote_plus — quote_plus encodes spaces as "+" which corrupts PAT tokens that contain "+" characters
- assert statements used (not if checks) for decomposed field None checks after URI mode — the model_validator invariant guarantees all three are set when uri is None; asserts document this contractually
- doctest Example uses result["uri"].startswith() instead of the full URI string — avoids lines that detect-secrets flags as Basic Auth credentials (user:password@host pattern)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_databricks_returns_short_name_without_find_spec to use valid DatabricksConfig**
- **Found during:** Task 2 (running all Databricks tests)
- **Issue:** test_drivers.py::TestResolveFoundryDriver::test_databricks_returns_short_name_without_find_spec called `DatabricksConfig()` with no args, which now raises ValidationError due to Task 1's model_validator
- **Fix:** Changed test to construct `DatabricksConfig(uri=SecretStr("..."))` — maintains test purpose (Foundry driver skips find_spec)
- **Files modified:** tests/test_drivers.py
- **Verification:** Test passes; mock_find.assert_not_called() still verified
- **Committed in:** aed826b (Task 2 commit)

**2. [Rule 1 - Bug] Corrected mock pool-factory wiring test assertion**
- **Found during:** Task 2 (writing TestDatabricksPoolFactory)
- **Issue:** Plan's test template used `call_kwargs.kwargs.get("db_kwargs", {})` but create_adbc_connection is called with positional args: `create_adbc_connection(driver_path, kwargs, entrypoint=...)` — "kwargs" is index 1 of positional args, not a keyword arg named "db_kwargs"
- **Fix:** Changed assertion to `call_args.args[1]` to access the second positional arg
- **Files modified:** tests/test_pool_factory.py
- **Verification:** test_decomposed_fields_wiring passes; asserts correct URL-encoded URI
- **Committed in:** aed826b (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bugs caused by our own validator change and incorrect API assumption)
**Impact on plan:** Both fixes necessary for tests to reflect the new validator behavior and the actual pool_factory call signature. No scope creep.

## Issues Encountered

- detect-secrets Basic Auth detector flags `token:value@host` URI patterns in test assertions — resolved with `# pragma: allowlist secret` inline comments and `# noqa: E501` where line length exceeded 100 chars; doctest output line restructured to use `result["uri"].startswith()` instead of full URI
- DuckDB pool tests (TestCreatePoolDuckDB) fail in this environment because duckdb is not installed — confirmed as pre-existing (present before Phase 9 changes); these are out of scope

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DBX-01 and DBX-02 complete: Databricks connection validation and decomposed-field URI construction are production-ready
- Pattern template established for MySQL (Phase 11) and ClickHouse (Phase 12) translators
- Phase 9 complete: both plans done, ready for Phase 10 (test wiring TEST-WIRING-01)

## Self-Check: PASSED

- FOUND: src/adbc_poolhouse/_databricks_config.py
- FOUND: src/adbc_poolhouse/_databricks_translator.py
- FOUND: tests/test_configs.py (databricks tests)
- FOUND: tests/test_translators.py (databricks tests)
- FOUND: tests/test_pool_factory.py (TestDatabricksPoolFactory)
- FOUND: tests/test_drivers.py (updated test)
- FOUND: docs/src/guides/databricks.md
- FOUND commit: 07ebac0 (Task 1)
- FOUND commit: aed826b (Task 2)
- FOUND commit: ca30683 (Task 3)
- FOUND commit: 25f0d05 (metadata)

---
*Phase: 09-infrastructure-and-databricks-fix*
*Completed: 2026-03-01*
