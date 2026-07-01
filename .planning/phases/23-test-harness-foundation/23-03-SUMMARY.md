---
phase: 23-test-harness-foundation
plan: 03
subsystem: testing
tags: [ast, import-lint, guard, async, anyio, stdlib]

# Dependency graph
requires:
  - phase: 23-01
    provides: tests/_async_harness/ package scaffold (the home for guard.py)
provides:
  - "scan_async_package(root) -> list[Finding] — the D-05 AST import-lint callable (HARD CONTRACT for Phases 24/25/27 meta-guards EDGE-25/27/28)"
  - "Finding frozen dataclass (path, lineno, rule, message)"
  - "Two rules: banned-asyncio-import, to_thread-without-limiter"
  - "Synthetic-source self-test suite proving both rules + no-op + alias-limitation"
affects: [24-async-core, 25-async-pool, 27-async-edge, EDGE-25, EDGE-27, EDGE-28]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-stdlib ast.NodeVisitor source-scan returning a findings list (no import-linter/ruff)"
    - "Graceful absent-path no-op (returns []) so the guard stays green before the scanned package exists"
    - "Synthetic-source self-testing via tmp_path (never scans the real, absent _async/)"

key-files:
  created:
    - tests/_async_harness/guard.py
    - tests/test_async_guard.py
  modified: []

key-decisions:
  - "D-05 realized as a callable returning list[Finding] (not import-linter/ruff config) — matches the EDGE meta-guard contract shape (assert findings == [])"
  - "Attribute-chain-tail matching catches anyio.to_thread.run_sync(...) and to_thread.run_sync(...); a fully-aliased run_sync re-import is an ACCEPTED, test-locked limitation, not a bug"
  - "import asyncio ban is a literal name/prefix check (no alias tracking) per CORE-03"

patterns-established:
  - "AST guard: frozen Finding + _GuardVisitor(visit_Import/visit_ImportFrom/visit_Call) + public scan_async_package entry point"
  - "Path-exists-then-act no-op idiom (mirrors tests/integration/conftest.py) for scanning a not-yet-created package"

metrics:
  duration: ~25m
  completed: 2026-06-27
  tasks: 2
  files: 2
---

# Phase 23 Plan 03: Async Import-Lint Guard (D-05) Summary

A pure-stdlib `ast.NodeVisitor` guard, `scan_async_package(root) -> list[Finding]`, that bans `import asyncio` / `from asyncio import …` and bare `to_thread.run_sync(...)` calls lacking an explicit `limiter=`, scoped to a configurable path and no-opping gracefully when that path is absent. Shipped with sync self-tests against synthetic source strings.

## What Was Built

- **`tests/_async_harness/guard.py`** — the guard module:
  - `Finding` frozen dataclass: `path`, `lineno`, `rule`, `message`.
  - `_GuardVisitor(ast.NodeVisitor)`: `visit_Import` / `visit_ImportFrom` flag the `asyncio` ban; `visit_Call` flags `to_thread.run_sync(...)` without a `limiter=` keyword. `_is_to_thread_run_sync` matches the attribute-chain tail so both `anyio.to_thread.run_sync` and `to_thread.run_sync` are caught.
  - `scan_async_package(root: str | Path) -> list[Finding]`: returns `[]` when `root` is absent (D-05 no-op), else `ast.parse`s each `*.py` under `root.rglob` and aggregates findings. Read-only — never imports/executes scanned source. Google-style docstring with Args/Returns/Note/Example; documents the accepted alias-limitation.
- **`tests/test_async_guard.py`** — plain sync self-tests (no `@pytest.mark.anyio`) under `class TestAsyncGuard`, feeding synthetic `.py` files into `tmp_path`: asyncio-import ban, to_thread-without-limiter flag, compliant-`limiter=` clean, absent-dir no-op, empty-dir no-op, and the alias-limitation locked as a known gap.

## Verification

