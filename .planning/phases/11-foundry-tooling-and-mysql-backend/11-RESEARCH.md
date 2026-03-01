# Phase 11: Foundry Tooling and MySQL Backend - Research

**Researched:** 2026-03-01
**Domain:** `just` recipes for dbc CLI installation + MySQL ADBC Foundry driver config/translator
**Confidence:** MEDIUM (dbc CLI multi-driver install syntax unverified; MySQL Go DSN kwarg names HIGH via official quickstarts)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DBC-01 | `justfile` recipe `install-dbc` — installs `dbc` CLI binary; uses `command -v dbc` guard | `command -v` vs `which` distinction documented; dbc install script URL confirmed |
| DBC-02 | `justfile` recipe `install-foundry-drivers` — runs `dbc install mysql clickhouse` with `--level env` scoping | CRITICAL: `--level env` is NOT a valid flag — see Open Questions; virtualenv scoping works automatically |
| DBC-03 | `DEVELOP.md` Foundry Driver Management section — install dbc, install drivers, verify with `dbc info`, uninstall | All four dbc commands confirmed in CLI reference |
| MYSQL-01 | `MySQLConfig` — Pydantic BaseSettings; URI-first decomposed-field fallback; `ConfigurationError` when neither provided | Pattern established by DatabricksConfig — direct model to follow |
| MYSQL-02 | `translate_mysql()` — Go DSN URI (`user:pass@tcp(host:port)/db`) from decomposed fields when URI absent | CONFIRMED via official adbc-quickstarts main.py: `"root:my-secret-pw@tcp(localhost:3306)/demo"` |
| MYSQL-03 | MySQL registered in `_FOUNDRY_DRIVERS` dict in `_drivers.py` | Pattern established by existing Foundry entries |
| MYSQL-04 | Unit tests for MySQLConfig validation; translator tests; mock-at-`create_adbc_connection` pool-factory wiring | Pattern established by Databricks tests in test_configs.py, test_translators.py, test_pool_factory.py |
| MYSQL-05 | MySQLConfig exported from `__init__.py`; MySQL warehouse guide page; API reference entry; mkdocs build passes | Three doc surfaces: guide page, configuration.md env_prefix table, mkdocs.yml nav entry |
</phase_requirements>

---

## Summary

Phase 11 has two distinct tracks: developer tooling (`just` recipes for the `dbc` CLI) and a new MySQL backend. Both tracks follow patterns already established in the project — the justfile tooling is new but the pattern for new backends is thoroughly established by Databricks, SQLite, and others.

The MySQL ADBC driver is Foundry-distributed (not on PyPI), confirmed at `docs.adbc-drivers.org`. Its connection string uses the Go MySQL Driver DSN format `user:pass@tcp(host:port)/db` — confirmed directly from the official `columnar-tech/adbc-quickstarts` `main.py` source. The `translate_mysql()` function follows the URI-first decomposed-field pattern established by `translate_databricks()`, with the difference that the output URI format is Go DSN rather than the Databricks-specific scheme.

A critical finding: the REQUIREMENTS.md spec says `dbc install mysql clickhouse --level env`, but `--level` only accepts `user` or `system` as values per official dbc CLI documentation. Virtualenv scoping is automatic when `VIRTUAL_ENV` is set — no `--level` flag is needed when inside an active virtualenv. The recipe must be adjusted. See Open Questions for the recommended resolution.

**Primary recommendation:** Follow the DatabricksConfig/translate_databricks pattern exactly for MySQL. For the justfile, use `command -v dbc` guard and run `dbc install mysql clickhouse` without `--level` (virtualenv scoping is automatic). Confirm exact flag syntax before committing DEVELOP.md.

---

## Standard Stack

### Core (No new dependencies required)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-settings | >=2.0.0 | BaseSettings for MySQLConfig | Already in project deps |
| adbc-driver-manager | >=1.8.0 | ADBC driver manager for Foundry resolution | Already bumped in Phase 9 |
| just | any | Task runner for dbc recipes | Already used in project (justfile exists) |
| dbc CLI | latest | Install/manage ADBC Foundry drivers | Official tool at `dbc.columnar.tech` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| urllib.parse.quote | stdlib | URL-encode password in Go DSN | Password may contain `@`, `+`, `=`, `/` etc. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Go DSN format `user:pass@tcp(host:port)/db` | MySQL URI `mysql://user:pass@host:port/db` | Official quickstarts use Go DSN; docs say both are supported but Go DSN appears in the Python example; requirements spec Go DSN |

