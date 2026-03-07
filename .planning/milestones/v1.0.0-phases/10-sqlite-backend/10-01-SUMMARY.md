---
plan: 10-01
phase: 10-sqlite-backend
status: complete
completed: 2026-03-01
requirements-completed:
  - SQLT-01
  - SQLT-02
---

# Plan 10-01: SQLiteConfig and translate_sqlite()

## What Was Built

Created two new source files implementing the SQLite backend foundation:

- `src/adbc_poolhouse/_sqlite_config.py` — `SQLiteConfig` class (pydantic-settings, env_prefix=`SQLITE_`)
- `src/adbc_poolhouse/_sqlite_translator.py` — `translate_sqlite()` pure function

## Key Decisions

- Followed `_duckdb_config.py` pattern exactly; differences: no `read_only` field, `SQLITE_` env prefix, `adbc_driver_sqlite_init` entrypoint, shared in-memory semantics in error message and docstring
- `translate_sqlite` returns `{"uri": config.database}` — SQLite ADBC driver uses `"uri"` key (not `"path"` like DuckDB)
- pool_size guard message explicitly notes SQLite in-memory is **shared** across connections (contrasted with DuckDB's per-connection isolation)

## Tasks Completed

| Task | Status |
|------|--------|
| Task 1: Create `_sqlite_config.py` | Complete |
| Task 2: Create `_sqlite_translator.py` | Complete |

## Verification

- `SQLiteConfig()` constructs with `database=':memory:'`, `pool_size=1`
- `SQLiteConfig(database=':memory:', pool_size=2)` raises `ValidationError`
- `SQLiteConfig(database='/tmp/x.db', pool_size=5)` succeeds
- `translate_sqlite(SQLiteConfig())` returns `{"uri": ":memory:"}`
- `translate_sqlite(SQLiteConfig(database="/data/x.db"))` returns `{"uri": "/data/x.db"}`
- `ruff` and `basedpyright` pass with 0 errors

## Self-Check: PASSED

## Commits

- `feat(10-01): add SQLiteConfig and translate_sqlite()`

## key-files

### created
- `src/adbc_poolhouse/_sqlite_config.py`
- `src/adbc_poolhouse/_sqlite_translator.py`
