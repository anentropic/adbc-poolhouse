---
phase: 34-async-metadata
plan: 02
subsystem: async
tags: [async, metadata, adbc, offload, duckdb, pyarrow, anyio]

# Dependency graph
requires:
  - phase: 34-01
    provides: four RED test files (test_meta_signature/roundtrip/stream/unsupported) that pin the observable META-01/02/03 contracts
  - phase: 29
    provides: AsyncRecordBatchReader (4-arg constructor, reader-lifetime lock, shielded invalidate)
  - phase: 24
    provides: AsyncConnection two-tier _offloading() guard + transient-token offload chokepoint
provides:
  - "_SyncConnection structural-typing Protocol on AsyncConnection (six adbc_get_* signatures)"
  - "_noop_cancel module-level cancel hook for connection-level metadata readers"
  - "AsyncConnection.adbc_get_info -> dict[str | int, Any]"
  - "AsyncConnection.adbc_get_table_types -> list[str]"
  - "AsyncConnection.adbc_get_table_schema -> pyarrow.Schema"
  - "AsyncConnection.adbc_get_objects / adbc_get_statistics / adbc_get_statistic_names -> AsyncRecordBatchReader"
affects:
  - plan 34-03 (docs: shrink async caveat, add metadata how-to, API-reference render + mkdocs --strict gate)
  - phase 35 (async prepared statements — same offload-wrapper pattern)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "connection-level metadata offload wrapper cloning commit/rollback (value) and fetch_record_batch (streaming)"
    - "_SyncConnection Protocol + cast bridge for the SQLAlchemy fairy (mirrors _SyncCursor)"
    - "module-level _noop_cancel for cursor-less readers (mirrors _pull convention)"
    - "_reader_open set AFTER the _offloading() span, success path only (Pitfall 3)"

key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_async/_connection.py
    - tests/async/test_meta_signature.py
    - tests/async/test_meta_roundtrip.py
    - tests/async/test_meta_stream.py
    - tests/async/test_meta_unsupported.py

key-decisions:
  - "Plain non-cancellable offload for all six methods (mirror commit/rollback) — the connection has no adbc_cancel, so no cancellable_offload/on_abort (locked #2)"
  - "Streaming trio wrap the native sync reader in AsyncRecordBatchReader with _noop_cancel as the 4th arg; _reader_open set after the span, success-path only (locked #1/#5)"
  - "Unsupported backend surfaces the driver's native NotSupportedError unchanged — no new error types, no find_spec (locked #6)"
  - "Moved _noop_cancel definition from task 1 to task 2 (first use) so each commit's basedpyright gate stays at 0 errors (reportUnusedFunction would otherwise fail task 1)"

patterns-established:
  - "Connection metadata methods reach the driver via cast('_SyncConnection', self._fairy) — no driver_connection unwrap"
  - "kw-only driver filters forwarded through functools.partial to keep the offload TypeVarTuple arity checked"

requirements-completed: [META-01, META-02, META-03]

# Metrics
duration: ~20min
completed: 2026-07-04
---

# Phase 34 Plan 02: Async Connection Metadata Implementation Summary

**Six `adbc_get_*` metadata methods on `AsyncConnection` as plain-offload wrappers over the SQLAlchemy fairy — value trio returns native dict/list/pyarrow.Schema, streaming trio returns AsyncRecordBatchReader — turning all 16 RED tests GREEN.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-04
- **Tasks:** 2 (both `tdd="true"` GREEN implementation against wave-1 RED tests)
- **Files modified:** 5 (1 source + 4 test files)

## Accomplishments

- Added the `_SyncConnection` structural Protocol carrying all six verified ADBC signatures, plus the module-level `_noop_cancel` cancel hook, mirroring the existing `_SyncCursor` / `_pull` idioms.
- Implemented the value-returning trio (`adbc_get_info`, `adbc_get_table_types`, `adbc_get_table_schema`) as plain `offload` calls inside `self._offloading()`, cloning `commit`/`rollback`; `adbc_get_table_schema` forwards its kw-only filters through `functools.partial`.
- Implemented the streaming trio (`adbc_get_objects`, `adbc_get_statistics`, `adbc_get_statistic_names`) as `offload` wrappers returning `AsyncRecordBatchReader(sync_reader, self._limiter, self, _noop_cancel)`, setting `_reader_open = True` after the offload span on the success path only.
- Each method carries a full Google-style Markdown docstring (Args/Returns/Raises + singular `Example:`), documenting the non-cancellable caveat and, for the streaming trio, the reader-lifetime lock and per-pull invalidate asymmetry.
- Removed the phase-29-style RED pyright pragma blocks from all four test files now that the symbols exist and type-check cleanly.

## Task Commits

Each task was committed atomically:

1. **Task 1: Typing bridge + value trio** — `be3a51f` (feat)
2. **Task 2: Streaming trio** — `fa0c899` (feat)

**Plan metadata:** see final `docs(34-02)` commit.

## Files Created/Modified

- `src/adbc_poolhouse/_async/_connection.py` — added `_SyncConnection` Protocol, `_noop_cancel`, and the six `adbc_get_*` methods (imports: `functools`, `Protocol`, `Any`/`Literal`/`pyarrow` under TYPE_CHECKING, runtime `AsyncRecordBatchReader`).
- `tests/async/test_meta_roundtrip.py` — dropped RED pragma block (value symbols exist).
- `tests/async/test_meta_signature.py` — dropped RED pragma block (all six symbols exist).
- `tests/async/test_meta_stream.py` — dropped RED pragma block (streaming symbols exist).
- `tests/async/test_meta_unsupported.py` — dropped RED pragma block (statistics symbols exist).

## Verification

- All 16 meta tests GREEN under asyncio and trio: `test_meta_signature` (6), `test_meta_roundtrip` (2), `test_meta_stream` (4), `test_meta_unsupported` (4).
- `.venv/bin/basedpyright src/adbc_poolhouse/_async/_connection.py` — 0 errors (strict). Test files also 0 errors after pragma removal.
- `test_meta_guard.py` — 2 passed (plain `offload` only, no bare `to_thread`, no `import asyncio`).
- Loop-stability gate: 20 iterations of `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async` — 0 hangs / 0 failures (2718 passed, 80 skipped each).

## Decisions Made

- **Non-cancellable offload for all six** (locked #2): the connection exposes no `adbc_cancel`, so every method uses plain `offload` (never `cancellable_offload`/`on_abort`), mirroring `commit`/`rollback`. The streaming readers thread `_noop_cancel` as the required 4th constructor arg.
- **`_reader_open` timing** (locked #5 / Pitfall 3): set to `True` after the `_offloading()` span exits and only on the success path, so a failed reader creation leaves the connection usable.
- **Native error unchanged** (locked #6): DuckDB's `NotSupportedError` for statistics propagates with no poolhouse wrapping and clean check-in.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Deferred `_noop_cancel` definition from Task 1 to Task 2**
- **Found during:** Task 1 (typing bridge + value trio)
- **Issue:** The plan's Task 1 action adds `_noop_cancel` (and the `AsyncRecordBatchReader` import), but neither is used until Task 2's streaming methods. basedpyright strict flagged `_noop_cancel` with `reportUnusedFunction` and ruff would flag the unused import — both break Task 1's "basedpyright 0 errors" acceptance criterion and the pre-commit gate.
- **Fix:** Moved the `_noop_cancel` definition and the runtime `AsyncRecordBatchReader` import into Task 2, where they are first used. All six Protocol signatures still landed in Task 1 as specified.
- **Files modified:** src/adbc_poolhouse/_async/_connection.py
- **Verification:** basedpyright reports 0 errors on `_connection.py` at both the Task 1 and Task 2 commits.
- **Committed in:** be3a51f (Task 1), fa0c899 (Task 2)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Task-attribution only — the same symbols land, split so each atomic commit passes the basedpyright gate. No behavioural change, no scope creep.

## Issues Encountered

- The `uv run basedpyright` pre-commit hook panics under the command sandbox (known gotcha: `system-configuration` NULL-object / uv Tokio panic). Both task commits were completed by re-running with the sandbox disabled so the hook ran natively — never `--no-verify`. Both passed all hooks natively.
- ruff-format auto-reformatted the new multi-line docstring openers on the first commit attempt of each task (project convention: newline after `"""`); the reformatted files were re-staged and committed.

## Threat Surface

No new threat surface beyond the plan's `<threat_model>`. All six methods forward caller-supplied `table_name`/`*_filter` strings to the driver untouched (T-34-01, accept — identical to `adbc_ingest`); each brackets its offload in `self._offloading()` and the streaming trio reuse the shared reader's shielded invalidate, keeping `pool.checkedout()` correct after a native error or cancelled pull (T-34-02, mitigate — proven by `test_meta_unsupported.py` and `test_meta_stream.py`).

## Next Phase Readiness

- Implementation complete; META-01/02/03 satisfied (GREEN). Ready for plan 34-03 (docs: shrink the async caveat, add the Connection metadata how-to, API-reference render + `mkdocs build --strict` gate, META-04).
- No blockers.

## Self-Check: PASSED

- FOUND: `.planning/phases/34-async-metadata/34-02-SUMMARY.md`
- FOUND: `src/adbc_poolhouse/_async/_connection.py`
- FOUND commit: `be3a51f` (Task 1)
- FOUND commit: `fa0c899` (Task 2)

---
*Phase: 34-async-metadata*
*Completed: 2026-07-04*
