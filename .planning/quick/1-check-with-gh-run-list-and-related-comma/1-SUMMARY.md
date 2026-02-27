---
phase: quick
plan: 1
subsystem: ci
tags: [ci, duckdb, mkdocs, bugfix]
dependency_graph:
  requires: []
  provides: [green-ci-main]
  affects: [ci.yml, pyproject.toml, uv.lock]
tech_stack:
  added: []
  patterns: [uv-extra-install, mkdocs-strict-mode]
key_files:
  created: []
  modified:
    - .github/workflows/ci.yml
    - pyproject.toml
    - uv.lock
decisions:
  - "Pin mkdocs-material>=9.5.0,<9.7.0: 9.7.x unconditionally emits MkDocs 2.0 incompatibility warning; 9.6.23 is the highest compatible release"
  - "Add --extra duckdb to uv sync: _duckdb C extension is bundled inside the duckdb wheel, not a separate adbc-driver-duckdb package"
metrics:
  duration: "4 min"
  completed: "2026-02-27"
---

# Quick 1: Fix CI Failures (duckdb import + mkdocs strict) Summary

**One-liner:** Fixed two independent CI failures — added `--extra duckdb` to CI sync step and pinned `mkdocs-material<9.7.0` to suppress strict-mode warning.

## What Was Fixed

Two independent CI failures were blocking the release pipeline (plan 07-06).

### Failure 1: TestCreatePoolDuckDB — ImportError in CI

**Root cause:** The CI "Sync dependencies" step ran `uv sync --locked --dev` without the `duckdb` optional extra. The `_duckdb` C extension is bundled inside the `duckdb` wheel, so `importlib.util.find_spec("_duckdb")` returned `None` in CI, causing `_resolve_duckdb()` to raise `ImportError: DuckDB ADBC driver not found` for all 5 DuckDB pool creation tests.

**Fix:** Changed `.github/workflows/ci.yml` sync step to:
```yaml
run: uv sync --locked --dev --extra duckdb
```

**Result:** All 16 tests in `tests/test_pool_factory.py` now pass (previously 5 FFFFF + 11 passing).

### Failure 2: Docs build — mkdocs-material 9.7.2 warning in strict mode

**Root cause:** `mkdocs-material` 9.7.2 unconditionally emits the warning "MkDocs 2.0 is incompatible with Material for MkDocs" regardless of the installed mkdocs version. The CI docs job uses `--strict`, which treats any warning as a fatal error.

**Fix:** Pinned `mkdocs-material` in `pyproject.toml` docs dependency group:
```toml
"mkdocs-material>=9.5.0,<9.7.0",
```

Regenerated `uv.lock` — mkdocs-material downgraded from 9.7.2 to 9.6.23.

**Result:** `uv run mkdocs build --strict` completes in 0.84s with no warnings.

## Files Changed

| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Added `--extra duckdb` to sync step |
| `pyproject.toml` | Pinned `mkdocs-material>=9.5.0,<9.7.0` |
| `uv.lock` | Regenerated: mkdocs-material 9.7.2 -> 9.6.23, backrefs 6.2 -> 5.9 |

## Verification

Local checks passed:
- `uv sync --locked --dev --extra duckdb` — succeeded
- `uv run pytest tests/test_pool_factory.py -v` — 16/16 passed
- `uv run mkdocs build --strict` — exits 0, no MkDocs 2.0 warning

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `.github/workflows/ci.yml` contains `--extra duckdb`: confirmed
- `pyproject.toml` contains `mkdocs-material>=9.5.0,<9.7.0`: confirmed
- `uv.lock` regenerated with mkdocs-material 9.6.23: confirmed
- Commit `dddeac0` exists: confirmed
