---
phase: 27-dual-backend-test-matrix
plan: 02
subsystem: testing
tags: [anyio, asyncio, trio, cassette, snowflake, duckdb, pytest, read-path, matrix]

# Dependency graph
requires:
  - phase: 27-dual-backend-test-matrix
    provides: "27-01's snowflake_async_pool cassette fixture + the duckdb_async_pool fixture this matrix resolves indirectly"
  - phase: 25-cassette-replay
    provides: "the pytest-adbc-replay snowflake_arrow_round_trip cassette (single recorded interaction) replayed offline"
provides:
  - "tests/async/test_matrix_readpath.py: the TEST-01/02 read-path backend-generic matrix (connect -> execute -> fetch_arrow_table/fetchall -> checkin) over {DuckDB, Snowflake cassette} x {asyncio, trio}"
  - "An indirect sync `pool` fixture pattern that resolves an async-generator pool fixture during SETUP (avoids the anyio-runner re-entry that getfixturevalue-in-body triggers)"
affects: [27-05-meta-test, dual-backend-test-matrix]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Backend-axis parametrization over the POOL FIXTURE NAME, resolved by an indirect sync `pool` fixture via request.getfixturevalue during SETUP (NOT in the running test body — that re-enters the anyio runner and raises)"
    - "Backend-neutral value assertions: case-insensitive column lookup (Snowflake folds aliases to N/S) and value comparison (Snowflake returns N as Decimal; Decimal('1') == 1)"
    - "Single execute per test to match a single-interaction cassette; fetch surface split across two tests (fetch_arrow_table vs fetchall) rather than two executes in one test"

key-files:
  created:
    - tests/async/test_matrix_readpath.py
  modified: []

key-decisions:
  - "The PATTERNS.md getfixturevalue-in-test-body pattern does NOT work for async fixtures under this anyio plugin (RuntimeError: another coroutine already running); moved the indirection into a sync `pool` fixture resolved at setup time"
  - "fetch surface kept to a SINGLE execute per test — the snowflake_arrow_round_trip cassette records exactly one interaction; a second execute raises CassetteMissError (interaction 1 not found)"
  - "Assertions are backend-neutral by value, not by casing/type: Snowflake folds unquoted aliases to N/S and returns N as Decimal('1'); case-insensitive column lookup + Decimal('1') == 1 keep one assertion working on both backends"
  - "fetchall typed `object` on the async surface -> cast to Sequence[Sequence[object]] for the assertions (mirrors the lifecycle test's Any treatment), basedpyright strict stays 0 errors"

patterns-established:
  - "Indirect sync `pool` fixture for backend-matrix parametrization over async pool fixtures"
  - "Case-insensitive _col() helper for backend-neutral column access (DuckDB lowercase vs Snowflake uppercase)"

requirements-completed: [TEST-01, TEST-02]

# Metrics
duration: ~15min
completed: 2026-06-28
---

# Phase 27 Plan 02: Read-Path Backend Matrix Summary

**A backend-generic read-path matrix (`tests/async/test_matrix_readpath.py`) proving the async layer runs connect -> execute -> `fetch_arrow_table`/`fetchall` -> check-in green over DuckDB (in-proc) and the Snowflake cassette (offline replay), each under both asyncio and trio — 8 green legs, no `src/` change.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-06-28
- **Tasks:** 1
- **Files created:** 1

