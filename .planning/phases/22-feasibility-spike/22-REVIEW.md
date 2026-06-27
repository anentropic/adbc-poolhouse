---
phase: 22-feasibility-spike
reviewed: 2026-06-27T15:40:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - benchmarks/_harness.py
  - benchmarks/gil_release.py
  - benchmarks/__init__.py
  - tests/test_benchmarks_harness.py
  - benchmarks/README.md
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: issues_found
---

# Phase 22: Code Review Report

**Reviewed:** 2026-06-27T15:40:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Re-review of the GIL-release feasibility spike after the WR-01/02/03 fix pass.
Scope is maintainer-only benchmark code outside `src/` (excluded from the wheel),
so production-hardening concerns are held to Info per the phase calibration.

**All three prior Warnings are confirmed resolved in the current code:**

- **WR-01 (zero-wall division)** — RESOLVED. `speedup()` now guards `wall <= 0.0`
  and raises an actionable `ValueError` (`_harness.py:71-76`) instead of a bare
  `ZeroDivisionError`. `parallel_efficiency` and `report` both flow through
  `speedup`, so all three paths are covered. Tests added at
  `tests/test_benchmarks_harness.py:70-83` (`test_speedup_zero_wall_raises`,
  `test_parallel_efficiency_zero_wall_raises`, `test_report_zero_wall_raises`).
- **WR-02 (`Barrier(n)` vs `len(conns)` deadlock)** — RESOLVED. `concurrent_wall`
  now rejects `len(conns) != n` up front (`_harness.py:151-153`) and builds the
  barrier with `timeout=60` (`_harness.py:159`) as defence-in-depth. Tests added
  at `tests/test_benchmarks_harness.py:86-99` (`TestConcurrentWall`), covering the
  happy path and the length-mismatch `ValueError`.
- **WR-03 (warm-up bias)** — RESOLVED. The warm-up loop now iterates every
  connection (`for c in conns: call(c, rows)`, `gil_release.py:162-163`) before
  the timed single-call and concurrent phases, so `conns[1:]` no longer pay
  cold-start cost inside the timed region. The loop is correctly placed outside
  the timed region and inside the `try` (so cleanup still runs on a warm-up
  failure).

The arithmetic core remains mathematically correct and the new tests assert the
right invariants. No Critical or Warning defects remain. Three Info items persist
or are partially open; none block the spike. No new defects were introduced by
the fixes.

No structural findings were provided for this review.

## Info

### IN-01: Temp database directory is never cleaned up (disk leak per run)

**File:** `benchmarks/gil_release.py:117`, `benchmarks/gil_release.py:121-124`
**Status:** STILL OPEN (unchanged by the fix pass).
**Issue:** `_pool` creates the DB via `os.path.join(tempfile.mkdtemp(), "bench.db")`.
`tempfile.mkdtemp()` creates a directory that is the caller's responsibility to
remove; the `finally` block disposes the pool and closes the ADBC source but
never deletes the temp directory or the (potentially multi-GB at 20M rows)
`bench.db` file. Every invocation leaks a directory under `$TMPDIR`. The WR-03
fix added a per-connection warm-up that writes/reads more, but the leak itself is
unchanged. Maintainer-only tooling, so Info, but trivially avoidable.
**Fix:** Track and remove the directory in `finally`:
```python
import shutil
tmpdir = tempfile.mkdtemp()
db = os.path.join(tmpdir, "bench.db")
...
finally:
    assert pool.checkedout() == 0, "connections leaked from the pool"  # noqa: S101
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]
    shutil.rmtree(tmpdir, ignore_errors=True)
```

### IN-02: `conns[i].close()` cleanup loop is not exception-isolated

**File:** `benchmarks/gil_release.py:168-169`
**Status:** STILL OPEN (unchanged by the fix pass).
**Issue:** In the `measure` finally, `for c in conns: c.close()` aborts the loop
on the first `close()` that raises, leaving the remaining connections un-returned
to the pool. That flips the downstream `assert pool.checkedout() == 0` in `_pool`
to fail, masking the original error with a confusing leak assertion. The WR-03
fix did not touch this loop. The interaction is slightly more reachable now: the
warm-up loop (`gil_release.py:162-163`) and `concurrent_wall` (whose `ex.map`
re-raises any worker exception when the result iterator is consumed) can raise
inside the `try`, then this un-isolated close loop runs during unwind and can
swallow that root cause behind the leak assertion. Low likelihood (checkin rarely
throws), hence Info.
**Fix:** Isolate each close so cleanup always completes, e.g.
`with contextlib.suppress(Exception): c.close()` per connection, or
collect-and-reraise after attempting every close.

### IN-03: Residual `concurrent_wall` coverage gaps (mostly closed)

**File:** `tests/test_benchmarks_harness.py`
**Status:** LARGELY RESOLVED — re-scoped to the remaining gap.
**Issue:** The WR-01/WR-02 fix pass closed the substantive parts of the original
IN-03: `TestConcurrentWall` now exercises the barrier-gated driver with a
synthetic `call` (`test_returns_nonnegative_wall`) and the length-mismatch guard
(`test_conns_length_mismatch_raises`), and the zero-wall path that WR-01 concerns
is now covered by three tests. What remains uncovered is narrow: there is no test
that the *median over `trials`* dimension of `concurrent_wall` behaves (e.g.
`trials > 1` returning the median of differing per-trial walls — hard to assert
deterministically with real timing) and no `n == 1` concurrent-wall case. These
are minor and partly infeasible to assert deterministically given the function
times real wall-clock; CI's stated contract is harness arithmetic +
`checkedout()==0` only, so this stays Info.
**Fix:** Optionally add an `n == 1` `concurrent_wall` smoke case
(`concurrent_wall(lambda _c: 0.0, [object()], n=1, trials=1) >= 0.0`) to lock the
single-thread path. No further action required for the spike.

---

_Reviewed: 2026-06-27T15:40:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
