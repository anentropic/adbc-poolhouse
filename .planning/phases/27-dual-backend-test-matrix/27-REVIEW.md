---
phase: 27-dual-backend-test-matrix
reviewed: 2026-06-28T15:26:50Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - tests/_async_harness/guard.py
  - tests/async/conftest.py
  - tests/async/test_limiter_stress.py
  - tests/async/test_matrix_readpath.py
  - tests/async/test_meta_guard.py
  - tests/async/test_stability_arrow.py
  - tests/test_async_guard.py
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 27: Code Review Report

**Reviewed:** 2026-06-28T15:26:50Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 27 is a test-layer phase: a backend-generic read-path matrix
(DuckDB + Snowflake cassette x asyncio + trio), a limiter-saturation stress
proof, an Arrow allocator-stability proof, two new source-scan guard callables
(`scan_async_test_hygiene`, `scan_for_positive_sleep`), and a real-package
meta-guard. There are zero `src/` changes, as intended.

The implementation is in good shape and respects every project-specific
concurrency invariant I checked for: no `anyio.fail_after` off-loop gating
(a real-clock `time.monotonic()` watchdog thread is used instead), drains flood
via `close()` not `release()`, no positive-duration `sleep()` literals in
`tests/async/`, no `import asyncio` / `@pytest.mark.asyncio`, and the gating
mechanics stay on DuckDB + stub (the Snowflake cassette `ReplayCursor` is never
gated). I confirmed empirically:

- The matrix collects the full 8-cell grid (2 tests x 2 backends x 2 loops) and
  all 8 cells PASS with the Snowflake driver installed; the
  `pytest.param(..., marks=[adbc_cassette(...)])` indirection genuinely mounts
  the cassette for the Snowflake leg and replays offline.
- The limiter stress test is stable across 12 back-to-back runs (0 hangs),
  matching the project's "loop the concurrency tests" discipline.
- The Arrow-stability reset-count assertion is real (fires `_N` times), not a
  tautology.
- All 43 Phase-27 tests pass.

The findings below are quality/robustness issues, not blockers. The most
substantive is a genuine correctness gap in the new hygiene guard
(`_is_pytest_mark`) that produces both false positives and false negatives for
the `from pytest import mark` decorator form — latent today because the live
suite only uses the full `pytest.mark.*` chain, and the gap is untested.

## Warnings

### WR-01: `_is_pytest_mark` mishandles the `from pytest import mark` form (false positive AND false negative)

**File:** `tests/_async_harness/guard.py:280-295`
**Issue:** `_is_pytest_mark` only matches a decorator whose chain is
`<...>.mark.<name>` where `node.value` is itself an `ast.Attribute` with
`.attr == "mark"`. It therefore matches `@pytest.mark.anyio` but NOT
`@mark.anyio` written via `from pytest import mark` — there `node.value` is an
`ast.Name("mark")`, not an `ast.Attribute`. I confirmed both failure modes
empirically:

- `from pytest import mark; @mark.anyio; async def test_x(): ...` is wrongly
  reported as `async-test-missing-anyio-marker` (a **false positive** — the test
  IS correctly anyio-marked, so the meta-guard would fail on a legitimate file).
- `from pytest import mark; @mark.asyncio; async def test_y(): ...` is NOT
  reported as `banned-pytest-asyncio-marker` (a **false negative** — the banned
  marker slips through; it only coincidentally trips the missing-anyio rule).

The live `tests/async/` suite all uses the full `pytest.mark.*` chain, so the
meta-guard passes today — but a guard whose sole job is hygiene enforcement
silently fails on a common, valid decorator form, and that gap is untested.
**Fix:** Match the `mark` segment as either an `ast.Attribute` (`pytest.mark`)
or an `ast.Name` (`mark`):
```python
def _is_pytest_mark(decorator: ast.expr, mark: str) -> bool:
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    if not (isinstance(node, ast.Attribute) and node.attr == mark):
        return False
    base = node.value
    return (isinstance(base, ast.Attribute) and base.attr == "mark") or (
        isinstance(base, ast.Name) and base.id == "mark"
    )
```
Add self-test cases in `tests/test_async_guard.py` for the `from pytest import
mark` form (both `@mark.anyio` clean and `@mark.asyncio` banned).

### WR-02: `real_clock_watchdog([])` cannot fail-fast a deadlocked real flood — docstring claim is false

**File:** `tests/async/test_limiter_stress.py:151-166`, `tests/async/_edge_helpers.py:63-78`
**Issue:** `test_real_duckdb_flood_drains` wraps its task group in
`real_clock_watchdog([])` and the docstring asserts "if the real flood ever
deadlocked, the body would overrun the wall-clock budget and the `watchdog[0] is
False` assertion would trip rather than hang CI." That is not what the watchdog
does. The watchdog thread, on timeout, sets `tripped[0] = True` and `close()`s
the supplied cursors — but the list is empty, so it breaks nothing open. The
`with` body (`async with anyio.create_task_group()`) is still suspended at the
`yield`; if the real workers genuinely deadlocked, `yield` never returns,
`done.set()` in `finally` never runs, and the `assert watchdog[0] is False` line
is never reached. The test hangs CI exactly as the watchdog claims to prevent.
The watchdog gives real protection ONLY when it has cursors it can force open
(the stub path, WR is not a problem there). For the empty-cursor real flood it is
decorative.
**Fix:** Either drop the misleading watchdog wrapping for the real-flood test and
rely on an outer pytest/CI timeout, or replace the empty-list watchdog with a
mechanism that can actually interrupt the body (e.g. a real-clock
`anyio.move_on_after` is unsuitable under MockClock — so document that the real
backstop is the suite-level timeout and correct the docstring to say so). At
minimum, fix the docstring so it does not claim fail-fast behaviour the code
cannot deliver.

