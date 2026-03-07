# Phase 12: ClickHouse Backend - Research

**Researched:** 2026-03-02
**Domain:** Columnar ADBC ClickHouse driver — config, translator, wiring, tests, docs
**Confidence:** MEDIUM (driver kwargs partially confirmed from quickstart source; docs only show `uri`)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Connection mode**
- Support both URI passthrough and individual fields — consistent with MySQL, Redshift, PostgreSQL
- Individual fields (`host`, `port`, `username`, `password`, `database`, and any additional
  driver-supported fields) are translated as **direct driver kwargs** — not assembled into a URI
- This is driven by the phase spec: `translate_clickhouse()` must emit `username` as a kwarg key
  (not `user`, and not wrapped inside a URI)

**Field coverage**
- Expose **all fields the Columnar ClickHouse driver supports as driver kwargs** — nothing more
- Researcher must verify the complete list of supported kwargs from the driver source/docs
  (public docs at docs.adbc-drivers.org only document `uri` for v0.1.0-alpha; check upstream)
- Minimum confirmed fields (from CH-01 + success criteria): `host`, `port`, `username`,
  `password`, `database`
- The `username` field on the config maps to the `username` driver kwarg (not `user`) — this is
  the key naming difference from MySQL and other backends
- If the driver has ClickHouse-specific params (e.g. `secure`, `compress`, protocol variant),
  expose them — researcher to confirm exact kwarg names

**Validation guard**
- Apply a `@model_validator(mode="after")` guard — same pattern as MySQL
- `ConfigurationError` if neither `uri` nor at minimum `host` + `username` is provided
- This matches the fail-fast approach established by MySQL

**Tests**
- Config construction and field validation (including `ConfigurationError` on missing required fields)
- Translator kwargs — assert exact dict output for both URI mode and individual fields mode
- Mock-at-`create_adbc_connection` test for full pool-factory wiring
- Match coverage depth of Redshift and MySQL test files

**Docs**
- Standard warehouse guide page: Foundry installation note, usage examples, field reference,
  env var table (`CLICKHOUSE_*`)
- Equivalent depth to existing guides (mysql.md, redshift.md)
- `uv run mkdocs build --strict` must pass

### Claude's Discretion
- Exact set of ClickHouse-specific kwargs beyond the minimum confirmed fields (researcher verifies)
- Whether `secure` translates to a boolean kwarg or a port convention
- Default port value (ClickHouse native: 9000; HTTPS: 8443; HTTP: 8123 — researcher to confirm
  which port the Foundry driver uses as its default)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CH-01 | `ClickHouseConfig` — Pydantic `BaseSettings`; `env_prefix="CLICKHOUSE_"`; `username` field mapping to `username` driver kwarg (not `user`) | Config pattern confirmed from MySQL/Databricks precedents; `username` kwarg confirmed from columnar-tech/adbc-quickstarts main.py |
| CH-02 | `translate_clickhouse()` — pure function mapping `ClickHouseConfig` fields to adbc_driver_manager kwargs | Translator pattern confirmed from `_mysql_translator.py` and `_redshift_translator.py`; confirmed kwargs: `uri`, `username`, `password`; individual fields mode emits direct kwargs (not a URI) |
| CH-03 | ClickHouse registered in `_FOUNDRY_DRIVERS` dict in `_drivers.py` | Pattern confirmed from existing MySQL/Databricks entries; driver short name is `"clickhouse"` |
| CH-04 | Unit tests for `ClickHouseConfig` validation; unit tests for `translate_clickhouse()` asserting exact kwargs dict; mock-at-`create_adbc_connection` test asserting full pool-factory wiring | Test patterns confirmed from `test_configs.py` (TestMySQLConfig), `test_translators.py` (TestMySQLTranslator, TestTranslateConfig), `test_pool_factory.py` (TestMySQLPoolFactory) |
| CH-05 | `ClickHouseConfig` exported from `__init__.py`; ClickHouse warehouse guide page in docs; API reference entry; `uv run mkdocs build --strict` passes | Guide pattern confirmed from `docs/src/guides/mysql.md`; nav insertion point in `mkdocs.yml` Warehouse Guides section; three doc surfaces: guide page, configuration.md env_prefix table, index.md install table |
</phase_requirements>

