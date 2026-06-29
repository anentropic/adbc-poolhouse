---
phase: 27-dual-backend-test-matrix
verified: 2026-06-28T00:00:00Z
status: human_needed
score: 6/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Push branch gsd/v1.4.0-async-api and confirm the dual-backend quality CI job is GREEN on Linux"
    expected: "The quality CI job runs test_matrix_readpath, test_stability_arrow, test_limiter_stress, and test_meta_guard under Linux, all green. The sync-no-anyio job continues to ignore tests/async/ (new tests excluded). Prior auto-approved sync-no-anyio live run is also green on this push."
    why_human: "Cross-platform stability cannot be verified locally. Phase 24-26 landmine: cancel races that pass 20/20 on macOS can hang on Linux CI. The x20 loop-stability gate ran locally (macOS, confirmed by SUMMARY), but Linux CI is the real cross-platform gate as documented in 27-05-PLAN.md checkpoint task and the project MEMORY."
---

# Phase 27: Dual-Backend Test Matrix — Verification Report

**Phase Goal:** The whole async layer is proven backend-generic and backend-neutral — every async test runs under asyncio and trio across DuckDB (in-proc) and the Snowflake cassette, with Arrow-memory stability and limiter-sizing stress proven and the no-asyncio meta-guards enforced.
**Verified:** 2026-06-28
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The async suite runs parametrized over asyncio and trio via `@pytest.mark.anyio`, exercised against DuckDB and Snowflake cassette (TEST-01/02) | VERIFIED | 8 legs collected: `test_fetch_arrow_table_round_trip` and `test_cursor_fetchall_surface` each run `[asyncio-duckdb_async_pool]`, `[asyncio-snowflake_async_pool]`, `[trio-duckdb_async_pool]`, `[trio-snowflake_async_pool]` — all 8 pass. `@pytest.mark.anyio` present, no `@pytest.mark.asyncio`, no `import asyncio`. |
| 2 | An Arrow memory-stability test confirms no allocator growth across many async cursor lifecycles (TEST-03) | VERIFIED | `tests/async/test_stability_arrow.py` runs N=100 cycles, asserts `delta == 0` and `reset_count == _N` via SQLAlchemy event listener. Passes `[asyncio]` and `[trio]`. Full suite: 433 passed, 2 skipped. |
| 3 | A limiter-sizing stress test confirms no deadlock or starvation when concurrency exceeds `pool_size` (TEST-04) | VERIFIED | `tests/async/test_limiter_stress.py` runs stub-gated 4x flood (`_FLOOD=32`, `_BOUND=8`), asserts `borrowed_tokens == _BOUND` at saturation and `== 0` after drain. Uses `real_clock_watchdog`, not `anyio.fail_after`. Real-DuckDB smoke flood also passes. Both `[asyncio]` and `[trio]` legs green. |
| 4 | A meta-test asserts every async test has `@pytest.mark.anyio`, no `@pytest.mark.asyncio`, no `asyncio` import, and no positive-duration sleep (EDGE-27/30) | VERIFIED | `tests/async/test_meta_guard.py` asserts `scan_async_test_hygiene("tests/async") == []` and `scan_for_positive_sleep("tests/async") == []`. Both pass. The guards are pure-stdlib AST scans in `tests/_async_harness/guard.py` (lines 400 and 447). |

**Score:** 4/4 ROADMAP success criteria verified

### Must-Have Truths (from PLAN frontmatter)

