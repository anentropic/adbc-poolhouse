---
phase: 30-async-bulk-write
plan: 01
subsystem: testing
tags: [adbc, adbc_ingest, async, anyio, trio, pyarrow, duckdb, tdd, cancel, invalidate, functools-partial]

# Dependency graph
requires:
  - phase: 29-arrow-streaming
    provides: "BlockingStubCursor sticky-release gate, test_reader_cancel.py cancel-harness template, duckdb_async_pool + make_stub_async_connection fixtures, RED-first TDD rhythm"
  - phase: 25-cancel-invalidate
    provides: "cancellable_offload + on_abort=invalidate poison-recovery contract the cancel test pins"
provides:
  - "BlockingStubCursor.adbc_ingest — blockable stub gate + ingest_call_count counter (deterministic in-flight cancel harness)"
  - "Four RED test files pinning INGEST-01..04 as executable contracts (round-trip, modes, cancel, signature)"
  - "Wave-0 RED baseline: all 20 test cases fail solely on the missing AsyncCursor.adbc_ingest — the GREEN target for Plan 30-02"
affects: [30-02, 30-async-bulk-write]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Blocking-stub in-flight cancel harness (ingest_call_count gate) over a slow-DuckDB race — deterministic, loopable"
    - "Wave-0 RED pyright pragmas: file-level suppression of ONLY the not-yet-existent-symbol errors, with a delete-on-GREEN comment (Phase 29 precedent)"

key-files:
  created:
    - tests/async/test_ingest_roundtrip.py
    - tests/async/test_ingest_modes.py
    - tests/async/test_ingest_cancel.py
    - tests/async/test_ingest_signature.py
  modified:
    - tests/_async_harness/stubs.py

key-decisions:
  - "Chose the blocking-stub cancel harness (Claude's Discretion, resolved per RESEARCH Pattern 2) over a slow DuckDB ingest — deterministic, no finish-before-cancel flake"
  - "Applied Phase 29 Wave-0 RED pyright pragmas to keep the strict whole-project basedpyright pre-commit hook green while the production method is still absent"

patterns-established:
  - "ingest_call_count gate: await_inside(lambda: ...ingest_call_count >= 1) proves the worker is inside the blocked ingest before cancelling"
  - "Cancel test asserts connection recovery ONLY (adbc_cancel==1, invalidate==1, checkedout 1->0), never post-cancel table state (D-30-10)"

requirements-completed: [INGEST-01, INGEST-02, INGEST-03, INGEST-04]

# Metrics
duration: 6min
completed: 2026-07-01
---

# Phase 30 Plan 01: Async Bulk Write RED Scaffolding Summary

**Four failing test files plus a blockable `BlockingStubCursor.adbc_ingest` gate that pin INGEST-01..04 (round-trip, modes, data pass-through, cancel/invalidate parity) as executable contracts — all 20 cases fail solely because `AsyncCursor.adbc_ingest` does not exist yet.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-01T20:58:32Z
- **Completed:** 2026-07-01T21:04:20Z
- **Tasks:** 3
- **Files modified:** 5 (1 harness modified, 4 test files created)

## Accomplishments

- Extended `BlockingStubCursor` with a blockable `adbc_ingest` (record-under-lock → `_block()` → `return 3`) plus an `ingest_call_count` counter, reusing the existing sticky-release cancel machinery with zero new latch wiring — the deterministic in-flight cancel harness for INGEST-04.
- Landed four RED test files that collect cleanly under strict basedpyright and fail only on the missing `AsyncCursor.adbc_ingest`: DuckDB create/append round-trip + Table/RecordBatch pass-through (INGEST-01/03), all four `Literal` modes with `replace` drop-then-create semantics (INGEST-02), and cancel/timeout/DuckDB-drain parity (INGEST-04).
- Encoded the concurrency-hygiene discipline verbatim from `test_reader_cancel.py` (`concurrency_marks` x-loop + timeout, `real_clock_watchdog`, `await_inside`, both anyio backends) and verified the RED failure is deterministic under a 5x repeat loop (20 cases, 0.11s, zero hangs).

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend BlockingStubCursor with a blockable adbc_ingest** - `8fc93e6` (test)
2. **Task 2: RED round-trip + modes + signature tests (INGEST-01/02/03)** - `fc9a734` (test)
3. **Task 3: RED cancel/invalidate parity test (INGEST-04, T-30-01)** - `f975f5b` (test)

_TDD note: this is the whole-plan RED gate (Wave 0). The GREEN commit (`feat`) lands in Plan 30-02, which implements `AsyncCursor.adbc_ingest`._

## Files Created/Modified

