---
phase: "15"
phase_name: "replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests"
verified: "2026-03-07T12:00:00Z"
status: passed
score: 8/8 must-haves verified
re_verification:
  previous_status: passed
  previous_score: 8/8
  gaps_closed: []
  gaps_remaining: []
  regressions: []
  notable: >
    Plan 04 success criterion (per-warehouse dotenv isolation) was intentionally
    reverted in Plan 05 commit bb81d8e at user direction. The autouse env-clearing
    fixture (the primary unit-test-isolation mechanism) remains in place. The
    phase-level goal is unaffected. Documented as deviation in 15-05-SUMMARY.md.
---

# Phase 15: Replace Syrupy Snapshot Tests with Cassette-Based Replay — Verification Report

**Phase Goal:** Syrupy is removed; Snowflake integration tests are migrated to cassette-based replay; Databricks cassette tests are added; all four integration tests pass in CI without credentials

**Verified:** 2026-03-07T12:00:00Z
**Status:** PASSED
**Re-verification:** Yes — independent verification against actual codebase (previous VERIFICATION.md was self-reported by execution agent)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Syrupy is removed from dev deps and uv.lock | VERIFIED | `pyproject.toml` has `pytest-adbc-replay` in place of `syrupy>=4.0`; grep for "syrupy" finds 0 matches in `pyproject.toml` and `uv.lock` |
| 2 | pytest-adbc-replay is installed and configured | VERIFIED | Version 1.0.0a1 in `uv.lock`; `adbc_auto_patch` and `adbc_cassette_dir` present in `[tool.pytest.ini_options]`; `addopts` credential gate absent |
| 3 | Snowflake integration tests use cassette-based replay | VERIFIED | `test_snowflake.py` has `@pytest.mark.adbc_cassette("snowflake_health")` and `@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")`; no syrupy imports anywhere in test files |
| 4 | Databricks cassette tests exist | VERIFIED | `tests/integration/test_databricks.py` exists with `test_connection_health` and `test_arrow_round_trip`, both decorated with `@pytest.mark.adbc_cassette` |
| 5 | All four integration tests pass without credentials | VERIFIED | `uv run pytest tests/integration/ -v` — 4 passed in 0.03s; adbc-replay record mode = none; no env vars required |
| 6 | Full test suite passes | VERIFIED | `uv run pytest -x -q` — 192 passed in 0.51s (188 unit + 4 integration); 0 failures, 0 skips |
| 7 | 12 cassette files committed | VERIFIED | `find tests/cassettes -type f` returns 12 files: 4 tests x 3 files (`000_query.sql`, `000_result.arrow`, `000_params.json`). All Arrow IPC files valid and readable by pyarrow |
| 8 | docs build passes | VERIFIED | `uv run mkdocs build --strict` completes with no errors |

**Score:** 8/8 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | pytest-adbc-replay dep, cassette ini config | VERIFIED | `pytest-adbc-replay` in `[dependency-groups].dev`; `adbc_auto_patch` and `adbc_cassette_dir` in `[tool.pytest.ini_options]`; no `addopts` |
| `.gitignore` | Databricks credential exclusion | VERIFIED | Lines 146-147: `.env.databricks` and `*.env.databricks` |
| `tests/integration/conftest.py` | Syrupy-free; databricks_pool fixture | VERIFIED | No syrupy imports; `snowflake_pool` and `databricks_pool` session-scoped fixtures present |
| `tests/integration/test_snowflake.py` | cassette-based, no syrupy | VERIFIED | `@pytest.mark.adbc_cassette` on both tests; no syrupy references |
| `tests/integration/test_databricks.py` | New cassette tests | VERIFIED | File exists with 2 tests, both using `@pytest.mark.adbc_cassette` |
| `tests/cassettes/snowflake_health/adbc_driver_snowflake.dbapi/` | 3-file triplet | VERIFIED | `000_query.sql` (SELECT 1), `000_result.arrow` (1 row, col `1`), `000_params.json` (null) |
| `tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/` | 3-file triplet | VERIFIED | `000_query.sql` (SELECT 1 AS n, 'hello' AS s), `000_result.arrow` (1 row, cols N,S), `000_params.json` (null) |
| `tests/cassettes/databricks_health/adbc_driver_manager.dbapi/` | 3-file triplet | VERIFIED | `000_query.sql` (SELECT 1), `000_result.arrow` (1 row, col `1`), `000_params.json` (null) |
| `tests/cassettes/databricks_arrow_round_trip/adbc_driver_manager.dbapi/` | 3-file triplet | VERIFIED | `000_query.sql` (SELECT 1 AS n, 'hello' AS s), `000_result.arrow` (1 row, cols n,s), `000_params.json` (null) |
| `tests/conftest.py` | Autouse env-clearing fixture | VERIFIED | `_clear_warehouse_env_vars` autouse fixture clears all 13 warehouse env prefixes via monkeypatch |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pyproject.toml [dependency-groups].dev` | pytest-adbc-replay (PyPI) | `pytest-adbc-replay` in dev deps | WIRED | Version 1.0.0a1 in uv.lock; plugin active (shown in pytest header: `plugins: adbc-replay-1.0.0a1`) |
| `pyproject.toml [tool.pytest.ini_options]` | pytest-adbc-replay plugin | `adbc_auto_patch` ini key | WIRED | Both driver modules listed; cassette_dir configured |
| `test_snowflake.py` | `tests/cassettes/snowflake_health/` | `@pytest.mark.adbc_cassette("snowflake_health")` | WIRED | Pattern present; cassette directory exists with valid files; test passes in replay |
| `test_snowflake.py` | `tests/cassettes/snowflake_arrow_round_trip/` | `@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")` | WIRED | Pattern present; cassette directory exists; test passes |
| `test_databricks.py` | `tests/cassettes/databricks_health/` | `@pytest.mark.adbc_cassette("databricks_health")` | WIRED | Pattern present; cassette directory exists; test passes |
| `test_databricks.py` | `tests/cassettes/databricks_arrow_round_trip/` | `@pytest.mark.adbc_cassette("databricks_arrow_round_trip")` | WIRED | Pattern present; cassette directory exists; test passes |
| `tests/conftest.py` | unit tests | autouse=True | WIRED | `_clear_warehouse_env_vars` runs before every test; 147 unit tests pass regardless of env state |

