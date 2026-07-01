---
phase: 25-cancellation
reviewed: 2026-06-28T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - src/adbc_poolhouse/_async/_cancel.py
  - src/adbc_poolhouse/_async/_connection.py
  - src/adbc_poolhouse/_async/_cursor.py
  - tests/_async_harness/guard.py
  - tests/_async_harness/stubs.py
  - tests/_async_harness/test_stubs.py
  - tests/async/test_async_guard.py
  - tests/async/test_edge_backend_parity.py
  - tests/async/test_edge_cancel_depth.py
  - tests/async/test_edge_exceptiongroup.py
  - tests/async/test_edge_limiter.py
  - tests/test_async_guard.py
  - docs/src/guides/async.md
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
---

# Phase 25: Code Review Report

**Reviewed:** 2026-06-28
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 25 wires cooperative cancellation into the async layer: `cancellable_offload`
(a watcher/worker anyio task group), `AsyncConnection.invalidate` (shielded
poison-recovery), and the cursor rewire to abort-and-invalidate on cancel. The
shield placement, single-shot `adbc_cancel`, idempotent double-cancel, and the
single-member `ExceptionGroup` unwrap are all implemented correctly and are
well-covered by the EDGE suite. The source guard correctly bans
`asyncio.CancelledError`, and no raw `asyncio.CancelledError` appears in the
package.

The headline concern is a genuine, if narrow, **time-of-check / time-of-use race
on the `worker_started` flag**: it is written on the worker thread and read on the
loop thread with no happens-before relationship, and there is a window in which a
cancellation that arrives just as the worker thread is being dispatched reads
`worker_started == False`, skips the abort, and — because the offload is
`abandon_on_cancel=False` — leaves the just-started driver call with no
`adbc_cancel` to unblock it. The deterministic stub tests cannot exercise this
window (they gate on `execute_call_count == 1`, which is set *after* the flag), so
the suite is green but the production `fail_after` path is exposed. The remaining
findings are robustness/maintainability issues around the cancel-path return value,
visibility of cross-thread flags, and a couple of test-fixture correctness gaps.

## Critical Issues

### CR-01: `worker_started` cross-thread flag has a TOCTOU window that can strand a started worker

**File:** `src/adbc_poolhouse/_async/_cancel.py:135,142-144,146-157`
**Issue:**
`worker_started` is written on the **worker thread** inside `_run` (line 143,
`worker_started = True`) and read on the **event-loop thread** inside `_watcher`
(line 151, `if worker_started:`). There is no synchronization or happens-before
edge between the two.

Trace the dangerous interleaving:

1. `tg.start_soon(_worker)` schedules the worker coroutine; it reaches
   `await offload(_run, limiter=limiter)`, acquires a limiter token, and anyio
   dispatches `_run` onto a worker thread.
2. Before that worker thread executes line 143 (`worker_started = True`), the
   surrounding scope is cancelled (e.g. `fail_after` deadline fires at an
   arbitrary instant).
3. The watcher's `done.wait()` raises the framework cancellation. It reads
   `worker_started`, sees `False`, and **skips `adbc_cancel()`** entirely.
4. The worker thread now runs line 143, then `fn(*args)` — the blocking driver
   call — and blocks. Nothing will ever fire `adbc_cancel` for it.
5. Because `offload` uses `abandon_on_cancel=False`, the task group must *join*
   the worker before it can exit. With no abort signal, the join (and the whole
   `async with anyio.create_task_group()`) hangs until the driver call happens to
   return on its own — defeating the entire point of cooperative cancellation.

The EDGE tests never hit this because they gate the cancel behind
`await await_inside(lambda: sc.execute_call_count == 1)`, and the stub increments
`execute_call_count` *before* `_block` — i.e. strictly after `worker_started` is
already `True`. Production `fail_after` / `move_on_after` deadlines have no such
ordering guarantee.

This is the exact "queued vs. started" boundary the design hinges on, and the flag
that defines it is read across a thread boundary at the one moment it is being
flipped. Even setting aside memory-model concerns (CPython's GIL makes the write
eventually visible), the *timing* hole is real: the watcher can observe the
pre-write value.

**Fix:**
The flag must transition to "started" no later than the moment the offload commits
to running the worker, and the watcher must not be able to observe a stale `False`
for an offload that will go on to block in the driver. Two viable directions:

- Drive the started/queued decision off the limiter's own accounting instead of a
  worker-thread write — e.g. record token acquisition on the loop thread before the
  thread is dispatched, so the loop-thread watcher reads a loop-thread-written flag
  (no cross-thread read):
  ```python
  # loop-thread bracket around the offload, conceptually:
  async def _worker() -> None:
      try:
          async with limiter:            # token acquired on the loop thread
              nonlocal worker_started
              worker_started = True      # written on the SAME thread the watcher reads on
              result["v"] = await anyio.to_thread.run_sync(
                  _run, abandon_on_cancel=False  # NB: keep the single-chokepoint guard satisfied
              )
      finally:
          done.set()
  ```
  (Whatever shape is chosen must keep the `scan_async_package` single-`offload`
  discipline intact — see WR-04.)
