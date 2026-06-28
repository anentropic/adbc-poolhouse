---
phase: 25-cancellation
plan: 04
subsystem: testing
tags: [anyio, trio, asyncio, cancellation, exceptiongroup, capacity-limiter, duckdb, adbc, edge]

# Dependency graph
requires:
  - phase: 25-cancellation (25-02)
    provides: cancellable_offload + single-member-EG unwrap + invalidate-on-cancel
  - phase: 25-cancellation (25-03)
    provides: cancelled_by_us flag (swallows the real-driver interrupt on the cancel path; keeps a genuine AdbcError bare on the non-cancel path)
  - phase: 25-cancellation (25-01)
    provides: BlockingStubConnection.invalidate + the re-armable BlockingStubCursor gate (adbc_cancel/release/close)
  - phase: 24-core-async-wrapper
    provides: AsyncPool/AsyncConnection/AsyncCursor, the transient-token model, the duckdb_async_pool + _stub_conn_on + await_inside + real_clock_watchdog harness
provides:
  - "EDGE-19: a genuine DuckDB AdbcError escapes cancellable_offload as a BARE AdbcError (single-member ExceptionGroup unwrapped), connection returns via reset (checkedout()==0), NOT invalidated"
  - "EDGE-09 cancel-mid-block leg (D-24-02): a transient limiter token returns to borrowed_tokens==0 exactly once on the cancel path, x50, both backends, loop-stable"
