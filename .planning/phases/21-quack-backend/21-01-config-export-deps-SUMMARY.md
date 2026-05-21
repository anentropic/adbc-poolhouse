---
phase: 21
plan: 01
subsystem: quack-backend
tags: [quack, config, packaging, public-api]
requires:
  - BaseWarehouseConfig (src/adbc_poolhouse/_base_config.py)
  - ConfigurationError (src/adbc_poolhouse/_exceptions.py)
  - SettingsConfigDict (pydantic-settings)
  - SecretStr, model_validator (pydantic)
provides:
  - QuackConfig (src/adbc_poolhouse/_quack_config.py)
  - QuackConfig in adbc_poolhouse public API
  - [quack] optional dependency group declaring adbc-driver-quack>=0.1.0a1
affects:
  - src/adbc_poolhouse/__init__.py (added import + __all__ entry)
  - pyproject.toml (added [quack] extra + entry in [all])
  - uv.lock (resolved adbc-driver-quack 0.1.0a6)
tech-stack:
  added: ["adbc-driver-quack (alpha, PyPI)"]
  patterns:
    - "Snowflake-style dual _driver_path + _dbapi_module with find_spec gate"
    - "URI XOR decomposed mutual-exclusion model_validator (Databricks/ClickHouse pattern)"
    - "SecretStr token with .get_secret_value() only inside to_adbc_kwargs()"
key-files:
  created:
    - src/adbc_poolhouse/_quack_config.py
    - .planning/phases/21-quack-backend/21-01-config-export-deps-SUMMARY.md
  modified:
    - src/adbc_poolhouse/__init__.py
    - pyproject.toml
    - uv.lock
decisions:
  - "uri is plain str (not SecretStr) — Quack URI cannot embed credentials"
  - "tls=False omits adbc.quack.tls kwarg entirely; emit 'true' only when tls=True"
  - "Decomposed mode rebuilds quack://{host}:{port} or quack://{host} (no port placeholder)"
  - "Token passes only via adbc.quack.token kwarg, never embedded in URI"
metrics:
  duration_seconds: 140
  completed: 2026-05-19
  tasks_completed: 3
  files_changed: 4
---

# Phase 21 Plan 01: Config, Export, Dependencies Summary

QuackConfig Pydantic model implementing the WarehouseConfig Protocol for the DuckDB Quack remote protocol via `adbc-driver-quack` (alpha PyPI driver), exported from the public API and declared as the `[quack]` optional extra.

## What Was Built

### `src/adbc_poolhouse/_quack_config.py` (new — 128 lines)

`QuackConfig(BaseWarehouseConfig)` with:

- Fields per QUACK-02 (locked in 21-CONTEXT.md):
  - `uri: str | None = None` — plain `str`, not `SecretStr` (Quack URI cannot embed credentials)
  - `host: str | None = None`
  - `port: int | None = None`
  - `token: SecretStr | None = None`
  - `tls: bool = False`
- `model_config = SettingsConfigDict(env_prefix="QUACK_")` for env-var loading
- `@model_validator(mode="after") check_connection_spec` — raises `ConfigurationError` when both `uri` and `host` are set, or when neither is set
- `_driver_path() -> str` — delegates to `self._resolve_driver_path("adbc_driver_quack")` (Snowflake pattern)
- `_dbapi_module() -> str | None` — returns `"adbc_driver_quack.dbapi"` when `importlib.util.find_spec("adbc_driver_quack")` is non-None, else `None`
- `to_adbc_kwargs() -> dict[str, str]`:
  - URI mode (`uri` set): passes `uri` through verbatim
  - Decomposed mode: rebuilds `quack://{host}:{port}` when port is set, `quack://{host}` when port is `None`
  - `adbc.quack.token` is included only when `token` is set (`.get_secret_value()` called here only)
  - `adbc.quack.tls = "true"` is included only when `tls=True` (omitted on default `False`)
- Google-style class docstring with `Example:` admonition (singular, fenced ```python```) and Markdown cross-ref `[create_pool][adbc_poolhouse.create_pool]` — no RST `:role:` syntax

### `src/adbc_poolhouse/__init__.py`

- Added `from adbc_poolhouse._quack_config import QuackConfig` between `PostgreSQLConfig` and `RedshiftConfig` imports
- Added `"QuackConfig",` to `__all__` between `"PostgreSQLConfig"` and `"RedshiftConfig"`

### `pyproject.toml`

- Added `quack = ["adbc-driver-quack>=0.1.0a1"]` to `[project.optional-dependencies]`
- Added `"adbc-poolhouse[quack]",` to the `all` extra list
- Alpha lower bound only, no upper cap — matches house style; `pip install --pre` may be required for resolution

### `uv.lock`

Regenerated; resolved `adbc-driver-quack 0.1.0a6` (latest available alpha).

## Decisions Ratified

| Decision | Status |
|----------|--------|
| `uri` field is plain `str`, not `SecretStr` | Confirmed — Quack URI does not carry credentials |
| `tls=False` omits the `adbc.quack.tls` kwarg entirely | Confirmed — driver default applies |
| Decomposed-mode URI uses `quack://{host}` (no `:None`) when port is unset | Confirmed |
| `token` passes only through `adbc.quack.token`, never URL-encoded into the URI | Confirmed |
| Snowflake dual `_driver_path` + `_dbapi_module` pattern (PyPI driver) | Confirmed |
| Mutual exclusion validator raises `ConfigurationError` (pydantic wraps as `ValidationError`) | Confirmed |
| `pyproject.toml` `[quack]` extra with `>=0.1.0a1` lower bound, included in `[all]` | Confirmed |
| Env prefix `QUACK_` | Confirmed |

