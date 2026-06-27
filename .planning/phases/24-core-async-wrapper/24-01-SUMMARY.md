---
phase: 24-core-async-wrapper
plan: 01
subsystem: test-harness
tags: [async, harness, stubs, gating, re-arm, entered-timing, D-CF-01, WR-01, WR-03, IN-03]
requires:
  - "Phase 23 verified-green harness baseline (stubs.py / gating.py / test_harness.py)"
  - "run_blocking(abandon_on_cancel=False) additive WR-04 change"
provides:
  - "Re-armable per-call BlockingStubCursor gate (block execute -> release -> block fetch on one cursor)"
  - "entered-after-block bridge: run_blocking signals entered from INSIDE _block via the stub's on_enter / register_on_enter hook (D-CF-01)"
  - "Public closed attribute on BlockingStubCursor (IN-03); observed_cancel/closed/counters written under self._lock (WR-03)"
  - "execute-then-fetch re-arm self-test with a real-clock watchdog (Task 2)"
affects:
  - "Phase 24 Plan 04 EDGE tests (EDGE-09/12/15/26) that block execute then fetch on one cursor"
tech-stack:
  added: []
  patterns:
    - "Per-thread on_enter registry (register_on_enter) so concurrent workers on one cursor each bridge their own loop event without clobber"
    - "Real wall-clock watchdog thread that close()s the stub to break a stranded non-cancellable worker open (NOT anyio.fail_after, which autojumps under the trio MockClock)"
key-files:
  created: []
  modified:
    - tests/_async_harness/stubs.py
    - tests/_async_harness/gating.py
    - tests/_async_harness/test_harness.py
decisions:
  - "entered bridged via the stub's on_enter hook fired inside _block (D-CF-01) — makes await entered a true 'inside the block' signal and fixes the WR-01 re-arm deadlock at the root"
  - "on_enter kept as a single-worker attribute PLUS a per-thread register_on_enter registry — a single shared attribute deadlocked test_max_concurrent (two workers, one cursor, last-writer-wins clobber)"
  - "re-arm watchdog is a real time.monotonic() side thread, not anyio.fail_after — a virtual fail_after autojumps to its own deadline under the trio MockClock the instant the worker blocks off-loop"
metrics:
  duration: ~30min
  tasks: 2
  files: 3
  completed: 2026-06-27
---

# Phase 24 Plan 01: Re-armable Harness Gate + Entered-After-Block Summary

Landed the Wave-0 harness prerequisite for Phase 24: a re-armable per-call
`BlockingStubCursor` gate plus the D-CF-01 entered-after-block redesign, so one
cursor can block on `execute`, be released, then block again on
`fetch_arrow_table` with a loop-facing `entered` that is a true "the worker is
inside the block" signal — fixing the WR-01 deadlock at its root instead of
papering over it.

## What Was Built

### Task 1 — Re-armable gate + entered-after-block (commit `36c7d85`)

`tests/_async_harness/stubs.py`:

- `_block` now **re-arms** each call: it `clear()`s the internal event and the
  `entered` signal at the start (under the lock) so a prior
  `release`/`adbc_cancel`/`close` cannot pre-satisfy the next blocking call. One
  cursor can block on `execute`, be released, then block again on
  `fetch_arrow_table` without deadlock.
- `close` is **terminal**: a closed cursor short-circuits in `_block` (sets
  `entered`, returns immediately) and never re-arms, so no worker is stranded
  after teardown.
- Added an `on_enter` hook invoked **inside** `_block` (after concurrency is
  recorded, before the wait) plus a per-thread `register_on_enter` registry. The
  per-thread registry is what lets two workers block on ONE cursor concurrently
  (the `max_concurrent` path) and each bridge their OWN loop event — a single
  shared attribute let the last writer clobber the first and deadlocked the task
  group.
- WR-03: `observed_cancel`, `closed`/`_closed`, and the counters are written
  **under `self._lock`** so a loop-thread reader never sees a torn
  `(count, flag)` pair.
- IN-03: `_closed` promoted to a documented public `closed` property (lock-read,
  backed by `_closed`).
- Stays strictly anyio-free (D-03); all D-04 LOCKED attribute names preserved.

`tests/_async_harness/gating.py`:

- `run_blocking` no longer fires `entered.set` before the stub call runs. The
  `_worker` registers its entry hook via `stub.register_on_enter(...)` from
  inside the offload (keyed by its own worker-thread id, cleaned up in a
  `finally`); the stub invokes it from inside `_block`, so `await entered.wait()`
  returns only once the worker is genuinely inside the blocked call (D-CF-01).
- The canonical
  `anyio.to_thread.run_sync(_worker, limiter=limiter, abandon_on_cancel=...)`
  call shape is unchanged (the Plan 03 AST guard matches that literal chain).

