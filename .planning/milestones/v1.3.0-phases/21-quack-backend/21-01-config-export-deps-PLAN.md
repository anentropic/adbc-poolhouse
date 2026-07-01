---
phase: 21
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/adbc_poolhouse/_quack_config.py
  - src/adbc_poolhouse/__init__.py
  - pyproject.toml
autonomous: true
requirements: [QUACK-01, QUACK-02, QUACK-03, QUACK-04, QUACK-05, QUACK-06, QUACK-07, QUACK-09]
requirements_addressed: [QUACK-01, QUACK-02, QUACK-03, QUACK-04, QUACK-05, QUACK-06, QUACK-07, QUACK-09]

must_haves:
  truths:
    - "User can `from adbc_poolhouse import QuackConfig`"
    - "User can construct QuackConfig(uri='quack://h:1234') and QuackConfig(host='h', port=1234)"
    - "QuackConfig(uri='...', host='...') raises ConfigurationError"
    - "QuackConfig() with neither uri nor host raises ConfigurationError"
    - "QuackConfig(host='h').to_adbc_kwargs() returns {'uri': 'quack://h'}"
    - "pip install adbc-poolhouse[quack] resolves adbc-driver-quack>=0.1.0a1"
  artifacts:
    - path: "src/adbc_poolhouse/_quack_config.py"
      provides: "QuackConfig class, _driver_path, _dbapi_module, to_adbc_kwargs, mutual exclusion validator"
      contains: "class QuackConfig(BaseWarehouseConfig)"
    - path: "src/adbc_poolhouse/__init__.py"
      provides: "QuackConfig in public API and __all__"
      contains: "QuackConfig"
    - path: "pyproject.toml"
      provides: "[quack] optional dep group with adbc-driver-quack>=0.1.0a1; included in [all]"
      contains: 'quack = ["adbc-driver-quack>=0.1.0a1"]'
  key_links:
    - from: "src/adbc_poolhouse/_quack_config.py"
      to: "BaseWarehouseConfig"
      via: "class inheritance"
      pattern: "class QuackConfig\\(BaseWarehouseConfig\\)"
    - from: "src/adbc_poolhouse/_quack_config.py::_driver_path"
      to: "self._resolve_driver_path('adbc_driver_quack')"
      via: "return statement"
      pattern: "_resolve_driver_path\\([\"']adbc_driver_quack[\"']\\)"
    - from: "src/adbc_poolhouse/__init__.py"
      to: "adbc_poolhouse._quack_config.QuackConfig"
      via: "import"
      pattern: "from adbc_poolhouse._quack_config import QuackConfig"
---

<objective>
Create the `QuackConfig` class and wire it into the public API + packaging.

Purpose: deliver the core config artifact for the Quack backend. After this plan, the v1.2.0 self-describing dispatch in `_pool_factory` will route `create_pool(QuackConfig(...))` correctly with zero changes to the factory itself.

Output:
- New file `src/adbc_poolhouse/_quack_config.py` mirroring Databricks (URI XOR decomposed) + Snowflake (PyPI dual `_driver_path` / `_dbapi_module`) patterns.
- `QuackConfig` exported from `adbc_poolhouse.__init__` and added to `__all__`, alphabetically between `PostgreSQLConfig` and `RedshiftConfig`.
- `pyproject.toml` declares `[quack]` optional dep group with `adbc-driver-quack>=0.1.0a1`, and the `all` extra includes `adbc-poolhouse[quack]`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
@.claude/skills/adbc-poolhouse-docs-author/SKILL.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/21-quack-backend/21-CONTEXT.md
@.planning/phases/21-quack-backend/21-RESEARCH.md
@.planning/phases/21-quack-backend/21-VALIDATION.md

# Reference implementations to mirror (READ before editing)
@src/adbc_poolhouse/_base_config.py
@src/adbc_poolhouse/_databricks_config.py
@src/adbc_poolhouse/_clickhouse_config.py
@src/adbc_poolhouse/_snowflake_config.py
@src/adbc_poolhouse/__init__.py
@pyproject.toml

