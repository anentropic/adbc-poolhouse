---
phase: 23-test-harness-foundation
plan: 02
subsystem: testing
tags: [anyio, trio, aiotools, threading, virtual-clock, event-gating, stubs, harness]

# Dependency graph
requires:
  - phase: 23-test-harness-foundation
    plan: 01
    provides: "tests/_async_harness/ package + nested function-scoped anyio_backend fixture (asyncio + trio-with-MockClock)"
provides:
  - "tests/_async_harness/stubs.py::BlockingStubCursor — pure-threading dbapi-shaped fake (execute/fetch_arrow_table/close/adbc_cancel + test-only release); D-04 LOCKED attributes (entered, observed_cancel, four call-count counters, execute_thread_ids, max_concurrent_in_execute)"
  - "tests/_async_harness/stubs.py::BlockingStubConnection — connection-level fake with explicit cursors/close_call_count/adbc_cancel_call_count/observed_cancel contract (EDGE-09..12/15/18)"
  - "tests/_async_harness/gating.py::run_blocking — async offload glue (anyio.to_thread.run_sync with explicit limiter=) + entered worker→loop bridge via anyio.from_thread.run_sync (no token)"
  - "tests/_async_harness/clock.py::virtual_clock — backend-dispatching virtual-clock facade (trio no-op / asyncio aiotools.VirtualClock().patch_loop())"
affects: [24-async-wrappers, 25-cancellation, 27-meta-guards]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-threading stub gated by a threading.Event released by release()/adbc_cancel()/close() — event-gating is the primary determinism mechanism (D-02), zero wall-clock sleeps"
    - "entered worker→loop bridge: anyio.from_thread.run_sync from an anyio worker thread needs no token (Pattern 3); the loop-facing gate is an anyio.Event, distinct from the stub's threading.Event of the same name (dual-entered Warning 2)"
    - "Submodule imports (import anyio.to_thread / import anyio.from_thread) instead of 'from anyio import to_thread' — the bare form shadows to a re-exported class under basedpyright strict"
    - "@contextmanager facade typed -> Generator[None] (not Iterator) to satisfy basedpyright reportDeprecated under py3.14"

key-files:
  created:
    - tests/_async_harness/stubs.py
    - tests/_async_harness/gating.py
    - tests/_async_harness/clock.py
    - tests/_async_harness/test_stubs.py
  modified: []

key-decisions:
  - "stubs.py is strictly anyio-free (D-03) — verified by an AST/grep assertion in the task verify; the anyio bridge lives only in gating.py (mitigates T-23-03)"
  - "close() and adbc_cancel() both release the internal threading.Event so no worker is ever stranded (mitigates T-23-04)"
  - "Both the stub's `entered` attribute and run_blocking's `entered` param carry explicit docstring notes recording the threading.Event-sync-signal vs anyio.Event-loop-gate distinction (mitigates T-23-07 / Pitfall 2)"
  - "Task 1 RED and GREEN landed in one commit: the strict basedpyright pre-commit hook rejects a test importing a not-yet-created module, so the failing-test phase was verified live (ModuleNotFoundError) then test+impl committed together"

patterns-established:
  - "Pure-threading self-tests (tests/_async_harness/test_stubs.py) prove the stub's release/cancel/close paths and max_concurrent without anyio — the loop-facing dual-backend assertions are deferred to Plan 04 (test_harness.py) where the anyio_backend machinery is visible"

requirements-completed: [TEST-05]

# Metrics
duration: 4min
completed: 2026-06-27
---

# Phase 23 Plan 02: Test Harness Runtime Machinery Summary

**The pure-threading `BlockingStubCursor`/`BlockingStubConnection` fakes (D-03/D-04 hard contract), the `run_blocking` offload glue that bridges the `entered` signal worker→loop with an explicit limiter (Pattern 3), and the `virtual_clock` backend-dispatching facade (D-01) — the arrange/trigger surface every later EDGE test rides on.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-27
- **Completed:** 2026-06-27
- **Tasks:** 3 (Task 1 TDD)
- **Files created:** 4 (3 harness modules + 1 pure-threading self-test)

## Accomplishments