---

## Summary

Phase 12 adds ClickHouse as the final Foundry-distributed backend in the v1.1 milestone. The
work follows the exact pattern established by Phase 11 (MySQL) — a `BaseWarehouseConfig` subclass,
a pure translator function, a `_FOUNDRY_DRIVERS` registration, tests at the depth of MySQL/Redshift,
and a warehouse guide page.

The critical distinction for ClickHouse is the kwarg naming: the Columnar driver uses `username`
(not `user`, which MySQL uses). This applies to both the config field name and the translated kwarg
key. Confirmed from the columnar-tech/adbc-quickstarts repository `main.py` for the clickhouse
database example, which explicitly uses `"username": "user"` in `db_kwargs`.

The Columnar ClickHouse driver (v0.1.0-alpha.1) publicly documents only `uri` as a connection
parameter. The quickstart source confirms `username` and `password` are also accepted as individual
kwargs. Individual fields mode should emit these as direct kwargs (not assembled into a URI), which
is consistent with the CONTEXT.md decision and distinguishes ClickHouse from MySQL (which assembles
a Go DSN URI). The default port for the HTTP interface is 8123; HTTPS is 8443.

**Primary recommendation:** Copy the MySQL backend pattern exactly, with three changes: (1) field
`username` instead of `user`; (2) decomposed mode emits direct kwargs dict (`username`, `password`,
`host`, `port`, `database`) rather than a Go DSN URI; (3) driver short name `"clickhouse"`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic-settings` | `>=2.0.0` | `BaseSettings` subclass, env prefix | Already in pyproject.toml; all other backends use it |
| `adbc-driver-manager` | `>=1.8.0` | ADBC DBAPI; Foundry manifest resolution | Floor already bumped in Phase 9; required for `dbc` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dbc` CLI | 0.2.0+ | Install Columnar ClickHouse driver | Local dev and CI setup |

### Installation

```bash
# No new Python dependencies — ClickHouse uses the existing Foundry manifest path
uv sync

# Install the Foundry ClickHouse driver locally (prerelease required)
dbc install --pre clickhouse
```

**Note:** The `--pre` flag is required because only alpha versions are available as of v0.1.0-alpha.1.

---

## Architecture Patterns

### Recommended File Layout

```
src/adbc_poolhouse/
├── _clickhouse_config.py      # NEW — ClickHouseConfig
├── _clickhouse_translator.py  # NEW — translate_clickhouse()
├── _drivers.py                # MODIFY — add ClickHouseConfig to _FOUNDRY_DRIVERS
├── _translators.py            # MODIFY — add ClickHouseConfig dispatch branch
└── __init__.py                # MODIFY — add ClickHouseConfig to imports and __all__

tests/
└── test_clickhouse.py         # NEW — or extend test_configs.py / test_translators.py

docs/src/guides/
└── clickhouse.md              # NEW — warehouse guide page

mkdocs.yml                     # MODIFY — add ClickHouse to Warehouse Guides nav
docs/src/guides/configuration.md  # MODIFY — add CLICKHOUSE_ row to env_prefix table
docs/src/index.md              # MODIFY — add ClickHouseConfig to install table if present
```

**File naming:** `_clickhouse_config.py` and `_clickhouse_translator.py` — follows all existing
backend naming conventions exactly.

**Test file naming:** Prior phases for Foundry backends (MySQL, Redshift) do not have dedicated
test files — all tests live in `test_configs.py`, `test_translators.py`, and `test_pool_factory.py`.
Follow the same pattern: add `TestClickHouseConfig`, `TestClickHouseTranslator`, and
`TestClickHousePoolFactory` classes in their respective existing test files.

### Pattern 1: Config Class (copy from MySQL with username substitution)

