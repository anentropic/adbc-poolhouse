# Architecture Patterns

**Domain:** adbc-poolhouse — ADBC backend expansion and Foundry driver tooling
**Researched:** 2026-03-01
**Confidence:** HIGH — based on direct source inspection of all files in the codebase plus dbc CLI reference docs from GitHub

---

## Recommended Architecture

The codebase already implements a clean slice-per-warehouse pattern. Every new backend
follows the same slotting model: one config file, one translator file, one entry in two
dispatch tables, one public re-export, one test class per file, one docs guide. The
pattern is mechanical and additive — no cross-cutting rewrites required.

```
create_pool(config)
    └─ resolve_driver(config)      <- _drivers.py   (dispatch: type -> driver path/name)
    └─ translate_config(config)    <- _translators.py (dispatch: type -> dict[str,str])
    └─ config._adbc_entrypoint()   <- _base_config.py (default None; DuckDB overrides)
         └─ create_adbc_connection(driver_path, kwargs, entrypoint)
                                   <- _driver_api.py  (single adbc_driver_manager facade)
```

### Component Boundaries

| File | Responsibility | What Changes Per New Backend |
|------|---------------|------------------------------|
| `_[warehouse]_config.py` | Pydantic BaseSettings model, env_prefix, field validators | NEW FILE — always |
| `_[warehouse]_translator.py` | Pure function: config -> dict[str, str] ADBC kwargs | NEW FILE — always |
| `_translators.py` | isinstance dispatch: config type -> translator fn | ADD import + elif branch |
| `_drivers.py` | type -> (pkg_name, extra) for PyPI; type -> short_name for Foundry | ADD entry to `_PYPI_PACKAGES` or `_FOUNDRY_DRIVERS` dict |
| `__init__.py` | Public re-exports | ADD import + `__all__` entry |
| `tests/test_configs.py` | Config model unit tests | ADD test class |
| `tests/test_translators.py` | Translator pure-function tests | ADD test class + dispatch test case |
| `tests/test_drivers.py` | Driver detection path tests | ADD test for new config type |
| `pyproject.toml` | Optional dependencies | ADD extra for PyPI backends only |
| `docs/src/guides/[warehouse].md` | Per-warehouse installation and usage guide | NEW FILE — always |
| `DEVELOP.md` | Developer guide | ADD dbc section |
| `justfile` | Developer task recipes | ADD dbc recipes |

---

## PyPI Backend: File-Level Change List

A PyPI backend is one where the ADBC driver is published to PyPI and installed via pip.
Current PyPI backends: Snowflake, BigQuery, PostgreSQL, FlightSQL.

**New files (create):**

1. `src/adbc_poolhouse/_[warehouse]_config.py`
   - Subclass `BaseWarehouseConfig`
   - Set `model_config = SettingsConfigDict(env_prefix="[WAREHOUSE]_")`
   - Map driver-specific connection params as typed Pydantic fields
   - Use `SecretStr` for passwords, tokens, URIs that embed credentials
   - Override `_adbc_entrypoint()` only if the driver requires a non-None entrypoint symbol (currently only DuckDB does; all other drivers return the base class default of `None`)
   - Do NOT implement `_adbc_driver_key()` — that method was removed in a prior tech debt cleanup and no longer exists on BaseWarehouseConfig

2. `src/adbc_poolhouse/_[warehouse]_translator.py`
   - Single pure function `translate_[warehouse](config: [Warehouse]Config) -> dict[str, str]`
   - Config type import under `TYPE_CHECKING` guard (avoids circular imports)
   - Map config fields to exact ADBC driver parameter key names
   - Omit `None` fields; include bool defaults as `'true'`/`'false'` strings

3. `docs/src/guides/[warehouse].md`
   - Installation: `pip install adbc-poolhouse[[warehouse]]`
   - Connection code examples
   - Env-var loading pattern

**Modified files (edit):**

4. `src/adbc_poolhouse/_drivers.py`
   - Add config class import at module level
   - Add entry to `_PYPI_PACKAGES` dict: `[Warehouse]Config: ("[pkg_name]", "[extra]")`
   - Example: `BigQueryConfig: ("adbc_driver_bigquery", "bigquery")`

