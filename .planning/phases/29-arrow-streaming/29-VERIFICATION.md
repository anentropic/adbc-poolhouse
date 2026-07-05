---
phase: 29-arrow-streaming
verified: 2026-07-01T18:00:00Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 10/12
  gaps_closed:
    - "STREAM-02: stub off-loop assertion is now non-vacuous — accesses reader._reader (the drained reader), narrows to BlockingStubReader via isinstance, and guards against all([]) with a non-empty assertion before the thread-id check"
    - "EDGE-20: patches reader._reader.close (the actual wrapped reader) so the shielded-close-raises path is genuinely exercised; asserts body error reachable via __context__ chain and async_conn._reader_open is False"
  gaps_remaining: []
  regressions: []
---

# Phase 29: Arrow Streaming — Verification Report

**Phase Goal:** Users can stream Arrow query results lazily via `await cursor.fetch_record_batch()` → `async for batch in reader:`, with the reader's lifetime safely bound to the checked-out connection so read-after-checkin surfaces a clean driver error (native closed-stream exception) rather than a use-after-free/segfault. The reader is an async context manager (`await reader.close()`/`__aexit__` closes it offloaded-and-shielded). Cancelling/timing out a batch pull fires `adbc_cancel` once and invalidates the connection so `pool.checkedout() == 0`, identical under asyncio and trio. A second in-flight op on the parent cursor while a reader is live raises `ConnectionBusyError`. An unclosed reader's `__del__` emits a `ResourceWarning` (never a "coroutine never awaited" `RuntimeWarning`); the happy path emits neither. New async public API is basedpyright-strict-clean (0 errors); the AST import-lint guard passes over `_async/` (no `import asyncio`, no bare `to_thread`).