```python
# Source: src/adbc_poolhouse/_mysql_config.py (verified in codebase)
from __future__ import annotations

from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class ClickHouseConfig(BaseWarehouseConfig):
    """ClickHouse warehouse configuration. ..."""

    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_")

    uri: SecretStr | None = None
    host: str | None = None
    port: int = 8123          # HTTP interface default — see note on port below
    username: str | None = None   # 'username' NOT 'user'
    password: SecretStr | None = None
    database: str | None = None

    @model_validator(mode="after")
    def check_connection_spec(self) -> Self:
        has_uri = self.uri is not None
        has_decomposed = self.host is not None and self.username is not None
        if not has_uri and not has_decomposed:
            raise ConfigurationError(
                "ClickHouseConfig requires either 'uri' or at minimum "
                "'host' and 'username'. Got none of these."
            )
        return self
```

### Pattern 2: Translator — Individual Fields as Direct Kwargs (not URI assembly)

**KEY DIFFERENCE FROM MYSQL:** MySQL assembles a Go DSN URI string and returns `{"uri": "..."}`.
ClickHouse's Columnar driver accepts individual kwargs directly. The decomposed mode returns a
dict with keys `username`, `password`, `host`, `port`, `database` as separate entries.

```python
# Source: confirmed from columnar-tech/adbc-quickstarts main.py (by-database/clickhouse/python)
def translate_clickhouse(config: ClickHouseConfig) -> dict[str, str]:
    if config.uri is not None:
        return {"uri": config.uri.get_secret_value()}

    # Decomposed mode — direct kwargs (NOT assembled into URI)
    assert config.host is not None
    assert config.username is not None

    kwargs: dict[str, str] = {
        "username": config.username,
        "host": config.host,
        "port": str(config.port),
    }
    if config.password is not None:
        kwargs["password"] = config.password.get_secret_value()
    if config.database is not None:
        kwargs["database"] = config.database
    return kwargs
```

**Important:** The `port` field is an `int` on the config but ADBC kwargs must be `dict[str, str]`
— convert with `str(config.port)` in the translator.

### Pattern 3: _FOUNDRY_DRIVERS Registration

```python
# Source: src/adbc_poolhouse/_drivers.py (verified in codebase)
# Add at module level import:
from adbc_poolhouse._clickhouse_config import ClickHouseConfig

# Add to dict:
_FOUNDRY_DRIVERS: dict[type, tuple[str, str]] = {
    ...
    ClickHouseConfig: ("clickhouse", "clickhouse"),
    ...
}
```

The tuple is `(driver_manager_name, dbc_install_name)`. Both are `"clickhouse"`.

### Pattern 4: _translators.py Dispatch

```python
# Source: src/adbc_poolhouse/_translators.py (verified in codebase)
# Add import:
from adbc_poolhouse._clickhouse_config import ClickHouseConfig
from adbc_poolhouse._clickhouse_translator import translate_clickhouse

# Add dispatch branch (alphabetical within Foundry group):
def translate_config(config: WarehouseConfig) -> dict[str, str]:
    if isinstance(config, BigQueryConfig):
        return translate_bigquery(config)
    if isinstance(config, ClickHouseConfig):        # NEW
        return translate_clickhouse(config)         # NEW
    if isinstance(config, DatabricksConfig):
        ...
```

### Anti-Patterns to Avoid

- **Using `user` instead of `username`:** ClickHouse driver kwarg is `username`. Using `user`
  causes a silent auth failure — the driver ignores unknown kwargs.
- **Assembling a URI in decomposed mode:** MySQL does this (Go DSN). ClickHouse does not — the
  driver accepts individual kwargs directly.
- **Importing ClickHouseConfig inside a function body in `_drivers.py`:** All config imports in
  `_drivers.py` are at module level (not inside functions). See existing pattern.
- **Omitting `str()` conversion on port:** `dict[str, str]` requires all values as strings.
  `port` is `int` on the config — translate with `str(config.port)`.
- **Missing `__all__` entry in `__init__.py`:** Three surfaces must be updated: `__init__.py`
  import + `__all__`, `_drivers.py` import + `_FOUNDRY_DRIVERS`, `_translators.py` import +
  dispatch branch. STATE.md note (Phase 10): "Three doc surfaces must be updated for every new
  backend" — guide page, configuration.md, index.md.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Env var loading | Custom os.getenv logic | `pydantic-settings` with `env_prefix` | Already used by all 11 other backends |
