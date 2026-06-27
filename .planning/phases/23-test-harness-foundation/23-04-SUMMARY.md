---
phase: 23-test-harness-foundation
plan: 04
subsystem: testing
tags: [anyio, trio, aiotools, virtual-clock, event-gating, dual-backend, self-tests, A1]

# Dependency graph
requires:
  - phase: 23-test-harness-foundation
    plan: 01
    provides: "tests/_async_harness/ package + nested function-scoped anyio_backend fixture (asyncio + trio-with-MockClock)"
  - phase: 23-test-harness-foundation
    plan: 02
    provides: "BlockingStubCursor (stubs.py), run_blocking (gating.py), virtual_clock (clock.py)"
  - phase: 23-test-harness-foundation
    plan: 03
    provides: "scan_async_package (guard.py) — independent; not exercised here"
provides:
  - "tests/_async_harness/test_harness.py — the dual-backend validation surface for the whole phase: block→release, block→adbc_cancel, off-loop-thread-id, deterministic max_concurrent==2, trio + asyncio virtual-clock, and a collection-level dual-parametrization check"
  - "Resolution record for Assumption A1: anyio's asyncio move_on_after/fail_after DOES honour aiotools.VirtualClock().patch_loop() — the asyncio virtual-clock leg passes with no wall-clock"
affects: [24-async-wrappers, 25-cancellation, 27-meta-guards]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-backend self-tests placed INSIDE the conftest package (tests/_async_harness/test_harness.py) so the anyio_backend fixture propagates downward and is visible (a sibling tests/test_async_harness.py would fail collection with 'fixture anyio_backend not found')"
    - "functools.partial to bind keyword args (entered=, limiter=) before tg.start_soon — anyio's TaskGroup.start_soon forwards POSITIONAL args only, never keywords"
    - "REAL wall-clock watchdog (time.monotonic() budget) for virtual-clock proofs, NOT a nested virtual fail_after — under trio's MockClock(autojump_threshold=0) a nested virtual watchdog autojumps to its OWN nearer deadline first and trips spuriously"
    - "Deterministic max_concurrent: two per-call anyio.Event gates, await BOTH entered events before asserting max_concurrent_in_execute == 2 (removes the spurious-pass race)"

key-files:
  created:
    - tests/_async_harness/test_harness.py
  modified: []

key-decisions:
  - "A1 RESOLVED (positive): anyio asyncio move_on_after honours aiotools VirtualClock().patch_loop() — test_asyncio_virtual_clock passes, so event-gating-only fallback for the asyncio timeout leg is NOT needed (D-02 keeps event-gating primary regardless)"
  - "The RESEARCH watchdog technique (nested virtual fail_after(5) around fail_after(3600)) is unsound on the trio MockClock leg — replaced with a monotonic wall-clock budget that proves no real time was consumed (T-23-08) and is correct on both backends"
  - "tg.start_soon does not forward keywords — run_blocking's entered=/limiter= are bound via functools.partial (the RESEARCH skeleton's keyword-on-start_soon form is illustrative, not the real anyio API)"

patterns-established:
  - "Backend-conditional self-tests guard on anyio_backend_name and pytest.skip the inapplicable leg, so test_trio_virtual_clock[asyncio] and test_asyncio_virtual_clock[trio] skip cleanly while both ids still appear in collection (dual-parametrization holds)"
  - "Collection-level meta-assertion via node-id suffixes (typed strings) rather than item.callspec.params (untyped under basedpyright strict)"

requirements-completed: [TEST-05]

# Metrics
duration: 10min
completed: 2026-06-27
---

# Phase 23 Plan 04: Dual-Backend Harness Self-Tests Summary