- Alternatively, make the abort *unconditional once a token is held* and make
  `adbc_cancel` itself a safe no-op when the worker never entered the driver
  (the cursor's `_adbc_cancel` already tolerates a missing hook; firing it on a
  not-yet-blocked cursor must be proven harmless for the real ADBC driver, not
  just the stub).

At minimum, add a test that cancels in the window *after* the offload is awaited
but *before* `execute_call_count` reaches 1 (e.g. an `on_enter`/registered hook
that flips a loop-visible event the instant the thread is dispatched, and cancel
on that signal rather than on `execute_call_count`), run under the x20 loop gate
to prove no hang.

## Warnings

### WR-01: Cancel path can silently `return None` instead of propagating cancellation

**File:** `src/adbc_poolhouse/_async/_cancel.py:170-181`
**Issue:**
On the cancel path the helper swallows the worker's interrupt `ExceptionGroup`,
does `await anyio.sleep(0)`, then `return result.get("v")`. The correctness of the
"never returns a value on cancel" guarantee rests *entirely* on the `sleep(0)`
checkpoint re-raising a still-pending enclosing cancellation. If the enclosing
cancel scope is no longer active at that checkpoint (the design doc itself
acknowledges "an already-exited internal cancel scope makes it a clean no-op"),
the function returns `result.get("v")` — which is `None` (or a stale value) for a
call that was actually cancelled. For `fetchone`/`fetchall`/`fetch_arrow_table`,
the caller would then receive `None`/empty as if the query had succeeded, with no
exception. This is a latent data-correctness trap: a "successful" return that
represents an aborted, poisoned query.
**Fix:**
Do not return a value on the cancel path. Re-raise explicitly so the contract does
not depend on an enclosing scope still being live:
```python
if cancelled_by_us:
    await anyio.sleep(0)            # surface an enclosing cancellation if one is pending
    raise get_cancelled_exc_class() # otherwise still refuse to return a value
```
If returning is genuinely required for some caller, assert `"v" not in result`
before returning so a stale/None success can never masquerade as a real result.

### WR-02: `cancelled_by_us` is read on the loop thread but its guarding write races the worker's interrupt

**File:** `src/adbc_poolhouse/_async/_cancel.py:136,152,170`
**Issue:**
`cancelled_by_us` is set in the watcher (line 152) and read after the task group
exits (line 170). The branch assumes that whenever `cancelled_by_us` is True, the
`BaseExceptionGroup` carries *the worker's interrupt* (to be swallowed). But the
watcher sets `cancelled_by_us = True` *before* it calls `adbc_cancel()`; if
`on_abort()` (the shielded `invalidate`) raises — e.g. the fairy's `invalidate`
throws — that exception also lands in the group while `cancelled_by_us` is True,
and the cancel branch will silently swallow it via `result.get("v")` (see WR-01).
A failed poison-recovery would thus be hidden entirely, leaving the pool
mis-accounted with no signal.
**Fix:**
Either set `cancelled_by_us = True` only *after* `adbc_cancel()` and `on_abort()`
have both completed without raising, or on the cancel branch filter the group: swallow
only the driver-interrupt member and re-raise any unexpected member (an
`invalidate` failure) rather than collapsing the whole group to a value.

### WR-03: `invalidate` poison-recovery re-borrows a limiter token mid-abort — deadlock risk on a tiny limiter

**File:** `src/adbc_poolhouse/_async/_cancel.py:153-156`, `src/adbc_poolhouse/_async/_connection.py:229-230`
**Issue:**
Inside the shield the watcher does `adbc_cancel()` then immediately
`await on_abort()`. `on_abort` is `AsyncConnection.invalidate`, which calls
`offload(self._fairy.invalidate, limiter=self._limiter)` — i.e. it must *acquire a
limiter token*. The just-aborted worker still holds its token until its thread
returns from `fn` and `to_thread.run_sync` releases it. The code relies on the
`await on_abort()` yielding to the loop so the worker's offload can complete and
free its token first. This happens to hold on a multi-token limiter, but the
ordering is implicit and undocumented in code (only the prose docstring asserts
"the just-unblocked worker has released its token"). On a `pool_size +
max_overflow == 1` pool, recovery competes for the single token with the worker it
just aborted; correctness depends on scheduler ordering that is not enforced.
**Fix:**
Either join the aborted worker explicitly before invoking `on_abort` (so the token
is provably released first), or run `invalidate`'s detach off the limiter entirely
(poison-recovery is a teardown, not a throughput-bounded call — it arguably should
not consume a pool token at all). Add an EDGE test with a 1-token limiter driving a
real cancel→invalidate to prove no deadlock under the x20 loop.

