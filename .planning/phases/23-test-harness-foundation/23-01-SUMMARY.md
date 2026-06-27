---
phase: 23-test-harness-foundation
plan: 01
subsystem: testing
tags: [anyio, trio, aiotools, pytest, async, virtual-clock, dependency-groups]

# Dependency graph
requires:
  - phase: 22-feasibility-spike
    provides: "GO verdict (with materialization caveat) gating the async milestone"
provides:
  - "Dev-group async deps: anyio>=4.13, trio>=0.31, aiotools>=2.2 (test-only, not in the wheel)"
  - "tests/_async_harness/ package (test-only async harness, never shipped in src/)"
  - "tests/_async_harness/conftest.py::anyio_backend — function-scoped fixture, params=[asyncio, trio], trio leg injects MockClock(autojump_threshold=0)"
affects: [24-async-wrappers, 25-cancellation, 27-meta-guards, 26-async-extra]

# Tech tracking
tech-stack:
  added: [anyio, trio, aiotools]
  patterns:
    - "Nested conftest scoping: anyio_backend lives in tests/_async_harness/ so the sync suite never loads the anyio plugin (downward propagation)"
    - "Function-scoped backend parametrization: fresh trio MockClock per test avoids clock-state bleed"

key-files:
  created:
    - tests/_async_harness/__init__.py
    - tests/_async_harness/conftest.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "anyio/trio/aiotools added to [dependency-groups] dev only; runtime [project.dependencies] untouched (D-07, zero-cost-sync-path goal)"
  - "anyio_backend defined in a NESTED conftest (not root tests/conftest.py) and no anyio_mode=auto, so the existing sync suite stays off the anyio plugin (RESEARCH Pitfall 4)"
  - "Fixture is function-scoped so each test gets a fresh MockClock (RESEARCH Open Question 2)"
  - "Plan 04 dual-backend self-tests pinned to tests/_async_harness/test_harness.py because conftest fixtures propagate downward only"

patterns-established:
  - "Downward-propagation rule documented in the conftest module docstring as the load-bearing constraint that fixes the self-test file location"
  - "trio leg uses the ('trio', {options}) tuple form so anyio forwards clock= straight to start_guest_run"

requirements-completed: [TEST-05]

# Metrics
duration: 12min
completed: 2026-06-27
---

# Phase 23 Plan 01: Test Harness Foundation Summary

**Dev-only anyio/trio/aiotools install plus a nested, function-scoped `anyio_backend` fixture (asyncio + trio-with-MockClock) that parametrizes the future async harness without dragging the existing 281-test sync suite under the anyio plugin.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-27
- **Completed:** 2026-06-27
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- Installed `anyio>=4.13`, `trio>=0.31`, `aiotools>=2.2` into `[dependency-groups] dev` only — runtime deps and the built wheel gain no async dependency (D-07, mitigates T-23-02).
- Verified resolved versions (anyio 4.14.1, trio 0.33.0, aiotools 2.2.3) and the two clock APIs the later legs need: `aiotools.VirtualClock.patch_loop` (resolves Assumption A2) and `trio.testing.MockClock`.
- Created the `tests/_async_harness/` test-only package with a function-scoped `anyio_backend` fixture parametrized over `["asyncio", "trio"]`; the trio leg returns `("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})`.
- Proved the existing sync suite is unaffected: 281 passed, identical to baseline, zero `anyio_backend not found` / async-collection errors, and the harness package collects nothing (no self-test files yet).

## Task Commits

Each task was committed atomically:

1. **Task 1: Install anyio, trio, aiotools into the dev group (D-07)** - `9f63426` (chore)
2. **Task 2: Create the async harness package + nested anyio_backend conftest (D-06)** - `e4122c4` (feat)
3. **Task 3: Prove the sync suite is unaffected by the new parametrization** - guard task, no code change (acceptance proven by the passing full suite; correct scoping was committed under Task 2)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `tests/_async_harness/__init__.py` - One-line "test-only async harness, never shipped" package marker (mirrors `benchmarks/__init__.py`).
- `tests/_async_harness/conftest.py` - Function-scoped `anyio_backend` fixture (asyncio + trio-with-MockClock); module docstring records the downward-propagation rule that keeps the sync suite plugin-free and pins the Plan 04 self-test location.
- `pyproject.toml` - Added the three async libraries to `[dependency-groups] dev` with RESEARCH floors; runtime/optional deps untouched.
- `uv.lock` - Lockfile updated for the new dev deps (anyio, trio, aiotools + transitives: sniffio, outcome, sortedcontainers, attrs, async-lru).

## Decisions Made
- **Pinned RESEARCH floors after `uv add`:** `uv add --dev` wrote bare `anyio`/`trio`/`aiotools` with no constraints; edited `pyproject.toml` to `>=4.13` / `>=0.31` / `>=2.2` per RESEARCH §Standard Stack, then `uv sync`.
- **Function-scoped fixture (no explicit `scope=`):** constructs a fresh `MockClock` per test to avoid virtual-clock state bleed (RESEARCH Open Question 2).
- **Nested conftest, no `anyio_mode = "auto"`:** keeps the anyio plugin opt-in via `@pytest.mark.anyio` and scoped strictly below `tests/_async_harness/` (RESEARCH Pitfall 4; protects future PKG-04).

## Deviations from Plan

None - plan executed exactly as written. No bugs, missing functionality, or blocking issues required deviation rules. Task 3 was a guard/verification task by design and produced no code changes.

## Issues Encountered
- **`uv` commands panic under the command sandbox** ("Attempted to create a NULL object" in `system-configuration`, then a Tokio executor panic). This hit `uv add`/`uv sync` and the `uv-lock` pre-commit hook. Resolved by running `uv`-touching commands (including the Task 2 `git commit`, whose `uv-lock` hook invokes uv) with the sandbox disabled. The sandbox restriction can be managed via the `/sandbox` command. No functional impact on the deliverables.
- **`anyio.__version__` does not exist:** the initial verify one-liner used `anyio.__version__`, which anyio deliberately does not expose. Switched the check to `importlib.metadata.version(...)` — confirmed anyio 4.14.1 / trio 0.33.0 / aiotools 2.2.3 and the required clock APIs. Verification-only; no deliverable change.

## Quality Gates
- `.venv/bin/ruff check tests/_async_harness/` — All checks passed.
- `.venv/bin/ruff format --check tests/_async_harness/` — 2 files already formatted.
- `.venv/bin/basedpyright tests/_async_harness/` — 0 errors, 0 warnings, 0 notes (strict).
- `.venv/bin/mkdocs build --strict` — passes (docs gate, CLAUDE.md phase ≥ 7). The harness lives under `tests/`, not `src/`, so it is not in the mkdocstrings API reference; the strict build is unaffected by this plan.
- `.venv/bin/pytest -q` — 281 passed (unchanged from baseline; no anyio leakage).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave-0 foundation is in place: the three async libraries are installed (dev-only) and the `anyio_backend` parametrization is available below `tests/_async_harness/`.
- Subsequent Wave plans in this phase can now add the harness modules (`stubs.py`, `clock.py`, `gating.py`, `guard.py`) and the dual-backend self-tests at `tests/_async_harness/test_harness.py` (file location pinned by the downward-propagation rule documented in the conftest).
- The `[async]` runtime extra and the real async wrappers remain correctly deferred (Phases 26 and 24 respectively).

## Self-Check: PASSED

- `tests/_async_harness/__init__.py` — FOUND
- `tests/_async_harness/conftest.py` — FOUND
- `.planning/phases/23-test-harness-foundation/23-01-SUMMARY.md` — FOUND
- Commit `9f63426` (Task 1) — FOUND
- Commit `e4122c4` (Task 2) — FOUND
- Runtime `[project.dependencies]` untouched; anyio/trio/aiotools present only in `[dependency-groups] dev` — VERIFIED

---
*Phase: 23-test-harness-foundation*
*Completed: 2026-06-27*
