# Phase 15: Replace Syrupy snapshot tests with pytest-adbc-replay VCR-style record/replay tests - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the existing Syrupy-based Snowflake snapshot tests with `pytest-adbc-replay` cassette-based record/replay tests. Add Databricks cassette tests (new — no existing coverage). Remove Syrupy entirely. Docker-based integration tests for PostgreSQL, MySQL, ClickHouse, and other local backends are out of scope for this phase (separate phase).

</domain>

<decisions>
## Implementation Decisions

### Plugin to use
- `pytest-adbc-replay` — already published on PyPI, just add it as a test dependency
- Replace `syrupy>=4.0` in `[project.optional-dependencies].dev` with `pytest-adbc-replay`
- No need to build a custom plugin

### Backend scope for cassette tests
- **Snowflake**: migrate the two existing tests (`test_connection_health`, `test_arrow_round_trip`)
- **Databricks**: add new cassette tests (no existing Snowflake-style tests exist for Databricks yet)
- **PostgreSQL, MySQL, ClickHouse, others**: deferred — will use Docker-based real connections in a future phase

### CI behaviour
- Cassettes are checked into the repository
- Cassette-based tests run in CI by default (no credentials required for replay)
- Recording requires real credentials and `--adbc-record=once` flag — done locally by developer

### Syrupy removal
- Remove `syrupy>=4.0` from `pyproject.toml`
- Delete `SnowflakeArrowSnapshotSerializer` class from `tests/integration/conftest.py`
- Delete `snowflake_snapshot` fixture from `tests/integration/conftest.py`
- Remove all syrupy imports (`JSONSnapshotExtension`, `SnapshotAssertion`, syrupy types)
- Delete any `.ambr` snapshot files if they exist (none found currently)

### Claude's Discretion
- Cassette directory location (default `tests/cassettes` is fine)
- Exact `adbc_auto_patch` driver module names for Snowflake and Databricks
- Cassette naming convention for each test
- Whether to keep `@pytest.mark.snowflake` alongside `@pytest.mark.adbc_cassette` or replace it

</decisions>

<specifics>
## Specific Ideas

- pytest-adbc-replay stores cassettes as `.sql` + `.arrow` + `.json` triplets per query, checked into version control
- Recording mode: `pytest --adbc-record=once` — records if cassette absent, replays if present
- Cassette format is human-readable enough to review in PRs (SQL is plain text, Arrow IPC is binary but .json has metadata)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/integration/conftest.py`: `snowflake_pool` session-scoped fixture — can be kept (still useful for recording); `snowflake_snapshot` + `SnowflakeArrowSnapshotSerializer` — to be deleted
- `tests/integration/test_snowflake.py`: Two test methods to migrate — `test_connection_health`, `test_arrow_round_trip`; class-level `@pytest.mark.snowflake` marker stays or moves to cassette approach

### Established Patterns
- Test deps live in `[project.optional-dependencies].dev` in `pyproject.toml`
- No `[tool.pytest.ini_options]` section exists yet — Phase 15 adds one for `adbc_auto_patch`
- `adbc_driver_manager.dbapi` is the intercept layer for Foundry (Databricks) backends
- `adbc_driver_snowflake.dbapi` (or similar) is the intercept layer for Snowflake

### Integration Points
- `tests/integration/conftest.py` — where session-scoped pool fixtures live
- `pyproject.toml` `[tool.pytest.ini_options]` — new section needed for `adbc_auto_patch`
- `.github/workflows/ci.yml` / `pr.yml` — cassette tests should run automatically (no special env gate needed once cassettes are checked in)

</code_context>

<deferred>
## Deferred Ideas

- Docker-based integration tests for PostgreSQL, MySQL, ClickHouse, and other local backends — future phase
- Adding cassette tests for other cloud backends (BigQuery, Redshift, etc.) — if/when credentials are available

</deferred>

---

*Phase: 15-replace-syrupy-snapshot-tests-with-pytest-adbc-replay-vcr-style-record-replay-tests*
*Context gathered: 2026-03-02*
