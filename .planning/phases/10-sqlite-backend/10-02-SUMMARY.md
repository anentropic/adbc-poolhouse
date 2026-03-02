---
plan: 10-02
phase: 10-sqlite-backend
status: complete
completed: 2026-03-01
requirements-completed:
  - SQLT-03
---

# Plan 10-02: Wire SQLiteConfig into Registries

## What Was Built

Wired `SQLiteConfig` into all four integration points:

- `src/adbc_poolhouse/_drivers.py` — added to `_PYPI_PACKAGES`
- `src/adbc_poolhouse/_translators.py` — added `translate_sqlite` dispatch branch
- `src/adbc_poolhouse/__init__.py` — exported in public namespace and `__all__`
- `pyproject.toml` — `sqlite = ["adbc-driver-sqlite>=1.0.0"]` optional extra + `[all]` + dev group
- `uv.lock` — regenerated, includes `adbc-driver-sqlite v1.10.0`

## Key Decisions

- SQLite placed in `_PYPI_PACKAGES` (not `_FOUNDRY_DRIVERS`) — correct, it's a PyPI driver
- `translate_sqlite` branch inserted alphabetically between `RedshiftConfig` and `SnowflakeConfig`
- `SQLiteConfig` added to dev dependency group so integration tests run in dev env

## Tasks Completed

| Task | Status |
|------|--------|
| Task 1: Register in `_drivers.py` and `_translators.py` | Complete |
| Task 2: Export and add sqlite extra | Complete |

## Verification

- `from adbc_poolhouse import SQLiteConfig` succeeds
- `"SQLiteConfig" in adbc_poolhouse.__all__` is True
- `translate_config(SQLiteConfig())` returns `{"uri": ":memory:"}`
- `SQLiteConfig in _PYPI_PACKAGES` is True
- `uv.lock` contains `adbc-driver-sqlite v1.10.0`
- ruff + basedpyright pass on all modified files

## Self-Check: PASSED

## Commits

- `feat(10-02): register SQLiteConfig in _PYPI_PACKAGES and translate_config`
- `feat(10-02): export SQLiteConfig and add sqlite optional extra`

## key-files

### modified
- `src/adbc_poolhouse/_drivers.py`
- `src/adbc_poolhouse/_translators.py`
- `src/adbc_poolhouse/__init__.py`
- `pyproject.toml`
- `uv.lock`