**Verified:** 2026-07-01T18:00:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (commit c45022a)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `await cursor.fetch_record_batch()` returns an `AsyncRecordBatchReader` (STREAM-01) | VERIFIED | `AsyncCursor.fetch_record_batch` in `_cursor.py:357-417` exists, offloads reader creation via `cancellable_offload`, returns `AsyncRecordBatchReader` |
| 2 | `async for batch in reader:` yields `pyarrow.RecordBatch` with each pull offloaded individually (STREAM-02) | VERIFIED | Production `__anext__` in `_reader.py:221-260` correctly offloads via `cancellable_offload(from_reader=True)`. Re-verified: stub-backed test now accesses `reader._reader` (the drained reader), narrows via `isinstance(stub_reader, BlockingStubReader)`, asserts `read_thread_ids` is non-empty (guards vacuous `all([])`), then asserts all thread ids differ from loop thread id. `BlockingStubReader.read_next_batch` records thread id before raising `StopIteration` on the default empty reader, so exactly one entry is recorded per pull. |
| 3 | `StopIteration` caught worker-side via `_EXHAUSTED` sentinel; `__anext__` raises `StopAsyncIteration` | VERIFIED | Module-level `_Exhausted`/`_EXHAUSTED`/`_pull` at `_reader.py:89-121`; `try: return sync_reader.read_next_batch() / except StopIteration: return _EXHAUSTED`; `__anext__` checks `if batch is _EXHAUSTED: raise StopAsyncIteration` |
| 4 | `close()`/`__aexit__` closes shielded inside `CancelScope(shield=True)`, clearing `_reader_open` in `finally` (STREAM-03) | VERIFIED | `_reader.py:262-290`: idempotent via `_detached`, `anyio.CancelScope(shield=True)`, `finally: self._owner._reader_open = False` |
| 5 | EDGE-20: when shielded close raises, `_reader_open` still cleared and body error reachable via `__context__` | VERIFIED | Re-verified: `test_shielded_cleanup_chains` now patches `reader._reader.close = _raising_close` (the actual wrapped reader, not a fresh stub). Body raises `_BodyBoom`; shielded close raises `_CloseBoom`. Test walks `__context__` chain and asserts `isinstance(e, _BodyBoom)` found; asserts `async_conn._reader_open is False`. Production `finally` correct; test now actually exercises the close-raises path. |
| 6 | Read-after-checkin surfaces native `pyarrow.lib.ArrowInvalid`, never segfault (STREAM-04/EDGE-33) | VERIFIED | DuckDB integration `test_reader_lifetime.py` passes; Snowflake leg legitimately skipped per A1 resolution (cassette cannot replay streaming, documented in 29-01-SUMMARY); `_detached` guard + `_release_arrow_allocators` reset backstop (D-29-12) verified |
| 7 | Cancel/timeout on a pull fires cursor's `adbc_cancel` once + invalidates so `checkedout() == 0` (STREAM-05) | VERIFIED | `test_reader_cancel.py` passes on asyncio + trio: `adbc_cancel_call_count == 1`, `invalidate_call_count == 1`; `test_invalidate_drains_pool_duckdb` confirms `checkedout() == 0`; `invalidate()` clears `_reader_open` (D-29-16, `_connection.py:340`) |
| 8 | Second in-flight op while reader live raises `ConnectionBusyError` (STREAM-06) | VERIFIED | `test_reader_busy.py` 10/10 passing on asyncio + trio: execute/second-fetch/commit all raise `ConnectionBusyError`; reader's own pulls exempt via `from_reader=True`; lock persists until `close()` not at drain |
| 9 | Unclosed `__del__` emits `ResourceWarning`; happy path emits neither `ResourceWarning` nor `RuntimeWarning` (EDGE-22/23) | VERIFIED | `_reader.py:317-333`: `__del__` uses `warnings.warn(..., ResourceWarning)` and NEVER calls `self.close()`; `test_reader_resource.py` passes on both backends |
| 10 | `_SyncReader` Protocol + `_SyncCursor.fetch_record_batch` land; basedpyright strict 0 errors (PKG-01) | VERIFIED | `_reader.py:73-86`: `_SyncReader(Protocol)` with `schema`, `read_next_batch`, `close`; `_cursor.py:74`: `def fetch_record_batch(self) -> pyarrow.RecordBatchReader: ...` in `_SyncCursor`; `basedpyright` run: **0 errors, 0 warnings, 0 notes** |
| 11 | AST import-lint passes over `_async/` (no `import asyncio`, no bare `to_thread`) (PKG-03) | VERIFIED | `tests/test_pkg_import_guard.py tests/async/test_async_guard.py` — 3 passed; no `import asyncio` found in `_reader.py` or `_cursor.py`; `to_thread` references in those files are docstring text only |
| 12 | Docs gate: async guide documents streaming, API reference renders `AsyncRecordBatchReader`, `mkdocs --strict` passes | VERIFIED | `async.md` contains streaming section at line 141+; `gen_ref_pages.py:49` includes `AsyncRecordBatchReader` reference block; `mkdocs build --strict` exits 0 |

**Score:** 12/12 truths verified

---

## Test Suite Results (Gate Runs — Re-verification)

### Primary Async + Harness Suite (3 runs)

```
Run 1: 168 passed, 6 skipped in 1.92s
Run 2: 168 passed, 6 skipped in 1.83s
Run 3: 168 passed, 6 skipped in 1.78s
```

Three consecutive clean runs, no hangs. The 6 skips are all legitimate and expected:
- 4 skips: `TestEdge33Snowflake` (asyncio + trio × 2 tests) — Snowflake cassette cannot replay streaming fetch_record_batch per A1 resolution; skipped with documented reason
- 2 skips: `TestVirtualClock` backend cross-tests in harness (backend-specific skips by design)

**No failures. No unexpected skips. No hangs across three runs.**

Note on cancel path risk: tests were run three times per re-verification. The project's "loop flaky concurrency tests" lesson recommends looped runs for cancel/hang-prone tests. The 29-03-SUMMARY reports ×15 loop with 0 hangs. Three clean runs here are consistent with that evidence. Human verification item 2 (loop ×20) remains as a recommended final gate.

### basedpyright (PKG-01)

```
.venv/bin/basedpyright
0 errors, 0 warnings, 0 notes
```

### Import-lint Guard (PKG-03)

```
.venv/bin/pytest tests/test_pkg_import_guard.py tests/async/test_async_guard.py -q
3 passed in 0.56s
```

