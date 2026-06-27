---
phase: 23-test-harness-foundation
reviewed: 2026-06-27T00:00:00Z
depth: deep
files_reviewed: 9
files_reviewed_list:
  - tests/_async_harness/__init__.py
  - tests/_async_harness/conftest.py
  - tests/_async_harness/stubs.py
  - tests/_async_harness/gating.py
  - tests/_async_harness/clock.py
  - tests/_async_harness/guard.py
  - tests/_async_harness/test_stubs.py
  - tests/_async_harness/test_harness.py
  - tests/test_async_guard.py
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues
---

# Phase 23: Code Review Report

**Reviewed:** 2026-06-27
**Depth:** deep (cross-file: stubs <-> gating <-> test_harness contract trace)
**Files Reviewed:** 9
**Status:** issues_found (advisory, non-blocking)

## Summary

Phase 23 ships test-only async-harness infrastructure under `tests/_async_harness/`
plus one guard self-test at `tests/test_async_guard.py`. There is no runtime/src
change. The threading core is sound: `max_concurrent_in_execute` is lock-guarded on
both increment and decrement, the high-water mark is captured before `entered.set()`
so a gated reader cannot observe a stale max, and the internal `threading.Event` is
sticky so there is no lost-wakeup between `entered.set()` and `_event.wait()`. The
gating bridge correctly omits `token=` (it runs on an anyio worker thread), threads
`limiter=` through, and the clock facade's backend dispatch matches how `MockClock`
vs `aiotools.patch_loop()` are injected. The full suite (307 passed) and
basedpyright-strict back this up.

No Critical findings. The Warnings below are **contract-stability and reuse-safety**
risks that a green suite does not exercise today but that Phases 24/25/27 can trip on
when they consume the HARD CONTRACT in ways the self-tests do not. None block the
phase; they are flagged so the consuming phases inherit the hazards consciously.

## Warnings

### WR-01: Sticky `_event` makes a `BlockingStubCursor` single-use; reuse silently stops blocking

**File:** `tests/_async_harness/stubs.py:105-119, 176-183`
**Issue:** `_event` is a `threading.Event`, and `release` / `adbc_cancel` / `close`
all call `self._event.set()` without ever calling `.clear()`. Once ANY of those fires,
`_event` stays set permanently. A SECOND `execute`/`fetch_arrow_table` on the same
cursor reaches `_event.wait()` (stubs.py:119) and returns IMMEDIATELY without blocking
— so `entered` may already be set, `max_concurrent_in_execute` no longer reflects a
real gate, and the Pattern-3 "wait until the worker is inside execute" determinism is
gone. The self-tests never re-call a released cursor, so this is invisible today, but
the HARD CONTRACT is consumed by Phases 24/25/27 (e.g. an async wrapper that does
`execute` then `fetch_arrow_table` on the SAME cursor, or any "retry"/"second query"
EDGE case) where the second blocking call must also gate. There is also no
self-test pinning "a cursor blocks on its FIRST call only" as intended-or-not, so the
limitation is undocumented.
**Fix:** Either document the single-use constraint as an explicit contract note on the
class (matching the alias-limitation precedent in `guard.py`) AND assert it in a
self-test, or make the gate re-armable so each blocking call waits on its own latch.
Re-arm sketch (keeps the sticky-per-call semantics testable):
```python
def release(self) -> None:
    with self._lock:
        self._event.set()
        # re-arm so a subsequent execute/fetch blocks again
        self._event = threading.Event() if not self._closed else self._event
```
Note the re-arm must coordinate with any worker currently inside `wait()` on the old
event object — simpler is to add a per-call `threading.Event` created in `execute` /
`fetch_arrow_table`. Minimum acceptable fix: a docstring note + a self-test locking the
single-use behaviour, so Phases 24/25 do not discover it at integration time.

### WR-02: `BlockingStubConnection.close()` / `adbc_cancel()` do not release workers blocked in handed-out cursors

**File:** `tests/_async_harness/stubs.py:238-247`
**Issue:** `conn.close()` only increments `close_call_count`; `conn.adbc_cancel()` only
increments its counter and flips `observed_cancel`. Neither iterates `self.cursors` to
call `cursor.close()` / `cursor.adbc_cancel()`. This matches the Plan-02 spec
(connection methods are count-only by design), so it is NOT a spec violation. The risk
is contract fragility: the cursor docstring advertises a "no worker is ever stranded"
guarantee (T-23-04), but that guarantee holds only at the CURSOR level. A Phase-24/25
EDGE test that offloads `cursor.execute()` and then models connection teardown by
calling ONLY `conn.close()` will strand the worker thread forever — exactly the DoS
T-23-04 set out to prevent, just one level up. The connection's `cursors` handle-list
makes propagation trivial but it is not wired.
**Fix:** Document on `BlockingStubConnection` that connection-level `close`/`adbc_cancel`
are recording-only and do NOT release cursor-level workers, so consumers must release
each cursor explicitly. If Phases 24/25 need connection-close-cancels-cursors semantics
(plausible for EDGE-09..12/15/18), add opt-in propagation:
```python
def close(self) -> None:
    with self._lock:
        self.close_call_count += 1
        cursors = list(self.cursors)
    for c in cursors:
        c.close()  # release any worker blocked in a handed-out cursor
```

### WR-03: `observed_cancel` is written outside the lock that guards the matching counter

