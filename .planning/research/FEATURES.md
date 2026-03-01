# Feature Landscape: New ADBC Backends and Foundry Driver Tooling

**Domain:** Python ADBC connection-pool library — backend expansion and developer tooling
**Researched:** 2026-03-01
**Scope:** New backends not yet in adbc-poolhouse (SQLite, MySQL, ClickHouse, Oracle, Teradata); dbc CLI workflow for Foundry driver management

---

## Context: What Already Exists

The following backends are already implemented (v1.0) and are **out of scope** for this research:

| Backend | Distribution | Pattern |
|---------|-------------|---------|
| DuckDB | PyPI (`duckdb` bundled) | Decomposed fields, `_adbc_entrypoint()` override |
| Snowflake | PyPI (`adbc-driver-snowflake`) | Decomposed fields, full auth matrix |
| BigQuery | PyPI (`adbc-driver-bigquery`) | Decomposed fields |
| PostgreSQL | PyPI (`adbc-driver-postgresql`) | `uri`-only config |
| FlightSQL | PyPI (`adbc-driver-flightsql`) | Decomposed fields |
| Databricks | Foundry (`databricks`) | `uri`-based, decomposed as supplemental |
| Redshift | Foundry (`redshift`) | `uri`-based, cluster-type fields |
| Trino | Foundry (`trino`) | `uri`-based, decomposed fields |
| MSSQL | Foundry (`mssql`) | `uri`-based, fedauth fields for Azure |

Teradata `.pyc` files exist in `__pycache__` but the source module is absent from `__init__.py` and the src tree. Teradata is in-progress or previously removed. See note in New Backends section.

---

## New Backends

### Decision Framework

Each candidate backend must meet the bar:
1. A working Foundry or PyPI ADBC driver exists (not just planned)
2. The driver is installable by consumers without building from source
3. The driver has confirmed Python support via `adbc_driver_manager`

Sources: `docs.adbc-drivers.org` (confirmed 2026-03-01), `adbc-quickstarts` by-database branch (confirmed 2026-03-01).

---

### SQLite — INCLUDE

**Distribution:** PyPI (`adbc-driver-sqlite`, Apache ADBC project)
**Install:** `pip install adbc-driver-sqlite` or `dbc install sqlite`
**Status:** Stable (Apache ADBC official driver; described as the reference implementation)
**Confidence:** HIGH — official Apache ADBC docs, PyPI package confirmed

**Why include:** The only local-file-backed database with a stable PyPI ADBC driver. Useful for testing, embedded data pipelines, and offline development. Complements DuckDB for local-first use cases.

**Connection parameters:**

| Pydantic field | Type | Driver kwarg key | Notes |
|---------------|------|-----------------|-------|
| `uri` | `str = ":memory:"` | `"uri"` | Filename path, SQLite URI (e.g. `file:data.db?mode=ro`), or `:memory:`. Defaults to an in-memory database shared across connections when omitted. |

**Additional driver options (set at connection level, not database level):**

| Option key | Type | Notes |
|-----------|------|-------|
| `adbc.sqlite.load_extension.enabled` | `"true"/"false"` | Enable extension loading; off by default |
| `adbc.sqlite.load_extension.path` | string | Path to `.so`/`.dll` to load |
| `adbc.sqlite.load_extension.entrypoint` | string | Entrypoint symbol in extension |
| `adbc.sqlite.query.batch_rows` | int string | Result batch size |

The connection-level options are not first-class config fields (they are set after `AdbcConnectionInit`), so they do not belong in `SQLiteConfig`. The `uri` field is the only database-level parameter.

**Pydantic field map:**
```python
class SQLiteConfig(BaseWarehouseConfig):
    model_config = SettingsConfigDict(env_prefix="SQLITE_")

    uri: str = ":memory:"
    """File path, SQLite URI string, or ':memory:'. Env: SQLITE_URI."""
```