<interfaces>
<!-- Critical contracts the executor needs. Do not explore the codebase further. -->

From `src/adbc_poolhouse/_base_config.py`:
```python
class BaseWarehouseConfig(BaseSettings):
    # Inherits pool tuning fields (pool_size, max_overflow, etc.)
    @staticmethod
    def _resolve_driver_path(package_name: str) -> str: ...
    def _driver_path(self) -> str | None: ...
    def _dbapi_module(self) -> str | None: ...
    def _adbc_entrypoint(self) -> str | None: ...
    def to_adbc_kwargs(self) -> dict[str, str]: ...
```

From `src/adbc_poolhouse/_exceptions.py`:
```python
class ConfigurationError(ValueError): ...
```

Pattern from `src/adbc_poolhouse/_snowflake_config.py` (PyPI driver wiring):
```python
import importlib.util

def _driver_path(self) -> str:
    return self._resolve_driver_path("adbc_driver_snowflake")

def _dbapi_module(self) -> str | None:
    if importlib.util.find_spec("adbc_driver_snowflake") is not None:
        return "adbc_driver_snowflake.dbapi"
    return None
```

Pattern from `src/adbc_poolhouse/_databricks_config.py` (model_validator returning Self):
```python
from typing import Self
from pydantic import model_validator

@model_validator(mode="after")
def check_connection_spec(self) -> Self:
    ...
    return self
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Create QuackConfig module</name>
  <files>src/adbc_poolhouse/_quack_config.py</files>
  <read_first>
    - src/adbc_poolhouse/_base_config.py (BaseWarehouseConfig, _resolve_driver_path, Protocol contract)
    - src/adbc_poolhouse/_databricks_config.py (URI XOR decomposed mutual-exclusion validator with Self return)
    - src/adbc_poolhouse/_clickhouse_config.py (simpler two-mode validator, alpha admonition style)
    - src/adbc_poolhouse/_snowflake_config.py (PyPI dual _driver_path + _dbapi_module pattern with importlib.util.find_spec)
    - src/adbc_poolhouse/_exceptions.py (ConfigurationError class)
    - .planning/phases/21-quack-backend/21-CONTEXT.md (locked decisions for field shapes, kwarg keys, omit-on-False TLS)
    - .planning/phases/21-quack-backend/21-RESEARCH.md "Code Examples" section (synthesized reference implementation)
    - .claude/skills/adbc-poolhouse-docs-author/SKILL.md (Google-style docstrings, Markdown not RST, Example: singular for admonition)
  </read_first>
  <action>
    Create `src/adbc_poolhouse/_quack_config.py` per QUACK-01 through QUACK-06 (locked decisions in 21-CONTEXT.md).

    Required imports (in order):
    ```python
    from __future__ import annotations
    import importlib.util
    from typing import Self

    from pydantic import SecretStr, model_validator
    from pydantic_settings import SettingsConfigDict

    from adbc_poolhouse._base_config import BaseWarehouseConfig
    from adbc_poolhouse._exceptions import ConfigurationError
    ```

    Class declaration:
    - `class QuackConfig(BaseWarehouseConfig):` (per QUACK-01)
    - Class docstring (Google-style, Markdown not RST) covering: purpose (DuckDB Quack remote protocol via `adbc-driver-quack` PyPI driver), alpha status with `pip install --pre adbc-poolhouse[quack]` note, two modes (URI / decomposed), mutual exclusion behaviour. Include an `Example:` (singular) admonition block with a fenced ```python``` snippet matching the form in 21-RESEARCH.md "Code Examples". Use Markdown cross-refs `` [create_pool][adbc_poolhouse.create_pool] ``, NEVER RST `:func:` / `:class:` roles.
    - `model_config = SettingsConfigDict(env_prefix="QUACK_")` (per QUACK-02 env loading)

    Fields, exactly in this order with attribute docstrings (per QUACK-02 — uri is plain str, NOT SecretStr; locked decision in 21-CONTEXT.md):
    ```python
    uri: str | None = None
    """Full connection URI `quack://host[:port]`. The driver's URI cannot
    embed credentials, so this is a plain str (not SecretStr). Env: QUACK_URI."""

    host: str | None = None
    """Quack server hostname. Alternative to URI mode. Env: QUACK_HOST."""

    port: int | None = None
    """Quack server port. Optional even in decomposed mode. Env: QUACK_PORT."""

    token: SecretStr | None = None
    """Bearer token. Passes via `adbc.quack.token` kwarg, never embedded
    in the URI, never URL-encoded. Env: QUACK_TOKEN."""

    tls: bool = False
    """Enable TLS. When False (default), the `adbc.quack.tls` kwarg is
    omitted entirely (driver default is "false"). Env: QUACK_TLS."""
    ```

    Mutual exclusion validator (per QUACK-03):
    ```python
    @model_validator(mode="after")
    def check_connection_spec(self) -> Self:
        """Raise ConfigurationError when both modes are set or neither is set."""
        has_uri = self.uri is not None
        has_host = self.host is not None
        if has_uri and has_host:
            raise ConfigurationError(
                "QuackConfig accepts either 'uri' or 'host', not both."
            )
        if not has_uri and not has_host:
            raise ConfigurationError(
                "QuackConfig requires either 'uri' or 'host'. Got neither."
            )
        return self
    ```

    Driver dispatch methods (per QUACK-05, QUACK-06):
    ```python
    def _driver_path(self) -> str:
        return self._resolve_driver_path("adbc_driver_quack")

    def _dbapi_module(self) -> str | None:
        if importlib.util.find_spec("adbc_driver_quack") is not None:
            return "adbc_driver_quack.dbapi"
        return None
    ```

    `to_adbc_kwargs()` (per QUACK-04 — Google-style docstring with Args/Returns):
    ```python
    def to_adbc_kwargs(self) -> dict[str, str]:
        """Convert config to ADBC driver connection kwargs.

        Returns:
            A dict with `uri` always set. `adbc.quack.token` is included
            when `token` is set; `adbc.quack.tls` is included only when
            `tls=True` (omitted on False — driver default is "false").
        """
        if self.uri is not None:
            uri = self.uri
        else:
            assert self.host is not None  # model_validator guarantees
            uri = (
                f"quack://{self.host}:{self.port}"
                if self.port is not None
                else f"quack://{self.host}"
            )

        result: dict[str, str] = {"uri": uri}
        if self.token is not None:
            result["adbc.quack.token"] = self.token.get_secret_value()  # pragma: allowlist secret
        if self.tls:
            result["adbc.quack.tls"] = "true"
        return result
    ```

    Security: token MUST be accessed via `.get_secret_value()` ONLY inside `to_adbc_kwargs`. Do NOT log, print, or include token in `__repr__` (Pydantic's `SecretStr` repr masks by default — do not override).
  </action>
  <verify>
    <automated>uv run python -c "import importlib.util; from adbc_poolhouse._quack_config import QuackConfig; c = QuackConfig(host='h'); k = c.to_adbc_kwargs(); assert k == {'uri': 'quack://h'}, k; c2 = QuackConfig(host='h', port=1234, tls=True); assert c2.to_adbc_kwargs() == {'uri': 'quack://h:1234', 'adbc.quack.tls': 'true'}, c2.to_adbc_kwargs(); print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/adbc_poolhouse/_quack_config.py`
    - `grep -q 'class QuackConfig(BaseWarehouseConfig)' src/adbc_poolhouse/_quack_config.py`
    - `grep -q 'env_prefix="QUACK_"' src/adbc_poolhouse/_quack_config.py`
    - `grep -q 'uri: str | None = None' src/adbc_poolhouse/_quack_config.py`
    - `grep -q 'token: SecretStr | None = None' src/adbc_poolhouse/_quack_config.py`
    - `grep -q 'tls: bool = False' src/adbc_poolhouse/_quack_config.py`
    - `grep -q '@model_validator(mode="after")' src/adbc_poolhouse/_quack_config.py`
    - `grep -q '_resolve_driver_path("adbc_driver_quack")' src/adbc_poolhouse/_quack_config.py`
    - `grep -q 'importlib.util.find_spec("adbc_driver_quack")' src/adbc_poolhouse/_quack_config.py`
    - `grep -q '"adbc.quack.token"' src/adbc_poolhouse/_quack_config.py`
    - `grep -q '"adbc.quack.tls"' src/adbc_poolhouse/_quack_config.py`
    - `grep -q 'Example:' src/adbc_poolhouse/_quack_config.py`  (admonition block in class docstring)
    - No RST role syntax: `! grep -E ':(class|func|meth|mod|obj):\`' src/adbc_poolhouse/_quack_config.py`
    - `uv run python -c "from adbc_poolhouse._quack_config import QuackConfig"` exits 0
  </acceptance_criteria>
  <done>
    File exists, all field declarations match locked decisions, validator raises on both-set / neither-set, to_adbc_kwargs() shape matches CONTEXT.md spec (token-omitted-on-None, tls-omitted-on-False), and the verify one-liner prints OK.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Export QuackConfig from public API</name>
  <files>src/adbc_poolhouse/__init__.py</files>
  <read_first>
    - src/adbc_poolhouse/__init__.py (entire file — note the alphabetical export ordering between PostgreSQLConfig and RedshiftConfig)
    - src/adbc_poolhouse/_quack_config.py (created in Task 1)
  </read_first>
  <action>
    Edit `src/adbc_poolhouse/__init__.py`:

    1. Add the import line in alphabetical position between the existing PostgreSQL import and the Redshift import:
       ```python
       from adbc_poolhouse._quack_config import QuackConfig
       ```
       (If the PostgreSQL or Redshift lines are not adjacent in the current file, insert the new line alphabetically between any `Post*` and `Red*` entries — the convention is strict alphabetical by class name.)

    2. Add `"QuackConfig",` to the `__all__` tuple/list, alphabetically between `"PostgreSQLConfig"` and `"RedshiftConfig"`. Match the existing list's quote style (double quotes) and trailing-comma style.

    Do NOT modify any other entries.
  </action>
  <verify>
    <automated>uv run python -c "from adbc_poolhouse import QuackConfig; import adbc_poolhouse; assert 'QuackConfig' in adbc_poolhouse.__all__, adbc_poolhouse.__all__; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'from adbc_poolhouse._quack_config import QuackConfig' src/adbc_poolhouse/__init__.py`
    - `grep -q '"QuackConfig"' src/adbc_poolhouse/__init__.py`
    - `uv run python -c "from adbc_poolhouse import QuackConfig"` exits 0
    - `uv run python -c "import adbc_poolhouse; assert 'QuackConfig' in adbc_poolhouse.__all__"` exits 0
  </acceptance_criteria>
  <done>
    QuackConfig is importable from the top-level `adbc_poolhouse` package and appears in `__all__`.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Declare [quack] optional dependency in pyproject.toml</name>
  <files>pyproject.toml</files>
  <read_first>
    - pyproject.toml (entire `[project.optional-dependencies]` block — note exact format of existing entries like `bigquery`, `clickhouse`, `snowflake`, and the `all` extra list around lines 22-28)
  </read_first>
  <action>
    Edit `pyproject.toml` `[project.optional-dependencies]`:

    1. Add the new extra (alphabetical position — after `postgresql` if present, else before `redshift`, else before `snowflake`; if uncertain, place between `bigquery`/`clickhouse`-style alphabetically by key name):
       ```toml
       quack = ["adbc-driver-quack>=0.1.0a1"]
       ```
       Alpha lower bound is REQUIRED (QUACK-09); no upper cap.

    2. Add `"adbc-poolhouse[quack]",` to the `all` extra list, alphabetically with the other `adbc-poolhouse[X]` entries. Match the existing indentation and trailing-comma style.

    Do NOT change any other dependency lines, versions, or unrelated config.
  </action>
  <verify>
    <automated>grep -q '^quack = \["adbc-driver-quack>=0.1.0a1"\]' pyproject.toml && grep -q '"adbc-poolhouse\[quack\]"' pyproject.toml && uv lock --check 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q '^quack = \[' pyproject.toml`
    - `grep -q 'adbc-driver-quack>=0.1.0a1' pyproject.toml`
    - `grep -q '"adbc-poolhouse\[quack\]"' pyproject.toml`
    - `uv lock --check` succeeds (or `uv lock` regenerates cleanly if lockfile is tracked)
    - `uv run python -c "from adbc_poolhouse import QuackConfig"` still works (no env regression)
  </acceptance_criteria>
  <done>
    `[quack]` extra declared with alpha lower bound, `[all]` includes Quack, lockfile resolves.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| User-process → config object | User passes hostnames, ports, tokens directly in Python — no parsing of external input |
| Config object → driver kwargs | `to_adbc_kwargs()` serialises fields into driver-bound dict; downstream is `adbc-driver-quack` (out of scope for our code) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-01 | Information Disclosure | `QuackConfig.token` (SecretStr) | mitigate | Pydantic `SecretStr` masks on `repr()` / `str()` / model dump by default. We do NOT override `__repr__` or `__str__`. `.get_secret_value()` is called ONLY inside `to_adbc_kwargs()` to build the kwarg dict; never logged, never raised in exception messages. |
| T-21-02 | Tampering | URI string in `to_adbc_kwargs()` decomposed mode | mitigate | `host` and `port` are typed (`str | None`, `int | None`). Pydantic enforces the int type on `port`. The URI is built via f-string with no further interpolation. No other kwargs are passed through user-controlled strings — `adbc.quack.token` and `adbc.quack.tls` are the only other keys and their values come from typed fields. |
| T-21-03 | Information Disclosure | Token in exception messages | mitigate | `ConfigurationError` messages in `check_connection_spec` reference field names only ("'uri'", "'host'"), never field values. The `assert self.host is not None` in `to_adbc_kwargs` is a developer guard, not a user-facing error — never reached because `model_validator` runs first. |
| T-21-04 | Repudiation | Token logged in driver invocation | accept | Once `.get_secret_value()` is returned in the kwargs dict, downstream `adbc-driver-quack` controls handling. Out of our scope; matches Snowflake/Databricks precedent. |
</threat_model>

<verification>
- `uv run python -c "from adbc_poolhouse import QuackConfig"` succeeds
- `uv run python -c "from adbc_poolhouse._quack_config import QuackConfig; QuackConfig(uri='quack://h:1', host='h')"` raises `ConfigurationError` (or wrapped `ValidationError`)
- `uv run python -c "from adbc_poolhouse._quack_config import QuackConfig; QuackConfig()"` raises `ConfigurationError` (or wrapped `ValidationError`)
- `grep -q '^quack = \[' pyproject.toml`
- `uv lock --check` exits 0
- No RST role syntax anywhere in new file: `! grep -E ':(class|func|meth|mod|obj):\`' src/adbc_poolhouse/_quack_config.py`
</verification>

<success_criteria>
- QUACK-01: QuackConfig class exists in src/adbc_poolhouse/_quack_config.py inheriting BaseWarehouseConfig — verified by grep
- QUACK-02: All five fields present with correct types (uri is plain str, token is SecretStr) — verified by grep
- QUACK-03: Mutual exclusion validator raises on both-set and neither-set — verified by inline python call
- QUACK-04: to_adbc_kwargs returns expected shape with token/tls omission semantics — verified by inline python one-liner in Task 1
- QUACK-05: _driver_path returns "adbc_driver_quack" via _resolve_driver_path — verified by grep
- QUACK-06: _dbapi_module returns "adbc_driver_quack.dbapi" when installed, None when not — verified by source review
- QUACK-07: QuackConfig importable from adbc_poolhouse and in __all__ — verified by inline python
- QUACK-09: pyproject.toml declares quack extra with alpha lower bound — verified by grep
</success_criteria>

<output>
After completion, create `.planning/phases/21-quack-backend/21-01-SUMMARY.md` documenting:
- Files created/modified
- Decisions ratified (e.g. confirmation that `uri: str | None` per locked decision)
- Verification outputs (paste the OK lines from inline python)
- Any deviations from CONTEXT.md (expect none)
</output>
