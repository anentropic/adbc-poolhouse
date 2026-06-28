---
phase: 26-packaging-extra-scoping
reviewed: 2026-06-28T09:07:15Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - src/adbc_poolhouse/_async/_offload.py
  - src/adbc_poolhouse/_async/_cancel.py
  - tests/test_offload_typing.py
  - tests/test_pkg_extra.py
  - tests/test_pkg_import_guard.py
  - tests/test_pool_factory.py
  - pyproject.toml
  - .github/workflows/ci.yml
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 26: Code Review Report

**Reviewed:** 2026-06-28T09:07:15Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 26 ("Packaging & Extra Scoping") tightens the `offload` / `cancellable_offload`
signatures to PEP 646 `TypeVarTuple`/`Unpack`, adds the `[async]` + `[all]` extras,
adds three anyio-free test files, fixes one pre-existing test bug, and adds a
`sync-no-anyio` CI job. The frozen `anyio.to_thread.run_sync` chokepoint body and the
inner-limiter pattern were excluded from review per the phase brief.

The packaging changes (`pyproject.toml`, `ci.yml`), the metadata test
(`test_pkg_extra.py`), the subprocess import-guard test (`test_pkg_import_guard.py`),
and the `test_pool_factory.py` fix are sound. The typing change itself is correct and
does not break the real call sites (basedpyright strict passes at 0 errors).

However, the **typing-regression fixture (`test_offload_typing.py`) does not detect the
regression it claims to pin.** I empirically regressed both signatures back to
`*args: object` and the fixture stayed green (0 errors, 0 warnings). The "expect-error"
half is inert because this project does not enable
`reportUnnecessaryTypeIgnoreComment`. This is the central guarantee PKG-05/D-03 was
meant to lock in, so it is filed as a BLOCKER: the artifact gives false confidence that
a future regression would be caught.

A note on the `_cancel.py` docstring (`from_thread.run_sync` bridge language): it is
stale relative to the synchronous loop-thread mechanism in `_offload.py`, but those
lines were authored in a prior phase (commit `1d642b3`) and are **not** part of this
phase's diff, so they are out of scope and not filed.

## Critical Issues

### CR-01: Typing-regression fixture does not actually detect the regression it pins

**File:** `tests/test_offload_typing.py:53-63` (and `:69-75`)
**Issue:**
The fixture's docstring (lines 10-17) and the inline comment at lines 53-57 claim that
if the offload signature regressed to `*args: object`, the suppressed
`# pyright: ignore[reportArgumentType]` would become *unnecessary* and basedpyright
would flag it via `reportUnnecessaryTypeIgnoreComment`, "turning this fixture red."

This is false in the project's actual configuration. I verified empirically:

1. Regressed BOTH `offload` and `cancellable_offload` back to
   `fn: Callable[..., _T]` / `*args: object`.
2. Ran `.venv/bin/basedpyright tests/test_offload_typing.py`.
3. Result: `0 errors, 0 warnings, 0 notes` — the fixture stayed green.

Root cause: `reportUnnecessaryTypeIgnoreComment` is **not active** in this project.
basedpyright strict mode does not enable it, and `pyproject.toml [tool.basedpyright]`
does not set it. A standalone probe confirms this — a clearly-unnecessary
`y: int = x  # pyright: ignore[reportAssignmentType]` placed inside `tests/` also
reports `0 errors, 0 warnings` under the project config. (A sanity check with a real
type error *is* caught, so basedpyright is genuinely analyzing the file — the
unnecessary-ignore detection is simply off.)

The positive `assert_type(good, str)` / `assert_type(bad, str)` calls do not catch the
regression either: under the loose `*args: object` signature the return type is still
`_T == str`, so all four `assert_type` calls still pass. Net effect: the entire
fixture would remain green after a full PKG-05 regression, so CI would never go red —
the opposite of the documented "locks that win in" guarantee.

**Fix:** Enable the rule so the expect-error mechanism actually bites. Add to
`pyproject.toml`:

```toml
[tool.basedpyright]
pythonVersion = "3.11"
typeCheckingMode = "strict"
include = ["src", "tests"]
reportPrivateUsage = false
reportUnnecessaryTypeIgnoreComment = "error"  # makes test_offload_typing.py bite
```

Then re-verify by temporarily regressing the signature and confirming basedpyright
reports the now-unnecessary ignore as an error. (Note: turning this on project-wide may
surface other currently-unnecessary ignores elsewhere; audit and clean those, or scope
the enforcement.) Alternatively, if a project-wide rule change is undesirable, replace
the expect-error approach with a direct positive assertion that the *argument* type is
checked — e.g. an `assert_type` on a value derived from `_Ts` binding, or a
basedpyright "expected-error" mechanism the project already trusts — so the regression
detector does not depend on a disabled rule.

