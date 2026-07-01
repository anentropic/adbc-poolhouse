---
phase: 25-cancellation
plan: 05
subsystem: docs-and-guard-gate
tags: [cancellation, docs-gate, mkdocs, edge-28, trio-neutrality, loop-stability]

# Dependency graph
requires:
  - phase: 25-cancellation
    plan: 01
    provides: "banned-asyncio-cancelled-error AST rule in scan_async_package (EDGE-28)"
  - phase: 25-cancellation
    plan: 02
    provides: "cancellable_offload + AsyncConnection.invalidate + rewired cursor methods; async-guide cancellation section (placeholder already replaced)"
  - phase: 25-cancellation
    plan: 03
    provides: "EDGE-01..07 + EDGE-29 backend-parity suite under tests/async"
  - phase: 25-cancellation
    plan: 04
    provides: "EDGE-19 bare-AdbcError unwrap + EDGE-09 cancel-mid-block token leg"
provides:
  - "async guide cooperative-cancellation/timeout section (Example admonition, move_on_after/scope.cancel parity, invalidate cross-link) passing mkdocs --strict"
  - "tests/async/test_async_guard.py — async-side EDGE-28 meta-assert scan_async_package('src/adbc_poolhouse/_async/') == []"
  - "phase-wide x20 loop gate proof (tests/async, 0 fails / 0 hangs, both backends)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Singular Example admonition (!!! example) wrapping a fenced python block in a how-to guide"
    - "Method-level cross-link via inline code + reference-index link (not a fragile method autoref that fails --strict)"
    - "Thin async-suite meta-assert mirroring the top-level guard self-tests, placed under tests/async/ to match the VALIDATION.md per-task command"

key-files:
  created:
    - tests/async/test_async_guard.py
  modified:
    - docs/src/guides/async.md

key-decisions:
  - "AsyncConnection.invalidate cross-linked via inline code + a reference-index link rather than a method-level mkdocstrings autoref, because method-level autorefs fail mkdocs --strict (Phase 24 note); the in-prose link targets the See also anchor"
  - "No importlib dance in tests/async/test_async_guard.py — tests/async/__init__.py already makes from tests._async_harness.guard import scan_async_package resolve, matching every other tests/async/ file"
  - "Task 1 was largely satisfied by 25-02 (the placeholder was already replaced); this plan refined that section to the full acceptance criteria (Example admonition, explicit move_on_after/scope.cancel parity, See also cross-link) rather than rewriting from a placeholder"

requirements-completed: [EDGE-28]

# Metrics
duration: 9min
completed: 2026-06-28
---

# Phase 25 Plan 05: Docs Gate + EDGE-28 Meta-Assert + Phase Loop Gate Summary

**The phase completion gate: the async guide now documents cooperative cancellation/timeout end to end (fail_after/move_on_after, joined-worker adbc_cancel abort, invalidate-on-cancel keeping `pool.checkedout()` correct, asyncio/trio parity) with a strict-passing `AsyncConnection.invalidate` cross-link; a new async-side EDGE-28 meta-assert proves the live `_async/` package scans clean including the `banned-asyncio-cancelled-error` rule; and the phase-wide x20 loop over `tests/async` is clean (0 failures, 0 hangs) under both backends.**

## Performance

- **Duration:** ~9 min
- **Completed:** 2026-06-28
- **Tasks:** 2 completed
- **Files:** 1 created, 1 modified

## Accomplishments

- `docs/src/guides/async.md` — refined the "Cancelling an in-flight query" section (the placeholder had already been replaced in 25-02): wrapped the `fail_after` snippet in a singular `!!! example` admonition; made the `move_on_after` / explicit `scope.cancel()` parity explicit ("only the surfaced exception type differs, and that difference comes from anyio's scope, not from anything the pool does"); spelled out the joined-worker `adbc_cancel` abort and the invalidate drop keeping `pool.checkedout()` correct; cross-linked `AsyncConnection.invalidate` in the **See also** block. Humanizer pass applied (no promotional vocabulary, no AI-tells, em-dashes within budget). `.venv/bin/mkdocs build --strict` exits 0; no RST roles in the new prose.
- `tests/async/test_async_guard.py` (NEW) — the async-suite EDGE-28 / CANCEL-04 meta-assert the VALIDATION.md per-task map references (`tests/async/test_async_guard.py -q`): `TestRealAsyncPackageClean.test_scan_async_package_is_empty` asserts `scan_async_package("src/adbc_poolhouse/_async/") == []`, proving the live package has no `import asyncio`, no bare `asyncio.CancelledError` (the new rule), and no un-limitered `to_thread.run_sync` after the 25-02 rewire. Static `ast.parse` scan, no event loop, no `@pytest.mark.anyio`.
- Phase loop gate run: x20 over `tests/async`, both backends — 64 passed per run, 0 failures, 0 hangs; `PHASE25_LOOP20_CLEAN` emitted.

