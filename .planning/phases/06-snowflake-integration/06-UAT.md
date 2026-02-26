---
status: complete
phase: 06-snowflake-integration
source: [06-01-SUMMARY.md]
started: 2026-02-25T16:10:00Z
updated: 2026-02-26T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Default pytest run excludes Snowflake tests
expected: Run `uv run pytest -q` — it completes without any Snowflake connection attempt. You should see all existing tests pass with "2 deselected" in the output (the Snowflake tests excluded by addopts).
result: pass

### 2. Snowflake tests are collected but not run by default
expected: Run `uv run pytest --collect-only -q 2>&1 | grep snowflake` — you should see `test_connection_health` and `test_arrow_round_trip` listed as collected items.
result: issue
reported: "saw tests/test_drivers.py::TestResolvePyPIDriver::test_path2_snowflake_missing_returns_package_name, test_path1_snowflake_found_returns_driver_path, tests/test_translators.py::TestTranslateConfig::test_snowflake_dispatch — integration tests not visible"
severity: minor

### 3. Snowflake tests skip gracefully without credentials
expected: Run `uv run pytest --override-ini="addopts=" -m snowflake -q` (without SNOWFLAKE_ACCOUNT set) — the 2 Snowflake tests should be **skipped** (not errored), with output like "2 skipped" and a message about SNOWFLAKE_ACCOUNT not set.
result: pass

### 4. .gitignore protects credentials
expected: Open `.gitignore` and search for `.env.snowflake` — you should find two entries: `.env.snowflake` and `*.env.snowflake`, preventing credential files from being committed.
result: pass

### 5. CONTRIBUTING.md documents snapshot recording workflow
expected: Open `CONTRIBUTING.md` — it should have a "How to Record Snowflake Snapshots" section with the exact command `pytest --override-ini="addopts=" -m snowflake --snapshot-update` and instructions for creating `.env.snowflake`.
result: pass

### 6. prek gate passes on all new files
expected: Run `uv run prek` — it should exit 0 with all hooks passing (ruff, basedpyright, detect-secrets). No violations from the new integration test files.
result: pass

## Summary

total: 6
passed: 5
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Running `pytest --collect-only -q | grep snowflake` shows test_connection_health and test_arrow_round_trip as collected items"
  status: failed
  reason: "User reported: saw only unit tests with snowflake in the name (test_drivers, test_translators) — integration tests not visible"
  severity: minor
  test: 2
  artifacts: []
  missing: []