**Installation:**
```bash
# No new Python packages needed for MySQL (Foundry-distributed, no PyPI extra)
# dbc CLI itself:
curl -LsSf https://dbc.columnar.tech/install.sh | sh

# Install MySQL ADBC driver (once dbc is installed):
dbc install mysql
```

---

## Architecture Patterns

### Pattern 1: justfile `command -v` Guard

**What:** Use `command -v dbc` (POSIX shell builtin) rather than `which dbc` to check if a binary is on PATH. `which` in `just` evaluates eagerly and may behave differently; `command -v` is the POSIX-standard check.

**When to use:** Any justfile recipe that installs a tool only if not already present.

**Example:**
```just
# Guard: only install if dbc is not already on PATH.
# 'command -v' is the POSIX way; 'which' is not portable and evaluates differently in just.
install-dbc:
    command -v dbc || curl -LsSf https://dbc.columnar.tech/install.sh | sh
```

Note: `just` executes each line via `sh -c`, so `command -v` works correctly. The `||` short-circuits — if `dbc` is found, the install script is not fetched.

### Pattern 2: `dbc install` for Foundry Drivers

**What:** Run `dbc install <driver>` inside the active virtualenv. When `VIRTUAL_ENV` is set (active venv), dbc automatically installs to `$VIRTUAL_ENV/etc/adbc/drivers/` — no `--level` flag needed.

**When to use:** `install-foundry-drivers` justfile recipe.

**Example:**
```just
# Install Foundry drivers into the active virtualenv.
# dbc uses VIRTUAL_ENV automatically — no --level flag required.
install-foundry-drivers:
    dbc install mysql
    dbc install clickhouse
```

Or, if `dbc install` accepts multiple names in a single invocation:
```just
install-foundry-drivers:
    dbc install mysql clickhouse
```

**IMPORTANT:** Whether `dbc install` accepts multiple driver names in one command is LOW confidence (not confirmed by official docs). Use two separate `dbc install` calls as the safe fallback.

### Pattern 3: MySQLConfig — URI-First Decomposed-Field Pattern

**What:** Pydantic BaseSettings subclass following DatabricksConfig exactly. Optional `uri` field (SecretStr) + decomposed fields. `model_validator` raises `ConfigurationError` when neither is fully specified.

**When to use:** Any Foundry backend that supports both URI and decomposed connection modes.

**Example:**
```python
# _mysql_config.py — follow _databricks_config.py pattern exactly
from __future__ import annotations

from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class MySQLConfig(BaseWarehouseConfig):
    """MySQL warehouse configuration."""

    model_config = SettingsConfigDict(env_prefix="MYSQL_")

    uri: SecretStr | None = None
    """Full connection URI: mysql://user:pass@host:port/db. Env: MYSQL_URI."""

    host: str | None = None
    """MySQL hostname. Env: MYSQL_HOST."""

    port: int = 3306
    """MySQL port. Default: 3306. Env: MYSQL_PORT."""

    user: str | None = None
    """MySQL username. Env: MYSQL_USER."""

    password: SecretStr | None = None
    """MySQL password. Env: MYSQL_PASSWORD."""

    database: str | None = None
    """MySQL database name. Env: MYSQL_DATABASE."""

    @model_validator(mode="after")
    def check_connection_spec(self) -> Self:
        has_uri = self.uri is not None
        has_decomposed = (
            self.host is not None
            and self.user is not None
            and self.database is not None
        )
        if not has_uri and not has_decomposed:
            raise ConfigurationError(
                "MySQLConfig requires either 'uri' or all of 'host', 'user', "
                "and 'database'. Got none of these."
            )
        return self
```

**Key decision:** Minimum decomposed fields are `host`, `user`, and `database`. `password` is optional (MySQL supports passwordless connections). `port` has a default (3306).

### Pattern 4: `translate_mysql()` — Go DSN Construction

**What:** Pure function following translate_databricks pattern. URI mode passes through URI string. Decomposed mode constructs `user:pass@tcp(host:port)/db`.

**When to use:** `translate_mysql()` — called by `_translators.py`.

**Example:**
```python
# _mysql_translator.py
from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from adbc_poolhouse._mysql_config import MySQLConfig


def translate_mysql(config: MySQLConfig) -> dict[str, str]:
    """Translate MySQLConfig to ADBC driver kwargs."""
    if config.uri is not None:
        return {"uri": config.uri.get_secret_value()}

    # Decomposed mode — model_validator guarantees host, user, database are set
    assert config.host is not None
    assert config.user is not None
    assert config.database is not None

    user = config.user
    port = config.port  # default 3306
    host = config.host
    db = config.database

    if config.password is not None:
        encoded_pass = quote(config.password.get_secret_value(), safe="")
        uri = f"{user}:{encoded_pass}@tcp({host}:{port})/{db}"
    else:
        uri = f"{user}@tcp({host}:{port})/{db}"

    return {"uri": uri}
```