5. `src/adbc_poolhouse/_translators.py`
   - Add config class import at module level
   - Add translator function import at module level
   - Add `if isinstance(config, [Warehouse]Config): return translate_[warehouse](config)` branch before the final `raise TypeError`
   - Alphabetical order within PyPI group per existing convention

6. `src/adbc_poolhouse/__init__.py`
   - Add `from adbc_poolhouse._[warehouse]_config import [Warehouse]Config`
   - Add `"[Warehouse]Config"` to `__all__`

7. `pyproject.toml`
   - Add `[warehouse] = ["[pypi-package]>=[min-version]"]` to `[project.optional-dependencies]`
   - Add `"adbc-poolhouse[[warehouse]]"` to the `all` extra list

8. `tests/test_configs.py` — add test class `Test[Warehouse]Config`
9. `tests/test_translators.py` — add test class `Test[Warehouse]Translator` + dispatch test case
10. `tests/test_drivers.py` — add Path 1 and Path 2 tests for the new config type

---

## Foundry Backend: File-Level Change List

A Foundry backend is one whose ADBC driver is distributed by the ADBC Driver Foundry
(not on PyPI) and accessed via `adbc_driver_manager` manifest resolution. Current
Foundry backends: Databricks, Redshift, Trino, MSSQL.

**New files (create):**

1. `src/adbc_poolhouse/_[warehouse]_config.py`
   - Same structure as PyPI config
   - No `_adbc_entrypoint()` override needed (Foundry drivers use manifest resolution, not a shared-lib entrypoint symbol)
   - Do not reference the dbc install name in the config model — that lives in `_drivers.py`

2. `src/adbc_poolhouse/_[warehouse]_translator.py`
   - Same pattern. For Foundry backends, connection is typically URI-only or URI-first with decomposed-field fallback. Verify key names against `docs.adbc-drivers.org` and `adbc-quickstarts` examples.

3. `docs/src/guides/[warehouse].md`
   - Installation: `pip install adbc-poolhouse` (no extra — Foundry drivers have no PyPI package)
   - dbc install command: `dbc install [short_name]`
   - Connection code examples

**Modified files (edit):**

4. `src/adbc_poolhouse/_drivers.py`
   - Add config class import at module level
   - Add entry to `_FOUNDRY_DRIVERS` dict: `[Warehouse]Config: ("[short_name]", "[short_name]")`
   - The first string is the `adbc_driver_manager` manifest name; the second is the `dbc install` name
   - Example: `DatabricksConfig: ("databricks", "databricks")`
   - `_driver_api.py` uses this dict to build the `dbc install [name]` error message automatically — no changes needed to `_driver_api.py`

5. `src/adbc_poolhouse/_translators.py`
   - Same as PyPI path — add imports and isinstance branch

6. `src/adbc_poolhouse/__init__.py`
   - Same as PyPI path — add import and `__all__` entry

7. `pyproject.toml`
   - No new optional dependency entry — Foundry drivers have no PyPI package
   - No change to the `all` extra

8. `tests/test_configs.py` — add test class
9. `tests/test_translators.py` — add test class + dispatch test
10. `tests/test_drivers.py` — add Foundry short-name test (assert `resolve_driver(Config())` returns the short name without calling `find_spec`)

**Not modified for Foundry:**

`_driver_api.py` — already handles all Foundry NOT_FOUND errors via the `_FOUNDRY_DRIVERS`
reverse-lookup. Adding a new entry to `_FOUNDRY_DRIVERS` in `_drivers.py` is the only
change needed. `_driver_api.py` imports that dict at runtime and builds `dbc install
[name]` error messages automatically.

---

## Dispatch Table Update Patterns

### `_drivers.py` — Two distinct dispatch dicts

```python
# PyPI: find_spec -> path, with manifest fallback
_PYPI_PACKAGES: dict[type, tuple[str, str]] = {
    SnowflakeConfig:  ("adbc_driver_snowflake",  "snowflake"),
    BigQueryConfig:   ("adbc_driver_bigquery",   "bigquery"),
    PostgreSQLConfig: ("adbc_driver_postgresql", "postgresql"),
    FlightSQLConfig:  ("adbc_driver_flightsql",  "flightsql"),
    # NEW PyPI backend:
    # [Warehouse]Config: ("[pkg_name]", "[extra]"),
}

# Foundry: skip find_spec, return short name for manifest resolution
_FOUNDRY_DRIVERS: dict[type, tuple[str, str]] = {
    DatabricksConfig: ("databricks", "databricks"),
    RedshiftConfig:   ("redshift",   "redshift"),
    TrinoConfig:      ("trino",      "trino"),
    MSSQLConfig:      ("mssql",      "mssql"),
    # NEW Foundry backend:
    # MySQLConfig:     ("mysql",      "mysql"),
    # TeradataConfig:  ("teradata",   "teradata"),
}
```