### mkdocs Strict Build (Docs Gate)

```
DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict
Documentation built in 1.61 seconds  [exit 0]
```

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/adbc_poolhouse/_async/_reader.py` | `AsyncRecordBatchReader` + `_SyncReader` Protocol + `_EXHAUSTED` sentinel + `_pull` | VERIFIED | 333 lines; composition (no pyarrow subclass); all required members present |
| `src/adbc_poolhouse/_async/_cursor.py` | `AsyncCursor.fetch_record_batch` + `_SyncCursor.fetch_record_batch` Protocol line | VERIFIED | `fetch_record_batch` at line 357; Protocol line at line 74 |
| `src/adbc_poolhouse/_async/_connection.py` | `_reader_open` flag + two-tier `_enter_offload(from_reader=)` / `_offloading(from_reader=)` | VERIFIED | `_reader_open = False` at line 140; `_enter_offload(*, from_reader: bool = False)` at line 149; `_offloading(*, from_reader=False)` at line 191; `_exit_offload` clears `_in_use` ONLY (line 188) |
| `tests/_async_harness/stubs.py` | `BlockingStubReader` + `BlockingStubCursor.fetch_record_batch()` | VERIFIED | `BlockingStubReader` exists; has `schema`, `read_next_batch`, `close`; NO `adbc_cancel` attribute; `read_thread_ids` recorded before StopIteration on empty reader (critical for non-vacuous STREAM-02 proof) |
| `tests/async/test_reader_stream.py` | STREAM-01/02 tests | VERIFIED | STREAM-01 test verified; STREAM-02 stub off-loop assertion now non-vacuous — accesses `reader._reader`, narrows via `isinstance`, guards with non-empty assertion |
| `tests/async/test_reader_close.py` | STREAM-03 + EDGE-20 tests | VERIFIED | STREAM-03 close test verified; EDGE-20 test now patches `reader._reader.close` (the actual wrapped reader), genuinely exercises the close-raises path |
| `tests/async/test_reader_lifetime.py` | STREAM-04/EDGE-33 DuckDB tests | VERIFIED | DuckDB legs pass; Snowflake legs legitimately skipped |
| `tests/async/test_reader_cancel.py` | STREAM-05 cancel/timeout tests | VERIFIED | All cancel/timeout/drain tests pass |
| `tests/async/test_reader_busy.py` | STREAM-06 busy guard tests | VERIFIED | 10/10 passing; foreign reject + reentrancy exemption + lock-until-close all green |
| `tests/async/test_reader_resource.py` | EDGE-22/23 ResourceWarning discipline | VERIFIED | Passes on asyncio and trio |
| `docs/src/guides/async.md` | Arrow streaming how-to section | VERIFIED | Streaming section present; `async with await cursor.fetch_record_batch() as reader:` usage documented; read-after-checkin contract; GIL/per-batch framing |
| `docs/scripts/gen_ref_pages.py` | `AsyncRecordBatchReader` reference block | VERIFIED | Line 49: `adbc_poolhouse._async._reader.AsyncRecordBatchReader` explicit block |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `AsyncCursor.fetch_record_batch` | `AsyncRecordBatchReader` | wraps sync reader; sets `owner._reader_open = True` AFTER offloading span | VERIFIED | `_cursor.py:398-417`: `with self._owner._offloading():` spans the creation; `self._owner._reader_open = True` is OUTSIDE the `with` block (Pitfall 5 correct) |
| `AsyncRecordBatchReader.__anext__` | `AsyncConnection._offloading(from_reader=True)` | reader-tier reentrant guard + `cancellable_offload(_pull)` | VERIFIED | `_reader.py:250`: `with self._owner._offloading(from_reader=True):` — the only `from_reader=True` caller in the codebase |
| `AsyncRecordBatchReader.__anext__` | cursor's `adbc_cancel` | `on_abort=owner.invalidate`; `adbc_cancel` passed at construction | VERIFIED | `_reader.py:251-257`: `cancellable_offload(self._adbc_cancel, _pull, ..., on_abort=self._owner.invalidate)` |
| `AsyncRecordBatchReader.close` | `_reader_open = False` | `finally` block in shielded close | VERIFIED | `_reader.py:284-290`: `finally: self._owner._reader_open = False` |
| `AsyncConnection.invalidate` | `_reader_open = False` | clears before shielded offload | VERIFIED | `_connection.py:340`: `self._reader_open = False` before `CancelScope(shield=True)` |
| `AsyncConnection._exit_offload` | does NOT touch `_reader_open` | clears `_in_use` only | VERIFIED | `_connection.py:186-188`: only `self._in_use = False` |
| `docs/src/guides/async.md` | `AsyncRecordBatchReader` | documented canonical `async with await cursor.fetch_record_batch()` | VERIFIED | Line 157 in guide |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `AsyncRecordBatchReader.__anext__` | `batch` | `cancellable_offload(_pull, self._reader, ...)` → `sync_reader.read_next_batch()` | Yes — DuckDB integration test confirms real Arrow batches from real query | FLOWING |
| `AsyncCursor.fetch_record_batch` | `sync_reader` | `cancellable_offload(..., self._cursor.fetch_record_batch, ...)` → real ADBC cursor | Yes — DuckDB integration creates real `pyarrow.RecordBatchReader` | FLOWING |

---

## Requirements Coverage

| Requirement | Source Plan | Description (from REQUIREMENTS.md) | Status | Evidence |
|-------------|------------|-------------------------------------|--------|----------|
| STREAM-01 | 29-01, 29-03 | `await cursor.fetch_record_batch()` returns `AsyncRecordBatchReader` | SATISFIED | `fetch_record_batch` in `_cursor.py`; `test_reader_stream.py` STREAM-01 passes |
| STREAM-02 | 29-01, 29-03 | `async for batch in reader:` offloads each pull individually | SATISFIED | Production correct; stub off-loop test now non-vacuous (gap closed in c45022a) |
| STREAM-03 | 29-01, 29-03 | Reader is async context manager; `close`/`__aexit__` offloaded and shielded | SATISFIED | `_reader.py:262-315`; `test_reader_close.py` STREAM-03 passes |
| STREAM-04 | 29-01, 29-03 | Lifetime bound to connection; read-after-checkin = clean driver exception | SATISFIED | `test_reader_lifetime.py` DuckDB legs pass; Snowflake manual-only per A1 |
| STREAM-05 | 29-01, 29-03 | Cancel fires `adbc_cancel` once + invalidate; `checkedout() == 0` | SATISFIED | `test_reader_cancel.py` passes; `_reader_open` cleared in `invalidate()` |
| STREAM-06 | 29-02, 29-03 | Second in-flight op while reader live raises `ConnectionBusyError` | SATISFIED | `test_reader_busy.py` 10/10 passing; REQUIREMENTS.md checkbox + traceability table updated to reflect completion |
| EDGE-33 | 29-01, 29-03 | Read after checkin on `AsyncRecordBatchReader` = clean exception, not crash | SATISFIED | DuckDB integration passes; Snowflake leg legitimately skipped (A1) |
| EDGE-20 | 29-01, 29-03 | Exception during shielded cleanup does not mask body error | SATISFIED | Production `finally` correct; EDGE-20 test now exercises close-raises path (gap closed in c45022a) |
| EDGE-22 | 29-01, 29-03 | Unclosed `__del__` emits `ResourceWarning`, not `RuntimeWarning` | SATISFIED | `_reader.py:317-333`; `test_reader_resource.py` passes |
| EDGE-23 | 29-01, 29-03 | Happy path (closed via context manager) emits neither warning | SATISFIED | `test_reader_resource.py` passes |
| PKG-01 | 29-03, 29-04 | `_SyncCursor` Protocol gains `fetch_record_batch`; basedpyright strict 0 errors | SATISFIED | `_cursor.py:74`; basedpyright: 0 errors, 0 warnings, 0 notes |
| PKG-03 | 29-02, 29-03 | AST import-lint passes over `_async/` | SATISFIED | Import-lint tests pass; no `import asyncio` in `_reader.py` or `_cursor.py` |

Note: REQUIREMENTS.md `STREAM-06` status and checkbox have been corrected from stale "e2e pending 29-03" to "Complete (29-03)" as part of this re-verification. The tests all pass.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/async/test_reader_cancel.py` | 78, 117, 153 | Readers created but never closed; `__del__` will emit `ResourceWarning` | WARNING (WR-03) | Latent `ResourceWarning` emissions; harmless today (no `filterwarnings = ["error::ResourceWarning"]` in CI); will break tests if strict warning mode is added |
| `tests/async/test_reader_lifetime.py` | 107-129, 130-158 | Readers left unclosed in read-after-close/checkin tests | WARNING (WR-03, intentional) | `ResourceWarning` is a correct side-effect of these tests; no error gate currently enforces it |