**Source:** Official `columnar-tech/adbc-quickstarts/python/mysql/mysql/main.py` uses `"root:my-secret-pw@tcp(localhost:3306)/demo"` as the `uri` value in `db_kwargs`.

### Pattern 5: Register in `_FOUNDRY_DRIVERS`

**What:** Add `MySQLConfig` to the `_FOUNDRY_DRIVERS` dict in `_drivers.py`. Driver manager name is `"mysql"` (the dbc install name).

**Example:**
```python
# In _drivers.py, add to _FOUNDRY_DRIVERS:
_FOUNDRY_DRIVERS: dict[type, tuple[str, str]] = {
    DatabricksConfig: ("databricks", "databricks"),
    MySQLConfig: ("mysql", "mysql"),           # NEW
    RedshiftConfig: ("redshift", "redshift"),
    TrinoConfig: ("trino", "trino"),
    MSSQLConfig: ("mssql", "mssql"),
}
```

### Pattern 6: Register in `_translators.py`

**What:** Add `isinstance` dispatch branch for `MySQLConfig` in `translate_config()`.

**Example:**
```python
# In _translators.py translate_config():
if isinstance(config, MySQLConfig):
    return translate_mysql(config)
```

Import must be added at module level (not in TYPE_CHECKING — config class is needed at runtime for isinstance).

### Pattern 7: Export from `__init__.py`

**What:** Add `MySQLConfig` import and `__all__` entry following alphabetical order.

**Example:**
```python
# In __init__.py:
from adbc_poolhouse._mysql_config import MySQLConfig

__all__ = [
    ...
    "MySQLConfig",  # insert alphabetically between MSSQLConfig and PostgreSQLConfig
    ...
]
```

### Anti-Patterns to Avoid

- **Using `which` in justfile:** `which` is not a POSIX builtin and evaluates differently in just's shell context. Use `command -v`.
- **`--level env` flag:** This is NOT a valid dbc flag. Valid values are `user` and `system`. Virtualenv scoping is automatic.
- **Multiple driver names in one `dbc install` call:** Unconfirmed — use separate `dbc install mysql` and `dbc install clickhouse` calls as the safe approach.
- **Calling `quote_plus()` for password:** Use `quote(safe="")` not `quote_plus()`. `quote_plus` encodes spaces as `+` which corrupts tokens; `safe=""` ensures `+`, `=`, `/` are all percent-encoded. (See Phase 9 decision in STATE.md.)
- **No `password` guard in Go DSN:** The Go DSN format `user:pass@tcp(...)` only includes `:pass` when a password is present. Emit `user@tcp(...)` when password is None.
- **Missing `_adbc_entrypoint` override for MySQL:** Unlike SQLite/DuckDB, MySQL is a Foundry driver with manifest resolution — `_adbc_entrypoint()` should return `None` (base class default). No override needed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| URL-encoding password | Custom string escaping | `urllib.parse.quote(safe="")` | Handles all edge cases: `@`, `+`, `=`, `/` must all be percent-encoded |
| CLI binary guard | `if which dbc:` | `command -v dbc \|\|` in just recipe | `which` is not POSIX portable; `command -v` is the standard check |
| Driver installation scoping | Custom `ADBC_DRIVER_PATH` manipulation | Rely on dbc's `VIRTUAL_ENV` auto-detection | dbc reads `VIRTUAL_ENV` automatically; no configuration needed |

**Key insight:** The entire Go DSN construction is straightforward string formatting — don't over-engineer it. Follow the Databricks pattern exactly (it already handles URL encoding correctly).

---

## Common Pitfalls

### Pitfall 1: `--level env` Does Not Exist

**What goes wrong:** Recipe runs `dbc install mysql --level env` and fails with "invalid level" error.

**Why it happens:** The REQUIREMENTS.md spec says `--level env` but this flag value does not exist. Valid values are `user` and `system`.

**How to avoid:** Run `dbc install mysql` without `--level` when inside an active virtualenv. `VIRTUAL_ENV` is set automatically by virtualenv activation, and dbc detects it. Drivers land in `$VIRTUAL_ENV/etc/adbc/drivers/`.

**Warning signs:** `dbc install --help` output shows only `user` and `system` as valid level values.

### Pitfall 2: Password Encoding — `quote_plus` vs `quote`

**What goes wrong:** Passwords containing `+` or spaces get double-encoded or silently corrupted.

