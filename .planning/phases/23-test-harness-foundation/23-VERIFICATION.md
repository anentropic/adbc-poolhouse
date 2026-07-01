---
phase: 23-test-harness-foundation
verified: 2026-06-27T00:00:00Z
status: passed
score: 3/3 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
---

# Phase 23: Test Harness Foundation Verification Report

**Phase Goal:** A deterministic, backend-neutral test harness exists so every later async and EDGE test can arrange/trigger/assert without real sleeps — built before the wrappers it exercises so harness churn never blocks correctness work.
**Verified:** 2026-06-27
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | `BlockingStubCursor`/`BlockingStubConnection` fake implements the dbapi surface (`execute`, `fetch_arrow_table`, `close`, `adbc_cancel`), blocks on a `threading.Event` released only by test or `adbc_cancel`, records thread-id, call counts, `observed_cancel`, an `entered` event, and max-concurrent-in-execute | ✓ VERIFIED | `tests/_async_harness/stubs.py` — pure-`threading` (zero anyio import). `execute`/`fetch_arrow_table` call `_block()` which waits on `self._event` (stubs.py:119). `release()`/`adbc_cancel()`/`close()` are the only releasers. `adbc_cancel` flips `observed_cancel=True` AND sets `_event` (151-162). Records: `execute_thread_ids` (135), `execute_call_count`/`fetch_call_count`/`adbc_cancel_call_count`/`close_call_count`, `observed_cancel`, `entered` (threading.Event, 94/118), `max_concurrent_in_execute` lock-guarded (114-116). All attribute names match D-04 hard contract. 11 stub self-tests pass (`test_stubs.py`). |
| 2 | Event-gating and virtual-clock helpers usable under both asyncio and trio replace wall-clock sleeps in timeout/cancel tests | ✓ VERIFIED | `gating.py` `run_blocking()` offloads via `anyio.to_thread.run_sync(_worker, limiter=limiter)` and bridges `entered` to the loop via `from_thread.run_sync(entered.set)` with no token. `clock.py` `virtual_clock(anyio_backend_name)` is a single backend-dispatching façade: trio leg no-op `yield` (clock injected at runner), asyncio leg wraps `aiotools.VirtualClock().patch_loop()`. All 6 async self-tests run under BOTH asyncio and trio (collect-only confirms `[asyncio]`+`[trio]` ids). `test_trio_virtual_clock[trio]` and `test_asyncio_virtual_clock[asyncio]` both PASS in 0.02s with wall-clock watchdog (`< 5.0s`) proving virtual time. |
| 3 | Source-scan/import-lint guard (asyncio-banned, bare-`to_thread`-without-limiter-banned in `_async/`) is exposed as a callable check the EDGE suite can assert against | ✓ VERIFIED | `guard.py` `scan_async_package(root) -> list[Finding]` — AST walk (`_GuardVisitor`), pure stdlib (`ast`/`dataclasses`/`pathlib`, no anyio/trio/adbc_poolhouse). Bans `import asyncio`/`from asyncio import …` (52-78) and `to_thread.run_sync(...)` lacking `limiter=` (80-93). Returns `[]` on absent/empty dir (156-157). Confirmed live: `scan_async_package('src/adbc_poolhouse/_async/')` → `[]` (dir absent until Phase 24). 5 guard self-tests pass against synthetic source strings (`test_async_guard.py`), incl. documented alias-limitation gap locked as expected behaviour. |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `pyproject.toml` | anyio/trio/aiotools in dev group only, NOT runtime | ✓ VERIFIED | Lines 56-58 inside `[dependency-groups] dev` (group starts L45). `[project].dependencies` = pydantic-settings, sqlalchemy, adbc-driver-manager only — no async deps (D-07 honoured). |
| `tests/_async_harness/__init__.py` | package marker | ✓ VERIFIED | Present, test-only. |
| `tests/_async_harness/conftest.py` | function-scoped `anyio_backend` fixture (asyncio + trio+MockClock), nested so it never reaches root | ✓ VERIFIED | `anyio_backend` fixture params `["asyncio","trio"]`; trio leg returns `("trio", {"clock": MockClock(autojump_threshold=0)})`. Function-scoped per docstring. Lives inside `_async_harness/` — root suite never sees it. |
| `tests/_async_harness/stubs.py` | BlockingStubCursor + Connection (HARD CONTRACT) | ✓ VERIFIED | Contains `max_concurrent_in_execute`; full D-04 surface. |
| `tests/_async_harness/gating.py` | run_blocking offload + entered bridge | ✓ VERIFIED | Contains `from_thread.run_sync` + `to_thread.run_sync(... limiter=)`. |
| `tests/_async_harness/clock.py` | virtual_clock façade | ✓ VERIFIED | Contains `VirtualClock().patch_loop`; backend dispatch on name. |
| `tests/_async_harness/guard.py` | scan_async_package callable | ✓ VERIFIED | `def scan_async_package` returning `list[Finding]`. |
| `tests/test_async_guard.py` | sync guard self-tests | ✓ VERIFIED | 5 tests on synthetic strings, no real `_async/` scan. |
| `tests/_async_harness/test_harness.py` | dual-backend self-tests | ✓ VERIFIED | Contains `anyio_backend_name`; 6 async tests dual-parametrized + collection-level `test_dual_parametrization`. |
| `tests/_async_harness/test_stubs.py` | pure-threading stub self-tests | ✓ VERIFIED | 13 sync tests, no anyio. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| conftest.py | trio.testing.MockClock | anyio_backend tuple option | ✓ WIRED | `("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})` (conftest.py:75). |
| conftest.py | test_harness.py | downward fixture propagation | ✓ WIRED | Self-tests inside same package; collect shows `[asyncio]`/`[trio]` ids — fixture resolves. |
| gating.py | stubs.py | run_blocking offloads stub_call | ✓ WIRED | `to_thread.run_sync(_worker, limiter=limiter)` (gating.py:80). |
| gating.py | anyio.from_thread | entered bridged worker→loop | ✓ WIRED | `from_thread.run_sync(entered.set)` no token (gating.py:77). |
| clock.py | aiotools.VirtualClock | patch_loop() on asyncio leg | ✓ WIRED | `aiotools.VirtualClock().patch_loop()` (clock.py:75). |
| test_harness.py | clock.py / gating.py | virtual_clock + run_blocking | ✓ WIRED | Both imported and exercised under both backends. |
| test_async_guard.py | guard.py | synthetic .py → assert findings | ✓ WIRED | `scan_async_package(tmp_path)` across 5 tests. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Full suite, no real sleeps | `.venv/bin/pytest -q` | 307 passed, 2 skipped in 0.78s | ✓ PASS (matches known-good 307/2, sub-second) |
| All 6 async self-tests dual-parametrized | `pytest test_harness.py --collect-only` | every async test has `[asyncio]` + `[trio]` | ✓ PASS |
| A1 asyncio virtual clock resolves positively | `pytest test_asyncio_virtual_clock[asyncio]` | PASSED in 0.02s | ✓ PASS |
| Trio virtual clock fires on virtual time | `pytest test_trio_virtual_clock[trio]` | PASSED | ✓ PASS |
| Guard no-ops on absent _async/ | `python -c scan_async_package('src/.../_async/')` | `[]` | ✓ PASS |
| Guard + stub self-tests | `pytest test_async_guard.py test_stubs.py` | 15 passed | ✓ PASS |
| basedpyright strict | `.venv/bin/basedpyright tests/_async_harness/ tests/test_async_guard.py` | 0 errors, 0 warnings, 0 notes | ✓ PASS |
| Docs gate (phase>=7) | `.venv/bin/mkdocs build --strict` | built in 1.08s, no warnings/errors | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| TEST-05 | 23-01/02/03/04 | Shared deterministic harness: BlockingStubCursor + event-gating/virtual-clock helpers + source-scan/import-lint guard, no real sleeps | ✓ SATISFIED | All three sub-deliverables present, substantive, wired, and exercised (truths 1-3 above). REQUIREMENTS.md L76 + L178 already mark TEST-05 Complete/Phase 23 — verified independently here. No other requirement maps to this phase (sole requirement per 23-CONTEXT.md). No orphaned requirements. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| (none) | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER in any harness file | — | Clean — completion is auditable. |

