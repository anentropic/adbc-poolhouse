---
phase: 05-pool-factory-and-duckdb-integration
plan: "02"
subsystem: pool-factory
tags: [sqlalchemy, queuepool, adbc, duckdb, arrow, cleanup, tdd]

# Dependency graph
requires:
  - phase: 05-01
    provides: PoolhouseError, ConfigurationError, _adbc_entrypoint on DuckDBConfig
  - phase: 04-translation-and-driver-detection
    provides: translate_config, resolve_driver, create_adbc_connection
provides:
  - create_pool() factory function in _pool_factory.py
  - Arrow allocator cleanup via SQLAlchemy reset event listener
  - Public re-exports: create_pool, PoolhouseError, ConfigurationError in __init__.py
affects:
  - 06+ (consumers of create_pool public API)
  - tests (16 integration tests covering POOL-01..05, TEST-01, TEST-07)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ADBC source+clone pattern: one source connection, QueuePool uses source.adbc_clone as factory"
    - "pool._adbc_source attached to pool instance for caller cleanup after dispose()"
    - "SQLAlchemy reset event for Arrow allocator cleanup (not checkin — reset fires on invalidation too)"
    - "contextlib.suppress(Exception) for cursor.close() in reset listener (ruff SIM105)"

key-files:
  created:
    - src/adbc_poolhouse/_pool_factory.py
    - tests/test_pool_factory.py
  modified:
    - src/adbc_poolhouse/__init__.py

key-decisions:
  - "ADBC source+clone pattern: create_adbc_connection() opens a source connection, QueuePool uses source.adbc_clone as the connection factory — each pool checkout clones the source, sharing the underlying AdbcDatabase via reference counting"
  - "pool._adbc_source attached dynamically (type: ignore[attr-defined]) so callers can close source after pool.dispose() — documented in create_pool() docstring"
  - "reset event (not checkin) for Arrow cleanup — reset fires on all return paths including invalidation; checkin receives None as dbapi_conn when connection is invalidated"
  - "TDD RED+GREEN combined into one commit — strict mode basedpyright (typeCheckingMode=strict, includes tests/) fails on unknown imports; RED-only commit requires implementation to exist for type checker"
  - "tmp_path type annotation is pathlib.Path (not pytest.TempPathFactory) — TempPathFactory is a different pytest fixture for creating directories; tmp_path is already a Path instance"

patterns-established:
  - "Pool lifecycle pattern: pool.dispose() then pool._adbc_source.close() — callers always responsible for closing source after pool disposal"
  - "Arrow cursor cleanup on reset event: iterate dbapi_conn._cursors WeakSet, close non-closed cursors with contextlib.suppress(Exception)"

requirements-completed: [POOL-01, POOL-02, POOL-03, POOL-04, POOL-05, TEST-01, TEST-07]

# Metrics
duration: 4min
completed: 2026-02-24
---

# Phase 5 Plan 02: Pool Factory Summary

**SQLAlchemy QueuePool factory via ADBC source+clone pattern with Arrow cursor cleanup on reset event**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-24T23:38:50Z
- **Completed:** 2026-02-24T23:42:45Z
- **Tasks:** 2 (RED + GREEN combined in one commit)
- **Files modified:** 3 (2 created, 1 updated)

## Accomplishments
- Created `_pool_factory.py` with `create_pool()` implementing the ADBC source+clone pool factory
- Registered Arrow allocator cleanup listener on SQLAlchemy `reset` event
- Updated `__init__.py` to export `create_pool`, `PoolhouseError`, `ConfigurationError` as public API
- Created full integration test suite (16 tests) covering all POOL-01..05 and TEST-01, TEST-07 requirements

## Task Commits

Tasks were combined into one commit due to strict basedpyright requiring implementation before RED test file could pass type checking:

1. **Tasks 1+2: RED+GREEN — test suite + factory implementation + public exports** - `1acd302` (test+feat)

**Plan metadata:** TBD (docs: complete plan)

