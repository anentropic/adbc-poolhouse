---
phase: 25-cancellation
artifact: review-fix
fixed: 2026-06-28
review_source: 25-REVIEW.md
findings_addressed:
  critical: 1
  warning: 5
  info: 3
findings_deferred:
  info: 1
status: complete
commits:
  - 1d642b3 fix(25): close CR-01 worker_started TOCTOU; re-raise on cancel (WR-01/02/04)
  - 26c35b2 fix(25): route invalidate through a dedicated teardown limiter (WR-03)
  - ff26320 test(25): regression tests for CR-01 dispatch window + WR-03/05, IN-02 nit
  - d450e81 docs(25): add synchronous-construction cue to async first-query example (IN-04)
---

# Phase 25 Code-Review Fix Summary

Fixes the findings in `25-REVIEW.md` for the cancellation machinery: the CRITICAL
TOCTOU race on `worker_started` (CR-01) plus the coupled cancel-path / recovery-path
warnings in the same code (WR-01..WR-05) and the cheap INFO nits (IN-01/02/04).

## One-liner

Moved the "worker started" signal off the worker thread: `offload` now acquires the
per-pool limiter token on the loop thread and fires a synchronous `on_dispatch` hook
before dispatching the worker, so `cancellable_offload`'s watcher reads the started
flag on the same thread it is written — closing the CR-01 race by construction — while
the cancel path always re-raises (never returns a stale value) and poison-recovery runs
off a dedicated teardown limiter.

## Root cause of CR-01

`worker_started` was written on the worker thread (`_run`) and read on the loop thread
(`_watcher`) with no happens-before edge. A cancellation delivered after the limiter
token was acquired and the worker thread dispatched but before `_run` set the flag made
the watcher read `False`, skip `adbc_cancel()`, and — because `offload` is
`abandon_on_cancel=False` — strand the just-started driver call with no abort, hanging
the task group until the call returned on its own.

The race is genuinely narrow under wall-clock timing (the worker OS thread usually wins
the flag write), which is why the original deterministic stub tests (gated on
`execute_call_count == 1`, set *after* the flag) never caught it. It is, however,
reliably reproducible under the trio `MockClock(autojump_threshold=0)`: the virtual
deadline autojumps the instant every loop task is blocked on the just-dispatched worker
— i.e. exactly in the post-dispatch / pre-driver-call window — so any worker-thread
signal loses the race. A direct reproduction on the pre-fix code produced
`adbc_cancel_call_count == 0` and a hung worker.

## The fix (chokepoint + guard constraint honored)

`src/adbc_poolhouse/_async/_offload.py`:
- `offload` now acquires the real per-pool token itself via `async with limiter:` on
  the loop thread, fires the new optional `on_dispatch` callback **synchronously** (no
  checkpoint between acquire and the callback), then dispatches the worker via
  `anyio.to_thread.run_sync(..., limiter=<per-call inner limiter>, abandon_on_cancel=False)`.
- Concurrency stays bounded by the held per-pool token; `to_thread.run_sync` borrows on
  behalf of the current task, so it cannot re-borrow the per-pool token already held.
- The literal `anyio.to_thread.run_sync(... limiter=, abandon_on_cancel=False)`
  chokepoint is preserved un-aliased, so `scan_async_package` still audits exactly one
  offload site. **`scan_async_package("src/adbc_poolhouse/_async/") == []` confirmed.**

`src/adbc_poolhouse/_async/_cancel.py`:
- `worker_started` is now set by `_mark_started`, passed as `on_dispatch` to `offload`
  and therefore run on the loop thread at dispatch. The watcher reads it on the same
  loop thread — no cross-thread read, no TOCTOU window, immune to MockClock autojump.
- A worker cancelled while still queued at token-acquire is never dispatched, so
  `on_dispatch` never runs and the flag stays `False` (EDGE-01/07 preserved:
  `invalidate_call_count == 0` for a never-started call).

