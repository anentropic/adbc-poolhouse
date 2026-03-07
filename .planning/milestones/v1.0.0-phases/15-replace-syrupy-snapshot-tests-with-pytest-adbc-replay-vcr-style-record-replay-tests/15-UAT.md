---
status: diagnosed
phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests
source: [15-01-SUMMARY.md, 15-02-SUMMARY.md, 15-03-SUMMARY.md]
started: 2026-03-07T00:00:00Z
updated: 2026-03-07T00:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Syrupy fully removed
expected: `uv run python -c "import syrupy"` fails with ModuleNotFoundError. No syrupy references remain in pyproject.toml dev dependencies.
result: pass

### 2. pytest-adbc-replay installed and configured
expected: `uv run python -c "import pytest_adbc_replay"` succeeds. pyproject.toml contains `adbc_auto_patch` and `adbc_cassette_dir = "tests/cassettes"` in `[tool.pytest.ini_options]`.
result: pass

### 3. Integration tests pass without credentials (replay mode)
expected: `uv run pytest tests/integration/ -v` runs 4 integration tests (2 Snowflake, 2 Databricks) and all pass without any real database credentials configured.
result: issue
reported: "Snowflake cassettes missing (removed in 6333ade). Databricks 2/2 pass, Snowflake 2/2 fail with CassetteMissError. Also, unit tests (test_configs, test_translators) contaminated by env vars when credentials are loaded from .env — DatabricksConfig/SnowflakeConfig Pydantic settings pick up env vars in unit tests that expect clean state. Recording Snowflake cassettes fails with 'account is empty' when .env has empty SNOWFLAKE_ACCOUNT."
severity: blocker

### 4. Full test suite passes
expected: `uv run pytest` runs the complete test suite (~192 tests) with 0 failures.
result: issue
reported: "6 failures: 2 Snowflake integration (missing cassettes, account is empty), 2 unit config tests (env var contamination — SecretStr not None, DatabricksConfig doesn't raise), 2 unit translator tests (env var contamination — extra keys in Snowflake dict, Databricks doesn't raise). Same root causes as test 3."
severity: blocker

### 5. Cassette files present with correct structure
expected: `tests/cassettes/` contains 4 subdirectories (snowflake_health, snowflake_arrow_round_trip, databricks_health, databricks_arrow_round_trip), each with `000_query.sql`, `000_result.arrow`, `000_params.json` files.
result: pass

### 6. No credential gate in CI config
expected: pyproject.toml `[tool.pytest.ini_options]` does NOT contain `addopts = "-m snowflake"` or similar credential-gating. Integration tests run by default.
result: pass

## Summary

total: 6
passed: 4
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "4 integration tests (2 Snowflake, 2 Databricks) pass without credentials in replay mode"
  status: failed
  reason: "User reported: Snowflake cassettes missing (removed in 6333ade). Databricks pass, Snowflake fail with CassetteMissError. Unit tests contaminated by env vars when .env credentials present. Recording Snowflake cassettes fails with 'account is empty'."
  severity: blocker
  test: 3
  root_cause: "Synthetic Snowflake cassettes removed in commit 6333ade without recording real replacements. Working tree reverted credential loading from .env.snowflake back to .env, but .env may have empty SNOWFLAKE_ACCOUNT. The test helper _snowflake_kwargs() catches the exception and returns {}, but in recording mode the real driver needs valid credentials."
  artifacts:
    - path: "tests/integration/test_snowflake.py"
      issue: "Loads .env instead of .env.snowflake (inconsistent with committed HEAD which uses .env.snowflake)"
    - path: "tests/cassettes/"
      issue: "Missing snowflake_health/ and snowflake_arrow_round_trip/ subdirectories"
  missing:
    - "Record real Snowflake cassettes: set credentials in .env.snowflake, run pytest --adbc-record=once -m snowflake"
    - "Restore .env.snowflake loading in test_snowflake.py (match conftest pattern)"
    - "Commit recorded cassette files to git"

- truth: "Full test suite (~192 tests) passes with 0 failures"
  status: failed
  reason: "User reported: 6 failures — 2 Snowflake integration (missing cassettes), 2 config unit tests (env var contamination from .env), 2 translator unit tests (env var contamination). Same root causes as test 3."
  severity: blocker
  test: 4
  root_cause: "pydantic-settings reads env vars by default during __init__. No global pytest fixture clears warehouse-specific env vars before unit tests. When .env is loaded (for cassette recording), SNOWFLAKE_* and DATABRICKS_* vars leak into os.environ and are picked up by unit tests that expect clean state. Pre-existing latent bug exposed by Phase 15 cassette workflow."
  artifacts:
    - path: "tests/test_configs.py"
      issue: "test_basic_construction expects password=None but SNOWFLAKE_PASSWORD env var populates it; test_databricks_no_args_raises expects ValidationError but DATABRICKS_* env vars satisfy requirements"
    - path: "tests/test_translators.py"
      issue: "test_account_only gets extra keys from SNOWFLAKE_USER/PASSWORD env vars; test_no_args_raises expects ValidationError but DATABRICKS_* env vars satisfy requirements"
  missing:
    - "Add autouse fixture to tests/conftest.py that clears all warehouse env prefixes (SNOWFLAKE_, DATABRICKS_, DUCKDB_, etc.) via monkeypatch.delenv before each unit test"
