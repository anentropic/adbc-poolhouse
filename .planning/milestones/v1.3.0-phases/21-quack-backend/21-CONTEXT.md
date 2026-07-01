# Phase 21: Quack Backend - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning
**Source:** /gsd-list-phase-assumptions exchange (user-confirmed corrections)

<domain>
## Phase Boundary

Add a new warehouse backend, `QuackConfig`, for the `adbc-driver-quack` PyPI driver (DuckDB Quack remote protocol). Delivers:

- `QuackConfig` Pydantic model implementing the `WarehouseConfig` Protocol
- Driver detection via PyPI path (`adbc_driver_quack`) with `_dbapi_module()` returning `adbc_driver_quack.dbapi`
- Optional dependency group `[quack]` in `pyproject.toml`
- Export from `adbc_poolhouse.__init__`
- Unit tests for validation + semi-integration test for pool wiring
- Per-warehouse guide page in docs, `configuration.md` row, `index.md` listing, `mkdocs.yml` nav entry
- Documentation quality gate satisfied (Google-style docstrings, `mkdocs build --strict` passing, humanizer pass)

**No changes to `_pool_factory.py`** — the v1.2.0 self-describing dispatch handles new backends automatically.

</domain>

<decisions>
## Implementation Decisions

### Config class shape
- File: `src/adbc_poolhouse/_quack_config.py`
- Inherits `BaseWarehouseConfig` with `SettingsConfigDict(env_prefix="QUACK_")`
- Fields exactly as REQUIREMENTS QUACK-02 specifies:
  - `uri: str | None = None` — **plain `str`, not `SecretStr`** (locked decision)
  - `host: str | None = None`
  - `port: int | None = None`
  - `token: SecretStr | None = None`
  - `tls: bool = False`
- All fields env-overridable via `QUACK_URI`, `QUACK_HOST`, `QUACK_PORT`, `QUACK_TOKEN`, `QUACK_TLS`

### URI / token / TLS conventions (locked from upstream driver README)
- The Quack driver's URI cannot embed credentials. Quote from `gizmodata/adbc-driver-quack`: "The URI is its own kwarg; everything else goes through `db_kwargs`."
- URI scheme is `quack://host[:port]` — port is optional in the URI itself.
- Therefore: `uri` field is plain `str` (no SecretStr wrapping needed, no credentials to protect).

### `to_adbc_kwargs()` behavior
- Returns `dict[str, str]` matching the driver's expected shape:
  ```python
  {
      "uri": "quack://...",
      "adbc.quack.token": "...",   # omitted when token is None
      "adbc.quack.tls": "true",    # omitted when tls is False (driver default)
  }
  ```
- **URI mode** (`uri` set): pass `uri` through verbatim.
- **Decomposed mode** (`host` set, no `uri`): rebuild `uri` as:
  - `quack://{host}:{port}` when `port` is set
  - `quack://{host}` when `port` is None (locked decision — omit explicit port)
- Token passes through `adbc.quack.token` kwarg — **never embedded in the URI**, never URL-encoded.
- `tls`: omit the `adbc.quack.tls` kwarg when `False` (driver default is `"false"`). Emit `"true"` only when `True`. This satisfies QUACK-04 "omitted when not set" by treating default-False as "not set".

### Mutual exclusion validator
- `@model_validator(mode="after")` raises `ConfigurationError` when:
  - Both `uri` AND `host` are set (mutual exclusion)
  - Neither `uri` NOR `host` is set (one required)
- `port` alone is not a valid spec (always needs `host` or `uri`)
- Matches the Pydantic `ValidationError`-wraps-`ConfigurationError` pattern used by Databricks/ClickHouse

### Driver dispatch wiring
- `_driver_path() -> str`: `return self._resolve_driver_path("adbc_driver_quack")` — same as Snowflake/BigQuery/PostgreSQL
- `_dbapi_module() -> str | None`: returns `"adbc_driver_quack.dbapi"` when `importlib.util.find_spec("adbc_driver_quack")` is not None, else `None`
- `_adbc_entrypoint()`: not overridden (default `None`)

### Dependency declaration
- `pyproject.toml` `[project.optional-dependencies]` adds:
  ```toml
  quack = ["adbc-driver-quack>=0.1.0a1"]
  ```
- `all` extra (line 25-28 area) updated to include `"adbc-poolhouse[quack]"`
- Alpha lower bound `0.1.0a1`, no upper cap — matches house style
- **Document `pip install --pre`** in the guide because the driver is alpha and pip may not resolve it without `--pre` depending on user configuration

### Export
- `src/adbc_poolhouse/__init__.py`: import `QuackConfig` from `_quack_config` and add to `__all__`, both alphabetically sorted (between `PostgreSQLConfig` and `RedshiftConfig`)

### Tests
- `tests/test_configs.py`: new `TestQuackConfig` class
  - URI-only construction
  - host-only construction (port defaults to None)
  - host+port construction
  - mutual exclusion: `uri` + `host` raises `ValidationError`
  - mutual exclusion: neither set raises `ValidationError`
  - `to_adbc_kwargs()` URI mode round-trip
  - `to_adbc_kwargs()` decomposed mode rebuilds URI without port when `port is None`
  - `to_adbc_kwargs()` decomposed mode rebuilds URI with port when `port` set
  - `token` passthrough → `adbc.quack.token`
  - `tls=True` → `adbc.quack.tls` = `"true"`
  - `tls=False` → `adbc.quack.tls` is **omitted**
  - env prefix `QUACK_*` loads correctly
