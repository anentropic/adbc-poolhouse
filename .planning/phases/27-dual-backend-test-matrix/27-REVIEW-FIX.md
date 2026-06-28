---
phase: 27-dual-backend-test-matrix
fixed_at: 2026-06-28T15:37:32Z
review_path: .planning/phases/27-dual-backend-test-matrix/27-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 27: Code Review Fix Report

**Fixed at:** 2026-06-28T15:37:32Z
**Source review:** .planning/phases/27-dual-backend-test-matrix/27-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (fix_scope=all: 4 warning + 3 info)
- Fixed: 7
- Skipped: 0

All fixes are in test/harness code under `tests/`. There are zero `src/`
changes, honouring the test-layer invariant. The full async suite passes
(143 passed, 2 skipped) and was looped 10x with 0 hangs / 0 fails, matching the
project's flaky-concurrency discipline.

## Fixed Issues

### WR-01: `_is_pytest_mark` mishandles the `from pytest import mark` form

**Files modified:** `tests/_async_harness/guard.py`, `tests/test_async_guard.py`
**Commit:** a7be28f
**Applied fix:** Rewrote `_is_pytest_mark` to match the `mark` segment as EITHER
an `ast.Attribute` (`pytest.mark.<mark>`) OR an `ast.Name` (`mark`, from
`from pytest import mark`). This closes both the false negative (a banned
`@mark.asyncio` slipping through) and the false positive (a legitimate
`@mark.anyio` wrongly flagged as missing the marker). Added two self-test cases
in `tests/test_async_guard.py` covering the imported-name form (clean `@mark.anyio`
and banned `@mark.asyncio`). Per the guardrails, re-ran `tests/test_async_guard.py`
(29 passed) and confirmed `scan_async_test_hygiene("tests/async")` and
`scan_for_positive_sleep("tests/async")` both still return `[]` — the widened
matcher does not false-flag the real suite.

### WR-02: `real_clock_watchdog([])` cannot fail-fast a deadlocked real flood

**Files modified:** `tests/async/test_limiter_stress.py`
**Commit:** 01ed319 (committed with WR-03; see note below)
**Applied fix:** Corrected the `test_real_duckdb_flood_drains` docstring (and the
inline assertion comment) to stop claiming fail-fast behaviour the empty-cursor
watchdog cannot deliver. The docstring now states plainly that, because this
flood has no blocking stub the watchdog could `close()`, a genuine deadlock would
hang at the `async with` body and never reach the post-body assertion — so the
real deadlock backstop is the suite-level / CI job timeout. The watchdog is
retained and documented as a soft over-budget signal only (catches a
slow-but-completing flood). No virtual timeout was introduced (the Phase 24-26
MockClock-autojump landmine is explicitly called out and avoided).

### WR-03: `borrowed_tokens == _BOUND` is structurally guaranteed, not an observed proof

**Files modified:** `tests/async/test_limiter_stress.py`, `tests/_async_harness/stubs.py`
**Commit:** 01ed319
**Applied fix:** Replaced the structurally-guaranteed `borrowed_tokens` equality
with a genuine over-admission proof that is independent of the limiter's own
accounting. Added a public `in_execute` read-only property to
`BlockingStubCursor` (the instantaneous companion to the existing
`max_concurrent_in_execute` high-water mark, lock-read). The stress test now sums
`in_execute` across all flood cursors — the workers ACTUALLY inside `_block` right
now — and asserts that cross-cursor sum equals `_BOUND` (never exceeded). The
limiter equality is kept as a secondary cross-check. Crucially, the saturation
WAIT now polls the cross-cursor inside-sum rather than `borrowed_tokens`: a worker
holds a limiter token from the moment the offload path acquires it but does not
reach the stub's `_block` until its worker thread runs, so polling
`borrowed_tokens` left a race (`inside_now == 0` while `borrowed_tokens == _BOUND`).
Polling the inside-sum closes that race. Verified by looping the stress test 12x
(0 hangs, 0 fails) — including catching and fixing the initial race during
verification.

**Note (WR-02 + WR-03):** Both findings touch `test_limiter_stress.py` in
adjacent regions and were co-verified by the same stress-loop run, so they share
commit 01ed319. WR-03 additionally modifies `stubs.py`.