**File:** `tests/_async_harness/stubs.py:159-162` (cursor), `243-247` (connection)
**Issue:** In `adbc_cancel`, `adbc_cancel_call_count += 1` is inside `self._lock` but
`self.observed_cancel = True` is set OUTSIDE it (likewise `close` at 171-173 sets
`_closed` outside the lock). Today every reader observes these via a `threading.Event`
release (`done.wait()` / `entered`) or thread join, which supplies the
happens-before, so the suite is correct. But the HARD CONTRACT invites Phases 24/25/27
to read `observed_cancel` from the LOOP thread concurrently with the cancelling thread
(that is the whole point of the cancel-path EDGE cases). Splitting the flag and its
counter across the lock boundary means a future consumer can observe
`adbc_cancel_call_count == 1` while `observed_cancel` is still `False` (or vice-versa)
without an intervening synchronization point — a torn, surprising contract read.
**Fix:** Set the flag and bump the counter under the same lock so any reader that
synchronizes on one sees both:
```python
def adbc_cancel(self) -> None:
    with self._lock:
        self.adbc_cancel_call_count += 1
        self.observed_cancel = True
    self._event.set()
```
Apply the same to `close` (move `self._closed = True` inside the lock).

### WR-04: `run_blocking` offers no cancellation path; `entered`-then-cancel from the loop strands the worker thread

**File:** `tests/_async_harness/gating.py:75-80`
**Issue:** `_worker` calls `stub_call(*args)`, which blocks on the stub's
`threading.Event`. `anyio.to_thread.run_sync` is invoked WITHOUT
`cancellable=True` / `abandon_on_cancel=True`, so if the surrounding task group or a
`fail_after` cancels while the worker is blocked, the worker keeps running until the
stub is released by some OTHER actor — and the loop will hang at task-group exit
waiting to join it. The self-tests always release/cancel the stub explicitly before
leaving the task group, so this never bites here. But the module docstring advertises
this as "the offload shape the Phase 24 async wrappers will use" and explicitly frames
it around "trigger cancel / timeout (Pattern 3)". A Phase-24 consumer that wraps
`run_blocking` in `fail_after` (the natural timeout EDGE case) and does NOT separately
poke the stub will deadlock at scope exit. The cancellation-shielding behaviour of the
real offload is the single most important thing Phases 24/25 must get right, and the
harness models the non-cancellable variant silently.
**Fix:** Document explicitly that `run_blocking` is NON-cancellable by design and that
consumers MUST release/cancel the stub to unblock the worker (the loop will not reclaim
it on cancel). If a cancellable variant is wanted for the timeout EDGE cases, expose it
as an explicit parameter so the consuming test chooses the semantics:
```python
return await anyio.to_thread.run_sync(
    _worker, limiter=limiter, abandon_on_cancel=False  # or True, per the EDGE case
)
```

## Info

### IN-01: `_is_to_thread_run_sync` false-positive surface beyond the documented alias gap

**File:** `tests/_async_harness/guard.py:95-111`
**Issue:** The matcher flags ANY `<x>.to_thread.run_sync(...)` or
`to_thread.run_sync(...)` by attribute-chain tail, regardless of what `to_thread`
resolves to. A user-defined object named `to_thread` with a `run_sync` method, or
`my_executor.to_thread.run_sync(...)`, would be flagged even though it is unrelated to
`anyio.to_thread`. For the in-repo `src/adbc_poolhouse/_async/` target this is
acceptable (no such names exist), but only the aliased-re-import FALSE-NEGATIVE is
documented; the symmetric FALSE-POSITIVE surface is not.
**Fix:** Add a one-line note to the `Note:` block in `scan_async_package` that the
matcher is name-based and would also flag an unrelated `*.to_thread.run_sync` attribute
chain, so future maintainers are not surprised if the guard fires on a non-anyio call.

### IN-02: `scan_async_package` lets `SyntaxError` from `ast.parse` propagate uncaught

**File:** `tests/_async_harness/guard.py:159-163`
**Issue:** `ast.parse(py.read_text(...))` will raise `SyntaxError` (or
`UnicodeDecodeError`) on a malformed/non-UTF-8 `.py` file under `root`, aborting the
whole scan with a traceback rather than a `Finding`. For the trusted in-repo target
this is fine and arguably desirable (a syntax error in `_async/` SHOULD be loud), but
the docstring frames the scan as a tolerant "graceful no-op on absent dir" guard, so a
hard crash on a malformed file is an undocumented sharp edge.
**Fix:** Either document that unparseable files raise (intended), or wrap parse in a
`try/except SyntaxError` that emits a `Finding` so one bad file does not mask the rest.

### IN-03: `BlockingStubCursor.close()` does not block subsequent calls or surface "closed" state in the contract

**File:** `tests/_async_harness/stubs.py:103, 164-174`
**Issue:** `_closed` is set by `close()` but never read anywhere (no method checks it,
it is not a public contract attribute, and no self-test asserts it). It is effectively
dead state. A consumer cannot tell from the public surface whether a cursor was closed,
and a post-close `execute` neither raises nor is gated (it returns immediately via the
sticky event, per WR-01).
**Fix:** Either drop `_closed` (dead field) or promote it to a documented public
attribute and assert it in a self-test, so the close contract is observable.

### IN-04: `test_two_concurrent_executes_raise_max_concurrent` busy-polls with a sleep-on-Event idiom

**File:** `tests/_async_harness/test_stubs.py:108-113`
**Issue:** The test reuses a never-set `threading.Event poll` purely as a `sleep`
(`poll.wait(timeout=0.01)`), looping up to 500 times for the high-water mark to reach 2.
This is a deliberate poll (the comment says so) and is bounded, but it is a wall-clock
busy-wait in an otherwise sleep-free suite and could flake on a heavily loaded CI box if
both daemon threads are slow to schedule before 5s of accumulated polling. Low priority.
**Fix:** Gate on each worker's `entered` deterministically instead of polling the
derived max: pass a shared/own `threading.Event` per worker, `entered.wait()` both, then
assert `max_concurrent_in_execute == 2` with no loop.

---

_Reviewed: 2026-06-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
