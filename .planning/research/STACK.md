# Stack Research: adbc-poolhouse

**Research Date:** 2026-03-01
**Research Type:** Subsequent Milestone — New ADBC backends and `dbc` CLI tooling
**Milestone:** v1.1.0 — Backend Expansion & Foundry Driver Tooling

---

## Scope Note

This file extends the original STACK.md (dated 2026-02-23) which documented the base stack for v1.0.
The v1.0 stack decisions (pydantic-settings, SQLAlchemy QueuePool, basedpyright, ruff, uv) are
**not re-researched here**. This file covers only:

1. New ADBC driver packages on PyPI (beyond the five already in the library)
2. The `dbc` CLI — commands, flags, and driver names for Foundry-distributed backends
3. What NOT to add — unstable, redundant, or wrong-distribution drivers

---

## Confidence Key

- HIGH — confirmed from multiple current sources (PyPI + official docs or release blog)
- MEDIUM — confirmed from one authoritative source (PyPI or official docs)
- LOW — from web search only, single source, or unverified claim

---

## 1. New ADBC Driver Packages on PyPI

### 1.1 adbc-driver-sqlite

**Recommendation:** Add as optional extra `sqlite = ["adbc-driver-sqlite>=1.0.0"]`
**Current version:** 1.10.0 (released January 9, 2026, as part of ADBC 22)
**PyPI name:** `adbc-driver-sqlite`
**Confidence:** HIGH

**Why add:**
- Stable, on PyPI, maintained by the Apache Arrow project (same team as postgresql, flightsql, snowflake).
- Provides an ADBC-native connection for SQLite — useful for local development, testing, and lightweight
  embedded data pipelines where consumers don't want a server-side warehouse.
- Follows the same install pattern as the other PyPI drivers: `pip install adbc-poolhouse[sqlite]`.
- ADBC 22 (January 2026) added more `info` key support; driver is actively maintained.
- The library's config + pool abstraction adds value here: consumers get the same `create_pool(SQLiteConfig(...))`
  API and a QueuePool-managed connection, not a one-off `connect()` call.

**Why it is NOT redundant with DuckDB:**
- DuckDB is for analytical/OLAP workloads and ships as a full embedded engine with its own SQL dialect.
  SQLite is for lightweight transactional/embedded use where standard SQL and portability matter.
  Different use cases; different user profiles.

**Key design note — pool_size=1 for :memory: databases:**
- Identical constraint to DuckDB: in-memory SQLite databases are connection-scoped.
  The config model must enforce `pool_size=1` when `database=":memory:"`, matching the pattern
  already established in `DuckDBConfig`.

**Distribution:** PyPI (`pip install adbc-driver-sqlite`)
**Driver path resolution:** PyPI path (find_spec → `adbc_driver_sqlite._driver_path()`)
**`_PYPI_PACKAGES` entry:** `SQLiteConfig: ("adbc_driver_sqlite", "sqlite")`

**Sources:**
- https://pypi.org/project/adbc-driver-sqlite/1.10.0
- https://arrow.apache.org/blog/2026/01/09/adbc-22-release/
- https://arrow.apache.org/adbc/current/driver/sqlite.html

---

### 1.2 ClickHouse — DO NOT ADD

**PyPI candidate:** `adbc_clickhouse` (GitHub: ClickHouse/adbc_clickhouse)
**Current status:** Work-in-progress. Many methods return `NotImplemented`.
**Confidence:** HIGH (confirmed from GitHub description and multiple search results)

**Why NOT to add:**
- Official project description: "Work-in-progress. Not production-ready. Many methods are stubbed and
  return NotImplemented errors."
- Not on PyPI as a stable release; the repository exists at ClickHouse/adbc_clickhouse but is
  explicitly marked as incomplete.
- Adding a WIP driver exposes users to silent query failures and broken ADBC protocol compliance.
- If ClickHouse connectivity is needed, the correct path today is `clickhouse-connect` (the mature
  ClickHouse Python driver at v0.13.0, February 2026) — but that is not ADBC-based and would
  require a completely different architecture path; it is out of scope for this library.

**Revisit when:** adbc_clickhouse reaches v1.0 and is published to PyPI with full ADBC compliance.

**Sources:**
- https://github.com/ClickHouse/adbc_clickhouse (project description)

---

### 1.3 MySQL — Foundry-distributed, NOT a new PyPI optional extra

**PyPI package:** Does not exist. No `adbc-driver-mysql` on PyPI.
**Distribution:** ADBC Driver Foundry via `dbc install mysql`
**Confidence:** MEDIUM (no `adbc-driver-mysql` PyPI package found in multiple searches;
  Foundry distribution confirmed by adbc-drivers.org and columnar-tech/adbc-quickstarts)