## Warnings

### WR-01: Fixture docstring asserts a CI guarantee that does not hold

**File:** `tests/test_offload_typing.py:10-23`
**Issue:**
Independent of the mechanism fix (CR-01), the module docstring states as fact:
"basedpyright reports `0 errors` on this file ONLY while the tightened signature is in
place." That is incorrect — basedpyright reports 0 errors on this file *whether or not*
the signature is tightened (demonstrated above). Leaving the prose unchanged after CR-01
would mislead the next maintainer into trusting a guard that is verified, when in fact
the wording over-claims. The docstring drives reader trust, so a false invariant in it
is a maintainability defect even if the runtime sentinel still passes.
**Fix:** After enabling `reportUnnecessaryTypeIgnoreComment` (CR-01), the claim becomes
true and no prose change is needed. If CR-01 is instead resolved by a different
mechanism, update this docstring so it describes the mechanism that actually fails on
regression. Do not ship the current prose with the current (inert) mechanism.

### WR-02: `except ImportError: continue` is broader than the lazy-async case it targets

**File:** `tests/test_pool_factory.py:115-117` and `:128-130`
**Issue:**
The fix swallows *any* `ImportError` from `getattr(adbc_poolhouse, name)` over every
name in `dir()`. The intent (per the new comment) is narrowly the lazy PEP 562 async
entry points raising under an anyio-absent install. But the bare `except ImportError`
would also silently skip a name whose access raised `ImportError` for an *unrelated*
reason (e.g. a genuinely broken lazy attribute introduced later), so a real regression
in the package's public surface could pass this "no global state" test unnoticed. The
test still asserts the QueuePool invariant only on names it could read, weakening it.
**Fix:** Scope the skip to the known lazy names so an unexpected `ImportError` still
fails loudly:

```python
import adbc_poolhouse
_lazy = adbc_poolhouse._LAZY_ASYNC_NAMES  # noqa: SLF001
for name in dir(adbc_poolhouse):
    try:
        val = getattr(adbc_poolhouse, name)
    except ImportError:
        if name in _lazy:
            continue
        raise
    assert not isinstance(val, sqlalchemy.pool.QueuePool), (
        f"Module-level QueuePool found: {name}"
    )
```

### WR-03: No CI job type-checks the no-anyio surface, so the lazy-import typing path is unverified there

**File:** `.github/workflows/ci.yml:49-92`
**Issue:**
The `sync-no-anyio` job runs the sync pytest subset but does **not** run basedpyright.
basedpyright runs only in the `quality` job, which uses the full `--dev` (anyio-present)
environment. `test_offload_typing.py` imports the real `offload`/`cancellable_offload`
symbols under `TYPE_CHECKING`, so its static assertions are only ever checked with anyio
installed. The phase's stated win is that the sync surface stays clean without anyio; the
typing guarantee for that surface is therefore asserted in an environment that does not
match the no-anyio install the job exists to protect. This is a coverage gap, not a
crash, but it means the PKG-05 fixture's value is concentrated entirely in the one
job that CR-01 shows is currently inert.
**Fix:** This is acceptable if CR-01 is fixed (basedpyright in the `quality` job would
then genuinely gate the regression). If desired, add a basedpyright invocation scoped to
the anyio-free fixtures in the `sync-no-anyio` job, or document explicitly that static
typing of the async surface is intentionally validated only in the anyio-present job.

## Info

### IN-01: `# noqa: UP044` rationale is correct but worth a one-line cross-reference

**File:** `src/adbc_poolhouse/_async/_offload.py:43`, `src/adbc_poolhouse/_async/_cancel.py:44`
**Issue:**
The `*args: Unpack[_Ts]  # noqa: UP044` suppresses ruff's preference for the
`*args: *_Ts` star syntax, justified as "Unpack[] spelling for 3.11 clarity (PKG-05)".
Both copies are identical and correct. Minor: the rationale lives only inline; a reader
auditing why the codebase avoids the modern `*_Ts` spelling has to infer it. Optional.
**Fix:** None required. Optionally hoist the rationale to a one-line module comment so
both call sites share a single source of truth.

### IN-02: Two `dir()`-iteration loops in `TestNoGlobalState` are near-duplicates

**File:** `tests/test_pool_factory.py:113-120` and `:127-132`
**Issue:**
`test_import_creates_no_pool_or_connection` and `test_reimport_creates_no_pool` now
carry the same `for name in dir(...): try/except ImportError` scan with only the assert
message differing. After applying the WR-02 fix the duplication grows. Low priority.
**Fix:** Optionally extract a small helper
`_assert_no_module_level_queuepool(module)` and call it from both tests so the
ImportError-skip policy lives in one place.

---

_Reviewed: 2026-06-28T09:07:15Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