**Key invariant:** A config type belongs in exactly one dict. If a driver is available
both on PyPI and through Foundry (currently no such case), prefer the PyPI path so
`find_spec` can resolve the shared library directly.

### `_translators.py` — isinstance chain

```python
def translate_config(config: WarehouseConfig) -> dict[str, str]:
    # Order within each group is alphabetical (existing convention).
    if isinstance(config, BigQueryConfig):    return translate_bigquery(config)
    if isinstance(config, DatabricksConfig):  return translate_databricks(config)
    if isinstance(config, DuckDBConfig):      return translate_duckdb(config)
    if isinstance(config, FlightSQLConfig):   return translate_flightsql(config)
    if isinstance(config, MSSQLConfig):       return translate_mssql(config)
    if isinstance(config, PostgreSQLConfig):  return translate_postgresql(config)
    if isinstance(config, RedshiftConfig):    return translate_redshift(config)
    if isinstance(config, SnowflakeConfig):   return translate_snowflake(config)
    if isinstance(config, TrinoConfig):       return translate_trino(config)
    # INSERT new backend here, maintaining alphabetical order:
    # if isinstance(config, MySQLConfig):     return translate_mysql(config)
    raise TypeError(f"Unsupported config type: {type(config).__name__}")
```

All concrete config classes are direct siblings of `BaseWarehouseConfig` (no
multi-level inheritance), so `isinstance` check order does not affect correctness.

---

## New Backends: Research-Confirmed Connection Parameter Patterns

The following patterns were verified from the `columnar-tech/adbc-quickstarts` repository
via GitHub API (HIGH confidence for URI shape).

### MySQL (Foundry — `dbc install mysql`)

```python
# URI format (verified: columnar-tech/adbc-quickstarts/python/mysql/mysql/main.py)
db_kwargs = {"uri": "root:password@tcp(localhost:3306)/dbname"}
```

MySQL URI format uses the Go DSN style (`tcp(host:port)/db`), not a standard URL scheme.
`MySQLConfig` fields: `uri: str | None`, plus decomposed `host`, `port`, `user`,
`password`, `database` for field-mode connection.

### Teradata (Foundry — `dbc install teradata`)

```python
# URI format (verified: columnar-tech/adbc-quickstarts/python/teradata/main.py)
db_kwargs = {"uri": "teradata://username:password@host:1025"}
```

Standard URL scheme. `TeradataConfig` fields: `uri: SecretStr | None`, plus decomposed
`host`, `port`, `user`, `password`.

Note: Teradata was previously dropped from this project because no Foundry driver existed
at that time (per `.planning/.continue-here.md`). The driver now exists in the
`adbc-drivers` GitHub org and has quickstart examples. Verify driver stability before
re-adding.

### ClickHouse (Foundry — `dbc install clickhouse`)

```python
# URI + decomposed (verified: columnar-tech/adbc-quickstarts/python/clickhouse/main.py)
db_kwargs = {"uri": "http://localhost:8123", "username": "user", "password": "pass"}
```

ClickHouse uses HTTP URI plus separate `username`/`password` keys.

### Oracle (Foundry — `dbc install oracle`)

```python
# URI format (verified: columnar-tech/adbc-quickstarts/python/oracle/main.py)
db_kwargs = {"uri": "oracle://system:password@localhost:1521/FREEPDB1"}
```

Standard Oracle connection string. `OracleConfig` fields: `uri: SecretStr | None`, plus
decomposed `host`, `port`, `user`, `password`, `service_name`.

---

## justfile Recipes: dbc Tooling

The `dbc` CLI (v0.2.0, February 2026) is the tool for installing Foundry drivers.
The following recipe shapes are derived from `columnar-tech/dbc/docs/reference/cli.md`
(HIGH confidence — fetched directly from GitHub).