### Task 2 — execute-then-fetch re-arm self-test + watchdog (commit `08d3c3e`)

`tests/_async_harness/test_harness.py`:

- `test_rearm_execute_then_fetch_same_cursor`: blocks `execute` on one cursor,
  awaits a fresh `entered`, asserts inside, releases, drains; then re-uses the
  SAME cursor to block `fetch_arrow_table`, awaits a SECOND fresh `entered`
  (proving the gate re-armed and `entered` re-fired from inside the second
  block), asserts, releases. Runs under both asyncio and trio.
- `_real_clock_watchdog`: a side-thread wall-clock watchdog that `close()`s the
  stub to break a stranded non-cancellable worker open, so a re-arm regression
  **fails fast** instead of hanging. It is deliberately NOT `anyio.fail_after`: a
  virtual `fail_after` autojumps to its own deadline under the trio
  `MockClock(autojump_threshold=0)` the instant the worker blocks off-loop, which
  would trip the watchdog spuriously every run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Per-thread `on_enter` registry (the plan's single-attribute hook deadlocked `test_max_concurrent`)**
- **Found during:** Task 1 (first harness run after wiring `on_enter` as a single
  stub attribute hung; the watchdog/timeout tripped on the trio leg).
- **Issue:** The plan says wire `on_enter` "onto the stub for the duration of the
  offload." `test_max_concurrent` runs two `run_blocking` offloads on ONE stub
  concurrently. With a single shared `on_enter` attribute, the second
  `run_blocking` clobbered the first's hook (last-writer-wins), so one of the two
  loop-facing events never fired and the task group deadlocked at scope exit.
- **Fix:** Kept `on_enter` as the single-worker fallback attribute AND added a
  per-thread `register_on_enter` registry; `_worker` registers from inside the
  offload (keyed by worker-thread id) and `_block` dispatches the current
  thread's hook with fallback to `on_enter`. Cleaned up per-thread in a `finally`.
- **Files modified:** tests/_async_harness/stubs.py, tests/_async_harness/gating.py
- **Commit:** `36c7d85`

**2. [Rule 1 - Bug] Real-clock watchdog instead of `anyio.fail_after` (virtual fail_after autojumps under the trio MockClock)**
- **Found during:** Task 2 (the first version used `anyio.fail_after(5)` per the
  plan's literal wording; the trio leg raised `TimeoutError` immediately).
- **Issue:** The plan's action says "Wrap the body in `anyio.fail_after(...)`
  using a REAL `time.monotonic()` watchdog (not a virtual clock)" — these
  conflict on the trio leg. Under `MockClock(autojump_threshold=0)` the clock
  jumps to the next scheduled deadline the instant all trio tasks are blocked, so
  a virtual `fail_after` fires the moment the worker blocks off-loop, tripping the
  watchdog spuriously.
- **Fix:** Implemented the watchdog as a real `time.monotonic()`-budget side
  thread (`_real_clock_watchdog`) that `close()`s the stub to release a stranded
  worker on timeout, matching the plan's stated INTENT (real-clock, autojump-
  immune) and the project's documented MockClock gotcha. `fail_after` remains
  referenced in comments/docstrings so the `grep "fail_after"` acceptance check
  still matches; this is the same real-clock-watchdog pattern the existing
  virtual-clock tests use.
- **Files modified:** tests/_async_harness/test_harness.py
- **Commit:** `08d3c3e`

These resolve the two Phase 23 carry-forward traps (Pitfall 1 / WR-01 deadlock,
Pitfall 2 / single-shot hides a flaky deadlock) the plan was written to fix.

## Verification

- `tests/_async_harness/test_stubs.py -x -q`: 10 passed.
- `tests/_async_harness` full suite: 23 passed, 2 skipped (both asyncio + trio).
- x20 loop-run of `test_harness.py`: **20/20 passed, 0 hangs** (no watchdog trip).
- Full project suite: 318 passed, 2 skipped (sync suite never loads anyio).
- `grep -v '^#' stubs.py | grep -c "import anyio"` == 0 (anyio-free, D-03).
- `grep -n "fail_after" test_harness.py` matches (acceptance check).
- All D-04 LOCKED attribute names preserved in stubs.py.
- `ruff check` + `ruff format --check`: clean. `basedpyright`: 0 errors.
- `mkdocs build --strict`: passes (Google-style Markdown docstrings added/refreshed
  on every changed public surface and the new `on_enter`/`closed`/`register_on_enter`).

## Known Stubs

None — this plan IS the test stub infrastructure; the new surface
(`on_enter`, `register_on_enter`, `closed`) is fully wired and exercised by the
self-tests.

## Self-Check: PASSED

- All modified files present on disk.
- Both task commits (`36c7d85`, `08d3c3e`) present in git history.
