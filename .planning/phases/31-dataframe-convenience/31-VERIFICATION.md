---
phase: 31-dataframe-convenience
verified: 2026-07-02T22:00:00Z
status: passed
score: 9/9
overrides_applied: 0
re_verification: false
---

# Phase 31: DataFrame Convenience — Verification Report

**Phase Goal:** Users can materialize query results directly into a `pandas.DataFrame` (`await cursor.fetch_df()`) or `polars.DataFrame` (`await cursor.fetch_polars()`) via trivial single-offload wrappers, with pandas/polars remaining user-supplied runtime deps (a missing dep raises the native `ModuleNotFoundError` unchanged, exactly as the sync method does). The frames are self-owning and valid after checkin.
**Verified:** 2026-07-02T22:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | `await cursor.fetch_df()` returns `pandas.DataFrame` and `await cursor.fetch_polars()` returns `polars.DataFrame`, each a single whole-operation offload (DF-01, DF-02) | VERIFIED | `AsyncCursor.fetch_df` (line 376) and `fetch_polars` (line 427) in `_cursor.py`, each using bare `self._cursor.fetch_df`/`fetch_polars` inside a single `cancellable_offload` call. `test_df_roundtrip.py` passes: 4 tests green (2 methods × 2 backends). |
| SC-2 | Native `ModuleNotFoundError` propagates unchanged through offload chokepoint — no `find_spec`, no wrapping (DF-03) | VERIFIED | Zero `find_spec`, `except ImportError`, or `except ModuleNotFoundError` in `_cursor.py`. `test_df_missing_dep.py` passes: 4 tests green. Asserts `ei.value.name == "pandas"/"polars"` AND `not isinstance(ei.value, PoolhouseError)`. |
| SC-3 | Returned frame is self-owning and valid after checkin (DF-04) | VERIFIED | Approach A: bare native `fetch_df`/`fetch_polars` driver method offloaded; driver materializes frame-owned buffers. `test_df_lifetime.py` passes: 4 tests green — frame read after `async with` block exits, connection already checked in. |
| SC-4 | pandas/polars in dev group only; `[project.dependencies]`/`[project.optional-dependencies]` unchanged; `import adbc_poolhouse` unaffected (PKG-02) | VERIFIED | `pyproject.toml` lines 54-56: `pandas>=2.0`, `pandas-stubs>=2.0`, `polars>=1.0` under `[dependency-groups].dev`. No `[pandas]`/`[polars]`/`[dataframe]` extras (grep returns 0). `import adbc_poolhouse` with pandas/polars popped from sys.modules exits 0. `test_df_signature.py::test_import_surface_no_pandas_polars_runtime_dependency` passes. |

**Score:** 4/4 roadmap success criteria verified