| Secret masking | Custom `__repr__` | `SecretStr` from pydantic | Used by `password`, `uri` fields |
| Validation guard | Manual if/raise | `@model_validator(mode="after")` | Used by MySQL and Databricks; integrates with Pydantic ValidationError |

**Key insight:** ClickHouse is the 12th backend. Every infrastructure decision has precedent. Copy
MySQL with the `username`/direct-kwargs differences; do not invent new patterns.

---

## Common Pitfalls

### Pitfall 1: Wrong Username Kwarg Name

**What goes wrong:** Using `user` instead of `username` in the translated dict causes silent auth
failure. The Columnar ClickHouse driver silently ignores unrecognised kwargs.
**Why it happens:** MySQL uses `user`; all other backends use `user`; ClickHouse is the exception.
**How to avoid:** The config field is `username`, and the translator emits `"username"` as the key.
**Warning signs:** Tests pass but connection to real server returns auth error.

### Pitfall 2: Assembling a URI for Decomposed Mode

**What goes wrong:** Implementing decomposed mode by building `http://username:password@host:port/db`
and returning `{"uri": ...}` — this is the MySQL pattern (Go DSN). ClickHouse's driver accepts
individual kwargs directly, so URI assembly is unnecessary and may cause parsing issues.
**Why it happens:** MySQL translator is the reference for Foundry backends but has a different
decomposed-mode strategy.
**How to avoid:** Decomposed mode returns individual keys: `username`, `host`, `port`, `database`,
`password` (when set).

### Pitfall 3: Port Default Mismatch

**What goes wrong:** Using port 9000 (ClickHouse native protocol) when the Columnar driver uses the
HTTP interface (port 8123).
**Why it happens:** ClickHouse has multiple ports for different protocols; 9000 is well-known.
**How to avoid:** The Columnar driver is HTTP-based (quickstart uses `http://localhost:8123/`).
Default port should be 8123 for the HTTP interface.
**Warning signs:** Connection fails with "Connection refused" on port 9000.

### Pitfall 4: Missing `str()` on Port in Translator

**What goes wrong:** `dict[str, str]` but `config.port` is `int`. Returning `{"port": 8123}` fails
the return type annotation and mypy/basedpyright checks.
**Why it happens:** `port` field is typed as `int` for validation; translator output must be
`dict[str, str]`.
**How to avoid:** Always wrap int fields with `str()` in the translator.

### Pitfall 5: Three Doc Surfaces Not Updated

**What goes wrong:** Adding `clickhouse.md` guide but forgetting `configuration.md` (env_prefix
table) and the index.md install table.
**Why it happens:** mkdocs build only validates nav links and strict warnings, not content
completeness.
**How to avoid:** Explicitly update all three: guide page, configuration.md row, index.md row.
Lesson from Phase 10 (STATE.md): "human checkpoint caught two missing entries post-guide-creation".

### Pitfall 6: `dbc install --pre clickhouse` Required

**What goes wrong:** `dbc install clickhouse` (without `--pre`) fails because only alpha releases
are available.
**Why it happens:** ClickHouse driver is v0.1.0-alpha.1 — only prerelease versions available.
**How to avoid:** Document `--pre` flag in the warehouse guide and any setup instructions.

---

## Code Examples

Verified patterns from codebase and official sources:

### ClickHouseConfig construction (expected behavior)

```python
# Pattern: follows MySQL model_validator — from src/adbc_poolhouse/_mysql_config.py
from adbc_poolhouse import ClickHouseConfig

# URI mode
config = ClickHouseConfig(uri="http://user:pass@localhost:8123/mydb")

# Individual fields mode
config = ClickHouseConfig(
    host="localhost",
    port=8123,
    username="default",
    password="secret",  # pragma: allowlist secret
    database="mydb",
)

# No args raises ConfigurationError (wrapped in ValidationError)
# ClickHouseConfig()  # raises
```

### translate_clickhouse() expected output

