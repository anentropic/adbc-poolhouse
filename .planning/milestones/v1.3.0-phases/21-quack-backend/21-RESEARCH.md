# Phase 21: Quack Backend - Research

**Researched:** 2026-05-19
**Domain:** New warehouse backend (PyPI-distributed alpha ADBC driver)
**Confidence:** HIGH

## Summary

Phase 21 adds `QuackConfig` for the `adbc-driver-quack` PyPI driver (DuckDB Quack remote protocol). All technical decisions are already locked in `21-CONTEXT.md` — the work is mechanical mirroring of existing backends, not new design. The closest pattern blends three references: Databricks (URI XOR decomposed mutual exclusion), ClickHouse (single-token simplicity and per-warehouse guide structure), and Snowflake (PyPI driver dual `_driver_path` + `_dbapi_module` pattern with `find_spec` gating).

Verified against the upstream `gizmodata/adbc-driver-quack` README: URI scheme is `quack://host[:port]`, kwargs are `adbc.quack.token` and `adbc.quack.tls`, the dbapi submodule is `adbc_driver_quack.dbapi`, and the driver is alpha (latest published `0.1.0a6` on PyPI as of 2026-05-19). The v1.2.0 self-describing dispatch in `_pool_factory.py` requires zero changes — adding `QuackConfig` is purely additive.

**Primary recommendation:** Implement file-by-file in this order: (1) `_quack_config.py` mirroring Databricks structure with ClickHouse-style validator; (2) `__init__.py` export; (3) `pyproject.toml` `[quack]` extra; (4) `tests/test_configs.py::TestQuackConfig`; (5) `tests/test_driver_imports.py::TestQuackImports`; (6) `tests/test_drivers.py` short-name + dbapi tests; (7) `docs/src/guides/quack.md`; (8) `configuration.md`, `index.md`, `mkdocs.yml`; (9) `uv run mkdocs build --strict`; (10) humanizer pass.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Config class shape** (file `src/adbc_poolhouse/_quack_config.py`, inherits `BaseWarehouseConfig`, `env_prefix="QUACK_"`):

- `uri: str | None = None` — **plain `str`, not `SecretStr`** (driver URI cannot embed credentials)
- `host: str | None = None`
- `port: int | None = None`
- `token: SecretStr | None = None`
- `tls: bool = False`

**URI / token / TLS conventions** (from upstream driver README):

- URI scheme is `quack://host[:port]` — port is optional in the URI itself
- Driver's URI cannot embed credentials — token always goes via `adbc.quack.token` kwarg, never embedded, never URL-encoded
- `uri` field is plain `str` (no `SecretStr` wrapping — no credentials to protect)

**`to_adbc_kwargs()` behavior:**

- Returns `dict[str, str]` shaped as:
  ```python
  {
      "uri": "quack://...",
      "adbc.quack.token": "...",   # omitted when token is None
      "adbc.quack.tls": "true",    # omitted when tls is False (driver default)
  }
  ```
- URI mode (`uri` set): pass `uri` through verbatim
- Decomposed mode (`host` set, no `uri`): rebuild URI as `quack://{host}:{port}` when port is set, or `quack://{host}` when port is None (omit explicit port — locked decision)
- `tls=False` → omit `adbc.quack.tls` entirely (driver default is `"false"`); `tls=True` → emit `"true"`

**Mutual exclusion validator** (`@model_validator(mode="after")`):

- Both `uri` AND `host` set → raise `ConfigurationError`
- Neither `uri` NOR `host` set → raise `ConfigurationError`
- `port` alone is not a valid spec

**Driver dispatch wiring:**

- `_driver_path() -> str: return self._resolve_driver_path("adbc_driver_quack")` (PyPI driver, same as Snowflake/BigQuery/PostgreSQL)
- `_dbapi_module() -> str | None`: returns `"adbc_driver_quack.dbapi"` when `importlib.util.find_spec("adbc_driver_quack")` is not None, else `None`
- `_adbc_entrypoint()`: not overridden (default `None`)

**Dependency declaration:**

- `[project.optional-dependencies]` adds `quack = ["adbc-driver-quack>=0.1.0a1"]`
- `all` extra updated to include `"adbc-poolhouse[quack]"`
- Alpha lower bound `0.1.0a1`, no upper cap
- Document `pip install --pre adbc-poolhouse[quack]` in the guide (alpha driver requires `--pre` depending on pip config)

**Export ordering:**

- Imported from `_quack_config` in `src/adbc_poolhouse/__init__.py`
- Added to `__all__` alphabetically between `PostgreSQLConfig` and `RedshiftConfig`

**Docs quality gate (CLAUDE.md, phase >= 7):**

- Google-style docstrings (Args/Returns/Raises) on all new public symbols
- Markdown in docstrings, NOT reStructuredText
- `uv run mkdocs build --strict` must pass
- Humanizer pass applied to new prose
- `adbc-poolhouse-docs-author` skill referenced in PLAN.md `<execution_context>`

### Claude's Discretion

- Docstring wording, prose phrasing in the guide
- Test case naming and assertion granularity (within the patterns laid out below)
- Ordering of fields within the config class (suggested: `uri`, `host`, `port`, `token`, `tls` — REQUIREMENTS QUACK-02 order)

### Deferred Ideas (OUT OF SCOPE)

