---
phase: 21
plan: 02
type: execute
wave: 2
depends_on: [21-01]
files_modified:
  - tests/test_configs.py
  - tests/test_driver_imports.py
  - tests/test_drivers.py
autonomous: true
requirements: [QUACK-08, QUACK-10, QUACK-11, QUACK-12]
requirements_addressed: [QUACK-08, QUACK-10, QUACK-11, QUACK-12]

must_haves:
  truths:
    - "Unit tests verify URI mode, decomposed mode, mutual exclusion, kwargs shape, token passthrough, TLS on/off, and env loading"
    - "Semi-integration test verifies create_pool(QuackConfig(...)) routes through the right dbapi connect under the conditional mock pattern"
    - "test_drivers.py contains short-name and dbapi tests for Quack mirroring the Snowflake pattern"
    - "All 241+ pre-existing tests still pass"
  artifacts:
    - path: "tests/test_configs.py"
      provides: "TestQuackConfig class with construction, validation, kwargs-shape, env-loading tests"
      contains: "class TestQuackConfig"
    - path: "tests/test_driver_imports.py"
      provides: "TestQuackImports class with conditional-mock create_pool wiring test"
      contains: "class TestQuackImports"
    - path: "tests/test_drivers.py"
      provides: "Quack short-name + dbapi module tests"
      contains: "test_quack_"
  key_links:
    - from: "tests/test_configs.py::TestQuackConfig"
      to: "QuackConfig"
      via: "import from adbc_poolhouse"
      pattern: "QuackConfig"
    - from: "tests/test_driver_imports.py::TestQuackImports"
      to: "_driver_installed('adbc_driver_quack')"
      via: "conditional patch target selection"
      pattern: "_driver_installed\\([\"']adbc_driver_quack[\"']\\)"
---

<objective>
Add comprehensive test coverage for the Quack backend.

Purpose: lock in QUACK-03 mutual exclusion, QUACK-04 kwargs shape (including token/tls omission semantics), QUACK-08 pool wiring, and QUACK-12 regression safety. Without these tests the locked behaviours in 21-CONTEXT.md cannot be enforced.

Output:
- `tests/test_configs.py::TestQuackConfig` covering construction, validation, kwargs serialisation in both modes, token passthrough, TLS on/off, env prefix loading, and pool tuning inheritance.
- `tests/test_driver_imports.py::TestQuackImports` mirroring `TestSnowflakeImports` line-for-line with the conditional-mock pattern.
- Driver-path and dbapi tests in `tests/test_drivers.py` mirroring the Snowflake PyPI patterns.

Note: REQUIREMENTS.md QUACK-10 says `tests/test_quack_config.py`; 21-CONTEXT.md and 21-RESEARCH.md supersede with `tests/test_configs.py::TestQuackConfig`. Use the CONTEXT.md location.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/21-quack-backend/21-CONTEXT.md
@.planning/phases/21-quack-backend/21-RESEARCH.md
@.planning/phases/21-quack-backend/21-VALIDATION.md
@.planning/phases/21-quack-backend/21-01-config-export-deps-PLAN.md
@src/adbc_poolhouse/_quack_config.py
@tests/test_configs.py
@tests/test_driver_imports.py
@tests/test_drivers.py

<interfaces>
<!-- The QuackConfig contract from Plan 01. Use these signatures directly. -->

```python
from adbc_poolhouse import QuackConfig

# Construction
QuackConfig(uri="quack://h:1234")             # URI mode
QuackConfig(host="h")                         # decomposed mode, no port
QuackConfig(host="h", port=1234)              # decomposed mode, with port
QuackConfig(host="h", token=SecretStr("tk")) # with token
QuackConfig(host="h", tls=True)               # with TLS

# Both raise pydantic.ValidationError (wrapping ConfigurationError):
QuackConfig(uri="quack://h", host="h")  # both set
QuackConfig()                             # neither set

# Serialization
QuackConfig(host="h").to_adbc_kwargs()
# -> {"uri": "quack://h"}

QuackConfig(host="h", port=1234, token=SecretStr("tk"), tls=True).to_adbc_kwargs()
# -> {"uri": "quack://h:1234", "adbc.quack.token": "tk", "adbc.quack.tls": "true"}

# Env loading (QUACK_ prefix)
# QUACK_HOST, QUACK_PORT, QUACK_TOKEN, QUACK_TLS, QUACK_URI

# Driver dispatch
QuackConfig(host="h")._driver_path()      # "adbc_driver_quack" if not installed; absolute .so path if installed
QuackConfig(host="h")._dbapi_module()     # "adbc_driver_quack.dbapi" if installed, None otherwise
```