affects: [27-test-matrix, 28-docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bare-error fidelity proof on a real driver: pytest.raises(AdbcError) + not isinstance(excinfo.value, BaseExceptionGroup), pinning the single-member-EG unwrap"
    - "checkedout()==0 after a NON-cancel error as the invalidate-only-on-cancel guardrail (reset path, never the invalidate path)"
    - "Cancel-path token accounting via the stub gate: cancel the scope -> watcher fires adbc_cancel -> worker released -> token released exactly once"

key-files:
  created:
    - tests/async/test_edge_exceptiongroup.py
  modified:
    - tests/async/test_edge_limiter.py

key-decisions:
  - "EDGE-19 reuses _ACCOUNTING_LOOPS from test_edge_limiter (imported via the same dotted-path module) so the x50 loop count lives in one place"
  - "EDGE-09 cancel leg asserts adbc_cancel_call_count==1 in addition to borrowed_tokens==0, pinning that the watcher (not the belt-and-braces finally release) is what unblocked the worker"
  - "A belt-and-braces stub_cur.release() in the finally guarantees the task group can always exit (fail-fast assertion, never a hang) without changing the happy cancel path where adbc_cancel already released the worker"

patterns-established:
  - "Real-driver exception-fidelity EDGE: assert the bare type AND not-a-group on a live DuckDB pool, looped, with a checkedout()==0 check-in assertion"
  - "Cancel-mid-block token accounting on the stub gate, x50, real_clock_watchdog-wrapped, release-in-finally, no positive-duration sleeps"

requirements-completed: [EDGE-19]

# Metrics
duration: 7min
completed: 2026-06-28
---

# Phase 25 Plan 04: Limiter / Exception-Fidelity EDGE (EDGE-19 + EDGE-09 cancel leg) Summary

**EDGE-19 pins that a genuine DuckDB `AdbcError` escapes `cancellable_offload` as a BARE `AdbcError` (single-member ExceptionGroup unwrapped) and the errored connection returns via the reset path (`checkedout()==0`, not invalidated); EDGE-09's owed cancel-mid-block leg (D-24-02) proves a transient limiter token returns to `borrowed_tokens==0` exactly once on the cancel path, x50, loop-stable.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-28T02:14:00Z
- **Completed:** 2026-06-28T02:21:00Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- **EDGE-19** (`tests/async/test_edge_exceptiongroup.py`, NEW): a `SELECT * FROM does_not_exist` on a real DuckDB pool raises a bare `AdbcError` (asserting both `pytest.raises(AdbcError)` and `not isinstance(excinfo.value, BaseExceptionGroup)`), and after the errored block `_pool.checkedout()==0` — the connection returned via the reset path and was NOT invalidated (invalidate-only-on-cancel; Pitfall 6 / EDGE-18 preserved). Looped x50 so repeated errored round-trips never leak a connection. Green under both asyncio and trio.
- **EDGE-09 cancel-mid-block leg** (D-24-02, `test_token_returns_after_cancel`): gates a stub-backed worker inside `execute`, cancels the scope so the watcher fires the stub's `adbc_cancel`, releasing the worker; asserts `adbc_cancel_call_count==1` and `borrowed_tokens==0` after the cancelled `cancellable_offload` (transient token released exactly once). x50 loop, both backends, `real_clock_watchdog`-wrapped, release-in-finally, no positive-duration sleeps.
- Updated the `test_edge_limiter.py` module docstring: the cancel-mid-block leg is no longer documented as absent — the success/error/cancel trio now covers every token-exit path.

## Task Commits

Each task was committed atomically:

1. **Task 1: EDGE-19 bare-AdbcError unwrap + checkedout()==0** — `c26de0f` (test)
2. **Task 2: EDGE-09 cancel-mid-block token leg (D-24-02, x50)** — `40b1d8f` (test)

## Files Created/Modified
- `tests/async/test_edge_exceptiongroup.py` (NEW) — EDGE-19: bare-`AdbcError` unwrap + `checkedout()==0` on a real DuckDB pool, x50, both backends.
- `tests/async/test_edge_limiter.py` (MOD) — added `test_token_returns_after_cancel` to `TestEdge09TokenAccounting`; removed the "deliberately NO cancel-mid-block leg" note from the module docstring.

## Decisions Made
- **Reused `_ACCOUNTING_LOOPS`** from `test_edge_limiter.py` in the new EDGE-19 file (imported via the same `tests.async.test_edge_limiter` dotted-path module that the limiter suite already loads via importlib) so the x50 loop count is defined once and the two suites loop in lock-step.
- **EDGE-09 asserts `adbc_cancel_call_count==1`** alongside `borrowed_tokens==0`, so the test proves the *watcher* (driving the driver-level cancel) unblocked the worker — not the belt-and-braces `finally` release. The finally release exists purely as a fail-fast safety valve so the task group can always exit and the post-body assertion trips instead of hanging.

## Deviations from Plan

None — plan executed exactly as written. Both tasks landed on the first implementation; the only post-write adjustment was a one-line lint fix (ruff B023: bound the `await_inside` lambda's loop variable as a default arg `lambda sc=stub_cur: ...`), folded into the same Task 2 commit before it was made. This is a within-task lint conformance, not a behavioural deviation.

## Issues Encountered
- The `basedpyright` pre-commit hook panics under the command sandbox (the known `uv`-under-sandbox panic noted in the environment); both task commits were made with the sandbox disabled, NOT with `--no-verify`, so the full hook suite (ruff, ruff-format, basedpyright, blacken-docs, detect-secrets) ran and passed.

## Verification
- `.venv/bin/pytest tests/async/test_edge_exceptiongroup.py tests/async/test_edge_limiter.py -q` → 14 passed (7 tests × asyncio+trio).
- EDGE-09 cancel leg loop-verified: `for i in $(seq 1 20)` with `rc=$?` (never `if ! pytest`) → 20/20 pass logs, 0 failures, 0 hangs.
- `.venv/bin/ruff check` + `.venv/bin/basedpyright` clean on both files.
- No positive-duration sleeps; `real_clock_watchdog` (not `anyio.fail_after`) used as the autojump-immune watchdog.

## Threat Mitigations Verified
- **T-25-04-DOS** (leaked limiter token on the cancel path → CapacityLimiter starvation): `test_token_returns_after_cancel` asserts `borrowed_tokens==0` after a cancelled offload across x50 — the transient token releases exactly once on the cancel path.
- **T-25-04-TMP** (over-/under-invalidating an errored connection): EDGE-19 asserts a non-cancel `AdbcError` returns the connection (`checkedout()==0`, NOT invalidated), pinning the invalidate-only-on-cancel contract (Pitfall 6 / EDGE-18).

No new threat surface introduced (tests only; no production code touched, no new dependency).

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- EDGE-19 and the EDGE-09 cancel leg close the limiter/exception-fidelity seam for Phase 25. The cancellation phase's deferred D-24-02 token-accounting leg is now satisfied.
- Ready for the remaining Phase 25 plan(s) and the Phase 27 dual-backend test matrix; no blockers.

## Self-Check: PASSED

- Files: `tests/async/test_edge_exceptiongroup.py` (created), `tests/async/test_edge_limiter.py` (modified), `25-04-SUMMARY.md` — all present.
- Commits: `c26de0f`, `40b1d8f` — both in git history.

---
*Phase: 25-cancellation*
*Completed: 2026-06-28*
