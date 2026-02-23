# Phase 2: Dependency Declarations - Context

**Gathered:** 2026-02-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Declare all runtime dependencies, optional warehouse extras, and missing dev dependencies in `pyproject.toml`. Resolve with `uv` to produce a complete `uv.lock`. Commit the lock file and document the dev setup command.

Scope is strictly `pyproject.toml` + `uv.lock` + REQUIREMENTS.md correction. No implementation code, no CI workflow files, no documentation pages — those belong in Phase 7.

</domain>

<decisions>
## Implementation Decisions

### Lock file strategy
- Commit `uv.lock` to git (currently untracked — this phase adds and commits it)
- Generate with `uv sync --all-extras` so the lock covers all optional warehouse driver deps
- CI must use `uv sync --frozen` to enforce the lock is up to date
- Document `uv sync --all-extras` in README or CONTRIBUTING as the dev setup command

### Optional extras — which drivers get extras
- Only create extras for PyPI-available drivers
- Confirmed PyPI extras: `[duckdb]`, `[snowflake]`, `[postgresql]`, `[flightsql]`
- `[bigquery]` — researcher must verify `adbc-driver-bigquery` is available on PyPI before including; include only if confirmed
- Foundry-distributed backends (Databricks, Redshift, Trino, MSSQL, Teradata) are **NOT** given extras in this phase — those drivers are not on PyPI
- `[all]` includes all confirmed PyPI extras only
- REQUIREMENTS.md SETUP-03 must be updated to reflect that Foundry driver extras are skipped in this phase

### Version constraint style for optional driver extras
- Open lower bounds only: `>=X` (no upper bound)
- Floor = latest stable version at time of writing (researcher confirms per-driver)
- Rationale: driver packages release frequently; upper bounds would increase maintenance overhead

### Version constraint style for runtime deps (pydantic-settings, sqlalchemy, adbc-driver-manager)
- Open lower bounds only: `>=X` style (not the `>=X,<Y` ranges specified in SETUP-02)
- Researcher determines the actual minimum version each dep requires (based on API usage), not just latest stable
- Rationale: pydantic-settings and sqlalchemy are common transitive deps — tight lower bounds cause unnecessary consumer conflicts
- This deviates from the literal spec in SETUP-02; update REQUIREMENTS.md SETUP-02 to reflect the chosen approach

### Dev dependency additions
- `syrupy>=4.0` and `coverage[toml]` go in the existing `[dependency-groups] dev` group (consistent with the existing pattern in pyproject.toml)
- No new dependency groups needed

### Claude's Discretion
- Exact minimum version floor for each runtime dep (researcher verifies against actual usage)
- Whether `adbc-driver-bigquery` is PyPI-available (researcher confirms)
- How to phrase the dev setup instructions in README/CONTRIBUTING

</decisions>

<specifics>
## Specific Ideas

- The constraint philosophy shift (open lower bounds for runtime deps) is intentional and should be called out clearly in REQUIREMENTS.md SETUP-02 — not silently deviated from
- The periodic CI-against-latest workflow (open a PR + mention @copilot on failure) was discussed but deferred — see Deferred Ideas

</specifics>

<deferred>
## Deferred Ideas

- **Foundry driver documentation** — Full documentation explaining how to install and use Foundry-distributed backends (Databricks, Redshift, Trino, MSSQL, Teradata) that have no PyPI extras. More than a README note — a proper docs section. Belongs in Phase 7 (Documentation and PyPI Publication).
- **Periodic CI against latest deps** — A scheduled workflow that builds against the latest available versions of all deps. On failure, opens a PR and mentions @copilot to fix. Covers both runtime deps and driver extras. Belongs in Phase 7 or a future milestone CI phase.

</deferred>

---

*Phase: 02-dependency-declarations*
*Context gathered: 2026-02-24*