### Available `dbc` Commands (v0.2.0)

| Command | Purpose |
|---------|---------|
| `dbc search [PATTERN]` | Search available drivers |
| `dbc install <DRIVER>` | Install a driver (user level by default) |
| `dbc uninstall <DRIVER>` | Uninstall a driver |
| `dbc info <DRIVER>` | Show driver metadata and version |
| `dbc init` | Create `dbc.toml` driver list file |
| `dbc add <DRIVER>` | Add driver to `dbc.toml` |
| `dbc remove <DRIVER>` | Remove driver from `dbc.toml` |
| `dbc sync` | Install all drivers from `dbc.toml` |
| `dbc docs [DRIVER]` | Open driver documentation in browser |

**There is no `dbc verify` subcommand.** The `dbc info <DRIVER>` subcommand shows
version and metadata. Runtime verification (is the driver loadable?) is handled by
the existing `create_adbc_connection()` in `_driver_api.py`, which raises a clear
`ImportError` when the manifest is missing.

### Recommended justfile Recipes

```just
# Install the dbc CLI via pipx (isolated, puts dbc on PATH)
dbc-install-cli:
    pipx install dbc

# Install all Foundry drivers supported by adbc-poolhouse
dbc-install-drivers:
    dbc install databricks
    dbc install redshift
    dbc install trino
    dbc install mssql

# Show metadata for each supported Foundry driver
dbc-info:
    dbc info databricks
    dbc info redshift
    dbc info trino
    dbc info mssql

# Uninstall all Foundry drivers
dbc-uninstall-drivers:
    dbc uninstall databricks
    dbc uninstall redshift
    dbc uninstall trino
    dbc uninstall mssql

# Search all available drivers (for discovery)
dbc-search:
    dbc search
```

### Recipe Design Notes

1. `dbc install` installs at user level by default. For CI or system-wide installs
   add `--level system`. For venv-local installs, `VIRTUAL_ENV` is auto-detected.

2. As of dbc 0.2.0, multiple drivers can be installed in a single call
   (`dbc install databricks redshift`). Separate lines in the justfile recipe are
   preferred for clear error attribution.

3. `dbc install` accepts version constraints: `dbc install databricks>=1.0.0`.
   The justfile recipes install latest stable (no version pin).

4. When a new Foundry backend is added to adbc-poolhouse: add the corresponding
   `dbc install [name]` line to `dbc-install-drivers` and `dbc uninstall [name]`
   to `dbc-uninstall-drivers`. Keep the list in alphabetical order.

---

## DEVELOP.md Changes Required

The existing `DEVELOP.md` has no section on Foundry driver management. The following
changes are needed:

### New section: "Foundry driver management"

Add under `## Common Tasks`. Content to cover:

1. What the ADBC Driver Foundry is (Columnar, not Apache) and why some drivers are not on PyPI
2. Installing the `dbc` CLI: `just dbc-install-cli` (or `pipx install dbc` directly)
3. Installing all supported Foundry drivers: `just dbc-install-drivers`
4. Checking driver metadata: `just dbc-info`
5. Reference to `https://docs.columnar.tech/dbc/` and `https://docs.adbc-drivers.org/`
6. `adbc_driver_manager` version requirement: `>=1.8.0` for manifest resolution. The
   dbc README explicitly states `adbc-driver-manager>=1.8.0` is required. The current
   `pyproject.toml` pins `>=1.0.0` — this should be updated.
7. The `ADBC_DRIVER_PATH` environment variable for per-project driver isolation
8. Brief note on the three-path detection strategy in `_drivers.py` so contributors
   understand how new Foundry backends integrate

### Update `## Project Structure` section

The current structure listing references files that no longer exist:
- Remove `_pool_types.py` from the listing (deleted in prior tech debt cleanup)
- The listing should not include `_teradata_*.py` (Teradata support was dropped)

### Update `## Common Tasks`

Add entries for:
- `just dbc-install-cli`
- `just dbc-install-drivers`
- `just dbc-info`

---

## Tech Debt Removals: Interaction With New Backend Additions

### Current Status of Declared Tech Debt

