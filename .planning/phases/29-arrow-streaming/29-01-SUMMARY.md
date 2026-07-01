---
phase: 29-arrow-streaming
plan: 01
subsystem: testing
tags: [pyarrow, record-batch-reader, anyio, asyncio, trio, adbc, cassette, stub-harness, red-scaffolding]

# Dependency graph
requires:
  - phase: 23-test-harness-foundation
    provides: BlockingStubCursor/BlockingStubConnection sticky-release _block harness, make_stub_async_connection fixture
  - phase: 24-core-async-wrapper
    provides: AsyncConnection._offloading guard, AsyncCursor offload shape, _SyncCursor Protocol
  - phase: 25-cancel-safety
    provides: cancellable_offload + on_abort invalidate poison-recovery, snowflake_async_pool cassette fixture
provides:
  - "BlockingStubReader harness stub satisfying the forthcoming _SyncReader surface (schema/read_next_batch/close), reusing the sticky-release _block idiom; no adbc_cancel (fired via owning cursor)"
  - "BlockingStubCursor.fetch_record_batch() returning a fresh BlockingStubReader"
  - "Six RED reader test files pinning STREAM-01..06 + EDGE-20/22/23/33, each parametrized asyncio x trio"
  - "A1 resolution: the Snowflake cassette CANNOT replay a streaming fetch_record_batch; Snowflake reader legs scoped to manual-only re-record"
affects: [29-02, 29-03, arrow-streaming, async-reader]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wave-0 RED scaffolding: tests reference not-yet-existing production symbols; file-level pyright pragmas suppress ONLY the missing-symbol errors under the strict whole-project gate (removed when GREEN lands)"
    - "Streaming stub reader mirrors the cursor stub's sticky-release _block gate; read_next_batch raises bare StopIteration (args==()) at exhaustion to exercise the worker-side _pull catch"
    - "A1 mechanism probe: assert the replay plugin's cursor surface directly (ReplayCursor has no fetch_record_batch) rather than round-tripping the cassette"

key-files:
  created:
    - tests/async/test_reader_stream.py
    - tests/async/test_reader_close.py
    - tests/async/test_reader_lifetime.py
    - tests/async/test_reader_cancel.py
    - tests/async/test_reader_busy.py
    - tests/async/test_reader_resource.py
    - tests/async/test_reader_cassette_smoke.py
  modified:
    - tests/_async_harness/stubs.py

key-decisions:
  - "A1 RESOLVED: the checked-in Snowflake cassette cannot replay a streaming fetch_record_batch (pytest-adbc-replay ReplayCursor implements only fetch_arrow_table + row fetches; the cassette stores one materialized Arrow result). Snowflake reader legs scoped to a manual-only re-record follow-up; DuckDB carries the mandatory EDGE-33 coverage."
  - "Reader-lifetime type gate: file-level pyright pragmas (reportMissingImports/AttributeAccessIssue/Unknown*Type) suppress ONLY the errors caused by the absent production symbols, keeping the strict whole-project basedpyright gate green while the tests stay RED."
  - "The added Snowflake cassette smoke asserts the replay-cursor surface (no fetch_record_batch) so a future plugin gaining streaming replay fails the test loudly — the signal to re-enable the offline Snowflake legs."

patterns-established:
  - "RED scaffolding pragma block: a documented 5-line pyright suppression tied to the exact missing symbols, to be deleted when GREEN lands"
  - "Streaming stub reader: sticky _closed_latched checked at _block entry before the re-arm clear; happy-path release transient; no adbc_cancel (Pitfall 4)"

requirements-completed: [STREAM-01, STREAM-02, STREAM-03, STREAM-04, STREAM-05, STREAM-06, EDGE-33, EDGE-20, EDGE-22, EDGE-23]

# Metrics
duration: 13min
completed: 2026-07-01
---

# Phase 29 Plan 01: Arrow Streaming Wave-0 RED Scaffolding Summary

**A `_SyncReader`-shaped blocking stub reader plus six RED reader test files (46 asyncio×trio cases) pinning STREAM-01..06 + EDGE-20/22/23/33, and a resolved A1 finding that the Snowflake cassette cannot replay streaming fetch_record_batch.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-07-01T16:29:52+01:00 (first task commit)
- **Completed:** 2026-07-01T16:41:27+01:00 (last task commit)
- **Tasks:** 3
- **Files modified:** 8 (1 harness extended, 7 test files created)