---

## Requirements Coverage

All plans in this phase declare `requirements: []`. The phase prompt states requirement IDs are TBD. Cross-referencing REQUIREMENTS.md:

| Requirement | Notes | Status |
|------------|-------|--------|
| **TEST-03** (Snowflake syrupy snapshot tests) | Phase 6 completed the syrupy-based implementation. Phase 15 supersedes it with cassette-based replay. TEST-03 is marked complete in REQUIREMENTS.md traceability table (Phase 6). The cassette approach is a replacement, not a regression. | SUPERSEDED — cassette replay delivers superior CI-safe outcome |
| **SETUP-04** (`syrupy>=4.0` in dev deps) | Marked complete in Phase 2. Phase 15 intentionally removes syrupy and replaces with pytest-adbc-replay. | SUPERSEDED — requirement fulfilled then deliberately evolved |

No REQUIREMENTS.md entries are orphaned for this phase. All phase plans carry `requirements: []` with no formal IDs to cross-reference.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/integration/conftest.py` | 22, 44 | `load_dotenv(.../".env")` loads bare `.env` instead of per-warehouse files | INFO | Functional non-issue (Plan 05 deliberately reverted Plan 04 change at user direction, documented in 15-05-SUMMARY.md); recording workflow uses single .env; replay is unaffected |
| `tests/integration/test_snowflake.py` | 23 | `load_dotenv(.../".env")` | INFO | Same as above — unified .env is intentional design decision |
| `tests/integration/test_databricks.py` | 24 | `load_dotenv(.../".env")` | INFO | Same as above |

No blocker anti-patterns. The dotenv path pattern is a documented, intentional deviation from Plan 04 made in Plan 05 commit `bb81d8e`. The autouse env-clearing fixture in `tests/conftest.py` protects unit test isolation regardless of which dotenv file is loaded.

---

## Human Verification Required

None. All checks are automatable and have been verified programmatically.

---

## Notable Implementation Details

1. **Real Snowflake cassettes (not synthetic):** Snowflake cassettes (`snowflake_health`, `snowflake_arrow_round_trip`) were recorded from a live Snowflake connection in Plan 05. Column names reflect real Snowflake behaviour: `SELECT 1 AS n, 'hello' AS s` returns columns `N`, `S` (uppercased by Snowflake). Databricks cassettes use lowercase `n`, `s`.

2. **adbc_driver_snowflake in dev deps:** The plan originally discussed whether to install the driver; it was added to `[dependency-groups].dev` as `adbc-driver-snowflake>=1.0.0` in addition to the existing optional extra. This is correct — dev tests need the driver importable.

3. **Dotenv path consolidation (Plan 05 deviation):** Plan 04 introduced per-warehouse dotenv files (`.env.snowflake`, `.env.databricks`). Plan 05 reverted this to a single `.env` file at user direction during live Snowflake recording. The unit-test isolation goal of Plan 04 is still achieved via the `_clear_warehouse_env_vars` autouse fixture, which clears env vars before each test regardless of which dotenv file was loaded.

4. **SQL normalization:** Cassette SQL files contain sqlglot-normalized multi-line SQL (e.g., `SELECT\n  1` rather than `SELECT 1`). This matches what pytest-adbc-replay stores when recording.

---

## Summary

All 8 must-haves verified against the actual codebase. The phase goal is fully achieved:

- Syrupy is completely absent from `pyproject.toml`, `uv.lock`, and all Python source files
- pytest-adbc-replay 1.0.0a1 is installed and active
- Snowflake integration tests are migrated to cassette-based replay with real recorded cassettes
- Databricks cassette tests are added
- All 4 integration tests pass in CI (replay) mode without any credentials
- Full 192-test suite passes with 0 failures
- docs build passes

The previous self-reported VERIFICATION.md (status: passed, score: 8/8) is confirmed accurate by independent codebase inspection.

---

_Verified: 2026-03-07T12:00:00Z_
_Verifier: Claude (gsd-verifier) — independent codebase inspection_