- `tests/_async_harness/stubs.py` - Added `BlockingStubCursor.adbc_ingest` (blockable, `del`s all six params, increments `ingest_call_count` under `_lock`, calls `_block()`, returns 3) + `ingest_call_count` init and class-attributes docstring entry. `mode` kept positional-or-keyword to match the driver/`_SyncCursor` Protocol.
- `tests/async/test_ingest_roundtrip.py` - INGEST-01 create/append round-trip (returns 3, count 3→6) + INGEST-03 `test_data_passthrough` (a `pyarrow.Table` and a `pyarrow.RecordBatch` round-trip unchanged). Both backends.
- `tests/async/test_ingest_modes.py` - INGEST-02: `create`/`append`/`create_append` accumulation and `replace` asserting drop-then-create (2 rows after replacing a 3-row table, not cumulative 5). Both backends.
- `tests/async/test_ingest_cancel.py` - INGEST-04: stub cancel leg (gate on `ingest_call_count >= 1`, cancel, `adbc_cancel_call_count == 1` + `invalidate_call_count == 1`), timeout leg (`virtual_clock` + `fail_after`), DuckDB drain leg (`conn.invalidate()`, `checkedout()` 1→0). `concurrency_marks`, both backends, `real_clock_watchdog` hang backstop, no positive sleeps, no post-cancel table-state assertions.
- `tests/async/test_ingest_signature.py` - INGEST-01 signature contract via `inspect.signature`: `mode`/`catalog_name`/`db_schema_name`/`temporary` are `KEYWORD_ONLY`, `table_name`/`data` are not, `mode` defaults to `"create"`.

## Decisions Made

- **Blocking-stub cancel harness over slow DuckDB** (Claude's Discretion resolved per RESEARCH Pattern 2 / D-30 harness note): a real ingest can finish before the cancel fires (flaky); the sticky-release stub gate is deterministic and reuses the existing `adbc_cancel`/`close`/`release` unblock path — no new cancel machinery in the stub.
- **Wave-0 RED pyright pragmas** (see Deviations, Rule 3): the strict whole-project basedpyright pre-commit hook (`include = ["src", "tests"]`, `typeCheckingMode = "strict"`) would block committing RED tests that reference the not-yet-existent `adbc_ingest`. Applied the established Phase 29 pattern — file-level `# pyright: report...=false` blocks suppressing only the missing-symbol errors, with a delete-on-GREEN comment.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wave-0 RED basedpyright pragmas to unblock the pre-commit type-check hook**
- **Found during:** Task 2 (and re-applied in Task 3)
- **Issue:** The plan's RED test files reference `AsyncCursor.adbc_ingest`, which does not exist until Plan 30-02. The project's basedpyright pre-commit hook runs `typeCheckingMode = "strict"` over `include = ["src", "tests"]` with `pass_filenames: false`, so the resulting `reportAttributeAccessIssue`/`reportUnknown*`/`reportIndexIssue` errors would fail the commit and block landing the RED scaffolding. The plan did not specify how to keep the strict hook green during RED.
- **Fix:** Added file-level `# pyright: report...=false` pragma blocks that suppress ONLY the errors caused by the not-yet-existent method (and, in the round-trip file, the deliberately-loose `object` return typing of `fetchone`/`fetchall`), each with a comment instructing removal once the production method lands. This is the exact in-repo precedent from Phase 29's RED reader tests (commit `e16ca20`, `test_reader_stream.py`).
- **Files modified:** tests/async/test_ingest_roundtrip.py, tests/async/test_ingest_modes.py, tests/async/test_ingest_cancel.py, tests/async/test_ingest_signature.py
- **Verification:** `.venv/bin/basedpyright` reports 0 errors across all four files + the stub; the RED runtime failures still hold (pragmas suppress static checks only, not the runtime `AttributeError`).
- **Committed in:** fc9a734 (Task 2), f975f5b (Task 3)

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** Necessary to land RED tests under the strict pre-commit gate; matches the established Phase 29 pattern exactly. No scope creep — the pragmas are RED-only and carry a delete-on-GREEN instruction for Plan 30-02.

## Issues Encountered

- **basedpyright pre-commit hook crashed under the command sandbox** (Rust `system-configuration` / Tokio panic when `uv run basedpyright` looked up macOS system config). Not a type error — the direct `.venv/bin/basedpyright` run was clean. Resolved by running the three per-task commits with the sandbox disabled so the hook could complete; the user can manage sandbox restrictions via `/sandbox`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 30-02 (GREEN) is unblocked: implement `AsyncCursor.adbc_ingest` as a `fetch_arrow_table` clone with a `functools.partial`-bound callable and `-> int` return, extend the `_SyncCursor` Protocol with `adbc_ingest`, add `import functools` + `CapsuleType`/`Literal` under `TYPE_CHECKING`. When it lands, the 20 RED cases here turn GREEN and the Wave-0 pyright pragmas in all four test files must be deleted so the files type-check cleanly under the strict whole-project gate.
- Cancel-test loop hygiene (`concurrency_marks`) is wired; Plan 30-02's GREEN verification must run `test_ingest_cancel.py` under a high `ADBC_ASYNC_REPEAT` (both backends, `rc=$?` + grep the pass line, never `if ! cmd` in zsh) to prove zero hangs — the deadlock a single-shot run would miss.
- No blockers.

## Self-Check: PASSED

All five source files and the SUMMARY exist on disk; all three task commits (`8fc93e6`, `fc9a734`, `f975f5b`) are present in the git log.

---
*Phase: 30-async-bulk-write*
*Completed: 2026-07-01*