## Accomplishments
- `tests/async/test_matrix_readpath.py` (TEST-01/02): two read-path tests, each parametrized over the backend axis and run under `{asyncio, trio}` via `@pytest.mark.anyio` → 8 passing legs (2 tests × 2 backends × 2 event loops).
- `test_fetch_arrow_table_round_trip`: connect → execute → `fetch_arrow_table` → assert `pyarrow.Table` with the expected row → assert `pool._pool.checkedout() == 0` after check-in, on both backends.
- `test_cursor_fetchall_surface`: the `AsyncCursor.fetchall` read-path row surface (D-27-05), single execute, check-in asserted.
- Snowflake leg replays the existing `snowflake_arrow_round_trip` cassette offline via the `@pytest.mark.snowflake` + `@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")` markers on the `pytest.param`; skips cleanly when the driver/cassette is absent (the `snowflake_async_pool` fixture's `importorskip`/`skip` fires during setup).
- Full async suite: 80 passed (was 72 before this file). `git diff src/` empty. basedpyright strict: 0 errors. Hygiene guard (`scan_async_test_hygiene`): no finding in the new file. `mkdocs build --strict`: passes.

## Task Commits

1. **Task 1: read-path backend matrix** — `429c3de` (test)

## Files Created/Modified
- `tests/async/test_matrix_readpath.py` (new) — the TEST-01/02 read-path matrix: `_BACKENDS` param list, `_col` case-insensitive column helper, the indirect sync `pool` fixture, and the two read-path tests under `TestReadPathMatrix`.

## Decisions Made
- **Indirect sync `pool` fixture instead of `getfixturevalue` in the test body.** The PATTERNS.md / RESEARCH pattern called for `pool = request.getfixturevalue(pool_fixture)` inside the test. Under this anyio plugin that re-enters the runner: `RuntimeError: Cannot schedule a coroutine in the test runner while another is already running; likely caused by request.getfixturevalue() on an async fixture`. Fixed by moving the indirection into a sync `pool` fixture (`@pytest.fixture(params=_BACKENDS)`) that resolves the async-generator pool fixture during the SETUP phase, where the plugin sets it up normally. The Snowflake leg's `importorskip`/`skip` fires there, so an absent driver/cassette skips just that param.
- **Single execute per test.** The `snowflake_arrow_round_trip` cassette records exactly ONE interaction; a second `execute` raised `CassetteMissError: Interaction 1 not found`. The original plan's fetch-surface test issued two executes (`fetchall` then `fetchone`); split to a single execute + `fetchall`, dropping the second-execute `fetchone` leg.
- **Backend-neutral assertions.** Snowflake folds the unquoted aliases to `N`/`S` (DuckDB keeps `n`/`s`) and returns `N` as `Decimal('1')` (DuckDB int `1`). Added a case-insensitive `_col()` helper and compared by value (`Decimal('1') == 1` is `True`), so one assertion holds on both backends rather than branching per backend.
- **`fetchall` cast.** `AsyncCursor.fetchall()` is typed `object` on the async surface; cast to `Sequence[Sequence[object]]` for the `len`/index assertions, mirroring the lifecycle test's `Any` treatment. basedpyright strict stays 0 errors.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `getfixturevalue` in the async test body re-enters the anyio runner**
- **Found during:** Task 1 (first verification run)
- **Issue:** The PATTERNS.md indirect pattern (`pool = request.getfixturevalue(pool_fixture)` inside the `@pytest.mark.anyio` test) raises `RuntimeError: ... another is already running` because the pool fixtures are async-generator fixtures and resolving them re-enters the running runner.
- **Fix:** Moved the indirection into a sync `pool` fixture (`@pytest.fixture(params=_BACKENDS)`) resolved at setup time; tests take `pool` directly. No `src/` change.
- **Files modified:** `tests/async/test_matrix_readpath.py`
- **Commit:** `429c3de`

**2. [Rule 1 - Bug] Single-interaction cassette + casing/type mismatch on the Snowflake leg**
- **Found during:** Task 1 (second/third verification runs)
- **Issue:** (a) a second `execute` against the single-interaction cassette raised `CassetteMissError: Interaction 1 not found`; (b) `table.column("n")` raised `KeyError` because Snowflake folds the alias to `N`; (c) `N` comes back as `Decimal`, not int.
- **Fix:** One execute per test (dropped the `fetchone`/second-execute leg); added the case-insensitive `_col()` helper; asserted by value (`Decimal('1') == 1`). The existing lifecycle cassette test had only asserted `num_rows == 1`, so it never surfaced (b)/(c).
- **Files modified:** `tests/async/test_matrix_readpath.py`
- **Commit:** `429c3de`

These are test-authoring corrections discovered against the real cassette/driver; the frozen async surface was never touched (CONSTRAINT held: no `src/` change, no new cassette recording).

## Issues Encountered
- **uv pre-commit hooks panic under the command sandbox.** The first `git commit` aborted with a `uv` tokio/`system-configuration` panic from the `basedpyright` hook (a sandbox artefact, NOT a real hook failure — `ruff format` had already passed and reformatted the docstrings). Re-ran the exact same commit with the sandbox disabled; all hooks (ruff, ruff-format, basedpyright, blacken-docs, detect-secrets) passed and the commit landed as `429c3de`. Consistent with the project MEMORY note on uv-under-sandbox. Never used `--no-verify`.

## Verification Evidence
- `.venv/bin/pytest tests/async/test_matrix_readpath.py -q` → 8 passed.
- `.venv/bin/pytest tests/async -q` → 80 passed.
- `git diff src/` → empty (frozen-surface constraint held).
- `.venv/bin/basedpyright tests/async/test_matrix_readpath.py` → 0 errors.
- `scan_async_test_hygiene('tests/async')` → no finding for `test_matrix_readpath.py` (every async test carries `@pytest.mark.anyio`; no `import asyncio`, no `@pytest.mark.asyncio`).
- `.venv/bin/mkdocs build --strict` → passes (docs gate; no public symbols added, only a test file with Google-style docstrings).

## Known Stubs
None. No placeholders, no empty data sources, no TODO/FIXME. The file exercises real backends end to end.

## User Setup Required
None. The Snowflake leg replays the existing offline cassette and skips cleanly when the driver/cassette is absent.

## Next Phase Readiness
- TEST-01 (asyncio/trio axis) and TEST-02 (DuckDB + Snowflake cassette) are now both proven on the read path.
- The indirect sync `pool` fixture and the `_col()` case-insensitive helper are available patterns for the remaining Wave 2 files (27-03 stability, 27-04 limiter-stress) should they also parametrize over the backend axis.
- 27-05's meta-test can assert `scan_async_test_hygiene('tests/async') == []` — this file complies.

## Self-Check: PASSED

- `27-02-SUMMARY.md` exists on disk.
- `tests/async/test_matrix_readpath.py` exists on disk.
- Task commit `429c3de` is present in the git log.
- `git diff src/` empty (frozen-surface constraint held).
- Pre-existing unrelated working-tree changes (`.planning/config.json`, `.planning/.continue-here.md`, `24-CONTEXT.md`) left untouched.

---
*Phase: 27-dual-backend-test-matrix*
*Completed: 2026-06-28*
