---
phase: 30-async-bulk-write
plan: 02
subsystem: async
tags: [adbc, adbc_ingest, async, anyio, trio, pyarrow, duckdb, functools-partial, cancel, invalidate, bulk-write, green]

# Dependency graph
requires:
  - phase: 30-async-bulk-write
    plan: 01
    provides: "Four RED test files (round-trip, modes, cancel, signature) + BlockingStubCursor.adbc_ingest gate; the GREEN target"
  - phase: 29-arrow-streaming
    provides: "_SyncCursor Protocol extension precedent (fetch_record_batch line); cancel-harness discipline"
  - phase: 25-cancel-invalidate
    provides: "cancellable_offload + on_abort=invalidate poison-recovery contract, reused verbatim"
provides:
  - "AsyncCursor.adbc_ingest — the sole new async method for the phase: a fetch_arrow_table clone with functools.partial arg binding, -> int return, and a docs-gate docstring"
  - "_SyncCursor.adbc_ingest structural Protocol member (driver shape) + import functools + Literal/CapsuleType TYPE_CHECKING imports"
  - "Async guide 'Bulk-loading Arrow data' section with the replace-drops-table warning and the four-mode table"
affects: [30-async-bulk-write, 31-dataframe-fetch, 33-docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Keyword-only args through the positional-variadic (Unpack[_Ts]) offload chokepoint via functools.partial — the milestone-general answer, first landed here"
    - "Permanent object-fetch type suppression via targeted inline # type: ignore[index] (not file-level pragma) where _SyncCursor.fetchone/fetchall return object"

key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_async/_cursor.py
    - tests/async/test_ingest_roundtrip.py
    - tests/async/test_ingest_modes.py
    - tests/async/test_ingest_cancel.py
    - tests/async/test_ingest_signature.py
    - docs/src/guides/async.md
    - docs/src/index.md

key-decisions:
  - "Moved `import functools` from Task 1 into Task 2 (where partial() is first used) so the Task 1 commit stays strict-clean under the whole-project basedpyright pre-commit hook — an unused runtime import is a hard error under typeCheckingMode=strict"
  - "Replaced the four test files' file-level RED basedpyright pragma blocks with targeted inline `# type: ignore[index]` on the genuinely-permanent object-fetch indexing (row[0] / [r[0] for r in fetchall()]); the missing-method pragmas were deleted outright on GREEN"

patterns-established:
  - "adbc_ingest body: 1st arg self._adbc_cancel (distinct bound method, unaffected by the partial), 2nd arg functools.partial(self._cursor.adbc_ingest, table_name, data, mode=..., ...); no _reader_open, no try/except"

requirements-completed: [INGEST-01, INGEST-02, INGEST-03, INGEST-04]

# Metrics
duration: 6min
completed: 2026-07-01
---

# Phase 30 Plan 02: Async Bulk Write GREEN Implementation Summary

**`AsyncCursor.adbc_ingest` — a near-mechanical clone of `fetch_arrow_table` whose only deltas are a `functools.partial`-bound callable, a `-> int` return, and the docstring — turns all 20 Plan 30-01 RED cases GREEN, with cancel/invalidate parity holding 20/20 looped on asyncio + trio.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-01T21:08:37Z
- **Completed:** 2026-07-01T21:15:30Z
- **Tasks:** 3
- **Files modified:** 7 (1 production, 4 tests, 2 docs)

## Accomplishments

- Implemented `AsyncCursor.adbc_ingest` as an exact `fetch_arrow_table` clone (Pattern A/B/C/D): `with self._owner._offloading():` wrapping a single `cancellable_offload(self._adbc_cancel, functools.partial(self._cursor.adbc_ingest, table_name, data, mode=..., catalog_name=..., db_schema_name=..., temporary=...), limiter=self._limiter, on_abort=self._owner.invalidate)`. No `_reader_open` lock (whole-op offload), no `try/except`, no chokepoint widening. The `functools.partial` binding four keyword-only public args through the positional-variadic offload is the phase's sole net-new construct, and it is strict-clean, runtime-correct, and guard-clean.
- Extended the `_SyncCursor` structural Protocol with `adbc_ingest(...) -> int` (driver shape: `mode` positional-or-keyword, latter three keyword-only), and added `import functools` (runtime) plus `Literal`/`CapsuleType` under `TYPE_CHECKING`. `basedpyright` is 0 errors over the whole project.
- Deleted the four RED test files' basedpyright pragma blocks on GREEN and proved the tests pass: round-trip/modes/signature (14 passed, both backends) and cancel/invalidate 20/20 looped (0 hangs, both backends — INGEST-04 / T-30-01). Re-ran the import-lint guard with `functools` present (T-30-02 closed).
- Documented `adbc_ingest` in the async guide with a round-trip example, the four-mode table, the explicit `replace`-**drops**-the-table warning (D-30-05), the EXPERIMENTAL marker on the three routing keywords (D-30-11), and the connection-not-table cancel-recovery caveat (D-30-10); `mkdocs build --strict` exits 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: _SyncCursor.adbc_ingest Protocol member + typing imports** - `d11467e` (feat)
2. **Task 2: Implement AsyncCursor.adbc_ingest (offload clone + docstring)** - `2579273` (feat)
3. **Task 3: Cancel-parity loop + guard re-verify + docs quality gate** - `69aaf7c` (docs)

_TDD note: this is the GREEN half of the Phase 30 whole-plan RED/GREEN cycle. The `test(30-01)` RED commits (`8fc93e6`, `fc9a734`, `f975f5b`) landed the failing tests + stub; these `feat(30-02)` commits satisfy them. GREEN gate present; RED gate present in 30-01._

## Files Modified

- `src/adbc_poolhouse/_async/_cursor.py` — Added `import functools` (runtime); `Literal` (typing) + `CapsuleType` (typing_extensions) under `TYPE_CHECKING`; the `_SyncCursor.adbc_ingest` Protocol member (after `fetch_record_batch`); and the `AsyncCursor.adbc_ingest` method (after `fetch_arrow_table`) with a Google-style Markdown docstring.
- `tests/async/test_ingest_roundtrip.py`, `test_ingest_modes.py`, `test_ingest_cancel.py`, `test_ingest_signature.py` — Deleted the Wave-0 RED pragma blocks. In `test_ingest_roundtrip.py` and `test_ingest_modes.py`, replaced the permanent `object`-fetch suppression with targeted inline `# type: ignore[index]` on `row[0]` / `[r[0] for r in await cursor.fetchall()]` (the loose `_SyncCursor.fetchone`/`fetchall` typing, matching the Phase 29 precedent).
- `docs/src/guides/async.md` — Added the "Bulk-loading Arrow data" section (round-trip example, four-mode table, `replace`-drops warning, EXPERIMENTAL keywords, cancel-recovers-connection-not-table caveat); moved `adbc_ingest` from the "not available yet" list to "what you get today". blacken-docs normalized one comment's alignment.
- `docs/src/index.md` — Removed `adbc_ingest` from the async "not available yet" sentence.

## Decisions Made

- **`import functools` belongs to Task 2, not Task 1** (see Deviations, Rule 3): the project's basedpyright pre-commit hook runs `typeCheckingMode=strict` over `src`+`tests` with `pass_filenames: false`. An `import functools` added in Task 1 (before `partial()` is used in Task 2) is a hard `reportUnusedImport` error and would block the Task 1 commit. Task 1 lands only the Protocol member + the annotation-only `Literal`/`CapsuleType` imports (strict-clean); Task 2 adds `functools` alongside its first use.
- **Targeted inline ignores over file-level RED pragmas for the permanent object-fetch typing.** The 30-01 roundtrip pragma comment flagged `reportIndexIssue`/`reportGeneralTypeIssues` etc. as reflecting the deliberately-loose `_SyncCursor` `object` return typing (not RED scaffolding). On GREEN, the missing-method pragmas are deleted outright, and the genuinely-permanent `row[0]` indexing suppression is narrowed to inline `# type: ignore[index]` at the exact call sites — cleaner and honest to the delete-on-GREEN intent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `import functools` moved from Task 1 to Task 2 to keep each commit strict-clean**
- **Found during:** Task 1
- **Issue:** Task 1's acceptance criteria and `<action>` place `import functools` in the runtime block during Task 1. But `functools.partial` is not used until Task 2's method body, and the whole-project basedpyright pre-commit hook (`typeCheckingMode=strict`, `pass_filenames: false`) treats an unused import as a hard `reportUnusedImport` error — the Task 1 commit would be rejected by its own type-check gate.
- **Fix:** Task 1 added only the `_SyncCursor.adbc_ingest` Protocol member and the annotation-only `Literal`/`CapsuleType` `TYPE_CHECKING` imports (strict-clean, 0 errors). Task 2 added `import functools` in the same edit that introduces `functools.partial(...)`, so every commit is strict-clean. The end state after Task 2 is identical to what the plan specifies (functools is a runtime import; grep-verifiable).
- **Files modified:** src/adbc_poolhouse/_async/_cursor.py
- **Verification:** `basedpyright src tests` = 0 errors after both Task 1 and Task 2; the pre-commit basedpyright hook passed on both `feat` commits.
- **Committed in:** d11467e (Task 1, no functools), 2579273 (Task 2, functools added)

### Environment Note (not a code deviation)

- The basedpyright pre-commit hook crashed under the command sandbox (macOS `system-configuration` / Tokio panic — identical to 30-01), not a type error: the direct `.venv/bin/basedpyright` run was clean. The three per-task commits were run with the sandbox disabled so the hook could complete. Per the plan's critical reminder, `--no-verify` was NOT used. The user can manage sandbox restrictions via `/sandbox`.
- blacken-docs reformatted one comment's whitespace in the new async-guide code block; re-staged and re-committed (formatting-only, no content change).

---

**Total deviations:** 1 auto-fixed (1 blocking). No architectural changes, no scope creep, no new files, no sync-core change (D-30-12), no chokepoint widening (D-30-04).
**Impact on plan:** The only adjustment is which task-commit carries the `import functools` line; the final code, tests, and docs are exactly as the plan specifies.

## Threat Register Outcome

- **T-30-01** (poisoned connection returned to the pool → pool starvation) — **mitigated**: `on_abort=self._owner.invalidate` reused verbatim; `test_ingest_cancel.py` passed 20/20 looped under asyncio + trio (0 hangs), asserting `adbc_cancel==1`, `invalidate==1`, `checkedout()` 1→0.
- **T-30-02** (import-lint guard over `_async/` after adding `functools`) — **mitigated**: `tests/test_pkg_import_guard.py` + `tests/async/test_async_guard.py` pass with `functools` present.
- **T-30-04** (concurrent C access) — **mitigated**: the `self._owner._offloading()` per-call `_in_use` guard is present (no `_reader_open` lock taken).
- **T-30-05** (abort-the-abort) — **mitigated**: inherited from the reused shielded once-only `adbc_cancel` in `cancellable_offload`.
- **T-30-03** (untrusted `table_name` identifier) — **accepted** per the library pass-through charter; documented in the docstring as a driver-level identifier not sanitized by poolhouse.

## Issues Encountered

- The `grep -Lq "passed" ...` idiom in the plan's loop-verify snippet is unreliable in zsh (it can report a false "missing pass line" while every log actually contains "passed"). Re-verified with an explicit `grep -l | wc -l` count = 20/20 and a `grep -lE "failed|error"` = empty. The loop itself was correct; only the assertion idiom was replaced.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 30 is functionally complete: `AsyncCursor.adbc_ingest` ships with all four requirements GREEN, cancel parity proven looped, the import-lint guard re-passing, and the docs gate satisfied.
- Phase 31 (`fetch_df`/`fetch_polars`) can reuse this phase's whole-op offload shape; the `functools.partial` keyword-binding pattern is now the established milestone answer for any future keyword-bearing offload.
- The full mode-table consolidation across the docs (DOCS-02) remains scoped to Phase 33; the `replace`-drops warning is present here so it is not absent in the interim.
- No blockers.

## Self-Check: PASSED

- `src/adbc_poolhouse/_async/_cursor.py` contains `async def adbc_ingest` (1 match) — FOUND.
- All three task commits present in git log: `d11467e`, `2579273`, `69aaf7c` — FOUND.
- Whole-project `basedpyright` 0 errors; full async suite 162 passed / 4 skipped; cancel loop 20/20; `mkdocs build --strict` exit 0 — all verified this session.

---
*Phase: 30-async-bulk-write*
*Completed: 2026-07-01*
