---
phase: 26-packaging-extra-scoping
verified: 2026-06-28T11:05:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Push the branch / open the PR and open the GitHub Actions run for the commit"
    expected: "The `Sync suite without anyio` job is green — the `Assert anyio is genuinely absent` step exits 0 (find_spec('anyio') is None) and the pytest step passes with tests/async + tests/_async_harness deselected; the existing `quality` matrix job also stays green under the relocked uv.lock"
    why_human: "Real GitHub Actions runners differ from this local host; the job's green status can only be observed on a pushed run. This is the PLAN 04 checkpoint:human-verify task, auto-approved under --auto policy but never actually observed on Actions."
---

# Phase 26: Packaging & Extra Scoping Verification Report

**Phase Goal:** The async surface ships behind an `[async]` extra with zero cost to sync users — `import adbc_poolhouse` succeeds and the sync suite passes with anyio uninstalled — and all async public API is fully typed under basedpyright strict.
**Verified:** 2026-06-28T11:05:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | (PKG-01) Package declares an `[async]` extra pinning `anyio>=4.13` and nothing else; `[all]` includes `adbc-poolhouse[async]`; uv.lock coherent | ✓ VERIFIED | `pyproject.toml:24` `async = ["anyio>=4.13"]`; `pyproject.toml:33` `"adbc-poolhouse[async]"` in `[all]`. `uv lock --locked` → `Resolved 98 packages`, exit 0 (sandbox-disabled; the in-sandbox run panicked on the known macOS system-configuration issue). Metadata test `tests/test_pkg_extra.py` (2 tests) passes. |
| 2 | (PKG-02) `import adbc_poolhouse` succeeds when anyio is unavailable | ✓ VERIFIED | Guard in `src/adbc_poolhouse/__init__.py:73-97` (PEP 562 `__getattr__`, `_LAZY_ASYNC_NAMES`). `tests/test_pkg_import_guard.py::test_sync_import_without_anyio` spawns a subprocess with a `MetaPathFinder` blocking anyio, asserts `create_pool in dir(...)`; passes. |
| 3 | (PKG-03) Accessing an async symbol anyio-absent raises `ImportError` naming the `[async]` extra | ✓ VERIFIED | `__init__.py:91-95` raises `ImportError` with `pip install adbc-poolhouse[async]`. `tests/test_pkg_import_guard.py::test_async_access_without_anyio_raises` asserts `"[async]"` in the message under the meta-path block; passes. |
| 4 | (PKG-04) A CI job installs the package anyio-absent, proves it, and runs the sync suite green | ✓ VERIFIED (artifact) / human-pending (live run) | `.github/workflows/ci.yml:49-92` `sync-no-anyio` job: `uv sync --locked --no-default-groups --extra duckdb --extra sqlite`, a `find_spec('anyio') is None` assertion step, and `pytest tests/ --ignore=tests/async --ignore=tests/_async_harness -m "not snowflake and not databricks"`. YAML parses; quality job unchanged. Real Actions green run is the human checkpoint below. |
| 5 | (PKG-05) All async public API fully typed under basedpyright strict; offload boundary type-checks forwarded args | ✓ VERIFIED | `_offload.py:42-43` + `_cancel.py:43-44` use `Callable[[Unpack[_Ts]], _T]` + `*args: Unpack[_Ts]` (TypeVarTuple, no ParamSpec). `.venv/bin/basedpyright src/adbc_poolhouse/_async` → 0 errors; full basedpyright → 0 errors. CR-01 fix proven: regressing both signatures to `*args: object` makes `tests/test_offload_typing.py` report 2 `reportUnnecessaryTypeIgnoreComment` errors (fixture genuinely bites); restoring → 0 errors. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `pyproject.toml` | `[async]` extra + `[all]` aggregation | ✓ VERIFIED | Lines 24, 33 present; additive diff only |
| `uv.lock` | relocked, coherent | ✓ VERIFIED | `uv lock --locked` exit 0 |
| `tests/test_pkg_extra.py` | metadata assertion, anyio-free | ✓ VERIFIED | 2 tests pass; only `importlib.metadata` imported |
| `src/adbc_poolhouse/_async/_offload.py` | TypeVarTuple `offload` | ✓ VERIFIED | `_Ts = TypeVarTuple`, `Unpack[_Ts]`; chokepoint literal at :105 intact (1 real call) |
| `src/adbc_poolhouse/_async/_cancel.py` | TypeVarTuple `cancellable_offload` | ✓ VERIFIED | Same pattern; leading `adbc_cancel` preserved |
| `tests/test_offload_typing.py` | expect-error fixture that bites | ✓ VERIFIED | File-scoped `reportUnnecessaryTypeIgnoreComment=error` pragma (:33); empirically proven to flag regression (CR-01 fix) |
| `tests/test_pkg_import_guard.py` | subprocess MetaPathFinder regression | ✓ VERIFIED | `MetaPathFinder` blocks anyio; 2 subprocess-isolated tests pass |
| `.github/workflows/ci.yml` | `sync-no-anyio` job | ✓ VERIFIED | Job present; `--no-default-groups`, `find_spec`, async-dir ignore all present |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `[all]` extra | `[async]` extra | `adbc-poolhouse[async]` self-ref | ✓ WIRED | `pyproject.toml:33` |
| `_offload.py offload` | `anyio.to_thread.run_sync` | literal attribute chain | ✓ WIRED | `_offload.py:105` un-aliased; `test_async_guard.py` (11 tests) green |
| import-guard child | `__getattr__` ImportError | `create_async_pool` access under anyio block | ✓ WIRED | Asserts `[async]` substring; subprocess test green |
| `sync-no-anyio` job | `uv sync --no-default-groups` | dev-group-excluding install | ✓ WIRED | `ci.yml:70` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| async surface fully typed (strict) | `.venv/bin/basedpyright src/adbc_poolhouse/_async` | `0 errors, 0 warnings, 0 notes` | ✓ PASS |
| whole project type-checks | `.venv/bin/basedpyright` | `0 errors, 0 warnings, 0 notes` | ✓ PASS |
| phase regression tests | `.venv/bin/pytest test_pkg_import_guard test_pkg_extra test_offload_typing` | `5 passed` | ✓ PASS |
| source guard / chokepoint intact | `.venv/bin/pytest tests/test_async_guard.py` | `11 passed` | ✓ PASS |
| full suite | `.venv/bin/pytest` | `401 passed, 2 skipped` | ✓ PASS |
| lockfile coherent | `uv lock --locked` | `Resolved 98 packages`, exit 0 | ✓ PASS |
| docs gate | `.venv/bin/mkdocs build --strict` | built, no warnings escalated | ✓ PASS |
| CR-01 fixture bites (regression proof) | regress signatures → `basedpyright tests/test_offload_typing.py` | `2 errors (reportUnnecessaryTypeIgnoreComment)`; restored → `0 errors` | ✓ PASS |
| ci.yml YAML valid | `python yaml.safe_load(...)['jobs']['sync-no-anyio']` | `ci-job-ok` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| PKG-01 | 26-01 | `[async]` extra adds `anyio>=4.13` only; `[all]` includes it | ✓ SATISFIED | Truth 1 |
| PKG-02 | 26-03 | `import adbc_poolhouse` works anyio-absent (PEP 562 guard) | ✓ SATISFIED | Truth 2 |
| PKG-03 | 26-03 | Async access anyio-absent raises ImportError naming `[async]` | ✓ SATISFIED | Truth 3 |
| PKG-04 | 26-04 | Sync suite passes with anyio uninstalled (CI job proves it) | ✓ SATISFIED (artifact); live Actions run = human checkpoint | Truth 4 |
| PKG-05 | 26-02 | Async public API fully typed under basedpyright strict | ✓ SATISFIED | Truth 5 |

