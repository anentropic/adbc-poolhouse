# Phase 6: Snowflake Integration - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Add syrupy snapshot tests for Snowflake: record locally with real credentials, commit snapshot files, replay in CI without credentials. Covers test file structure, a custom Arrow serializer that strips non-deterministic fields, credential management, and the snapshot update workflow. Documentation of the recording workflow goes in CONTRIBUTING.md as part of this phase.

</domain>

<decisions>
## Implementation Decisions

### What the tests exercise
- Two distinct tests: (1) connection health — `create_pool()` + acquire connection + `SELECT 1` verifies the full pool path works against real Snowflake; (2) Arrow data round-trip — `SELECT 1 AS n, 'hello' AS s`, assert schema + rows match snapshot
- Query for Arrow test: `SELECT 1 AS n, 'hello' AS s` — deterministic, no real tables required, captures both integer and varchar Arrow types
- Happy-path default config only: account, user, password, warehouse, database — no multi-variant testing (already covered by unit tests)
- Dedicated file: `tests/integration/test_snowflake.py` — separate from DuckDB integration tests because Snowflake requires real credentials and the marker isolation is cleaner

### Serializer design
- `SnowflakeArrowSnapshotSerializer` lives in `tests/integration/` — test-internal utility, not exported from the package
- Snapshot captures Arrow schema + all rows, serialized as readable JSON (schema as JSON object + rows as JSON array) — human-reviewable in PR diffs, credential residue easy to spot
- Strip from Arrow schema metadata: `queryId`, timestamps, `elapsedTime` (roadmap-specified) — Claude's discretion to identify and strip any additional non-deterministic fields found in actual Snowflake ADBC driver responses at implementation time

### Credential management
- Credentials supplied via `.env.snowflake` dotenv file (gitignored) — consistent with SnowflakeConfig's env-var support
- Test fixture loads the dotenv file and constructs `SnowflakeConfig` from the resulting environment variables
- No-creds behavior: `pytest.skip()` when `SNOWFLAKE_ACCOUNT` env var is absent
- Tests only run when explicitly opted in: `pytest -m snowflake` — default `pytest` run never attempts a Snowflake connection

### Snapshot update workflow
- Standard syrupy update mechanism: `pytest --snapshot-update -m snowflake` re-records all Snowflake snapshots
- Snapshot files stored at syrupy default: `tests/integration/__snapshots__/` — auto-managed, co-located with test file
- Add 'How to record Snowflake snapshots' section to `CONTRIBUTING.md` in this phase (while the workflow details are fresh)

### Claude's Discretion
- Exact pytest marker configuration (`pyproject.toml` markers section + `addopts` to exclude `snowflake` marker by default)
- How to load `.env.snowflake` in the conftest fixture (python-dotenv or manual `load_dotenv`)
- Exact serializer implementation details — which Arrow metadata fields beyond the roadmap-specified three to strip, based on what the real driver returns

</decisions>

<specifics>
## Specific Ideas

- In a neighboring project (`../cubano`), a conditional mock-connection pattern was considered but explicitly rejected here in favour of `pytest.skip` — simpler and the committed snapshot already validates data shape at recording time

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 06-snowflake-integration*
*Context gathered: 2026-02-25*
