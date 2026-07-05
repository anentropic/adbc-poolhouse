---
phase: 31-dataframe-convenience
plan: 02
subsystem: async-cursor
tags: [green-wave, dataframe, pandas, polars, offload, docs]
requires:
  - "fetch_arrow_table offload shape (_cursor.py:341, shipped v1.4.0)"
  - "cancellable_offload + on_abort=invalidate contract (_cancel.py, Phase 25)"
  - "_offloading()/_in_use per-call C-access guard (_connection.py)"
  - "Six RED test files + BlockingStubCursor.fetch_df/fetch_polars harness (Plan 31-01)"
provides:
  - "AsyncCursor.fetch_df -> pandas.DataFrame (single whole-op offload, DF-01)"
  - "AsyncCursor.fetch_polars -> polars.DataFrame (single whole-op offload, DF-02)"
  - "_SyncCursor.fetch_df/fetch_polars Protocol members (-> object, D-31-06)"
  - "TYPE_CHECKING pandas/polars imports for deferred return annotations (D-31-07, PKG-02)"
  - "DataFrame convenience section in the async guide (DOCS groundwork)"
affects:
  - "Phase 32 (P2 edge-hardening) extends the fetch_df/fetch_polars paths"
tech-stack:
  added: [pandas-stubs]
  patterns:
    - "byte-for-byte fetch_arrow_table clone: swap only the callable, the return annotation, and the docstring (D-31-03)"
    - "Protocol -> object bridged to the public pandas/polars annotation via typing.cast (keeps the Protocol driver-agnostic while giving consumers accurate IDE types)"
    - "native ModuleNotFoundError propagates unwrapped through the offload chokepoint (no find_spec, no try/except — DF-03)"
key-files:
  created: []
  modified:
    - src/adbc_poolhouse/_async/_cursor.py
    - docs/src/guides/async.md
    - pyproject.toml
    - uv.lock
    - tests/async/test_df_roundtrip.py
    - tests/async/test_df_lifetime.py
    - tests/async/test_df_signature.py
    - tests/async/test_df_missing_dep.py
    - tests/async/test_df_busy.py
    - tests/async/test_df_cancel.py
decisions:
  - "Bridged the -> object Protocol return (D-31-06) to the public pandas/polars annotation (D-31-07) with typing.cast at each return site — the only way to satisfy both locked decisions under strict basedpyright (fetch_arrow_table avoids this only because its Protocol member returns pyarrow.Table)"
  - "Added pandas-stubs to the dev group: pandas ships no inline type stubs, so strict basedpyright errors on `import pandas` without it (polars bundles its own). Dev-group-only tooling dep, consistent with D-31-08 (no runtime dep, no extra)"
  - "Fixed test_df_missing_dep (authored in 31-01) to release the stub gate: it awaited fetch_df() with no concurrent releaser, so the worker parked in _block() forever once the method existed — it only 'passed RED' because AttributeError fired before the offload"
metrics:
  duration_min: 42
  completed: 2026-07-02T21:30:00Z
  tasks: 2
  files: 10
---

# Phase 31 Plan 02: DataFrame Convenience GREEN Summary

Landed `AsyncCursor.fetch_df` and `AsyncCursor.fetch_polars` as byte-for-byte clones of `fetch_arrow_table` — each one `with self._owner._offloading():` wrapping a single `cancellable_offload` of the bare `self._cursor.fetch_df`/`fetch_polars` reference (no `functools.partial`, no `find_spec`, no wrapping) — turning all 30 RED tests from Plan 31-01 GREEN, with the `_SyncCursor` Protocol extended, pandas/polars imported only under `TYPE_CHECKING`, cancel/busy parity verified 20/20 looped, and the async guide documenting the user-supplied pandas/polars contract.

## What Was Built