All 5 declared requirement IDs accounted for. No orphaned requirements (REQUIREMENTS.md maps exactly PKG-01..05 to Phase 26).

**Note on PKG-05 wording:** REQUIREMENTS.md line 68 records the mechanism correction (struck `ParamSpec/Concatenate`, replaced with PEP 646 `TypeVarTuple/Unpack`) with rationale (ParamSpec cannot compile — keyword-only params cannot follow `*args: P.args`). The implementation uses TypeVarTuple/Unpack and is verified to type-check the offload-boundary args under strict, satisfying the requirement intent. No ParamSpec found in `_async`. Not failed for the historical wording.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | None | — | No TODO/FIXME/XXX/TBD/HACK/PLACEHOLDER in any phase-modified file |

### Code Review Disposition (26-REVIEW.md)

The standard review flagged CR-01 as a BLOCKER: the typing fixture was inert because `reportUnnecessaryTypeIgnoreComment` was disabled. **This is now FIXED and independently re-verified.** A file-scoped `# pyright: reportUnnecessaryTypeIgnoreComment=error` pragma (`tests/test_offload_typing.py:33`) makes the negative half bite — empirically confirmed: regressing both offload signatures produces 2 unnecessary-ignore errors. WR-02 (scoped `except ImportError` to `_LAZY_ASYNC_NAMES` in `test_pool_factory.py`) and the IN nits were addressed per the latest commits. No outstanding review BLOCKER.

### Human Verification Required

#### 1. sync-no-anyio CI job is green on GitHub Actions

**Test:** Push the branch (or open the PR), then open the GitHub Actions run for the commit.
**Expected:** The `Sync suite without anyio` job passes — the `Assert anyio is genuinely absent` step exits 0 (`find_spec('anyio') is None`), and the pytest step is green with `tests/async` and `tests/_async_harness` deselected. The existing `quality` matrix job also stays green under the relocked `uv.lock`.
**Why human:** Real GitHub Actions runners differ from the local host; job green status is only observable on a pushed run. This is the PLAN 04 `checkpoint:human-verify` task — auto-approved under the phase `--auto` policy but never actually observed on Actions. All locally-verifiable aspects (YAML validity, install incantation, assertion step, deselection flags, sync suite passing locally with 401 passed) are VERIFIED.

### Gaps Summary

No gaps. All 5 observable truths are VERIFIED against the codebase with empirical evidence:
the `[async]` extra ships and the lockfile is coherent (PKG-01); the PEP 562 guard makes
`import adbc_poolhouse` anyio-free and emits an `[async]`-naming ImportError on async access,
both pinned by subprocess-isolated regression tests (PKG-02/03); the async surface is fully
typed under basedpyright strict with a now-genuinely-biting expect-error fixture (PKG-05);
and the `sync-no-anyio` CI job artifact is correct (PKG-04). The full suite is green
(401 passed, 2 skipped), basedpyright is 0 errors project-wide, and the docs strict gate
passes. The single human item is observing the PKG-04 CI job green on a real Actions run —
an environment that cannot be reproduced locally — which is why overall status is
`human_needed` rather than `passed`.

---

_Verified: 2026-06-28T11:05:00Z_
_Verifier: Claude (gsd-verifier)_