### Locked Decisions (23-CONTEXT.md) — Honoured

| Decision | Status | Evidence |
| --- | --- | --- |
| D-01 single backend-dispatching virtual-clock façade | ✓ | `clock.py` dispatches on `anyio_backend_name`. |
| D-02 event-gating primary for cancel determinism | ✓ | `gating.run_blocking` + `entered` bridge; clock covers deadlines. |
| D-03 pure-threading stubs, zero async | ✓ | `stubs.py` imports only `threading`. |
| D-04 records thread-id/counts/observed_cancel/entered/max-concurrent | ✓ | All LOCKED attribute names present. |
| D-05 AST callable returning findings list, no-ops on absent dir | ✓ | `scan_async_package` verified live. |
| D-06 anyio_backend parametrization + dual-leg self-tests | ✓ | conftest + 6 dual-parametrized tests. |
| D-07 anyio/trio/aiotools dev-only, runtime extra deferred | ✓ | dev group only; `[project.dependencies]` clean. |

### Advisory Review Findings (23-REVIEW.md) — Assessment vs Phase Goal

The advisory review reported 0 criticals, 4 warnings, 4 info. Assessed against the phase goal ("a deterministic harness *exists*, built before the wrappers so churn never blocks correctness work"):

| Finding | Nature | Rises to phase-GOAL gap? |
| --- | --- | --- |
| WR-01 sticky `_event` makes cursor single-use | Reuse-safety for Phase 24 execute→fetch reuse | No — forward-looking hardening. The harness *exists* and is deterministic for its self-tests; single-use blocking is not contradicted by any of the 3 success criteria. Phase 24 owns execute→fetch reuse and can re-arm/document then. |
| WR-02 conn.close/adbc_cancel don't propagate to cursors | Matches Plan-02 count-only spec by design | No — explicitly a spec match, not a violation. Phase 24/25 hardening item. |
| WR-03 observed_cancel written outside the matching lock | Torn-read risk only for future concurrent loop-thread readers | No — every current reader synchronizes via Event/join (happens-before holds). Forward-looking. |
| WR-04 run_blocking non-cancellable (no abandon_on_cancel) | Models non-cancellable variant; consumers must release stub | No — self-tests always release/cancel; the real cancellable offload is Phase 24/25's responsibility. |
| IN-01..04 | Info-level documentation/dead-field notes | No. |