```python
# Individual fields — direct kwargs (NOT a URI string)
# Source: columnar-tech/adbc-quickstarts by-database/clickhouse/python/main.py
config = ClickHouseConfig(
    host="localhost",
    username="default",
    password="secret",  # pragma: allowlist secret
    database="mydb",
)
result = translate_clickhouse(config)
# Expected:
# {
#     "username": "default",
#     "host": "localhost",
#     "port": "8123",
#     "password": "secret",
#     "database": "mydb",
# }
```

### _FOUNDRY_DRIVERS entry

```python
# Source: src/adbc_poolhouse/_drivers.py (verified pattern)
_FOUNDRY_DRIVERS: dict[type, tuple[str, str]] = {
    ...
    ClickHouseConfig: ("clickhouse", "clickhouse"),
    ...
}
```

### Mock pool-factory test pattern

```python
# Source: tests/test_pool_factory.py TestMySQLPoolFactory.test_decomposed_fields_wiring
from unittest.mock import MagicMock, patch
from adbc_poolhouse import ClickHouseConfig, create_pool

config = ClickHouseConfig(
    host="localhost",
    username="default",
    database="mydb",
)
mock_conn = MagicMock()
mock_conn.adbc_clone = MagicMock(return_value=MagicMock())

with patch(
    "adbc_poolhouse._pool_factory.create_adbc_connection",
    return_value=mock_conn,
) as mock_factory:
    pool = create_pool(config)
    pool.dispose()

mock_factory.assert_called_once()
call_args = mock_factory.call_args
actual_kwargs = call_args.args[1]
assert actual_kwargs.get("username") == "default"
assert actual_kwargs.get("host") == "localhost"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `adbc_driver_manager >= 1.0.0` | `>= 1.8.0` | Phase 9 | Required for dbc CLI 0.2.0 Foundry manifest |
| Manual driver detection | `_FOUNDRY_DRIVERS` manifest path | Phase 9+ | Foundry drivers skip find_spec entirely |

**Deprecated/outdated:**
- ClickHouse via Apache ADBC (`github.com/ClickHouse/adbc_clickhouse`): WIP, many NotImplemented
  stubs, explicitly marked out of scope in REQUIREMENTS.md. Use Columnar Foundry driver only.

---

## Open Questions

1. **Are there ClickHouse-specific kwargs beyond uri/username/password/host/port/database?**
   - What we know: The quickstart only shows `uri`, `username`, `password`. Public docs only show
     `uri`. No documentation of `secure`, `compress`, or protocol flags for the Columnar driver.
   - What's unclear: Whether the driver accepts `secure` (boolean), `compress`, or other kwargs.
   - Recommendation: Implement only the confirmed fields (uri, host, port, username, password,
     database). Do not speculate on additional kwargs — the CONTEXT.md decision says "expose all
     fields the driver supports, but nothing else." Mark as LOW confidence and note for Phase
     implementation to verify against `dbc install --pre clickhouse` + driver introspection.

2. **Does the `database` field appear in the individual kwargs dict?**
   - What we know: The quickstart `main.py` shows only `uri`, `username`, `password` — no `database`
     kwarg shown separately. The URI example is `http://localhost:8123/` (no database path).
   - What's unclear: Whether `database` is a standalone kwarg or must be embedded in the URI.
   - Recommendation: Include `database` as an optional kwarg in decomposed mode. If the driver
     silently ignores it, the plan executor can adjust. This is the safe default — omitting it
     would require URI assembly to specify a database.

