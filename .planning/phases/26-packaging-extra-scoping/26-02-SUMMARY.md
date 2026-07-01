---
phase: 26-packaging-extra-scoping
plan: 02
subsystem: typing
tags: [typevartuple, pep646, unpack, basedpyright, anyio, offload, async]

# Dependency graph
requires:
  - phase: 24-core-async-wrapper
    provides: "offload() / cancellable_offload() dispatch chokepoint + scan_async_package source guard"
  - phase: 25
    provides: "frozen async module structure; basedpyright strict at 0 errors on _async"
provides:
  - "TypeVarTuple/Unpack-typed offload() in _async/_offload.py (positional args now type-checked at the dispatch boundary)"
  - "TypeVarTuple/Unpack-typed cancellable_offload() in _async/_cancel.py (leading adbc_cancel param preserved outside the variadic)"
  - "tests/test_offload_typing.py — expect-error fixture pinning the PKG-05 win against regression to *args: object"
affects: [phase-27-dual-backend-test-matrix, phase-28-async-docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PEP 646 TypeVarTuple/Unpack variadic forwarder for a generic dispatch helper that has its own keyword-only params (mirrors anyio's own to_thread.run_sync typing)"
    - "basedpyright expect-error fixture: load-bearing # pyright: ignore[reportArgumentType] proves a negative typing case bites (stripping it surfaces the error; a signature regression makes the ignore unnecessary → also red)"

key-files:
  created:
    - tests/test_offload_typing.py
  modified:
    - src/adbc_poolhouse/_async/_offload.py
    - src/adbc_poolhouse/_async/_cancel.py

key-decisions:
  - "Mechanism is TypeVarTuple/Unpack, NOT ParamSpec/Concatenate — ParamSpec does not compile because the typing spec forbids keyword-only params (limiter/on_dispatch/on_abort) after *args: P.args (RESEARCH Pitfall 1)"
  - "Kept the explicit Unpack[_Ts] spelling the plan mandates and suppressed ruff UP044 (which wants inline *_Ts) with a per-line noqa, rather than switching spellings — both type-check at pythonVersion 3.11, Unpack[] is the spelling the critical_constraints pin"
  - "Imported the real offload symbols under TYPE_CHECKING in the fixture so the module is anyio-free at import time and collects in the no-anyio CI env"

patterns-established:
  - "Pattern: tighten a *args: object forwarder to *args: Unpack[_Ts] + fn: Callable[[Unpack[_Ts]], _T], keeping keyword-only config params and any leading positional param outside the variadic"
  - "Pattern: static-typing regression fixture with a runtime sentinel test — the substantive assertion is basedpyright reporting 0 errors with load-bearing reportArgumentType ignores"

requirements-completed: [PKG-05]

# Metrics
duration: 5min
completed: 2026-06-28
---

# Phase 26 Plan 02: Async offload typing tightening (PKG-05) Summary

**Replaced the loose `Callable[..., _T]` + `*args: object` on `offload()` and `cancellable_offload()` with the PEP 646 `TypeVarTuple`/`Unpack` variadic forwarder, so a wrong-typed positional argument at the dispatch boundary is now a basedpyright error instead of being silently accepted — pinned by an expect-error fixture.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-28T08:34:27Z
- **Completed:** 2026-06-28T08:39:44Z
- **Tasks:** 2
- **Files modified:** 3 (2 source signatures + 1 new test)

## Accomplishments
- `offload()` (`_offload.py`) and `cancellable_offload()` (`_cancel.py`) now carry `fn: Callable[[Unpack[_Ts]], _T]` + `*args: Unpack[_Ts]`, with a new `_Ts = TypeVarTuple("_Ts")` beside the existing `_T`. The positional args forwarded to `fn` are now type-checked against `fn`'s signature.
- The keyword-only `limiter`/`on_dispatch`/`on_abort` params (and the leading `adbc_cancel` param of `cancellable_offload`) stay outside the variadic — which is precisely why TypeVarTuple, not ParamSpec, is the correct mechanism.
- The literal `anyio.to_thread.run_sync(lambda: fn(*args), limiter=, abandon_on_cancel=False)` chokepoint body was left byte-for-byte; `scan_async_package` (the source guard) stays clean.
- New `tests/test_offload_typing.py` proves the tightening bites: negative probes pass a `str` where an `int` is expected on both helpers, suppressed by `# pyright: ignore[reportArgumentType]`. The ignores are load-bearing — stripping them surfaces 2 `reportArgumentType` errors, so a regression to `*args: object` would make them *unnecessary* (also red). Positive `assert_type()` calls pin that correct calls keep the exact return type.
- basedpyright strict: `0 errors, 0 warnings, 0 notes` on both `src/adbc_poolhouse/_async` and the new fixture.

## Task Commits

Each task was committed atomically:

1. **Task 1: TypeVarTuple-tighten offload() and cancellable_offload()** - `b7cc931` (feat)
2. **Task 2: Expect-error fixture proving the tightening bites** - `ab19124` (test)

_Task 1 is a typing change (no behavioural runtime change), so it carries a single `feat` commit rather than the RED/GREEN split — the "RED" negative proof is delivered by the Task 2 fixture, which is itself the expect-error regression. See TDD Gate Compliance below._

## Files Created/Modified
- `src/adbc_poolhouse/_async/_offload.py` - `offload()` signature tightened to TypeVarTuple/Unpack; added `_Ts`; extended the `typing` import to `TypeVarTuple, Unpack`; chokepoint body untouched.
- `src/adbc_poolhouse/_async/_cancel.py` - `cancellable_offload()` signature tightened identically, keeping the leading `adbc_cancel: Callable[[], None]` param outside the variadic; body (task group, `BaseExceptionGroup` unwrap) untouched.
- `tests/test_offload_typing.py` (NEW) - static-typing regression fixture; `offload`/`cancellable_offload` imported under `TYPE_CHECKING` (anyio-free at import time); runtime body is a sentinel test.

## Decisions Made
- **TypeVarTuple, not ParamSpec.** The requirement text / ROADMAP said `ParamSpec`/`Concatenate`, but ParamSpec does not compile here: the typing spec forbids keyword-only params after `*args: P.args`, and `offload`/`cancellable_offload` each have keyword-only config params. TypeVarTuple/Unpack (PEP 646) is the correct, idiomatic mechanism — it is what anyio itself uses for `to_thread.run_sync` (RESEARCH-verified).
- **Kept the `Unpack[_Ts]` spelling, suppressed ruff UP044.** The critical_constraints pin the `Unpack[_Ts]` spelling (the plan's "3.11 clarity" rationale). Ruff's `UP044` lint wants the inline `*_Ts` form. Both spellings type-check clean under basedpyright at `pythonVersion = "3.11"`, so honoring the plan's explicit spelling and adding a per-line `# noqa: UP044` was the right reconciliation rather than silently switching spellings (see Deviations).
- **Real symbols imported under `TYPE_CHECKING`.** Keeps the fixture anyio-free at import time so it collects in the no-anyio CI env (Plan 26-04), while still pinning the *real* signatures rather than a stand-in.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Suppressed ruff UP044 to preserve the mandated `Unpack[_Ts]` spelling**
- **Found during:** Task 1 (committing the tightened signatures)
- **Issue:** The pre-commit ruff lint hook raised `UP044 Use \`*\` for unpacking` on `*args: Unpack[_Ts]` in both files, wanting the inline `*_Ts` form. The plan's `critical_constraints` and `<action>` explicitly mandate the `Unpack[_Ts]` spelling (and forbid inline `*_Ts`), so auto-converting would violate the plan; leaving it unsuppressed blocks the commit (the hook fails).
- **Fix:** Added `# noqa: UP044  Unpack[] spelling for 3.11 clarity (PKG-05)` to the `*args: Unpack[_Ts]` line in both `_offload.py` and `_cancel.py`. Empirically verified both spellings type-check clean under basedpyright at `pythonVersion 3.11` (the RESEARCH "inline `*_Ts` is 3.12+" note is inaccurate for the function-signature position, but the plan's mandated spelling is honored regardless).
- **Files modified:** src/adbc_poolhouse/_async/_offload.py, src/adbc_poolhouse/_async/_cancel.py
- **Verification:** `.venv/bin/ruff check` → All checks passed; `.venv/bin/basedpyright src/adbc_poolhouse/_async` → 0 errors.
- **Committed in:** b7cc931 (Task 1 commit)

**2. [Rule 3 - Blocking] Fixture cleanups for lint/checker gates (unused-function ref, D213 docstring, format)**
- **Found during:** Task 2 (committing the fixture)
- **Issue:** basedpyright flagged the static probe function as `reportUnusedFunction`; ruff flagged `D213` on a multi-line test docstring; the ruff-format hook reformatted one call.
- **Fix:** Referenced the probe (`_ = _offload_typing_probe`) so it is not reported unused; shortened the test docstring to a single line (house style); accepted the ruff-format reformat.
- **Files modified:** tests/test_offload_typing.py
- **Verification:** `.venv/bin/basedpyright tests/test_offload_typing.py` → 0 errors; `.venv/bin/ruff check` + `ruff format --check` clean; `pytest` green.
- **Committed in:** ab19124 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking lint/checker gates)
**Impact on plan:** No scope creep. Both deviations are gate-satisfying cleanups; neither alters the typing mechanism or the chokepoint. The `Unpack[]` spelling the plan mandates is preserved.

## TDD Gate Compliance
This plan's frontmatter is `type: execute` (not `type: tdd`), and Task 1 is a pure static-typing change with no runtime behaviour change — so the per-task RED/GREEN/REFACTOR commit split does not apply. The negative ("RED") proof for the tightening is delivered as a first-class artifact by Task 2's expect-error fixture (`test(...)` commit `ab19124`), which is the regression that fails if the signature reverts to `*args: object`. The Task 1 implementation lands as `feat(...)` commit `b7cc931`. The MVP+TDD runtime gate was not signalled active for this phase.

## Issues Encountered
- **basedpyright pre-commit hook panics under the command sandbox.** The hook's `system-configuration` network probe is blocked by the sandbox (`Attempted to create a NULL object` Rust panic → uv Tokio failure), aborting the commit. Resolved by re-running each commit with the sandbox disabled (per the plan's `<sandbox_note>`), NOT by bypassing hooks with `--no-verify`. Both commits then passed all hooks (ruff, basedpyright, blacken-docs, detect-secrets).

## Known Stubs
None — the change is a signature tightening plus a regression fixture; no placeholder data or unwired surfaces.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PKG-05 satisfied: the async offload boundary type-checks forwarded positional args, basedpyright strict stays at 0 errors on `_async`, the source guard is clean, and the negative case is pinned by an expect-error fixture.
- The fixture is anyio-free at import time, so it is ready to collect in the no-anyio CI job (Plan 26-04) once that job lands.
- Docs gate (phase >= 7): `.venv/bin/mkdocs build --strict` passes; no public-symbol docstring prose changed (only the typed `*args` annotation), so no humanizer pass was required.

## Self-Check: PASSED
- FOUND: src/adbc_poolhouse/_async/_offload.py (TypeVarTuple present)
- FOUND: src/adbc_poolhouse/_async/_cancel.py (TypeVarTuple present)
- FOUND: tests/test_offload_typing.py (4 reportArgumentType markers)
- FOUND commit: b7cc931 (feat — Task 1)
- FOUND commit: ab19124 (test — Task 2)
- Acceptance: basedpyright `_async` = 0 errors; basedpyright fixture = 0 errors; source guard 11 passed; ParamSpec absent (0/0); chokepoint literal intact.

---
*Phase: 26-packaging-extra-scoping*
*Completed: 2026-06-28*
