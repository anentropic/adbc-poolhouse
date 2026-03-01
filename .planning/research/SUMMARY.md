# Project Research Summary

**Project:** adbc-poolhouse v1.1.0 — Backend Expansion & Debt Cleanup
**Domain:** Python ADBC connection-pool library — backend expansion and developer tooling
**Researched:** 2026-03-01
**Confidence:** HIGH

## Executive Summary

adbc-poolhouse has a clean, mechanically extensible architecture: one config file, one translator file, two dispatch-table entries, one public re-export, and one docs guide per backend. Adding new backends in v1.1.0 is additive and slice-isolated — no cross-cutting rewrites are required. The milestone adds four new backends (SQLite via PyPI; MySQL, ClickHouse, and Teradata via the Columnar ADBC Driver Foundry), fixes a silent-failure bug in the Databricks translator's decomposed-field path, and introduces justfile recipes for `dbc` CLI driver management. The `dbc` CLI (v0.2.0, February 2026) is the canonical tool for installing Foundry drivers and requires `adbc-driver-manager>=1.8.0` for manifest resolution — the project's current `>=1.0.0` floor must be bumped.

The recommended build order is driven by one hard dependency: the Databricks decomposed-field fix must land before MySQL, Teradata, or ClickHouse, because those translators follow the URI-first-with-decomposed-fallback pattern and will model themselves on a broken Databricks implementation if the fix is deferred. Beyond that single constraint, all backend slices are independent and touch disjoint files. Two tech debt items declared open in PROJECT.md (removal of `_adbc_driver_key()` and deletion of `_pool_types.py`) are already complete — confirmed from live source inspection and `.planning/.continue-here.md` — and are not active work items for this milestone.

The primary risks are: (1) the Databricks translator fix carries five specific pitfalls around URL-encoding, silent empty-dict, OAuth M2M, and leading-slash normalisation that must all be addressed in the initial implementation; (2) the `dbc` CLI justfile recipes require a `command -v dbc` prerequisite guard and `--level env` install flag from the start, not as later refinements; and (3) Teradata requires `dbc auth login` (private registry) before `dbc install teradata`, and connection parameters must be verified against a live driver install before writing the translator.

## Conflict Resolution: Teradata Driver Availability

PITFALLS.md states "no Teradata driver exists in the ADBC Driver Foundry — docs.adbc-drivers.org lists 8 drivers, Teradata absent." ARCHITECTURE.md states "`dbc install teradata` is available" (HIGH confidence, fetched from `columnar-tech/dbc/docs/reference/driver_list.md` via GitHub API).

**Both sources are correct for what they describe.** The conflict is a scoping difference, not a factual contradiction:

- `docs.adbc-drivers.org` lists **public** Foundry drivers (8 drivers). Teradata is absent because it is a **private-registry** driver that requires authentication before installation.
- The `dbc` CLI driver registry (`columnar-tech/dbc/docs/reference/driver_list.md`) includes private-registry drivers not listed on the public documentation site.
- FEATURES.md independently confirms the distinction: public drivers (MySQL, ClickHouse, Databricks, Redshift, Trino, MSSQL) install without authentication; private-registry drivers (Teradata, Oracle) require `dbc auth login` first.

**Authoritative answer:** The Teradata driver exists in the dbc private registry and is installable via `dbc auth login && dbc install teradata`. It is intentionally absent from `docs.adbc-drivers.org` because that site covers only the public Foundry. ARCHITECTURE.md (GitHub source, HIGH confidence) is the authoritative source for the driver's existence. PITFALLS.md's concern about field-name verification remains valid — decomposed connection parameters must be confirmed against a live driver install before writing the translator.

**Recommendation:** Include TeradataConfig and `translate_teradata()` in this milestone. Gate decomposed-field implementation on a live `dbc install teradata` smoke test. Ship URI-only initially (`teradata://user:pass@host:1025` — confirmed from `adbc-quickstarts`) and add decomposed fields only after key names are verified.

## Key Findings

### Recommended Stack

The v1.0 stack (pydantic-settings, SQLAlchemy QueuePool, basedpyright, ruff, uv) is confirmed correct and is not re-researched. New stack additions for v1.1.0:

**Core technologies — new additions only:**
- `adbc-driver-sqlite>=1.0.0` (PyPI, Apache ADBC project): Stable driver at v1.10.0; follows the same release cadence as the existing PostgreSQL/FlightSQL/Snowflake drivers; adds an optional `sqlite` extra. Current ADBC 22 (January 2026) release.
- `dbc` CLI (Columnar, v0.2.0, February 2026): Foundry driver manager — canonical tool for installing MySQL, ClickHouse, Teradata, and all existing Foundry backends. Install via `curl -LsSf https://dbc.columnar.tech/install.sh | sh` or `uv tool install dbc`.
- `adbc-driver-manager>=1.8.0`: Version floor bump required — dbc README explicitly states manifest resolution requires `>=1.8.0`. Current `>=1.0.0` pin must be updated.

**What NOT to add:**
- `adbc_clickhouse` (ClickHouse's own ADBC driver): Alpha-stage, WIP, explicitly not production-ready per their README. Use the Columnar Foundry `clickhouse` driver (`dbc install clickhouse`) instead.
- Oracle backend: Private-registry only (`dbc auth login` required), no concrete consumer, deferred to a future milestone.
- Spark driver: Does not exist as ADBC. Use FlightSQL or DatabricksConfig.
- `adbc-driver-duckdb` separate PyPI package: DuckDB bundles ADBC in its wheel; this package is redundant.

See `.planning/research/STACK.md` for the full version table, dbc CLI command reference, and pyproject.toml optional-dependency block.

### Expected Features

**Must have (table stakes) — required for every new backend before it ships:**
- Config class (`*Config`) with Pydantic field validation and env-prefix
- Parameter translator (pure function: config → `dict[str, str]` ADBC kwargs; omit `None` fields)
- Registration in `_PYPI_PACKAGES` or `_FOUNDRY_DRIVERS` dispatch dict
- Export in `__init__.py`
- Unit tests for config model and translator function
- Docs guide page (`docs/src/guides/[warehouse].md`)

**Backend-specific must-have behaviours:**

| Backend | Must-have special behaviour | Distribution |
|---------|---------------------------|-------------|
| SQLite | `pool_size=1` guard for `:memory:` databases (same pattern as DuckDB); `_adbc_entrypoint()` override to `adbc_driver_sqlite_init` | PyPI extra |
| MySQL | Decomposed-to-URI translation that hides the Go DSN format (`user:pass@tcp(host:port)/db`) — consumers must not need to know this convention | Foundry public |
| ClickHouse | `username` field (not `user`) matching the driver kwarg exactly; HTTP URI format (`http://host:port`) | Foundry public |
| Teradata | Private-registry auth workflow documented in justfile and DEVELOP.md; URI-only initially (`teradata://user:pass@host:1025`) | Foundry private |
| Databricks (fix) | URI-first with decomposed-field fallback; URL-encoding via `urllib.parse.quote()`; `model_validator` gate for all-None config; `http_path` leading-slash normalisation; URI-precedence `UserWarning` when both URI and decomposed fields are set | Existing — fix only |

**Defer to future milestones:**
- Oracle backend (private registry, no concrete consumer)
- MySQL SSL field parameters (DSN query-string params; add when specifically requested)
- ClickHouse JWT/cert auth beyond basic `username`/`password`
- Multiple MySQL-family configs (MariaDB, TiDB, Vitess all share `MySQLConfig` via MySQL wire protocol — no separate classes needed)

See `.planning/research/FEATURES.md` for the full dbc CLI workflow documentation and justfile recipe designs.

### Architecture Approach

The slice-per-warehouse pattern is mechanical and fully additive. Every new backend follows an identical checklist: two new source files (`_[warehouse]_config.py`, `_[warehouse]_translator.py`), entries in two dispatch tables (`_PYPI_PACKAGES` or `_FOUNDRY_DRIVERS` in `_drivers.py`; alphabetical `isinstance` branch in `_translators.py`), one `__init__.py` re-export, three test additions (configs, translators, drivers), one docs guide, and for PyPI backends one `pyproject.toml` extra. No changes to `_driver_api.py` or `_pool_factory.py` are needed for any new backend — the existing infrastructure handles driver dispatch and error messaging automatically.

**Major components:**
1. `_drivers.py` — two dispatch dicts (`_PYPI_PACKAGES` for PyPI backends, `_FOUNDRY_DRIVERS` for Foundry backends); type-keyed; drives both driver resolution and the automatic `dbc install [name]` error messages emitted by `_driver_api.py`
2. `_translators.py` — alphabetical `isinstance` chain; maps config type to translator function; single `translate_config()` public entry point; receives new `if isinstance(config, XConfig): return translate_x(config)` branch per backend
3. `_[warehouse]_config.py` — Pydantic BaseSettings subclass per backend; env-prefix; `SecretStr` for credentials; pool-size validators where applicable; no `_adbc_driver_key()` method (already removed)
4. `_[warehouse]_translator.py` — pure function; maps config fields to exact ADBC driver kwarg keys; omits `None` fields; for Foundry backends uses URI-first with decomposed fallback
5. `_driver_api.py` — single `adbc_driver_manager` facade (unchanged); NOT_FOUND handler reads `_FOUNDRY_DRIVERS` reverse-lookup to emit `dbc install [name]` automatically

**Key invariant:** A config type belongs in exactly one dispatch dict. PyPI-distributed drivers go in `_PYPI_PACKAGES`; Foundry-only drivers go in `_FOUNDRY_DRIVERS`. A Foundry driver incorrectly placed in `_PYPI_PACKAGES` will trigger a `find_spec` call that always returns `None`, bypassing the correct error message path.

**Tech debt status:** `_adbc_driver_key()` is already removed from `BaseWarehouseConfig` and all subclasses. `_pool_types.py` (AdbcCreatorFn) is already deleted. Do not re-introduce either. PROJECT.md still shows these as open — it is stale.

See `.planning/research/ARCHITECTURE.md` for file-level change lists, dispatch table code, anti-pattern catalogue, and scalability notes.

### Critical Pitfalls

1. **Databricks URI URL-encoding (PITFALL-D1, CRITICAL)** — PAT tokens contain base64 characters (`+`, `=`, `/`) that are URI metacharacters. Construct the URI using `urllib.parse.quote(token, safe="")` on every variable component. An f-string without encoding silently misparses tokens that contain `+` or `=`. Test with a token string that is exactly `dapi+test=value/path`.

2. **DatabricksConfig all-None validation gate (PITFALL-D2, CRITICAL)** — without a `model_validator(mode="after")` that requires either `uri` or all of `host`+`http_path`+`token`, `create_pool()` receives `{}` and fails with a cryptic driver error. Add this validator to `DatabricksConfig` before updating the translator, independent of the translator change.

3. **`dbc` not in PATH — opaque failure (PITFALL-J1, CRITICAL)** — every justfile recipe that calls `dbc` must open with a `command -v dbc` guard inside a `#!/usr/bin/env bash` shebang recipe that prints a human-readable install instruction. Do not use just's `which()` function — it evaluates at parse time against the parent process PATH, not recipe execution PATH (PITFALL-J3, MODERATE).

4. **Driver installs to wrong path level (PITFALL-J4, MODERATE)** — `dbc install` without `--level env` installs to the user-level path, which `uv run python` does not search first. All `install-drivers` recipes must use `dbc install --level env [driver]` so drivers land in `$VIRTUAL_ENV/etc/adbc/drivers/` where `adbc_driver_manager` finds them.

5. **Dead method re-introduction (PITFALL-R2, MODERATE)** — `_adbc_driver_key()` and `_pool_types.py` are already removed. Any plan or stale document that lists them as open work is incorrect. Do not add `_adbc_driver_key()` to any new config class. Use the `_PYPI_PACKAGES`/`_FOUNDRY_DRIVERS` dispatch tables instead.

See `.planning/research/PITFALLS.md` for the full pitfall catalogue with code-level prevention patterns and unit test recipes.

## Implications for Roadmap

Based on the combined research, the recommended phase structure for v1.1.0 is:

### Phase 1: Housekeeping, Infrastructure, and Databricks Fix
**Rationale:** Three independent but foundational tasks that must precede all backend work. The `adbc-driver-manager` floor bump is required for Foundry manifest resolution to work correctly. The justfile tooling must exist before contributors can install and test Foundry drivers locally. The Databricks fix must land before MySQL, Teradata, or ClickHouse because those translators model themselves on the URI-first decomposed-field pattern — implementing them before the fix means following a broken template.
**Delivers:** `adbc-driver-manager>=1.8.0` floor in `pyproject.toml`; justfile `dbc-install-cli`, `dbc-install-drivers`, `dbc-info`, `dbc-uninstall-drivers`, `dbc-search` recipes with `command -v` guards and `--level env`; DEVELOP.md "Foundry driver management" section; `DatabricksConfig` decomposed-field support with URL-encoding, validation gate, leading-slash normalisation, and URI-precedence warning; updated PROJECT.md closing the two already-completed tech debt items.
**Avoids:** PITFALL-D1, PITFALL-D2, PITFALL-D3, PITFALL-D4, PITFALL-J1, PITFALL-J3, PITFALL-J4
**Research flag:** No further research needed — all patterns and pitfalls are fully documented with code-level examples.

### Phase 2: SQLite Backend (PyPI)
**Rationale:** Lowest complexity of all new backends. Uses the DuckDB pattern almost exactly. Adding SQLite first validates that the PyPI slice mechanism still works cleanly after Phase 1 changes and gives confidence before tackling Foundry backends. This is also a short phase — it can be reviewed and merged quickly.
**Delivers:** `SQLiteConfig`, `translate_sqlite()`, `sqlite` PyPI extra (`adbc-driver-sqlite>=1.0.0`), `pool_size=1` guard for `:memory:`, `_adbc_entrypoint()` override to `adbc_driver_sqlite_init`, full test coverage, `docs/src/guides/sqlite.md`.
**Uses:** Apache ADBC `adbc-driver-sqlite>=1.0.0` (HIGH confidence, PyPI, stable ADBC 22)
**Avoids:** Bare-import safety (DRIV-04 pattern — `find_spec` guard before import; config type goes in `_PYPI_PACKAGES`)
**Research flag:** No further research needed. Entrypoint symbol and `:memory:` pool-size semantics are confirmed from official Apache ADBC docs.

### Phase 3: MySQL Backend (Foundry — public registry)
**Rationale:** First Foundry backend of this milestone and the highest consumer-value addition (MySQL is the most-deployed open-source RDBMS; MariaDB, TiDB, and Vitess use the same driver). Depends on Phase 1 for both the DatabricksConfig fix (establishes URI-first decomposed-field pattern) and the justfile tooling (needed to install and test the driver). The Go DSN URI format (`user:pass@tcp(host:port)/db`) is the primary implementation complexity.
**Delivers:** `MySQLConfig`, `translate_mysql()`, `_FOUNDRY_DRIVERS` entry with key `"mysql"`, full test coverage including the Go DSN format edge cases, `docs/src/guides/mysql.md`, updated justfile `dbc-install-drivers` recipe.
**Avoids:** Anti-Pattern 3 (Foundry driver in `_FOUNDRY_DRIVERS`, not `_PYPI_PACKAGES`); Anti-Pattern 4 (empty dict when decomposed fields provided but URI absent)
**Research flag:** MySQL individual kwarg key names for the decomposed-field path are MEDIUM confidence — quickstarts only show URI-based connections. Before writing the decomposed-field translator path, run `dbc install mysql` locally and confirm that `host`, `port`, `user`, `password`, `database` are accepted as separate kwargs (or establish that the driver is URI-only like Databricks).

### Phase 4: ClickHouse Backend (Foundry — public registry)
**Rationale:** Independent of MySQL. Low complexity — HTTP URI plus `username` and `password`; no DSN assembly. Grouped separately from MySQL because the `username` (not `user`) kwarg name is a non-obvious driver convention that deserves its own focused test class. Connection parameters are confirmed from live `adbc-quickstarts` code (HIGH confidence).
**Delivers:** `ClickHouseConfig`, `translate_clickhouse()`, `_FOUNDRY_DRIVERS` entry with key `"clickhouse"`, full test coverage, `docs/src/guides/clickhouse.md`, updated justfile recipe.
**Avoids:** `username` vs `user` field naming trap (FEATURES.md flags this as a silent auth failure if the wrong key is used)
**Research flag:** No further research needed. Connection parameters confirmed from `columnar-tech/adbc-quickstarts` live Python code (HIGH confidence).

### Phase 5: Teradata Backend (Foundry — private registry)
**Rationale:** Last new backend because it requires private-registry authentication (`dbc auth login`) which adds friction to local testing. The URI pattern is confirmed from `adbc-quickstarts` (`teradata://user:pass@host:1025`). Start with URI-only, add decomposed fields only after key names are verified against a live driver. Justfile must document the `dbc auth login` prerequisite separately from the public-driver installation recipe.
**Delivers:** `TeradataConfig`, `translate_teradata()`, `_FOUNDRY_DRIVERS` entry with key `"teradata"`, full test coverage, `docs/src/guides/teradata.md`, separate `dbc-install-private-drivers` justfile recipe that calls `dbc auth login` before `dbc install teradata`.
**Avoids:** PITFALL-T2 (ODBC vs ADBC field name confusion — comment all accepted key names with `# VERIFIED from live dbc install teradata + connection test`)
**Research flag:** Decomposed-field key names need live verification via `dbc auth login && dbc install teradata`. If private-registry access is unavailable, ship URI-only with a documented limitation and defer decomposed fields.

### Phase Ordering Rationale

- Phase 1 before all others: DatabricksConfig fix establishes the authoritative decomposed-field pattern; version floor and justfile tooling are prerequisites for Foundry driver testing.
- Phase 2 (SQLite) before Phases 3-5: Validates the PyPI slice mechanism independently; lowest risk, highest confidence; builds confidence before Foundry work.
- Phases 3-5 are independent of each other and can be parallelised or reordered. MySQL first for highest consumer value; ClickHouse second for lowest complexity; Teradata last for private-registry friction.
- Every phase produces a fully shippable slice — no phase leaves the library in a partial state.

### Research Flags

Phases that can proceed without further research:
- **Phase 1** (Housekeeping + Databricks fix): All pitfalls and patterns documented with code-level prevention steps. No unknowns.
- **Phase 2** (SQLite): PyPI path, entrypoint name (`adbc_driver_sqlite_init`), and `:memory:` semantics all confirmed from official Apache ADBC docs and PyPI.
- **Phase 4** (ClickHouse): Connection parameters confirmed from live `adbc-quickstarts` code (HIGH confidence).

Phases that need a local spike or live verification step before implementation:
- **Phase 3** (MySQL): Decomposed-field individual kwarg names (not URI) are MEDIUM confidence. Run `dbc install mysql` locally and confirm the exact key strings before writing the decomposed-field translator path.
- **Phase 5** (Teradata): Private-registry access required to confirm decomposed field names. URI-only path can be shipped without live verification; decomposed-field path cannot.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyPI packages confirmed from `pypi.org` and official Apache ADBC blog; dbc CLI confirmed from `columnar-tech/dbc` GitHub; version pins from live release data (ADBC 22, dbc 0.2.0) |
| Features | HIGH | Connection parameter shapes confirmed from `columnar-tech/adbc-quickstarts` live Python examples fetched via GitHub API (2026-03-01); dbc command reference from `columnar-tech/dbc/docs/reference/cli.md` (v0.2.0) |
| Architecture | HIGH | Based on direct source inspection of all files in `src/adbc_poolhouse/`, `tests/`, `justfile`, `pyproject.toml`, `.planning/.continue-here.md`; dbc CLI reference fetched from GitHub |
| Pitfalls | HIGH for Databricks and justfile risks; MEDIUM for Teradata field names | Databricks pitfalls derived from official driver docs (URI-only confirmed from `docs.adbc-drivers.org`); justfile pitfalls from `just` issue tracker and dbc docs; Teradata decomposed-field names MEDIUM because private-registry access was unavailable during research |

**Overall confidence:** HIGH

### Gaps to Address

- **MySQL decomposed-field kwarg names** (MEDIUM confidence): Quickstarts show only URI-based connections. Before writing the decomposed-field translator path, confirm that the Columnar MySQL ADBC driver accepts individual `host`, `port`, `user`, `password`, `database` kwargs — or establish that it is URI-only like Databricks, in which case decomposed fields assemble a URI rather than being passed as separate kwargs.

- **Teradata private-registry access**: URI connection parameters are confirmed (`teradata://user:pass@host:1025`). Decomposed-field key names are inferred from the MSSQL pattern and are LOW confidence. Verify before adding decomposed fields to `TeradataConfig`. If access is unavailable, ship URI-only with a clear limitation note.

- **`adbc-driver-manager>=1.8.0` floor impact**: Bumping from `>=1.0.0` is a breaking change for consumers pinned to versions below 1.8.0. Verify whether this warrants a semver bump beyond v1.1.0 before finalising the release plan.

- **Stale PROJECT.md task list**: PROJECT.md lists `_adbc_driver_key()` removal and `_pool_types.py` deletion as open tasks. Both are confirmed complete from live source and `.planning/.continue-here.md`. Close these items in PROJECT.md before starting Phase 1 to avoid confusion when acting on the task list.

- **`dbc` CLI version stability**: dbc is at v0.2.x (pre-1.0). The CLI interface may change before v1.2.0 planning. Monitor for breaking changes; consider pinning `uv tool install dbc==0.2.x` in CI if the interface changes affect justfile recipes.

## Sources

### Primary — HIGH Confidence
- `src/adbc_poolhouse/` (all source files, direct inspection, 2026-03-01) — architecture, dispatch table pattern, dead code status
- `.planning/.continue-here.md` — confirms `_adbc_driver_key()` removed, `_pool_types.py` deleted in v0.1 cleanup
- `columnar-tech/dbc/docs/reference/cli.md` (v0.2.0, GitHub, 2026-03-01) — dbc command reference
- `columnar-tech/dbc/docs/reference/driver_list.md` (GitHub, 2026-03-01) — Teradata in dbc private registry confirmed
- `columnar-tech/dbc/README.md` (GitHub, 2026-03-01) — `adbc-driver-manager>=1.8.0` requirement
- `columnar-tech/adbc-quickstarts` Python examples (GitHub API, 2026-03-01) — MySQL, Teradata, ClickHouse, Oracle URI formats confirmed from live code
- `docs.adbc-drivers.org/drivers/index.html` — public Foundry driver list (8 drivers; Teradata absent — private registry)
- `docs.adbc-drivers.org/drivers/databricks/index.html` — Databricks driver is URI-only
- `arrow.apache.org/adbc/current/driver/sqlite.html` — SQLite entrypoint symbol (`adbc_driver_sqlite_init`), `:memory:` semantics
- `pypi.org/project/adbc-driver-sqlite/1.10.0` — confirmed stable, ADBC 22 release
- `arrow.apache.org/blog/2026/01/09/adbc-22-release/` — ADBC 22 (v1.10.0) version reference

### Secondary — MEDIUM Confidence
- `deepwiki.com/columnar-tech/dbc/4-commands-reference` — dbc command reference (indexed November 2025, pre-0.2.0)
- `deepwiki.com/columnar-tech/dbc/5.1-configuration-levels` — dbc install paths per platform
- `columnar.tech/blog/announcing-dbc-0.2.0/` (February 10, 2026) — dbc 0.2.0 feature summary including declarative `dbc.toml` and `dbc auth login`
- `siliconangle.com/2025/10/29/columnar-launches-...` — MySQL Foundry driver launch (October 2025)
- `api.github.com/orgs/adbc-drivers/repos` — 23 repositories confirmed including mysql, clickhouse

### Tertiary — LOW Confidence
- `dbc install --level env` flag behaviour — documented but not tested in this environment
- MySQL decomposed-field individual kwarg key names — inferred from MSSQL pattern; needs live driver verification
- `just` issue #2597 (`which()` parse-time evaluation) — documented by maintainer, not independently reproduced

---
*Research completed: 2026-03-01*
*Ready for roadmap: yes*