## Task Commits

1. **Task 1: refine async-guide cancellation section + invalidate cross-link** — `6186c21` (docs)
2. **Task 2: EDGE-28 async-side meta-assert** — `d16de0b` (test)

## Files Created/Modified

- `tests/async/test_async_guard.py` (NEW) — single-class, single-test async-side meta-assert; direct `from tests._async_harness.guard import scan_async_package` (no importlib dance needed).
- `docs/src/guides/async.md` — Example admonition, parity prose, invalidate cross-link in See also.

## Deviations from Plan

### Plan-vs-reality reconciliation (no auto-fixes required)

- **Task 1 scope already partly done by 25-02.** The plan's Task 1 action says "replace the placeholder paragraph". 25-02 had already replaced it with a working cancellation section. This plan refined that section to the full Task-1 acceptance criteria (Example admonition, explicit `move_on_after`/`scope.cancel` parity, See also cross-link) instead of replacing a placeholder. The objective itself anticipated this ("the async-guide section already partly written"). Not a code deviation — the end state matches every Task-1 acceptance criterion.
- **No importlib dance.** The plan said to use "the same `importlib` dance the other `tests/async/` files use if needed for the reserved-keyword dir". It is not needed: `tests/async/__init__.py` exists, so a plain `from tests._async_harness.guard import scan_async_package` resolves (every other `tests/async/` file imports the harness this way). The thin meta-assert uses the direct import.
- **invalidate cross-link style.** Per the Phase 24 note that method-level mkdocstrings autorefs fail `--strict`, `AsyncConnection.invalidate` is cross-linked with inline code + a reference-index link (the See also bullet) rather than a `[...][adbc_poolhouse.AsyncConnection.invalidate]` autoref. The in-prose mention links to the See also anchor. `mkdocs build --strict` passes.

## Authentication Gates

None.

## Environment Note

The Task 2 commit included a Python file, so the `basedpyright` pre-commit hook ran and panicked under the command sandbox (the known `uv` / system-configuration NULL-object crash, MEMORY "uv sandbox workarounds"). The commit was re-run with the sandbox disabled; all hooks then passed (ruff, ruff-format, basedpyright, blacken-docs, detect-secrets). No `--no-verify` was used. The Task 1 commit touched only Markdown, so basedpyright was skipped and it committed inside the sandbox without issue.

## Verification

- `.venv/bin/mkdocs build --strict` → exit 0, `DOCS_STRICT_PASS`; no RST roles in the new async.md prose (`grep -nE ':(func|class|meth|mod|attr):'` clean).
- `.venv/bin/pytest tests/async/test_async_guard.py -q` → 1 passed, `GUARD_META_PASS`.
- `.venv/bin/ruff check` / `format --check` on the new test → clean; `.venv/bin/basedpyright src/adbc_poolhouse/_async/` → 0 errors, 0 warnings, 0 notes.
- Full suite `.venv/bin/pytest -q` → 388 passed, 2 skipped (sync + harness + async, both backends).
- **Phase x20 loop** over `tests/async` (MEMORY loop-flaky-concurrency lesson; `rc=$?` + per-run `grep -q passed`, never `if ! pytest` — zsh `!` gotcha): 20/20 runs, 64 passed each, 0 failures, 0 hangs → `PHASE25_LOOP20_CLEAN`.

## Known Stubs

None.

## Threat Flags

None. This plan is docs + a static read-only meta-assert + the loop gate; no new network endpoint, auth path, file-access pattern, or trust-boundary schema change. Both register entries (T-25-05-TMP trio-neutrality scan, T-25-05-DOS loop gate) are mitigated exactly as the threat model specified.

## Self-Check: PASSED

- Files exist: `tests/async/test_async_guard.py`, `docs/src/guides/async.md` — both FOUND.
- Commits exist: `6186c21`, `d16de0b` — both FOUND in `git log`.