### WR-03: `borrowed_tokens == _BOUND` assertion is structurally guaranteed, not an observed bound proof

**File:** `tests/async/test_limiter_stress.py:109-111`
**Issue:** The "running-max equals the bound and is never exceeded" proof reads
`observed_max = limiter.borrowed_tokens` and asserts `observed_max == _BOUND`.
But `anyio.CapacityLimiter(_BOUND)` mathematically caps `borrowed_tokens` at
`_BOUND` — it can never exceed it by construction. The preceding
`await_inside(lambda: limiter.borrowed_tokens == _BOUND)` already waited until it
equals `_BOUND`, so the follow-up equality assertion can only fail in a tiny
race window (a token released between the poll and the read). The test thus
proves "saturation was reached," but the "never exceeded the bound" claim in the
docstring is enforced by the limiter type, not by this observation — the
assertion cannot meaningfully catch a wrapper bug that over-admits, because such
a bug would manifest as the library NOT using a single shared limiter, which this
test does not exercise (it injects the limiter itself via `_stub_conn_on`).
**Fix:** This is acceptable as a saturation/no-starvation smoke, but tone down
the docstring claim ("never exceeded") to match what is actually proven, or add a
genuine over-admission check by sampling `max_concurrent_in_execute` on the stub
cursors (which counts workers actually inside `_block`, independent of the
limiter's own accounting) and asserting it equals `_BOUND`.

### WR-04: `snowflake_async_pool` mutates global `os.environ` without restoring it

**File:** `tests/async/conftest.py:138`
**Issue:** The fixture does `os.environ.setdefault("SNOWFLAKE_ACCOUNT",
"replay-account")` and never removes it. `setdefault` avoids clobbering a real
value, but once set by the first Snowflake-leg test the variable persists for the
remainder of the process, leaking test state into any later test or fixture that
reads `SNOWFLAKE_ACCOUNT`. The same pattern exists in the pre-existing
`test_async_lifecycle.py`, so this is consistency-with-precedent rather than a new
defect, but a fixture is the right place to scope it.
**Fix:** Use pytest's `monkeypatch` to set and auto-restore:
```python
@pytest.fixture
async def snowflake_async_pool(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncPool]:
    ...
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", os.environ.get("SNOWFLAKE_ACCOUNT", "replay-account"))
    ...
```
(or capture/restore the prior value in the `finally` block).

## Info

### IN-01: Duplicated scan machinery between `scan_async_package` and `_scan_with`

**File:** `tests/_async_harness/guard.py:203-225` vs `247-269`
**Issue:** `scan_async_package` carries its own copy of the
`rglob` + tolerant `ast.parse` + `unparseable-source` loop, while the newer
`scan_async_test_hygiene` / `scan_for_positive_sleep` share the identical loop
factored into `_scan_with`. The two loop bodies are byte-for-byte equivalent. A
future fix to the tolerant-parse behaviour must be applied in two places.
**Fix:** Refactor `scan_async_package` to delegate to `_scan_with(root,
_GuardVisitor)` (the visitor signature already matches `Callable[[str],
_BaseVisitor]` since `_GuardVisitor.__init__(path)` is compatible). Optionally
make `_GuardVisitor` subclass `_BaseVisitor` to formalise the contract.

### IN-02: `event.listen` in the Arrow-stability test is never explicitly removed

**File:** `tests/async/test_stability_arrow.py:68`
**Issue:** `event.listen(duckdb_async_pool._pool, "reset", _on_reset)` registers a
SQLAlchemy listener but never calls `event.remove`. In practice this is harmless
because the `duckdb_async_pool` fixture builds a fresh pool per test and disposes
it on teardown, so the listener dies with the pool. Worth a one-line note or an
explicit `event.remove` in a `finally`/`addfinalizer` for clarity, since the
listener closes over the test-local `reset_count`.
**Fix:** Register cleanup so intent is explicit:
```python
event.listen(duckdb_async_pool._pool, "reset", _on_reset)
request.addfinalizer(lambda: event.remove(duckdb_async_pool._pool, "reset", _on_reset))
```
(or wrap the body in try/finally with `event.remove`).

### IN-03: `_col` would silently collapse case-variant duplicate column names

**File:** `tests/async/test_matrix_readpath.py:78-79`
**Issue:** `_col` builds `{n.lower(): n for n in table.column_names}` to do
case-insensitive lookup. If a result ever returned two columns differing only in
case (e.g. `n` and `N`), the dict comprehension would silently keep only the
last, and the test would assert against the wrong column without any error. The
current single-row `SELECT 1 AS n, 'hello' AS s` shape cannot produce a
collision, so this is a latent robustness note, not a live bug.
**Fix:** No action needed for the current query; if `_col` is reused for wider
result shapes, add an assertion that the lowercased name set has no collisions,
or look up the exact name when present before falling back to case-folding.

---

_Reviewed: 2026-06-28T15:26:50Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
