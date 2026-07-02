---
phase: 32-p2-edge-hardening
verified: 2026-07-02T23:00:00Z
status: passed
score: 7/7 truths verified (Linux-CI gate confirmed by orchestrator via gh + user-approved at blocking checkpoint)
overrides_applied: 0
human_verification_resolved:
  - test: "Confirm Linux-CI run 28622475955 is the authoritative x20 async loop gate for EDGE-24/31/32 on Python 3.11 + 3.14 (0 hangs)"
    outcome: "CONFIRMED — orchestrator ran `gh run view 28622475955` this session: conclusion=success; jobs 'Quality gates (3.11)'=success and 'Quality gates (3.14)'=success (each runs the async suite with ADBC_ASYNC_REPEAT=20), 'Sync suite without anyio'=success. 0 hangs. User typed 'approved' at the Plan 03 Task 2 blocking checkpoint after being shown this green result."
    resolved: "2026-07-02"
---

# Phase 32: P2 Edge Hardening Verification Report

**Phase Goal:** The remaining deferred P2 async edge cases are pinned by deterministic arrange/trigger/assert tests — each run under both asyncio and trio — extending existing chokepoint coverage across the new streaming, ingest, and DataFrame paths plus the __del__ finalizer surface. No new production machinery beyond the finalizers; tests reuse the Phase 23 BlockingStubCursor harness, now that all four new methods exist.
**Verified:** 2026-07-02T23:00:00Z
**Status:** passed
**Re-verification:** No — initial verification (Linux-CI human gate resolved by orchestrator this session)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | EDGE-08: cancel before `adbc_ingest` offload delivered at boundary (`ingest_call_count == 0`), both backends | ✓ VERIFIED | `tests/async/test_edge_checkpoint.py` line 80: `assert sc.ingest_call_count == 0`; file exists, 83 lines, substantive; `concurrency_marks` + `real_clock_watchdog` used; `anyio.fail_after` absent as watchdog; green (2 passed asyncio+trio) |
| 2 | EDGE-13: contextvar set before `fetch_df` is visible to worker thread (copy-in) | ✓ VERIFIED | `tests/async/test_edge_contextvars.py` line 117: `assert seen == ["outer"]`; `sc.on_enter = _probe` wires worker-thread probe; `df_call_count == 1` confirms real path ran; green (4 passed) |
| 3 | EDGE-14: worker contextvar mutation does not leak back to calling task after `fetch_df` | ✓ VERIFIED | `tests/async/test_edge_contextvars.py` line 162: `assert _cv.get() == "outer"`; worker sets `"inner"` inside probe but caller sees `"outer"` after offload returns; green (4 passed) |
| 4 | EDGE-31: `move_on_after` deadline fires on blocked streaming pull AND blocked `adbc_ingest` — `adbc_cancel` once, invalidate once, `cancelled_caught is True`, both backends, x20 | ✓ VERIFIED | `tests/async/test_edge_timeout_precision.py` lines 154-155 (pull) and 186-187 (ingest): `adbc_cancel_call_count == 1`, `invalidate_call_count == 1`; uses `move_on_after(5)` under `virtual_clock` autojump (correct; `move_on_after(0)` delivers before dispatch = EDGE-08, not EDGE-31); `concurrency_marks`; 20 passed locally |
| 5 | EDGE-32: op completing at deadline−ε not over-cancelled — no `adbc_cancel`, no `invalidate`, `cancelled_caught is False`, on streaming pull AND ingest, both backends, x20 | ✓ VERIFIED | `tests/async/test_edge_timeout_precision.py` lines 240-242 (pull) and 278-280 (ingest): `caught is False`, `adbc_cancel_call_count == 0`, `invalidate_call_count == 0`; real-thread releaser outside `virtual_clock` (Pitfall 2 discipline correctly applied); 20 passed locally |
| 6 | EDGE-24: pending offload at loop shutdown (mid-stream + mid-ingest) raises no library-attributable exception; real duckdb drained-close raises nothing with `checkedout() == 0`, both backends, x20 | ✓ VERIFIED (macOS + Linux CI) | `tests/async/test_edge_shutdown.py`: `catch_warnings` idiom + `_offending(caught) == []` assertions at lines 125, 158, 194; `release()` in teardown (Pitfall 3); real `duckdb_async_pool` leg at lines 162-194; 20 passed locally. SUMMARY claims Linux-CI run 28622475955 green (Python 3.11+3.14, 0 hangs) but cannot be confirmed programmatically — routed to human verification |
| 7 | Zero new production machinery — no src/ changes | ✓ VERIFIED | `git diff --name-only b2ffd1a..HEAD -- 'src/'` produced empty output; all 8 commits in this phase are `docs(*)` or `test(*)` prefix, confirming test-only; both Wave 1 SUMMARYs explicitly state "no production change" |

