---
phase: "15"
phase_name: "replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests"
status: passed
verified_at: "2026-03-02T22:00:00Z"
---

# Phase 15 Verification

## Phase Goal

> Syrupy is removed; Snowflake integration tests are migrated to cassette-based replay; Databricks cassette tests are added; all four integration tests pass in CI without credentials

## Must-Have Verification

### 1. Syrupy removed

**Check:** `grep -c "syrupy" pyproject.toml` → 0

**Result:** PASS — syrupy is absent from pyproject.toml. `syrupy==5.1.0` removed from uv.lock.

### 2. pytest-adbc-replay installed and configured

**Check:** `uv run python -c "import pytest_adbc_replay; print('OK')"` → OK

**Check:** `[tool.pytest.ini_options]` contains `adbc_auto_patch`, `adbc_cassette_dir`, no `addopts` gate

**Result:** PASS — pytest-adbc-replay 1.0.0a1 installed; both driver modules in adbc_auto_patch; cassette_dir configured; credential gate removed.

### 3. Snowflake integration tests migrated to cassette-based replay

**Check:** `test_snowflake.py` uses `@pytest.mark.adbc_cassette`, no pool fixture dependency

**Check:** No syrupy imports in any .py test file

**Result:** PASS — test_snowflake.py rewritten with `@pytest.mark.adbc_cassette("snowflake_health")` and `@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")`; no syrupy references in any Python source file.

### 4. Databricks cassette tests added

**Check:** `tests/integration/test_databricks.py` exists with `test_connection_health` and `test_arrow_round_trip`

**Result:** PASS — file exists with both tests, both use `@pytest.mark.adbc_cassette`.

### 5. All four integration tests pass without credentials

**Check:** `uv run pytest tests/integration/ -v` (no SNOWFLAKE_ACCOUNT set, no DATABRICKS_* set)

**Result:** PASS
```
tests/integration/test_databricks.py::test_connection_health PASSED
tests/integration/test_databricks.py::test_arrow_round_trip PASSED
tests/integration/test_snowflake.py::test_connection_health PASSED
tests/integration/test_snowflake.py::test_arrow_round_trip PASSED
4 passed in 0.02s
```

### 6. Full test suite passes

**Check:** `uv run pytest -x -q` → 192 passed

**Result:** PASS — 188 unit tests + 4 integration tests; 0 skipped; 0 errors.

### 7. 12 cassette files committed

**Check:** `find tests/cassettes -type f | sort` → 12 files

**Result:** PASS — 12 cassette files across 4 test directories (3 files per test: _query.sql, _result.arrow, _params.json).

### 8. docs build passes

**Check:** `uv run --group docs mkdocs build --strict` → "Documentation built"

**Result:** PASS — docs build completes with no errors.

## Summary

All must-haves verified. Phase 15 goal achieved.

**Score:** 8/8 must-haves verified

**Notable:** The pre-commit basedpyright hook checks all project files, so wave boundary (Plans 15-01, 15-02, 15-03 in separate commits) could not be maintained. All work landed in a single commit `74b4845`. The functional outcomes of all three plans are fully achieved.

**Key implementation discoveries:**
- pytest-adbc-replay cassette naming: `{prefix}_query.sql`, `{prefix}_result.arrow`, `{prefix}_params.json`
- Cassette SQL must be sqlglot-normalized: `sqlglot.parse_one(sql).sql(pretty=True, normalize=True)`
- `_driver_api.py` needed `driver=` keyword arg (not positional) for pytest-adbc-replay compatibility