**Why it happens:** `quote_plus` encodes spaces as `+` (HTTP form encoding), but the `+` in the Go DSN is a literal plus sign in the password.

**How to avoid:** Always use `urllib.parse.quote(value, safe="")`. This is established project convention from Phase 9 (Databricks fix). See STATE.md decision: `[Phase 09-02]: urllib.parse.quote(safe='') for URL-encoding PAT tokens`.

**Warning signs:** Password round-trip test fails when password contains `+`, `=`, `/`, or `@`.

### Pitfall 3: Missing Doc Surfaces (Three Required)

**What goes wrong:** `uv run mkdocs build --strict` fails because MySQL guide is present in `mkdocs.yml` nav but not in `docs/src/guides/`.

**Why it happens:** Three surfaces must be updated simultaneously: (1) new guide page `docs/src/guides/mysql.md`, (2) `guides/configuration.md` env_prefix table row, (3) `mkdocs.yml` nav entry. Missing any one causes a strict-mode build failure.

**How to avoid:** Check the Phase 10 pattern — SQLite required all three. Treat the three-surface update as an atomic task. STATE.md decision: `[Phase 10]: Three doc surfaces must be updated for every new backend`.

**Warning signs:** `uv run mkdocs build --strict` exits with "navigation file not found" or similar error.

### Pitfall 4: `dbc install` Multiple Drivers — Unverified Syntax

**What goes wrong:** `dbc install mysql clickhouse` may work or may only install `mysql` and ignore `clickhouse` (or fail with argument error).

**Why it happens:** The dbc CLI reference shows only single-driver examples. Whether it accepts variadic driver names is not confirmed in official docs.

**How to avoid:** Use two separate `dbc install` calls: `dbc install mysql` and `dbc install clickhouse`. This is safe regardless.

**Warning signs:** Recipe silently installs only the first driver.

### Pitfall 5: MySQLConfig Minimum Decomposed Field Set

**What goes wrong:** Requiring all five fields (`host`, `port`, `user`, `password`, `database`) means passwordless MySQL connections fail construction.

**Why it happens:** MySQL does support connections without a password. `port` has a sensible default (3306).

**How to avoid:** Require only `host`, `user`, and `database` as the minimum set. `password` is optional (SecretStr | None). `port` defaults to 3306.

**Warning signs:** `MySQLConfig(host="h", user="u", database="db")` (no password) raises ConfigurationError unexpectedly.

### Pitfall 6: `__all__` Alphabetical Order

**What goes wrong:** `MySQLConfig` is placed after `MSSQLConfig` in `__init__.py.__all__` but before `PostgreSQLConfig` — this is correct. But inserting it in the wrong position breaks the alphabetical convention.

**How to avoid:** `MySQLConfig` sorts after `MSSQLConfig` (My > MS) and before `PostgreSQLConfig`. The `__all__` list should be: `MSSQLConfig`, `MySQLConfig`, `PostgreSQLConfig`.

---

## Code Examples

Verified patterns from official sources:

### MySQL ADBC Connection (Go DSN format)

```python
# Source: columnar-tech/adbc-quickstarts/python/mysql/mysql/main.py (official)
from adbc_driver_manager import dbapi

with dbapi.connect(
    driver="mysql",
    db_kwargs={"uri": "root:my-secret-pw@tcp(localhost:3306)/demo"}
) as con:
    ...
```

### dbc CLI Installation

```bash
# Source: docs.columnar.tech/dbc/ (official)
curl -LsSf https://dbc.columnar.tech/install.sh | sh
```

### dbc Driver Install

```bash
# Source: docs.columnar.tech/dbc/guides/installing/ (official)
dbc install mysql
dbc install clickhouse
```

### justfile `command -v` Guard Pattern

```just
# 'command -v' is the POSIX way to check if a binary is on PATH.
# The || means: if dbc is found, skip the install.
install-dbc:
    command -v dbc || curl -LsSf https://dbc.columnar.tech/install.sh | sh
```

### Foundry Driver Registration

```python
# Source: existing _drivers.py pattern (project codebase)
_FOUNDRY_DRIVERS: dict[type, tuple[str, str]] = {
    DatabricksConfig: ("databricks", "databricks"),
    MySQLConfig: ("mysql", "mysql"),  # driver_manager_name, dbc_install_name
    RedshiftConfig: ("redshift", "redshift"),
    TrinoConfig: ("trino", "trino"),
    MSSQLConfig: ("mssql", "mssql"),
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| MySQL URI format (`mysql://user:pass@host/db`) | Go DSN format (`user:pass@tcp(host:port)/db`) | dbc MySQL driver always | Both work per docs; official quickstarts use Go DSN; requirements spec Go DSN |
| `which` for binary detection | `command -v` | Standard POSIX practice | `which` is not portable; `command -v` is the POSIX standard |
| Explicit `--level` for virtualenv scoping | Automatic via `VIRTUAL_ENV` env var | dbc always | No flag needed when inside an active virtualenv |

