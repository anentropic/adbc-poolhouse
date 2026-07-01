---
phase: 27-dual-backend-test-matrix
plan: 03
subsystem: testing
tags: [anyio, pyarrow, allocator, sqlalchemy-event, duckdb, stability, async]

# Dependency graph
requires:
  - phase: 27-dual-backend-test-matrix
    plan: 01
    provides: "the duckdb_async_pool real-driver fixture and the anyio_backend dual-backend axis fixture this stability test runs against"
  - phase: 24-core-async-wrapper
    provides: "the frozen AsyncPool / AsyncConnection surface (connect -> cursor -> execute -> fetch_arrow_table) and the _release_arrow_allocators reset path observed here"
provides:
  - "TEST-03: a deterministic Arrow allocator-stability proof (zero total_allocated_bytes delta over N>=100 cursor lifecycles, no RSS) plus a once-per-checkin reset-event-count assertion, x{asyncio, trio}"
affects: [27-meta-test, dual-backend-test-matrix]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deterministic allocator-leak proof: gc.collect() baseline -> N>=100 (open/execute/fetch_arrow_table/del/checkin) cycles -> gc.collect() -> assert pyarrow.total_allocated_bytes() delta == 0 (no monotonic growth, NOT process RSS)"
    - "Observe the SQLAlchemy pool reset event via event.listen(pool._pool, 'reset', counter) to count the _release_arrow_allocators symmetric-cleanup path once per checkin WITHOUT touching frozen src/"

key-files:
  created:
    - tests/async/test_stability_arrow.py
  modified: []

key-decisions:
  - "Allocator delta asserted exact-zero (delta == 0), not just bounded — verified deterministic 20/20 this session; the documented fallback (delta < single_table_bytes, RESEARCH Pitfall 5) was not needed"
  - "Reset count gathered via a read-only SQLAlchemy event listener on pool._pool, never by patching _release_arrow_allocators or any src/ symbol (locked constraint)"
  - "Imported `from sqlalchemy import event` (the repo's own _pool_factory.py:27 form) instead of `import sqlalchemy` + `sqlalchemy.event` — the latter trips basedpyright reportAttributeAccessIssue against the installed stubs"

patterns-established:
  - "Stability test = real DuckDB pool + dual allocator/reset assertions under @pytest.mark.anyio; extends the TestEdge21ArrowLifetime loop from 5 to N=100"

requirements-completed: [TEST-03]

# Metrics
duration: ~5min
completed: 2026-06-28
---

# Phase 27 Plan 03: Arrow Allocator-Stability Test Summary

**A deterministic `tests/async/test_stability_arrow.py` (TEST-03) proving zero `pyarrow.total_allocated_bytes()` growth across N=100 async cursor lifecycles on the real DuckDB pool, plus a SQLAlchemy-listener assertion that the `_release_arrow_allocators` reset path fires exactly once per checkin — under both asyncio and trio, with no `src/` change.**

## Performance

- **Duration:** ~5 min
- **Completed:** 2026-06-28
- **Tasks:** 1
- **Files created:** 1