## Accomplishments
- Extended `tests/_async_harness/stubs.py` with `BlockingStubReader` (satisfying the forthcoming `_SyncReader` surface: `schema` property, blocking `read_next_batch`, terminal `close`) plus `BlockingStubCursor.fetch_record_batch()`. It reuses the cursor stub's sticky-release `_block` gate (`_closed_latched` checked at entry before the re-arm clear), stays anyio-free (D-03), and has NO `adbc_cancel` of its own (Pitfall 4). `read_next_batch` raises a bare `StopIteration` (`args == ()`) at exhaustion so the worker-side `_pull` catch is exercised in later waves.
- Authored six RED test files under `tests/async/` (46 tests, asyncio×trio): `test_reader_stream.py` (STREAM-01/02), `test_reader_close.py` (STREAM-03 + EDGE-20), `test_reader_lifetime.py` (STREAM-04/EDGE-33), `test_reader_cancel.py` (STREAM-05), `test_reader_busy.py` (STREAM-06), `test_reader_resource.py` (EDGE-22/23). Cancel/busy/lifetime carry `concurrency_marks` (loop + timeout).
- Resolved research assumption A1 with a direct plugin-surface probe (`test_reader_cassette_smoke.py`) and scoped the Snowflake reader legs accordingly.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend the harness with a BlockingStubReader + stub fetch_record_batch** - `7652762` (test)
2. **Task 2: Author the six failing reader test files (STREAM-01..06 + EDGE-20/22/23/33)** - `e16ca20` (test)
3. **Task 3: Snowflake cassette streaming smoke (resolve A1) and record the decision** - `64cd6cd` (test)

**Plan metadata:** (this SUMMARY + STATE/ROADMAP/REQUIREMENTS) committed separately.

## Files Created/Modified
- `tests/_async_harness/stubs.py` - Added `BlockingStubReader` + `BlockingStubCursor.fetch_record_batch()`; extended the module docstring.
- `tests/async/test_reader_stream.py` - STREAM-01/02: returns `AsyncRecordBatchReader`; `async for` yields `pyarrow.RecordBatch`; pulls run off the loop thread (real DuckDB + stub thread-id proof).
- `tests/async/test_reader_close.py` - STREAM-03 + EDGE-20: `schema` synchronous passthrough; `async with` close; a raising shielded close chains the body error via `__context__` and still clears `_reader_open`.
- `tests/async/test_reader_lifetime.py` - STREAM-04/EDGE-33: DuckDB drain-then-checkin rows + read-after-close/checkin native `pyarrow.lib.ArrowInvalid` ("stream that has already been closed"); Snowflake legs skipped per A1.
- `tests/async/test_reader_cancel.py` - STREAM-05: cancel/timeout on a pull fires the cursor's `adbc_cancel` once, invalidates once, `pool.checkedout() == 0` (real DuckDB invalidate leg).
- `tests/async/test_reader_busy.py` - STREAM-06: foreign op while the reader is live raises `ConnectionBusyError`; the reader's own pulls are exempt; the lock persists until `close()`, not at drain.
- `tests/async/test_reader_resource.py` - EDGE-22/23: unclosed reader `__del__` emits `ResourceWarning` and no "coroutine never awaited" `RuntimeWarning`; the `async with` happy path emits neither.
- `tests/async/test_reader_cassette_smoke.py` - A1 probe: asserts the `pytest-adbc-replay` `ReplayCursor` has no `fetch_record_batch` (fails loudly if a future plugin adds streaming replay).

## Decisions Made
- **A1 (Snowflake cassette streaming replay) = NO.** The `pytest-adbc-replay` `ReplayCursor` (`.venv/.../pytest_adbc_replay/_cursor.py`) implements only `fetch_arrow_table` (a materialized `pyarrow.Table`) plus `fetchall`/`fetchone`/`fetchmany`; it has NO `fetch_record_batch`, and the checked-in `snowflake_arrow_round_trip` cassette stores a single materialized `.arrow` result (`SELECT 1 AS n, 'hello' AS s`), not a streaming reader interaction. The cassette therefore cannot serve a streaming `fetch_record_batch` offline. Both Snowflake reader legs in `test_reader_lifetime.py` are scoped to a MANUAL-ONLY re-record follow-up (per 29-VALIDATION §Manual-Only Verifications): they carry `@pytest.mark.snowflake` (CI runs `-m "not snowflake and not databricks"`, so they never run in the offline gate) plus a class-level `pytest.mark.skip` with the A1 reason. DuckDB carries the mandatory EDGE-33 coverage and is NOT gated on the Snowflake result.
- **Wave-0 type-gate reconciliation (see Deviations Rule 3).** The strict whole-project basedpyright pre-commit hook (`include = ["src", "tests"]`, `pass_filenames: false`) would reject RED tests that reference the not-yet-existing `fetch_record_batch` / `AsyncRecordBatchReader` (116 unknown-symbol errors). Resolved with a documented file-level pyright pragma block in each RED file, suppressing ONLY the five rules that fire because of the absent symbols; the block is to be deleted when plans 02/03 land the production code.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RED tests vs. the strict whole-project basedpyright gate**
- **Found during:** Task 2 (authoring the six RED reader test files)
- **Issue:** The project's basedpyright pre-commit hook type-checks all of `tests/` on every commit (`pass_filenames: false`, `include = ["src","tests"]`, strict). The RED tests reference `AsyncCursor.fetch_record_batch` and `adbc_poolhouse._async._reader.AsyncRecordBatchReader`, which do not exist until plans 02/03 — 116 unknown-symbol / missing-import errors that would block the commit. The plan explicitly wants these RED tests committed now.
- **Fix:** Added a documented file-level pyright pragma block (`# pyright: reportMissingImports=false` + `reportAttributeAccessIssue` + `reportUnknown{Variable,Member,Argument}Type=false`) to each of the six RED reader test files, tied by comment to the exact missing symbols and marked for deletion when GREEN lands. Removed a now-redundant `# type: ignore[attr-defined]` in the cancel test.
- **Files modified:** all six `tests/async/test_reader_*.py` (except the smoke test, which references only the installed plugin surface)
- **Verification:** `.venv/bin/basedpyright` (whole project) = 0 errors; `.venv/bin/ruff check` = clean; `.venv/bin/pytest ... --collect-only` = 46 tests, 0 collection errors; a targeted run FAILS RED with `AttributeError: 'AsyncCursor' object has no attribute 'fetch_record_batch'`.
- **Committed in:** `e16ca20` (Task 2 commit)