**Score:** 7/7 truths verified (EDGE-24 Linux-CI leg confirmed by orchestrator via `gh run view 28622475955` — Quality gates 3.11 + 3.14 both success, async x20 loop 0 hangs — and user-approved at the mandatory blocking checkpoint)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/async/test_edge_checkpoint.py` | EDGE-08 cancel-at-offload on `adbc_ingest`, dual-backend | ✓ VERIFIED | 83 lines (min 30); contains `ingest_call_count`; `concurrency_marks`; `real_clock_watchdog`; no `anyio.fail_after` |
| `tests/async/test_edge_contextvars.py` | EDGE-13 copy-in + EDGE-14 no-leak-back on `fetch_df`, dual-backend | ✓ VERIFIED | 162 lines (min 30); contains `ContextVar`; `-k`-selectable names (`copied_in`, `no_leak`); no `concurrency_marks` (correct — deterministic); no `real_clock_watchdog` |
| `tests/async/test_edge_timeout_precision.py` | EDGE-31 `move_on_after` + EDGE-32 `deadline_epsilon` on streaming pull + ingest | ✓ VERIFIED | 280 lines (min 60); contains `move_on_after`; `virtual_clock` trigger; `real_clock_watchdog` guard; `concurrency_marks` |
| `tests/async/test_edge_shutdown.py` | EDGE-24 loop-shutdown cleanliness, mid-stream + mid-ingest + real drained-close | ✓ VERIFIED | 194 lines (min 50); contains `catch_warnings`; `concurrency_marks`; real `duckdb_async_pool` leg |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `test_edge_checkpoint.py` | `tests/_async_harness/stubs.py` | `BlockingStubCursor.ingest_call_count` | ✓ WIRED | `assert sc.ingest_call_count == 0` at line 80; `adbc_cancel_call_count`, `invalidate_call_count`, `observed_cancel` also asserted |
| `test_edge_contextvars.py` | `tests/_async_harness/stubs.py` | `sc.on_enter = _probe` (worker-thread hook, `_block` fallback) | ✓ WIRED | `on_enter` set at lines 109, 153; cleared in `finally` at lines 115, 159; `df_call_count` verified at line 118 |
| `test_edge_timeout_precision.py` | `tests/_async_harness/clock.py` | `virtual_clock` deadline trigger | ✓ WIRED | Imported via `importlib` at line 62; used as context manager at lines 145, 178, 234, 272 |
| `test_edge_timeout_precision.py` | `tests/_async_harness/stubs.py` | `record_batch_batches` armed before `fetch_record_batch` (Pitfall 5); `adbc_cancel_call_count` / `invalidate_call_count` | ✓ WIRED | `record_batch_batches = [object()]` at lines 142, 221; assertions at lines 154-155, 186-187, 241-242, 279-280 |
| `test_edge_shutdown.py` | `tests/_async_harness/stubs.py` | `c.release()` in teardown (Pitfall 3 discipline) | ✓ WIRED | `for c in stub_conn.cursors: c.release()` at lines 123 and 157 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All four test modules green (asyncio + trio) | `.venv/bin/pytest tests/async/test_edge_checkpoint.py tests/async/test_edge_contextvars.py tests/async/test_edge_timeout_precision.py tests/async/test_edge_shutdown.py -q` | 20 passed in 0.18s | ✓ PASS |
| mkdocs strict build passes | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` | exit code 0 | ✓ PASS |
| Zero production source changes | `git diff --name-only b2ffd1a..HEAD -- 'src/'` | (empty output) | ✓ PASS |
| PKG-03: no bare `import asyncio` in `_async/` | `grep -rn "^import asyncio" src/adbc_poolhouse/_async/` | (empty — no matches) | ✓ PASS |
| PKG-03: no bare `to_thread` calls in `_async/` | `grep -rn "to_thread" src/adbc_poolhouse/_async/ \| grep -v "_offload"` | Only docstring/comment references, no actual calls | ✓ PASS |
| No `anyio.fail_after` used as watchdog | `grep -n "anyio.fail_after" <all four test files>` | Only in docstring prose (explaining its absence), never in executable code | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| EDGE-08 | 32-01 | Cancel before offload delivered at boundary (adbc_ingest) | ✓ SATISFIED | `test_edge_checkpoint.py::test_cancel_before_ingest_is_clean`; `ingest_call_count == 0`; marked `[x]` in REQUIREMENTS.md |
| EDGE-13 | 32-01 | Contextvar copy-in visible in worker (fetch_df) | ✓ SATISFIED | `test_edge_contextvars.py::test_contextvar_copied_in_to_fetch_df_worker`; `seen == ["outer"]`; marked `[x]` in REQUIREMENTS.md |
| EDGE-14 | 32-01 | Worker contextvar mutation does not leak back to caller | ✓ SATISFIED | `test_edge_contextvars.py::test_contextvar_mutation_does_not_leak_back_from_fetch_df`; `_cv.get() == "outer"` after offload; marked `[x]` in REQUIREMENTS.md |
| EDGE-24 | 32-02 | Pending offload at loop shutdown raises nothing | ✓ SATISFIED (local) / ? CI-pending | `test_edge_shutdown.py`; 3 legs; marked `[x]` in REQUIREMENTS.md; macOS x20 green; Linux-CI pending human confirm |
| EDGE-31 | 32-02 | `move_on_after` still cancels blocked op (streaming + ingest) | ✓ SATISFIED | `test_edge_timeout_precision.py`; `adbc_cancel_call_count == 1`, `invalidate_call_count == 1`; marked `[x]` in REQUIREMENTS.md |
| EDGE-32 | 32-02 | Op completing at deadline−ε not over-cancelled | ✓ SATISFIED | `test_edge_timeout_precision.py`; `cancelled_caught is False`, 0 cancel/invalidate; marked `[x]` in REQUIREMENTS.md |

