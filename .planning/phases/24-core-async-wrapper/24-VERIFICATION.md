---
phase: 24-core-async-wrapper
verified: 2026-06-27T23:35:10Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification_discharged:
  - test: "Run the async test suite (concurrency surface) in a ×20 loop to confirm 0 hangs"
    expected: "20/20 runs pass with 0 hangs/watchdog trips"
    result: "DISCHARGED 2026-06-28 by orchestrator — 20/20 runs, 0 failures, 48 passed per run (zsh-safe loop). The concurrency-flaky surface is the async suite, so it was the loop target; full suite confirmed once at 358 passed / 2 skipped."
  - test: "Confirm basedpyright 0 errors on src/adbc_poolhouse/_async/"
    expected: "basedpyright exits 0 with 0 errors, 0 warnings"
    result: "DISCHARGED 2026-06-28 by orchestrator — `.venv/bin/basedpyright src/adbc_poolhouse/_async/` run outside the command sandbox: 0 errors, 0 warnings, 0 notes."
---

# Phase 24: Core Async Wrapper Verification Report

**Phase Goal:** A user can run a full async query end-to-end (`create_async_pool` → `connect` → `execute` → `fetch_arrow_table` → checkin) on any of the 13 backends, with every structural pitfall except cancellation already closed: dedicated per-pool limiter, offload-everything rule, symmetric Arrow cleanup, and strict typing.
**Verified:** 2026-06-27T23:35:10Z
**Status:** passed (two human-verification items discharged by orchestrator re-run on 2026-06-28 — see frontmatter `human_verification_discharged`)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Full async query end-to-end (`create_async_pool→connect→cursor→execute→fetch_arrow_table→checkin`) passes on real DuckDB under asyncio and trio | ✓ VERIFIED | `tests/async/test_async_lifecycle.py::TestHappyPath::test_execute_fetch_arrow_table` asserts `isinstance(tbl, pyarrow.Table)` + `checkedout()==0`; suite passes 38 tests in 0.51s |
| 2 | Dedicated per-pool limiter: `AsyncPool` owns exactly one `CapacityLimiter(pool_size + max_overflow)`, never the global 40-token default | ✓ VERIFIED | `_pool.py:87`: `self._limiter = anyio.CapacityLimiter(pool_size + max_overflow)` — one per pool; EDGE-12 test asserts `observed_max == bound` under 4x flood |
| 3 | Offload-everything rule: single `offload()` chokepoint with `limiter=` + `abandon_on_cancel=False`; no bare `to_thread` calls; `import asyncio` banned and lint-enforced | ✓ VERIFIED | `_offload.py:67-71` is the only `anyio.to_thread.run_sync` call; `scan_async_package('src/adbc_poolhouse/_async') == []` asserted in `tests/test_async_guard.py::TestRealAsyncPackage`; grep confirms 0 `import asyncio` in `_async/` |
| 4 | Symmetric Arrow cleanup: shielded checkin fires `_release_arrow_allocators`; `fetch_arrow_table` returns materialized `pyarrow.Table` readable after checkin; `checkedout()==0` after `__aenter__` failure (no leak over N iters) | ✓ VERIFIED | `_connection.py:240`: `CancelScope(shield=True)` in `__aexit__`; `test_edge_resource.py`: reads table after checkin, `isinstance(tbl, pyarrow.Table)` twice; `test_edge_exceptions.py`: `_LEAK_LOOPS=20` iterations, `checkedout()==0` every run |
| 5 | Strict typing: backend-generic (no per-backend async code, D-24-04); structural pitfalls closed: aliasing → `ConnectionBusyError`, token accounting balanced on success+error (EDGE-09), concurrent max bounded (EDGE-12), ADBC errors propagate with exact type+traceback (EDGE-17) | ✓ VERIFIED | `test_async_guard.py::test_no_backend_config_names_in_executable_code` AST scan finds 0 backend names in executable code; `test_edge_aliasing.py`: `ConnectionBusyError` raised + `max_concurrent_in_execute==1`; `test_edge_limiter.py`: `borrowed_tokens==0` ×7 assertions; `test_edge_exceptions.py`: `_offload` frame in traceback |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/_async_harness/stubs.py` | Re-armable per-call blocking gate + `on_enter` hook + public `closed` attr + flags under lock | ✓ VERIFIED | `_block` re-arms (clears event) each call; `on_enter`/`register_on_enter` fire from inside `_block`; `closed` is a lock-guarded `@property`; `import anyio` count = 0 |
| `tests/_async_harness/gating.py` | `run_blocking` bridges `entered` via `register_on_enter` from INSIDE `_block` (D-CF-01) | ✓ VERIFIED | Confirmed `on_enter` bridge pattern; `entered` fires only after worker is inside blocked section |
| `tests/_async_harness/test_harness.py` | execute-then-fetch re-arm self-test with real-clock watchdog | ✓ VERIFIED | `test_rearm_execute_then_fetch_same_cursor` present; `_real_clock_watchdog` wraps the test; `fail_after` referenced in docstrings (grep token) |
| `src/adbc_poolhouse/_async/_offload.py` | Single `to_thread.run_sync` chokepoint with `limiter=` + `abandon_on_cancel=False` | ✓ VERIFIED | File read; single call at line 67-71; no exception re-wrap |
| `src/adbc_poolhouse/_async/_pool.py` | `AsyncPool` owning `CapacityLimiter(pool_size+max_overflow)`; shielded `close` | ✓ VERIFIED | Line 87: limiter; line 113: `CancelScope(shield=True)` |
| `src/adbc_poolhouse/_async/_factory.py` | `create_async_pool` 3 overloads + `managed_async_pool` + `close_async_pool`; reuses `_create_pool_impl` verbatim | ✓ VERIFIED | `from adbc_poolhouse._pool_factory import _create_pool_impl` present; 3 `@overload` decorators confirmed; no backend class names in executable code |
| `src/adbc_poolhouse/_async/_connection.py` | `AsyncConnection`: sync `cursor()`; `_in_use` no-await check-and-set; shielded `close`/`__aexit__`; no `anyio.Lock` | ✓ VERIFIED | `def cursor()` (no `async`); `_enter_offload` reads then writes `_in_use` in single sync span; 2x `CancelScope(shield=True)` (close + `__aexit__`); `anyio.Lock` count = 0 |
| `src/adbc_poolhouse/_async/_cursor.py` | `AsyncCursor`: full DBAPI surface offloaded; `description`/`rowcount`/`arraysize` sync `@property`; `fetch_arrow_table` returns materialized `Table`; no exception re-wrap | ✓ VERIFIED | All blocking methods bracket `offload()` with `_enter_offload`/`_exit_offload`; 3 `@property` non-async passthroughs; `fetch_arrow_table` returns `self._cursor.fetch_arrow_table()` directly |
| `src/adbc_poolhouse/_exceptions.py` | `ConnectionBusyError(PoolhouseError)` with canonical D-24-03 message | ✓ VERIFIED | `class ConnectionBusyError(PoolhouseError)` at line 30; canonical message present; exported in `__all__` |
| `tests/async/conftest.py` | `anyio_backend` fixture scoped to `tests/async/` only; NOT in root conftest | ✓ VERIFIED | `anyio_backend` count = 4 in conftest; root conftest absent (non-existent file) |
| `tests/async/test_async_lifecycle.py` | Happy path + sync-surface + Snowflake cassette leg | ✓ VERIFIED | `test_execute_fetch_arrow_table`, `test_managed_async_pool`, `TestSyncSurface`, `TestSnowflakeCassetteBackend` all present |
| `tests/async/test_edge_limiter.py` | EDGE-09/10/11/12 | ✓ VERIFIED | `borrowed_tokens==0` ×7; cancel-while-queued recovery; transient-token no-deadlock; running-max == bound under 4x flood |
| `tests/async/test_edge_aliasing.py` | EDGE-15 `ConnectionBusyError` + `max_concurrent_in_execute==1` | ✓ VERIFIED | Both assertions present in test |
| `tests/async/test_edge_exceptions.py` | EDGE-17 exact type+traceback; EDGE-18 no leak over 20 iters | ✓ VERIFIED | `_offload` frame asserted in traceback; `_LEAK_LOOPS=20`, `checkedout()==0` every iteration |
| `tests/async/test_edge_resource.py` | EDGE-21 materialized `Table` readable after checkin | ✓ VERIFIED | `isinstance(tbl, pyarrow.Table)` after connection scope exits, after pool closed |
| `tests/async/test_edge_loophygiene.py` | EDGE-25 worker thread ≠ loop thread; EDGE-26 concurrent coroutine advances | ✓ VERIFIED | `execute_thread_ids[0] != loop_thread_id`; counter increments across `sleep(0)` checkpoints while offload blocked |
| `tests/test_async_guard.py` | EDGE-25 static: `scan_async_package(_ASYNC_PKG)==[]`; D-24-04 no-backend-names AST check | ✓ VERIFIED | `TestRealAsyncPackage` class with both assertions present; passes 10 tests |
| `docs/src/guides/async.md` | Async usage guide with `ConnectionBusyError` antipattern + honest concurrency framing | ✓ VERIFIED | Contains `ConnectionBusyError` (×2), `create_async_pool` (×3), `fetch_arrow_table` (×4); I/O-vs-materialization honesty with SPIKE numbers |
| `mkdocs.yml` | Nav entry for async guide | ✓ VERIFIED | `- Async Pool: guides/async.md` present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_offload.py:offload` | `anyio.to_thread.run_sync` | Literal un-aliased call with `limiter=` + `abandon_on_cancel=False` | ✓ WIRED | Line 67-71 confirmed; literal chain preserved |
| `_pool.py:AsyncPool.connect` | `_offload.py:offload` | `offload(self._pool.connect, limiter=self._limiter)` | ✓ WIRED | Line 101 confirmed |
| `_factory.py:create_async_pool` | `_pool_factory._create_pool_impl` | `from adbc_poolhouse._pool_factory import _create_pool_impl` + direct call | ✓ WIRED | No fork, no per-backend branch |
| `__init__.py:__getattr__` | `adbc_poolhouse._async` | PEP 562 lazy import guarding anyio absence | ✓ WIRED | `_LAZY_ASYNC_NAMES` frozenset + `__getattr__` at line 73; `__dir__` at line 100 |
| `_cursor.py:AsyncCursor.execute` | `_connection.py:AsyncConnection._enter_offload/_exit_offload` | `self._owner._enter_offload()` / `finally: self._owner._exit_offload()` | ✓ WIRED | Pattern present on all 7 blocking cursor methods |
| `_connection.py:__aexit__` | `fairy.close()` reset event | Shielded `offload(self._fairy.close, ...)` fires pool reset listener | ✓ WIRED | `CancelScope(shield=True)` + `offload(self._fairy.close...)` at line 240-241 |
| `tests/async/conftest.py:anyio_backend` | `tests/_async_harness/conftest.py:anyio_backend` | Verbatim mirror confined to `tests/async/` | ✓ WIRED | Root conftest absent; no leakage to sync suite |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `test_async_lifecycle.py::test_execute_fetch_arrow_table` | `tbl` (pyarrow.Table) | Real DuckDB driver via `cur.fetch_arrow_table()` → `AsyncCursor.fetch_arrow_table()` → `offload(self._cursor.fetch_arrow_table, ...)` | Yes — `SELECT 42` returns real row | ✓ FLOWING |
| `test_edge_limiter.py` | `limiter.borrowed_tokens` | `pool._limiter` (live anyio.CapacityLimiter) | Yes — reflects real in-flight worker count | ✓ FLOWING |
| `test_edge_exceptions.py` | AdbcError exception + traceback | Real DuckDB bad query (`SELECT * FROM nonexistent_table_xyz`) | Yes — real driver error | ✓ FLOWING |
| `test_edge_resource.py` | `tbl` (pyarrow.Table) | Real DuckDB `fetch_arrow_table` after connection checkin | Yes — materialized, self-owning buffers | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full async suite (38 tests) | `.venv/bin/python -m pytest tests/async -q` | 38 passed in 0.51s | ✓ PASS |
| Guard tests (10 tests) | `.venv/bin/python -m pytest tests/test_async_guard.py -q` | 10 passed in 0.02s | ✓ PASS |
| Full project suite (358 tests) | `.venv/bin/python -m pytest -q` | 358 passed, 2 skipped in 1.09s | ✓ PASS |
| mkdocs strict build | `.venv/bin/mkdocs build --strict` | rc=0 (INFO-level relative-link notices only, not strict failures) | ✓ PASS |
| No asyncio imports in `_async/` | `grep -n "import asyncio" src/adbc_poolhouse/_async/*.py` | No output | ✓ PASS |
| No debt markers in async source | `grep -rE "TBD\|FIXME\|XXX" src/adbc_poolhouse/_async/` | No output | ✓ PASS |
| `anyio.Lock` absent from `_connection.py` | `grep -n "anyio.Lock" src/adbc_poolhouse/_async/_connection.py` | No output | ✓ PASS |
| `cursor()` is not async | `grep -n "async def cursor" src/adbc_poolhouse/_async/_connection.py` | No output | ✓ PASS |
| Example blocks ≥ 6 across `_async/` | `grep -c "Example:" src/adbc_poolhouse/_async/*.py` | factory=3, connection=1, cursor=1, pool=1 (total=6) | ✓ PASS |
| RST roles absent from `_async/` | `grep -rE ":(func\|class\|meth\|attr\|mod):" src/adbc_poolhouse/_async/` | No output | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes exist for this phase; the acceptance evidence is the pytest suite.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CORE-01 | 24-02, 24-04 | Single offload helper, no bare `to_thread` | ✓ SATISFIED | `_offload.py` is the only call site; `scan_async_package==[]` asserted |
| CORE-02 | 24-02, 24-04 | Per-pool `CapacityLimiter(pool_size+max_overflow)` | ✓ SATISFIED | `_pool.py:87`; EDGE-12 proves bound |
| CORE-03 | 24-02, 24-04 | `import asyncio` banned, lint-enforced | ✓ SATISFIED | `scan_async_package` rule + guard test; 0 asyncio imports confirmed |
| CORE-04 | 24-02, 24-04, 24-05 | Backend-generic via `WarehouseConfig` Protocol | ✓ SATISFIED | AST no-backend-names check; `_create_pool_impl` reuse; Snowflake cassette leg |
| APOOL-01 | 24-02, 24-04 | `create_async_pool` with mirrored signature + overloads | ✓ SATISFIED | 3 `@overload` decorators; same kwargs as `create_pool` |
| APOOL-02 | 24-02, 24-04 | `await close_async_pool(pool)` offloaded | ✓ SATISFIED | `close_async_pool` awaits `pool.close()`; shielded in `AsyncPool.close` |
| APOOL-03 | 24-02, 24-04 | `async with managed_async_pool(...) as pool:` | ✓ SATISFIED | `@contextlib.asynccontextmanager` with shielded finally; lifecycle test |
| ACONN-01 | 24-02, 24-03, 24-04 | `await pool.connect()` offloaded under pool limiter | ✓ SATISFIED | `_pool.py:101`; happy-path test |
| ACONN-02 | 24-03, 24-04 | `AsyncConnection` async context manager; shielded checkin | ✓ SATISFIED | `__aexit__` with `CancelScope(shield=True)` |
| ACONN-03 | 24-03, 24-04, 24-05 | `cursor()` synchronous (no `await`) | ✓ SATISFIED | `def cursor()` (no `async`); sync-surface test asserts not a coroutine |
| ACONN-04 | 24-03, 24-04 | `await conn.commit()` + `await conn.rollback()` offloaded | ✓ SATISFIED | Both offload through `_enter_offload`/`offload`/`_exit_offload`; lifecycle test |
| ACONN-05 | 24-03, 24-04 | `await conn.close()` offloaded + shielded | ✓ SATISFIED | `close()` with `CancelScope(shield=True)`; lifecycle test |
| ACONN-06 | 24-03, 24-04 | Checkin fires `_release_arrow_allocators` via `fairy.close()` | ✓ SATISFIED | `__aexit__` offloads `fairy.close`; reset event wiring unchanged |
| ACUR-01 | 24-03, 24-04 | `await cursor.execute(...)` offloaded | ✓ SATISFIED | `_cursor.py:162`; happy-path test |
| ACUR-02 | 24-03, 24-04 | `await cursor.executemany(...)` offloaded | ✓ SATISFIED | `_cursor.py:189`; lifecycle test |
| ACUR-03 | 24-03, 24-04 | `await cursor.fetchone/fetchmany/fetchall()` offloaded | ✓ SATISFIED | `_cursor.py:216-284`; lifecycle test |
| ACUR-04 | 24-03, 24-04, 24-05 | `await cursor.fetch_arrow_table()` → materialized `pyarrow.Table` | ✓ SATISFIED | Returns `fetch_arrow_table` result directly; EDGE-21 test |
| ACUR-05 | 24-03, 24-04 | `AsyncCursor` async context manager; shielded `close` | ✓ SATISFIED | `close()` with `CancelScope(shield=True)`; `__aexit__` calls close |
| ACUR-06 | 24-03, 24-04 | ADBC errors propagate with exact type + traceback | ✓ SATISFIED | No re-wrap in `offload` or cursor; EDGE-17 asserts `_offload` frame |
| ACUR-07 | 24-03, 24-04, 24-05 | Sync `description`/`rowcount`/`arraysize` `@property` passthroughs | ✓ SATISFIED | All three are `@property` non-`async`; sync-surface test |
| EDGE-09 | 24-04 | Token borrowed-then-released on success+error paths (×50); cancel-mid-block deferred D-24-02 | ✓ SATISFIED | `_ACCOUNTING_LOOPS=50`; `borrowed_tokens==0` ×7 in test; cancel-mid-block correctly absent |
| EDGE-10 | 24-04 | Queued-acquire cancel leaks no token; concurrency recovers | ✓ SATISFIED | `test_cancel_while_queued_on_saturated_limiter`; `borrowed_tokens==0` after recovery |
| EDGE-11 | 24-04 | Holding connection + second offload: no self-deadlock (transient token) | ✓ SATISFIED | `test_transient_token_no_self_deadlock`; real-clock watchdog; transient model by construction |
| EDGE-12 | 24-04 | In-flight max == `pool_size+max_overflow` under 4x flood | ✓ SATISFIED | `test_running_max_equals_bound_under_flood`; `assert observed_max == bound` |
| EDGE-15 | 24-03, 24-04 | Concurrent aliasing → `ConnectionBusyError`; `max_concurrent_in_execute==1` | ✓ SATISFIED | `test_edge_aliasing.py`; both assertions present and tested |
| EDGE-17 | 24-03, 24-04 | Worker exception: exact type + traceback with worker frame | ✓ SATISFIED | `_offload` frame asserted in rendered traceback; `isinstance(exc, AdbcError)` |
| EDGE-18 | 24-03, 24-04 | `__aenter__`/post-checkout failure → `checkedout()==0`; no cumulative leak | ✓ SATISFIED | `_LEAK_LOOPS=20`; `checkedout()==0` every iteration |
| EDGE-21 | 24-03, 24-04 | Materialized `Table` valid after checkin (no use-after-checkin) | ✓ SATISFIED | `test_table_readable_after_checkin`; reads table after connection scope exit and pool close |
| EDGE-25 | 24-04 | Worker thread ≠ loop thread; no `asyncio`/bare-`to_thread` lint | ✓ SATISFIED | `execute_thread_ids[0] != threading.get_ident()` (loop); `scan_async_package==[]` |
| EDGE-26 | 24-04 | Concurrent coroutine advances while offload blocks | ✓ SATISFIED | Counter increments across `sleep(0)` checkpoints while stub worker blocked |

