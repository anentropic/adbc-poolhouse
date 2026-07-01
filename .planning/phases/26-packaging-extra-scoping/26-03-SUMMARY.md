---
phase: 26-packaging-extra-scoping
plan: 03
subsystem: testing
tags: [pep562, import-guard, anyio, subprocess, metapathfinder, packaging]

# Dependency graph
requires:
  - phase: 24-core-async-wrapper
    provides: the PEP 562 __getattr__ lazy-import guard in src/adbc_poolhouse/__init__.py
  - phase: 25-cancellation
    provides: the shipped _LAZY_ASYNC_NAMES + ImportError naming the [async] extra
provides:
  - subprocess-isolated regression test locking in the zero-cost sync import (PKG-02)
  - subprocess-isolated regression test locking in the [async]-naming ImportError on async access (PKG-03)
affects: [26-04-no-anyio-ci, 27-test-matrix, future-refactors-of-__getattr__]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Subprocess + importlib.abc.MetaPathFinder anyio-block to test optional-dependency guards without uninstalling anyio"
    - "Per-branch sentinel prints (SYNC_IMPORT_OK / ASYNC_GUARD_OK) so each test proves its own branch executed in the child"

key-files:
  created:
    - tests/test_pkg_import_guard.py
  modified: []

key-decisions:
  - "Verify-not-rebuild (D-01): src/adbc_poolhouse/__init__.py left byte-for-byte unchanged; the test pins the already-shipped guard"
  - "Two test functions share one meta-path-block child script; each asserts its own sentinel (SYNC_IMPORT_OK for PKG-02, ASYNC_GUARD_OK for PKG-03)"
  - "Subprocess (not in-process monkeypatch) is mandatory — sys.modules caching of anyio/_async would mask the negative branch (RESEARCH Pitfall 2)"

patterns-established:
  - "Subprocess-isolated import-guard regression: child interpreter installs a MetaPathFinder raising ImportError for anyio*, then exercises the guard with a clean module table"
  - "anyio-free-at-collection test modules (only subprocess/sys/textwrap; no @pytest.mark.anyio) so they collect under the no-anyio CI job (Plan 04)"

requirements-completed: [PKG-02, PKG-03]

# Metrics
duration: ~6min
completed: 2026-06-28
---

# Phase 26 Plan 03: Import-Guard Regression Summary

**Subprocess-isolated regression (MetaPathFinder anyio-block) pinning the PEP 562 guard: `import adbc_poolhouse` stays anyio-free (PKG-02) and async-symbol access raises an `ImportError` naming the `[async]` extra (PKG-03).**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-28T08:39:44Z (approx, session continuation)
- **Completed:** 2026-06-28
- **Tasks:** 1
- **Files modified:** 1 (created)

## Accomplishments
- New `tests/test_pkg_import_guard.py` with two anyio-free tests sharing one meta-path-block child interpreter.
- `test_sync_import_without_anyio` (PKG-02): with anyio blocked, `import adbc_poolhouse` succeeds and `create_pool` is present.
- `test_async_access_without_anyio_raises` (PKG-03): accessing `create_async_pool` anyio-absent raises an `ImportError` whose message contains `[async]`.
- A fresh subprocess guarantees a clean `sys.modules`, so the guard's `except ImportError` negative branch genuinely fires (proven by per-branch sentinels).
- The already-shipped guard in `src/adbc_poolhouse/__init__.py` was left untouched (D-01 verify-not-rebuild).

## Task Commits

Each task was committed atomically:

1. **Task 1: Subprocess + meta-path-block import-guard regression** - `369394a` (test)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `tests/test_pkg_import_guard.py` - Two subprocess-isolated tests; a `_Blocker` `MetaPathFinder` raises `ImportError` for `anyio*` in a child `python -c` process, which then asserts sync import works (PKG-02) and async access raises `ImportError` naming `[async]` (PKG-03), each via its own stdout sentinel.

## Decisions Made
- **D-01 honored:** the `__getattr__` guard and `_LAZY_ASYNC_NAMES` in `__init__.py` are untouched; this plan only adds a regression that proves them.
- **One child, two tests:** the child script prints `SYNC_IMPORT_OK` after the sync-import assertion and `ASYNC_GUARD_OK` after the async-access assertion; each test runs the child and asserts its own sentinel. This keeps a single source of truth for the anyio-block setup while giving PKG-02 and PKG-03 independent, separately-named test functions (RESEARCH Test Map).
- **Subprocess over monkeypatch:** an in-process `sys.meta_path` patch would be defeated by `sys.modules` already caching `anyio`/`adbc_poolhouse._async` from an earlier test in the worker (Pitfall 2). A child interpreter is the only reliable isolation.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The basedpyright pre-commit hook panicked under the command sandbox (`system-configuration` NULL-object panic from a blocked macOS network probe) — the documented `uv`/basedpyright sandbox gotcha. Re-ran the commit with the sandbox disabled (no `--no-verify`); all hooks, including basedpyright, then passed. No code change involved.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PKG-02 and PKG-03 are pinned by passing, anyio-free, subprocess-isolated tests — a permanent regression against future `__getattr__` / `_LAZY_ASYNC_NAMES` refactors.
- The module is anyio-free at collection time, so it is ready to collect under Plan 04's `sync-no-anyio` CI job (`--ignore=tests/async` does not exclude it; it has no anyio import at module scope).
- Remaining in phase: Plan 04 (PKG-04 no-anyio CI job).

## Self-Check: PASSED
- `tests/test_pkg_import_guard.py` — FOUND
- Commit `369394a` — FOUND (`git log` confirms)
- `.venv/bin/pytest tests/test_pkg_import_guard.py -q` — 2 passed
- `src/adbc_poolhouse/__init__.py` — unchanged in `369394a` (D-01 verified)

---
*Phase: 26-packaging-extra-scoping*
*Completed: 2026-06-28*
