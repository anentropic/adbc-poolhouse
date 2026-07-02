---
phase: 32-p2-edge-hardening
plan: 01
subsystem: testing
tags: [anyio, contextvars, cancellation, offload, trio, asyncio, edge-hardening]

# Dependency graph
requires:
  - phase: 30-async-bulk-write
    provides: "adbc_ingest offload path + BlockingStubCursor.ingest_call_count counter"
  - phase: 31-dataframe-convenience
    provides: "fetch_df offload path + BlockingStubCursor.fetch_df/df_call_count + on_enter worker probe"
  - phase: 24-edge-cases
    provides: "test_edge_cancel_depth analog, real_clock_watchdog, concurrency_marks, make_stub_async_connection"
provides:
  - "EDGE-08 pinned: a cancel set before the adbc_ingest offload is delivered at the offload boundary (ingest_call_count == 0), both backends"
  - "EDGE-13 pinned: contextvar copy-in visible in the fetch_df worker"
  - "EDGE-14 pinned: worker contextvar mutation does not leak back to the caller after fetch_df"
affects: [32-02, 32-03, phase-33-documentation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Assert-don't-add: pin an anyio chokepoint guarantee on a NEW-method offload by cloning a green analog"
    - "Worker-entry contextvar probe via the stub's shared on_enter (not register_on_enter, which keys by the calling-thread id)"

key-files:
  created:
    - tests/async/test_edge_checkpoint.py
    - tests/async/test_edge_contextvars.py
  modified: []

key-decisions:
  - "EDGE-08 used the analog's bare pre-cancelled CancelScope (not the RESEARCH pytest.raises variant): a self-cancelling scope swallows the cancel at exit; ingest_call_count == 0 is the load-bearing assertion (PATTERNS §EDGE-08)"
  - "EDGE-13/14 worker probe wired via the shared on_enter attribute, NOT register_on_enter: register_on_enter keys the hook by the CALLING (loop) thread id while _block dispatches by the WORKER thread id, so the per-thread hook never fires; on_enter is _block's documented fallback and runs on the worker thread"

patterns-established:
  - "Pattern 1(a) contextvar pinning: set the module ContextVar, read/mutate it from a worker-thread on_enter probe on a real fetch_df offload, release the gated worker from a real side thread"

requirements-completed: [EDGE-08, EDGE-13, EDGE-14]

# Metrics
duration: 12min
completed: 2026-07-02
---

# Phase 32 Plan 01: P2 Edge Hardening — anyio chokepoint guarantees Summary

**Three RED-first-but-green-on-arrival tests pinning anyio's cancel-at-offload delivery (EDGE-08 on `adbc_ingest`) and contextvar copy-in / no-leak-back (EDGE-13/14 on `fetch_df`) across both asyncio and trio.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-02T20:57:00Z
- **Completed:** 2026-07-02T21:09:00Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments

- **EDGE-08** — `tests/async/test_edge_checkpoint.py`: a cancel set before the `adbc_ingest` offload with no intervening checkpoint is delivered at the offload boundary; the stub's ingest worker never runs (`ingest_call_count == 0`), and nothing to abort fires (`adbc_cancel_call_count == 0`, `invalidate_call_count == 0`, `observed_cancel is False`). Dual-backend; trio noted as the discriminator (every `await` is a checkpoint there).
- **EDGE-13** — `tests/async/test_edge_contextvars.py::test_contextvar_copied_in_to_fetch_df_worker`: a contextvar set before `fetch_df` is visible to the worker thread (`seen == ["outer"]`), proving `to_thread.run_sync`'s `copy_context` copy-in on a real new-method path.
- **EDGE-14** — `tests/async/test_edge_contextvars.py::test_contextvar_mutation_does_not_leak_back_from_fetch_df`: the worker's `_cv.set("inner")` is discarded at the offload boundary; the caller still reads `"outer"` afterwards (no leak back).
- All three assert an already-holding anyio guarantee at the single `offload()` chokepoint — no production code touched (test-only plan honoured).

## Task Commits

Each task was committed atomically:

1. **Task 1: EDGE-08 cancel delivered at the offload boundary on `adbc_ingest`** — `6dce5f2` (test)
2. **Task 2: EDGE-13/14 contextvar copy-in + no-leak-back on `fetch_df`** — `aedbc2b` (test)

## Files Created/Modified

- `tests/async/test_edge_checkpoint.py` — EDGE-08 cancel-at-offload assertion on `adbc_ingest`, dual-backend, `concurrency_marks` + `real_clock_watchdog` guard.
- `tests/async/test_edge_contextvars.py` — EDGE-13 copy-in + EDGE-14 no-leak-back on `fetch_df`, `-k`-selectable (`copied_in` / `no_leak`), no gating (deterministic single-offload assertions).

## Decisions Made

- **EDGE-08 cancel form:** used the analog's bare pre-cancelled `anyio.CancelScope()` (not the RESEARCH `pytest.raises(cancelled_exc)` variant). A self-cancelling scope swallows the cancellation at scope exit, so wrapping it in `pytest.raises` would fail; the load-bearing signal is `ingest_call_count == 0` (PATTERNS §EDGE-08 sanctions the bare form).
- **EDGE-13/14 probe mechanism:** wired the worker-side contextvar read/mutate through the stub's shared `on_enter` attribute rather than `register_on_enter`. See the deviation below — this was a discovered blocking issue in the PATTERNS-recommended mechanism, resolved without any harness change.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `register_on_enter` probe never fired; switched to the shared `on_enter` attribute**
- **Found during:** Task 2 (EDGE-13/14 contextvar tests)
- **Issue:** The plan and PATTERNS §Pattern 1(a) direct the worker-entry contextvar probe to be registered via `BlockingStubCursor.register_on_enter(probe)`. That method keys the hook in `_on_enter_by_thread` by `threading.get_ident()` of the CALLING thread — the loop thread — but `_block` looks the hook up by the WORKER thread's id (`self._on_enter_by_thread.get(threading.get_ident(), self.on_enter)`). The ids never match, so the probe never ran and `seen` stayed empty (4/4 red: `assert [] == ['outer']`).
- **Fix:** Set `sc.on_enter = _probe` directly (cleared to `None` in the `finally`). `on_enter` is `_block`'s documented single-worker fallback and fires on the worker thread inside the blocked section — exactly the copied-in-context observation point. Added an inline comment and updated the module docstring explaining why `register_on_enter` is wrong here.
- **Files modified:** `tests/async/test_edge_contextvars.py` (test-only; NO harness/production change)
- **Verification:** `.venv/bin/pytest tests/async/test_edge_contextvars.py -q` → 4 passed; `-k copied_in` and `-k no_leak` each exit 0; basedpyright 0 errors.
- **Committed in:** `aedbc2b` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** The plan's fallback clause anticipated this ("If `register_on_enter` proves awkward..."), though the resolution used the shared `on_enter` fallback rather than Pattern 1(b)'s direct-`offload` import — this keeps the assertion on the real `fetch_df` path (Pattern 1(a)'s stated preference) with zero harness edits. No scope creep; test-only constraint fully honoured.

## Issues Encountered

- The `register_on_enter` thread-id mismatch above. No production change was needed — the discovered-necessity contingency did NOT trigger; the fix stayed entirely within the test file using an existing harness attribute.

## Verification Evidence

- `.venv/bin/pytest tests/async/test_edge_checkpoint.py -x -q` → 2 passed (asyncio + trio).
- `.venv/bin/pytest tests/async/test_edge_contextvars.py -q` → 4 passed; `-k copied_in -x` → 2 passed, exit 0; `-k no_leak -x` → 2 passed, exit 0.
- `.venv/bin/basedpyright tests/async/test_edge_checkpoint.py tests/async/test_edge_contextvars.py` → 0 errors, 0 warnings, 0 notes.
- `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest <both files> -q` → 44 passed, 0 hangs (checkpoint marked ×20; contextvars unmarked, per plan).
- No `anyio.fail_after` used as a watchdog anywhere; `real_clock_watchdog` guards the checkpoint file; the contextvars file carries no `concurrency_marks` / `virtual_clock` / `real_clock_watchdog` (deterministic legs, per RESEARCH §Pattern-1).

## User Setup Required

None — test-only, no external service configuration.

## Next Phase Readiness

- The two lowest-risk P2 legs (EDGE-08/13/14) are green and locked. Remaining Phase 32 requirements (EDGE-24/31/32 + finalizers) proceed in later plans.
- No blockers. The discovered-necessity production contingency remains untriggered.

## Known Stubs

None — both files assert real observable behaviour on real `adbc_ingest` / `fetch_df` offload paths.

## Self-Check: PASSED

- `tests/async/test_edge_checkpoint.py` — FOUND
- `tests/async/test_edge_contextvars.py` — FOUND
- Commit `6dce5f2` — FOUND
- Commit `aedbc2b` — FOUND

---
*Phase: 32-p2-edge-hardening*
*Completed: 2026-07-02*