- Live integration test against a real Quack server (no public test server)
- Cassette replay for Quack (single-protocol driver — not warranted)
- Decomposed username/password auth (Quack uses single token only)
- Quack-specific pool tuning knobs (standard `QueuePool` params suffice)
- Quickstart example for Quack on `index.md` (listing only)

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUACK-01 | `QuackConfig` exists in `src/adbc_poolhouse/_quack_config.py`, inheriting `BaseWarehouseConfig` | Mirror `_databricks_config.py` structure |
| QUACK-02 | Exposes `uri`, `host`, `port`, `token`, `tls` fields | Field definitions locked in CONTEXT.md |
| QUACK-03 | Validates `uri` XOR `host` (model_validator) | Mirror ClickHouse `check_connection_spec` |
| QUACK-04 | `to_adbc_kwargs()` returns dict with optional token/tls keys | Locked serialization spec |
| QUACK-05 | `_driver_path()` returns `"adbc_driver_quack"` (PyPI module name) | Use `_resolve_driver_path` helper |
| QUACK-06 | `_dbapi_module()` returns `adbc_driver_quack.dbapi` module path | Mirror `SnowflakeConfig._dbapi_module` |
| QUACK-07 | Exported from `adbc_poolhouse.__init__` | Insert between `PostgreSQLConfig` and `RedshiftConfig` |
| QUACK-08 | `create_pool(QuackConfig(...))` works via self-describing dispatch | No `_pool_factory` changes needed |
| QUACK-09 | `pyproject.toml` `quack` extra: `adbc-driver-quack>=0.1.0a1` | Verified against PyPI (latest `0.1.0a6`) |
| QUACK-10 | Unit tests for validation in `tests/test_configs.py::TestQuackConfig` | Mirror `TestClickHouseConfig` (line 477+) |
| QUACK-11 | Semi-integration test with conditional mock | Mirror `TestSnowflakeImports` (lines 68-103) |
| QUACK-12 | All 241 existing tests continue to pass | Pure addition — no edits to existing tests |
| QUACK-13 | `docs/src/guides/quack.md` per-warehouse guide | Mirror `clickhouse.md` structure |
| QUACK-14 | Alpha warning admonition + GitHub link | Mirror ClickHouse alpha admonition |
| QUACK-15 | `configuration.md` table row added | Add `QUACK_` row to env_prefix table |
| QUACK-16 | `index.md` listing updated | Add to PyPI drivers table (with `--pre` note) |
| QUACK-17 | `mkdocs.yml` nav entry | Alphabetical position under Warehouse Guides |
| QUACK-18 | `mkdocs build --strict` passes + humanizer pass | Docs quality gate |

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-settings | >=2.0.0 | Config base + env loading | `BaseWarehouseConfig` already uses it |
| adbc-driver-manager | >=1.8.0 | ADBC dispatch | Underlying dependency |
| adbc-driver-quack | >=0.1.0a1 | Quack ADBC driver | The new optional dependency |

**Version verification (2026-05-19):**