**Notes on scope decisions (locked in CONTEXT):**
- EDGE-16 DROPPED per D-24-03 (no per-connection lock ships; aliasing rejects, does not queue)
- EDGE-09 cancel-mid-block leg DEFERRED to Phase 25 per D-24-02 (requires `adbc_cancel` wiring)
- ACONN-02 `CancelScope(shield=True)` on checkin ships in Phase 24; cooperative cancel (CANCEL-01..04) deferred to Phase 25

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `_connection.py:218-241` | `__aexit__` | Bypasses `_in_use` guard (WR-01 from code review) | ⚠️ Warning | An aliased task's `__aexit__` can run `fairy.close()` concurrently with an in-flight sibling; only triggers on aliasing misuse (the exact use case `ConnectionBusyError` should prevent). Happy path is unaffected. |
| `_connection.py:134-151` | `cursor()` | Unguarded synchronous FFI call (WR-02 from code review) | ⚠️ Warning | `cursor()` calls `self._fairy.cursor()` on the loop thread without `_in_use` guard; synchronous but touches the C driver. Aliased-task scenario only; correct for all documented usage. |
| `_connection.py:188-207, 218-241` | `close()` / `__aexit__` | Double-close on explicit `close()` + context exit (WR-03 from code review) | ⚠️ Warning | Currently idempotent via SQLAlchemy fairy; would become non-idempotent if fairy internals change. No `_closed` guard on `AsyncConnection`. |
| `_async/_factory.py:104-114` | `close_async_pool` | Not idempotent; re-runs blocking teardown on every call (WR-04 from code review) | ⚠️ Warning | A second `close_async_pool` call re-closes an already-closed ADBC source; driver-dependent whether safe. |