All six requirement IDs from PLAN frontmatter are accounted for in REQUIREMENTS.md (marked `[x]`). No orphaned requirements.

**Note on EDGE-31 deviation:** The PLAN and RESEARCH skeleton described using `move_on_after(0)` for EDGE-31, but empirical testing revealed that an already-expired scope is delivered at the limiter acquire checkpoint BEFORE the worker dispatches (making it cancel-before-offload = EDGE-08, not blocked-op cancel). The executor correctly used `move_on_after(5)` under the autojumping `virtual_clock` instead — this satisfies the PLAN's stated truth (`adbc_cancel_call_count == 1`, `invalidate_call_count == 1`) and the REQUIREMENTS.md description ("cancels a blocked execute/streaming pull cleanly"). The `contains: "move_on_after"` artifact check is satisfied (24 occurrences). This deviation is a plan-skeleton bug fixed correctly in execution.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER found in any of the four new test files | — | — |

No debt markers, no empty implementations, no hardcoded empty data flowing to assertions. All assertions operate on real observable behaviour over real new-method offload paths.

### Human Verification — RESOLVED

#### 1. Linux-CI x20 Gate for EDGE-24/31/32 — CONFIRMED GREEN

**Test:** Confirm GitHub Actions CI run 28622475955 shows the async suite's `ADBC_ASYNC_REPEAT=20` loop green on Python 3.11 AND 3.14 with 0 hangs.

**Outcome (2026-07-02):** CONFIRMED. The orchestrator ran `gh run view 28622475955` this session: `conclusion=success`; jobs `Quality gates (3.11)`=success, `Quality gates (3.14)`=success (each runs the async suite under `ADBC_ASYNC_REPEAT=20`), `Sync suite without anyio`=success; 0 hangs. The user was shown this green result and typed "approved" at the Plan 03 Task 2 blocking checkpoint (`autonomous: false`). The verifier sub-agent could not reach GitHub, but the orchestrator has and did — so the authoritative gate for the cancel/lost-wakeup races (EDGE-24/31/32) is satisfied on Linux, not only macOS.

---

### Gaps Summary

No gaps found. All six EDGE requirements have passing tests with substantive, wired, non-stub implementations. Zero production code was changed (confirmed via git diff). The Linux-CI corroboration for EDGE-24/31/32 (the phase plan's non-bypassable blocking checkpoint) has been CONFIRMED green (run 28622475955, 3.11 + 3.14, 0 hangs) and user-approved. Phase verification is PASSED.

---

_Verified: 2026-07-02T23:00:00Z_
_Verifier: Claude (gsd-verifier)_