**The phase's validation surface: `tests/_async_harness/test_harness.py` drives the stub/gating/clock machinery through event-gating and the virtual clock under BOTH asyncio and trio with zero real sleeps — and resolves Assumption A1 positively (anyio's asyncio `move_on_after` honours aiotools `VirtualClock().patch_loop()`).**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-27T09:36:59Z
- **Completed:** 2026-06-27
- **Tasks:** 3 (Tasks 1+2 ship code; Task 3 is the full-suite + docs gate)
- **Files created:** 1 (`tests/_async_harness/test_harness.py`)

## Accomplishments

- **Event-gating self-tests (Task 1, D-06):** `test_block_then_release`, `test_block_then_adbc_cancel`, `test_offloaded_thread_id`, and `test_max_concurrent` drive `run_blocking` + the `anyio.Event` loop-facing gate under both backends. The block→release path leaves `observed_cancel` False; the block→`adbc_cancel` path flips it True and bumps `adbc_cancel_call_count`; the off-loop test proves `execute_thread_ids[0] != threading.get_ident()` (pre-proving the EDGE-25 mechanism); `test_max_concurrent` uses a `CapacityLimiter(2)` and TWO per-call `anyio.Event`s, awaiting BOTH before asserting `max_concurrent_in_execute == 2` (deterministic, no race). Every test is event-gated — no `anyio.sleep` / `time.sleep` anywhere.
- **Virtual-clock self-tests (Task 2, D-01):** `test_trio_virtual_clock` (trio leg) and `test_asyncio_virtual_clock` (asyncio leg) each prove `anyio.move_on_after(3600)` fires on VIRTUAL time (`cancelled_caught`) while a real `time.monotonic()` watchdog confirms < 5 s of wall-clock was consumed. The trio leg locks the RESEARCH-VERIFIED MockClock injection as a test; the asyncio leg resolves open-question A1.
- **A1 RESOLVED (positive):** anyio's asyncio `move_on_after`/`fail_after` DO honour `aiotools.VirtualClock().patch_loop()` — the asyncio virtual-clock leg passes with no wall-clock. So the contained-risk fallback (event-gating-only for the asyncio timeout leg) is NOT needed; event-gating remains primary per D-02 regardless. This is an honest pass, not a faked one (see the watchdog correction below).
- **Dual-parametrization collection check:** `test_dual_parametrization` inspects collected node ids and asserts every async self-test in the module carries both `[asyncio]` and `[trio]` ids. `--collect-only` confirms all six async tests are parametrized over both backends.
- **Full suite + docs gate (Task 3):** `.venv/bin/pytest -q` is green at **307 passed, 2 skipped** (baseline 291 → +13 async-harness items run here; the 2 skips are the backend-conditional virtual-clock guards on their inapplicable leg — expected). No sync-suite regression. `.venv/bin/mkdocs build --strict` exits 0 (phase ≥ 7 docs gate).

## Task Commits

Each task was committed atomically (sandbox disabled for the `uv`-backed basedpyright pre-commit hook — see Issues):

1. **Task 1: Event-gating + thread-id + max-concurrent self-tests (D-06)** — `8b1306b` (test)
2. **Task 2: Virtual-clock self-tests (trio + asyncio A1) + dual-parametrization check** — `bc4c952` (test)
3. **Task 3: Full-suite green + docs gate** — verification-only, no new source; results recorded above. No `Example:` gaps found (all four key entry points — `BlockingStubCursor`, `virtual_clock`, `run_blocking`, `scan_async_package` — already carry `Example:` blocks from Plans 02/03), so no docstring commit was needed.

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

## Files Created

- `tests/_async_harness/test_harness.py` — dual-backend self-tests placed INSIDE the conftest package so the `anyio_backend` fixture is visible: `TestEventGating` (block→release / block→adbc_cancel / offloaded-thread-id / deterministic max_concurrent), `TestVirtualClock` (trio + asyncio virtual-clock under a real wall-clock watchdog), and a module-level `test_dual_parametrization` collection check.

## Decisions Made