- `tests/test_driver_imports.py`: new `TestQuackImports` class
  - Conditional mock: if `_driver_installed("adbc_driver_quack")` → patch `adbc_driver_quack.dbapi.connect`; else → patch `adbc_driver_manager.dbapi.connect` (Snowflake/BigQuery pattern)
  - Assert `mock_connect.assert_called_once()` and that Quack config keys arrive in kwargs (e.g., `"uri"` present)
- `tests/test_drivers.py`: add `test_quack_returns_short_name` (matches `test_clickhouse_returns_short_name` pattern)
- All 241 existing tests must continue to pass

### Documentation
- New file: `docs/src/guides/quack.md`
  - Alpha-status warning admonition at the top
  - External link: `https://github.com/gizmodata/adbc-driver-quack`
  - Install instructions: `pip install --pre adbc-poolhouse[quack]` (note `--pre` due to alpha driver)
  - URI mode example
  - Decomposed mode example (host + optional port)
  - Token + TLS usage example
  - Env var loading section (`QUACK_*` prefix)
  - "See also" links to `configuration.md` and `pool-lifecycle.md`
  - mkdocstrings cross-refs use `[QuackConfig][adbc_poolhouse.QuackConfig]` Markdown syntax (not RST `:class:`)
- `docs/src/guides/configuration.md`: add Quack row to the per-warehouse table
- `docs/src/index.md`: add Quack to the backend listing (listing only, no example — per QUACK deferrals)
- `mkdocs.yml`: add `guides/quack.md` to nav (alphabetical position with other backends)
- `uv run mkdocs build --strict` must pass
- Humanizer pass applied to all new prose (per CLAUDE.md)

### Project skills
- Phase ≥ 7, so `adbc-poolhouse-docs-author` skill MUST be referenced in any PLAN.md `<execution_context>` covering documentation work
- Google-style docstrings (Args/Returns/Raises) on all new public symbols
- Markdown in docstrings, not RST

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Pattern references (existing code to mirror)
- `src/adbc_poolhouse/_databricks_config.py` — URI-first with decomposed fallback pattern (closest analog to Quack)
- `src/adbc_poolhouse/_clickhouse_config.py` — alternate URI-first pattern with mutual exclusion
- `src/adbc_poolhouse/_snowflake_config.py` — PyPI driver `_driver_path` + `_dbapi_module` dual override pattern
- `src/adbc_poolhouse/_base_config.py` — `BaseWarehouseConfig`, `WarehouseConfig` Protocol, `_resolve_driver_path` helper
- `src/adbc_poolhouse/__init__.py` — export ordering convention

### Test patterns
- `tests/test_configs.py::TestClickHouseConfig` (lines 477+) — config unit test layout
- `tests/test_driver_imports.py::TestSnowflakeImports` (lines 68-103) — conditional mock pattern for PyPI alpha drivers
- `tests/test_drivers.py::test_clickhouse_returns_short_name` (line 170) — driver path short-name test

### Docs patterns
- `docs/src/guides/clickhouse.md` — per-warehouse guide layout including alpha admonition and dual-mode examples
- `docs/src/guides/configuration.md` — table format for new row
- `docs/src/index.md` — backend listing format
- `mkdocs.yml` — nav structure

### Project rules
- `CLAUDE.md` — docs quality gate (phases ≥ 7 require docs-author skill, mkdocs strict build, humanizer pass)
- `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — project doc style rules

### Upstream driver
- `https://github.com/gizmodata/adbc-driver-quack` — README confirms URI/token/TLS semantics

### Phase requirements
- `.planning/REQUIREMENTS.md` QUACK-01 through QUACK-18 — every ID must be addressed by at least one plan

</canonical_refs>

<specifics>
## Specific Ideas

- Mirror Databricks' two-mode shape but with simpler validator (only `uri` XOR `host` required; no http_path; token is separate from URI).
- Mirror Snowflake's dual `_driver_path` + `_dbapi_module` pattern because the driver is PyPI-distributed and ships its own `dbapi` submodule.
- Mirror ClickHouse's guide structure (alpha admonition + dual-mode examples + env-var loading).
- Use the same `Self` return type, `model_validator(mode="after")` decorator, and `ConfigurationError` pattern as Databricks/ClickHouse for stylistic consistency.
- Keep `to_adbc_kwargs()` body small: a single branch on `self.uri is not None`, then conditional inserts for `token` and `tls`.

</specifics>

<deferred>
## Deferred Ideas

Per REQUIREMENTS.md "None deferred for this milestone" section, but the following were explicitly excluded from scope:

- Live integration test against a real Quack server (no public test server available)
- Cassette replay for Quack (single-protocol driver — not warranted)
- Decomposed username/password auth (Quack uses single token only)
- Quack-specific pool tuning knobs (standard `QueuePool` params suffice)
- Quickstart example on `index.md` (user confirmed not needed — listing only)

</deferred>

---

*Phase: 21-quack-backend*
*Context gathered: 2026-05-19 via /gsd-list-phase-assumptions exchange + upstream driver README verification*
