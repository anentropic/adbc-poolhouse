---
phase: 10-rewrite-integration-tests-to-use-pool-ap
verified: 2026-03-07T00:00:00Z
status: passed
score: 4/4 must-haves verified
---

# Quick Task 10: Rewrite Integration Tests Verification Report

**Task Goal:** Rewrite integration tests to use pool API and wire up conftest fixtures
**Verified:** 2026-03-07
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Integration tests exercise create_pool/close_pool API, not raw driver connections | VERIFIED | Both test files use `pool.connect()` / `conn.cursor()` / `cur.execute()` flow; no `adbc_driver_manager.dbapi` or `adbc_driver_snowflake.dbapi` imports anywhere in integration tests |
| 2 | Tests use session-scoped pool fixtures from conftest.py | VERIFIED | All 4 test functions (`test_connection_health`, `test_arrow_round_trip` in both files) declare `databricks_pool: Any` or `snowflake_pool: Any` as parameters; conftest.py provides both as `scope="session"` fixtures |
| 3 | Cassette markers are preserved so replay works in CI | VERIFIED | `@pytest.mark.databricks` x2 and `@pytest.mark.adbc_cassette("databricks_health")` / `@pytest.mark.adbc_cassette("databricks_arrow_round_trip")` preserved; `@pytest.mark.snowflake` x2 and `@pytest.mark.adbc_cassette("snowflake_health")` / `@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")` preserved |
| 4 | No per-test-file _connect_kwargs / _db_kwargs helpers remain | VERIFIED | `_databricks_connect_kwargs` and `_snowflake_db_kwargs` not found anywhere in integration test files; confirmed by both AST scan and grep |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/integration/conftest.py` | Session-scoped snowflake_pool and databricks_pool fixtures using create_pool | VERIFIED | Contains `def snowflake_pool()` and `def databricks_pool()`, both scope="session", both call `create_pool(config)` and `close_pool(pool)`. Imports `create_pool, close_pool` from `adbc_poolhouse`. |
| `tests/integration/test_databricks.py` | Pool-based Databricks integration tests using databricks_pool | VERIFIED | 2 test functions, both inject `databricks_pool: Any`; use `pool.connect()` -> `cursor()` -> `execute()` -> `fetch*()`; no raw driver code |
| `tests/integration/test_snowflake.py` | Pool-based Snowflake integration tests using snowflake_pool | VERIFIED | 2 test functions, both inject `snowflake_pool: Any`; use `pool.connect()` -> `cursor()` -> `execute()` -> `fetch*()`; no raw driver code |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `test_databricks.py` | `conftest.py` | databricks_pool fixture injection | VERIFIED | `def test_connection_health(databricks_pool: Any)` and `def test_arrow_round_trip(databricks_pool: Any)` — pytest resolves fixture from conftest |
| `test_snowflake.py` | `conftest.py` | snowflake_pool fixture injection | VERIFIED | `def test_connection_health(snowflake_pool: Any)` and `def test_arrow_round_trip(snowflake_pool: Any)` — pytest resolves fixture from conftest |
| `conftest.py` | `src/adbc_poolhouse/_pool_factory.py` | create_pool / close_pool imports | VERIFIED | `from adbc_poolhouse import DatabricksConfig, SnowflakeConfig, close_pool, create_pool` on line 10 |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| QUICK-10 | Rewrite integration tests to use pool API and wire conftest fixtures | SATISFIED | All integration test functions use pool fixtures; conftest wires create_pool/close_pool; no raw driver connections remain |

### Anti-Patterns Found

None. All three files are clean — no TODOs, FIXMEs, placeholders, empty returns, or pass-only bodies.

### Human Verification Required

None required for the automated goals. One known accepted limitation:

**Known / Accepted:** Tests will fail when actually executed in record mode until `pytest-adbc-replay` adds `adbc_clone()` support. This is explicitly acknowledged in the plan and acceptable per user decision. The structural rewrite (the goal of this task) is complete.

### Lint Status

`ruff` was not available in the current environment (Python 3.14 not installed, `uv` unavailable). Structural checks (AST parse, import scan, fixture injection) all pass. The files contain only standard Python constructs that are straightforward to lint.

## Summary

All 4 observable truths verified. All 3 required artifacts exist, are substantive, and are correctly wired. No raw driver connection code remains anywhere in the integration test directory. Cassette markers are intact for CI replay. conftest.py is unchanged and correctly provides session-scoped pool fixtures backed by `create_pool`/`close_pool` from the public API.

---

_Verified: 2026-03-07_
_Verifier: Claude (gsd-verifier)_