**2. [Rule 3 - Blocking] A1 outcome forced a skip-scope, not just a RED-scope, on the Snowflake legs**
- **Found during:** Task 3 (A1 cassette smoke)
- **Issue:** The plan anticipated the Snowflake legs might need `skip`/`xfail` if A1 came back negative. A1 IS negative (the replay cursor has no `fetch_record_batch`), so the Snowflake reader legs can NEVER run offline against the current cassette — even after GREEN they would `AttributeError` in replay. Leaving them merely RED would fail the Task-3 verify (`rc ∈ {0,5}`).
- **Fix:** Added a class-level `pytest.mark.skip` (with an A1 reason) to `TestEdge33Snowflake`, on top of the existing `@pytest.mark.snowflake` recording-only marker, and documented both legs as manual-only re-record follow-ups.
- **Files modified:** `tests/async/test_reader_lifetime.py`; added `tests/async/test_reader_cassette_smoke.py`
- **Verification:** `.venv/bin/pytest tests/async -k "cassette_smoke or (reader_lifetime and snowflake)"` → `1 passed, 4 skipped, 132 deselected`, rc=0.
- **Committed in:** `64cd6cd` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking)
**Impact on plan:** Both were necessary to reconcile the plan's RED-scaffolding intent with the project's strict type gate and the negative A1 outcome. No scope creep — no production code was written (Wave-0 correctly stays RED).

## Issues Encountered
- **Sandboxed `.venv/bin/basedpyright` pre-commit hook panics under the command sandbox** (`uv` → `system-configuration` "Attempted to create a NULL object"), a known project pitfall (MEMORY uv-sandbox-workarounds). All three commits were completed by running the commit outside the command sandbox; the hook then passed (`Type checking (basedpyright)....Passed`). Direct `.venv/bin/basedpyright` invocations for verification all reported 0 errors.
- **Background-shell heuristic + a blocking stub read.** An early Task-1 verification script called `read_next_batch()` synchronously, which correctly blocks forever on the stub's internal event (by design — the worker must be released from another thread); the corrected script drives the pull from a side thread and releases on `entered`. No stub bug.

## Snowflake Cassette A1 — Definitive Record
- **Question (A1):** Can the checked-in Snowflake `snowflake_arrow_round_trip` cassette replay a streaming `fetch_record_batch`?
- **Answer:** **No.** `pytest_adbc_replay._cursor.ReplayCursor` exposes `execute`, `executemany`, `fetch_arrow_table`, `fetchall`, `fetchone`, `fetchmany`, `description`, `rowcount`, `arraysize`, `close` — no `fetch_record_batch`. The cassette (`tests/cassettes/snowflake_arrow_round_trip/adbc_driver_snowflake.dbapi/000_result.arrow`) is a single materialized Arrow result.
- **Consequence:** Snowflake EDGE-33 leg scoped to a manual-only re-record follow-up (skipped in the automated gate); DuckDB EDGE-33 coverage stands alone and is mandatory. `test_reader_cassette_smoke.py` guards the fact — it will fail if a future replay plugin gains streaming support, prompting re-enablement.

## Next Phase Readiness
- Wave-0 RED surface is complete: every Phase-29 requirement is pinned to an automated assertion that currently fails for the right reason (production symbols absent), ready to turn GREEN as plans 02/03 land `_reader.py`, `AsyncCursor.fetch_record_batch`, the `_SyncReader` Protocol, and the `_reader_open` two-tier guard.
- **GREEN-wave cleanup reminder:** delete the file-level pyright pragma block from all six RED test files once the production symbols exist (the strict gate must then pass without suppression), and confirm the `# noqa: SLF001` private-access lines still hold.
- Blocker/constraint carried forward: the Snowflake streaming leg needs a live-credential cassette re-record before it can join the offline gate (tracked as manual-only in 29-VALIDATION).

## Self-Check: PASSED

- All 8 created/modified files verified present on disk.
- All 3 task commits verified in git history (`7652762`, `e16ca20`, `64cd6cd`).

---
*Phase: 29-arrow-streaming*
*Completed: 2026-07-01*
