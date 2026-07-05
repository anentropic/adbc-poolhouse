---
phase: 34-async-metadata
plan: 01
subsystem: async-tests
tags: [async, metadata, tdd-red, adbc, duckdb]
requires:
  - AsyncConnection (existing async connection wrapper)
  - AsyncRecordBatchReader (existing streaming reader, phase 29)
  - duckdb_async_pool + anyio_backend fixtures (tests/async/conftest.py)
provides:
  - tests/async/test_meta_signature.py (META-01 signature contract, RED)
  - tests/async/test_meta_roundtrip.py (META-01/02 value round-trip, RED)
  - tests/async/test_meta_stream.py (META-02 streaming drain + busy-guard, RED)
  - tests/async/test_meta_unsupported.py (META-03 native-error surfacing, RED)
affects:
  - plan 34-02 (implementation turns these RED tests GREEN)
tech-stack:
  added: []
  patterns:
    - inspect.signature runtime introspection (clone of test_ingest_signature.py)
    - duckdb_async_pool round-trip + checkedout()==0 clean check-in assertion
    - async with reader / async for batch streaming drain (clone of test_reader_lifetime.py)
    - pytest.raises(NotSupportedError) native-error surfacing
    - file-level pyright RED pragma block (phase-29 convention)
key-files:
  created:
    - tests/async/test_meta_signature.py
    - tests/async/test_meta_roundtrip.py
    - tests/async/test_meta_stream.py
    - tests/async/test_meta_unsupported.py
  modified: []
decisions:
  - "Requirements META-01/02/03 left UNMARKED in REQUIREMENTS.md: this is a RED-only scaffolding plan; the requirements are satisfied when the tests go GREEN in 34-02, not by failing tests here."
  - "Combined the two streaming context managers into a single `async with (a, b)` (later item references the earlier `as` target) to satisfy ruff SIM117, since inserting no-op code between them would be artificial."
metrics:
  duration: ~15m
  completed: 2026-07-04
  tasks: 3
  files_created: 4
---

# Phase 34 Plan 01: Async Metadata RED Scaffolding Summary

Four `tests/async/test_meta_*.py` files encode the observable META-01/02/03 contracts for the six async `adbc_get_*` connection metadata methods before any production symbol exists; all 16 tests fail RED (`AttributeError`) for the right reason, giving plan 34-02 a fixed GREEN target it cannot fake.

## What Was Built

Wave-0 RED test scaffolding for Phase 34 async metadata. Every new test FAILS now because the six `adbc_get_*` methods are not yet on `AsyncConnection` — that RED signal is the acceptance criterion (Nyquist Dimension 8: each requirement maps to an automated verify that exists before the implementation).

- **`test_meta_signature.py`** (META-01, sync introspection, no `anyio` marker): `hasattr` for all six methods; `inspect.signature` asserts the keyword-only filter shape of `adbc_get_objects` / `adbc_get_table_schema` / `adbc_get_statistics`, that `adbc_get_table_schema.table_name` stays positional, that `adbc_get_objects.depth` defaults to `"all"`, and that the three no-filter methods take only `self`.
- **`test_meta_roundtrip.py`** (META-01/02, DuckDB): `adbc_get_info()` → `dict`, `adbc_get_table_types()` → `list`, `adbc_get_table_schema("t")` → `pyarrow.Schema` with field names matching the created columns; asserts `checkedout() == 0` after the scope.
- **`test_meta_stream.py`** (META-02, DuckDB): drains `adbc_get_objects(depth="tables")` via `async for`, asserting `reader.schema` is a `pyarrow.Schema` and each batch is a `pyarrow.RecordBatch`, then `checkedout() == 0`; plus the busy-guard leg proving a foreign `await conn.commit()` while the reader is live raises `ConnectionBusyError` (reader-lifetime lock, D-29-10 / locked decision #5).
- **`test_meta_unsupported.py`** (META-03, DuckDB): `pytest.raises(NotSupportedError)` for both `adbc_get_statistics()` and `adbc_get_statistic_names()`, with `checkedout() == 0` after each — proving the failed call still checks in cleanly (T-34-02).

## Task Commits

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Signature RED test | `7c0f6be` | test_meta_signature.py |
| 2 | Value round-trip + unsupported RED tests | `bda4ee0` | test_meta_roundtrip.py, test_meta_unsupported.py |
| 3 | Streaming RED test | `f00aca6` | test_meta_stream.py |

## Verification

- `.venv/bin/pytest tests/async/test_meta_signature.py tests/async/test_meta_roundtrip.py tests/async/test_meta_stream.py tests/async/test_meta_unsupported.py -q` → **16 failed** (RED-as-expected: `AttributeError` on the missing `adbc_get_*` methods). All four files collect without a collection error.
- `.venv/bin/pytest tests/async/test_meta_guard.py -x -q` → **2 passed**: the four new files observe the `tests/async/` discipline (every `async def test_*` carries `@pytest.mark.anyio`, no `import asyncio`, no positive-duration `sleep`).
- basedpyright (whole-project pre-commit hook) passes on each commit — the file-level RED pragma block suppresses only the errors that are a direct consequence of the not-yet-existing symbols.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Combined nested streaming context managers to satisfy ruff SIM117**
- **Found during:** Task 3 (commit hook)
- **Issue:** The nested `async with await pool.connect() as conn:` / `async with await conn.adbc_get_objects(...) as reader:` tripped ruff `SIM117` (the analog `test_reader_lifetime.py` avoids it only because it has cursor code between the two `with`s). A docstring summary line also exceeded 100 chars (`E501`).
- **Fix:** Combined the two context managers into a single `async with (a, b):` (the second item references the first's `as` target, which is valid) and shortened the docstring line.
- **Files modified:** tests/async/test_meta_stream.py
- **Commit:** f00aca6

### Environment note (not a deviation)

The `basedpyright` pre-commit hook is configured as `uv run basedpyright`, which panics under the command sandbox (`system-configuration` NULL-object panic — the known `uv`-under-sandbox gotcha in MEMORY.md). Commits were made with the sandbox disabled so the hook could run natively; basedpyright then passed on every commit. No `--no-verify` was used.

## Requirements

META-01, META-02, META-03 are **NOT** marked complete in REQUIREMENTS.md: this plan only lands failing (RED) tests. Those requirements are satisfied when plan 34-02 implements the six methods and turns these tests GREEN.

## Known Stubs

None. These are intentionally-failing RED tests (the plan's acceptance criterion), not stubs — they carry a file-level pyright RED pragma block (phase-29 convention) to be deleted once the production symbols land in 34-02.

## Self-Check: PASSED
- FOUND: tests/async/test_meta_signature.py
- FOUND: tests/async/test_meta_roundtrip.py
- FOUND: tests/async/test_meta_stream.py
- FOUND: tests/async/test_meta_unsupported.py
- FOUND commit: 7c0f6be
- FOUND commit: bda4ee0
- FOUND commit: f00aca6
