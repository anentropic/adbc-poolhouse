---
phase: quick-8
plan: 8
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_configs.py
  - tests/test_translators.py
  - tests/test_drivers.py
  - docs/src/guides/mysql.md
autonomous: true
requirements: []

must_haves:
  truths:
    - "All 11 config classes have env-prefix and constructor tests (not just smoke tests)"
    - "translate_config() dispatch is tested for every backend"
    - "resolve_driver() is tested for every Foundry and PyPI driver"
    - "MySQL guide URI example is consistent with Databricks guide (SecretStr shown)"
    - "uv run pytest tests/ passes with no new failures"
  artifacts:
    - path: "tests/test_configs.py"
      provides: "Config tests for all 11 backends"
    - path: "tests/test_translators.py"
      provides: "Translator dispatch tests for all 11 backends"
    - path: "tests/test_drivers.py"
      provides: "Driver resolution tests for all Foundry and PyPI backends"
    - path: "docs/src/guides/mysql.md"
      provides: "MySQL guide with consistent SecretStr URI example"
  key_links:
    - from: "tests/test_configs.py"
      to: "adbc_poolhouse.*Config"
      via: "env prefix tests using monkeypatch"
      pattern: "monkeypatch\\.setenv"
    - from: "tests/test_translators.py"
      to: "adbc_poolhouse._translators.translate_config"
      via: "dispatch tests"
      pattern: "translate_config.*translate_"
    - from: "tests/test_drivers.py"
      to: "adbc_poolhouse._drivers.resolve_driver"
      via: "Foundry short-name and PyPI package-name assertions"
      pattern: "resolve_driver"
---

<objective>
Fill config/translator/driver test coverage gaps and fix one docs inconsistency.

Purpose: The review identified systematic under-testing of Foundry backends (Redshift, Trino, MSSQL) and incomplete dispatch coverage in translate_config() and resolve_driver(). The MySQL guide also shows a plain string for a SecretStr field, inconsistent with every other Foundry guide.
Output: Extended test files with full per-backend coverage plus corrected MySQL guide.
</objective>

<execution_context>
@/Users/paul/.claude/get-shit-done/workflows/execute-plan.md
@/Users/paul/.claude/get-shit-done/templates/summary.md
@.claude/skills/adbc-poolhouse-docs-author/SKILL.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md

@tests/test_configs.py
@tests/test_translators.py
@tests/test_drivers.py
@docs/src/guides/mysql.md

<interfaces>
<!-- Current coverage gaps identified by review. Do not re-implement what exists — append only. -->

<!-- test_configs.py existing classes:
  TestBaseWarehouseConfig, TestDuckDBConfig, TestSnowflakeConfig,
  TestApacheBackendConfigs (BigQuery/PostgreSQL/FlightSQL smoke tests),
  TestPostgreSQLConfig (full coverage), TestFoundryBackendConfigs (sparse),
  TestSQLiteConfig (full), TestMySQLConfig (full)
-->

<!-- test_translators.py existing classes:
  TestDuckDBTranslator, TestSnowflakeTranslator, TestBigQueryTranslator,
  TestPostgreSQLTranslator, TestFlightSQLTranslator, TestDatabricksTranslator,
  TestRedshiftTranslator, TestTrinoTranslator, TestMSSQLTranslator,
  TestTranslateConfig (only duckdb_dispatch, snowflake_dispatch),
  TestMySQLTranslator, TestSQLiteTranslator
-->

<!-- test_drivers.py existing classes:
  TestResolveDuckDB (full), TestResolvePyPIDriver (snowflake only),
  TestResolveFoundryDriver (databricks + redshift only),
  TestResolveDriverEdgeCases, TestCreateAdbcConnectionFoundryNotFound
-->

<!-- Config env_prefixes (from source):
  REDSHIFT_, TRINO_, MSSQL_, FLIGHTSQL_ -->

<!-- Foundry backends in _FOUNDRY_DRIVERS:
  DatabricksConfig("databricks"), MSSQLConfig("mssql"), MySQLConfig("mysql"),
  RedshiftConfig("redshift"), TrinoConfig("trino") -->