| Plan | Truth | Status | Evidence |
|------|-------|--------|----------|
| 27-01 | `snowflake_async_pool` fixture yields a cassette-backed AsyncPool and skips cleanly when driver/cassette absent | VERIFIED | `conftest.py` lines 109-143: `importorskip`, `pytest.skip` on absent cassette, `create_async_pool(SnowflakeConfig())`, `finally: await close_async_pool(pool)`. |
| 27-01 | `scan_async_test_hygiene(root)` returns `list[Finding]` for asyncio imports, `@pytest.mark.asyncio`, and missing `@pytest.mark.anyio` | VERIFIED | `guard.py` line 400; `_TestHygieneVisitor` class handles all three rules. Returns `[]` for absent root (confirmed by import test). |
| 27-01 | `scan_for_positive_sleep(root)` returns `Finding` for positive-duration sleep literals and allows `sleep(0)` and non-literal args | VERIFIED | `guard.py` line 447; `_PositiveSleepVisitor.visit_Call` checks `first.value > 0`, excludes `bool`. Allows `sleep(0)` and non-constants. |
| 27-01 | Synthetic-source self-tests prove both guard callables flag violators and pass clean source | VERIFIED | `tests/test_async_guard.py` passes (confirmed by `.venv/bin/pytest tests/async/test_meta_guard.py tests/async/test_matrix_readpath.py tests/async/test_stability_arrow.py tests/async/test_limiter_stress.py tests/test_async_guard.py -x -q`: 43 passed). |
| 27-02 | Read-path surface runs green parametrized over DuckDB and Snowflake cassette | VERIFIED | 8-leg matrix (2 backends × 2 loops × 2 test functions), all 8 pass. |
| 27-02 | Every read-path test runs under asyncio and trio via `@pytest.mark.anyio` | VERIFIED | Confirmed by collector output and passing test run. `anyio_backend` fixture in conftest parametrizes `["asyncio", "trio"]`. |
| 27-02 | Snowflake leg replays offline and skips cleanly when driver/cassette absent | VERIFIED | `pytest.importorskip` + `pytest.skip` path present in `snowflake_async_pool` fixture; cassette marker `adbc_cassette("snowflake_arrow_round_trip")` on snowflake param. |
| 27-02 | `checkedout() == 0` after each read-path round trip | VERIFIED | Lines 132 and 154 of `test_matrix_readpath.py`: `assert pool._pool.checkedout() == 0` in both test bodies. |
| 27-03 | `pyarrow.total_allocated_bytes()` shows no monotonic growth across N>=100 cycles | VERIFIED | `_N = 100`, `assert delta == 0` on line 93 of `test_stability_arrow.py`. Passes both backends. |
| 27-03 | Reset event fires exactly once per checkin across N cycles | VERIFIED | `sqlalchemy.event.listen(duckdb_async_pool._pool, "reset", _on_reset)` on line 68; `assert reset_count == _N` on line 97. |
| 27-03 | Stability test runs under asyncio and trio | VERIFIED | `@pytest.mark.anyio` on line 39; `anyio_backend_name` arg requested and `del`-ed (drives axis). Collector: `[asyncio]` and `[trio]` legs. |
| 27-04 | 4x(pool_size+max_overflow) stub-gated flood: running-max == bound, never exceeded | VERIFIED | `_FLOOD=32`, `_BOUND=8`; `assert observed_max == _BOUND` on line 111. |
| 27-04 | Every queued worker runs (no starvation), `borrowed_tokens` drains to 0 | VERIFIED | `await await_inside(lambda: limiter.borrowed_tokens == 0)` + `assert limiter.borrowed_tokens == 0` on lines 123, 125. |
| 27-04 | Real-DuckDB smoke flood completes with `checkedout() == 0`, no deadlock | VERIFIED | `test_real_duckdb_flood_drains` passes; `assert duckdb_async_pool._pool.checkedout() == 0` and `assert duckdb_async_pool._limiter.borrowed_tokens == 0` on lines 168-169. |
| 27-04 | Real-clock `time.monotonic()` watchdog, never `anyio.fail_after`; loop-stable under asyncio and trio | VERIFIED | `real_clock_watchdog` used in both tests (lines 102, 151). Grep for `anyio.fail_after` in test file returns only docstring/comment occurrences, zero code uses. |
| 27-05 | Meta-test asserts `scan_async_test_hygiene('tests/async') == []` | VERIFIED | `test_meta_guard.py` line 50. Passes. |
| 27-05 | Meta-test asserts `scan_for_positive_sleep('tests/async') == []` | VERIFIED | `test_meta_guard.py` line 62. Passes. |
| 27-05 | Any file the meta-scan flags is fixed (only flagged file, not blanket rewrite) | VERIFIED | Both scans return `[]` against the live `tests/async/`; no fixes were needed beyond the phase's own new files (which were written correctly from the start). |
| 27-05 | Full async suite is green | VERIFIED | `.venv/bin/pytest tests/async tests/_async_harness tests/test_async_guard.py -q`: 141 passed, 2 skipped. Full suite: 433 passed, 2 skipped. |