- **A1 resolved positively** — anyio's asyncio backend reads its deadline from the running loop's clock, which `aiotools.VirtualClock().patch_loop()` patches; `test_asyncio_virtual_clock` fires `move_on_after(3600)` instantly. Phase 25 does NOT need an event-gating fallback for the asyncio timeout leg.
- **The RESEARCH watchdog technique was unsound and was corrected** (see Deviations) — replaced the nested virtual `fail_after(5)` watchdog with a `time.monotonic()` wall-clock budget. This keeps the T-23-08 intent (catch a test that accidentally rides wall-clock) while being correct under the trio MockClock.
- **`tg.start_soon` forwards positional args only** — bound `entered=`/`limiter=` via `functools.partial` (the RESEARCH skeleton's keyword-on-`start_soon` form does not match the real anyio API).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tg.start_soon(run_blocking, ..., entered=..., limiter=...)` raises `TypeError`**
- **Found during:** Task 1
- **Issue:** The verbatim RESEARCH skeleton passes `entered=`/`limiter=` as keywords to `tg.start_soon`. anyio's `TaskGroup.start_soon(func, *args)` forwards positional args ONLY — keywords raise `TypeError: start_soon() got an unexpected keyword argument 'entered'`, failing all 8 collected event-gating tests.
- **Fix:** Bound the keyword args with `functools.partial(run_blocking, entered=..., limiter=...)` and `start_soon`'d the partial with the positional `stub.execute, "SELECT 1"`. Behaviour identical; deterministic gating preserved.
- **Files modified:** `tests/_async_harness/test_harness.py`
- **Verification:** `8 passed` (4 tests × 2 backends).
- **Committed in:** `8b1306b` (Task 1 commit)

**2. [Rule 1 - Bug] The RESEARCH nested-virtual-watchdog technique trips spuriously on the trio MockClock leg**
- **Found during:** Task 2
- **Issue:** RESEARCH Pattern 2 (line 294) proposes wrapping the inner virtual `fail_after(3600)` in an OUTER virtual `fail_after(5)` watchdog. Under trio's `MockClock(autojump_threshold=0)`, BOTH deadlines share the same virtual clock; autojump advances to the NEAREST deadline (5 s) the moment all tasks block, so the outer watchdog fires FIRST and raises `TimeoutError` — `test_trio_virtual_clock[trio]` failed. The technique only makes sense if the watchdog is real-time, but a nested anyio `fail_after` is virtual on this leg.
- **Fix:** Replaced the nested virtual watchdog with a real `time.monotonic()` budget: measure wall-clock around the `virtual_clock(...)` + `move_on_after(3600)` block and assert `cancelled_caught` (the virtual deadline fired) AND `wall_elapsed < 5.0 s` (no real time consumed). This preserves the T-23-08 intent and is correct on both backends. Verified independently that the trio MockClock fires `move_on_after(3600)` in ~9 ms of wall-clock.
- **Files modified:** `tests/_async_harness/test_harness.py`
- **Verification:** trio + asyncio virtual-clock tests pass; `--collect-only` shows both ids.
- **Committed in:** `bc4c952` (Task 2 commit)

**3. [Rule 3 - Blocking] `item.callspec.params` is untyped under basedpyright strict**
- **Found during:** Task 2
- **Issue:** The first `test_dual_parametrization` draft inspected `item.callspec.params["anyio_backend"]`; basedpyright strict raised 5 `reportUnknownMemberType` errors (`callspec`/`params` are untyped on pytest's `Item`), and a `reportAttributeAccessIssue` ignore did not cover them — blocking the strict-clean criterion.
- **Fix:** Rewrote the check to inspect collected node-id strings (typed) and match the `[asyncio]`/`[trio]` suffixes, asserting the suffix set equals both ids. No `pyright: ignore` needed.
- **Files modified:** `tests/_async_harness/test_harness.py`
- **Verification:** `.venv/bin/basedpyright tests/_async_harness/test_harness.py` → 0 errors.
- **Committed in:** `bc4c952` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 bug)
**Impact on plan:** All three are reconciliations of illustrative RESEARCH snippets against the real anyio API + the project's strict toolchain, plus one genuine correctness fix to an unsound watchdog pattern. No scope creep; the deliverable and its assertions are exactly what the plan specified, only the mechanism is correct.

## Issues Encountered

- **`uv`-backed pre-commit hooks panic under the command sandbox** (same as Waves 1–2): the `basedpyright` and `uv-lock` hooks invoke `uv`, which panics under the sandbox (`system-configuration` NULL-object panic → Tokio executor panic). Both task commits and the final metadata commit were run with the sandbox disabled; basedpyright was verified clean via `.venv/bin/basedpyright` beforehand. No functional impact.

## A1 Resolution Record

**Open-question A1** (RESEARCH lines 500/507–510): *Does anyio's asyncio `fail_after`/`move_on_after` deadline honour `aiotools.VirtualClock().patch_loop()`?*

**Resolution: YES.** `test_asyncio_virtual_clock` proves `anyio.move_on_after(3600)` fires instantly (`cancelled_caught` True) under `virtual_clock("asyncio")` — which enters `aiotools.VirtualClock().patch_loop()` — while the real `time.monotonic()` watchdog confirms < 5 s of wall-clock. anyio's asyncio backend computes its deadline from the running loop's clock, which aiotools patches, so virtual time drives the deadline. The contained-risk fallback (event-gating-only for the asyncio timeout leg) is therefore NOT required. Per D-02 event-gating remains the primary cancel-path mechanism regardless; the virtual clock now covers the deadline/timeout paths on BOTH legs, ready for Phase 25's EDGE-06/31/32.

## Threat Model Coverage

- **T-23-08 (DoS — a self-test consuming real wall-clock):** mitigated. The virtual-clock tests carry a real `time.monotonic()` budget (< 5 s); a test that accidentally rode wall-clock would blow the budget and fail loudly. (The nested-virtual-watchdog the threat register cited was found unsound on the trio leg and replaced — see Deviation 2 — but the mitigation intent is preserved by the monotonic budget.)
- **T-23-09 (Repudiation — A1 silently passing/failing):** mitigated. `test_asyncio_virtual_clock` exists specifically to surface A1; it passes, and the result is recorded above (not swallowed).
- **T-23-10 (Repudiation — dual-backend self-tests silently NOT running):** mitigated. The file is pinned INSIDE the conftest package; collection shows every async test parametrized over both ids, and `test_dual_parametrization` asserts this at runtime, so a regressed file location would fail loudly.

## Known Stubs

None. `test_harness.py` is pure test code exercising the Plan 01/02/03 machinery; no placeholders, no unwired data.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- The phase's validation surface is real and green: block→release / block→adbc_cancel / off-loop / max-concurrent / trio + asyncio virtual-clock all pass under both backends with no real sleeps; the EDGE-12/15/25 mechanisms are pre-proven.
- A1 is resolved positively, so Phase 25 can rely on the virtual clock for the asyncio timeout leg as well as the trio leg (event-gating still primary per D-02).
- The harness (stubs + gating + clock + guard) is now fully self-tested; Phase 24 can build the real `_async/` wrappers against a verified arrange/trigger surface.

## Self-Check: PASSED

- `tests/_async_harness/test_harness.py` — FOUND
- `.planning/phases/23-test-harness-foundation/23-04-SUMMARY.md` — FOUND
- Commit `8b1306b` (Task 1) — FOUND
- Commit `bc4c952` (Task 2) — FOUND
- Full suite: 307 passed, 2 skipped — VERIFIED
- `mkdocs build --strict` exit 0 — VERIFIED
- A1 resolved (asyncio virtual clock passes) — VERIFIED

---
*Phase: 23-test-harness-foundation*
*Completed: 2026-06-27*