**Task 1 — methods + Protocol + TYPE_CHECKING imports (`43c94c7`):**
- `AsyncCursor.fetch_df(self) -> pandas.DataFrame` and `AsyncCursor.fetch_polars(self) -> polars.DataFrame`, inserted immediately after `fetch_arrow_table`. Each body is the `fetch_arrow_table` offload shape verbatim, differing only in the callable (bare `self._cursor.fetch_df`/`fetch_polars`, zero-arg — no `functools.partial`), the return annotation, and the docstring (Google-style, Markdown, with a singular `Example:` admonition and the "you install pandas/polars yourself; a missing dep surfaces the native `ModuleNotFoundError`" note). `on_abort=self._owner.invalidate` reused verbatim (D-31-09). No `_reader_open` lock, no new reader class, no shielded scope, no `find_spec`, no `try/except` (D-31-03/05).
- `_SyncCursor` Protocol gained `def fetch_df(self) -> object: ...` and `def fetch_polars(self) -> object: ...` beside `fetch_arrow_table`/`fetch_record_batch` (D-31-06).
- `import pandas` / `import polars` added under the existing `if TYPE_CHECKING:` block (D-31-07); `from __future__ import annotations` keeps the return-annotation strings unevaluated at runtime.
- `fetch_df`/`fetch_polars` added to the module-docstring offloaded-surface list.
- Deleted the Wave-0 RED pyright pragma blocks from the five test files (`test_df_roundtrip`, `test_df_lifetime`, `test_df_missing_dep`, `test_df_busy`, `test_df_cancel`).

**Task 2 — loop-verify + docs (`8d968b5`):**
- Loop-verified `test_df_cancel.py` + `test_df_busy.py` 20 iterations via `rc=$?` + grep (never `if ! cmd` in zsh): **20/20, LOOP-GREEN**, 0 hangs, 14 tests per iteration.
- Added a "Fetching a DataFrame" section to `docs/src/guides/async.md`: `fetch_df` → `pandas.DataFrame`, `fetch_polars` → `polars.DataFrame` as single offloaded calls, the self-owning-frame guarantee (valid after checkin, DF-04), and the user-supplied / native-`ModuleNotFoundError` contract (DF-03). Plain fenced `python` block, NOT wrapped in `!!! example` (project rule). Humanizer pass applied (no promotional language, no AI vocabulary, one em-dash per paragraph).

## Verification

- All 31-01 RED tests GREEN: `test_df_roundtrip` / `test_df_lifetime` / `test_df_missing_dep` / `test_df_signature` / `test_async_guard` → **18 passed**; full DF surface across both backends.
- Cancel + busy parity: **20/20 looped, LOOP-GREEN**, 0 hangs (0 failures across 20 iterations, verified via `rc=$?` + grep).
- `.venv/bin/basedpyright` over the whole tree (src + tests) → **0 errors, 0 warnings, 0 notes**.
- `scan_async_package` over `_async/` → `[]` (PKG-03, via `test_async_guard.py`).
- Runtime import-leak check: `import adbc_poolhouse` with `pandas`/`polars` popped from `sys.modules` → **import OK** (PKG-02).
- Acceptance greps: bare `self._cursor.fetch_df`/`fetch_polars` refs present; no `functools.partial`/`find_spec`/`except ModuleNotFoundError` near the DF methods; no top-level `import pandas`/`import polars`; Protocol members `-> object`; module-docstring surface list updated.
- `.venv/bin/mkdocs build --strict` → **exit 0**.
- Full async suite: `.venv/bin/pytest tests/async` → **193 passed, 4 skipped** (0 failures).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `typing.cast` at each return site to bridge the `-> object` Protocol to the public pandas/polars annotation**
- **Found during:** Task 1 (first basedpyright run).
- **Issue:** `cancellable_offload` returns the callable's declared type. Because `_SyncCursor.fetch_df`/`fetch_polars` are typed `-> object` (D-31-06, LOCKED), the offload returns `object`, which strict basedpyright rejects as not assignable to the public `-> pandas.DataFrame`/`-> polars.DataFrame` (D-31-07, LOCKED). `fetch_arrow_table` never hits this because its Protocol member returns `pyarrow.Table`, matching its public annotation. The plan's two locked decisions are only jointly satisfiable with an explicit cast.
- **Fix:** Wrapped each `await cancellable_offload(...)` in `cast("pandas.DataFrame", ...)` / `cast("polars.DataFrame", ...)` with a comment explaining it is a no-runtime-effect bridge between the driver-agnostic Protocol type and the public return type. Both locked decisions preserved; no Protocol change.
- **Files modified:** `src/adbc_poolhouse/_async/_cursor.py`.
- **Commit:** `43c94c7`.