<!-- PyPI backends in _PYPI_PACKAGES:
  SnowflakeConfig("adbc_driver_snowflake"), BigQueryConfig("adbc_driver_bigquery"),
  PostgreSQLConfig("adbc_driver_postgresql"), FlightSQLConfig("adbc_driver_flightsql"),
  SQLiteConfig("adbc_driver_sqlite") -->
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fill config class test gaps for Redshift, Trino, MSSQL, FlightSQL</name>
  <files>tests/test_configs.py</files>
  <behavior>
    - TestRedshiftConfig: uri mode constructs, aws_secret_access_key is SecretStr (masked in repr), env prefix loads host+user+database (REDSHIFT_HOST/USER/DATABASE), env prefix pool_size (REDSHIFT_POOL_SIZE)
    - TestTrinoConfig: uri mode constructs, schema_ requires model_validate({'schema': 'X'}) not schema_='X', password is SecretStr, env prefix loads host (TRINO_HOST), env prefix pool_size (TRINO_POOL_SIZE)
    - TestMSSQLConfig: uri mode constructs, password is SecretStr (masked in repr), env prefix loads host (MSSQL_HOST), env prefix pool_size (MSSQL_POOL_SIZE)
    - TestApacheBackendConfigs: add test_flightsql_env_prefix_pool_size using FLIGHTSQL_POOL_SIZE env var
    - Add the new classes below the existing TestFoundryBackendConfigs class; do not modify existing tests
    - Pattern for env prefix tests: monkeypatch.setenv then construct with no args
    - Pattern for SecretStr: assert value not in repr(config)
    - TrinoConfig schema_: model_validate({'schema': 'PUBLIC'}) sets schema_ field (same as SnowflakeConfig pattern from STATE.md decisions)
  </behavior>
  <action>
    Append three new test classes (TestRedshiftConfig, TestTrinoConfig, TestMSSQLConfig) to tests/test_configs.py after the existing TestFoundryBackendConfigs class. Also add test_flightsql_env_prefix_pool_size to TestApacheBackendConfigs.

    For TestRedshiftConfig — add to imports if needed: RedshiftConfig.
    For TestTrinoConfig — add to imports if needed: TrinoConfig.
    For TestMSSQLConfig — add to imports if needed: MSSQLConfig.
    All three are already imported at the top of test_configs.py.

    Env prefix patterns follow existing tests exactly (monkeypatch.setenv, then Config() with no args).
    SecretStr tests: construct with a known value, assert value not in repr(config).
    Schema alias test for Trino: use model_validate({'schema': 'PUBLIC'}) per the established SnowflakeConfig pattern (STATE.md [03-02] decision).
  </action>
  <verify>
    <automated>uv run pytest tests/test_configs.py -x -q 2>&1 | tail -10</automated>
  </verify>
  <done>
    All new test methods pass. No regressions in existing tests. Three new test classes visible in test_configs.py: TestRedshiftConfig, TestTrinoConfig, TestMSSQLConfig.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Fill translate_config dispatch and resolve_driver coverage gaps</name>
  <files>tests/test_translators.py, tests/test_drivers.py</files>
  <behavior>
    test_translators.py — TestTranslateConfig additions:
    - test_bigquery_dispatch: translate_config(BigQueryConfig()) == translate_bigquery(BigQueryConfig())
    - test_postgresql_dispatch: translate_config(PostgreSQLConfig()) == translate_postgresql(PostgreSQLConfig())
    - test_flightsql_dispatch: translate_config(FlightSQLConfig()) == translate_flightsql(FlightSQLConfig())
    - test_databricks_dispatch: translate_config(DatabricksConfig(uri=...)) == translate_databricks(same)
    - test_redshift_dispatch: translate_config(RedshiftConfig()) == translate_redshift(RedshiftConfig())
    - test_trino_dispatch: translate_config(TrinoConfig()) == translate_trino(TrinoConfig())
    - test_mssql_dispatch: translate_config(MSSQLConfig()) == translate_mssql(MSSQLConfig())
    - test_mysql_dispatch: translate_config(MySQLConfig(host=..., user=..., database=...)) == translate_mysql(same)
    - test_sqlite_dispatch: translate_config(SQLiteConfig()) == translate_sqlite(SQLiteConfig())

    test_drivers.py — TestResolvePyPIDriver additions (Path 2 fallback, find_spec=None):
    - test_path2_bigquery_missing_returns_package_name: result == "adbc_driver_bigquery"
    - test_path2_postgresql_missing_returns_package_name: result == "adbc_driver_postgresql"
    - test_path2_flightsql_missing_returns_package_name: result == "adbc_driver_flightsql"
    - test_path2_sqlite_missing_returns_package_name: result == "adbc_driver_sqlite"

    test_drivers.py — TestResolveFoundryDriver additions:
    - test_mysql_returns_short_name: resolve_driver(MySQLConfig(host=..., user=..., database=...)) == "mysql"
    - test_trino_returns_short_name: resolve_driver(TrinoConfig()) == "trino"
    - test_mssql_returns_short_name: resolve_driver(MSSQLConfig()) == "mssql"
    All three must assert find_spec was not called (same pattern as existing databricks and redshift tests).
  </behavior>
  <action>
    Append dispatch test methods to the existing TestTranslateConfig class in test_translators.py. Import DatabricksConfig using SecretStr uri for dispatch test — use SecretStr("databricks://token:dapi@host:443/wh/abc") and pragma: allowlist secret comment.

    In test_drivers.py:
    - Add four methods to TestResolvePyPIDriver (following the existing snowflake pattern: patch find_spec to None, assert package name returned)
    - Add three methods to TestResolveFoundryDriver (following existing databricks pattern: patch find_spec, call resolve_driver, assert find_spec not called, assert short name returned)

    For MySQLConfig in driver tests: use MySQLConfig(host="h", user="u", database="db") — the minimal valid decomposed spec.
    For TrinoConfig and MSSQLConfig: use default construction (no required fields).
  </action>
  <verify>
    <automated>uv run pytest tests/test_translators.py tests/test_drivers.py -x -q 2>&1 | tail -10</automated>
  </verify>
  <done>
    TestTranslateConfig has 11 dispatch tests (one per backend). TestResolvePyPIDriver covers all 5 PyPI backends. TestResolveFoundryDriver covers all 5 Foundry backends. All pass.
  </done>