This is the reviewer's preferred direction ("record token acquisition on the loop
thread before the thread is dispatched"). The reviewer's illustrative snippet passed the
*same* limiter to `run_sync` inside `async with limiter`, which raises
`RuntimeError("this borrower is already holding one of this CapacityLimiter's tokens")`;
the working realization holds the real token across the `async with` and dispatches under
a per-call inner limiter.

## Per-finding resolution

### CR-01 (CRITICAL) — RESOLVED
TOCTOU on `worker_started`. Fixed as above. Regression coverage:
- `TestOffloadDispatchSync` (`test_edge_cancel_depth.py`): deterministically locks the
  fix mechanism — `on_dispatch` runs on the loop thread, strictly before `fn`, with the
  token held (`borrowed_tokens == 1`). **Fails hard on the pre-fix `offload`** (no
  `on_dispatch` parameter → `TypeError`), so it is a durable guard against
  re-introducing a cross-thread flag.
- `test_cancel_in_dispatch_window_still_aborts`: cancels in the post-dispatch /
  pre-driver-call window via `fail_after` under `virtual_clock`, with **no
  release-in-finally** (only the watcher's `adbc_cancel` can unblock the worker).
  Proves `adbc_cancel_call_count == 1`, `invalidate_call_count == 1`, and the wall-clock
  watchdog never trips. Both backends; survives the ×20 loop.

### WR-01 + WR-04 — RESOLVED
Cancel path no longer returns a value. It yields once at `await anyio.sleep(0)` (so an
enclosing pending cancellation surfaces) and otherwise `raise get_cancelled_exc_class()
from None`. A cancelled, poisoned call can never return `None`/stale as a success. The
`# type: ignore[return-value]` is removed; `basedpyright` is clean with no suppression.

### WR-02 — RESOLVED
`cancelled_by_us` is set `True` **only after** `adbc_cancel()` and `on_abort()` both
return without raising. If the poison-recovery (`invalidate`) raises, the flag stays
`False`, so its exception is surfaced on the non-cancel branch (unwrapped from its
single-member group) rather than silently swallowed as the expected driver interrupt.

### WR-03 — RESOLVED
`AsyncConnection.invalidate` offloads through a **dedicated 1-token teardown limiter**
(`self._teardown_limiter`), not the shared pool `limiter`, so recovery never contends
for the pool token the just-aborted worker is still releasing. Removes the unenforced
scheduler-ordering dependency entirely. Coverage: `TestEdge09bOneTokenInvalidate`
(`test_edge_limiter.py`) drives a real cancel → invalidate on a `CapacityLimiter(1)`,
proving `adbc_cancel == 1`, `invalidate == 1`, `borrowed_tokens == 0`, watchdog never
trips — ×20, both backends.

### WR-05 — RESOLVED
The EDGE-29 parity reader (`test_tuple_equal_across_backends`) now `pytest.skip`s with a
clear reason when either backend leg is absent (`-k` filter, single-backend selection,
or xdist distributing the two recorder cases to different workers) instead of
KeyErroring or vacuously comparing a backend to itself. The docstring documents that the
suite must run in-process (no xdist) for the parity assertion to be meaningful.

### IN-01 — RESOLVED
The new loop-thread synchronization point is documented in `offload`'s `on_dispatch`
docstring, the `cancellable_offload` docstring (a dedicated synchronization paragraph),
and inline comments on `_mark_started` / the `async with limiter` acquire.

### IN-02 — RESOLVED
Removed the dead `sc = stub_conn.cursors[0] if stub_conn.cursors else None` / `del sc`
in the EDGE-05 stub leg of `test_edge_cancel_depth.py`.

### IN-04 — RESOLVED
Added `# synchronous: no await` to the `create_async_pool(...)` construction line in
`docs/src/guides/async.md`, mirroring the cue already on `conn.cursor()`.
`.venv/bin/mkdocs build --strict` exits 0.

### IN-03 — DEFERRED (per task scope)
Logging-observability nicety: `_adbc_cancel` silently no-ops a missing hook. The task
brief explicitly says "Skip IN-03 unless trivial — it's a logging-observability nicety."
Deferred; no behavioural risk introduced by this fix set (the real ADBC cursor always
exposes `adbc_cancel`; the tolerance only affects non-blocking replay backends).

## Verification evidence

- **Guard:** `scan_async_package("src/adbc_poolhouse/_async/") == []` (incl. the
  banned-asyncio-cancelled-error rule). `tests/test_async_guard.py` +
  `tests/async/test_async_guard.py` → 12 passed. The literal limitered
  `to_thread.run_sync` chokepoint stays the single offload site.
- **Cancel path never returns a value:** WR-01/04 resolved; no `type: ignore` on any
  return in `_cancel.py`.
- **Full suite:** `.venv/bin/pytest -q` → **396 passed, 2 skipped** (the 2 skips are the
  pre-existing async lifecycle skips, unrelated). Async subset → 72 passed.
- **×20 loop (MEMORY discipline, `rc=$?`, never `if ! pytest`):**
  `test_edge_cancel_depth.py` + `test_edge_limiter.py` + `test_edge_backend_parity.py`,
  both backends → **0 hangs, 0 fails over 20 runs**, all 20 logs grep-confirmed to
  contain the `41 passed` line. The new tests in isolation → 0 hangs / 0 fails over 20,
  all logs show `8 passed`. Watchdog is the wall-clock `real_clock_watchdog`, not
  `anyio.fail_after`. No positive-duration sleeps (event-gating / virtual clock only).
- **Lint/type:** `.venv/bin/ruff check` clean; `.venv/bin/basedpyright` → 0 errors, 0
  warnings, 0 notes.
- **Docs:** `.venv/bin/mkdocs build --strict` exits 0.
- **Prior EDGE assertions intact:** EDGE-01/02/03/04/05/06/07/09 (incl. the token leg),
  10/11/12, 19, 28, 29 all still pass; no regression of over-invalidate
  (EDGE-01/07 still assert `invalidate_call_count == 0` for never-started calls).

## Pre-fix discrimination (proof the bug was real)

- Direct reproduction of the CR-01 window on the pre-fix `_cancel.py`/`_offload.py` under
  trio `MockClock`: watcher observed `worker_started == False`, fired `adbc_cancel` 0
  times, worker hung until a real-thread safety releaser unblocked it.
- `TestOffloadDispatchSync` fails on the pre-fix `offload` (no `on_dispatch` param):
  4 failed → 4 passed after the fix.
- Pre-fix `EDGE-06 parity` `fail_after` leg now stable under the new offload (the
  MockClock-autojump exposure is closed).

## Files changed

- `src/adbc_poolhouse/_async/_offload.py` — loop-thread token acquire + `on_dispatch`
  hook + per-call inner limiter; chokepoint preserved.
- `src/adbc_poolhouse/_async/_cancel.py` — loop-thread `worker_started`, re-raise on
  cancel, post-recovery `cancelled_by_us`, docs.
- `src/adbc_poolhouse/_async/_connection.py` — dedicated `_teardown_limiter` for
  `invalidate`.
- `tests/async/test_edge_cancel_depth.py` — CR-01 regression + dispatch-sync contract
  tests; IN-02 nit.
- `tests/async/test_edge_limiter.py` — WR-03 1-token invalidate no-deadlock test.
- `tests/async/test_edge_backend_parity.py` — WR-05 topology-robust parity reader.
- `docs/src/guides/async.md` — IN-04 cue.

## Self-Check: PASSED

- All four commits present: `1d642b3`, `26c35b2`, `ff26320`, `d450e81` (verified via
  `git log`).
- All changed files exist on disk and are committed (`git status` shows no uncommitted
  fix files).
- Full suite + guard + ×20 loop + ruff + basedpyright + mkdocs all green on the
  committed state.
