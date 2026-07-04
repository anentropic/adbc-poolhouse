---
phase: 35-async-prepared-statements
plan: 02
subsystem: async-cursor
tags: [async, pyarrow, adbc, prepared-statements, offload, cancel, tdd, green]

# Dependency graph
requires:
  - phase: 35-async-prepared-statements
    plan: 01
    provides: "Five RED tests/async/test_prep_*.py + BlockingStubCursor.adbc_prepare/adbc_execute_schema counters — the fixed GREEN target"
  - phase: 34-async-metadata
    provides: "cancellable/non-cancellable offload precedent + non-poisoning cancel assertion pattern (invalidate==0)"
provides:
  - "AsyncCursor.adbc_prepare(operation) -> pyarrow.Schema | None — offload wrapper, cancellable but non-poisoning"
  - "AsyncCursor.adbc_execute_schema(operation, parameters=None) -> pyarrow.Schema — result schema WITHOUT executing"
  - "_SyncCursor Protocol adbc_prepare/adbc_execute_schema signatures (-> object, driver-agnostic)"
affects: [35-03 (docs — the two symbols auto-render via the existing AsyncCursor mkdocstrings block)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cancellable-but-non-poisoning offload: clone execute through cancellable_offload with on_abort OMITTED (D-35-04) — fires adbc_cancel once, no invalidate"
    - "Driver-agnostic Protocol + cast: Protocol method typed -> object, public method casts to pyarrow.Schema | None / pyarrow.Schema (copied from fetch_df)"

key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_async/_cursor.py
    - tests/async/test_prep_roundtrip.py
    - tests/async/test_prep_no_execute.py
    - tests/async/test_prep_unsupported.py
    - tests/async/test_prep_cancel.py
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Both methods forward args POSITIONALLY (no functools.partial) — they mirror execute, not the keyword-only adbc_ingest (D-35-02/03)"
  - "on_abort OMITTED on both — a prepare/execute_schema writes no state, so a cancelled call returns a clean connection with NO invalidate (D-35-04, LOCKED)"
  - "Tasks 1 and 2 share one implementation commit: test_prep_signature.py asserts BOTH symbols exist and the whole-project basedpyright-strict hook requires both present, so the two methods form one indivisible GREEN unit"

requirements-completed: [PREP-01, PREP-02]

# Metrics
duration: 4min
completed: 2026-07-04
---

# Phase 35 Plan 02: Async Prepared-Statement GREEN Implementation Summary

**Added `AsyncCursor.adbc_prepare` and `adbc_execute_schema` as near-exact clones of `AsyncCursor.execute` through the single `cancellable_offload` chokepoint with `on_abort` omitted (cancellable but non-poisoning, D-35-04), plus the two `_SyncCursor` Protocol signatures — turning all five Wave-1 RED tests GREEN on asyncio and trio.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-07-04T20:11:43Z
- **Completed:** 2026-07-04T20:16:06Z
- **Tasks:** 2 (implementation) + green-wave pragma cleanup
- **Files modified:** 6 (1 source, 4 tests, 1 requirements)

## Accomplishments
- Extended the `_SyncCursor` structural Protocol with `adbc_prepare(operation, /) -> object` and `adbc_execute_schema(operation, parameters=..., /) -> object`, keeping the async layer driver-agnostic and stub-testable (D-35-05).
- Implemented `AsyncCursor.adbc_prepare(operation) -> pyarrow.Schema | None`: a single whole-operation offload that prepares the query without executing it and returns the bind-parameter schema (or `None`), casting off the `-> object` Protocol return.
- Implemented `AsyncCursor.adbc_execute_schema(operation, parameters=None) -> pyarrow.Schema`: returns the result-set schema WITHOUT executing the query, forwarding `(operation, parameters)` positionally exactly as `execute` does.
- Both clone `execute` with `on_abort` OMITTED — cancellable (a surrounding cancel/timeout fires `adbc_cancel` once) but non-poisoning (no `invalidate`; the clean connection returns to the pool). No `functools.partial`, no `find_spec`, no try/except (D-35-02/03/04/06).
- Native driver errors surface unchanged through the offload chokepoint (DuckDB `NotSupportedError` for `adbc_execute_schema`, EDGE-17).
- Google-style Markdown docstrings (Args/Returns/Raises + singular `Example:`) on both public methods, documenting the no-execute contract, the cancellable-but-non-poisoning cancel semantics, and the native-error passthrough.
- Removed the four Wave-1 RED pyright suppression pragma blocks now that the referenced symbols exist; whole-project basedpyright strict stays at 0 errors without them.
- Marked PREP-01 and PREP-02 Complete (35-02) in REQUIREMENTS.md, mirroring how META was marked at 34-02 (not the RED scaffold).

## Task Commits

1. **Tasks 1 + 2: Protocol signatures + both AsyncCursor methods** — `b0df77a` (feat)
2. **Green-wave cleanup: remove RED pyright pragmas from the four test files** — `d3dd2b7` (test)
3. **Plan metadata (SUMMARY + STATE + ROADMAP + REQUIREMENTS):** this commit (docs)

## Files Created/Modified
- `src/adbc_poolhouse/_async/_cursor.py` — Added two `_SyncCursor` Protocol signatures and the two public `AsyncCursor` methods (125 insertions).
- `tests/async/test_prep_{roundtrip,no_execute,unsupported,cancel}.py` — Deleted the Wave-1 file-level `# pyright: report*=false` pragma blocks (31 deletions).
- `.planning/REQUIREMENTS.md` — PREP-01/PREP-02 checkboxes ticked and traceability rows set to `Complete (35-02)`.

## Decisions Made
- **Tasks 1 and 2 landed in a single implementation commit.** `test_prep_signature.py` asserts BOTH `adbc_prepare` and `adbc_execute_schema` exist on `AsyncCursor`, and the whole-project basedpyright-strict pre-commit hook requires both methods present to typecheck the reference sites. The two methods are therefore an indivisible GREEN unit — the plan's own Task 1 behavior bullet states both `hasattr` checks must be True after Task 1. Splitting into two source commits would leave the first commit unable to pass its own gates. The pragma cleanup is the genuinely separable second commit.
- **Both methods omit `on_abort`.** This is the load-bearing D-35-04 (LOCKED) point and the exact CR-34-01 hazard avoided: adding `on_abort=self._owner.invalidate` would drop a never-poisoned connection. Proven by `test_prep_cancel.py` (`adbc_cancel_call_count == 1`, `invalidate_call_count == 0`).
- **No sync-side counterpart added.** The sync surface is a pool factory (`create_pool` → raw `QueuePool`); sync users call the native ADBC cursor methods directly (D-35-07).

## Deviations from Plan
None — plan executed exactly as written. The two-methods-in-one-commit structure is not a scope deviation; it is the coupling the plan itself describes (Task 1 behavior: both `hasattr` True), recorded above as a decision.

## Authentication Gates
None.

## Verification Results
- `.venv/bin/pytest tests/async/test_prep_signature.py test_prep_roundtrip.py test_prep_no_execute.py test_prep_unsupported.py -q` → 8 passed (asyncio + trio).
- `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_prep_cancel.py -q` → 80 passed, 0 hangs.
- `.venv/bin/pytest tests/async -q` → 247 passed, 4 skipped (existing suite green, no regression).
- `.venv/bin/basedpyright` (whole project, strict) → 0 errors, 0 warnings, 0 notes.
- `.venv/bin/pytest tests/async/test_async_guard.py test_meta_guard.py -q` → 3 passed (import-lint chokepoint clean).
- `.venv/bin/ruff check` on the four cleaned test files → all checks passed.

## Issues Encountered
- The basedpyright pre-commit hook panicked under the command sandbox (macOS `system-configuration` `dynamic_store.rs` NULL-object panic) on both commits — a known MEMORY gotcha. The direct `.venv/bin/basedpyright` whole-project run reports 0 errors; both commits were re-run with the sandbox disabled so the hook's system call succeeds. Not a code defect.

## Known Stubs
None. Both public methods are fully wired to the underlying sync ADBC cursor via the offload chokepoint; no placeholder data, no empty return.

## Threat Flags
None. No new network endpoint, auth path, file access, or schema surface beyond the plan's `<threat_model>`. T-35-02 (connection-busy/poisoned after a cancelled or unsupported call) is the mitigate disposition, satisfied by the omitted `on_abort`: `test_prep_cancel.py` (`invalidate_call_count == 0`, no hang) and `test_prep_unsupported.py` (`checkedout() == 0` after the native error).

## Docs Quality Gate (CLAUDE.md, phases >= 7)
Both new public methods carry Google-style Markdown docstrings (Args/Returns/Raises + singular `Example:` fenced ```python block), no RST `:role:` syntax. The consumer-facing guide/index caveat removal + `mkdocs build --strict` + humanizer pass are plan 35-03 (PREP-03); the phase docs completion gate is evaluated at phase close. The two symbols auto-render through the existing `AsyncCursor` mkdocstrings block (no nav edit needed).

## Self-Check: PASSED

- `src/adbc_poolhouse/_async/_cursor.py` contains `async def adbc_prepare` and `async def adbc_execute_schema` — confirmed.
- Commits `b0df77a` and `d3dd2b7` present in git log — confirmed.
- All five prep test files pass under both backends; whole-project basedpyright strict 0 errors — confirmed.

---
*Phase: 35-async-prepared-statements*
*Completed: 2026-07-04*