**Score:** 19/19 must-have truths verified (all 6 PLAN-level requirement IDs covered)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/async/conftest.py` | `snowflake_async_pool` cassette fixture | VERIFIED | 8,150 bytes. `async def snowflake_async_pool` at line 110. Google-style docstring with `Yields:` section. `_CASSETTE_ROOT` constant at line 55. |
| `tests/_async_harness/guard.py` | `scan_async_test_hygiene` + `scan_for_positive_sleep` AST scanners | VERIFIED | 20,841 bytes. `scan_async_test_hygiene` at line 400, `scan_for_positive_sleep` at line 447. Both have Google-style docstrings with `Example:` admonition blocks using fenced code (Markdown, not RST). `Finding` dataclass updated with new rule ids. |
| `tests/test_async_guard.py` | Synthetic-source self-tests for both new guard callables | VERIFIED | Passes (included in the 43-test run). Tests cover violator cases and clean/allowed cases (sleep(0), non-literal arg, `@pytest.mark.anyio`-present pass case). |
| `tests/async/test_matrix_readpath.py` | TEST-01/02 read-path backend-generic matrix | VERIFIED | 7,069 bytes (>30 lines). 8 parametrized legs. `getfixturevalue` indirect resolution; `adbc_cassette("snowflake_arrow_round_trip")` marker on snowflake param. |
| `tests/async/test_stability_arrow.py` | TEST-03 Arrow allocator-stability + reset-event-count proof | VERIFIED | 4,722 bytes (>30 lines). `_N = 100`. `event.listen`, `total_allocated_bytes`, `reset_count == _N` all present. |
| `tests/async/test_limiter_stress.py` | TEST-04 stub-gated limiter flood + real-DuckDB smoke flood | VERIFIED | 8,839 bytes (>40 lines). `real_clock_watchdog` present. `CapacityLimiter` with `_BOUND=8`. Drain via `cur.close()`, no `release()`. |
| `tests/async/test_meta_guard.py` | EDGE-27/30 real-package meta-tests asserting guard callables return `[]` | VERIFIED | 3,012 bytes (>15 lines). Two sync tests (no `@pytest.mark.anyio`). `scan_async_test_hygiene(_ASYNC_TESTS) == []` and `scan_for_positive_sleep(_ASYNC_TESTS) == []`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/async/conftest.py` | `adbc_poolhouse.create_async_pool(SnowflakeConfig(...))` | snowflake cassette pool construction | VERIFIED | Line 139: `pool = create_async_pool(SnowflakeConfig())` |
| `tests/_async_harness/guard.py` | `Finding` dataclass | new rule ids returned by both scanners | VERIFIED | `Finding` docstring lists all rule ids including `"banned-pytest-asyncio-marker"`, `"async-test-missing-anyio-marker"`, `"positive-sleep-literal"` |
| `tests/async/test_matrix_readpath.py` | `snowflake_async_pool` / `duckdb_async_pool` fixtures | `request.getfixturevalue` indirect parametrization | VERIFIED | Line 104: `return request.getfixturevalue(request.param)` |
| `tests/async/test_matrix_readpath.py` | pytest-adbc-replay cassette | `pytest.mark.adbc_cassette` marker on snowflake param | VERIFIED | Lines 51-53: `pytest.mark.adbc_cassette("snowflake_arrow_round_trip")` |
| `tests/async/test_stability_arrow.py` | pool reset event | `sqlalchemy.event.listen(pool._pool, 'reset', counter)` | VERIFIED | Line 68: `event.listen(duckdb_async_pool._pool, "reset", _on_reset)` |
| `tests/async/test_stability_arrow.py` | pyarrow allocator counter | `total_allocated_bytes` delta across N cycles | VERIFIED | Lines 73, 92: `baseline = pyarrow.total_allocated_bytes()`, `delta = pyarrow.total_allocated_bytes() - baseline` |
| `tests/async/test_limiter_stress.py` | `real_clock_watchdog` / `await_inside` | `importlib.import_module("tests.async._edge_helpers")` | VERIFIED | Lines 56-58: `_helpers = importlib.import_module("tests.async._edge_helpers")` |
| `tests/async/test_limiter_stress.py` | `BlockingStubConnection` + `AsyncConnection` sharing one `CapacityLimiter` | `_stub_conn_on(limiter)` flood | VERIFIED | Lines 68-72: `_stub_conn_on` helper; line 97: `limiter = anyio.CapacityLimiter(_BOUND)` |
| `tests/async/test_meta_guard.py` | `scan_async_test_hygiene` / `scan_for_positive_sleep` | `assert scan(...) == []` | VERIFIED | Lines 50, 62: both assertions over `"tests/async"` root |