```
PyPI adbc-driver-quack latest: 0.1.0a6
All releases: 0.1.0a1, 0.1.0a2, 0.1.0a3, 0.1.0a4, 0.1.0a5, 0.1.0a6
```
[VERIFIED: PyPI JSON API https://pypi.org/pypi/adbc-driver-quack/json]

Lower bound `>=0.1.0a1` will resolve to `0.1.0a6` today; no upper cap matches house style.

## Technical Approach Summary

The implementation is a hybrid of three existing backends — each contributes one shape feature:

| Source | What to copy |
|--------|--------------|
| `_databricks_config.py` | Two-mode URI XOR decomposed validator skeleton, `model_validator(mode="after")` with `Self` return |
| `_clickhouse_config.py` | Simpler validator (only two required fields, no `http_path` triple), `to_adbc_kwargs()` branching style, alpha-admonition guide layout |
| `_snowflake_config.py` | Dual `_driver_path() = self._resolve_driver_path(...)` + `_dbapi_module()` with `importlib.util.find_spec` gate (PyPI driver shipping its own dbapi submodule) |

The Quack driver is **simpler than any existing backend** for two reasons:

1. **No SecretStr on URI** — the upstream driver explicitly forbids embedding credentials in the URI, so `uri: str | None` (not `SecretStr | None`). Verified in CONTEXT.md against the README quote: "The URI is its own kwarg; everything else goes through `db_kwargs`."
2. **Single optional token** — no username/password decomposition needed; the token is one `SecretStr` field that goes through `adbc.quack.token` kwarg, never URL-encoded into the URI (unlike Databricks which embeds the token in `databricks://token:{quote(token)}@host:443/path`).

The `_pool_factory.py` self-describing dispatch (v1.2.0) requires zero changes — once `QuackConfig` returns a non-None `_dbapi_module()` (when driver installed) or `_driver_path()` (always), `create_pool` will route correctly.

## Reference Implementations to Mirror

### Pattern references (existing code)

| File | What to copy |
|------|--------------|
| `src/adbc_poolhouse/_databricks_config.py` | URI-first + decomposed fallback structure; `model_validator(mode="after")` returning `Self`; raise `ConfigurationError` for invalid combinations |
| `src/adbc_poolhouse/_clickhouse_config.py` | Simpler two-mode validator (only two fields required for decomposed); `to_adbc_kwargs()` branching on `self.uri is not None` first |
| `src/adbc_poolhouse/_snowflake_config.py` | `_driver_path() = self._resolve_driver_path("adbc_driver_quack")` (line 137); `_dbapi_module()` with `importlib.util.find_spec` gate (lines 139-142); the `import importlib.util` at the top |
| `src/adbc_poolhouse/_base_config.py` | `BaseWarehouseConfig` base, `WarehouseConfig` Protocol, `_resolve_driver_path` static helper at line 158 |
| `src/adbc_poolhouse/__init__.py` | Alphabetical export ordering — insert `from adbc_poolhouse._quack_config import QuackConfig` between PostgreSQL and Redshift imports; insert `"QuackConfig"` between `"PostgreSQLConfig"` and `"RedshiftConfig"` in `__all__` |

### Test references

| File | What to copy |
|------|--------------|
| `tests/test_configs.py::TestClickHouseConfig` (lines 477-562) | Full unit test class layout: env loading, mutual exclusion via `pytest.raises(ValidationError)`, `monkeypatch.setenv` for env prefix tests, `WarehouseConfig` protocol assertion |
| `tests/test_driver_imports.py::TestSnowflakeImports` (lines 68-103) | Conditional mock pattern: `if _driver_installed("adbc_driver_quack"): patch("adbc_driver_quack.dbapi.connect"); else: patch("adbc_driver_manager.dbapi.connect")` |
| `tests/test_drivers.py::test_clickhouse_returns_short_name` (line 170) | Pattern for testing `_driver_path()` short-name return. **But note:** Quack is PyPI, not Foundry — so the model is closer to `test_snowflake_missing_returns_package_name` (line 78) which patches `find_spec` and asserts the package name fallback |
| `tests/test_drivers.py::test_snowflake_installed_returns_dbapi_module` (line 112) | Pattern for asserting `_dbapi_module()` returns `"adbc_driver_quack.dbapi"` when find_spec returns a spec |

### Docs references

| File | What to copy |
|------|--------------|
| `docs/src/guides/clickhouse.md` | Alpha-status admonition style, dual-mode examples, env-var loading section, "See also" footer |
| `docs/src/guides/configuration.md` (line 11-23) | Format of env_prefix table row — add `[QuackConfig][adbc_poolhouse.QuackConfig]` + `QUACK_` |
| `docs/src/guides/configuration.md` (line 73) | Foundry-distributed paragraph — Quack does NOT belong here; it's PyPI. Add it to the PyPI list elsewhere |
| `docs/src/index.md` (lines 22-29) | Format of PyPI drivers table row — `pip install --pre adbc-poolhouse[quack]` (note `--pre` due to alpha) |
| `docs/src/index.md` (line 42) | "PyPI-installed" backend listing — add `QuackConfig` alphabetically |
| `mkdocs.yml` (lines 99-111) | Warehouse Guides nav — add `- Quack: guides/quack.md` alphabetically |

## Implementation Sequence

File-by-file order (each step independently testable; later steps depend on earlier ones):

1. **`src/adbc_poolhouse/_quack_config.py`** — new file
   - Imports: `importlib.util`, `Self` (typing), `SecretStr`, `model_validator` (pydantic), `SettingsConfigDict` (pydantic_settings), `BaseWarehouseConfig`, `ConfigurationError`
   - Class docstring (Google-style) with mode summary and alpha-driver note
   - Field declarations with attribute docstrings (`QUACK_*` env var mention)
   - `check_connection_spec` validator (`mode="after"`, returns `Self`)
   - `_driver_path() -> str` returning `self._resolve_driver_path("adbc_driver_quack")`
   - `_dbapi_module() -> str | None` with `find_spec` gate
   - `to_adbc_kwargs() -> dict[str, str]` with Args/Returns docstring

2. **`src/adbc_poolhouse/__init__.py`** — edit
   - Add `from adbc_poolhouse._quack_config import QuackConfig` after `PostgreSQLConfig` line, before `RedshiftConfig` line
   - Add `"QuackConfig",` to `__all__` between `"PostgreSQLConfig"` and `"RedshiftConfig"`

3. **`pyproject.toml`** — edit
   - Add `quack = ["adbc-driver-quack>=0.1.0a1"]` to `[project.optional-dependencies]`
   - Add `"adbc-poolhouse[quack]",` to the `all` extra list
   - **Do not** modify `adbc_auto_patch` — Quack uses the same on-demand mock pattern as Snowflake (existing entries cover what's needed; new tests use explicit `patch` calls)

4. **`tests/test_configs.py`** — edit
   - Import `QuackConfig` at top of file
   - Add `TestQuackConfig` class with all test cases listed in CONTEXT.md (URI-only, host-only, host+port, mutual exclusion both ways, kwargs round-trip in both modes, port-omission in decomposed mode, token passthrough, tls true/false, env prefix loads)

5. **`tests/test_driver_imports.py`** — edit
   - Add `QuackConfig` to the import block
   - Add `TestQuackImports` class mirroring `TestSnowflakeImports` lines 68-103 with conditional mock

6. **`tests/test_drivers.py`** — edit
   - Add to `TestPyPIDriverPath`: `test_quack_found_returns_driver_path` and `test_quack_missing_returns_package_name` (mirroring Snowflake at lines 65-82)
   - Add to `TestPyPIDbApiModule`: `test_quack_installed_returns_dbapi_module` and `test_quack_not_installed_returns_none` (mirroring Snowflake at lines 112-123)

7. **`docs/src/guides/quack.md`** — new file
   - Alpha admonition at top (mirror ClickHouse line-by-line)
   - External link to `https://github.com/gizmodata/adbc-driver-quack`
   - Install: `pip install --pre adbc-poolhouse[quack]`
   - URI-mode example
   - Decomposed-mode example
   - Token + TLS usage example
   - `QUACK_*` env-var section
   - "See also" footer linking `configuration.md` and `pool-lifecycle.md`
   - Use Markdown cross-refs `[QuackConfig][adbc_poolhouse.QuackConfig]` (NOT RST `:class:`)

8. **`docs/src/guides/configuration.md`** — edit
   - Add `| [`QuackConfig`][adbc_poolhouse.QuackConfig] | `QUACK_` |` row to env_prefix table (alphabetical or appended — match existing convention)

9. **`docs/src/index.md`** — edit
   - Add `| Quack | `pip install --pre adbc-poolhouse[quack]` |` row to PyPI drivers table (note `--pre`)
   - Add `QuackConfig` to the "PyPI-installed" listing on line 42 (alphabetical)

10. **`mkdocs.yml`** — edit
    - Add `- Quack: guides/quack.md` to Warehouse Guides nav (alphabetical with siblings — between MySQL and SQLite, or position to match index.md convention)

11. **`uv run mkdocs build --strict`** — must pass

12. **Humanizer pass** — apply to `quack.md` and any new prose in `configuration.md` / `index.md`

13. **`uv run pytest`** — all 241 prior tests pass + new Quack tests pass

## ADBC Driver Wiring Details

The v1.2.0 self-describing dispatch in `src/adbc_poolhouse/_pool_factory.py` (verified at lines 55-65) handles new backends with zero modification:

```python
cfg_driver_path = config._driver_path()
cfg_dbapi_module = config._dbapi_module()
if cfg_driver_path is None and cfg_dbapi_module is None:
    raise ...
```

For `QuackConfig`:

| Method | When driver installed | When driver missing | Used by `_pool_factory` |
|--------|----------------------|---------------------|--------------------------|
| `_driver_path()` | absolute `.so`/`.dylib` path from `adbc_driver_quack._driver_path()` | string `"adbc_driver_quack"` (manifest fallback) | Always non-None |
| `_dbapi_module()` | `"adbc_driver_quack.dbapi"` | `None` | Routes through Python dbapi when set |
| `_adbc_entrypoint()` | `None` (inherited) | `None` | Default init symbol |

**Dispatch decision:** When `_dbapi_module()` returns a non-None string, `_pool_factory` imports that module and calls its `connect()` — bypassing `adbc_driver_manager`. When it returns `None`, the factory falls back to `_driver_path()` and routes through `adbc_driver_manager.dbapi.connect(driver=..., entrypoint=...)`.

This is identical to Snowflake/BigQuery/PostgreSQL behavior — the only difference is the driver package name passed to `_resolve_driver_path`.

## Test Strategy

### Unit tests — `tests/test_configs.py::TestQuackConfig`

Mirror `TestClickHouseConfig` shape (lines 477-562). Required cases:

- **Construction** — URI-only succeeds; `host`-only succeeds (port defaults to None); `host`+`port` succeeds
- **Mutual exclusion** — both `uri` AND `host` → `pytest.raises(ValidationError)`; neither → `pytest.raises(ValidationError)`
- **Field types** — `token` is `SecretStr` (repr masking check); `uri` is plain `str` (not SecretStr — explicit assert)
- **`to_adbc_kwargs()` URI mode** — `{"uri": "quack://host:1234"}` round-trip
- **`to_adbc_kwargs()` decomposed without port** — input `host="h"`, no `port` → `uri == "quack://h"` (no `:None`)
- **`to_adbc_kwargs()` decomposed with port** — input `host="h"`, `port=1234` → `uri == "quack://h:1234"`
- **Token passthrough** — `token=SecretStr("tk")` → result contains `"adbc.quack.token": "tk"`
- **TLS True** — `tls=True` → result contains `"adbc.quack.tls": "true"`
- **TLS False omission** — `tls=False` (default) → key `"adbc.quack.tls"` **NOT** present in result
- **Env loading** — `QUACK_HOST`, `QUACK_PORT`, `QUACK_TOKEN`, `QUACK_TLS`, `QUACK_URI` all load via env_prefix (use `monkeypatch.setenv`)
- **Pool tuning inheritance** — `QUACK_POOL_SIZE=7` → `c.pool_size == 7`
- **Protocol satisfaction** — `isinstance(c, WarehouseConfig)` passes (structural check)

### Semi-integration test — `tests/test_driver_imports.py::TestQuackImports`

Mirror `TestSnowflakeImports` (lines 68-103) exactly. The class shape:

```python
class TestQuackImports:
    def test_create_pool_wiring(self) -> None:
        config = QuackConfig(host="h")  # minimal valid spec
        mock_conn = MagicMock()
        mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

        if _driver_installed("adbc_driver_quack"):
            with patch("adbc_driver_quack.dbapi.connect", return_value=mock_conn) as mock_connect:
                pool = create_pool(config)
                pool.dispose()
            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            assert "uri" in call_kwargs  # Quack config keys arrive in kwargs
        else:
            with patch("adbc_driver_manager.dbapi.connect", return_value=mock_conn) as mock_connect:
                pool = create_pool(config)
                pool.dispose()
            mock_connect.assert_called_once()
            assert "driver" in mock_connect.call_args.kwargs
```

### Driver path / dbapi unit tests — `tests/test_drivers.py`

Add to `TestPyPIDriverPath` (lines 62-106):

- `test_quack_found_returns_driver_path` — patches `find_spec` and `__import__` to inject a mock package returning a fake `.so` path; asserts the path round-trips
- `test_quack_missing_returns_package_name` — patches `find_spec` to None; asserts `QuackConfig(host="h")._driver_path() == "adbc_driver_quack"`

Add to `TestPyPIDbApiModule` (lines 109-148):

- `test_quack_installed_returns_dbapi_module` — patches `find_spec` to a MagicMock; asserts result `== "adbc_driver_quack.dbapi"`
- `test_quack_not_installed_returns_none` — patches `find_spec` to None; asserts result is `None`

### Test-count invariant

CONTEXT.md QUACK-12 requires all 241 existing tests continue to pass. Adding new tests (estimated ~20 new) means the post-phase count should be ~261. No edits to existing tests are required — this is a pure addition.

### File-location decision

**Resolved discrepancy:** REQUIREMENTS.md QUACK-10 says `tests/test_quack_config.py`; CONTEXT.md says `tests/test_configs.py::TestQuackConfig`. CONTEXT.md is the more recent locked decision and aligns with the established pattern (all 12 existing backends live in `tests/test_configs.py`). **Use `tests/test_configs.py::TestQuackConfig`** — flag the QUACK-10 wording in the plan as superseded by CONTEXT.md.

## Documentation Strategy

### Per-warehouse guide (`docs/src/guides/quack.md`)

Structure (mirror `clickhouse.md`):

1. H1 title — "Quack guide"
2. Alpha admonition (use MkDocs `!!! warning` or `!!! note` — match ClickHouse exactly)
3. External link to `https://github.com/gizmodata/adbc-driver-quack`
4. Install command: `pip install --pre adbc-poolhouse[quack]` (explain `--pre` for alpha)
5. ## Connection — overview of URI XOR decomposed modes; `ConfigurationError` link
6. ### URI mode — code example using plain string URI (no `SecretStr` wrapping — explain in prose why Quack differs from ClickHouse)
7. ### Decomposed mode — `host`/`port`/`token`/`tls` example
8. ### TLS — note default-off, set `tls=True` for TLS
9. ## Loading from environment variables — `QUACK_*` prefix
10. ## See also — links to `configuration.md`, `pool-lifecycle.md`

mkdocstrings cross-refs use Markdown syntax: `` [QuackConfig][adbc_poolhouse.QuackConfig] `` — NOT RST `:class:`QuackConfig``.

### `configuration.md` updates

- Add row to env_prefix table (line 11-23): `| [`QuackConfig`][adbc_poolhouse.QuackConfig] | `QUACK_` |`
- **Do NOT** add Quack to the Foundry paragraph (line 73) — Quack is PyPI, not Foundry. If a parallel PyPI listing exists, add Quack there; otherwise the env_prefix row alone is sufficient

### `index.md` updates

- Add row to PyPI drivers table (line 23-29): `| Quack | `pip install --pre adbc-poolhouse[quack]` |` — explicit `--pre` note required
- Add `QuackConfig` to the PyPI-installed config listing (line 42), alphabetical: `BigQueryConfig, DuckDBConfig, FlightSQLConfig, PostgreSQLConfig, QuackConfig, SnowflakeConfig, SQLiteConfig`

### `mkdocs.yml` nav

Add `- Quack: guides/quack.md` to the Warehouse Guides nav block (lines 99-111). Current ordering is mixed (not strictly alphabetical — Snowflake first, others scattered). **Recommendation:** Append at the end before SQLite, or insert alphabetically — match the convention used when ClickHouse and MySQL were added.

### Quality gates (CLAUDE.md, phase >= 7)

1. **Google-style docstrings** on `QuackConfig` class and all public fields (attribute docstrings string-literal style for Pydantic, per skill rules)
2. **Markdown in docstrings** — backticks for cross-refs, NOT RST `:func:` / `:class:` roles (project memory rule)
3. **`uv run mkdocs build --strict`** must exit 0 — strict mode fails on broken cross-refs, so verify the `[QuackConfig][...]` link resolves
4. **Humanizer pass** — eliminate promotional language ("powerful", "seamlessly"), AI vocabulary ("delve", "leverage"), vague attributions ("this allows you to"), em dash overuse (max one per paragraph). Apply per `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` and the linked humanizer skill
5. **`adbc-poolhouse-docs-author` skill** referenced in PLAN.md `<execution_context>` block for the documentation plan(s)
6. **Example block** — class docstring should include an `Example:` admonition section with a fenced ` ```python ` block (per project memory: `Example:` singular = admonition box; `Examples:` plural = plain doctest section)

## Validation Architecture

> Required section for Nyquist VALIDATION.md generation.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0.0 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/test_configs.py::TestQuackConfig tests/test_driver_imports.py::TestQuackImports -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| QUACK-01 | `QuackConfig` class exists and inherits `BaseWarehouseConfig` | unit | `uv run pytest tests/test_configs.py::TestQuackConfig::test_uri_mode_constructs -x` |
| QUACK-02 | Fields `uri`, `host`, `port`, `token`, `tls` exist with correct types | unit | `uv run pytest tests/test_configs.py::TestQuackConfig -k field -x` |
| QUACK-03 | Mutual exclusion enforced | unit | `uv run pytest tests/test_configs.py::TestQuackConfig -k "exclusion or raises" -x` |
| QUACK-04 | `to_adbc_kwargs()` shape including omitted keys | unit | `uv run pytest tests/test_configs.py::TestQuackConfig -k kwargs -x` |
| QUACK-05 | `_driver_path()` returns `"adbc_driver_quack"` when not installed | unit | `uv run pytest tests/test_drivers.py::TestPyPIDriverPath::test_quack_missing_returns_package_name -x` |
| QUACK-06 | `_dbapi_module()` returns `"adbc_driver_quack.dbapi"` when installed | unit | `uv run pytest tests/test_drivers.py::TestPyPIDbApiModule::test_quack_installed_returns_dbapi_module -x` |
| QUACK-07 | Exported from `adbc_poolhouse.__init__` | unit | `uv run python -c "from adbc_poolhouse import QuackConfig; assert QuackConfig"` |
| QUACK-08 | `create_pool(QuackConfig(...))` returns a pool | semi-integration | `uv run pytest tests/test_driver_imports.py::TestQuackImports -x` |
| QUACK-09 | `pyproject.toml` declares `quack` extra | manual / file inspection | `grep -A1 "^quack" pyproject.toml` |
| QUACK-10 | Unit tests exist | unit | `uv run pytest tests/test_configs.py::TestQuackConfig -x` |
| QUACK-11 | Semi-integration test exists | semi-integration | `uv run pytest tests/test_driver_imports.py::TestQuackImports -x` |
| QUACK-12 | 241 existing tests still pass | unit (full suite) | `uv run pytest` (assert exit 0) |
| QUACK-13 | `quack.md` guide exists with required sections | manual / build | `uv run mkdocs build --strict` (fails on broken cross-refs) + manual section review |
| QUACK-14 | Alpha warning + external link present | manual | grep `quack.md` for admonition keyword + `gizmodata/adbc-driver-quack` URL |
| QUACK-15 | `configuration.md` table row present | manual | grep `configuration.md` for `QUACK_` |
| QUACK-16 | `index.md` listing updated | manual | grep `index.md` for `quack` + `QuackConfig` |
| QUACK-17 | `mkdocs.yml` nav entry present | build | `uv run mkdocs build --strict` (would warn on un-nav'd guide) + grep yaml |
| QUACK-18 | mkdocs strict + humanizer | build + manual | `uv run mkdocs build --strict` + humanizer-checklist review |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_configs.py::TestQuackConfig -x` (fastest signal; runs in < 5s)
- **Per wave merge:** `uv run pytest` (full suite; ~30s) + `uv run mkdocs build --strict`
- **Phase gate:** Full suite green + mkdocs strict pass + humanizer checklist applied + `/gsd-verify-work`

### Wave 0 Gaps

- None — existing test infrastructure (pytest, conftest, `tests/test_configs.py`, `tests/test_driver_imports.py`, `tests/test_drivers.py`) covers all required test types. No new framework install or fixtures needed.

### Validation gates (Nyquist sampling)

| Gate | Mechanism | Coverage |
|------|-----------|----------|
| Mutual-exclusion validation | Unit tests with `pytest.raises(ValidationError)` | QUACK-03 |
| Env-var loading | Unit tests with `monkeypatch.setenv` | QUACK-02 (env), QUACK-12 (pool tuning inheritance) |
| Kwarg shape (URI mode, decomposed mode, token, tls on/off) | Unit tests on `to_adbc_kwargs()` return value | QUACK-04 |
| Driver dispatch wiring | Semi-integration test with conditional mock | QUACK-05, QUACK-06, QUACK-08, QUACK-11 |
| Docs build correctness | `uv run mkdocs build --strict` | QUACK-13, QUACK-14, QUACK-15, QUACK-16, QUACK-17, QUACK-18 |
| Prose quality | Humanizer-checklist manual review | QUACK-18 |
| Regression safety | Full pytest run | QUACK-12 |

## Project Constraints (from CLAUDE.md)

- **Phase >= 7 docs gate (this phase is 21):** All new public symbols need Google-style docstrings (Args/Returns/Raises); key entry points need an `Example:` block; consumer-facing behavior reflected in the guide; `uv run mkdocs build --strict` passes; humanizer pass applied to all new or substantially rewritten prose
- **Docs-author skill required:** Plans for documentation work MUST include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>`
- **Docstring style (from MEMORY.md):** Google-style; Markdown syntax in docstrings (NOT RST); `Example:` singular for admonition; mkdocstrings cross-refs use `` [Name][module.Name] `` Markdown form

## Risks and Mitigations

### Risk 1: Alpha driver install behavior
**What goes wrong:** `pip install adbc-poolhouse[quack]` without `--pre` may fail to resolve the alpha `adbc-driver-quack==0.1.0a6` because pip's default resolver excludes pre-releases unless `--pre` is specified or the requirement is itself pre-release-pinned.
**Why it happens:** PEP 440 says pre-releases are excluded by default; a constraint of `>=0.1.0a1` *should* allow pre-releases (since the constraint itself names a pre-release), but pip's heuristics vary by version.
**How to avoid:** Document `pip install --pre adbc-poolhouse[quack]` in `quack.md` and `index.md`. Optionally test on a clean venv.
**Warning signs:** "Could not find a version that satisfies the requirement adbc-driver-quack>=0.1.0a1" — solved by `--pre`.

### Risk 2: Env-var leakage in tests
**What goes wrong:** Tests that set `QUACK_URI` or `QUACK_HOST` via `monkeypatch.setenv` leak into other tests, causing `QuackConfig()` in unrelated tests to silently pick up state.
**Why it happens:** Pydantic-settings reads env at instantiation; if a prior test set `QUACK_HOST=foo` without proper teardown, subsequent `QuackConfig()` calls pick it up.
**How to avoid:** Always use `monkeypatch.setenv` (auto-reverts per test) and never `os.environ[...] = ...`. Verify by running the new tests in isolation AND interleaved with the full suite. The existing `TestClickHouseConfig` shows the correct pattern.
**Warning signs:** Tests pass individually but fail when run together; assertion failures on `c.host is None`.

### Risk 3: Driver-side TLS default
**What goes wrong:** A future driver release changes the default of `adbc.quack.tls` from `"false"` to `"true"`. Our omit-on-False behavior would then silently enable TLS.
**Why it happens:** Alpha driver behavior is unstable; defaults may shift.
**How to avoid:** The locked decision (omit on False) matches the *current* driver default. If the driver default flips, we either keep our omit-on-False semantics (and accept the behavior change tracks upstream) or switch to always-emit. Document the dependency on the current default in the `to_adbc_kwargs` docstring.
**Warning signs:** Integration users report unexpected TLS handshakes after a driver upgrade.

### Risk 4: mkdocs strict mode catching cross-ref typos
**What goes wrong:** `[QuackConfig][adbc_poolhouse.QuackConfig]` mistyped as `[adbc_poolhouse.QuackConfig]` fails the strict build.
**Why it happens:** mkdocstrings cross-refs are case-sensitive and module-path-sensitive.
**How to avoid:** Run `uv run mkdocs build --strict` after every doc edit, not only at the end.
**Warning signs:** mkdocs warns "Could not find a python object" — usually a typo or missing export from `__init__.py`.

### Risk 5: REQUIREMENTS vs CONTEXT discrepancy on test file location
**What goes wrong:** Implementer follows QUACK-10 wording literally and creates `tests/test_quack_config.py`, breaking the project-wide pattern of co-locating tests in `tests/test_configs.py`.
**Why it happens:** REQUIREMENTS.md and CONTEXT.md disagree.
**How to avoid:** Plan should explicitly state "follow CONTEXT.md — `tests/test_configs.py::TestQuackConfig`" and note REQUIREMENTS.md wording is superseded.
**Warning signs:** Reviewer asks why Quack alone has a separate test file.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Project | ✓ | >=3.11 (project requirement) | — |
| uv | Test/build commands | ✓ (assumed — used throughout project) | — | `python -m pytest` |
| pytest | Test execution | ✓ | >=8.0.0 (dev dep) | — |
| mkdocs + Material | Docs build | ✓ | mkdocs>=1.6.0 (docs dep) | — |
| mkdocstrings[python] | Docs cross-refs | ✓ | >=0.26.0 | — |
| adbc-driver-quack | Optional — for live testing only | unknown (alpha) | latest: 0.1.0a6 | Tests use `find_spec` gate and conditional mock — work whether or not driver is installed |

**No blocking dependencies.** The semi-integration test is specifically designed to work without the driver installed (mocks `adbc_driver_manager.dbapi.connect` in that case).

## Code Examples

### Example 1: QuackConfig class shape (mirroring Databricks + Snowflake)

```python
# src/adbc_poolhouse/_quack_config.py
"""Quack warehouse configuration."""

from __future__ import annotations

import importlib.util
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class QuackConfig(BaseWarehouseConfig):
    """
    Quack warehouse configuration.

    Uses the `adbc-driver-quack` PyPI driver (DuckDB Quack remote protocol).
    The driver is alpha — install with `pip install --pre adbc-poolhouse[quack]`.

    Supports two connection modes:

    - URI mode: set `uri` with `quack://host[:port]`.
    - Decomposed mode: set `host` and optionally `port`.

    Construction raises `ConfigurationError` if both modes are set
    simultaneously or if neither is set.

    Example:
        ```python
        from adbc_poolhouse import QuackConfig, create_pool

        config = QuackConfig(host="quack.example.com", port=8080)
        pool = create_pool(config)
        ```
    """

    model_config = SettingsConfigDict(env_prefix="QUACK_")

    uri: str | None = None
    """Full connection URI `quack://host[:port]`. The driver's URI cannot
    embed credentials, so this is a plain str. Env: QUACK_URI."""

    host: str | None = None
    """Quack server hostname. Alternative to URI mode. Env: QUACK_HOST."""

    port: int | None = None
    """Quack server port. Optional even in decomposed mode. Env: QUACK_PORT."""

    token: SecretStr | None = None
    """Bearer token. Passes via `adbc.quack.token` kwarg, never embedded
    in the URI. Env: QUACK_TOKEN."""

    tls: bool = False
    """Enable TLS. When False (default), the `adbc.quack.tls` kwarg is
    omitted entirely. Env: QUACK_TLS."""

    @model_validator(mode="after")
    def check_connection_spec(self) -> Self:
        """Raise ConfigurationError on uri+host both set or neither set."""
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

    def _driver_path(self) -> str:
        return self._resolve_driver_path("adbc_driver_quack")

    def _dbapi_module(self) -> str | None:
        if importlib.util.find_spec("adbc_driver_quack") is not None:
            return "adbc_driver_quack.dbapi"
        return None

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert config to ADBC driver connection kwargs.

        Returns:
            Dict with `uri` always set. `adbc.quack.token` is included
            when `token` is set; `adbc.quack.tls` is included only when
            `tls=True` (omitted on False — driver default is "false").
        """
        if self.uri is not None:
            uri = self.uri
        else:
            assert self.host is not None  # model_validator guarantees
            uri = f"quack://{self.host}:{self.port}" if self.port is not None else f"quack://{self.host}"

        result: dict[str, str] = {"uri": uri}
        if self.token is not None:
            result["adbc.quack.token"] = self.token.get_secret_value()  # pragma: allowlist secret
        if self.tls:
            result["adbc.quack.tls"] = "true"
        return result
```

Source: synthesized from `_databricks_config.py`, `_clickhouse_config.py`, `_snowflake_config.py` patterns. Verified field order against REQUIREMENTS.md QUACK-02.

### Example 2: Conditional-mock semi-integration test

```python
# tests/test_driver_imports.py — append after TestSnowflakeImports
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

Source: line-for-line mirror of `tests/test_driver_imports.py::TestSnowflakeImports` (lines 68-103).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Adding `QuackConfig` requires no edits to `_pool_factory.py` | ADBC Driver Wiring Details | Plan misses a required edit; would surface immediately in `TestQuackImports` failure |
| A2 | `tests/test_configs.py::TestQuackConfig` is the correct location (per CONTEXT.md, not the `tests/test_quack_config.py` in QUACK-10) | Test Strategy | Low — either location works; reviewer might request file rename |
| A3 | `pip install --pre` is required for alpha driver resolution | Risks | Low — `--pre` is harmless when not needed |
| A4 | `mkdocs build --strict` will warn on a guide file present but not in nav | Validation Architecture | Medium — if false, QUACK-17 still requires explicit nav entry per acceptance criteria |
| A5 | mkdocs nav ordering: alphabetical within Warehouse Guides | Documentation Strategy | Low — current `mkdocs.yml` is not strictly alphabetical; planner can choose position |

All other research claims are verified against either the upstream README (via WebFetch), the project source code (via direct file reads), or PyPI JSON API (curl).

## Open Questions

None — CONTEXT.md has locked all material decisions and the upstream README has been re-verified. Two minor clarifications already addressed in the body:

1. **Test file location:** REQUIREMENTS.md QUACK-10 vs CONTEXT.md disagree — resolved in favor of CONTEXT.md (`tests/test_configs.py::TestQuackConfig`).
2. **mkdocs nav order:** Existing `mkdocs.yml` is not strictly alphabetical; planner can choose either alphabetical or append. Recommend documenting the choice in PLAN.md.

## Sources

### Primary (HIGH confidence)
- `src/adbc_poolhouse/_databricks_config.py` (read in full) — URI/decomposed pattern
- `src/adbc_poolhouse/_clickhouse_config.py` (read in full) — two-mode validator pattern
- `src/adbc_poolhouse/_snowflake_config.py` (read in full) — PyPI dual-method pattern
- `src/adbc_poolhouse/_base_config.py` (read in full) — `BaseWarehouseConfig`, Protocol, `_resolve_driver_path`
- `src/adbc_poolhouse/__init__.py` (read in full) — export ordering
- `src/adbc_poolhouse/_pool_factory.py` (lines 1-100, grep) — self-describing dispatch verified
- `tests/test_configs.py` lines 477-562 — `TestClickHouseConfig` shape
- `tests/test_driver_imports.py` lines 1-110 — conditional mock pattern
- `tests/test_drivers.py` lines 62-203 — PyPI driver path + dbapi tests
- `docs/src/guides/clickhouse.md` — guide pattern
- `docs/src/guides/configuration.md` — table format
- `docs/src/index.md` — backend listing format
- `mkdocs.yml` — nav structure
- `pyproject.toml` — current extras shape
- `CLAUDE.md` — phase >= 7 docs gate
- `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — docs voice + humanizer rules
- `~/.claude/projects/.../MEMORY.md` — docstring style rules (Google + Markdown not RST)

### Secondary (MEDIUM confidence — verified via WebFetch + curl)
- `https://github.com/gizmodata/adbc-driver-quack` README — URI scheme, kwarg names, dbapi module path, alpha status (WebFetch, 2026-05-19)
- `https://pypi.org/pypi/adbc-driver-quack/json` — current published versions `0.1.0a1` through `0.1.0a6` (curl JSON API, 2026-05-19)

### Tertiary
- None — all assertions are verified or marked as ASSUMED in the Assumptions Log.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified against PyPI JSON API and upstream README on 2026-05-19
- Architecture: HIGH — three reference implementations read in full, pattern is unambiguous mirror
- Pitfalls: HIGH for items 1-4 (each maps to a known project pattern); MEDIUM for item 5 (depends on reviewer interpretation)
- Validation Architecture: HIGH — test framework and infrastructure exist; no Wave 0 gaps

**Research date:** 2026-05-19
**Valid until:** 2026-06-19 (alpha driver may publish new versions; project patterns are stable)
