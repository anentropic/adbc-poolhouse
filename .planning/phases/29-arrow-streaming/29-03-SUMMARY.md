---
phase: 29-arrow-streaming
plan: 03
subsystem: api
tags: [async, anyio, pyarrow, record-batch-reader, streaming, offload, cancellation, adbc]

# Dependency graph
requires:
  - phase: 29-01
    provides: the six Wave-0 RED reader test files + BlockingStubReader harness stub
  - phase: 29-02
    provides: AsyncConnection._reader_open lifetime flag + two-tier from_reader entry guard
provides:
  - AsyncRecordBatchReader — composition wrapper over a sync pyarrow.RecordBatchReader
  - module-level _Exhausted/_EXHAUSTED sentinel + _pull worker helper (StopIteration→sentinel)
  - _SyncReader structural Protocol (schema/read_next_batch/close)
  - AsyncCursor.fetch_record_batch + _SyncCursor.fetch_record_batch Protocol line (PKG-01)
  - the __aexit__/__del__/_detached/per-batch-cancel surface phases 30-31 copy
affects: [30-async-bulk-write, 31-dataframe-convenience, 32-edge-hardening, 33-documentation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Composition (hold sync reader), never subclass pyarrow.RecordBatchReader (D-29-01)"
    - "Worker-side StopIteration→module-level sentinel across to_thread (D-29-05)"
    - "Per-pull cancellable_offload(from_reader=True) reentrancy tier (D-29-10/14)"
    - "Shielded idempotent close clearing lifetime lock in finally (EDGE-20/D-29-16)"
    - "Warn-only __del__ ResourceWarning, never awaits a coroutine (D-29-15)"
    - "Reader-lifetime lock set success-only OUTSIDE the creation offload span (Pitfall 5)"

key-files:
  created:
    - src/adbc_poolhouse/_async/_reader.py
  modified:
    - src/adbc_poolhouse/_async/_cursor.py
    - src/adbc_poolhouse/_async/_connection.py
    - tests/_async_harness/stubs.py

key-decisions:
  - "AsyncConnection.invalidate clears _reader_open so close-after-invalidate stays a safe no-op (Rule 1 fix)"
  - "Empty stub reader exhausts on the first pull (no block); blocks only with pending batches"
  - "Stub cursor propagates adbc_cancel/close/release to its readers (Pitfall 4 wiring)"
  - "fetch_record_batch docstring uses a plain AsyncRecordBatchReader reference (cross-module autoref unresolved until a dedicated API page)"

patterns-established:
  - "Streaming async wrapper as a near-verbatim sibling of AsyncCursor"
  - "Reader-lifetime binding to the checked-out connection via _reader_open, cleared only by close/checkin/invalidate"

requirements-completed: [STREAM-01, STREAM-02, STREAM-03, STREAM-04, STREAM-05, EDGE-33, EDGE-20, EDGE-22, EDGE-23, PKG-01, PKG-03]

# Metrics
duration: ~55min
completed: 2026-07-01
---

# Phase 29 Plan 03: Arrow Streaming Reader Summary

**`AsyncRecordBatchReader` — a composition wrapper over the sync `pyarrow.RecordBatchReader` with per-batch offloaded iteration, worker-side StopIteration→sentinel, shielded idempotent close, warn-only `__del__`, and connection-lifetime binding so read-after-checkin surfaces the driver's native `ArrowInvalid` — plus `AsyncCursor.fetch_record_batch` that creates it.**

## Performance

- **Duration:** ~55 min
- **Started:** 2026-07-01T~16:53Z
- **Completed:** 2026-07-01
- **Tasks:** 2 (both TDD, Wave-0 RED tests turned GREEN)
- **Files modified:** 10 (2 production created/extended, 1 production Rule-1 fix, 1 harness, 6 test files)

## Accomplishments

- **`_reader.py`** ships `AsyncRecordBatchReader` by composition (never subclasses `pyarrow.RecordBatchReader`, D-29-01): the `_SyncReader` structural Protocol, the module-level `_Exhausted`/`_EXHAUSTED` sentinel and `_pull` helper (catches worker-side `StopIteration` so it never crosses `to_thread` as `RuntimeError`, D-29-05), per-pull `cancellable_offload(from_reader=True)` iteration, shielded idempotent `close` that clears `_reader_open` in a `finally` (EDGE-20), and a warn-only `__del__` that never calls `self.close()` (EDGE-22, D-29-15).
- **`AsyncCursor.fetch_record_batch`** offloads reader creation, then sets `owner._reader_open = True` OUTSIDE the `_offloading()` span, success-only (Pitfall 5), and wraps the sync reader — threading the CURSOR's own `_adbc_cancel` as the 4th constructor arg (the reader has none of its own, Pitfall 4). `_SyncCursor` gains the `fetch_record_batch` Protocol line (PKG-01).
- **All reader tests GREEN on both backends:** STREAM-01/02/03/04/05/06, EDGE-33/20/22/23 pass under asyncio AND trio on DuckDB (Snowflake legs skip-scoped per 29-01 A1). Looped ×15 → 0 hangs (no deadlock, no platform-dependent lost-wakeup).
- **Gates green:** whole-project basedpyright strict 0 errors; ruff clean; import-lint guard (`scan_async_package`) `[]` over `_async/`; pkg-import guard; `mkdocs build --strict` clean; no circular import.

## Task Commits

1. **Task 1: Create `_reader.py`** — `04d8ff4` (feat) — AsyncRecordBatchReader + _SyncReader + _EXHAUSTED sentinel + module-level _pull.
2. **Task 2: Wire `AsyncCursor.fetch_record_batch` + extend `_SyncCursor` Protocol** — `a841f65` (feat) — includes the Rule-1 `invalidate` fix in `_connection.py`.
3. **GREEN-wave cleanup + harness fix** — `1db6d3f` (test) — stub reader release wiring, cancel/timeout test arming, pyarrow typed-alias + `AsyncRecordBatchReader` typing, removed the six Wave-0 RED pyright pragma blocks, `_cursor.py` docs-ref fix.

## Files Created/Modified

- `src/adbc_poolhouse/_async/_reader.py` (created, 333 lines) — the streaming reader wrapper.
- `src/adbc_poolhouse/_async/_cursor.py` — `fetch_record_batch` method + Protocol line + runtime import of `AsyncRecordBatchReader`; docs-ref made plain-text.
- `src/adbc_poolhouse/_async/_connection.py` — `invalidate` now clears `_reader_open` (Rule 1 fix).
- `tests/_async_harness/stubs.py` — `BlockingStubReader.read_next_batch` exhausts-when-empty; `BlockingStubCursor` retains + propagates cancel/close/release to readers; `fetch_record_batch` gains keyword batches/schema + `record_batch_batches` default.
- `tests/async/test_reader_{stream,close,lifetime,busy,resource,cancel}.py` — removed RED pyright pragma blocks; cancel/timeout arm a pending batch; lifetime uses typed `pyarrow.ArrowInvalid`; `_drain_one` typed.

## Decisions Made

- **`invalidate` clears `_reader_open`.** A cancelled reader-held connection being dropped must release its lifetime lock so the documented close-after-invalidate no-op does not raise `ConnectionBusyError`. Aligns with the existing `_in_use`-bypass discipline on the teardown paths (the fresh per-`connect()` `AsyncConnection` remains the ultimate backstop, D-29-13).
- **Empty stub reader exhausts without blocking; blocking is opt-in via pending batches.** This reconciles the drain tests (no external release) with the gated cancel/timeout tests (need a blocked, cancellable pull), matching the stub's own "exhausts on the first pull" contract.
- **Stub cursor propagates cancel/close/release to its readers.** Pitfall 4: a cancelled reader pull fires the CURSOR's `adbc_cancel`, but the blocked worker waits on the READER's separate gate, so the cursor must reach through to unblock it (mirrors a real driver closing its reader when the cursor closes).
- **Plain `AsyncRecordBatchReader` reference in the cursor docstring.** The cross-module autoref target is unresolved until `_reader.py` gets a dedicated API-reference page; the reader's own docstrings cross-ref fine. Keeps `mkdocs --strict` clean without a new page in this plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `invalidate` did not clear `_reader_open`, breaking close-after-invalidate**
- **Found during:** Task 2 (STREAM-05 `test_invalidate_drains_pool_duckdb`)
- **Issue:** After a live reader's connection was invalidated, `_reader_open` stayed `True`; a subsequent `await conn.close()` (foreign tier) raised `ConnectionBusyError` instead of being the documented safe no-op — failing the STREAM-05 pool-drain contract on both backends.
- **Fix:** `AsyncConnection.invalidate` now sets `self._reader_open = False` before the shielded offload, releasing the now-defunct lifetime lock.
- **Files modified:** `src/adbc_poolhouse/_async/_connection.py`
- **Verification:** `test_invalidate_drains_pool_duckdb` passes on asyncio + trio.
- **Committed in:** `a841f65`

**2. [Rule 3 - Blocking] Stub `BlockingStubReader`/`BlockingStubCursor` gaps hung the stub-backed reader tests**
- **Found during:** Task 1/2 verification (`test_stub_pull_recorded_on_worker_thread`, `test_cancel_during_pull_*`, `test_timeout_during_pull_*` all hung to the 40s timeout)
- **Issue:** The empty stub reader blocked forever on the first pull (drain tests had no release), and the cursor's `adbc_cancel`/`close`/`release` never reached the reader's separate blocking gate (cancel/timeout tests could not unblock the worker — Pitfall 4).
- **Fix:** `read_next_batch` exhausts immediately when empty (blocks only with pending batches); `BlockingStubCursor` retains handed-out readers and propagates cancel/close/release to them; `fetch_record_batch` gains keyword batches/schema + a `record_batch_batches` default so the real async path can be armed to block. The cancel/timeout tests arm a pending batch.
- **Files modified:** `tests/_async_harness/stubs.py`, `tests/async/test_reader_cancel.py`
- **Verification:** The six previously-hanging stub tests pass; the full async + harness suite (168 passed) confirms no Phase 24/25 EDGE regression; looped ×15 = 0 hangs.
- **Committed in:** `1db6d3f`

**3. [Rule 3 - Blocking] Strict-mode errors surfaced when the RED pyright pragma blocks were removed**
- **Found during:** GREEN-wave cleanup (removing the Wave-0 pragma blocks per the plan's critical note)
- **Issue:** `pyarrow.lib.ArrowInvalid` is untyped in the pyarrow stubs (`reportUnknownMemberType`), and `_drain_one(reader: object)` called `reader.__anext__()` on `object` — 11 strict errors across `test_reader_lifetime.py` / `test_reader_cancel.py`.
- **Fix:** switched the lifetime tests to the typed `pyarrow.ArrowInvalid` alias (same class), typed `_drain_one`'s param as `AsyncRecordBatchReader`.
- **Files modified:** `tests/async/test_reader_lifetime.py`, `tests/async/test_reader_cancel.py`
- **Verification:** whole-project basedpyright strict 0 errors; ruff clean.
- **Committed in:** `1db6d3f`

**4. [Rule 3 - Blocking] mkdocs `--strict` aborted on an unresolved cross-module autoref**
- **Found during:** GREEN-wave docs gate
- **Issue:** `[AsyncRecordBatchReader][adbc_poolhouse._async._reader.AsyncRecordBatchReader]` in `_cursor.py` could not resolve (the new `_reader.py` module has no dedicated reference page), aborting the strict build.
- **Fix:** used a plain `` `AsyncRecordBatchReader` `` reference in that docstring (the reader's own docstrings' cross-refs resolve fine).
- **Files modified:** `src/adbc_poolhouse/_async/_cursor.py`
- **Verification:** `mkdocs build --strict` passes with 0 warnings.
- **Committed in:** `1db6d3f`

---

**Total deviations:** 4 auto-fixed (1 Rule-1 bug, 3 Rule-3 blocking). One (the `invalidate` fix) touched a file outside the plan's `files_modified` (`_connection.py`) but was required for the plan's own STREAM-05 must-have. The rest are test-harness/scaffolding fixes the plan's critical notes anticipated (the Wave-0 GREEN-wave cleanup).
**Impact on plan:** No scope creep. The production design (`_reader.py` + `fetch_record_batch`) matches the plan and PATTERNS templates verbatim; the deviations close plan-01 harness gaps and satisfy the strict typing/docs gates.

## Issues Encountered

- **Pre-commit basedpyright panics under the command sandbox** (known uv-sandbox pitfall — a `system-configuration` NULL-object panic). All three commits were made outside the sandbox with hooks enabled (never `--no-verify`), and the basedpyright hook passed each time.
- **Stub-backed reader tests hung on first run.** Diagnosed as the plan-01 harness gaps above; resolved via the Rule-3 fixes and confirmed with a ×15 loop (0 hangs) per the project's loop-flaky-concurrency lesson.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The streaming surface (`__aexit__`/`__del__`/`_detached`/per-batch-cancel) is in place for Phases 30 (async bulk write) and 31 (DataFrame convenience) to copy.
- `_SyncCursor` Protocol extension pattern (PKG-01) and the import-lint gate (PKG-03) are established.
- Snowflake reader legs remain manual-only re-record follow-ups (29-01 A1); DuckDB carries the mandatory EDGE-33 coverage.

## Self-Check: PASSED

- FOUND: `src/adbc_poolhouse/_async/_reader.py` (class `AsyncRecordBatchReader`)
- FOUND: `AsyncCursor.fetch_record_batch` in `_cursor.py`
- FOUND: `.planning/phases/29-arrow-streaming/29-03-SUMMARY.md`
- FOUND commits: `04d8ff4`, `a841f65`, `1db6d3f`

---
*Phase: 29-arrow-streaming*
*Completed: 2026-07-01*
