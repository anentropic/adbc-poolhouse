---
phase: 22-feasibility-spike
reviewed: 2026-06-27T14:05:21Z
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
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 22: Code Review Report

**Reviewed:** 2026-06-27T14:05:21Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the GIL-release feasibility spike: the ADBC-free arithmetic core
(`_harness.py`), the threaded benchmark driver (`gil_release.py`), the package
init, the harness unit tests, and the README. Calibrated for maintainer-only
benchmark code excluded from the wheel — production-hardening concerns are held
to Info.

The arithmetic core is mathematically correct: `speedup = (n*single)/wall` and
`parallel_efficiency = speedup/n` reduce to the documented bounds (`n` / `1` /
`1/n`), the `report` dict keys and bounds match their docstrings, and the unit
tests assert the right invariants. No Critical defects.

The findings cluster on the two places the calibration notes flagged as
high-stakes: (1) the arithmetic functions divide by `wall` with no zero guard,
and (2) the `concurrent_wall` barrier silently couples the `n` parameter to
`len(conns)` with no timeout, so a length mismatch deadlocks forever. Both are
latent at the single in-repo call site but are real defects in reusable
functions, and neither is exercised by a test.

No structural findings were provided for this review.

## Warnings

### WR-01: `speedup()` / `parallel_efficiency()` raise `ZeroDivisionError` on zero wall-clock

**File:** `benchmarks/_harness.py:65`, `benchmarks/_harness.py:81`
**Issue:** `speedup` computes `(n * single) / wall` with no guard on `wall == 0.0`.
`parallel_efficiency` and `report` both flow through `speedup`, so all three
crash with `ZeroDivisionError` when `wall` is zero. This is not hypothetical for
this code: the README itself warns that "tiny queries finish faster than the
thread-pool and barrier overhead," and `time.perf_counter()` deltas for a
trivially fast `call` (or a smoke run with `--rows` very small) can round to
`0.0`. A maintainer running the documented smoke command with a tiny query can
take down the whole run on an unhandled exception rather than getting a (clearly
bogus) number. The calibration notes call out division-by-zero on this core as a
highest-value check; no test exercises `wall == 0`.
**Fix:** Guard the divisor and surface a sentinel/`inf` (or a clear `ValueError`)
instead of crashing:
```python
def speedup(single: float, wall: float, n: int) -> float:
    if wall <= 0.0:
        # sub-resolution wall time — ratio is undefined; signal rather than crash
        return float("inf")
    return (n * single) / wall
```
If a hard failure is preferred over `inf`, raise `ValueError("wall must be > 0; "
"query too fast to time — increase --rows")` so the message is actionable.

### WR-02: `concurrent_wall` deadlocks forever when `len(conns) != n`

**File:** `benchmarks/_harness.py:135-143`
**Issue:** The barrier is built with `n` parties (`threading.Barrier(n)`) but the
number of `task` invocations is driven by `ex.map(task, conns)`, i.e.
`len(conns)`. The two are independent parameters. If `len(conns) < n`, fewer than
`n` threads ever call `barrier.wait()`, the barrier never trips, and because the
barrier has **no timeout** every worker blocks permanently — the
`ThreadPoolExecutor` context manager then hangs on exit waiting for tasks that
will never finish. There is no assertion tying `len(conns)` to `n`. The sole
in-repo caller (`measure`) passes `conns` of length `n`, so this is latent today,
but it is an unguarded precondition on a reusable, separately-importable function
and a classic silent-hang trap for the next caller.
**Fix:** Either assert the contract or derive `n` from `conns` so they cannot
diverge, and add a barrier timeout so a mismatch fails loudly instead of hanging:
```python
def trial() -> float:
    if len(conns) != n:
        raise ValueError(f"len(conns)={len(conns)} must equal n={n}")
    barrier = threading.Barrier(n, timeout=60)
    ...
```
Prefer deriving `n = len(conns)` at the call boundary if a single source of truth
is acceptable.

### WR-03: Concurrent connections are never warmed, biasing `wall` upward (understates speedup)

**File:** `benchmarks/gil_release.py:156-158`
**Issue:** The warm-up and the single-call baseline both run exclusively on
`conns[0]` (`call(conns[0], rows)`). The other `n-1` connections used by
`concurrent_wall` are created but never exercised before the timed concurrent
phase, so their first call in `concurrent_wall` pays cold per-connection costs
(connection-local caches, lazy ADBC statement setup) that `conns[0]` already paid
during warm-up and baseline. This asymmetry inflates `wall_s` relative to
`single_call_s`, which deflates the headline `speedup_x` — i.e. it biases the
measurement toward the "GIL not released" conclusion, the opposite of an
optimistic bias. For a go/no-go decision driven by this ratio, a systematic
downward bias on speedup is a correctness concern for the *measurement*, not just
a nicety.
**Fix:** Warm every connection before timing, e.g.:
```python
for c in conns:
    call(c, rows)  # warm all connections, not just conns[0]
single = median(call(conns[0], rows) for _ in range(trials))
```

## Info

### IN-01: Temp database directory is never cleaned up (disk leak per run)

**File:** `benchmarks/gil_release.py:117`, `benchmarks/gil_release.py:121-124`
**Issue:** `_pool` creates the DB via `os.path.join(tempfile.mkdtemp(), "bench.db")`.
`tempfile.mkdtemp()` creates a directory that is the caller's responsibility to
remove; the `finally` block disposes the pool and closes the ADBC source but
never deletes the temp directory or the (potentially multi-GB for 20M rows)
`bench.db` file. Every invocation leaks a temp dir under `$TMPDIR`. Maintainer
tooling, so Info, but trivially avoidable.
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

### IN-02: `conns[i].close()` cleanup is not exception-isolated

**File:** `benchmarks/gil_release.py:161-162`
**Issue:** In the `measure` finally, `for c in conns: c.close()` will abort the
loop on the first `close()` that raises, leaving the remaining connections
un-returned to the pool. That in turn flips the downstream
`assert pool.checkedout() == 0` in `_pool` to fail — masking the original error
with a confusing leak assertion. Low likelihood (checkin rarely throws), hence
Info.
**Fix:** Isolate each close, e.g. wrap in `contextlib.suppress(Exception)` per
connection, or collect-and-reraise after attempting all closes.

### IN-03: `concurrent_wall` is uncovered by tests; `wall == 0` and N==1 wall paths untested

**File:** `tests/test_benchmarks_harness.py`
**Issue:** The suite thoroughly covers `speedup` / `parallel_efficiency` /
`report` / `median` and the N==1 edge, but never exercises `concurrent_wall`
(even with a synthetic in-process `call`, which the module's ADBC-free design
makes feasible) and never exercises the `wall == 0` / sub-resolution-timing path
that WR-01 concerns. Adding a `concurrent_wall` test with a fake `call` would
also have caught the WR-02 barrier/`conns` coupling. Info because CI's stated
contract is harness arithmetic + `checkedout()==0` only.
**Fix:** Add a test that drives `concurrent_wall(call=lambda c: 0.0, conns=[...],
n=len(conns), trials=1)` and a test asserting the chosen zero-wall behaviour from
WR-01.

---

_Reviewed: 2026-06-27T14:05:21Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
