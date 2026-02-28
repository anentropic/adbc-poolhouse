---
phase: quick-7
plan: 7
subsystem: docs
tags: [readme, pypi, packaging, docs]
dependency_graph:
  requires: []
  provides: [consumer-readme, pypi-urls]
  affects: [README.md, pyproject.toml]
tech_stack:
  added: []
  patterns: []
key_files:
  created: []
  modified:
    - README.md
    - pyproject.toml
decisions:
  - "[quick-7]: README.md replaces dev-only content with tagline, DuckDB example, warehouse list, and four links — development setup instructions belong in CONTRIBUTING, not the consumer README"
  - "[quick-7]: pyproject.toml [project.urls] added between [project.optional-dependencies] and [build-system] per PEP 621 convention"
metrics:
  duration: "~1 min"
  completed: "2026-02-28"
  tasks_completed: 2
  files_modified: 2
---

# Quick Task 7: Improve README and Add Project Homepage Summary

Consumer-facing README with install command, DuckDB quick example, and four documentation links; pyproject.toml [project.urls] table with Homepage, Documentation, Source, and Changelog entries for the PyPI sidebar.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Add [project.urls] to pyproject.toml | 19f3a11 | pyproject.toml |
| 2 | Rewrite README.md as consumer-facing landing page | 19e9733 | README.md |

## What Was Built

**pyproject.toml** — Added `[project.urls]` table between `[project.optional-dependencies]` and `[build-system]`:

```toml
[project.urls]
Homepage = "https://anentropic.github.io/adbc-poolhouse/"
Documentation = "https://anentropic.github.io/adbc-poolhouse/"
Source = "https://github.com/anentropic/adbc-poolhouse"
Changelog = "https://anentropic.github.io/adbc-poolhouse/changelog/"
```

**README.md** — Replaced the dev-only content (quality gates, setup commands) with:
- Tagline: "One config in, one pool out"
- `pip install adbc-poolhouse` with pointer to docs for driver extras
- Complete DuckDB example (no credentials required) mirroring docs/src/index.md
- One-line warehouse list (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL / Azure SQL / Fabric)
- Four links (Documentation, Changelog, Source, PyPI)
- MIT license line

## Verification

- `pyproject.toml` has `[project.urls]` with all four entries confirmed by grep
- `uv run mkdocs build --strict` passes with zero warnings or errors
- No promotional language, AI vocabulary, or em dash overuse in README prose
- Development/Quality Gates/Setup section removed entirely

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- README.md exists: confirmed
- pyproject.toml [project.urls] section: confirmed (1 section, 4 entries)
- Commits exist: 19f3a11 (pyproject.toml), 19e9733 (README.md) — confirmed
- mkdocs build --strict: passed with zero warnings
