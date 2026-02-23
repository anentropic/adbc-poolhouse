# External Integrations

**Analysis Date:** 2026-02-23

## APIs & External Services

**Data Warehouse Drivers (planned - per `_notes/design-discussion.md`):**

The library's purpose is to wrap ADBC drivers for data warehouses. No integrations are implemented yet (the package source at `src/adbc_poolhouse/__init__.py` is an empty skeleton). Planned integrations:

- Snowflake - v1 production target
  - SDK/Client: `adbc-driver-snowflake` (PyPI, Apache ADBC project)
  - Auth: account, user, password, private key, token (via Pydantic BaseSettings - reads from env)

- DuckDB - v1 dev/test target
  - SDK/Client: `duckdb` (PyPI, built-in Apache ADBC support)
  - Auth: File path or in-memory (no credentials required for local use)

- BigQuery - future
  - SDK/Client: `adbc-driver-bigquery` (PyPI)

- PostgreSQL - future
  - SDK/Client: `adbc-driver-postgresql` (PyPI)

- Apache Spark (Flight SQL) - future
  - SDK/Client: `adbc-driver-flightsql` (PyPI)

- Databricks - future
  - SDK/Client: `adbc-driver-manager` + Foundry `dbc install databricks`

- Redshift - future
  - SDK/Client: `adbc-driver-manager` + Foundry `dbc install redshift`

- Trino - future
  - SDK/Client: `adbc-driver-manager` + Foundry `dbc install trino`

- MSSQL/Fabric/Synapse - future
  - SDK/Client: `adbc-driver-manager` + Foundry `dbc install mssql`

- Teradata - future
  - SDK/Client: `adbc-driver-manager` + Foundry `dbc install teradata`

## Data Storage

**Databases:**
- None (this is a connection pooling library, not an application with its own database)
- The library creates pooled connections TO external databases; it does not manage its own data store

**File Storage:**
- Local filesystem only (DuckDB file-based databases are a consumer concern)

**Caching:**
- None at library level
- SQLAlchemy QueuePool (planned) handles connection reuse internally

## Authentication & Identity

**Auth Provider:**
- No auth provider - authentication is warehouse-specific and delegated to ADBC drivers
- Planned: Pydantic BaseSettings models will read warehouse credentials from environment variables (e.g. `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_PASSWORD`, etc.)
- Private key auth (for Snowflake key-pair authentication) planned as a supported auth method

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- No logging framework configured currently
- Planned: Helpful error messages when required ADBC drivers are not installed

## CI/CD & Deployment

**Hosting:**
- PyPI - package distribution target (https://pypi.org/p/adbc-poolhouse)
- GitHub Pages - documentation hosting (https://anentropic.github.io/adbc-poolhouse/)
  - Deployed via `.github/workflows/docs.yml` on push to `main`

**CI Pipeline:**
- GitHub Actions
  - `.github/workflows/ci.yml` - Runs on every push: quality gates (prek) + pytest, matrix Python 3.11/3.14
  - `.github/workflows/pr.yml` - Runs on pull requests: pytest with coverage, posts coverage comment via `MishaKav/pytest-coverage-comment@v1.1.51`
  - `.github/workflows/docs.yml` - Builds and deploys MkDocs site to GitHub Pages on push to `main`
  - `.github/workflows/release.yml` - Triggered on semver tags (`v*.*.*`): builds distributions, validates installation, generates changelog via git-cliff, publishes to PyPI via `pypa/gh-action-pypi-publish`

**Dependency Updates:**
- GitHub Dependabot (`.github/dependabot.yml`) - weekly updates for GitHub Actions and pip dependencies, grouped

## Environment Configuration

**Required env vars:**
- None currently (no implemented features)
- Planned: Warehouse-specific credentials read via Pydantic BaseSettings (exact var names TBD per warehouse config model)

**Secrets location:**
- GitHub repository secrets: `GITHUB_TOKEN` (used in PR workflow for coverage comments)
- PyPI publishing uses OIDC Trusted Publishing (no stored secret - GitHub's `id-token: write` permission)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Third-Party Developer Tools

**Changelog:**
- git-cliff v2.7.0 - Generates CHANGELOG.md from conventional commits
- Config: `.cliff.toml`
- Runs in release workflow via direct binary download from GitHub releases

**Pre-commit Infrastructure:**
- pre-commit hooks defined in `.pre-commit-config.yaml`
- Runner: prek (Rust-based, installed via `uv tool install prek`)
- Remote hook sources: `astral-sh/ruff-pre-commit`, `astral-sh/uv-pre-commit`, `adamchainz/blacken-docs`

---

*Integration audit: 2026-02-23*