**What the MySQL driver covers:**
- Columnar launched the MySQL ADBC driver as part of the Driver Foundry (October 2025).
- Connects to MySQL, MariaDB, TiDB, and Vitess (MySQL-wire-compatible systems) via `driver="mysql"`
  in `adbc_driver_manager.dbapi.connect()`.
- Installed via `dbc install mysql`; loaded via `adbc_driver_manager` at runtime.

**Implication for adbc-poolhouse:**
- If `MySQLConfig` is added, it goes in `_FOUNDRY_DRIVERS` alongside Databricks/Redshift/Trino/MSSQL.
- The dbc driver name is `"mysql"`.
- No PyPI optional extra; users must install the Foundry driver separately with `dbc`.

**Sources:**
- https://github.com/adbc-drivers (org page lists mysql repo)
- https://github.com/columnar-tech/adbc-quickstarts (python/ dir lists MySQL)
- https://siliconangle.com/2025/10/29/columnar-launches-redefine-data-connectivity-arrow-powered-adbc-drivers/

---

### 1.4 Spark — Does not exist as an ADBC driver

**Status:** No `adbc-driver-spark` exists on PyPI. No Foundry driver found.
**Confidence:** MEDIUM (absence confirmed across multiple searches and official driver lists)

**Why not:**
- Spark is a compute engine, not a database. ADBC targets SQL databases and query engines that
  return columnar results via Arrow — Spark's Python interface is PySpark, not a driver in this model.
- FlightSQL is the correct mechanism for connecting to Spark with Arrow semantics:
  Spark Thrift Server or Databricks SQL Warehouse both expose Arrow Flight SQL endpoints,
  accessible via the existing `adbc-driver-flightsql` already in the library.
- Do not add a Spark config. Direct consumers to FlightSQL or DatabricksConfig.

---

### 1.5 Oracle — Foundry-listed, not yet confirmed as stable

**Status:** Oracle mentioned in some `dbc` driver lists, but not confirmed as officially released
  or stable by Columnar or the ADBC Drivers org.
**Confidence:** LOW

**Recommendation:** Do not add in v1.1.0. The adbc-drivers.org official driver list as of
  early 2026 covers: BigQuery, Databricks, MSSQL, MySQL, Redshift, Snowflake, Trino.
  Oracle is not confirmed in official Foundry documentation.
  Revisit if/when `dbc install oracle` is documented on docs.columnar.tech.

---

## 2. Current Versions — Updated Reference for Existing PyPI Drivers

All Apache Arrow ADBC C/Go/Python packages versioned together and released as ADBC 22
(January 9, 2026). Python packages are at version **1.10.0**.

| PyPI Package | Recommended Minimum | ADBC 22 Version | Confidence |
|---|---|---|---|
| `adbc-driver-manager` | `>=1.0.0` | 1.10.0 | HIGH |
| `adbc-driver-snowflake` | `>=1.0.0` | 1.10.0 | HIGH |
| `adbc-driver-postgresql` | `>=1.0.0` | 1.10.0 | HIGH |
| `adbc-driver-flightsql` | `>=1.0.0` | 1.10.0 | HIGH |
| `adbc-driver-bigquery` | `>=1.3.0` | separate release cadence | MEDIUM |
| `adbc-driver-sqlite` | `>=1.0.0` | 1.10.0 | HIGH |

The existing minimum version pins in `pyproject.toml` (`>=1.0.0` for most packages) remain
appropriate — they do not need to be bumped to `>=1.10.0` because the library does not rely on
features introduced after 1.0.0. Keeping the floor low maximises consumer compatibility.

**Sources:**
- https://arrow.apache.org/blog/2026/01/09/adbc-22-release/
- https://pypi.org/project/adbc-driver-sqlite/1.10.0

---

## 3. The `dbc` CLI — Foundry Driver Management

### 3.1 What `dbc` is