**Deprecated/outdated:**
- `which dbc` in shell guards: replaced by `command -v dbc` per POSIX and the project requirement spec

---

## Open Questions

1. **`dbc install mysql clickhouse` — single command or two separate calls?**
   - What we know: `dbc install <driver>` works for single drivers. Official docs only show single-driver examples.
   - What's unclear: Whether `dbc install mysql clickhouse` (multiple positional args) is supported.
   - Recommendation: Use two separate `dbc install` calls in the justfile recipe. Safe regardless of whether multi-install works.

2. **`--level env` flag in REQUIREMENTS.md (DBC-02)**
   - What we know: `--level` only accepts `user` or `system` per official dbc CLI docs. `--level env` will fail.
   - What's unclear: Whether the requirements author intended `--level user` (user-level install), `--level system`, or simply no `--level` (automatic virtualenv detection).
   - Recommendation: Use `dbc install mysql` and `dbc install clickhouse` without `--level` flag. When inside an active virtualenv (`VIRTUAL_ENV` is set), dbc automatically installs to `$VIRTUAL_ENV/etc/adbc/drivers/`. This is the correct behaviour for local dev. **Flag this discrepancy in the plan as a decision point for the human.**

3. **MySQL minimum decomposed fields — `password` required?**
   - What we know: The official MySQL quickstart uses `root:my-secret-pw@tcp(...)` — password present. MySQL does support passwordless connections.
   - What's unclear: Whether the project convention requires `password` in the minimum set.
   - Recommendation: Make `password` optional (SecretStr | None) in the model validator's minimum check. Include `password` in the Go DSN only when it is not None.

4. **`dbc info` syntax for DEVELOP.md**
   - What we know: `dbc info` is a valid command ("Shows information about the latest version of the driver with the given name").
   - What's unclear: Whether `dbc info mysql` (driver-specific) or plain `dbc info` is the right invocation for "verify installation".
   - Recommendation: Document `dbc info mysql` and `dbc info clickhouse` as the verification commands for each driver. This matches the pattern of `dbc install <name>`.

---

## Validation Architecture

> `workflow.nyquist_validation` is not set in `.planning/config.json` — skipping this section.

---

## Sources

### Primary (HIGH confidence)
- `columnar-tech/adbc-quickstarts/python/mysql/mysql/main.py` (raw GitHub) — Go DSN URI format `user:pass@tcp(host:port)/db` confirmed as the actual connection string used by the MySQL ADBC driver
- `docs.adbc-drivers.org/drivers/mysql/` — MySQL ADBC driver connection parameters; `uri` is the sole kwarg key
- `docs.columnar.tech/dbc/reference/config_level/` — `--level` accepts only `user` and `system`; `VIRTUAL_ENV` is used automatically for virtualenv scoping
- `docs.columnar.tech/dbc/reference/cli/` — full command list: install, uninstall, info, search, sync, etc.
- Project codebase: `_databricks_config.py`, `_databricks_translator.py`, `_drivers.py`, `_translators.py`, `__init__.py` — established patterns for Foundry backend registration and URI-first decomposed-field translation

### Secondary (MEDIUM confidence)
- `docs.columnar.tech/dbc/guides/installing/` — `dbc install <driver>` syntax; `--level user` and `--level system` only; virtualenv auto-detection confirmed
- `docs.adbc-drivers.org/` — MySQL is listed as an available Foundry driver
- STATE.md `[Phase 09-02]` decision — `urllib.parse.quote(safe='')` for URL-encoding; `quote_plus` is wrong for token/password values

### Tertiary (LOW confidence)
- `dbc install mysql clickhouse` (single command, multiple drivers) — not documented; assume two separate calls required
- `dbc info mysql` syntax for per-driver info — command exists but exact invocation for installed-driver verification not confirmed

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all patterns from existing project
- MySQL Go DSN format: HIGH — confirmed from official adbc-quickstarts source
- dbc CLI install URL and basic commands: HIGH — from official docs.columnar.tech
- `--level env` flag: HIGH (confirmed invalid) — only `user`/`system` accepted
- Multiple-driver install syntax: LOW — not confirmed; use separate calls as fallback
- MySQL minimum decomposed field set: MEDIUM — password optionality is design decision

**Research date:** 2026-03-01
**Valid until:** 2026-04-01 (dbc CLI is evolving; re-verify if significant time passes)