## Verification Outputs

Task 1 inline-python verify:
```
$ uv run python -c "...assert k == {'uri': 'quack://h'}...; ...assert c2.to_adbc_kwargs() == {'uri': 'quack://h:1234', 'adbc.quack.tls': 'true'}...; print('OK')"
OK
```

Task 2 inline-python verify:
```
$ uv run python -c "from adbc_poolhouse import QuackConfig; ...assert 'QuackConfig' in adbc_poolhouse.__all__...; print('OK')"
OK
```

Task 3 grep + lock check:
```
$ grep -q '^quack = \["adbc-driver-quack>=0.1.0a1"\]' pyproject.toml && echo OK
OK
$ grep -q '"adbc-poolhouse\[quack\]"' pyproject.toml && echo OK
OK
$ uv lock --check
Resolved 88 packages in 3ms
```

Mutual exclusion verify:
```
$ uv run python -c "QuackConfig(uri='quack://h:1', host='h')"
... ValidationError ...
$ uv run python -c "QuackConfig()"
... ValidationError ...
```

Final cross-check:
```
$ uv run python -c "from adbc_poolhouse import QuackConfig; print('import OK')"
import OK
$ grep -E ':(class|func|meth|mod|obj):`' src/adbc_poolhouse/_quack_config.py
(no output — no RST role syntax present)
```

## Commits

| Task | Hash    | Type  | Message |
|------|---------|-------|---------|
| 1    | f4bb8e7 | feat  | add QuackConfig for adbc-driver-quack backend |
| 2    | 8fdbd69 | feat  | export QuackConfig from adbc_poolhouse public API |
| 3    | 3328288 | chore | declare [quack] optional dependency for adbc-driver-quack |

## Requirements Addressed

- QUACK-01: `QuackConfig` class importable from `adbc_poolhouse`
- QUACK-02: All five fields present with locked types (uri plain str, token SecretStr)
- QUACK-03: Mutual exclusion validator raises on both-set and neither-set
- QUACK-04: `to_adbc_kwargs` shape matches CONTEXT.md spec (token/tls omission semantics)
- QUACK-05: `_driver_path` delegates to `_resolve_driver_path("adbc_driver_quack")`
- QUACK-06: `_dbapi_module` find_spec-gated to `"adbc_driver_quack.dbapi"`
- QUACK-07: `QuackConfig` in `__all__` and importable from `adbc_poolhouse`
- QUACK-09: `pyproject.toml` declares `quack` extra with `>=0.1.0a1` alpha lower bound

## Deviations from Plan

**1. [Rule 3 - Blocker] Lockfile regeneration**

- Found during: Task 3 verification (`uv lock --check`)
- Issue: After adding `quack` extra, `uv lock --check` reported the lockfile needed updating
- Fix: Ran `uv lock` to resolve `adbc-driver-quack 0.1.0a6`; verified `uv lock --check` exits 0 afterwards
- Files modified: `uv.lock`
- Commit: `3328288` (rolled into Task 3 commit since lockfile and pyproject changes are inseparable)

**2. [Rule 3 - Worktree base] Branch base behind feature branch**

- Found during: Pre-execution `worktree_branch_check`
- Issue: Worktree HEAD was at `4bf4e79` (main) but the feature branch base is `dbca9d4` (phase-21 docs)
- Fix: Fast-forwarded the worktree branch with `git reset --hard dbca9d4` (no local commits to preserve)
- Plus copied `21-01-config-export-deps-PLAN.md` and `21-RESEARCH.md` from the main checkout into this worktree's `.planning/phases/21-quack-backend/` (the worktree had been created before plans were written to disk)

No deviations from `21-CONTEXT.md` locked decisions.

## Threat Surface

All entries in the plan's `<threat_model>` STRIDE register (T-21-01 through T-21-04) remain accurate. No new threat surfaces introduced beyond what was already documented in the plan:

- T-21-01 mitigated: `SecretStr` masks token on repr/str; `.get_secret_value()` is called only inside `to_adbc_kwargs`; never logged
- T-21-02 mitigated: Decomposed URI built from typed fields (`str`, `int`); only `token` and `tls` are additional kwargs and come from typed fields
- T-21-03 mitigated: `ConfigurationError` messages reference field names ("'uri'", "'host'") only, never values
- T-21-04 accepted: Once `.get_secret_value()` returns into kwargs, downstream `adbc-driver-quack` controls handling (matches Snowflake/Databricks precedent)

## Known Stubs

None. All fields are wired, validator and serializer fully implemented, and the public API export is complete.

## Self-Check: PASSED

Files exist:
- FOUND: src/adbc_poolhouse/_quack_config.py
- FOUND: src/adbc_poolhouse/__init__.py (modified)
- FOUND: pyproject.toml (modified)
- FOUND: uv.lock (modified)
- FOUND: .planning/phases/21-quack-backend/21-01-config-export-deps-SUMMARY.md

Commits exist:
- FOUND: f4bb8e7 — feat(21-01): add QuackConfig for adbc-driver-quack backend
- FOUND: 8fdbd69 — feat(21-01): export QuackConfig from adbc_poolhouse public API
- FOUND: 3328288 — chore(21-01): declare [quack] optional dependency for adbc-driver-quack