**2. [Rule 3 - Blocking] Added `pandas-stubs` to the dev group**
- **Found during:** Task 1 (first basedpyright run).
- **Issue:** `pandas` ships no inline (PEP 561) type stubs, so strict basedpyright errors `Stub file not found for "pandas"` on the new `TYPE_CHECKING` import. polars bundles its own stubs (no error). The plan/RESEARCH assumed the dev-group deps alone resolve the annotations; they do for polars but not pandas.
- **Fix:** Added `"pandas-stubs>=2.0"` to `[dependency-groups].dev` (dev-group-only, no runtime dep, no extra — consistent with D-31-08). `uv sync --all-groups` installed `pandas-stubs==3.0.3.260530`; basedpyright then clean (0 errors).
- **Files modified:** `pyproject.toml`, `uv.lock`.
- **Commit:** `43c94c7`.

**3. [Rule 1 - Bug] Fixed `test_df_missing_dep.py` to release the stub gate**
- **Found during:** Task 1 (running the missing-dep test).
- **Issue:** The 31-01-authored test awaited `cur.fetch_df()` directly with no concurrent releaser. The stub's `fetch_df` calls `self._block()` (which waits on an unset `threading.Event`) BEFORE checking `_fetch_df_raises`, so the worker parks in `_block()` forever and the `pytest.raises` never fires. It "passed RED" in 31-01 only because the method did not exist yet (`AttributeError` fired before the offload). Now that the method exists, the test hangs.
- **Fix:** Rewrote both tests to drive `fetch_df`/`fetch_polars` in a task group, wait for the worker to be inside `_block` (`await_inside(df_call_count >= 1)`), then `stub.release()` so the injected native `ModuleNotFoundError` crosses the real `to_thread.run_sync` boundary (preserving the DF-03 "raise after `_block` releases" contract). Capture the exception and assert exact `.name` + `not isinstance(PoolhouseError)`. Verified 4 passed (2 tests × 2 backends), no hang.
- **Files modified:** `tests/async/test_df_missing_dep.py`.
- **Commit:** `43c94c7`.

### Environment note

`uv sync` and the basedpyright/uv-lock pre-commit hooks crash under the command sandbox (Rust `system-configuration` NULL / Tokio panic — a macOS sandbox restriction, not a real failure, matching the Plan 31-01 observation). `uv sync` and both `git commit` calls were run with the sandbox disabled; all direct `.venv/bin/*` runs were sandboxed and clean. Users can manage sandbox restrictions via `/sandbox`.

## Known Stubs

None. Both production methods are fully wired to the driver's native `fetch_df`/`fetch_polars`; there are no placeholder returns or unwired data paths. The stub `fetch_df`/`fetch_polars` in the test harness return `None` when no exception is injected, which is intentional and internal to the concurrency tests (they never inspect the return value; the positive round-trip tests use the real DuckDB driver).

## Threat Flags

None. The two methods route through the existing single `to_thread.run_sync` offload chokepoint and reuse the shipped `_offloading()`/`_in_use` guard and `on_abort=invalidate` recovery — no new network endpoint, auth path, file access, or trust-boundary surface beyond what `fetch_arrow_table` already crosses (threat register T-31-01..04 all mitigated by reused controls, proven by the GREEN cancel/busy/lifetime/missing-dep tests).

## Self-Check: PASSED

- `src/adbc_poolhouse/_async/_cursor.py` — FOUND (contains `async def fetch_df`, `async def fetch_polars`).
- `docs/src/guides/async.md` — FOUND (contains "Fetching a DataFrame" section).
- Commit `43c94c7` (feat) — FOUND in git history.
- Commit `8d968b5` (docs) — FOUND in git history.
