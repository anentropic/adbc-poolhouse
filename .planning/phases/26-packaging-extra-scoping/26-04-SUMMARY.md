---
phase: 26-packaging-extra-scoping
plan: 04
subsystem: ci
tags: [ci, github-actions, anyio, uv, no-default-groups, packaging, zero-cost-sync]

# Dependency graph
requires:
  - phase: 26-packaging-extra-scoping
    provides: "Plan 01 [async] extra + relocked uv.lock (the --locked install enforces it)"
  - phase: 23-test-harness
    provides: "anyio/trio/aiotools scoped to the dev dependency-group only (zero runtime async dep)"
provides:
  - "sync-no-anyio CI job proving the sync suite passes with anyio genuinely absent (PKG-04)"
  - "permanent CI guard that find_spec('anyio') is None in the no-dev install (T-26-07)"
affects: [27-test-matrix, future-changes-to-the-async-dependency-scoping]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "uv sync --no-default-groups --extra <backend> to install runtime + a sync backend with the dev group (anyio/trio) excluded"
    - "uv run --with pytest --with pytest-adbc-replay to supply dev-only test tooling to a no-dev environment at run time"
    - "find_spec('anyio') is None assertion step as a false-green guard for an optional-dependency-absent claim"

key-files:
  created: []
  modified:
    - .github/workflows/ci.yml
    - tests/test_pool_factory.py

key-decisions:
  - "Install footprint is --extra duckdb --extra sqlite (both anyio-free, in-proc, no-network sync backends) so the SQLite integration test runs; still excludes anyio via --no-default-groups"
  - "Deselect BOTH tests/async AND tests/_async_harness — the Phase-23 harness conftest imports trio.testing at collection time (RESEARCH/PLAN only named tests/async)"
  - "Deselect the snowflake/databricks markers — their cassette replay keys on the installed cloud driver, which the minimal install omits (CassetteMissError otherwise); they stay covered by the quality job"
  - "Use uv run --with (least lockfile churn) rather than a PEP 735 sync-test group — verified clean against uv 0.9.18"
  - "[Rule 1] TestNoGlobalState made anyio-safe: skip lazy async names whose getattr raises ImportError under the supported [async]-absent install"

patterns-established:
  - "Sibling CI job that diverges from quality only on the install line + adds an absence assertion + deselects async-importing test trees"
  - "Locally simulate a clean-runner CI install via UV_PROJECT_ENVIRONMENT=<throwaway> uv sync, since uv run against the dev .venv does not remove already-installed packages"

requirements-completed: [PKG-04]

# Metrics
duration: ~30min
completed: 2026-06-28
---

# Phase 26 Plan 04: No-anyio CI Guard Job Summary

A dedicated `sync-no-anyio` GitHub Actions job that installs the package with anyio
genuinely absent (`uv sync --locked --no-default-groups --extra duckdb --extra sqlite`),
asserts `importlib.util.find_spec('anyio') is None`, then runs the sync test suite green
(299 passed) with the async-importing test trees and cloud-driver tests deselected —
proving the shipped package has no hard async dependency (PKG-04, D-04).

## What Was Built