### WR-04: Cancel path returns `result.get("v")` with a `type: ignore` that masks a real `None`-typing hole

**File:** `src/adbc_poolhouse/_async/_cancel.py:181`
**Issue:**
`return result.get("v")  # type: ignore[return-value]` suppresses the type checker
precisely where the value can legitimately be `None` for a `_T` that is not
`Optional`. The `type: ignore` hides exactly the defect described in WR-01 from the
static analyzer. Even if WR-01 is resolved by re-raising, leaving a blanket
`type: ignore` on a return statement is a maintenance hazard.
**Fix:**
Resolve WR-01 (re-raise instead of returning), which removes the need for the
suppression. If a value-return path is kept, narrow it: `result["v"]` (KeyError if
absent is a louder failure than a silent `None`), not `result.get("v")`.

### WR-05: EDGE-29 backend-parity reader test can pass when only one backend ran

**File:** `tests/async/test_edge_backend_parity.py:112-130`, `tests/async/test_edge_cancel_depth.py:84-146`
**Issue:**
`test_tuple_equal_across_backends` asserts both keys are present and equal, which
is good — but it depends on pytest collection/run order placing both parametrized
recorder invocations before the reader, with a *session-scoped* dict. If the suite
is ever run with `-k` filtering, `-p no:randomly` disabled, xdist (`-n auto`, which
distributes parametrized cases across workers and breaks the shared session dict),
or a single backend selected, the reader either errors on a missing key or — worse
under xdist — sees a dict populated by only the local worker and silently compares
a backend to itself. The parity guarantee (CANCEL-04) would then be vacuously
"green."
**Fix:**
Make the parity assertion robust to runner topology: collect both tuples in one
test that runs both backends inline (e.g. via `anyio.run` per backend within a
single non-parametrized test), or `xfail`/skip explicitly when a key is absent
rather than KeyErroring, and document that this suite must not run under xdist.

## Info

### IN-01: `worker_started` / `cancelled_by_us` lack any memory-visibility comment despite cross-thread use

**File:** `src/adbc_poolhouse/_async/_cancel.py:135-136,142-144`
**Issue:**
`worker_started` is written on a worker thread and read on the loop thread; the
inline comment explains the *semantic* boundary but says nothing about the
cross-thread read being safe only by virtue of the GIL. Future readers (or a
free-threaded/no-GIL build) will not know this is load-bearing.
**Fix:**
Add a comment noting the cross-thread access and its GIL dependence (and, once
CR-01 is fixed, document the new synchronization point).

### IN-02: `del sc` / unused locals in EDGE tests are dead manipulation

**File:** `tests/async/test_edge_cancel_depth.py:236,254`
**Issue:**
`sc = stub_conn.cursors[0] if stub_conn.cursors else None` is assigned then
`del sc`'d without ever being read (line 254). This is dead code that obscures the
test's intent.
**Fix:**
Remove the unused `sc` assignment and the `del sc`.

### IN-03: `_adbc_cancel` silently no-ops a missing hook — fine for stubs, risky for real drivers

**File:** `src/adbc_poolhouse/_async/_cursor.py:130-143`
**Issue:**
`_adbc_cancel` resolves `adbc_cancel` via `getattr(..., None)` and silently does
nothing if absent. The docstring justifies this for a non-blocking replay backend,
but for a *blocking* backend that simply lacks the method, a cancel would silently
fail to abort and (combined with `abandon_on_cancel=False`) hang — with no warning.
The "tolerated as a no-op" path is indistinguishable from a genuine bug.
**Fix:**
Keep the tolerance, but make it observable — log a debug/warning when the hook is
absent at the moment an abort is actually attempted, so a hang on a real backend is
diagnosable rather than silent.

### IN-04: Docs example uses `await pool.connect()` but `create_async_pool` is shown without `await`

**File:** `docs/src/guides/async.md:38-43`
**Issue:**
The first-query example calls `pool = create_async_pool(...)` (sync) and then
`async with await pool.connect()`. This is internally consistent with the codebase
(construction is sync, connect is async), but the mixed `await`/no-`await` on
adjacent pool calls is a common reader trip-hazard; the surrounding prose explains
it, but the example itself has no inline cue.
**Fix:**
Add a trailing comment on the construction line mirroring the `# synchronous: no
await` cue already used for `conn.cursor()`, e.g.
`pool = create_async_pool(...)  # synchronous: no await`.

---

_Reviewed: 2026-06-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
