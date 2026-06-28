---
phase: 27-dual-backend-test-matrix
plan: 05
subsystem: testing
tags: [anyio, ast-guard, meta-test, pytest, async, edge-27, edge-30]

# Dependency graph
requires:
  - phase: 27-dual-backend-test-matrix
    provides: "scan_async_test_hygiene / scan_for_positive_sleep guard callables (Plan 27-01) and the complete Wave-2 tests/async/ suite (Plans 27-02/03/04) the meta-scan validates"
provides:
  - "tests/async/test_meta_guard.py: EDGE-27/30 real-package meta-tests asserting both guard callables return [] over the whole tests/async/ package"
  - "A standing meta-guard that fails CI if any future async test reintroduces import asyncio, @pytest.mark.asyncio, or a positive sleep literal"
affects: [dual-backend-test-matrix, phase-27-completion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Real-package meta-test mirroring tests/async/test_async_guard.py: plain sync test (no @pytest.mark.anyio — the AST guard needs no event loop), asserts scan_*('tests/async') == []"
    - "EDGE-30 sleep scan scoped to tests/async/ ONLY — the harness keeps deliberate positive sleeps under virtual clocks that would false-positive"

key-files:
  created:
    - tests/async/test_meta_guard.py
  modified: []

key-decisions:
  - "Meta-tests are plain sync (no @pytest.mark.anyio) — the scanners are pure-stdlib AST walks that never import or run the inspected modules, so no event loop is needed (mirrors test_async_guard.py:11-13)"
  - "EDGE-30 scan root is tests/async only, never the harness root — the harness has deliberate virtual-clock sleeps (anyio.sleep(3600)) that would false-positive (D-27-02 scope lock)"
  - "No file was flagged by either scan, so no fix was applied — the no-fix path is the expected D-27-02 outcome; no blanket rewrite of the ~10 hardened EDGE files"

patterns-established:
  - "Standing source-scan meta-guard certifying the no-asyncio / anyio-parametrized / no-positive-sleep discipline across the whole async test package"

requirements-completed: [EDGE-27, EDGE-30]

# Metrics
duration: ~4min
completed: 2026-06-28
---

# Phase 27 Plan 05: EDGE-27/30 Meta-Guards + Phase Completion Gates Summary

**A real-package meta-test (`tests/async/test_meta_guard.py`) that points the two Plan 27-01 AST guards at the now-complete `tests/async/` package and asserts both return `[]` — certifying the whole async suite is asyncio-free, anyio-parametrized, and free of positive sleep literals — plus the phase-level ×20 loop-stability and mkdocs docs gates.**

## Performance

- **Duration:** ~4 min
- **Completed:** 2026-06-28
- **Tasks:** 2 auto + 1 checkpoint (loop/docs gates run locally; Linux CI gate surfaced)
- **Files created:** 1

## Accomplishments
- `tests/async/test_meta_guard.py` with two plain-sync real-package meta-tests:
  - `test_async_test_package_hygiene`: `scan_async_test_hygiene("tests/async") == []` (EDGE-27 — no `import asyncio` / `from asyncio import ...`, no `@pytest.mark.asyncio`, every `async def test_*` carries `@pytest.mark.anyio`). Per D-27-03 the "both backends" axis here is the anyio asyncio/trio axis the marker selects.
  - `test_no_positive_sleep_in_async_tests`: `scan_for_positive_sleep("tests/async") == []` (EDGE-30 — no positive-duration sleep literal). Scan root scoped to `tests/async/` ONLY, never the harness root.
- Both meta-tests pass: `.venv/bin/pytest tests/async/test_meta_guard.py -x -q` → 2 passed. A preview scan already returned `[]` for both guards, so no existing file was flagged and no fix was applied (the expected D-27-02 no-fix path).
- Full async + harness + guard suite green: `.venv/bin/pytest tests/async tests/_async_harness tests/test_async_guard.py -q` → 141 passed, 2 skipped (Snowflake driver/cassette-absent fixtures skip cleanly).
- `.venv/bin/mkdocs build --strict` → exit 0 (the new public harness symbols' Google-style docstrings from Plan 27-01 render clean; the version-2 advisory banner from a plugin is not a strict error).
- ×20 loop-stability gate GREEN (0 hangs) across all four phase concurrency tests — `test_matrix_readpath`, `test_stability_arrow`, `test_limiter_stress`, `test_meta_guard` — 20/20 logs containing "passed" each, verified with the zsh-safe `rc=$?` + separate `grep` form (the `if ! pytest` form is a confirmed zsh history-expansion landmine).

## Task Commits

1. **Task 1: EDGE-27/30 real-package meta-tests** — `a38cb68` (test)
2. **Task 2: Full async suite green + docs/mkdocs gate** — verification-only, no file change, no commit (suite green, mkdocs --strict passes, no docstring fix needed).

## Files Created/Modified
- `tests/async/test_meta_guard.py` (created, 62 lines) — `TestRealAsyncTestPackageHygiene` with the two real-package meta-tests; imports `scan_async_test_hygiene` / `scan_for_positive_sleep` from `tests._async_harness.guard`; module docstring documents the read-only-AST / no-event-loop rationale and the `tests/async`-only sleep scope.

## Decisions Made
- **Plain sync meta-tests, no `@pytest.mark.anyio`** — the scanners are pure-stdlib `ast.parse` walks that never import or run the inspected modules, so no event loop is required. Mirrors `tests/async/test_async_guard.py`.
- **EDGE-30 scan scoped to `tests/async/` only** — `tests/_async_harness/` has deliberate positive sleeps under virtual clocks (`anyio.sleep(3600)`); scanning the harness root would false-positive (RESEARCH Pitfall 1, D-27-02).
- **No-fix path taken** — both scans returned `[]` against the complete Wave-2/EDGE suite, so no file was flagged and no fix applied; no blanket rewrite of the hardened EDGE files (D-27-02).

## Deviations from Plan

None — plan executed exactly as written. (Task 2 was a verification-only task: the suite was already green and `mkdocs --strict` already passed, so no docstring fix or extra code was needed, hence no second commit.)

## Issues Encountered
- **uv pre-commit hooks panic under the command sandbox.** The first `git commit` aborted with a uv tokio executor panic from the `basedpyright` hook ("Attempted to create a NULL object"). This is the documented uv-under-sandbox issue, not a real type failure — verified independently with `.venv/bin/basedpyright tests/async/test_meta_guard.py` → 0 errors. Resolved by re-running the exact `git commit` with the sandbox disabled; all hooks (ruff, ruff-format, basedpyright, blacken-docs, detect-secrets) then passed. No `--no-verify` used.
- **zsh `!` history-expansion landmine in the loop gate.** The first loop attempt used `if ! grep ...`, which zsh parsed as history expansion (`command not found: !`), silently skipping the failure check and faking green "OK" lines. Re-ran with the MEMORY-prescribed zsh-safe form (`rc=$?` + separate `grep -q` capturing `grc=$?`), confirming a genuine 20/20 across all four tests.

## CI / Cross-Platform Gate (remaining human-action)
- The new `tests/async/test_meta_guard.py` is collected by the `quality` CI job (full suite) and correctly EXCLUDED from the `sync-no-anyio` job, which ignores `tests/async` and `tests/_async_harness` (`.github/workflows/ci.yml:87`).
- The Linux `quality` CI gate is the one remaining human-action: a green local ×20 loop does NOT prove cross-platform stability (Phase 24-26 landmine — passes on macOS, can hang on Linux CI). This run is NOT authorized to push the branch, so the gate is surfaced as a checkpoint for the user.

## User Setup Required
None — no external service configuration. The Snowflake fixture replays an offline cassette and skips cleanly when the driver/cassette is absent.

## Next Phase Readiness
- EDGE-27 and EDGE-30 are closed at the local level; the async test package is asyncio-free, anyio-parametrized, and positive-sleep-free as a standing meta-guard.
- Phase 27 local deliverables are complete (all five plans). The only outstanding item is the cross-platform Linux `quality` CI confirmation, which requires the user to push `gsd/v1.4.0-async-api`.
- No `src/` modification; the frozen async surface is intact.

## Self-Check: PASSED

- `27-05-SUMMARY.md` exists on disk.
- `tests/async/test_meta_guard.py` exists; commit `a38cb68` present in git log.
- `git diff src/` empty (frozen-surface constraint held).
- Pre-existing unrelated working-tree changes (`.planning/config.json`, `.planning/.continue-here.md`, `24-CONTEXT.md`) left untouched.

---
*Phase: 27-dual-backend-test-matrix*
*Completed: 2026-06-28*
