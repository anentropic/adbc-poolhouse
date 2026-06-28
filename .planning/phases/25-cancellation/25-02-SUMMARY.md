---
phase: 25-cancellation
plan: 02
subsystem: async-core
tags: [cancellation, anyio, offload, invalidate, exception-group, async-cursor]

# Dependency graph
requires:
  - phase: 24-core-async-wrapper
    provides: "offload chokepoint, AsyncConnection/AsyncCursor offloaded surface, _in_use aliasing guard, shielded check-in"
  - phase: 25-cancellation
    plan: 01
    provides: "BlockingStubConnection.invalidate + invalidate_call_count seam, banned-asyncio-cancelled-error AST rule"
provides:
  - "cancellable_offload(adbc_cancel, fn, *args, limiter, on_abort) — watcher/worker task group, worker-started abort gate, single-member ExceptionGroup unwrap"
  - "AsyncConnection.invalidate() — shielded offloaded fairy.invalidate(), bypasses _in_use"
  - "six AsyncCursor query/fetch methods rewired through cancellable_offload with invalidate-on-real-abort"
affects: [25-03, 25-04, 25-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Watcher/worker anyio task group as a cooperatively-cancellable offload (D-25-01)"
    - "worker_started flag set on the worker thread (inside to_thread.run_sync) to distinguish entered-driver from queued-at-token-acquire"
    - "on_abort shielded callback so poison-recovery fires only on a genuine abort, never on a clean/never-started call"
    - "single-member ExceptionGroup unwrap (eg.exceptions[0]) preserving the bare AdbcError + worker frame (EDGE-17/19)"
    - "Lazy getattr-based adbc_cancel resolution tolerating a backend that lacks it"

key-files:
  created:
    - src/adbc_poolhouse/_async/_cancel.py
  modified:
    - src/adbc_poolhouse/_async/_connection.py
    - src/adbc_poolhouse/_async/_cursor.py
    - docs/src/guides/async.md

key-decisions:
  - "Invalidate moved INTO cancellable_offload's shielded watcher via on_abort, gated on worker_started — fixes a saturated-limiter deadlock and over-invalidate of a never-poisoned connection (deviation, Rule 1+2)"
  - "worker_started is set on the worker thread as fn's first action, the precise entered-driver boundary; a queued-at-token cancel leaves it False"
  - "adbc_cancel resolved lazily via getattr so a replay/cassette backend without it (D-24-04) is tolerated as a no-op rather than crashing on attribute access"
  - "EG unwrap kept inside cancellable_offload so cursor methods see a bare cancellation or bare AdbcError (RESEARCH Open Q2/A2)"
  - "to_thread.run_sync chokepoint stays literal in _offload.py; _cancel.py calls offload() only (scan_async_package stays [])"

patterns-established:
  - "Cooperatively-cancellable offload = watcher (parks on Event, aborts on cancel) + worker (offload, releases watcher in finally)"
  - "Poison-recovery gated on a real abort, never on a clean/queued cancel (EDGE-01/07 semantics)"

requirements-completed: [CANCEL-01, CANCEL-02, CANCEL-03, EDGE-19]

# Metrics
duration: 15min
completed: 2026-06-28
---

# Phase 25 Plan 02: Cancellation Machinery Summary

**The load-bearing cooperative-cancellation implementation: a `cancellable_offload` watcher/worker task group that aborts an in-flight ADBC call via the driver's thread-safe `adbc_cancel` and invalidates the poisoned connection (shielded), plus the rewire of the six `AsyncCursor` query/fetch methods through it. A worker-started gate makes the abort and poison-recovery fire only when the worker genuinely entered the driver call — closing a saturated-limiter deadlock and an over-invalidate that the verbatim research pattern would have shipped.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-28T01:05:41Z
- **Completed:** 2026-06-28T01:20:07Z
- **Tasks:** 2 completed
- **Files:** 1 created, 3 modified

## Accomplishments

- `src/adbc_poolhouse/_async/_cancel.py` (NEW): `cancellable_offload(adbc_cancel, fn, *args, limiter, on_abort)` — a two-task anyio task group. The watcher parks on an `Event`; on cancellation it fires `adbc_cancel()` once (shielded) and awaits the optional `on_abort()` recovery, then re-raises (never swallows, D-25-06). The worker runs `offload(... abandon_on_cancel=False)` and releases the watcher in `finally`. A single-member `ExceptionGroup` on the non-cancel path is unwrapped so a genuine `AdbcError` exits bare with its off-loop worker frame intact (EDGE-17/19).
- `AsyncConnection.invalidate()` (NEW public method): shielded, offloads `fairy.invalidate()`, bypasses `_enter_offload`/`_exit_offload` for the same reclaim-safety rationale as `__aexit__` (D-25-03, CANCEL-02). Google-style docstring (docs gate).
- Six `AsyncCursor` methods (`execute`, `executemany`, `fetchone`, `fetchmany`, `fetchall`, `fetch_arrow_table`) rewired from `offload(...)` to `cancellable_offload(..., on_abort=self._owner.invalidate)`; `fetchmany`'s `size is None` two-arm branch routes both arms. `close` left untouched (still shielded `offload`, deliberately non-cancellable, D-25-04).
- `to_thread.run_sync` stays literal in `_offload.py` only; `_cancel.py` calls `offload()`. `scan_async_package("src/adbc_poolhouse/_async/")` stays `[]` (incl. the Plan-01 `banned-asyncio-cancelled-error` rule).
- Docs gate: async guide gained a "Cancelling an in-flight query" section; `.venv/bin/mkdocs build --strict` exits 0 with no cross-reference warnings.

## Task Commits

1. **Task 1: `cancellable_offload` watcher/worker helper** — `8e1253a` (feat)
2. **Task 2: invalidate-on-cancel + worker-started abort gate** (incl. the deviation fixes) — `f7aed35` (feat)

_The Task-1 commit shipped the verbatim RESEARCH Pattern 1 body; Task 2's commit both wired it into the cursor/connection AND refined `cancellable_offload` (worker-started gate, `on_abort`) to fix two regressions the verbatim pattern surfaced under the existing test suite. The refinement to `_cancel.py` is committed with Task 2 because it is part of the same wiring deviation._

## Files Created/Modified

- `src/adbc_poolhouse/_async/_cancel.py` (NEW) — `cancellable_offload`. Final shape adds a `worker_started` nonlocal (set on the worker thread as `fn`'s first action) gating both `adbc_cancel` and `on_abort`, and an optional `on_abort` shielded recovery callback.
- `src/adbc_poolhouse/_async/_connection.py` — added `invalidate()` after `close()`.
- `src/adbc_poolhouse/_async/_cursor.py` — added `cancellable_offload` import, `adbc_cancel` to the `_SyncCursor` Protocol, a lazy `_adbc_cancel()` helper, and rewired the six methods. `anyio` import retained (used by `close`'s shield); the transient `get_cancelled_exc_class` import was removed once invalidate moved into `cancellable_offload`.
- `docs/src/guides/async.md` — replaced the "lands in a later release" placeholder with a cancellation/timeout section.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Saturated-limiter deadlock on a queued-acquirer cancel**
- **Found during:** Task 2 (full async suite — `TestEdge10CancelWhileQueued` and a direct probe).
- **Issue:** The plan's verbatim design (Pattern 2: cursor `except get_cancelled_exc_class(): await self._owner.invalidate()`) deadlocks when a query is cancelled while still *queued* at token-acquire on a saturated limiter. The cancelled-but-queued worker holds no token to release, so the invalidate's shielded `offload` waits forever for a token held by the still-blocked workers. `TestEdge10CancelWhileQueued` (a pre-existing, passing Phase-24-deferred reference test) flipped from a 0.04s pass to a 10s watchdog-tripping failure; a direct probe hung (timeout).
- **Fix:** Moved the poison-recovery into `cancellable_offload` via an `on_abort` callback, fired (shielded) only after a genuine `adbc_cancel` abort, and gated the whole abort path on a `worker_started` flag set on the worker thread (inside `to_thread.run_sync`, i.e. only after a token is acquired and the driver call entered). A queued-at-token cancel now leaves `worker_started` False: no `adbc_cancel`, no invalidate, no token contention, no deadlock.
- **Files modified:** `_cancel.py` (gate + `on_abort`), `_cursor.py` (pass `on_abort=self._owner.invalidate`, drop the per-method `except` branch).
- **Commit:** `f7aed35`

**2. [Rule 2 - Missing correctness] Over-invalidate of a never-poisoned connection (EDGE-01/07 semantics)**
- **Found during:** Task 2 (same investigation as #1).
- **Issue:** A connection whose worker never entered the driver is NOT poisoned and must NOT be invalidated (RESEARCH Observable Signals: `invalidate_call_count == 0` on EDGE-01/07; Pitfall 6). The verbatim design invalidated on every caught cancellation regardless of whether a real C call was aborted.
- **Fix:** The `worker_started` gate (from #1) makes invalidate fire only when an in-flight call was actually aborted. Probe confirms: queued cancel → `invalidate_count == 0`; worker-inside cancel → `adbc_cancel_count == 1`, `invalidate_count == 1`, `borrowed_tokens == 0`.
- **Files modified:** `_cancel.py`, `_cursor.py`.
- **Commit:** `f7aed35`

**3. [Rule 1 - Bug] `AttributeError: 'ReplayCursor' object has no attribute 'adbc_cancel'`**
- **Found during:** Task 2 (Snowflake cassette leg `test_async_snowflake_arrow_round_trip`).
- **Issue:** The rewire passes `self._cursor.adbc_cancel` to `cancellable_offload`, evaluated eagerly at call-construction. The `pytest-adbc-replay` `ReplayCursor` (a legitimate non-blocking replay backend, D-24-04) does not implement `adbc_cancel`, so the eager attribute access raised on the success path even though cancel never fires.
- **Fix:** Added `AsyncCursor._adbc_cancel()`, which resolves `adbc_cancel` lazily via `getattr(..., None)` and no-ops when absent. The six methods pass `self._adbc_cancel`. A non-blocking replay backend never aborts mid-flight, so the no-op path is correct and unreachable in practice for it.
- **Files modified:** `_cursor.py`.
- **Commit:** `f7aed35`

### Acceptance-criteria note (benign grep delta)

The plan's Task-2 acceptance criterion expected `grep -c 'self._owner.invalidate'` == 6 (the old per-method `await self._owner.invalidate()`). With the cleaner `on_abort=self._owner.invalidate` design the count is **7** (six methods, with `fetchmany`'s two arms each passing `on_abort`). The intent — every cancellable method drives the owner's invalidate on a real cancel — is fully preserved; the literal count differs because invalidate is now passed as a callback rather than called in six `except` blocks. `cancellable_offload` count is 8 (1 import + 7 call sites). `close` remains untouched (plain shielded `offload`).

## Authentication Gates

None.

## Environment Note

The `basedpyright` pre-commit hook invokes `uv`, which panics under the command sandbox (system-configuration NULL-object crash, MEMORY "uv sandbox workarounds"). Both task commits were therefore run with the sandbox disabled so the hooks executed normally; all hooks passed (ruff, ruff-format, basedpyright, blacken-docs, detect-secrets). No `--no-verify` was used.

## Verification

- `cancellable_offload` imports; `AsyncConnection.invalidate` present.
- `scan_async_package("src/adbc_poolhouse/_async/") == []` (incl. the new rule); no `to_thread.run_sync` call in `_cancel.py` (AST-confirmed; the only textual matches are docstring prose).
- `.venv/bin/basedpyright src/adbc_poolhouse/_async/` → 0 errors; `.venv/bin/ruff check`/`format --check` → clean.
- Phase 24 EDGE-15/17/18 regressions (`test_edge_aliasing.py`, `test_edge_exceptions.py`) → 6 passed.
- Full async + harness + guard suite → 75 passed, 2 skipped; full project suite → 362 passed, 2 skipped.
- **Loop-verified ×20** (MEMORY loop-flaky-concurrency lesson; `rc=$?` + grep, never `if ! pytest`): `tests/async tests/_async_harness` → 0 fails, 0 hangs.
- Behavioural probes (queued-cancel: no deadlock, `invalidate_count==0`, held tokens preserved; worker-inside cancel: `adbc_cancel==1`, `invalidate==1`, `borrowed==0`) → all correct.
- `.venv/bin/mkdocs build --strict` → exit 0, no cross-reference warnings (docs gate).

## Known Stubs

None. All deliverables are fully wired and exercised by the existing suite; the behavioural EDGE proofs (EDGE-02/04/05/19/29) land in 25-03/25-04, which drive this implementation.

## Threat Flags

None. No new network endpoint, auth path, file-access pattern, or trust-boundary schema change beyond the plan's `<threat_model>` (loop→worker `adbc_cancel`, cancelled-op→pool invalidate — both implemented as specified).

## Self-Check: PASSED

- Files exist: `src/adbc_poolhouse/_async/_cancel.py`, `_connection.py`, `_cursor.py`, `docs/src/guides/async.md` — all FOUND.
- Commits exist: `8e1253a`, `f7aed35` — both FOUND in `git log`.