### Data-Flow Trace (Level 4)

These are test files, not UI components; they generate their own data through actual API calls and assert on real return values. There is no external data source to trace — the tests drive real or stub backends and assert on outputs. All assertions verified as non-trivial (not hardcoded) by reading the test bodies above.

| Artifact | Data Source | Produces Real Data | Status |
|----------|------------|-------------------|--------|
| `test_matrix_readpath.py` | Real DuckDB pool + Snowflake cassette (offline replay) | Yes — asserts `pyarrow.Table.num_rows == 1`, column values, `checkedout() == 0` | FLOWING |
| `test_stability_arrow.py` | Real DuckDB pool, 100-cycle loop | Yes — `delta = total_allocated_bytes() - baseline`, `reset_count` from listener | FLOWING |
| `test_limiter_stress.py` | BlockingStubConnection + real DuckDB pool | Yes — `limiter.borrowed_tokens` polled live, `checkedout()` checked | FLOWING |
| `test_meta_guard.py` | AST scan of `tests/async/` source files | Yes — scanner walks real source files, returns real `Finding` lists | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All Phase 27 test files pass | `.venv/bin/pytest tests/async/test_meta_guard.py tests/async/test_matrix_readpath.py tests/async/test_stability_arrow.py tests/async/test_limiter_stress.py tests/test_async_guard.py -x -q` | 43 passed in 0.56s | PASS |
| Full async suite green | `.venv/bin/pytest tests/async tests/_async_harness tests/test_async_guard.py -q` | 141 passed, 2 skipped in 1.33s | PASS |
| Full project suite | `.venv/bin/pytest -q` | 433 passed, 2 skipped in 2.69s | PASS |
| mkdocs build --strict | `.venv/bin/mkdocs build --strict` | Documentation built successfully (0 errors; one non-fatal MkDocs 2.x deprecation warning unrelated to docs content) | PASS |
| 16 test legs collected for Phase 27 | `.venv/bin/pytest tests/async/test_matrix_readpath.py ... --collect-only -q` | 16 tests collected including 8-leg read-path matrix, 2-leg stability, 4-leg limiter, 2 meta-guard sync tests | PASS |
| No src/ changes in Phase 27 commits | `git log --oneline 4094274^..cbcec2f -- src/` | Empty output (no src/ files touched) | PASS |
| `anyio.fail_after` not used in test_limiter_stress.py code | `grep -n "anyio.fail_after" tests/async/test_limiter_stress.py` | Matches only in docstring/comment text, zero code uses | PASS |
| Drain uses `close()` not `release()` | `grep -n "\.close()" tests/async/test_limiter_stress.py` | Line 120: `cur.close()` in drain loop | PASS |
| `_N >= 100` | `grep -n "_N = " tests/async/test_stability_arrow.py` | `_N = 100` | PASS |

### Probe Execution

No conventional probe scripts (`scripts/*/tests/probe-*.sh`) declared or found for this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TEST-01 | 27-02 | Async suite runs parametrized over asyncio and trio via anyio pytest plugin | SATISFIED | `test_matrix_readpath.py` 8 legs; `@pytest.mark.anyio` on all async tests |
| TEST-02 | 27-02 | Async layer exercised against DuckDB and Snowflake cassette | SATISFIED | `_BACKENDS = ["duckdb_async_pool", pytest.param("snowflake_async_pool", ...)]` |
| TEST-03 | 27-03 | Arrow memory-stability test confirms no allocator growth | SATISFIED | `delta == 0` and `reset_count == _N` over 100 cycles |
| TEST-04 | 27-04 | Limiter-sizing stress confirms no deadlock or starvation | SATISFIED | `observed_max == _BOUND`, `borrowed_tokens == 0` after drain; real-clock watchdog |
| EDGE-27 | 27-01, 27-05 | Every async test parametrized over asyncio AND trio, no asyncio import or marker | SATISFIED | `scan_async_test_hygiene("tests/async") == []` asserted and passing |
| EDGE-30 | 27-01, 27-05 | Timeout/cancel tests use virtual clock or event gating, no positive-duration sleep | SATISFIED | `scan_for_positive_sleep("tests/async") == []` asserted and passing |