- **`.github/workflows/ci.yml` — new `sync-no-anyio` job** (sibling to `quality`):
  - Mirrors `quality`'s `actions/checkout@v6` + `astral-sh/setup-uv@v7`
    (`enable-cache`, `cache-dependency-glob: uv.lock`), pinned to a single
    `python-version: "3.11"`, `timeout-minutes: 15`.
  - Install: `uv sync --locked --no-default-groups --extra duckdb --extra sqlite`.
    `--no-default-groups` drops the `dev` group (the only place anyio/trio/aiotools
    live). `--locked` enforces the Plan-01 relocked `uv.lock`.
  - Assertion step: exits 0 only when `find_spec('anyio') is None` (T-26-07 — fails
    loudly if anyio ever leaks into the no-dev install).
  - Test step: `uv run ... --with pytest --with pytest-adbc-replay pytest tests/
    --ignore=tests/async --ignore=tests/_async_harness -m "not snowflake and not databricks"`.
  - `quality` job left byte-for-byte unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tests/_async_harness` also imports trio at collection time**
- **Found during:** Task 1 local simulation (clean `uv sync` + sync-suite run).
- **Issue:** The PLAN/RESEARCH recipe deselected only `tests/async`, but
  `tests/_async_harness/conftest.py` does `import trio.testing` at module scope —
  collection died with `ModuleNotFoundError: No module named 'trio'` before any test ran.
- **Fix:** Added `--ignore=tests/_async_harness` to the pytest step.
- **Files modified:** `.github/workflows/ci.yml`
- **Commit:** 8a630a6

**2. [Rule 3 - Blocking] Cloud-driver integration tests fail under the minimal install**
- **Found during:** Task 1 local simulation.
- **Issue:** `tests/integration/test_snowflake.py` (and databricks) raised
  `CassetteMissError` — `pytest-adbc-replay` keys the cassette path on the *installed*
  driver module, which the `--extra duckdb` install omits, so the replay path diverged
  from the recorded cassette. These are cross-driver tests, not sync-core tests.
- **Fix:** Deselected via `-m "not snowflake and not databricks"` (they remain covered
  by the `quality` job, which installs all drivers via the dev group's `[all]`).
- **Files modified:** `.github/workflows/ci.yml`
- **Commit:** 8a630a6

**3. [Rule 3 - Blocking] SQLite integration test needs the sqlite driver**
- **Found during:** Task 1 local simulation.
- **Issue:** `TestSQLitePoolFactory::test_sqlite_in_memory_query` runs a real `SELECT 42`
  via the SQLite driver, which `--extra duckdb` alone does not install
  (`ImportError: ADBC driver 'adbc_driver_sqlite' not found`).
- **Fix:** Added `--extra sqlite` to the install (SQLite is anyio-free, in-proc, and
  no-network — the same character as duckdb, so it does not dilute the "no anyio" intent).
- **Files modified:** `.github/workflows/ci.yml`
- **Commit:** 8a630a6

**4. [Rule 1 - Bug] `TestNoGlobalState` crashes under the supported anyio-absent install**
- **Found during:** Task 1 local simulation.
- **Issue:** Both `TestNoGlobalState` tests iterate `for name in dir(adbc_poolhouse):
  getattr(adbc_poolhouse, name)`. With anyio absent, accessing the lazy async entry
  points (`create_async_pool`, `managed_async_pool`, `close_async_pool`) fires the PEP 562
  guard and raises `ImportError`, crashing the test. The `[async]`-absent install is the
  supported sync-only configuration, so this is a genuine bug in the test.
- **Fix:** Wrapped the `getattr` in `try/except ImportError: continue` — names whose
  access raises are by definition not a module-level `QueuePool` instance, preserving the
  POOL-05 "no global state" assertion. Verified to still pass in the with-anyio dev env.
- **Files modified:** `tests/test_pool_factory.py`
- **Commit:** 8a630a6

## How It Was Verified (local)

Because `uv run` against the dev `.venv` does not *remove* already-installed packages,
the no-anyio environment was simulated with a clean throwaway venv:

```
UV_PROJECT_ENVIRONMENT=$TMPDIR/noanyio uv sync --locked --no-default-groups \
    --extra duckdb --extra sqlite          # 11→13 pkgs, no anyio
$TMPDIR/noanyio/.venv/bin/python -c "import importlib.util,sys; \
    sys.exit(0 if importlib.util.find_spec('anyio') is None else 1)"   # RC=0
uv run --no-default-groups --extra duckdb --extra sqlite \
    --with pytest --with pytest-adbc-replay \
    pytest tests/ --ignore=tests/async --ignore=tests/_async_harness \
    -m "not snowflake and not databricks"   # 299 passed, 4 deselected
```

- anyio-absent assertion: **RC=0**, `find_spec('anyio') is None`.
- Sync suite under anyio-absent: **299 passed, 4 deselected, 0 failed**.
- YAML parse: `jobs.sync-no-anyio` valid; contains `--no-default-groups`,
  `tests/async`, `tests/_async_harness`, `find_spec`, and the marker deselection;
  `quality` job's `uv sync --locked --dev --extra duckdb` line unchanged.
- Fixed `TestNoGlobalState` still green in the with-anyio dev env (2 passed).
- Docs gate: `.venv/bin/mkdocs build --strict` succeeded (no `--strict` errors).
- prek hooks (ruff, ruff-format, basedpyright, yaml/json checks, detect-secrets): all passed at commit.

## Pending — Manual-Only Verification (the checkpoint)

PLAN Task 2 is a `checkpoint:human-verify` for the **real GitHub Actions run**, which
cannot execute on this machine. Per the phase's `--auto` policy it is **auto-approved**
on the basis of the fully-passing local simulation above. The single remaining manual
item (26-VALIDATION.md "Manual-Only Verifications: real CI differs from local") is:

> On the next push / PR, open the Actions run and confirm the **Sync suite without
> anyio** job is green — specifically that the "Assert anyio is genuinely absent" step
> exits 0 and the pytest step passes — and that the existing **Quality gates** matrix
> job still passes (the relocked `uv.lock` is enforced there too).

This is expected to pass given the clean-venv simulation already reproduced the
runner's install path. If it fails, the divergence would be a CI-environment specific
detail (e.g. a driver-availability difference) iterable directly on `ci.yml`.

## Requirements Completed

- **PKG-04** — the existing sync test suite passes with anyio uninstalled; a dedicated
  CI job (`sync-no-anyio`) proves there is no hard async dependency, with an explicit
  anyio-absence assertion guarding against a false green.

## Self-Check: PASSED

- `.planning/phases/26-packaging-extra-scoping/26-04-SUMMARY.md` — FOUND
- `.github/workflows/ci.yml` (contains `sync-no-anyio`) — FOUND
- `tests/test_pool_factory.py` — FOUND
- Task 1 commit `8a630a6` — FOUND in git history