3. **Should `host` and `port` be separate kwargs or only available via URI?**
   - What we know: The quickstart uses `uri` for host/port (`http://localhost:8123/`). No quickstart
     example shows `host` as a standalone kwarg.
   - What's unclear: Whether the driver accepts `host` and `port` as individual connection kwargs.
   - Recommendation: Include them in decomposed mode. If the driver requires a URI even in
     decomposed mode, the plan executor can switch to URI assembly. The CONTEXT.md locks
     "individual fields are translated as direct driver kwargs."

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (confirmed from pyproject.toml and existing tests) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_configs.py tests/test_translators.py tests/test_drivers.py tests/test_pool_factory.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CH-01 | `ClickHouseConfig` constructs; `username` field present; `ConfigurationError` on empty | unit | `uv run pytest tests/test_configs.py -k "ClickHouse" -x` | ❌ Wave 0 — add `TestClickHouseConfig` class |
| CH-02 | `translate_clickhouse()` emits correct kwargs dict for URI + decomposed modes | unit | `uv run pytest tests/test_translators.py -k "ClickHouse" -x` | ❌ Wave 0 — add `TestClickHouseTranslator` + dispatch test |
| CH-03 | `resolve_driver(ClickHouseConfig(...))` returns `"clickhouse"` | unit | `uv run pytest tests/test_drivers.py -k "clickhouse" -x` | ❌ Wave 0 — add test to existing `TestFoundryDrivers` class |
| CH-04 | Mock pool-factory wiring: correct kwargs reach `create_adbc_connection` | unit | `uv run pytest tests/test_pool_factory.py -k "ClickHouse" -x` | ❌ Wave 0 — add `TestClickHousePoolFactory` class |
| CH-05 | `from adbc_poolhouse import ClickHouseConfig` succeeds; mkdocs builds | smoke + build | `python -c "from adbc_poolhouse import ClickHouseConfig"` + `uv run mkdocs build --strict` | ❌ Wave 0 — created by implementation |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_configs.py tests/test_translators.py tests/test_drivers.py tests/test_pool_factory.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green + `uv run mkdocs build --strict` passes before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `TestClickHouseConfig` class in `tests/test_configs.py` — covers CH-01
- [ ] `TestClickHouseTranslator` class + `test_clickhouse_dispatch` in `tests/test_translators.py` — covers CH-02
- [ ] `test_clickhouse_returns_short_name` in `tests/test_drivers.py::TestFoundryDrivers` — covers CH-03
- [ ] `TestClickHousePoolFactory` class in `tests/test_pool_factory.py` — covers CH-04

---

## Sources

### Primary (HIGH confidence)
- `src/adbc_poolhouse/_mysql_config.py` — established config pattern with `model_validator`
- `src/adbc_poolhouse/_mysql_translator.py` — translator structure and docstring pattern
- `src/adbc_poolhouse/_drivers.py` — `_FOUNDRY_DRIVERS` dict and import pattern
- `src/adbc_poolhouse/_translators.py` — dispatch coordinator pattern
- `src/adbc_poolhouse/__init__.py` — `__all__` and import pattern
- `tests/test_configs.py` — TestMySQLConfig test class pattern
- `tests/test_translators.py` — TestMySQLTranslator + TestTranslateConfig dispatch pattern
- `tests/test_pool_factory.py` — TestMySQLPoolFactory mock-at-create_adbc_connection pattern
- `docs/src/guides/mysql.md` — warehouse guide page structure
- `mkdocs.yml` — Warehouse Guides nav section location

### Secondary (MEDIUM confidence)
- `https://raw.githubusercontent.com/columnar-tech/adbc-quickstarts/by-database/clickhouse/python/main.py`
  — confirmed `"username"` kwarg name (not `"user"`); confirmed `"password"` kwarg; confirmed HTTP
  port 8123 as the connection default
- `https://docs.adbc-drivers.org/drivers/clickhouse/index.html` — driver version v0.1.0-alpha.1;
  confirmed driver short name `"clickhouse"`; confirmed `--pre` flag required for installation

### Tertiary (LOW confidence)
- WebSearch inference: `database`, `host`, `port` as individual kwargs in decomposed mode — not
  confirmed from official source, inferred from ADBC driver patterns and CONTEXT.md decisions

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — identical to 11 existing backends; no new dependencies
- Architecture patterns: HIGH — directly copied from MySQL with documented differences
- Driver kwargs: MEDIUM — `uri`, `username`, `password` confirmed from quickstart source; `host`,
  `port`, `database` as individual kwargs are inferred (not confirmed from official docs)
- Pitfalls: HIGH — `username` vs `user` confirmed; URI vs direct-kwargs difference is architectural
- Docs pattern: HIGH — confirmed from mysql.md, configuration.md, STATE.md Phase 10 lesson

**Research date:** 2026-03-02
**Valid until:** 2026-04-01 (driver is alpha; kwargs could change but core pattern is stable)