From `tests/test_driver_imports.py` (existing helper):
```python
def _driver_installed(package_name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(package_name) is not None
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add TestQuackConfig to tests/test_configs.py</name>
  <files>tests/test_configs.py</files>
  <read_first>
    - tests/test_configs.py (full file — note import block at top, structure of TestClickHouseConfig at lines 477-562, and the WarehouseConfig protocol-isinstance assertion pattern)
    - .planning/phases/21-quack-backend/21-CONTEXT.md "Tests" section (full list of required cases)
    - .planning/phases/21-quack-backend/21-RESEARCH.md "Unit tests" section (line-by-line required cases)
    - src/adbc_poolhouse/_quack_config.py (the artifact under test from Plan 01)
  </read_first>
  <action>
    Edit `tests/test_configs.py`:

    1. Add `QuackConfig` to the existing `from adbc_poolhouse import (...)` block, alphabetically with the other config imports. Also ensure `SecretStr` is imported from pydantic (it likely already is — reuse if so).

    2. Append a new class `TestQuackConfig` to the file (after the last existing TestXxxConfig class). Mirror the shape of `TestClickHouseConfig` (lines 477-562). Required test methods (one per locked behaviour — name them descriptively):

       - `test_uri_mode_constructs`: `QuackConfig(uri="quack://h:1234")` succeeds; assert `c.uri == "quack://h:1234"`, `c.host is None`, `c.port is None`.
       - `test_host_only_constructs`: `QuackConfig(host="h")` succeeds; assert `c.host == "h"`, `c.port is None`, `c.uri is None`.
       - `test_host_port_constructs`: `QuackConfig(host="h", port=1234)`; assert both set.
       - `test_uri_and_host_raises`: `with pytest.raises(ValidationError): QuackConfig(uri="quack://h", host="h")`.
       - `test_neither_uri_nor_host_raises`: `with pytest.raises(ValidationError): QuackConfig()`.
       - `test_port_alone_raises`: `with pytest.raises(ValidationError): QuackConfig(port=1234)` (no host, no uri).
       - `test_uri_is_plain_str_not_secretstr`: assert `type(QuackConfig(uri="quack://h").uri) is str` (NOT SecretStr) — explicit guard for the locked decision.
       - `test_token_is_secretstr`: `c = QuackConfig(host="h", token="tk")`; assert `isinstance(c.token, SecretStr)`; assert `"tk" not in repr(c)` (SecretStr masking).
       - `test_to_adbc_kwargs_uri_mode`: `QuackConfig(uri="quack://h:1234").to_adbc_kwargs() == {"uri": "quack://h:1234"}`.
       - `test_to_adbc_kwargs_decomposed_no_port`: `QuackConfig(host="h").to_adbc_kwargs() == {"uri": "quack://h"}` (no `:None` suffix).
       - `test_to_adbc_kwargs_decomposed_with_port`: `QuackConfig(host="h", port=1234).to_adbc_kwargs() == {"uri": "quack://h:1234"}`.
       - `test_to_adbc_kwargs_token_passthrough`: `c = QuackConfig(host="h", token="tk"); k = c.to_adbc_kwargs()`; assert `k["adbc.quack.token"] == "tk"`.
       - `test_to_adbc_kwargs_tls_true`: `c = QuackConfig(host="h", tls=True); k = c.to_adbc_kwargs()`; assert `k["adbc.quack.tls"] == "true"`.
       - `test_to_adbc_kwargs_tls_false_omitted`: `c = QuackConfig(host="h", tls=False); k = c.to_adbc_kwargs()`; assert `"adbc.quack.tls" not in k`.
       - `test_to_adbc_kwargs_token_omitted_when_none`: `c = QuackConfig(host="h"); k = c.to_adbc_kwargs()`; assert `"adbc.quack.token" not in k`.
       - `test_env_prefix_loads`: use `monkeypatch.setenv("QUACK_HOST", "envhost"); monkeypatch.setenv("QUACK_PORT", "9999"); monkeypatch.setenv("QUACK_TLS", "true"); monkeypatch.setenv("QUACK_TOKEN", "envtok")` (NEVER `os.environ[...] = ...`), then `c = QuackConfig()`; assert `c.host == "envhost"`, `c.port == 9999`, `c.tls is True`, `c.token.get_secret_value() == "envtok"`. (URI not set in env so decomposed mode passes the validator.)
       - `test_pool_tuning_inherited`: `monkeypatch.setenv("QUACK_POOL_SIZE", "7"); c = QuackConfig(host="h")`; assert `c.pool_size == 7`.
       - `test_satisfies_warehouse_config_protocol`: `from adbc_poolhouse._base_config import WarehouseConfig; assert isinstance(QuackConfig(host="h"), WarehouseConfig)` (structural protocol check).

    3. Use `pytest.raises(ValidationError)` from `pydantic`, not bare `ConfigurationError`, because pydantic wraps the validator error. (Match the existing TestClickHouseConfig / TestDatabricksConfig pattern.)

    4. Security note for tests: tokens in test fixtures MUST be obvious placeholders like `"tk"`, `"envtok"`, or `"test-token-not-real"`. Append `# pragma: allowlist secret` to any line that detect-secrets might flag.
  </action>
  <verify>
    <automated>uv run pytest tests/test_configs.py::TestQuackConfig -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'class TestQuackConfig' tests/test_configs.py`
    - `grep -q 'QuackConfig' tests/test_configs.py`
    - `grep -q 'test_to_adbc_kwargs_decomposed_no_port' tests/test_configs.py`
    - `grep -q 'test_to_adbc_kwargs_tls_false_omitted' tests/test_configs.py`
    - `grep -q 'test_env_prefix_loads' tests/test_configs.py`
    - `grep -q 'test_satisfies_warehouse_config_protocol' tests/test_configs.py`
    - `grep -q 'monkeypatch.setenv' tests/test_configs.py`  (env handling uses monkeypatch, not os.environ — security)
    - `uv run pytest tests/test_configs.py::TestQuackConfig -x -q` exits 0
  </acceptance_criteria>
  <done>
    All TestQuackConfig methods pass. Mutual exclusion, kwargs-shape (token/tls omission semantics), env loading, and protocol satisfaction all locked in.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Add TestQuackImports semi-integration test</name>
  <files>tests/test_driver_imports.py</files>
  <read_first>
    - tests/test_driver_imports.py (full file — especially TestSnowflakeImports at lines 68-103 and the `_driver_installed` helper at the top)
    - .planning/phases/21-quack-backend/21-RESEARCH.md "Code Examples — Example 2" (line-for-line semi-integration test)
    - src/adbc_poolhouse/_quack_config.py (artifact under test)
    - src/adbc_poolhouse/_pool_factory.py (verify self-describing dispatch — no edits needed, just understanding for the test)
  </read_first>
  <action>
    Edit `tests/test_driver_imports.py`:

    1. Add `QuackConfig` to the import block at the top, alphabetical with the other configs.

    2. Append a new class `TestQuackImports` after `TestSnowflakeImports`. Line-for-line mirror per 21-RESEARCH.md "Code Examples — Example 2":

       ```python
       class TestQuackImports:
           """Semi-integration test: real Quack driver import (if available), mocked connection."""

           def test_create_pool_wiring(self) -> None:
               config = QuackConfig(host="h")
               mock_conn = MagicMock()
               mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

               if _driver_installed("adbc_driver_quack"):
                   with patch(
                       "adbc_driver_quack.dbapi.connect",
                       return_value=mock_conn,
                   ) as mock_connect:
                       pool = create_pool(config)
                       pool.dispose()
                   mock_connect.assert_called_once()
                   assert "uri" in mock_connect.call_args.kwargs
               else:
                   with patch(
                       "adbc_driver_manager.dbapi.connect",
                       return_value=mock_conn,
                   ) as mock_connect:
                       pool = create_pool(config)
                       pool.dispose()
                   mock_connect.assert_called_once()
                   assert "driver" in mock_connect.call_args.kwargs
       ```

       Use the existing `from unittest.mock import MagicMock, patch` and `from adbc_poolhouse import create_pool` already imported in the file. The `_driver_installed` helper is already present.

    3. Do NOT add any new test fixtures or modify `conftest.py`. The conditional-mock pattern is fully self-contained inside the test method.
  </action>
  <verify>
    <automated>uv run pytest tests/test_driver_imports.py::TestQuackImports -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'class TestQuackImports' tests/test_driver_imports.py`
    - `grep -q '_driver_installed("adbc_driver_quack")' tests/test_driver_imports.py`
    - `grep -q 'adbc_driver_quack.dbapi.connect' tests/test_driver_imports.py`
    - `grep -q 'adbc_driver_manager.dbapi.connect' tests/test_driver_imports.py`
    - `uv run pytest tests/test_driver_imports.py::TestQuackImports -x -q` exits 0
  </acceptance_criteria>
  <done>
    TestQuackImports passes whether or not `adbc-driver-quack` is installed in the test environment. Conditional mock pattern exactly mirrors TestSnowflakeImports.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Add driver-path and dbapi-module tests</name>
  <files>tests/test_drivers.py</files>
  <read_first>
    - tests/test_drivers.py (full file — especially TestPyPIDriverPath around lines 62-106 and TestPyPIDbApiModule around lines 109-148; note the Snowflake test patterns)
    - .planning/phases/21-quack-backend/21-RESEARCH.md "Driver path / dbapi unit tests" section
    - src/adbc_poolhouse/_quack_config.py
  </read_first>
  <action>
    Edit `tests/test_drivers.py`:

    1. Add `QuackConfig` to the import block, alphabetical.

    2. Add to `TestPyPIDriverPath` (mirror Snowflake at lines 65-82):
       - `test_quack_found_returns_driver_path`: patch `importlib.util.find_spec` and `__import__` to inject a fake package whose `_driver_path` returns a sentinel; assert `QuackConfig(host="h")._driver_path()` returns that sentinel. Match the Snowflake test's mocking depth.
       - `test_quack_missing_returns_package_name`: patch `importlib.util.find_spec` to return `None`; assert `QuackConfig(host="h")._driver_path() == "adbc_driver_quack"`.

    3. Add to `TestPyPIDbApiModule` (mirror Snowflake at lines 112-123):
       - `test_quack_installed_returns_dbapi_module`: patch `importlib.util.find_spec` to return a MagicMock; assert `QuackConfig(host="h")._dbapi_module() == "adbc_driver_quack.dbapi"`.
       - `test_quack_not_installed_returns_none`: patch `find_spec` to return `None`; assert `QuackConfig(host="h")._dbapi_module() is None`.

    4. ALSO add a `test_quack_returns_short_name` test at module level (per 21-VALIDATION.md row 21-02-03) — even though this is largely a duplicate of `test_quack_missing_returns_package_name`, the validation map calls it out explicitly. Implement it as a one-liner mirroring `test_clickhouse_returns_short_name` (line 170): patch `find_spec` to None, call `_driver_path()`, assert equals `"adbc_driver_quack"`.
  </action>
  <verify>
    <automated>uv run pytest tests/test_drivers.py -k "quack" -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'test_quack_found_returns_driver_path' tests/test_drivers.py`
    - `grep -q 'test_quack_missing_returns_package_name' tests/test_drivers.py`
    - `grep -q 'test_quack_installed_returns_dbapi_module' tests/test_drivers.py`
    - `grep -q 'test_quack_not_installed_returns_none' tests/test_drivers.py`
    - `grep -q 'test_quack_returns_short_name' tests/test_drivers.py`
    - `uv run pytest tests/test_drivers.py -k "quack" -x -q` exits 0
  </acceptance_criteria>
  <done>
    All Quack-specific driver-path and dbapi-module tests pass. PyPI-driver dispatch fully covered.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 4: Run full test suite — verify zero regression</name>
  <files></files>
  <read_first>
    - .planning/phases/21-quack-backend/21-VALIDATION.md (Sampling Rate: full suite gate after each wave)
  </read_first>
  <action>
    Run the entire test suite to confirm QUACK-12 (all 241 pre-existing tests still pass) AND the new Quack tests pass together. No new code or fixtures — this is a verification gate task.

    Command: `uv run pytest -x -q`

    Expected: All tests green. Total count should be ~261+ (241 existing + ~20 new). If any pre-existing test fails, STOP and investigate before continuing — that indicates Plan 01 introduced a regression (e.g., import-time side effect from the new module).
  </action>
  <verify>
    <automated>uv run pytest -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest -x -q` exits 0
    - Pytest output shows >= 261 tests passed (existing 241 + new Quack tests)
    - No skips except pre-existing skips
  </acceptance_criteria>
  <done>
    Full suite green. Plan 01 did not break anything; new Quack tests integrate cleanly.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test env vars → QuackConfig instances | `monkeypatch.setenv` sets process-local env that pydantic-settings reads at construction |
