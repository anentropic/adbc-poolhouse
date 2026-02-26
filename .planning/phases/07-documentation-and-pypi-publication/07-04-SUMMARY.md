---
phase: 07-documentation-and-pypi-publication
plan: "04"
subsystem: infra
tags: [github-actions, pypi, testpypi, oidc, mkdocs, release-pipeline]

# Dependency graph
requires:
  - phase: 07-documentation-and-pypi-publication
    provides: docs build infrastructure (mkdocs, docs group in pyproject.toml)
provides:
  - Complete 7-job release pipeline in .github/workflows/release.yml
  - TestPyPI publish with OIDC before real PyPI publish
  - Smoke test from TestPyPI validating create_pool and DuckDBConfig imports
  - Docs deploy to GitHub Pages gated on successful PyPI publish
  - Version-in-wheel vs git-tag validation in validate job
affects: [pypi-publish, release-process, docs-deploy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Release gate pattern: build -> (validate, changelog) -> publish-testpypi -> smoke-test-testpypi -> publish-pypi -> deploy-docs"
    - "Job-level permissions override for pages:write (workflow-level contents:read is insufficient)"
    - "OIDC publish to TestPyPI using testpypi environment name with pypa/gh-action-pypi-publish"

key-files:
  created: []
  modified:
    - .github/workflows/release.yml

key-decisions:
  - "smoke-test-testpypi imports 'from adbc_poolhouse import create_pool, DuckDBConfig' — not PoolConfig (absent from __all__)"
  - "deploy-docs has job-level pages:write — workflow-level contents:read does not grant Pages write"
  - "Python matrix corrected from ['3.11', '3.14'] to ['3.11', '3.12'] — 3.14 not yet released"

patterns-established:
  - "TestPyPI-first pattern: always smoke-test from TestPyPI before publishing to real PyPI"
  - "Cookiecutter artifact prevention: verify import uses hardcoded package name, not template placeholder"

requirements-completed: [DIST-02, DIST-03]

# Metrics
duration: 2min
completed: 2026-02-26
---

# Phase 7 Plan 04: Fix and Extend Release Pipeline Summary

**7-job release pipeline with TestPyPI smoke-test gate and GitHub Pages docs deploy, fixing cookiecutter placeholder and Python 3.14 matrix bugs**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-02-26T13:23:35Z
- **Completed:** 2026-02-26T13:25:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Fixed cookiecutter placeholder bug (`{{ cookiecutter.package_name }}`) in wheel install check — now uses `adbc_poolhouse`
- Fixed Python matrix from `["3.11", "3.14"]` to `["3.11", "3.12"]` — 3.14 is not released
- Added version-in-wheel vs git-tag check to the validate job
- Added `publish-testpypi` job with OIDC and testpypi environment, running after validate and changelog
- Added `smoke-test-testpypi` job that installs from TestPyPI and imports `create_pool, DuckDBConfig`
- Renamed `publish` job to `publish-pypi`, now gated on smoke test success
- Added `deploy-docs` job with job-level `pages: write` permission, runs after publish-pypi

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix bugs and extend release.yml pipeline** - `7656337` (feat)

**Plan metadata:** (pending final metadata commit)

## Files Created/Modified

- `.github/workflows/release.yml` - Complete 7-job release pipeline with TestPyPI gate and docs deploy

## Decisions Made

- `smoke-test-testpypi` imports `from adbc_poolhouse import create_pool, DuckDBConfig` — `PoolConfig` is not in `__all__` and would cause the smoke test to fail on a valid wheel
- `deploy-docs` uses job-level `permissions: pages: write` — the workflow-level `permissions: contents: read` does not grant Pages write access; job-level permissions override the workflow level
- Python matrix corrected to `["3.11", "3.12"]` — Python 3.14 is not yet released and cannot be tested

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

The `testpypi` and `github-pages` GitHub Actions environments must be created in the repository settings before the pipeline can run:

- Create a `testpypi` environment with OIDC trusted publishing configured for test.pypi.org
- Create a `pypi` environment with OIDC trusted publishing configured for pypi.org
- Enable GitHub Pages via Settings > Pages > Source: "GitHub Actions"

## Next Phase Readiness

- Release pipeline is complete and ready for the first tagged release
- Docs pipeline (`docs.yml`) handles continuous docs deploy on main branch pushes; `deploy-docs` in `release.yml` deploys on each release tag

---
*Phase: 07-documentation-and-pypi-publication*
*Completed: 2026-02-26*
