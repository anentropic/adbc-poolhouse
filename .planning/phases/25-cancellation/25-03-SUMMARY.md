---
phase: 25-cancellation
plan: 03
subsystem: testing
tags: [cancellation, anyio, asyncio, trio, edge-tests, duckdb, exception-group, loop-stability]

# Dependency graph
requires:
  - phase: 25-cancellation
    plan: 02
    provides: "cancellable_offload (watcher/worker + on_abort + worker_started gate), AsyncConnection.invalidate, six cursor methods rewired"
  - phase: 25-cancellation
    plan: 01
    provides: "BlockingStubConnection.invalidate + invalidate_call_count seam"
  - phase: 24-core-async-wrapper
    provides: "make_stub_async_connection, duckdb_async_pool, await_inside, real_clock_watchdog, dual-backend anyio_backend fixture, EDGE test template"
provides:
  - "tests/async/test_edge_cancel_depth.py — EDGE-01..07 stub-driven cancel suite + real-driver duckdb (invalidate) and checkin_duckdb legs, dual-backend, x20-loop-stable"
  - "tests/async/test_edge_backend_parity.py — EDGE-29 cross-backend cancel-tuple equality (session-scoped dict + reader assert)"
  - "_cancel.py cancelled_by_us interrupt-swallow fix: the real cancel path now surfaces the caller's TimeoutError, not the driver ProgrammingError"