| Mocked driver connect → kwargs assertion | Tests inspect `mock_connect.call_args.kwargs` to assert wiring; no real network |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-05 | Information Disclosure | Test fixtures using placeholder tokens | mitigate | Test tokens use obvious placeholders (`"tk"`, `"envtok"`, `"test-token-not-real"`); detect-secrets will not flag them, but append `# pragma: allowlist secret` to any line that does. NEVER paste real credentials. |
| T-21-06 | Tampering | Env var leakage between tests | mitigate | Tests MUST use `monkeypatch.setenv` (auto-reverts per test), NEVER `os.environ[...] = ...`. Verified by grep acceptance criterion in Task 1. |
| T-21-07 | Repudiation | Mock connection bypasses real driver | accept | Conditional-mock pattern is the project-wide standard (TestSnowflakeImports precedent). The semi-integration test verifies wiring, not driver behaviour. Live integration is explicitly out of scope per CONTEXT.md. |
</threat_model>

<verification>
- `uv run pytest tests/test_configs.py::TestQuackConfig -x -q` exits 0
- `uv run pytest tests/test_driver_imports.py::TestQuackImports -x -q` exits 0
- `uv run pytest tests/test_drivers.py -k quack -x -q` exits 0
- `uv run pytest -x -q` (full suite) exits 0 with >= 261 tests passed
- `! grep -E 'os\.environ\[["\']QUACK_' tests/test_configs.py` (no env-var leakage anti-pattern)
</verification>

<success_criteria>
- QUACK-08: create_pool(QuackConfig(...)) returns a working pool — verified by TestQuackImports
- QUACK-10: Unit tests cover all validation paths and kwargs shapes — verified by TestQuackConfig passing
- QUACK-11: Semi-integration test with conditional mock — verified by TestQuackImports passing
- QUACK-12: All 241 existing tests pass — verified by Task 4 full-suite run
</success_criteria>

<output>
After completion, create `.planning/phases/21-quack-backend/21-02-SUMMARY.md` documenting:
- Test count before / after (e.g. "241 → 263")
- Any test cases added beyond the explicit CONTEXT.md list (and why)
- Confirmation that QUACK-10 file-location discrepancy was resolved in favour of CONTEXT.md (`tests/test_configs.py`, not `tests/test_quack_config.py`)
- Full-suite green confirmation
</output>