| Item | Actual Status | Impact on New Backends |
|------|--------------|------------------------|
| Remove `_pool_types.py` (AdbcCreatorFn) | DONE — file does not exist in repo | None — do not import this |
| Remove `_adbc_driver_key()` from BaseWarehouseConfig and all subclasses | DONE — not present in current source | New config files MUST NOT implement this method |
| Fix DatabricksConfig decomposed-field gap (host/http_path/token silently produce `{}` when URI absent) | PENDING — `translate_databricks()` only emits `uri` | Must fix before adding new Foundry backends that use decomposed fields (MySQL, Teradata, ClickHouse) |
| Verify Teradata field names against real Columnar ADBC Teradata driver | PENDING — but Teradata config/translator don't exist yet | Teradata is a new backend, not a fix to existing code |

The PROJECT.md file still lists items 1 and 2 as `[ ]` (open), but the source files
confirm they were completed in a prior session. The `.planning/.continue-here.md` file
records this explicitly: "Deleted `_pool_types.py` (AdbcCreatorFn unused)" and
"Removed dead `_adbc_driver_key()` abstract method from base + all 10 subclasses".

### Build Order Implication

Fix the DatabricksConfig decomposed-field gap **before** adding MySQL, Teradata, or
ClickHouse. The fix establishes the authoritative pattern for URI-first with
decomposed-field fallback that those translators will follow. Adding them before the
fix means their translators are modelled on a broken Databricks translator.

---

## Correct Build Order

The dependency DAG for this milestone is:

```
1. Tech debt removals (already done in prior session — no work needed)
   - _pool_types.py deleted
   - _adbc_driver_key() removed

2. DatabricksConfig decomposed-field fix
   - translate_databricks() gains host/http_path/token decomposed path
   - test_translators.py gains decomposed-field test cases
   - MUST come before new Foundry backends with decomposed fields

3. justfile dbc recipes (independent of backend additions)
   - dbc-install-cli, dbc-install-drivers, dbc-info, dbc-uninstall-drivers, dbc-search

4. DEVELOP.md dbc section (depends on justfile recipes existing)

5. pyproject.toml adbc-driver-manager version bump
   - Change >=1.0.0 to >=1.8.0 (manifest resolution requires 1.8.0 per dbc README)
   - Independent of backend additions but affects Foundry driver correctness

6. New Foundry backend: Teradata (verify driver stability before implementing)
   - _teradata_config.py
   - _teradata_translator.py
   - _drivers.py: entry in _FOUNDRY_DRIVERS
   - _translators.py: entry in isinstance chain
   - __init__.py: export
   - tests/test_configs.py: class
   - tests/test_translators.py: class
   - tests/test_drivers.py: case
   - docs/src/guides/teradata.md (replaces existing placeholder page)
   - justfile: add teradata to dbc-install-drivers and dbc-uninstall-drivers

7. New Foundry backend: MySQL (parallel with Teradata — independent slices)
   - Same file list as step 6 with mysql substituted

8. New backends: ClickHouse, Oracle, others (same pattern; verify driver stability each)

9. (No separate docs step — docs are created as part of each backend slice)
```

**Why this order:**

- Step 2 before steps 6-8: DatabricksConfig fix establishes the correct decomposed-field pattern
- Steps 3-5 are independent and can be parallelised or done in any order relative to each other
- Steps 6-8 are independent slices that touch disjoint files
- Any step can be committed independently since each slice is self-contained

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Putting driver logic in the config model

**What:** Adding dispatch logic, driver path resolution, or dbc install commands into
the config model (`_[warehouse]_config.py`).

**Why bad:** Config models are data containers. Driver resolution lives in `_drivers.py`
dispatch tables. Mixing them creates coupling that makes testing harder and breaks the
separation that lets `_driver_api.py` be the single `adbc_driver_manager` importer.

**Instead:** Config model fields only. Detection logic in `_drivers.py` dict entries.

### Anti-Pattern 2: Importing driver packages at module level in `_drivers.py`

**What:** Adding `import adbc_driver_[warehouse]` at the top of `_drivers.py`.

**Why bad:** Breaks bare-import safety (the module docstring calls this DRIV-04). The
library must be importable without any ADBC driver installed. Driver package imports
are guarded inside function bodies (`_resolve_pypi_driver` uses `__import__` after
`find_spec` confirms presence).