### WR-04: `snowflake_async_pool` mutates global `os.environ` without restoring it

**Files modified:** `tests/async/conftest.py`
**Commit:** e783696
**Applied fix:** Switched the fixture from `os.environ.setdefault("SNOWFLAKE_ACCOUNT",
...)` to `monkeypatch.setenv("SNOWFLAKE_ACCOUNT", os.environ.get("SNOWFLAKE_ACCOUNT",
"replay-account"))`. monkeypatch auto-restores the prior value (or unsets it) on
teardown so the replay dummy never leaks into later tests/fixtures; reading the
existing value back as the default preserves a real `SNOWFLAKE_ACCOUNT` if one is
already set. Added the `monkeypatch` arg to the fixture signature and documented
it. Verified the full read-path matrix (8 cells, Snowflake leg active) still
passes.

### IN-01: Duplicated scan machinery between `scan_async_package` and `_scan_with`

**Files modified:** `tests/_async_harness/guard.py`
**Commit:** f8f2a64
**Applied fix:** Refactored `scan_async_package` to delegate to the shared
`_scan_with(root, _GuardVisitor)`, removing the byte-for-byte duplicate
`rglob` + tolerant `ast.parse` + absent-root loop so the tolerant-parse behaviour
lives in one place. Promoted `_GuardVisitor` to subclass `_BaseVisitor` (moved
`_BaseVisitor` above it and removed the now-duplicate later definition) to
formalise the `Callable[[str], _BaseVisitor]` factory contract. Verified all 29
guard self-tests pass — including the real-package scan and the
unparseable/non-utf8 tolerance tests — proving delegation preserved behaviour;
re-confirmed all three live scans still return `[]`.

### IN-02: `event.listen` in the Arrow-stability test is never explicitly removed

**Files modified:** `tests/async/test_stability_arrow.py`
**Commit:** 66119f4
**Applied fix:** Added `request: pytest.FixtureRequest` to the test signature and
registered `request.addfinalizer(lambda: event.remove(...))` immediately after the
`event.listen` call, so the listener (which closes over the test-local
`reset_count`) is removed explicitly on teardown rather than relying on the pool's
implicit disposal. Verified the test (both backend legs) passes across 3 loops.

### IN-03: `_col` would silently collapse case-variant duplicate column names

**Files modified:** `tests/async/test_matrix_readpath.py`
**Commit:** 0ed559b
**Applied fix:** Made `_col` prefer an exact-case match when present, and only
fall back to case-folding when the lowercased name set is collision-free —
raising `KeyError` on an ambiguous case-variant collision instead of silently
resolving to the wrong column. No behaviour change for the current
`SELECT 1 AS n, 'hello' AS s` shape (DuckDB hits the exact-case path, Snowflake's
uppercased `N`/`S` takes the safe case-fold path). Documented the new `Raises`
contract. Verified all 8 matrix cells pass.

## Verification

- `tests/test_async_guard.py`: 29 passed (includes 2 new WR-01 cases).
- Live guard scans: `scan_async_package`, `scan_async_test_hygiene`,
  `scan_for_positive_sleep` all return `[]` against the real package / suite.
- `tests/async/test_limiter_stress.py`: looped 12x — 0 hangs, 0 fails.
- `tests/async/test_matrix_readpath.py`: 8 passed (both backends x both loops).
- `tests/async/test_stability_arrow.py`: passed across 3 loops (both backends).
- Full async suite (`tests/async tests/_async_harness tests/test_async_guard.py`):
  **143 passed, 2 skipped**, looped 10x — **0 hangs, 0 fails**.
- All commits passed the full pre-commit hook chain (ruff, ruff format,
  basedpyright type-check, blacken-docs, detect-secrets).

Invariants held: no `src/` changes; no `anyio.fail_after`/virtual-timeout
introduced for off-loop gating; drains still flood via `close()` not `release()`;
no assertions weakened into tautologies (WR-03 strengthened the proof); no sleeps
added; new public symbol (`in_execute`) has a Google-style Markdown docstring.

---

_Fixed: 2026-06-28T15:37:32Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
