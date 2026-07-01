---
phase: 29-arrow-streaming
reviewed: 2026-07-01T00:00:00Z
depth: deep
files_reviewed: 7
files_reviewed_list:
  - src/adbc_poolhouse/_async/_reader.py
  - src/adbc_poolhouse/_async/_cursor.py
  - src/adbc_poolhouse/_async/_connection.py
  - docs/scripts/gen_ref_pages.py
  - tests/_async_harness/stubs.py
  - tests/async/test_reader_close.py
  - tests/async/test_reader_stream.py
  - tests/async/test_reader_cancel.py
  - tests/async/test_reader_busy.py
  - tests/async/test_reader_guard.py
  - tests/async/test_reader_lifetime.py
  - tests/async/test_reader_resource.py
  - tests/async/test_reader_cassette_smoke.py
findings:
  critical: 0
  warning: 3
  info: 0
  total: 3
status: issues
---

# Phase 29: Code Review Report

**Reviewed:** 2026-07-01
**Depth:** deep
**Files Reviewed:** 13
**Status:** issues\_found

## Summary

Phase 29 introduces `AsyncRecordBatchReader`, the two-tier `_reader_open` lifetime guard on `AsyncConnection`, and the full per-batch offload / shielded-close pipeline. The production implementation — `_reader.py`, the `fetch_record_batch` method in `_cursor.py`, and the `_reader_open` additions to `_connection.py` — is sound across all the headline risk areas. No use-after-free path, no pool leak on cancel, no `StopIteration` escape, no reentrancy deadlock, no premature `_reader_open` clear, and `__del__` is correctly warn-only. The design decisions in D-29-05 through D-29-16 are correctly implemented.

Three findings affect the test suite: two render specific test assertions vacuous (the tests pass but prove nothing), and one is a recurring test hygiene issue around unclosed readers in cancel tests. None affect the production code path.

## Critical Issues

No critical issues found.

## Warnings

### WR-01: EDGE-20 test patches a fresh stub reader, not the one wrapped by `reader`

**File:** `tests/async/test_reader_close.py:112`

**Issue:** The EDGE-20 test asserts that when the shielded `close()` raises, `_reader_open` is still cleared and the body error is reachable via `__context__`. The intent is correct, but the mechanism fails silently. Line 112:

```python
stub_conn.cursors[-1].fetch_record_batch().close = _raising_close
```

`BlockingStubCursor.fetch_record_batch()` always creates a **new** `BlockingStubReader` and appends it to `_readers`. The reader already wrapped inside the `AsyncRecordBatchReader` (`reader._reader`) is `_readers[0]`; the object returned by this second call is `_readers[1]`. Patching `_readers[1].close` leaves `_readers[0].close` — the one actually called by `offload(self._reader.close, ...)` — untouched. The test body raises `_BodyBoom`, the real close succeeds silently, and `_reader_open` is cleared normally. The test GREEN-passes, but it proves only the body-raises-alone path, not the close-raises path the EDGE-20 contract requires.

**Fix:** Patch the reader already wrapped by `reader`, not a fresh one:

```python
# Replace line 112 with:
reader._reader.close = _raising_close  # type: ignore[method-assign]
# or equivalently:
stub_conn.cursors[-1]._readers[0].close = _raising_close  # type: ignore[method-assign]
```

With this change the offloaded `close()` will actually raise `_CloseBoom`, and the assertion that `_reader_open` is cleared and `_BodyBoom` is reachable via `__context__` will be a genuine proof of the EDGE-20 guarantee.

---

### WR-02: STREAM-02 stub leg asserts on a fresh, unread reader — vacuous assertion

**File:** `tests/async/test_reader_stream.py:142-143`

**Issue:** `test_stub_pull_recorded_on_worker_thread` is meant to prove that every `read_next_batch` call ran on a worker thread (the STREAM-02 off-loop guarantee). After draining the reader via `async for`, it does:

```python
stub_reader = stub_cursor.fetch_record_batch()   # line 142
assert all(tid != loop_thread_id for tid in stub_reader.read_thread_ids)  # line 143
```

Again `stub_cursor.fetch_record_batch()` creates a **new** `BlockingStubReader` — one that has never been read. Its `read_thread_ids` is `[]`. The assertion `all(... for ... in [])` is vacuously `True` by Python semantics. The test passes unconditionally, regardless of which thread the pulls actually ran on. The comment `# a fresh reader exposes the contract` is misleading and apparently reflects the intention to access the original reader, not create a new one.

**Fix:** Access `read_thread_ids` from the reader that was actually used:

```python
# Option A: reach through the internal attribute (test-internal access)
assert all(tid != loop_thread_id for tid in reader._reader.read_thread_ids)

# Option B: access via the retained readers list
assert all(tid != loop_thread_id for tid in stub_conn.cursors[-1]._readers[0].read_thread_ids)
```

Either form will contain the real worker thread ids from the `async for` drain and make the assertion non-trivial.

---

### WR-03: Cancel and lifetime tests leave readers unclosed, emitting latent `ResourceWarning`

**Files:** `tests/async/test_reader_cancel.py` (lines 233–253, 268–290, 313–323), `tests/async/test_reader_lifetime.py` (lines 107–129, 130–158)

**Issue:** Several tests create readers, use them, and then exit without calling `reader.close()`. By design, `AsyncRecordBatchReader.__del__` emits `ResourceWarning` for every unclosed instance. Affected tests include:

- `test_cancel_during_pull_aborts_and_invalidates` and `test_timeout_during_pull_aborts_and_invalidates`: `reader` is created before the task group and never explicitly closed after the cancel path runs. On test function return, `__del__` fires.
- `test_invalidate_drains_pool_duckdb`: `reader` is created, `__anext__` called once, `invalidate()` called, but `reader.close()` is never called.
- `test_read_after_close_raises_arrow_invalid_duckdb` and `test_read_after_checkin_raises_arrow_invalid_duckdb` in the lifetime suite: deliberately skip the explicit close to test the post-close/post-checkin behavior, so `__del__` fires as a side effect.

Currently `ResourceWarning` is not converted to an error (no `filterwarnings` in `pyproject.toml` or any conftest), so the tests pass. If a future `filterwarnings = ["error::ResourceWarning"]` is added (common in strict CI), every one of these tests will fail with an unexpected `ResourceWarning` rather than the intended assertion error.

**Fix:** After cancel/invalidate, set the detached flag or call a no-raise close to silence the finalizer. For the cancel tests where the connection is already invalidated, the safest approach is:

```python
# After the cancel scope exits and assertions are checked:
reader._detached = True   # suppress the ResourceWarning; pool already cleaned up

# Or for the invalidate test where close() is safe after invalidate():
await reader.close()      # idempotent; safe after connection.invalidate()
```

For the "read-after" tests where the intent is to show behavior on an unclosed reader, the `ResourceWarning` is a correct side effect of the test scenario. These can be explicitly expected:

```python
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore", ResourceWarning)
    async with await duckdb_async_pool.connect() as conn:
        ...
```

---

_Reviewed: 2026-07-01_
_Reviewer: Claude (adversarial code review)_
_Depth: deep_