- `tests/_async_harness/guard.py` AST-structure check: `scan_async_package`, `Finding`, `_GuardVisitor` all defined; pure stdlib (only `ast`, `dataclasses`, `pathlib`).
- `.venv/bin/basedpyright tests/_async_harness/guard.py` and `tests/test_async_guard.py`: 0 errors, 0 warnings (strict).
- `.venv/bin/pytest tests/test_async_guard.py -q`: 5 passed. Full harness run: 15 passed.
- `.venv/bin/mkdocs build --strict`: builds clean.

## Deviations from Plan

### Process deviations (no functional impact)

**1. TDD RED gate not committed in isolation**
- **Found during:** Task 1 (tdd="true").
- **Issue:** The RED test (`tests/test_async_guard.py` referencing the not-yet-existent `guard.py`) cannot be committed on its own because the repo's pre-commit gate runs basedpyright in strict mode, which hard-fails on the unresolved import (`reportMissingImports` + cascading `Unknown` types). A failing-import test file is, by construction, un-type-checkable until the implementation exists.
- **Resolution:** RED was demonstrated at runtime (pytest failed at collection with `ModuleNotFoundError`), then the guard was implemented (GREEN) and the two files committed as separate atomic commits: `feat` (guard) then `test` (self-tests). The strict-type gate effectively forces implementation-before-commit for type-coupled test files. Documented under TDD Gate Compliance below.

**2. Atomic-commit re-split**
- **Issue:** During a hook-aborted commit cycle, the staged test file was inadvertently bundled into the first guard commit.
- **Resolution:** `git reset --soft HEAD~1` and re-committed as two atomic commits (`492f176` guard, `5becafd` tests). No content change.

### None functional — plan executed as written otherwise.

## TDD Gate Compliance

- **RED:** Demonstrated at runtime — `tests/test_async_guard.py` failed collection with `ModuleNotFoundError: No module named 'tests._async_harness.guard'` before any implementation. Not committed in isolation because basedpyright-strict (a hard pre-commit gate) rejects the unresolved import; see Deviation 1.
- **GREEN:** `feat(23-03)` commit `492f176` — guard implemented, all 5 tests pass.
- **TEST commit:** `test(23-03)` commit `5becafd` — self-tests landed after GREEN (commit ordering reflects the strict-type constraint, not a skipped RED).
- **REFACTOR:** None needed.

> Note: the canonical RED-then-GREEN commit order is inverted here (feat before test) solely because of the strict-typing pre-commit gate on an import-coupled test file. The RED state was verified before implementation; behaviour was test-driven.

## Security Notes (threat model)

- **T-23-06 (mitigate):** `scan_async_package` reads source only — `ast.parse`, never `exec`/`import`. The docstring documents that `root` should point at the in-repo async package and that no untrusted/remote path should be passed. Mitigation applied.
- **T-23-07 (accept):** a malformed `.py` raising `SyntaxError` surfaces as a test failure — the desired signal — as accepted in the plan.

## Sandbox / Hook Notes

Pre-commit hooks are `uv`-backed; under the command sandbox basedpyright panics (`system-configuration` NULL-object panic / Tokio executor failure — the known issue per MEMORY uv-sandbox-workarounds). Commits were made with the sandbox disabled so the real hooks (ruff, ruff-format, basedpyright-strict, detect-secrets) ran and passed. ruff auto-reformatted `guard.py` docstrings (multi-line summary style) on first pass; the reformatted, hook-approved version is what landed.

## Known Stubs

None. The guard is fully wired; the absent-`_async/` no-op is intentional (the package arrives in Phase 24) and locked by `test_noop_absent_dir`.

## Self-Check: PASSED

- FOUND: tests/_async_harness/guard.py
- FOUND: tests/test_async_guard.py
- FOUND: .planning/phases/23-test-harness-foundation/23-03-SUMMARY.md
- FOUND: commit 492f176 (feat — guard)
- FOUND: commit 5becafd (test — self-tests)
