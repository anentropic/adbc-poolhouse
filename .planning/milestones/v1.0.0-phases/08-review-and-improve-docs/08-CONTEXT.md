# Phase 8: review-and-improve-docs - Context

**Gathered:** 2026-02-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Review and improve the documentation established in Phase 7 — quickstart (index.md), four guide pages, per-warehouse guides (new), and changelog. No new library capabilities are in scope.

</domain>

<decisions>
## Implementation Decisions

### Already implemented (during discussion)
- Removed "Snapshot testing in CI" section from `guides/snowflake.md` — internal concern, not user-facing
- Rewrote dbt profiles section in `guides/consumer-patterns.md` using `dbt.config.profile.Profile.from_raw_profiles` + `ProfileRenderer` — handles Jinja (`env_var()` calls); old raw YAML approach silently breaks with Jinja templates
- Renamed section to "Loading credentials from dbt"; added honest caveat that `from_raw_profiles` is internal dbt-core API, stable across 1.x

### index.md additions
- After the "Installation" section: add a new section explaining that adbc-poolhouse also requires an ADBC driver for the target warehouse. Include a list of all supported warehouses with install commands and links (PyPI packages where available, Foundry path for Databricks/Redshift/Trino/MSSQL/Teradata)
- "First pool in five minutes" section: add a list of typed config class names (DuckDBConfig, SnowflakeConfig, BigQueryConfig, etc.) so readers can see all options at a glance

### Per-warehouse guide pages
- Create one guide page per warehouse following the Snowflake guide structure: install the extra, required/notable fields with a code example, env var prefix, see-also
- All warehouses get a page: DuckDB, Snowflake (already exists), BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, Teradata
- MSSQL and Teradata: stub pages only (install + env var prefix, no auth examples) — field coverage for these is best-effort and unverified
- Update mkdocs.yml nav to include all warehouse pages

### Public cleanup API
- Add a public `close_pool(pool)` helper function to replace the current `pool.dispose()` + `pool._adbc_source.close()` two-step pattern
- Also expose as a context manager so callers can use `with managed_pool(config) as pool: ...`
- Update all docs (quickstart, pool-lifecycle guide, consumer patterns) to use the new public API — eliminate all references to `pool._adbc_source`

### Pool tuning documentation
- `guides/pool-lifecycle.md`: add a "Tuning the pool" section with a brief summary of the available kwargs and their defaults
- `guides/configuration.md`: add a full kwargs table (pool_size, max_overflow, timeout, recycle, pre_ping) with types, defaults, and a sentence on when to change each

### Changelog
- Wire `git-cliff` to generate `docs/src/changelog.md` from commit history
- Should produce an initial entry covering all commits to date

### Prose quality
- Terse, technical voice — no hand-holding, trust the reader; keep existing style
- Apply humanizer pass to all new or substantially rewritten prose
- New per-warehouse pages follow the same structural pattern as the existing Snowflake guide

### Claude's Discretion
- Exact wording and structure of the ADBC driver install section on index.md
- Whether Foundry-path warehouses need extra explanation vs PyPI warehouses
- git-cliff configuration details (tag pattern, template)
- How to structure the context manager API (standalone function vs class)

</decisions>

<specifics>
## Specific Ideas

- The dispose pattern calling `pool._adbc_source.close()` is unacceptable as user-facing documentation — fix it at the library level with a public helper and context manager
- Pool tuning kwargs are documented nowhere currently; this is a significant gap
- The dbt integration should use `Profile.from_raw_profiles` (dbt-core 1.0+) not raw YAML — already implemented
- MSSQL/Teradata: stub pages rather than omitting, so users can confirm those backends exist; caveat that field coverage is best-effort
- git-cliff is already configured in the release workflow; reuse that configuration to populate the docs changelog

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 08-review-and-improve-docs*
*Context gathered: 2026-02-28*