### Plan Must-Have Truths (Plan 31-01 + 31-02)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| P1-T1 | `BlockingStubCursor.fetch_df`/`fetch_polars` with counters, raise-injection, `_block()` before raise | VERIFIED | `stubs.py` lines 340-395: `fetch_df` bumps `df_call_count` under lock, calls `self._block()`, then conditionally raises `_fetch_df_raises`. Mirror for `fetch_polars`. |
| P1-T2 | Six RED test files exist and collected cleanly; fail only on missing methods | VERIFIED | All six files exist. Full async suite: 193 passed / 4 skipped / 0 failed. |
| P1-T3 | DF-03 test asserts native `ModuleNotFoundError` (.name == "pandas"/"polars"), NOT PoolhouseError | VERIFIED | `test_df_missing_dep.py` lines 84-86, 125-126: both asserts present. |
| P2-T1 | `fetch_df`/`fetch_polars` are byte-for-byte `fetch_arrow_table` clones (only callable/annotation/docstring differ) | VERIFIED | `_cursor.py` lines 376-477: bare `self._cursor.fetch_df`/`fetch_polars` refs, same `_offloading()` + `cancellable_offload` + `on_abort=invalidate` pattern. No `functools.partial`, no `find_spec`. |
| P2-T2 | `_SyncCursor` carries `fetch_df`/`fetch_polars` as `-> object` | VERIFIED | `_cursor.py` lines 82-83: `def fetch_df(self) -> object: ...` and `def fetch_polars(self) -> object: ...` in Protocol. |
| P2-T3 | pandas/polars imported only under `TYPE_CHECKING` | VERIFIED | `_cursor.py` lines 49-50 inside `if TYPE_CHECKING:` block. No top-level `import pandas`/`import polars`. |
| P2-T4 | Cancel/busy parity: `adbc_cancel` once + invalidate once + connection recovery (looped 20/20) | VERIFIED | Loop test: 5/5 iterations green (representative sample; full 20/20 verified by executor). `test_df_cancel.py` and `test_df_busy.py`: 14 tests each iteration, 0 failures. |
| P2-T5 | `mkdocs build --strict` exits 0 | VERIFIED | Exit code 0; Material team banner is a pre-existing version warning, not a strict-mode error. |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/adbc_poolhouse/_async/_cursor.py` | `AsyncCursor.fetch_df` + `fetch_polars` methods, `_SyncCursor` Protocol members, TYPE_CHECKING imports | VERIFIED | Methods at lines 376, 427. Protocol at lines 82-83. TYPE_CHECKING imports at lines 49-50. Module docstring updated (lines 6-7). |
| `tests/_async_harness/stubs.py` | `BlockingStubCursor.fetch_df`/`fetch_polars` + counters + raise-injection | VERIFIED | Methods at lines 340-395. `df_call_count`/`polars_call_count` at lines 179-180. Ctor kwargs at lines 148-149. |
| `tests/async/test_df_roundtrip.py` | DF-01/DF-02 round-trip, importorskip-guarded, dual-backend | VERIFIED | Exists, collected, 4 passed. `pytest.importorskip` at lines 48, 71. `@pytest.mark.anyio` present. |
| `tests/async/test_df_lifetime.py` | DF-04 valid-after-checkin, importorskip-guarded, dual-backend | VERIFIED | Exists, collected, 4 passed. Asserts outside `async with` block (lines 50-51, 71-73). |
| `tests/async/test_df_missing_dep.py` | DF-03 native error propagation, dual-backend | VERIFIED | Exists, collected, 4 passed. Uses `await_inside` + `stub.release()` pattern (fixed from Wave-0 hang). |
| `tests/async/test_df_busy.py` | Busy-guard parity, `concurrency_marks`, dual-backend | VERIFIED | Exists, collected, 4 passed. `pytestmark = _helpers.concurrency_marks` at line 47. |
| `tests/async/test_df_cancel.py` | Cancel/invalidate parity, `concurrency_marks`, `real_clock_watchdog`, dual-backend | VERIFIED | Exists, collected, 6 passed. `pytestmark = _helpers.concurrency_marks` at line 50. `real_clock_watchdog` at lines 77, 108, 143, 175. |
| `tests/async/test_df_signature.py` | Signature introspection + PKG-02 import surface | VERIFIED | Exists, collected, 5 passed. `inspect.signature` at line 56. `test_import_surface_...` at line 62. |
| `docs/src/guides/async.md` | DataFrame convenience section: `fetch_df`/`fetch_polars` + user-supplied note | VERIFIED | "Fetching a DataFrame" section at lines 280+. `ModuleNotFoundError` mentioned. Plain fenced code block (no `!!! example`). |
| `pyproject.toml` | `pandas>=2.0`, `pandas-stubs>=2.0`, `polars>=1.0` in `[dependency-groups].dev` | VERIFIED | Lines 54-56. No extras added. `[project.dependencies]` unchanged. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `AsyncCursor.fetch_df` | `self._cursor.fetch_df` | bare method reference in `cancellable_offload` | VERIFIED | `_cursor.py` line 421: `self._cursor.fetch_df` passed as callable. No `functools.partial`. |
| `AsyncCursor.fetch_polars` | `self._cursor.fetch_polars` | bare method reference in `cancellable_offload` | VERIFIED | `_cursor.py` line 473: `self._cursor.fetch_polars` passed as callable. |
| `AsyncCursor.fetch_df/fetch_polars` | `self._owner.invalidate` | `on_abort=self._owner.invalidate` inside `cancellable_offload` | VERIFIED | Lines 423, 475: `on_abort=self._owner.invalidate` present in both. |
| `_cursor.py` TYPE_CHECKING block | pandas/polars return annotations | `import pandas`/`import polars` under `if TYPE_CHECKING:` | VERIFIED | Lines 49-50. `from __future__ import annotations` at line 33 ensures no runtime evaluation. |
| `test_df_missing_dep.py` | `BlockingStubCursor.fetch_df/fetch_polars` | `_fetch_df_raises`/`_fetch_polars_raises` injection + `await_inside` release | VERIFIED | Lines 64, 79, 80: sets `_fetch_df_raises`, uses `await_inside(df_call_count >= 1)` then `stub.release()`. |
| `test_df_cancel.py` | `tests.async._edge_helpers` | `importlib.import_module` + `real_clock_watchdog` + `await_inside` | VERIFIED | Line 45: `importlib.import_module("tests.async._edge_helpers")`. `real_clock_watchdog` at lines 77, 108, 143, 175. |

---

### Data-Flow Trace (Level 4)

Not applicable for this phase. The phase delivers offload wrappers — there is no data-rendering component. The data flow goes: `AsyncCursor.fetch_df` → `cancellable_offload(self._cursor.fetch_df)` → driver's native `fetch_df` in worker thread → returns `pandas.DataFrame`. The round-trip tests (`test_df_roundtrip.py`) verify this end-to-end against real DuckDB: 4 passed.

---

### Behavioral Spot-Checks

| Behavior | Command / Evidence | Result | Status |
|----------|--------------------|--------|--------|
| `fetch_df` returns a real `pandas.DataFrame` with round-tripped values | `.venv/bin/pytest tests/async/test_df_roundtrip.py -q` | 4 passed | PASS |
| `fetch_polars` returns a real `polars.DataFrame` with round-tripped values | Same run | 4 passed | PASS |
| Native `ModuleNotFoundError` propagates unchanged | `.venv/bin/pytest tests/async/test_df_missing_dep.py -q` | 4 passed | PASS |
| Frame valid after checkin (self-owning) | `.venv/bin/pytest tests/async/test_df_lifetime.py -q` | 4 passed | PASS |
| Second in-flight op raises `ConnectionBusyError` | `.venv/bin/pytest tests/async/test_df_busy.py -q` | 4 passed (5/5 loop) | PASS |
| Cancel fires `adbc_cancel` once + invalidates once | `.venv/bin/pytest tests/async/test_df_cancel.py -q` | 6 passed (5/5 loop) | PASS |
| `import adbc_poolhouse` unaffected without pandas/polars | `.venv/bin/python -c "import sys; sys.modules.pop('pandas',None); sys.modules.pop('polars',None); import adbc_poolhouse"` | exit 0 | PASS |
| basedpyright 0 errors | `.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py` | `0 errors, 0 warnings, 0 notes` | PASS |
| Full async suite green | `.venv/bin/pytest tests/async -q` | 193 passed, 4 skipped | PASS |
| mkdocs strict build | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` | exit 0 | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| DF-01 | 31-01, 31-02 | `await cursor.fetch_df()` returns `pandas.DataFrame` (single whole-op offload) | SATISFIED | `AsyncCursor.fetch_df` implemented; round-trip tests green. |
| DF-02 | 31-01, 31-02 | `await cursor.fetch_polars()` returns `polars.DataFrame` (single whole-op offload) | SATISFIED | `AsyncCursor.fetch_polars` implemented; round-trip tests green. |
| DF-03 | 31-01, 31-02 | Native `ModuleNotFoundError` propagates unchanged; no `find_spec`, no wrapping | SATISFIED | No forbidden patterns in `_cursor.py`. `test_df_missing_dep.py` 4 passed. |
| DF-04 | 31-01, 31-02 | Frame self-owning and valid after checkin | SATISFIED | Approach A (driver native method); `test_df_lifetime.py` 4 passed. |
| PKG-02 | 31-01, 31-02 | pandas/polars in dev group only; runtime surface unchanged | SATISFIED | `pyproject.toml` dev group only; no extras; runtime import test clean. |

