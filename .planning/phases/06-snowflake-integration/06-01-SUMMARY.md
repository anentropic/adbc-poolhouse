---
phase: 06-snowflake-integration
plan: "01"
subsystem: testing
tags: [syrupy, pyarrow, snowflake, snapshot-testing, pytest, conftest]

# Dependency graph
requires:
  - phase: 05-pool-factory-and-duckdb-integration
    provides: create_pool() factory and SnowflakeConfig that the integration fixtures use
provides:
  - SnowflakeArrowSnapshotSerializer: stable JSON serializer stripping non-deterministic Arrow metadata
  - snowflake_snapshot fixture: syrupy SnapshotAssertion pre-configured with SnowflakeArrowSnapshotSerializer
  - snowflake_pool fixture: session-scoped QueuePool with skip-on-no-creds logic
  - Two integration tests: test_connection_health + test_arrow_round_trip (snowflake marker)
  - pyproject.toml marker registration + addopts excluding snowflake from default runs
  - CONTRIBUTING.md snapshot recording workflow documentation
affects: [snapshot recording workflow, CI configuration, future Snowflake tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Custom syrupy extension via JSONSnapshotExtension subclass: override serialize() only, inherit all file I/O"
    - "Skip-on-no-credentials pattern: pytest.skip() inside session-scoped fixture when SNOWFLAKE_ACCOUNT absent"
    - "addopts + --override-ini='addopts=' pattern: exclude integration markers from default runs, override for recording"
    - "SnapshotAssertion.use_extension() pattern: domain-specific snapshot fixture without changing global default"

key-files:
  created:
    - tests/integration/__init__.py
    - tests/integration/conftest.py
    - tests/integration/test_snowflake.py
    - CONTRIBUTING.md
  modified:
    - pyproject.toml
    - .gitignore

key-decisions:
  - "SnowflakeArrowSnapshotSerializer in TYPE_CHECKING import block for SnapshotAssertion and syrupy types (ruff TC002)"
  - "pyarrow annotated with # type: ignore[import-untyped] — no stubs available; internal arrow ops use # type: ignore[union-attr]"
  - "snowflake_pool fixture uses type: ignore[call-arg] for SnowflakeConfig() — basedpyright cannot see env-var-provided required fields"
  - "All non-deterministic meta key strips are defensive — current adbc-driver-snowflake 1.10.0 may not emit these fields"

patterns-established:
  - "Pattern 1: Custom syrupy extension — subclass JSONSnapshotExtension, override only serialize(), inherit all storage methods"
  - "Pattern 2: Integration test marker isolation — addopts excludes marker, --override-ini='addopts=' to run"
  - "Pattern 3: Credential-safe fixtures — load_dotenv with override=False, pytest.skip() when env var absent"

requirements-completed: [TEST-03]

# Metrics
duration: 4min
completed: 2026-02-25
---

# Phase 6 Plan 1: Snowflake Snapshot Test Infrastructure Summary

**Syrupy snapshot infrastructure for Snowflake ADBC tests: custom Arrow serializer stripping non-deterministic metadata, skip-on-no-creds conftest fixtures, two integration tests, and CONTRIBUTING.md recording workflow**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-25T15:57:05Z
- **Completed:** 2026-02-25T16:01:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Created `SnowflakeArrowSnapshotSerializer` (subclass of `JSONSnapshotExtension`) that serializes Arrow tables to stable JSON, stripping 6 non-deterministic schema metadata keys defensively
- Created `tests/integration/conftest.py` with `snowflake_snapshot` and `snowflake_pool` fixtures — pool skips when `SNOWFLAKE_ACCOUNT` absent (CI-safe)
- Created `tests/integration/test_snowflake.py` with two `@pytest.mark.snowflake` tests: connection health (SELECT 1) and Arrow round-trip snapshot
- Configured pytest marker with `addopts = "-m 'not snowflake'"` so default `uv run pytest` never attempts a Snowflake connection (82 tests pass, 2 deselected)
- Created `CONTRIBUTING.md` documenting exact `pytest --override-ini="addopts=" -m snowflake --snapshot-update` recording workflow

## Task Commits

Each task was committed atomically:

1. **Task 1: Infrastructure, serializer, and conftest fixtures** - `dcce2a8` (feat)
2. **Task 2: Integration tests and CONTRIBUTING.md** - `01b480b` (feat)

**Plan metadata:** _(docs commit pending)_

## Files Created/Modified
- `tests/integration/__init__.py` - Empty package file enabling conftest.py scoping
- `tests/integration/conftest.py` - `SnowflakeArrowSnapshotSerializer`, `snowflake_snapshot`, `snowflake_pool` fixtures
- `tests/integration/test_snowflake.py` - Two `@pytest.mark.snowflake` integration tests
- `CONTRIBUTING.md` - Snapshot recording/replay workflow documentation
- `pyproject.toml` - Added `[tool.pytest.ini_options]` with snowflake marker and addopts
- `.gitignore` - Added `.env.snowflake` and `*.env.snowflake` entries

## Decisions Made
- `SnapshotAssertion` and syrupy type imports moved to `TYPE_CHECKING` block — ruff TC002 rule requires third-party imports used only as annotations to be deferred; valid with `from __future__ import annotations`
- `pyarrow` annotated with `# type: ignore[import-untyped]` — no stubs available; internal arrow attribute access uses `# type: ignore[union-attr]` throughout serialize()
- `SnowflakeConfig()` call uses `# type: ignore[call-arg]` — basedpyright cannot see env-var-provided required fields (established pattern from phase 03)
- Defensive stripping of 6 non-deterministic meta keys even though current driver (1.10.0) may not emit them — roadmap-specified behavior

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Moved SnapshotAssertion to TYPE_CHECKING block in both conftest.py and test_snowflake.py**
- **Found during:** Task 1 and Task 2 (prek ruff verification)
- **Issue:** ruff TC002 flagged `from syrupy.assertion import SnapshotAssertion` as third-party import that should be in TYPE_CHECKING block since it's only used as type annotation (valid with `from __future__ import annotations`)
- **Fix:** Moved import to `if TYPE_CHECKING:` block in both files; ruff auto-fixed some, manual fix for remaining
- **Files modified:** `tests/integration/conftest.py`, `tests/integration/test_snowflake.py`
- **Verification:** ruff and basedpyright both pass
- **Committed in:** `dcce2a8`, `01b480b` (part of task commits)

**2. [Rule 1 - Bug] Added type: ignore annotations for pyarrow untyped imports**
- **Found during:** Task 1 (basedpyright verification)
- **Issue:** basedpyright strict mode reports `reportMissingTypeStubs` for pyarrow and multiple `reportUnknownMemberType` / `reportUnknownVariableType` errors from untyped pyarrow API usage
- **Fix:** Added `# type: ignore[import-untyped]` on pyarrow import; `# type: ignore[union-attr]` on all pyarrow attribute accesses inside serialize()
- **Files modified:** `tests/integration/conftest.py`
- **Verification:** basedpyright passes with 0 errors
- **Committed in:** `dcce2a8` (part of task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - type annotation compliance)
**Impact on plan:** Both fixes necessary for prek gate (ruff + basedpyright). No scope creep.

## Issues Encountered
None beyond the type annotation fixes documented above.

## User Setup Required
None - no external service configuration required. Snowflake credentials are optional (tests skip gracefully when absent).

## Next Phase Readiness
- Snapshot infrastructure is ready for recording against real Snowflake credentials
- Record snapshots with: `pytest --override-ini="addopts=" -m snowflake --snapshot-update`
- Phase 6 plan 1 complete — Snowflake integration phase is complete (only 1 plan)

## Self-Check: PASSED

All created files confirmed present:
- `tests/integration/__init__.py` — FOUND
- `tests/integration/conftest.py` — FOUND
- `tests/integration/test_snowflake.py` — FOUND
- `CONTRIBUTING.md` — FOUND
- `.planning/phases/06-snowflake-integration/06-01-SUMMARY.md` — FOUND

Commits confirmed:
- `dcce2a8` — FOUND
- `01b480b` — FOUND

---
*Phase: 06-snowflake-integration*
*Completed: 2026-02-25*