- **`stubs.py` (Task 1, D-03/D-04):** `BlockingStubCursor` is a pure-`threading` dbapi-shaped fake — `execute`/`fetch_arrow_table` block forever on an internal `threading.Event` until released by the test (`release`), cancelled (`adbc_cancel`, which also flips `observed_cancel`), or closed (`close`). All D-04 LOCKED attributes are present: `entered`, `observed_cancel`, the four call-count counters, `execute_thread_ids`, and the lock-guarded `max_concurrent_in_execute` high-water mark. `BlockingStubConnection` mirrors the connection surface with the explicit `cursors`/`close_call_count`/`adbc_cancel_call_count`/`observed_cancel` contract that EDGE-09..12/15/18 assert against. The module imports no anyio (D-03), verified by an AST/grep assertion.
- **`gating.py` (Task 2, Pattern 3):** `async def run_blocking(stub_call, *args, entered, limiter)` offloads the blocking stub call via `anyio.to_thread.run_sync(..., limiter=limiter)` (the compliant shape the Plan 03 guard enforces) and bridges `entered` to the loop via `anyio.from_thread.run_sync(entered.set)` — no token needed because the worker already runs on an anyio worker thread. This is where anyio lives; the stub stays pure-threading.
- **`clock.py` (Task 3, D-01):** `virtual_clock(anyio_backend_name)` is a `@contextlib.contextmanager` facade: the trio leg is a bare `yield` (the `MockClock` is injected at the runner via the Wave-1 `anyio_backend` fixture), the asyncio leg wraps `aiotools.VirtualClock().patch_loop()` in-body. The docstring documents the runner-injection-vs-in-body-patch asymmetry that drives the dispatch.
- **Dual-`entered` distinction documented in both modules:** the stub's `entered` (a `threading.Event`, the sync signal for pure-threading self-tests) and `run_blocking`'s `entered` (an `anyio.Event`, the loop-facing gate) share a name but are different objects; both docstrings state which is which so a Phase 24 author never awaits a `threading.Event` on the loop (mitigates T-23-07 / Pitfall 2).
- **Pure-threading self-tests (`test_stubs.py`):** 10 tests prove the fresh-state contract, the block→release / block→adbc_cancel / block→close release paths, the recorded thread-id and call counts, and that two concurrent executes lift `max_concurrent_in_execute` to 2 — all without anyio, an event loop, or any wall-clock sleep.

## Task Commits

Each task was committed atomically (sandbox disabled for the `uv`-backed basedpyright pre-commit hook — see Issues):

1. **Task 1: BlockingStubCursor / BlockingStubConnection (D-03/D-04)** — `850500b` (feat). RED phase verified live (`ModuleNotFoundError` against the missing `stubs` module) before test+impl were committed together; see the RED/GREEN note below.
2. **Task 2: run_blocking offload glue + entered worker→loop bridge (Pattern 3)** — `2013112` (feat)
3. **Task 3: virtual_clock backend-dispatching facade (D-01)** — `692278a` (feat)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

## Files Created

- `tests/_async_harness/stubs.py` — pure-threading `BlockingStubCursor` + `BlockingStubConnection` (HARD CONTRACT for Phases 24/25/27); module docstring states the deliberately anyio-free framing and the dual-`entered` warning.
- `tests/_async_harness/gating.py` — `run_blocking` async offload glue + `entered` worker→loop bridge; the module where anyio lives.
- `tests/_async_harness/clock.py` — `virtual_clock` backend-dispatching virtual-clock facade.
- `tests/_async_harness/test_stubs.py` — pure-threading self-tests for the stub release/cancel/close paths and `max_concurrent_in_execute` (the loop-facing dual-backend assertions are deferred to Plan 04).

## Decisions Made

- **Task 1 RED + GREEN in one commit (TDD-vs-strict-hook reconciliation):** the project's `basedpyright` pre-commit hook type-checks the whole project strictly and rejects committing a test that imports a not-yet-created module. The classic "commit the failing test first" RED commit is therefore impossible under the hook. The RED phase was instead verified live — `pytest` against the missing `stubs` module produced a `ModuleNotFoundError` collection error — after which `stubs.py` was implemented (GREEN, 10/10 passing) and test + implementation committed together in `850500b`. RED/GREEN discipline was preserved; only the commit boundary differs.
- **Submodule imports for anyio thread helpers:** `from anyio import to_thread` resolves (under basedpyright strict) to a re-exported class name (`BrokenWorkerInterpreter`) that shadows the `anyio.to_thread` submodule, producing `reportAttributeAccessIssue` on `run_sync`. Switched to `import anyio.to_thread` / `import anyio.from_thread` and fully-qualified calls. The plan's verify substrings (`from_thread.run_sync`, `limiter=limiter`) remain satisfied.
- **`virtual_clock` typed `-> Generator[None]`:** under Python 3.14, basedpyright's `reportDeprecated` flags `@contextmanager` annotated `-> Iterator[...]` and asks for `Generator[...]`. Used `Generator[None]` (a `Yields:` docstring section accompanies it).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `from anyio import to_thread` fails basedpyright strict**
- **Found during:** Task 2
- **Issue:** The RESEARCH Pattern 3 snippet uses `from anyio import to_thread`; under basedpyright strict that name resolves to a re-exported class, not the submodule, so `to_thread.run_sync` raised `reportAttributeAccessIssue` (2 errors) and blocked the strict-clean done criterion.
- **Fix:** Imported the submodules explicitly (`import anyio.to_thread`, `import anyio.from_thread`) and fully-qualified the calls. Behaviour identical; verify substrings still match.
- **Files modified:** `tests/_async_harness/gating.py`
- **Commit:** `2013112`