</task>

<task type="auto">
  <name>Task 3: Fix MySQL guide URI example and verify mkdocs build</name>
  <files>docs/src/guides/mysql.md</files>
  <action>
    In docs/src/guides/mysql.md, update the URI mode example to use SecretStr explicitly (same pattern as the Databricks guide):

    Replace:
    ```python
    config = MySQLConfig(
        uri="root:password@tcp(localhost:3306)/mydb",  # pragma: allowlist secret
    )
    ```

    With:
    ```python
    from pydantic import SecretStr
    from adbc_poolhouse import MySQLConfig, create_pool

    config = MySQLConfig(
        uri=SecretStr("root:password@tcp(localhost:3306)/mydb"),  # pragma: allowlist secret
    )
    pool = create_pool(config)
    ```

    The existing import line at the top of that code block may need adjusting — read the file first and make a minimal edit.

    After editing, run `uv run mkdocs build --strict` to confirm no regressions.
    Apply a humanizer pass to the edited paragraph (see SKILL.md Step 3) — the MySQL guide is short and was last written in Phase 11; check for AI vocabulary and em dash overuse.
  </action>
  <verify>
    <automated>uv run mkdocs build --strict 2>&1 | tail -5</automated>
  </verify>
  <done>
    MySQL guide URI mode example uses SecretStr. mkdocs build --strict exits 0. No other guide pages changed.
  </done>
</task>

</tasks>

<verification>
Run the full test suite to confirm no regressions:

```
uv run pytest tests/ -q 2>&1 | tail -15
```

Expected: all existing tests pass, new test count increases by ~20+ tests.
</verification>

<success_criteria>
1. `uv run pytest tests/test_configs.py` passes with new TestRedshiftConfig, TestTrinoConfig, TestMSSQLConfig classes present
2. `uv run pytest tests/test_translators.py` passes with all 11 backends covered in TestTranslateConfig
3. `uv run pytest tests/test_drivers.py` passes with all 5 PyPI + 5 Foundry backends in driver resolution tests
4. `uv run mkdocs build --strict` exits 0
5. MySQL guide URI example uses `SecretStr(...)` consistent with Databricks guide
</success_criteria>

<output>
After completion, create `.planning/quick/8-review-all-backend-config-docs-and-tests/8-SUMMARY.md` summarising what was changed and any gaps still open.
</output>