All 6 requirement IDs declared in PLAN frontmatter and ROADMAP are satisfied. DOCS-01..04 are tracked as Phase 28 (pending), correctly deferred.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | No TBD/FIXME/XXX/TODO/PLACEHOLDER anti-patterns found in Phase 27 files |

Scanned: `tests/async/conftest.py`, `tests/_async_harness/guard.py`, `tests/async/test_matrix_readpath.py`, `tests/async/test_stability_arrow.py`, `tests/async/test_limiter_stress.py`, `tests/async/test_meta_guard.py`. No debt markers. No stub patterns. No hardcoded empty returns.

### Context Decision Compliance (D-27-01..11)

| Decision | Constraint | Verified |
|----------|-----------|---------|
| D-27-01 | EDGE-27 via meta-test scanning `tests/async/`, not a blanket rewrite | Yes — `test_meta_guard.py` calls `scan_async_test_hygiene` |
| D-27-02 | Fix ONLY meta-flagged files; no blanket sweep of EDGE tests | Yes — both scans return `[]`, no fixes needed |
| D-27-03 | "Both backends" for EDGE-27 = asyncio/trio axis | Yes — meta-guard checks `@pytest.mark.anyio` presence |
| D-27-04 | `snowflake_async_pool` backed by existing Phase 25 cassette, no live Snowflake | Yes — `importorskip` + cassette `skip` guard; `_CASSETTE_ROOT` points to `tests/cassettes/` |
| D-27-05 | DuckDB × Snowflake cross-product: read-path only | Yes — `test_matrix_readpath.py` is strictly SELECT + `fetch_arrow_table` + `fetchall` |
| D-27-06 | Stub-gated mechanics stay DuckDB+stub only | Yes — `test_limiter_stress.py` uses `BlockingStubConnection`, no cassette in limiter tests |
| D-27-07 | Arrow stability: `total_allocated_bytes()` delta, NOT RSS, N >= 100 | Yes — `_N = 100`, `pyarrow.total_allocated_bytes()` |
| D-27-08 | Reset-event count via `sqlalchemy.event.listen`, no src/ patching | Yes — line 68 of `test_stability_arrow.py` |
| D-27-09 | Stability test runs ×{asyncio, trio} | Yes — `anyio_backend_name` arg drives axis |
| D-27-10 | Limiter flood: 4×(pool_size+max_overflow) workers, running-max == bound | Yes — `_FLOOD=32`, `_BOUND=8`, assertion on line 111 |
| D-27-11 | Deadlock detection: real-clock watchdog, NEVER `anyio.fail_after` | Yes — `real_clock_watchdog` used; zero code uses of `anyio.fail_after` |

### Human Verification Required

#### 1. Linux CI Cross-Platform Gate

**Test:** Push branch `gsd/v1.4.0-async-api` to GitHub and confirm the dual-backend `quality` CI job is GREEN on Linux.

**Expected:** All Phase 27 tests (`test_matrix_readpath`, `test_stability_arrow`, `test_limiter_stress`, `test_meta_guard`) appear in the `quality` job run and pass. The `sync-no-anyio` job does NOT collect them (they are under `tests/async/`, which is ignored). Prior auto-approved `sync-no-anyio` live run remains green on this push.

**Why human:** Cross-platform stability cannot be verified programmatically from macOS. This is the documented project-level landmine from Phases 24-26: cancel races in off-loop worker gating (the `test_limiter_stress.py` stub-gated flood is the highest-risk test) can pass 20/20 on macOS but hang on Linux CI. The x20 loop-stability gate was run locally on macOS (confirmed in 27-05-SUMMARY.md), but Linux CI is the real gate per the project's MEMORY and 27-04-PLAN.md / 27-05-PLAN.md checkpoint tasks.

---

### Gaps Summary

No automated gaps found. All 6 ROADMAP success criteria verified. All 19 must-have truths from PLAN frontmatter verified. All 6 requirement IDs (TEST-01, TEST-02, TEST-03, TEST-04, EDGE-27, EDGE-30) satisfied. No src/ changes. No anti-patterns. `mkdocs build --strict` passes. Full suite: 433 passed, 2 skipped.

The single pending item is the Linux CI cross-platform gate, which is a human-action item (push + CI check), not an automated gap. It is expected per the phase context and is the correct final sign-off gate for this phase.

---

_Verified: 2026-06-28_
_Verifier: Claude (gsd-verifier)_