**2. [Rule 3 - Blocking] `@contextmanager` + `-> Iterator[None]` flagged deprecated (py3.14)**
- **Found during:** Task 3
- **Issue:** basedpyright `reportDeprecated` rejects `@contextmanager` annotated `-> Iterator[None]` under Python 3.14, blocking the strict-clean criterion.
- **Fix:** Changed the return annotation to `-> Generator[None]` (import `collections.abc.Generator`) and used a `Yields:` docstring section.
- **Files modified:** `tests/_async_harness/clock.py`
- **Commit:** `692278a`

These are mechanical type-checker reconciliations of verbatim RESEARCH snippets against the project's strict basedpyright + py3.14 toolchain; no behaviour changed.

## Issues Encountered

- **`uv`-backed pre-commit hooks panic under the command sandbox** (same as Wave 1): the `basedpyright` and `uv-lock` pre-commit hooks invoke `uv`, which panics under the sandbox (`system-configuration` NULL-object panic → Tokio executor panic). All three task commits and the final metadata commit were therefore run with the sandbox disabled. The sandbox can be managed via `/sandbox`. No functional impact on the deliverables.

## Threat Model Coverage

- **T-23-03 (Tampering — anyio in the stub):** mitigated. `stubs.py` is anyio-free, enforced by the Task 1 AST/grep verify.
- **T-23-04 (DoS — stranded blocked worker):** mitigated. Both `close()` and `adbc_cancel()` call `self._event.set()`; the `test_close_releases_blocked_worker` / `test_adbc_cancel_releases_and_flips_observed_cancel` self-tests assert the release paths.
- **T-23-07 (Repudiation — dual-`entered` mis-wiring):** mitigated. The distinction is documented on the stub's `entered` attribute, on `run_blocking`'s `entered` parameter, and in both module docstrings.
- **T-23-05 (Information Disclosure):** accepted — pure in-process test fakes, no external input.

## Quality Gates

- `.venv/bin/ruff check tests/_async_harness/` — All checks passed.
- `.venv/bin/ruff format --check tests/_async_harness/` — all formatted.
- `.venv/bin/basedpyright tests/_async_harness/` — 0 errors, 0 warnings, 0 notes (strict).
- `.venv/bin/pytest tests/_async_harness/` — 10 passed (stub self-tests).
- `.venv/bin/pytest -q` — 291 passed (281 sync baseline + 10 new stub self-tests; no anyio leakage into the sync suite).
- `.venv/bin/mkdocs build --strict` — passes (docs gate, CLAUDE.md phase ≥ 7). The harness lives under `tests/`, not `src/`, so it is not in the mkdocstrings API reference; the strict build is unaffected.

## Known Stubs

None. The `BlockingStub*` classes are *intentional* test fakes (the phase deliverable), not unfinished stubs: `fetch_arrow_table` returns `None` by design (later phases inject a real `pyarrow.Table` where a result is needed), which is documented in its docstring.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- The arrange/trigger surface is complete: `BlockingStubCursor`/`BlockingStubConnection` (HARD CONTRACT), `run_blocking` offload glue + `entered` bridge, and `virtual_clock` are all available below `tests/_async_harness/` and strict-clean.
- **Deferred to Plan 04 (Wave 3):** the loop-facing dual-backend self-tests (`test_harness.py`) that drive `run_blocking` + the `anyio.Event` bridge and assert the virtual clock fires `fail_after` on both legs without wall-clock — these require the `anyio_backend` machinery, which is only visible to test files at/below the conftest's package.
- **Plan 03 (the guard) is independent** and runs in parallel; this plan models the compliant `to_thread.run_sync(..., limiter=...)` call shape it will enforce.

## Self-Check: PASSED

- `tests/_async_harness/stubs.py` — FOUND
- `tests/_async_harness/gating.py` — FOUND
- `tests/_async_harness/clock.py` — FOUND
- `tests/_async_harness/test_stubs.py` — FOUND
- `.planning/phases/23-test-harness-foundation/23-02-SUMMARY.md` — FOUND
- Commit `850500b` (Task 1) — FOUND
- Commit `2013112` (Task 2) — FOUND
- Commit `692278a` (Task 3) — FOUND
- `stubs.py` contains no `import anyio` — VERIFIED

---
*Phase: 23-test-harness-foundation*
*Completed: 2026-06-27*