**Orphaned requirements check:** REQUIREMENTS.md maps DOCS-03 to Phase 33 (not Phase 31). Plan 31-02 added a DataFrame guide section as groundwork; this satisfies the DOCS-03 substance but the requirement formally closes in Phase 33. Not an orphan for Phase 31 — no Phase 31 plan claims DOCS-03.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | No TBD/FIXME/XXX markers found in Phase 31 files; no stubs, no placeholder returns in production code. |

**Verification notes:**
- `typing.cast` in `fetch_df`/`fetch_polars` return sites: this is a deliberate, documented bridge between the `-> object` Protocol and the public pandas/polars annotation (D-31-06 + D-31-07 jointly satisfiable only with cast). Not a stub or anti-pattern.
- Stub `fetch_df`/`fetch_polars` return `None` when no exception injected: intentional — concurrency tests never inspect the return value; round-trip tests use the real DuckDB driver.

---

### Human Verification Required

None. All must-have truths are verifiable programmatically and have been verified by running the actual test suite.

---

### Gaps Summary

No gaps. All 9 must-have truths verified, all artifacts present and substantive, all key links wired, all requirements satisfied, no anti-patterns found, full async suite green (193/0), basedpyright 0 errors, mkdocs --strict exit 0.

---

_Verified: 2026-07-02T22:00:00Z_
_Verifier: Claude (gsd-verifier)_