**Conclusion:** All 4 warnings are reuse-safety hazards that the green suite does not exercise and that the *consuming* phases (24/25/27) inherit consciously. None falsifies a Phase 23 success criterion. They are legitimate follow-up hardening items, not phase-goal gaps. The review itself states "None block the phase." Recommend Phase 24 planning explicitly inherit WR-01 (execute→fetch cursor reuse) as a known hazard.

### Human Verification Required

None. All three success criteria are programmatically verifiable and verified: the suite runs sleep-free in 0.78s, both backends are confirmed via collected node ids, the A1 asyncio virtual-clock question is resolved by a passing test, and the guard callable is exercised directly. No visual/real-time/external-service behaviour is involved.

### Gaps Summary

No gaps. All 3 ROADMAP success criteria are observably TRUE in the codebase, all 10 artifacts exist / are substantive / are wired / flow real data, all 7 key links are wired, TEST-05 is satisfied, all 7 locked decisions (D-01..D-07) are honoured, no debt markers, basedpyright-strict and the docs gate both pass. All known-good signals (307 passed / 2 skipped sub-second; 6 dual-backend self-tests under asyncio+trio; A1 resolved positively; deps dev-only) confirmed independently. The 4 advisory review warnings are non-blocking forward-looking hardening items for the consuming phases, not phase-goal gaps.

---

_Verified: 2026-06-27_
_Verifier: Claude (gsd-verifier)_
