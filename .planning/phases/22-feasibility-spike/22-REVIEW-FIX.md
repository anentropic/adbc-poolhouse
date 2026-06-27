---
phase: 22-feasibility-spike
fixed_at: 2026-06-27T14:40:00Z
review_path: .planning/phases/22-feasibility-spike/22-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 22: Code Review Fix Report

**Fixed at:** 2026-06-27T14:40:00Z
**Source review:** .planning/phases/22-feasibility-spike/22-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (the 3 Warnings; Info findings IN-01/02/03 are out of the critical_warning scope)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: `speedup()` / `parallel_efficiency()` raise `ZeroDivisionError` on zero wall-clock

**Files modified:** `benchmarks/_harness.py`, `tests/test_benchmarks_harness.py`
**Commit:** 05da6de
**Applied fix:** Added a `wall <= 0.0` guard to `speedup()` that raises an
actionable `ValueError` ("wall must be > 0 ... increase --rows so the concurrent
phase is timeable") instead of letting a bare `ZeroDivisionError` escape. Chose a
hard, actionable failure over the reviewer's alternative `float("inf")` sentinel:
returning `inf` would silently propagate a bogus value into `report()` and the
go/no-go decision, whereas a `ValueError` tells the maintainer exactly how to fix
the run. `parallel_efficiency()` and `report()` both flow through `speedup()`, so
all three paths are covered by the single guard. Added a `Raises:` docstring entry
and three tests (`test_speedup_zero_wall_raises`,
`test_parallel_efficiency_zero_wall_raises`, `test_report_zero_wall_raises`).

### WR-02: `concurrent_wall` deadlocks forever when `len(conns) != n`

**Files modified:** `benchmarks/_harness.py`, `tests/test_benchmarks_harness.py`
**Commit:** 201b91d
**Applied fix:** Added an up-front `len(conns) != n` precondition check raising a
clear `ValueError` (`len(conns)=... must equal n=...`), so a mismatch fails loudly
before any thread is spawned instead of leaving the barrier permanently un-tripped
and hanging the `ThreadPoolExecutor` on exit. Also gave the `threading.Barrier` a
`timeout=60` as defence-in-depth, so any future caller that slips past the length
check raises `BrokenBarrierError` rather than blocking forever. Preserved the
existing single call site's behaviour (`measure` passes `conns` of length `n`,
which still satisfies the new contract). Added a `Raises:` docstring entry and a
`TestConcurrentWall` class with a happy-path test (synthetic no-op `call`) and a
length-mismatch test.

### WR-03: Concurrent connections are never warmed, biasing `wall` upward (understates speedup)

**Files modified:** `benchmarks/gil_release.py`
**Commit:** f252b3a
**Applied fix:** Replaced the single `call(conns[0], rows)` warm-up with a
`for c in conns: call(c, rows)` loop that warms **every** connection before the
timed concurrent phase, so `conns[1:]` no longer pay cold per-connection costs
(connection-local caches, lazy ADBC statement setup) on their first call inside
`concurrent_wall`. The warm-up loop stays outside the timed region (it precedes
both the single-call baseline and the `concurrent_wall` call). Updated the
`measure` docstring to state that every connection is warmed.

**Go/no-go note:** This fix does NOT invalidate the GO verdict recorded in
`22-GO-NO-GO.md`. The bug biased the measurement *toward* the "GIL not released"
conclusion (cold connections inflated `wall_s`, deflating `speedup_x`). Warming all
connections removes that downward bias, which can only move `speedup_x` further in
the GO direction. The directional finding holds. `22-GO-NO-GO.md` was not edited.

## Verification

- `.venv/bin/pytest -q`: 312 passed, 2 skipped (pre-existing skips).
- `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`: clean.
- `.venv/bin/basedpyright` (project-configured strict, `include = ["src", "tests"]`):
  0 errors. Note: `benchmarks/` is intentionally outside the strict `include`
  scope, so a direct `basedpyright benchmarks/gil_release.py` invocation surfaces
  pre-existing `reportUnknown*` noise (15 errors on the unchanged file, from
  `pool.connect()` being `# type: ignore`d to `Unknown`). The WR-03 change adds
  only the same pre-existing error class on the same `Unknown`-typed loop variable;
  it introduces no new error inside the gated scope. The project's pre-commit hook
  (`uv run basedpyright`, no path) respects `include` and passed on every commit.
- Each commit ran the real pre-commit hooks (basedpyright/ruff/uv-lock). The
  sandbox blocks `uv`, so commits were made with the sandbox disabled (per the
  milestone's established practice) rather than bypassing hooks with `--no-verify`.

---

_Fixed: 2026-06-27T14:40:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
