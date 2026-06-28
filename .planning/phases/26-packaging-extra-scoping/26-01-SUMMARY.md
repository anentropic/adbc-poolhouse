---
phase: 26-packaging-extra-scoping
plan: 01
subsystem: packaging
tags: [packaging, optional-dependencies, extras, uv-lock, metadata-test]
requires:
  - "pyproject.toml [project.optional-dependencies] existing extras table"
  - "anyio>=4.13 already pinned in [dependency-groups].dev (D-02 floor source)"
provides:
  - "[async] optional-dependency extra pinning anyio>=4.13"
  - "[all] aggregate now includes adbc-poolhouse[async]"
  - "uv.lock coherent with the new extra (uv sync --locked succeeds)"
  - "tests/test_pkg_extra.py metadata assertion (anyio-free, no-anyio-CI-safe)"
affects:
  - "Plan 04 no-anyio CI job (--locked install depends on this relock)"
tech-stack:
  added: []
  patterns:
    - "self-referential extra aggregation: adbc-poolhouse[<name>] inside [all]"
    - "anyio-free metadata test via importlib.metadata.get_all('Provides-Extra')"
key-files:
  created:
    - tests/test_pkg_extra.py
  modified:
    - pyproject.toml
    - uv.lock
decisions:
  - "Pinned anyio>=4.13 (not >=4.0.0) per D-02, matching the dev-group floor; resolves to 4.14.1"
  - "No new third-party package introduced — anyio is an already-audited dev dependency (T-26-01 accept)"
metrics:
  duration: ~10min
  completed: 2026-06-28
---

# Phase 26 Plan 01: [async] Extra Declaration Summary

Declared the `[async]` optional-dependency extra (`anyio>=4.13`), aggregated it into `[all]`, relocked `uv.lock` for `--locked` coherence, and added an anyio-free `importlib.metadata` test proving the extra ships in package metadata.

## What Was Built

- **`pyproject.toml`** — Added `async = ["anyio>=4.13"]` to `[project.optional-dependencies]` (after `sqlite`, before `all`) and appended `"adbc-poolhouse[async]"` as the final element of the `all` aggregate. Additive-only diff; no runtime `dependencies`, dependency-groups, or other extra rows touched.
- **`uv.lock`** — Relocked via `uv lock` so the lockfile carries the new extra (RESEARCH Pitfall 5: the `quality` job's `uv sync --locked` fails on a stale lockfile). Diff is purely additive (the new `async` extra node + `all` self-reference + `provides-extras` line rewrite).
- **`tests/test_pkg_extra.py`** (NEW) — Anyio-free, plain-sync module (only `importlib.metadata`, no `@pytest.mark.anyio`). Two tests: `test_async_extra_is_declared` and `test_all_extra_is_declared`, asserting `Provides-Extra` advertises both extras. Collectable under the Plan 04 no-anyio CI guard job.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Add the [async] extra and relock | ae6287e | pyproject.toml, uv.lock |
| 2 | Metadata-assertion test for the extra | 5405644 | tests/test_pkg_extra.py |

## Verification Results

- `uv lock --locked` → exit 0 (lockfile coherent, no "out of date")
- `grep` → `async = ["anyio>=4.13"]` present; `adbc-poolhouse[async]` present in `[all]`
- `.venv/bin/pytest tests/test_pkg_extra.py -q` → 2 passed
- AST scan of the test module → zero executable `anyio` imports / `pytest.mark.anyio` (anyio-free at import confirmed beyond grep, which only matched docstring prose)
- `.venv/bin/mkdocs build --strict` → exit 0 (phase docs gate green; no prose changed this plan but the gate was run as a phase completion requirement)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Stale installed package metadata required an editable reinstall**
- **Found during:** Task 2
- **Issue:** `tests/test_pkg_extra.py` reads the *installed* `.dist-info` via `importlib.metadata`, which predated the Task 1 pyproject edit, so the first run reported the `async` extra absent. This is a build-metadata-staleness blocker, not a test bug.
- **Fix:** Ran `uv sync --locked --dev --extra duckdb` to refresh the editable install's metadata, after which both assertions pass. No code change — environment refresh only.
- **Files modified:** none (env state only)
- **Commit:** n/a (the test file as written is correct)

## Sandbox / Environment Notes (normal flow, not deviations)

- `uv lock`, `uv sync`, and the basedpyright pre-commit hook (which shells out to `uv`) each panicked under the command sandbox with a macOS `system-configuration`/`dynamic_store` "NULL object" error — uv's network-reachability probe is blocked by the sandbox. Each was re-run with the sandbox disabled and succeeded. The user can manage sandbox restrictions via `/sandbox`.
- The pre-commit `uv-lock` hook passed on both commits, independently confirming pyproject/lockfile coherence.

## Threat Surface

No new security-relevant surface beyond the plan's `<threat_model>`. The `[async]` extra references `anyio`, an already-present, audited `dev`-group dependency (T-26-01 / T-26-SC accept); no new third-party package is introduced and no legitimacy checkpoint was required.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: pyproject.toml
- FOUND: uv.lock
- FOUND: tests/test_pkg_extra.py
- FOUND commit ae6287e
- FOUND commit 5405644