**Special behaviour:** Like DuckDB `:memory:`, an in-memory SQLite database shared across connections (SQLite's shared-cache mode) is the default when no file is specified. Unlike DuckDB, multiple connections to the same in-memory SQLite DB share state (not isolated). `pool_size=1` is still the safer default for `:memory:` to avoid unexpected concurrent-write errors from SQLite's per-file lock.

**Complexity:** Low. Follows the DuckDB pattern exactly. The `_adbc_entrypoint()` override is needed: the SQLite Apache driver uses the entrypoint `adbc_driver_sqlite_init`.

**Dependency on existing patterns:** Identical to DuckDBConfig. PyPI resolution path in `_drivers.py` via `find_spec("adbc_driver_sqlite")`, then `pkg._driver_path()`.

---

### MySQL — INCLUDE

**Distribution:** Foundry (Columnar `adbc-drivers/mysql` repo)
**Install:** `dbc install mysql`
**Status:** Stable on Foundry (pre-built binaries on Columnar CDN); not on PyPI
**Confidence:** HIGH — README confirmed from `adbc-drivers/mysql`, quickstart confirmed from `adbc-quickstarts`

**Why include:** MySQL is the most-deployed open-source RDBMS. MariaDB, TiDB, and Vitess use the same driver (MySQL wire protocol). A single `MySQLConfig` covers all four.

**URI format:** `user:password@tcp(host:port)/dbname`

Note the format is **not** `mysql://` — it follows Go's `database/sql` DSN convention (this driver is written in Go). The Columnar quickstart confirms this format:
```
"uri": "root:my-secret-pw@tcp(localhost:3306)/demo"
```

**Pydantic field map:**

| Pydantic field | Type | Driver kwarg key | Notes |
|---------------|------|-----------------|-------|
| `uri` | `SecretStr \| None` | `"uri"` | Full DSN: `user:pass@tcp(host:port)/dbname`. May contain credentials. |
| `host` | `str \| None` | — | Supplemental; compose into URI at translation time |
| `port` | `int \| None` | — | Supplemental; default 3306 |
| `user` | `str \| None` | — | Supplemental |
| `password` | `SecretStr \| None` | — | Supplemental |
| `database` | `str \| None` | — | Default database name |

**Translation strategy:** URI wins if provided. If absent, translate decomposed fields into the `user:pass@tcp(host:port)/db` DSN format at translation time. This matches the DatabricksConfig pattern.

**Complexity:** Medium. URI format is unconventional (Go DSN, not `mysql://`). Decomposed-to-URI translation is straightforward but needs a unit test that explicitly covers the non-standard DSN format.

**Dependency on existing patterns:** Foundry driver path in `_drivers.py`. Add to `_FOUNDRY_DRIVERS` dict with key `"mysql"`.

**MariaDB/TiDB/Vitess:** These use the MySQL wire protocol and can share `MySQLConfig` with the same `mysql` Foundry driver. No separate config class is needed.

---

### ClickHouse — INCLUDE (with caution)

**Distribution:** Foundry (Columnar, `clickhouse` driver name); official ClickHouse ADBC driver from `ClickHouse/adbc_clickhouse` is separate but **work-in-progress and not production-ready**
**Install:** `dbc install clickhouse` (Columnar Foundry driver)
**Status:** Columnar Foundry driver is stable for basic query flow; official ClickHouse ADBC driver is alpha-stage
**Confidence:** MEDIUM — quickstart confirmed for Columnar driver; ClickHouse's own driver README explicitly says "not ready for production"

**Why include:** ClickHouse is a major OLAP/analytics database increasingly used alongside data warehouses. The Foundry driver supports the HTTP interface which is ClickHouse's most stable API surface.

**Connection parameters:** HTTP-interface based. URI is `http://host:port` or `https://host:port`.

| Pydantic field | Type | Driver kwarg key | Notes |
|---------------|------|-----------------|-------|
| `uri` | `str \| None` | `"uri"` | `http://host:port` or `https://host:port`. Required. |
| `username` | `str \| None` | `"username"` | Note: key is `username`, not `user` — ClickHouse-specific |
| `password` | `SecretStr \| None` | `"password"` | HTTP basic auth password |
| `database` | `str \| None` | `"database"` | Default database (ClickHouse schema) |

**Important field naming difference:** ClickHouse uses `username` not `user` as the driver kwarg key. The Pydantic field should be named `username` to match directly and avoid a confusing field-to-kwarg rename.

**Complexity:** Low. URI-only connection with simple additional fields. Translation is trivial — no DSN assembly needed.

**Dependency on existing patterns:** Foundry driver path. Add to `_FOUNDRY_DRIVERS` with key `"clickhouse"`.

**Flag:** The official ClickHouse ADBC driver (`ClickHouse/adbc_clickhouse`) is alpha/WIP and explicitly not production-ready. Do not use it. Only the Columnar Foundry `clickhouse` driver is viable.

---

### Teradata — COMPLETE (missing source, not new)

**Distribution:** Foundry private registry (Columnar, `teradata` driver name; requires `dbc auth login`)
**Install:** `dbc auth login` then `dbc install teradata`
**Status:** `.pyc` files present in `__pycache__` indicate this was implemented but the source `.py` file is absent from the tree. Not in `__init__.py`.
**Confidence:** HIGH for connection parameters (quickstart confirmed)

**Why include:** The source module exists as compiled bytecode — it was written but not committed or was deleted. This is not a new backend; it needs to be recovered/rewritten, not researched from scratch.

**Connection parameters:**

| Pydantic field | Type | Driver kwarg key | Notes |
|---------------|------|-----------------|-------|
| `uri` | `SecretStr \| None` | `"uri"` | `teradata://user:pass@host:1025` — standard scheme, port 1025 |
| `host` | `str \| None` | — | Decomposed alternative |
| `user` | `str \| None` | — | Decomposed alternative |
| `password` | `SecretStr \| None` | — | Decomposed alternative |
| `port` | `int \| None` | — | Default 1025 |

**Quickstart reference:**
```python
dbapi.connect(
    driver="teradata",
    db_kwargs={"uri": "teradata://YOUR_USERNAME:YOUR_PASSWORD@YOUR_HOST:1025"},
)
```

**Private registry note:** Teradata requires `dbc auth login` before `dbc install teradata`. This is different from public Foundry drivers (MySQL, ClickHouse, MSSQL etc.) which do not require auth. The justfile recipes must document this distinction.

**Complexity:** Low (standard URI pattern). Medium if the `_teradata_config.py` source needs to be reconstructed from the compiled `.pyc`.

---

### Oracle — EXCLUDE (for this milestone)

**Distribution:** Foundry private registry (requires `dbc auth login` then `dbc install oracle`)
**Status:** Available in dbc 0.2.0+ (launched February 2026) via private registry
**Confidence:** MEDIUM — dbc 0.2.0 announcement confirmed

**Why exclude:** Requires private registry authentication (`dbc auth login`). Oracle has a more complex licensing environment. Adding a private-registry-only backend adds friction to the developer workflow without a concrete consumer requesting it. Defer to a future milestone when there is a specific consumer asking for Oracle.

**Connection parameters when added:**
```python
# quickstart shows: "uri": "oracle://system:password@localhost:1521/FREEPDB1"
```

Standard URI pattern (`oracle://user:pass@host:port/service_name`). Low complexity when needed.

---

## New Backend Summary Table

| Backend | Include? | Distribution | Driver name | URI format | Complexity |
|---------|----------|-------------|------------|-----------|-----------|
| SQLite | Yes | PyPI | `adbc_driver_sqlite` | filename or `file:` URI or `:memory:` | Low |
| MySQL | Yes | Foundry (public) | `mysql` | `user:pass@tcp(host:port)/db` | Medium |
| ClickHouse | Yes | Foundry (public) | `clickhouse` | `http://host:port` | Low |
| Teradata | Recover (not new) | Foundry (private) | `teradata` | `teradata://user:pass@host:port` | Low |
| Oracle | No (future) | Foundry (private) | `oracle` | `oracle://user:pass@host:port/svc` | Low |

---

## dbc CLI Developer Workflow

### What dbc Is

`dbc` is the Columnar Technologies CLI for installing and managing ADBC drivers. It downloads pre-built driver binaries from the Columnar CDN (public) or a private registry (Oracle, Teradata), installs them to a user-level or system-level location, and registers them as ADBC driver manifests so that `adbc_driver_manager` can resolve them by name (e.g. `driver="mysql"`).

**Current version:** 0.2.0 (released February 10, 2026)
**Requires:** `adbc-driver-manager>=1.8.0` for manifest support

### Installation

```bash
# Recommended: standalone installer (no Python env needed)
curl -LsSf https://dbc.columnar.tech/install.sh | sh

# Alternative: pipx (puts dbc on PATH without a venv)
pipx install dbc

# Alternative: uv tool install (similar to pipx)
uv tool install dbc

# Alternative: Homebrew (macOS)
brew install columnar-tech/tap/dbc

# Verify install
dbc --version
```

### Complete Developer Workflow: Public Foundry Drivers

Public drivers (Databricks, Redshift, Trino, MSSQL, MySQL, ClickHouse) require no authentication:

```bash
# 1. Install a driver
dbc install mysql

# 2. Verify the driver is installed and discoverable
dbc info mysql

# 3. Verify the driver can be loaded by adbc_driver_manager
#    (the canonical smoke test — same check adbc-poolhouse performs)
python -c "
from adbc_driver_manager import dbapi
import adbc_driver_manager._lib as _lib
db = _lib.AdbcDatabase(driver='mysql')
print('mysql driver loaded OK')
"

# 4. Search for available drivers (read-only, no install)
dbc search

# 5. List what is installed at the current level
dbc info mysql  # info for one driver
# (no bare "dbc list" command; use "dbc search" to see all registry drivers)

# 6. Uninstall / remove a driver
dbc remove mysql
```

### Complete Developer Workflow: Private Registry Drivers (Teradata, Oracle)

```bash
# 1. Authenticate with the private registry (browser OAuth flow)
dbc auth login

# 2. Install private driver (now authenticated)
dbc install teradata

# 3. Verify (same as public)
dbc info teradata

# 4. Smoke test
python -c "
from adbc_driver_manager import dbapi
import adbc_driver_manager._lib as _lib
db = _lib.AdbcDatabase(driver='teradata')
print('teradata driver loaded OK')
"
```

### Declarative Project Workflow (dbc.toml)

For reproducible dev environments, `dbc` supports a lockfile-based declarative mode:

```bash
# Initialize a dbc.toml in the project root
dbc init

# Add drivers to dbc.toml (equivalent to editing the file)
dbc add mysql
dbc add clickhouse
dbc add "databricks>=1.0.0"  # version constraint supported

# Install all listed drivers and write dbc.lock
dbc sync

# On another machine or CI: reproduce exact installed set
dbc sync
```

### dbc CLI Reference (Commands Used in Recipes)

| Command | Purpose | Notes |
|---------|---------|-------|
| `dbc install <driver>` | Download and install driver | User level by default; `--level system` for system-wide |
| `dbc install --pre <driver>` | Install pre-release build | For testing fixes before stable release |
| `dbc info <driver>` | Show driver metadata, version, path | Read-only; fetches from registry CDN |
| `dbc search` | List all available drivers in registry | Read-only; `--pre` to include pre-releases |
| `dbc remove <driver>` | Uninstall a driver | Removes from the installed level |
| `dbc add <driver>` | Add driver to `dbc.toml` driver list | Declarative; does not install immediately |
| `dbc sync` | Install all drivers in `dbc.toml` | Creates/updates `dbc.lock` |
| `dbc init` | Create a `dbc.toml` in current directory | Declarative workflow entry point |
| `dbc auth login` | Authenticate with private registry | Required for Teradata, Oracle |
| `dbc docs <driver>` | Open driver documentation (dbc 0.2.0+) | `--no-open` to print URL only |

**Flags available on most subcommands:**
- `--level user` / `--level system` / `--level env` — installation scope
- `--quiet` — suppress output (for embedding in scripts)
- `--json` — structured JSON output (for programmatic consumption)
- `--pre` — include pre-release builds

### Verifying a Foundry Driver From the Command Line

The canonical verification sequence for a Foundry driver is:

```bash
# Step 1: confirm dbc sees the driver installed
dbc info mysql

# Step 2: confirm the ADBC driver manager can resolve and load it
python -c "
from adbc_driver_manager import _lib
try:
    db = _lib.AdbcDatabase(driver='mysql')
    print('OK: driver=mysql resolved and loaded')
except Exception as e:
    print(f'FAIL: {e}')
"

# Step 3: confirm a real connection (requires live database)
#   - not suitable for justfile recipes (no creds in repo)
#   - leave this as a manual step in docs
```

The `_lib.AdbcDatabase(driver='<name>')` call is the correct smoke test: it exercises the manifest lookup and shared-library load without requiring a network-reachable database. This is the same internal path that `adbc-poolhouse`'s `create_pool()` takes before attempting a real connection.

---

## Justfile Recipes for Foundry Driver Tooling

### Proposed Recipes

```just
# Install the dbc CLI (standalone installer; no Python env required)
install-dbc:
    curl -LsSf https://dbc.columnar.tech/install.sh | sh

# Install all public Foundry drivers supported by adbc-poolhouse
install-foundry-drivers:
    dbc install databricks
    dbc install redshift
    dbc install trino
    dbc install mssql
    dbc install mysql
    dbc install clickhouse

# Install private Foundry drivers (requires dbc auth login first)
install-private-drivers:
    @echo "Authenticating with Columnar private registry..."
    dbc auth login
    dbc install teradata

# Verify all installed Foundry drivers are loadable by adbc_driver_manager
verify-foundry-drivers:
    #!/usr/bin/env python3
    from adbc_driver_manager import _lib
    drivers = ["databricks", "redshift", "trino", "mssql", "mysql", "clickhouse"]
    failed = []
    for d in drivers:
        try:
            _lib.AdbcDatabase(driver=d)
            print(f"OK  {d}")
        except Exception as e:
            print(f"FAIL {d}: {e}")
            failed.append(d)
    if failed:
        raise SystemExit(f"Failed drivers: {failed}")

# Show info for all public Foundry drivers (version, path)
info-foundry-drivers:
    @for driver in databricks redshift trino mssql mysql clickhouse; do \
        echo "--- $$driver ---"; \
        dbc info $$driver; \
    done

# Remove all installed Foundry drivers (cleanup)
remove-foundry-drivers:
    dbc remove databricks
    dbc remove redshift
    dbc remove trino
    dbc remove mssql
    dbc remove mysql
    dbc remove clickhouse
```

**Notes on recipe design:**
- `install-dbc` is a separate recipe from `install-foundry-drivers` so CI can cache the dbc binary
- `verify-foundry-drivers` uses an inline Python script rather than shelling out to individual commands, so it produces a single summary rather than per-driver exit codes
- Private drivers (`teradata`, `oracle`) are in a separate recipe because they require interactive auth (`dbc auth login` prompts a browser flow)
- The `remove-foundry-drivers` recipe is useful for clean test setups but should not be in default CI runs

---

## Table Stakes vs Differentiators

### Table Stakes for Each New Backend

These features are required for a backend to ship — absent any of them, the backend is incomplete.

| Feature | SQLite | MySQL | ClickHouse | Teradata |
|---------|--------|-------|-----------|---------|
| Config class (`*Config`) | Required | Required | Required | Required (recover) |
| Parameter translation function | Required | Required | Required | Required (recover) |
| Registration in `_drivers.py` | Required | Required | Required | Required (recover) |
| Export in `__init__.py` | Required | Required | Required | Required |
| Driver name verified working | High confidence | High confidence | Medium confidence | High confidence |
| Unit tests for translator | Required | Required | Required | Required |
| Documentation page | Required | Required | Required | Required |

### Differentiators

Features that add genuine value beyond a bare config class:

| Feature | Backend | Value | Complexity |
|---------|---------|-------|-----------|
| Decomposed fields with URI assembly | MySQL | Parity with existing Databricks/Trino pattern; consumers don't need to know Go DSN format | Low |
| Pool size validation for `:memory:` | SQLite | Same as DuckDB: prevent silent isolated-state bug | Low |
| ClickHouse `username` field (not `user`) | ClickHouse | Correct kwarg name prevents silent auth failure; most users guess `user` | Low |
| Private registry workflow documentation | Teradata | Auth flow is non-obvious; requires `dbc auth login` before `dbc install` | Low |

### Anti-Features (Explicitly Not Building)

| Anti-Feature | Reason |
|-------------|--------|
| Oracle backend | Private registry, no concrete consumer, deferred |
| ClickHouse official driver (`ClickHouse/adbc_clickhouse`) | Alpha-stage, explicitly not production-ready per their README |
| MySQL-specific SSL fields | Driver supports TLS but SSL parameters are query-string params in the DSN; initial implementation is URI-only with a note |
| ClickHouse HTTP auth beyond basic username/password | Columnar quickstart shows only `uri`/`username`/`password`; additional auth (JWT, cert) is undocumented in the Foundry driver |
| Multiple MySQL-family configs (MariaDB, TiDB, Vitess) | Single `MySQLConfig` covers all; they share the MySQL wire protocol and the same Foundry driver |

---

## Feature Dependencies

```
Existing patterns (DatabricksConfig, TrinoConfig):
  └── MySQL: URI-or-decomposed pattern, Foundry driver path
  └── MSSQL: URI-or-decomposed pattern, Foundry driver path

Existing patterns (DuckDBConfig):
  └── SQLite: decomposed uri field, PyPI driver path, pool_size=1 guard for :memory:

New connection model (HTTP-based):
  └── ClickHouse: uri + username + password, Foundry driver path, username kwarg != user

Existing Foundry-driver infrastructure (_FOUNDRY_DRIVERS dict, resolve_driver()):
  └── All new Foundry backends extend this dict

New private registry auth flow:
  └── Teradata: dbc auth login → dbc install teradata → standard Foundry path
```

---

## Sources

- ADBC Drivers Foundry overview: https://docs.adbc-drivers.org/ (confirmed 2026-03-01) — HIGH confidence
- dbc CLI README: https://github.com/columnar-tech/dbc (confirmed 2026-03-01) — HIGH confidence
- dbc 0.2.0 announcement: https://columnar.tech/blog/announcing-dbc-0.2.0/ (February 10, 2026) — HIGH confidence
- MySQL ADBC driver README: https://github.com/adbc-drivers/mysql (confirmed 2026-03-01) — HIGH confidence
- ClickHouse ADBC driver README: https://github.com/ClickHouse/adbc_clickhouse (confirmed 2026-03-01) — HIGH confidence (WIP status explicitly stated)
- adbc-quickstarts by-database branch: https://github.com/columnar-tech/adbc-quickstarts (confirmed 2026-03-01) — HIGH confidence (live code, not docs)
  - MySQL: `root:my-secret-pw@tcp(localhost:3306)/demo` URI format
  - ClickHouse: `http://localhost:8123` + `username`/`password` kwargs
  - SQLite: `games.sqlite` filename URI
  - Oracle: `oracle://system:password@localhost:1521/FREEPDB1`
  - Teradata: `teradata://YOUR_USERNAME:YOUR_PASSWORD@YOUR_HOST:1025`
- Apache ADBC SQLite driver docs: https://arrow.apache.org/adbc/current/driver/sqlite.html — HIGH confidence
- dbc CLI DeepWiki commands reference: https://deepwiki.com/columnar-tech/dbc/4-commands-reference — MEDIUM confidence (indexed November 2025, pre-0.2.0)