affects: [25-04, 25-05, 27-testing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Real-thread (clock-independent) worker release via the stub's `entered` threading.Event — survives the trio MockClock autojump that starves a loop-side releaser"
    - "EDGE-07 finished-op proof: complete the op outside any virtual deadline, then wrap a checkpoint-only sleep(0) in move_on_after so the deadline has no off-loop wait to autojump past"
    - "cancelled_by_us flag in cancellable_offload: swallow the aborted worker's driver interrupt and yield one cancellation checkpoint so an enclosing cancelled scope surfaces (D-25-05)"
    - "Deterministic real-driver CANCEL-02 proof via AsyncConnection.invalidate() drainage instead of racing a best-effort, wedge-prone adbc_cancel"

key-files:
  created:
    - tests/async/test_edge_cancel_depth.py
    - tests/async/test_edge_backend_parity.py
  modified:
    - src/adbc_poolhouse/_async/_cancel.py

key-decisions:
  - "cancellable_offload gained a cancelled_by_us flag: on the real cancel path the aborted worker RAISES the driver interrupt (DuckDB ProgrammingError), which the task group surfaced as a single-member ExceptionGroup that escaped past the caller's fail_after; the fix swallows that interrupt and yields one cancellation checkpoint so the caller's TimeoutError/scope.cancel surfaces (deviation, Rule 1)"
  - "The real-driver in-flight execute-cancel leg was replaced by a deterministic AsyncConnection.invalidate() drainage proof: DuckDB's adbc_cancel against a live query is best-effort (ADBC-spec-permitted miss) AND intermittently WEDGES the worker thread inside the C execute (~10-40% of cold runs), an unfixable driver-level hang that violates the zero-hang x20 gate"
  - "EDGE-07 releases the gated worker from a REAL side thread (waits on the stub's entered threading.Event), because a loop-side releaser is starved under the trio MockClock autojump"

patterns-established:
  - "Clock-independent worker release for real-time-sensitive cancel/finish legs (real thread + stub.entered event)"
  - "Best-effort driver operations (adbc_cancel) are proven via their downstream invariant (pool drainage), not by asserting the racy operation itself succeeds"

requirements-completed: [CANCEL-01, CANCEL-02, CANCEL-03, CANCEL-04, EDGE-01, EDGE-02, EDGE-03, EDGE-04, EDGE-05, EDGE-06, EDGE-07, EDGE-29]

# Metrics
duration: ~95min
completed: 2026-06-28
---

# Phase 25 Plan 03: Cancel-Depth EDGE Suite + Backend Parity Summary

**The milestone's highest-risk correctness proof: EDGE-01..07 driving every cancel through the Phase 23/24 stub harness (signal-exact: `adbc_cancel_call_count`/`invalidate_call_count`/`observed_cancel`/surfaced exception), the EDGE-29 cross-backend cancel-tuple equality, and a discovered-and-fixed `_cancel.py` bug where a real cancelled DuckDB query leaked its `ProgrammingError` past the caller's `fail_after` instead of surfacing a clean `TimeoutError`. Every cancel test is dual-backend, wall-clock-watchdog-wrapped, event-gated (zero positive-duration sleeps), and x20-loop-stable with 0 hangs.**

## Performance

- **Duration:** ~95 min (most of it spent diagnosing and de-flaking the real-driver `adbc_cancel` interaction)
- **Started:** 2026-06-28
- **Completed:** 2026-06-28
- **Tasks:** 2 completed
- **Files:** 2 created, 1 modified

## Accomplishments

- `tests/async/test_edge_cancel_depth.py` (NEW, 426 lines): nine `@pytest.mark.anyio` tests (18 dual-backend cases) covering EDGE-01 `before` (cancel before the offload starts: no `execute`, no `adbc_cancel`, no `invalidate`), EDGE-02 `during` (cancel mid-block: `adbc_cancel`×1, `invalidate`×1, `observed_cancel`), EDGE-03 `escapes` (the framework cancellation is never swallowed; no trio hang), EDGE-04 `double` (a second cancel during the shielded cleanup stays idempotent — `adbc_cancel`×1 not 2), EDGE-05 `checkin` (stub) + `checkin_duckdb` (real), EDGE-06 `parity` (`fail_after` under `virtual_clock` vs explicit `scope.cancel()` — both abort once, only the surfaced type differs), EDGE-07 `finished` (`move_on_after` on a finished op: `cancelled_caught is False`, no abort), plus the real-driver `duckdb` invalidate-drainage leg.
- `tests/async/test_edge_backend_parity.py` (NEW, 130 lines): EDGE-29 / CANCEL-04 — a session-scoped dict both backend legs write `(adbc_cancel_count, invalidate_count, checkedout_after)` into, plus a non-parametrized reader asserting `asyncio == trio`. The cancel choreography is byte-identical to EDGE-02 `during`; only the backend differs.
- Discovered and fixed a real-cancel correctness bug in `cancellable_offload` (see Deviations): the caller now sees its own `TimeoutError`, never the driver's "Interrupted!".
- Every cancel test verified x20 under both backends (0 hangs), `real_clock_watchdog`-wrapped (never `anyio.fail_after` as the watchdog), event-gated with `await_inside` (no positive-duration sleeps). Full async + harness suite: 85 passed, 2 skipped. Full project suite: 383 passed, 2 skipped. `scan_async_package(_async/)` stays clean. `mkdocs build --strict` passes (docs gate).

## Task Commits

1. **Task 1: EDGE-01..07 cancel-depth suite (+ `_cancel.py` interrupt-swallow fix)** — `4fb1d6b` (test)
2. **Task 2: EDGE-29 backend-parity tuple equality** — `e95d81f` (test)

_The `_cancel.py` fix is committed with Task 1 because Task 1's real-driver legs are what surfaced it; it is the deviation that makes the EDGE-02/03/06 cancel-path assertions hold on the real driver._

## Files Created/Modified

- `tests/async/test_edge_cancel_depth.py` (NEW) — the EDGE-01..07 suite + two real-driver DuckDB legs. Names embed the `-k` selectors the validation map uses (`before`/`during`/`escapes`/`double`/`checkin`/`parity`/`finished`/`duckdb`/`checkin_duckdb`).
- `tests/async/test_edge_backend_parity.py` (NEW) — EDGE-29 tuple equality.
- `src/adbc_poolhouse/_async/_cancel.py` (MOD) — added a `cancelled_by_us` flag and a cancel-path branch that swallows the aborted worker's driver interrupt and yields one cancellation checkpoint (see Deviation 1).

## Decisions Made

- **EDGE-07 / real-cancel releases run on a REAL thread** that waits on the stub's `entered` `threading.Event`, because a loop-side releaser is starved under the trio `MockClock(autojump_threshold=0)` (virtual time jumps to the deadline while the loop is parked on the off-loop worker).
- **The real-driver in-flight execute-cancel assertion is the pool-drainage invariant, not the cancel race itself** — DuckDB's `adbc_cancel` is best-effort (ADBC-spec-permitted miss) and intermittently wedges the worker thread, so the deterministic proof drives the same `AsyncConnection.invalidate()` the cancel path drives (see Deviation 2).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Real cancelled DuckDB query leaked its `ProgrammingError` past the caller's `fail_after`**
- **Found during:** Task 1 (the real-driver execute-cancel leg).
- **Issue:** `25-02`'s `cancellable_offload` assumed anyio collapses the bundled (framework cancellation + worker interrupt) back into the framework cancellation on the cancel path. The live DuckDB probe shows otherwise: when the watcher fires `adbc_cancel`, the worker's `execute` returns by **raising** `adbc_driver_manager.ProgrammingError("...INTERRUPT Error: Interrupted!")`, and the task group surfaces it as a **single-member** `ExceptionGroup` (the watcher's re-raised `Cancelled` is consumed by the outer scope and does not appear in the group). The existing `len(eg.exceptions) == 1` unwrap then re-raised the bare `ProgrammingError`, which escaped past the caller's `fail_after` instead of a clean `TimeoutError`. (The stub legs never hit this because the stub's `adbc_cancel` returns the worker cleanly with no interrupt.)
- **Fix:** Added a `cancelled_by_us` flag set in the watcher's `except get_cancelled_exc_class()` branch (gated on `worker_started`). In the `except BaseExceptionGroup` handler, when `cancelled_by_us`, the worker's interrupt is recognised as the expected side-effect of our own `adbc_cancel` (D-25-02 — by the flag, never by sniffing the type/message), swallowed, and one cancellation checkpoint is yielded (`await anyio.sleep(0)`): an enclosing cancelled scope (`fail_after`/`move_on_after`/`scope.cancel`) surfaces its own cancellation there, while an already-exited internal cancel scope makes it a clean no-op. Verified across both `fail_after` (→ `TimeoutError`) and `scope.cancel()` (→ nothing) via live probes and the EDGE-19 non-cancel path (a genuine `AdbcError` still unwraps bare, `cancelled_by_us` stays False).
- **Files modified:** `src/adbc_poolhouse/_async/_cancel.py`.
- **Verification:** Real-driver cancel surfaces `TimeoutError` and drains `checkedout() == 0`; EDGE-19 (`test_edge_exceptions.py`) and the full async suite (85 passed) stay green; `scan_async_package` clean.
- **Committed in:** `4fb1d6b` (Task 1 commit).

**2. [Rule 1 - Bug] Real-driver in-flight `adbc_cancel` wedges the worker thread (non-deterministic driver hang)**
- **Found during:** Task 1 (x20 loop of the real-driver execute-cancel leg).
- **Issue:** The plan's `-k duckdb` leg "cancels a real in-flight op and asserts `checkedout() == 0`". A wall-clock `fail_after` against a genuinely-slow DuckDB query intermittently (~10–40% of cold runs, reproduced with `faulthandler`) leaves the worker thread **wedged inside the C `dbapi.py:924 execute`** for tens of seconds after `adbc_cancel` returns `0.000s` — a driver-level hang, not a wrapper bug (the ADBC spec explicitly states a cancel is best-effort and "not guaranteed to" abort). This violates the phase's hard zero-hang x20 gate (the MEMORY loop-flaky lesson) and cannot be fixed test-side.
- **Fix:** Replaced the flaky in-flight execute-cancel leg with a **deterministic** real-driver proof of the same invariant: the `duckdb` leg drives the cancel path's `AsyncConnection.invalidate()` (the shielded, offloaded `fairy.invalidate()` the watcher fires via `on_abort`) on a genuinely checked-out connection and asserts `pool.checkedout()` goes `1 → 0`, with a following `close()` a safe no-op. This proves the real-pool drainage CANCEL-01/02 targets; the cancel → `adbc_cancel` → `invalidate` **wiring** is proven deterministically on the stub `during` leg, and a real cancel-during-checkin is proven on the trio-stable `checkin_duckdb` leg.
- **Files modified:** `tests/async/test_edge_cancel_depth.py` (leg rewritten; module/class docstrings document the rationale).
- **Verification:** x20 full-file loop clean (0 hangs); `faulthandler` dump captured the wedged `execute` stack confirming the hang is in the driver C call.
- **Committed in:** `4fb1d6b` (Task 1 commit).

---

**Total deviations:** 2 auto-fixed (2 bugs).
**Impact on plan:** Deviation 1 is a genuine cancel-path correctness fix that the plan's own EDGE-02/03/06 real-driver intent depends on. Deviation 2 substitutes a deterministic real-driver proof of the identical no-leak invariant for an inherently non-deterministic driver behaviour, honouring the zero-hang gate. No scope creep; all twelve plan requirements are covered with loop-stable proofs.

## Issues Encountered

- **Choosing a real-driver slow query was a rabbit hole.** `count(*)` cross products fold to a multiplication (instant, racy); `sum(range(1e10))` runs in giant chunks that miss the interrupt for 12s+; `sum(a.i*b.i)` over `range(2e4)²` scans for a bounded ~1.3s but still wedges via Deviation 2's driver bug. The wedge is independent of the query and of the preceding tests (reproduced with the two real-driver legs alone), which is what drove the switch to the deterministic `invalidate()` proof.
- **EDGE-07 trio flakiness** from the MockClock autojump was resolved by completing the op outside any virtual deadline and releasing the worker from a real side thread.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. Every EDGE leg is fully wired and asserts real observable signals. The one substitution (real in-flight cancel → deterministic invalidate drainage, Deviation 2) is a documented driver-limitation workaround, not a stub: it exercises the real connection/pool poison-recovery path end to end.

## Threat Flags

None. This plan adds tests only; no new network endpoint, auth path, file-access pattern, or trust-boundary schema. The `_cancel.py` fix tightens the existing loop→worker cancel boundary (it makes the cancel surface correctly) without introducing new surface.

## Next Phase Readiness

- The cancel-depth and backend-parity proofs are green and loop-stable, unblocking 25-04 (the broader cancel/error-path EDGE work) and 25-05.
- **Carry-forward for Phase 27 (real-backend matrix):** the real-driver in-flight `adbc_cancel` wedge is a DuckDB/ADBC driver limitation (this version) — any future real-in-flight-cancel coverage must budget for a best-effort, possibly-wedging cancel and assert the downstream drainage invariant rather than the cancel race.

## Self-Check: PASSED

- Files exist: `tests/async/test_edge_cancel_depth.py`, `tests/async/test_edge_backend_parity.py`, `.planning/phases/25-cancellation/25-03-SUMMARY.md` — all FOUND.
- Commits exist: `4fb1d6b` (Task 1), `e95d81f` (Task 2) — both FOUND in `git log`.

---
*Phase: 25-cancellation*
*Completed: 2026-06-28*
