---
phase: 30-async-bulk-write
reviewed: 2026-07-01T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - src/adbc_poolhouse/_async/_cursor.py
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 30: Code Review Report

**Reviewed:** 2026-07-01
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

Reviewed `src/adbc_poolhouse/_async/_cursor.py` for the Phase 30 `AsyncCursor.adbc_ingest` addition. The implementation is structurally sound: it is a near-exact clone of `fetch_arrow_table` with the correct offload shape (`_offloading()` guard, `cancellable_offload` with `self._adbc_cancel` as first arg and `functools.partial` as second, `on_abort=self._owner.invalidate`). Cancel-safety is intact — `self._adbc_cancel` is a distinct bound method not captured in the partial, so `cancellable_offload` fires it independently on abort. No `_reader_open` lifetime lock is taken (correct for a whole-op offload). `Literal`/`CapsuleType` under `TYPE_CHECKING` with `from __future__ import annotations` is safe. No exception swallowing or wrapping. The `functools.partial` binds all four positional/keyword args into a zero-arg callable, so the empty `*args` tuple passed to `cancellable_offload` is correct.

One warning (stale module docstring) and two info-level observations (example comment ambiguity, `Literal` ordering inconsistency between the Protocol stub and the public method).

## Warnings

### WR-01: Module docstring enumerates offloaded methods but omits `adbc_ingest`

**File:** `src/adbc_poolhouse/_async/_cursor.py:5-6`

**Issue:** The module-level docstring lists the complete set of offloaded blocking calls: `` `execute`, `executemany`, `fetchone`, `fetchmany`, `fetchall`, `fetch_arrow_table`, `close` ``. Phase 30 added `adbc_ingest` as a further offloaded method. The module docstring now presents an incomplete picture of the async surface to any reader who relies on it as an authoritative list.

**Fix:** Add `adbc_ingest` to the enumerated list on line 6:

```python
"""
The async cursor wrapper: offloaded DBAPI surface, materialized Arrow, sync props.

[`AsyncCursor`][adbc_poolhouse._async._cursor.AsyncCursor] wraps a single sync
ADBC dbapi cursor and offloads every blocking call --- `execute`, `executemany`,
`fetchone`, `fetchmany`, `fetchall`, `fetch_arrow_table`, `adbc_ingest`, `close`
--- through the owning pool's limiter. ...
"""
```

## Info

### IN-01: Docstring example comment conflates return value with table total

**File:** `src/adbc_poolhouse/_async/_cursor.py:438`

**Issue:** The inline comment on the second `adbc_ingest` call reads `# 3, now 6 total`. The return value of that call is `3` (rows written in the second call), not `6`. The `# now 6 total` is an aside about the table state, not the return value. A reader skimming the example could misread it as the method returning `6`.

**Fix:** Split the comment to make the return value unambiguous:

```python
await cursor.adbc_ingest("people", people, mode="append")  # returns 3 (6 rows total now)
```

### IN-02: `Literal` mode ordering differs between `_SyncCursor` Protocol stub and `AsyncCursor`

**File:** `src/adbc_poolhouse/_async/_cursor.py:82` vs `375`

**Issue:** `_SyncCursor.adbc_ingest` lists `mode` as `Literal["append", "create", "replace", "create_append"]` (alphabetical-ish order), while `AsyncCursor.adbc_ingest` lists it as `Literal["create", "append", "replace", "create_append"]` (default-first order). Semantically identical (`Literal` is an unordered set of string values), but inconsistent on visual inspection.

**Fix:** Align both to the same order — prefer the public-API order (`"create"` first, matching the default):

```python
# _SyncCursor.adbc_ingest (line 82)
mode: Literal["create", "append", "replace", "create_append"] = ...,
```

---

_Reviewed: 2026-07-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