## Files Created/Modified
- `src/adbc_poolhouse/_pool_factory.py` - New: create_pool() factory with ADBC source+clone pattern and reset event listener
- `tests/test_pool_factory.py` - New: 16 integration tests across 4 test classes (POOL-01..05, TEST-01, TEST-07)
- `src/adbc_poolhouse/__init__.py` - Added create_pool, PoolhouseError, ConfigurationError imports and __all__ entries

## Decisions Made
- ADBC source+clone pattern: one source connection opened via create_adbc_connection(), QueuePool uses source.adbc_clone as its connection factory — standard ADBC pattern for connection pooling
- pool._adbc_source dynamically attached to pool instance so callers can close it after dispose() — documented in the create_pool() docstring as a required cleanup step
- reset event chosen over checkin for Arrow cursor cleanup — reset fires on ALL return paths including connection invalidation; checkin receives None as dbapi_conn when connection is invalidated, making cleanup impossible
- TDD RED+GREEN combined in one commit — basedpyright strict mode includes tests/ and fails on unknown imports from adbc_poolhouse; a RED-only commit (without the implementation) fails the pre-commit type-check hook
- tmp_path fixture type annotation corrected to pathlib.Path — the original plan used pytest.TempPathFactory which is a different fixture; tmp_path is already a resolved Path instance

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed E501 lines in test file docstrings**
- **Found during:** Task 1 (RED test file creation)
- **Issue:** Two docstring lines exceeded the 100-char ruff line limit
- **Fix:** Shortened class docstring and method docstring to fit within limit
- **Files modified:** tests/test_pool_factory.py
- **Verification:** ruff check passes
- **Committed in:** 1acd302

**2. [Rule 1 - Bug] Fixed wrong tmp_path fixture type annotation**
- **Found during:** Task 1 (RED test file creation)
- **Issue:** Plan used `pytest.TempPathFactory` as the type for `tmp_path` fixture but TempPathFactory is a different fixture; tmp_path is `pathlib.Path`; basedpyright reported reportOperatorIssue on `/` operator
- **Fix:** Changed all `pytest.TempPathFactory` annotations to `pathlib.Path`, added `from pathlib import Path` import
- **Files modified:** tests/test_pool_factory.py
- **Verification:** basedpyright reports 0 errors on test file
- **Committed in:** 1acd302

**3. [Rule 1 - Bug] Replaced try/except/pass with contextlib.suppress**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** ruff SIM105 flags try/except/pass pattern in _release_arrow_allocators
- **Fix:** Replaced with `with contextlib.suppress(Exception): cur.close()`; added `import contextlib`
- **Files modified:** src/adbc_poolhouse/_pool_factory.py
- **Verification:** prek passes with 0 violations
- **Committed in:** 1acd302

---

**Total deviations:** 3 auto-fixed (3 Rule 1 bugs)
**Impact on plan:** All auto-fixes necessary for correctness and prek compliance. No scope creep.

## Issues Encountered
- basedpyright strict mode requires implementation to exist before RED test file can be committed — strict typeCheckingMode with tests/ included means unknown import symbols in the test file are errors; resolved by implementing GREEN before committing, preserving the spirit of TDD

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `create_pool()` is the primary deliverable of Phase 5 — fully implemented and tested
- Public API (create_pool, PoolhouseError, ConfigurationError) exported from adbc_poolhouse
- All 86 tests green (70 pre-existing + 16 new pool factory tests)
- Ready for Phase 6 (Snowflake integration tests / syrupy snapshots)

---
*Phase: 05-pool-factory-and-duckdb-integration*
*Completed: 2026-02-24*

## Self-Check: PASSED

- FOUND: src/adbc_poolhouse/_pool_factory.py
- FOUND: tests/test_pool_factory.py
- FOUND: src/adbc_poolhouse/__init__.py
- FOUND: .planning/phases/05-pool-factory-and-duckdb-integration/05-02-SUMMARY.md
- FOUND commit: 1acd302 (test+feat: RED+GREEN pool factory)