## Accomplishments
- `tests/async/test_stability_arrow.py` (97 lines, `TestStability03ArrowAllocator`): one `@pytest.mark.anyio` test taking `duckdb_async_pool` and `anyio_backend_name` (`del`'d, per the `test_edge_resource.py:57` convention), so it runs ×{asyncio, trio} (D-27-09).
- **Primary signal (D-27-07):** `gc.collect()` baseline → `_N = 100` cycles of `connect → cursor → execute → fetch_arrow_table → del tbl → checkin` → `gc.collect()` → `assert pyarrow.total_allocated_bytes() - baseline == 0`. No process RSS (rejected as non-deterministic). Verified exact-zero, deterministic, 20/20 loop runs.
- **Belt-and-braces (D-27-08 / ACONN-06):** `event.listen(duckdb_async_pool._pool, "reset", _on_reset)` counts the pool reset (the `_release_arrow_allocators` symmetric-cleanup path), then `assert reset_count == _N` — one reset per checkin, observed read-only without touching frozen `src/`.
- Per-cycle `assert duckdb_async_pool._pool.checkedout() == 0` confirms each connection returned to the pool.

## Task Commits

1. **Task 1: Arrow allocator-stability + reset-count test** - `64ff72d` (test)

## Files Created/Modified
- `tests/async/test_stability_arrow.py` (created) - The TEST-03 stability proof: module docstring, `_N = 100`, dual allocator-delta + reset-count assertions under `@pytest.mark.anyio`.

## Decisions Made
- **Exact-zero allocator delta** (`delta == 0`), not merely bounded: verified deterministic across the 20× loop, so the documented `delta < single_table_bytes` fallback (RESEARCH Pitfall 5) was unnecessary.
- **Reset count via read-only listener:** `event.listen(pool._pool, "reset", ...)` observes the symmetric-cleanup path; it does not patch `_release_arrow_allocators` or any `src/` symbol (locked constraint held).
- **Import form `from sqlalchemy import event`:** matches the repo's own `_pool_factory.py:27` usage and satisfies `.venv/bin/basedpyright` (the PATTERNS snippet's `import sqlalchemy` + `sqlalchemy.event.listen` trips `reportAttributeAccessIssue` against the installed stubs). The plan's `event\.listen` key-link pattern is still satisfied.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] SQLAlchemy event import form**
- **Found during:** Task 1 typecheck (`.venv/bin/basedpyright`)
- **Issue:** The PATTERNS.md snippet used `import sqlalchemy` + `sqlalchemy.event.listen(...)`, which basedpyright flags as `reportAttributeAccessIssue` ("event" is not a known attribute of module "sqlalchemy") and `reportUnknownMemberType` against the installed type stubs — a blocking typecheck failure for the pre-commit gate.
- **Fix:** Switched to `from sqlalchemy import event` and `event.listen(...)`, the exact form the production code uses at `src/adbc_poolhouse/_pool_factory.py:27`. Behaviour identical; the `event\.listen` key-link pattern still matches.
- **Files modified:** `tests/async/test_stability_arrow.py`
- **Commit:** `64ff72d`

## Verification
- `.venv/bin/pytest tests/async/test_stability_arrow.py -x -q` → `2 passed` (asyncio + trio legs).
- **20× loop-stability gate** (project rule for async tests, MEMORY): `rc=$?` + `grep "2 passed"` (zsh `!` landmine avoided) → `pass=20 fail=0`, 0 hangs.
- `.venv/bin/basedpyright tests/async/test_stability_arrow.py` → 0 errors.
- Hygiene: no `import asyncio`, no `@pytest.mark.asyncio`, `@pytest.mark.anyio` present. Both Plan 01 guards stay clean over `tests/async`: `scan_async_test_hygiene == []`, `scan_for_positive_sleep == []`.
- Key-link patterns present: `event.listen` and `total_allocated_bytes`.
- `git diff --stat src/` empty (frozen-surface constraint held). No file deletions in the commit.
- `.venv/bin/mkdocs build --strict` passes (docs gate, CLAUDE.md phases ≥ 7); this test adds no consumer-facing docs surface.

## Issues Encountered
- **uv pre-commit hooks panic under the command sandbox.** The first `git commit` aborted with the documented uv tokio/`system-configuration` NULL-object panic from the `uv run basedpyright` hook (not a real type failure — `.venv/bin/basedpyright` is clean). Re-ran the exact `git commit` with the sandbox disabled (per the executor instructions / project MEMORY); all hooks (ruff, ruff-format, basedpyright, blacken-docs, detect-secrets) then passed. No `--no-verify`.

## Known Stubs
None — the test is a complete, passing proof wired to the real DuckDB pool.

## User Setup Required
None — pure in-process DuckDB test, no credentials, no external services.

## Next Phase Readiness
- TEST-03 is satisfied: the highest async-DB-wrapper failure mode (silent Arrow-allocator leak) now has a deterministic, dual-backend regression test.
- The new file is hygiene-clean, so the Wave 3 meta-guard test (`scan_async_test_hygiene("tests/async") == []`) stays green when it lands.
- No `src/` modification; the frozen async surface is intact.

## Self-Check: PASSED

- `tests/async/test_stability_arrow.py` exists on disk (97 lines).
- `27-03-SUMMARY.md` exists on disk.
- Task commit `64ff72d` is present in the git log.
- `git diff --stat src/` empty (frozen-surface constraint held).
- Pre-existing unrelated working-tree changes (`.planning/config.json`, `24-CONTEXT.md`, deleted `.planning/.continue-here.md`) left untouched.

---
*Phase: 27-dual-backend-test-matrix*
*Completed: 2026-06-28*