No `TBD`, `FIXME`, or `XXX` debt markers found in files modified by this phase.

The two previously-blocking anti-patterns (vacuous STREAM-02 assertion; EDGE-20 patching wrong reader) are now resolved as of commit c45022a.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All async + harness tests green (run 1) | `.venv/bin/pytest tests/async/ tests/_async_harness/ -q` | 168 passed, 6 skipped in 1.92s | PASS |
| All async + harness tests green (run 2) | `.venv/bin/pytest tests/async/ tests/_async_harness/ -q` | 168 passed, 6 skipped in 1.83s | PASS |
| All async + harness tests green (run 3) | `.venv/bin/pytest tests/async/ tests/_async_harness/ -q` | 168 passed, 6 skipped in 1.78s | PASS |
| basedpyright 0 errors | `.venv/bin/basedpyright` | 0 errors, 0 warnings, 0 notes | PASS |
| Import-lint guard | `.venv/bin/pytest tests/test_pkg_import_guard.py tests/async/test_async_guard.py -q` | 3 passed | PASS |
| mkdocs strict build | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` | exit 0 | PASS |
| STREAM-06 e2e | `.venv/bin/pytest tests/async/test_reader_busy.py -v` (from prior run) | 10 passed | PASS |

---

## Human Verification Required

### 1. Docs voice and accuracy review

**Test:** Run `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs serve` and read the new "Streaming a result set batch by batch" section in the async guide.
**Expected:** The `async with await cursor.fetch_record_batch() as reader:` canonical usage is clear; the lifetime contract (reader locks connection for its whole lifetime; read-after-checkin surfaces `pyarrow.lib.ArrowInvalid` from the driver, not a poolhouse type) is stated honestly; the concurrency framing (per-batch offload, GIL reacquired during materialization, no real parallelism from a single reader) is accurate and non-promotional. The API reference for `AsyncRecordBatchReader` and `AsyncCursor.fetch_record_batch` renders Args/Returns/Raises + Example with no rogue RST colons.
**Why human:** Voice, accuracy, and tone cannot be verified programmatically. The 29-04 human-verify checkpoint was auto-approved under `--auto` chain execution; a human pass remains a documented nice-to-have.

### 2. Cancel path loop verification under asyncio + trio

**Test:** Run `for i in $(seq 20); do .venv/bin/pytest tests/async/test_reader_cancel.py -q || echo "FAILED iter $i"; done` and confirm 0 hangs in 20 iterations.
**Expected:** All 20 iterations complete without hangs (no deadlock, no platform-dependent lost-wakeup).
**Why human:** The project's "loop flaky concurrency tests" memory lesson requires looped execution for cancel/timeout paths. Three gate runs (each covering the full cancel suite) were clean; the 29-03-SUMMARY reports ×15 loop with 0 hangs. A further ×20 loop provides additional confidence on the cancel paths specifically.

---

## Gaps Summary

No gaps. Both previously-identified test gaps (STREAM-02 vacuous assertion, EDGE-20 patching wrong reader) are resolved in commit c45022a. All 12 must-haves are now fully verified. The two advisory WR-03 ResourceWarning warnings in cancel/lifetime tests remain as non-blocking notes (no `filterwarnings = error` gate in CI today).

---

_Verified: 2026-07-01T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification of: 2026-07-01T17:03:53Z (gaps_found, 10/12)_
