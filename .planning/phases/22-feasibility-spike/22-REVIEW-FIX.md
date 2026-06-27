---
phase: 22-feasibility-spike
fixed_at: 2026-06-27
review_path: .planning/phases/22-feasibility-spike/22-REVIEW.md
iteration: 2
fix_scope: all
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 22 — Code Review Fix Report (iteration 2)

> This is the second fix pass. Iteration 1 (scope `critical_warning`) fixed the 3 Warnings
> WR-01/02/03 (commits `05da6de`, `201b91d`, `f252b3a`). This pass (`--fix --all`) closes the 3
> remaining Info findings. After iteration 1, the re-review (`d8c7895`) confirmed
> 0 Critical / 0 Warning / 3 Info; this pass resolves all three.

## Fixed Issues

### IN-01 — temp-dir disk leak in `gil_release.py`

`measure._pool` created its DuckDB database under `tempfile.mkdtemp()` but never removed that
directory, leaking one temp dir (holding a potentially multi-GB `bench.db`) per benchmark run.

**Fix (`a48874f`):** capture the `mkdtemp()` path and `shutil.rmtree(tmpdir, ignore_errors=True)`
in the `finally`, ordered **last** — after the pool and ADBC source are closed — so the DB file is
no longer held open when the directory is removed. Docstring updated to state the cleanup ordering.

### IN-02 — non-isolated `conn.close()` loop masks the real error

The cleanup loop `for c in conns: c.close()` was not exception-isolated. A single raising `close()`
during unwind would abort the loop, leave the remaining connections checked out, and flip the
`pool.checkedout() == 0` assertion in `_pool` — surfacing a confusing leak assertion that masks the
true root cause (e.g. a warm-up or `concurrent_wall` failure propagating during unwind).

**Fix (`cb04a91`):** wrap each individual close in `contextlib.suppress(Exception)` so one failing
connection can no longer abort the rest. Every connection still gets closed on the happy path and
`pool.checkedout() == 0` still holds; only the error-masking cross-talk is removed.

### IN-03 — missing `n == 1` `concurrent_wall` coverage

The substantive `concurrent_wall` gaps (no coverage at all, no zero-wall test) were already closed in
iteration 1 via `TestConcurrentWall` + the zero-wall tests. The reviewer flagged only a narrow,
optional `n == 1` single-thread smoke case as still uncovered.

**Fix (`cda0ce2`):** added `TestConcurrentWall::test_single_thread_wall_nonnegative`, asserting the
`n == 1` single-thread path returns a finite, non-negative wall time. Low-risk, fast (pure callable,
no real driver).

## Verification

- `.venv/bin/pytest -q` → **313 passed, 2 skipped** (the 2 skips are the backend-conditional
  virtual-clock guards from Phase 23, unrelated). Sub-second runtime.
- `.venv/bin/ruff check` + `ruff format --check` → clean.
- Project-scoped `basedpyright` strict (`include = ["src", "tests"]`; `benchmarks/` is intentionally
  excluded) → 0 errors. The IN-01/02 edits add only the same pre-existing `reportUnknown*` class on the
  already-`# type: ignore`d `pool.connect()` line, which is outside the strict gate's scope.

## Notes

- The GO verdict in `22-GO-NO-GO.md` is unaffected by any fix in either pass. (The iteration-1 WR-03
  warm-up bias ran *against* GO; correcting it only widened the margin. The Info fixes here are pure
  resource-hygiene / test-coverage and change no measurement.)
- All `benchmarks/` files are maintainer-only and excluded from the built wheel; severity was
  calibrated accordingly.

_Iteration: 2 · Scope: all (Critical + Warning + Info) · Fixed: 3/3 · Skipped: 0_