`dbc` is the ADBC driver management CLI tool from [Columnar](https://columnar.tech/dbc/), launched
October 2025 alongside the ADBC Driver Foundry. It installs pre-built ADBC drivers from a public
driver registry (analogous to pip for Python packages, but for native ADBC shared libraries).

**Installation methods (all equivalent):**
```bash
# Linux / macOS shell installer
curl -LsSf https://dbc.columnar.tech/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://dbc.columnar.tech/install.ps1 | iex"

# uv tool (Python ecosystem, cross-platform)
uv tool install dbc

# Homebrew (macOS)
brew install columnar-tech/tap/dbc

# Windows MSI
# Download from https://dbc.columnar.tech/latest/dbc-latest-x64.msi
```

**Confidence:** MEDIUM (installation methods confirmed from docs.columnar.tech search results;
  uv tool install confirmed via columnar documentation)

---

### 3.2 Core `dbc` Commands

**Confidence:** MEDIUM for install/sync/info; LOW for exact flags of search/list
(official docs at docs.columnar.tech/dbc/ could not be fetched directly — assembled from
multiple search results including DeepWiki, GitHub issues, and blog posts).

#### `dbc install` — Install a driver

```bash
dbc install DRIVER [--level LEVEL] [--json] [--no-verify]
```

| Argument/Flag | Description |
|---|---|
| `DRIVER` | Driver name (see driver names table below) |
| `--level LEVEL` | Installation scope: `user` (default) or `system`. When omitted, checks `ADBC_DRIVER_PATH`, then `VIRTUAL_ENV`, then `CONDA_PREFIX`, then falls back to User level |
| `--json` | Output machine-readable JSON |
| `--no-verify` | Skip post-install verification step |

**Installation locations by level:**
- **User:** `~/.config/columnar/adbc_drivers/` (Linux/macOS), `%APPDATA%\columnar\adbc_drivers\` (Windows)
- **System:** system-wide path (requires elevated privileges)
- **Virtual env:** `$VIRTUAL_ENV/etc/adbc/drivers/` (detected automatically when `VIRTUAL_ENV` is set)
- **Conda:** `$CONDA_PREFIX/etc/adbc/drivers/` (detected automatically when `CONDA_PREFIX` is set)

**Single driver installation (current v1.x behaviour):**
```bash
dbc install databricks
dbc install redshift
dbc install mssql
dbc install mysql
dbc install trino
```

Note: Installing multiple drivers in a single command (`dbc install databricks redshift`) was
raised as a feature request in [GitHub issue #277](https://github.com/columnar-tech/dbc/issues/277)
and may not be supported in the current release. Write justfile recipes with one `dbc install`
call per driver.

**Confidence:** MEDIUM (command syntax confirmed; multi-driver flag unconfirmed)

---

#### `dbc info` — Get information about a driver

```bash
dbc info DRIVER
```

Example:
```bash
dbc info duckdb
dbc info mssql
```

Returns metadata about the driver (version, description, supported platforms).
**Confidence:** MEDIUM (confirmed from search results referencing the info subcommand)

---

#### `dbc search` — Search the driver registry

```bash
dbc search [QUERY]
```

Lists available drivers matching the query (or all drivers if query is omitted).
Used to discover what is available in the Foundry registry.
**Confidence:** LOW (subcommand name confirmed from docs structure references; exact flags unknown)

---

#### `dbc sync` — Synchronise installed drivers

```bash
dbc sync [--level LEVEL]
```

Updates installed drivers to their latest versions, respecting the same `--level` flag as install.
Analogous to `pip install --upgrade` for the driver registry.
**Confidence:** MEDIUM (confirmed from multiple references to sync as a parallel to install)

---

### 3.3 Foundry Driver Names

The following table maps adbc-poolhouse config classes to their `dbc` driver names.
Driver names are the exact string passed to `dbc install` and used as the `driver` argument
in `adbc_driver_manager.dbapi.connect()`.

| Config Class | `dbc install` name | `adbc_driver_manager` driver string | Distribution |
|---|---|---|---|
| `DatabricksConfig` | `databricks` | `"databricks"` | Foundry |
| `RedshiftConfig` | `redshift` | `"redshift"` | Foundry |
| `TrinoConfig` | `trino` | `"trino"` | Foundry |
| `MSSQLConfig` | `mssql` | `"mssql"` | Foundry |
| *(future)* `MySQLConfig` | `mysql` | `"mysql"` | Foundry |

Note: Teradata is listed in some dbc documentation. Verify via `dbc info teradata` or
`dbc search teradata` before finalising field names for `TeradataConfig` — this is called
out in PROJECT.md as "verify Teradata field names against real Columnar ADBC Teradata driver".

**Confidence:** HIGH for databricks/redshift/trino/mssql (confirmed by existing `_FOUNDRY_DRIVERS`
in `_drivers.py` and corroborated by Foundry documentation); MEDIUM for mysql (Foundry-confirmed,
not yet in the library); LOW for oracle (mentioned in some lists, not confirmed in official Foundry docs).

**Sources:**
- https://docs.columnar.tech/dbc/ (official reference)
- https://docs.adbc-drivers.org/ (ADBC Driver Foundry documentation)
- https://deepwiki.com/columnar-tech/adbc-quickstarts/4.1-microsoft-sql-server
- https://github.com/columnar-tech/dbc/issues/277
- https://columnar.tech/blog/announcing-dbc-0.2.0/
- https://docs.columnar.tech/dbc/reference/config_level/

---

### 3.4 `dbc` in Justfile Recipes

The justfile recipes for v1.1.0 should cover:

```just
# Install the dbc CLI (run once per machine)
install-dbc:
    curl -LsSf https://dbc.columnar.tech/install.sh | sh

# Install all Foundry drivers (run after install-dbc)
install-foundry-drivers:
    dbc install databricks
    dbc install redshift
    dbc install trino
    dbc install mssql

# Verify a specific driver is installed and working
verify-driver driver:
    dbc info {{driver}}

# List what's installed
list-drivers:
    dbc search
```

Note: `dbc install` detects `VIRTUAL_ENV` automatically — running inside a uv venv will install
drivers into the venv's `etc/adbc/drivers/` path without any extra flags. This means `uv run just
install-foundry-drivers` will scope the drivers to the project venv.

**Confidence:** MEDIUM (virtual env auto-detection confirmed from config_level docs; recipe
structure inferred from install command semantics)

---

## 4. New `pyproject.toml` Optional-Dependency Block

The only new PyPI extra from this research is `sqlite`. All new Foundry backends (MySQL) do not
have PyPI packages and therefore do not get extras entries.

```toml
[project.optional-dependencies]
duckdb = ["duckdb>=0.9.1"]
snowflake = ["adbc-driver-snowflake>=1.0.0"]
postgresql = ["adbc-driver-postgresql>=1.0.0"]
flightsql = ["adbc-driver-flightsql>=1.0.0"]
bigquery = ["adbc-driver-bigquery>=1.3.0"]
sqlite = ["adbc-driver-sqlite>=1.0.0"]          # NEW
all = [
    "adbc-poolhouse[duckdb]",
    "adbc-poolhouse[snowflake]",
    "adbc-poolhouse[postgresql]",
    "adbc-poolhouse[flightsql]",
    "adbc-poolhouse[bigquery]",
    "adbc-poolhouse[sqlite]",                   # NEW
]
```

---

## 5. What NOT to Add — Decision Table

| Candidate | Verdict | Rationale |
|---|---|---|
| `adbc-driver-sqlite` | ADD (PyPI extra) | Stable, on PyPI, useful for local dev and lightweight pipelines |
| `adbc_clickhouse` | DO NOT ADD | WIP, NotImplemented methods, not production-ready |
| `adbc-driver-mysql` (PyPI) | DOES NOT EXIST | Foundry-only; install via `dbc install mysql` |
| `MySQLConfig` (Foundry) | CONSIDER — scope after Teradata verification | Goes in `_FOUNDRY_DRIVERS` if added |
| Spark driver | DOES NOT EXIST | Use FlightSQL or DatabricksConfig; Spark is a compute engine not a driver target |
| Oracle driver | NOT YET — LOW confidence | Not confirmed stable in Foundry docs; revisit when `dbc info oracle` is documented |
| `adbc-driver-duckdb` (separate PyPI package) | DO NOT USE | DuckDB bundles ADBC in its wheel directly; `adbc-driver-duckdb` is redundant (noted in v1.0 research, confirmed still correct) |

---

## 6. Open Questions / Gaps

- **Teradata field names:** PROJECT.md flags this explicitly. Run `dbc install teradata && dbc info teradata`
  on a real machine to confirm the connection parameter names before writing `TeradataConfig`.
  The Columnar driver may use different field names than the generic Teradata JDBC/ODBC conventions.

- **MySQL driver maturity:** The MySQL Foundry driver launched October 2025. Usage patterns,
  known bugs, and connection parameter completeness have not been independently tested. Phase-specific
  research or a live spike is recommended before writing `MySQLConfig`.

- **Oracle driver availability:** Low-confidence listing. Confirm with `dbc search oracle` before
  planning any OracleConfig work.

- **`dbc` version:** Current dbc version is 0.2.x (the 0.2.0 announcement was the most recent
  found). The tool is still pre-1.0; command interface may change. Monitor for breaking changes
  before v1.2.0 work.

- **`dbc search` exact flags:** Only confirmed that the subcommand exists. Full flag reference
  requires fetching docs.columnar.tech/dbc/ directly.

---

*Research by Claude Code — 2026-03-01*
*Sources: PyPI, arrow.apache.org/blog, docs.columnar.tech, docs.adbc-drivers.org,*
*github.com/adbc-drivers, deepwiki.com/columnar-tech, siliconangle.com*