None of the above anti-patterns involve unresolved `TBD`/`FIXME`/`XXX` debt markers, `return null`/`return []` stubs flowing to user-visible output, or hardcoded empty data. They are robustness gaps documented in the code review (24-REVIEW.md) and represent known-acceptable deviations for Phase 24, with fixes expected in later phases. No BLOCKERS.

### Human Verification Required

#### 1. Loop-stability re-run (×20)

**Test:** Run `.venv/bin/python -m pytest tests/async tests/test_async_guard.py -q` twenty consecutive times (or the loop command from 24-04-PLAN acceptance criteria)
**Expected:** 20/20 runs complete with 0 hangs, 0 failures, no watchdog trips — same result as executor's claimed 20/20 runs
**Why human:** MEMORY.md documents a ~33% deadlock that was missed by single-shot verification in Phase 23. The SUMMARY claims ×20 loop pass but that evidence is from the executor's environment. The verifier's single-shot run (358 passed, 2 skipped) is necessary but insufficient given this project's documented history of concurrency flakiness. This check takes ~20 minutes and exceeds the 10-second spot-check constraint.

#### 2. basedpyright strict 0-error confirmation

**Test:** Run `.venv/bin/basedpyright src/adbc_poolhouse/_async/` outside the command sandbox
**Expected:** 0 errors, 0 warnings (strict mode)
**Why human:** basedpyright panics under the macOS command sandbox due to NULL SCDynamicStore (documented in project MEMORY.md as `uv-sandbox-workaround`). The executor ran this successfully outside the sandbox and reported 0 errors on all 5 plans' summaries. This cannot be reproduced inside the sandbox. A human must confirm the claim holds on the current HEAD.

### Gaps Summary

No gaps were found. All 30 requirement IDs (CORE-01..04, APOOL-01..03, ACONN-01..06, ACUR-01..07, EDGE-09..12/15/17/18/21/25/26) are addressed by substantive, wired, data-flowing artifacts. The 4 code-review warnings (WR-01..04) are known robustness gaps, not correctness failures on the documented happy path, and are not blockers for the phase goal.

The two human verification items are process hygiene checks (loop-stability and type-checking outside the sandbox), not evidence of implementation gaps. All codebase artifacts exist, are substantive, are wired, and produce real data.

---

_Verified: 2026-06-27T23:35:10Z_
_Verifier: Claude (gsd-verifier)_