**Instead:** Only config class imports at module level in `_drivers.py`. Driver package
imports inside function bodies under `find_spec` guard.

### Anti-Pattern 3: Adding Foundry backends to `_PYPI_PACKAGES`

**What:** Adding a Foundry-distributed driver (Databricks, MySQL, Teradata) to the
`_PYPI_PACKAGES` dict rather than `_FOUNDRY_DRIVERS`.

**Why bad:** `_PYPI_PACKAGES` triggers a `find_spec` call that always returns `None` for
Foundry-only drivers. The Path 2 fallback returns the package name as a manifest key,
which accidentally works — but it bypasses the `_FOUNDRY_DRIVERS` reverse lookup used
by `_driver_api.py` to build the `dbc install [name]` error message.

**Instead:** Foundry-only drivers go in `_FOUNDRY_DRIVERS`. The `_driver_api.py`
NOT_FOUND handler uses `_FOUNDRY_DRIVERS.values()` to resolve the correct install name.

### Anti-Pattern 4: Emitting empty dict from decomposed-field translators

**What:** Implementing a translator that only emits `uri` when set and silently returns
`{}` when decomposed fields (host, port, user, password) are provided instead.

**Why bad:** Silent connection failures. The driver receives no parameters and raises
an unhelpful error at connection time rather than a clear error at translation time.

**Instead:** For URI-first translators, implement both paths: if `uri` is set, return
early with `{"uri": ...}`; otherwise map decomposed fields. This is the pattern the
DatabricksConfig fix will establish — follow it for all new Foundry backends.

### Anti-Pattern 5: Implementing `_adbc_driver_key()` on a new config class

**What:** Adding `def _adbc_driver_key(self) -> str:` to a new config class.

**Why bad:** This method was removed in tech debt cleanup. It is no longer part of
`BaseWarehouseConfig` or the `WarehouseConfig` Protocol. Any new implementation will
be dead code immediately.

**Instead:** Register the config type in `_PYPI_PACKAGES` or `_FOUNDRY_DRIVERS`.

---

## Scalability Considerations

| Concern | Current (9 warehouses) | At 20 warehouses | At 50 warehouses |
|---------|------------------------|-----------------|-----------------|
| `_translators.py` isinstance chain | 9 branches, ~70 lines | ~20 branches, ~140 lines | Too long — refactor to dict dispatch |
| `_drivers.py` import block | 9 config imports | ~20 imports | Acceptable |
| `__init__.py` export list | 10 symbols | ~22 symbols | Acceptable |
| `tests/test_translators.py` | ~270 lines | ~540 lines | Split into per-warehouse test files |

At 20 warehouses the isinstance chain in `_translators.py` is still acceptable. At 50
warehouses, refactor to a `dict[type, Callable]` dispatch table (same shape as
`_drivers.py` already uses). That refactor does not change external behaviour.

---

## Sources

- **HIGH confidence** (direct source inspection): All files in `src/adbc_poolhouse/`,
  `tests/`, `justfile`, `DEVELOP.md`, `pyproject.toml`, `.planning/.continue-here.md`,
  `docs/src/guides/`
- **HIGH confidence** (dbc CLI reference): `columnar-tech/dbc/docs/reference/cli.md`
  fetched via GitHub raw URL (v0.2.0, released 2026-02-10)
- **HIGH confidence** (dbc driver list reference): `columnar-tech/dbc/docs/reference/driver_list.md`
- **HIGH confidence** (dbc README): `columnar-tech/dbc/README.md` — confirms `>=1.8.0`
  requirement for manifest resolution
- **HIGH confidence** (adbc-drivers org repos): `api.github.com/orgs/adbc-drivers/repos`
  — 23 repositories confirmed including mysql, clickhouse, mssql, databricks, redshift,
  trino (also: oracle via quickstarts)
- **HIGH confidence** (connection parameter shapes): `columnar-tech/adbc-quickstarts`
  Python examples for mysql, teradata, clickhouse, oracle — fetched via GitHub API
- **MEDIUM confidence** (decomposed-field key names for MySQL, Teradata, ClickHouse):
  quickstarts show URI only; individual key names for decomposed-field mode need
  verification against driver source or `docs.adbc-drivers.org`
