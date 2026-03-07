# Phase 14: Homepage Discovery Fix - Context

**Gathered:** 2026-03-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Add MySQL and ClickHouse to two places in `docs/src/index.md`: the ADBC drivers install table and the "First pool" config class list. Also update REQUIREMENTS.md to mark MYSQL-05 and CH-05 complete. No new code — documentation edits only.

</domain>

<decisions>
## Implementation Decisions

### Install table structure
- Reorganize the full ADBC drivers table into two groups: PyPI installable first, Foundry-distributed second
- Within each group, rows are alphabetical by warehouse name
- PyPI group: Apache Arrow Flight SQL, BigQuery, DuckDB, PostgreSQL, Snowflake, SQLite
- Foundry group: ClickHouse, Databricks, MSSQL / Azure SQL / Fabric, MySQL, Redshift, Trino

### MySQL and ClickHouse table cells
- Both use the same Foundry pattern as existing Databricks/Redshift/Trino/MSSQL rows
- Cell format: `Foundry-distributed — see [Foundry installation](guides/X.md)`
- Alpha details for ClickHouse (including `--pre` flag) stay in the ClickHouse guide, not the homepage table

### Config class list
- Mirror the table grouping: PyPI configs first (alphabetical), then Foundry configs (alphabetical)
- PyPI group: `BigQueryConfig`, `DuckDBConfig`, `FlightSQLConfig`, `PostgreSQLConfig`, `SnowflakeConfig`, `SQLiteConfig`
- Foundry group: `ClickHouseConfig`, `DatabricksConfig`, `MSSQLConfig`, `MySQLConfig`, `RedshiftConfig`, `TrinoConfig`

### Claude's Discretion
- Exact markdown formatting of the table restructure (header row, alignment)
- Whether to add a visual separator or sub-header between PyPI and Foundry groups (or keep one flat table)

</decisions>

<specifics>
## Specific Ideas

- User explicitly chose consistency with existing Foundry driver pattern — no special treatment for ClickHouse alpha on the homepage
- The `--pre` flag requirement is documented in `docs/src/guides/clickhouse.md` and confirmed by Phase 13 tracking fix

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/src/index.md`: target file, contains both the install table and the config class list prose block
- `docs/src/guides/clickhouse.md`: already documents `dbc install --pre clickhouse` and ClickHouse alpha status
- `docs/src/guides/mysql.md`: already documents `dbc install mysql`

### Established Patterns
- Foundry driver table cell format (from current index.md): `Foundry-distributed — see [Foundry installation](guides/X.md)`
- Config class list format (from current index.md): comma-separated inline list, backtick-wrapped names

### Integration Points
- `uv run mkdocs build --strict` must pass after edits — no broken links or invalid markdown
- REQUIREMENTS.md MYSQL-05 and CH-05 rows need checkbox + traceability updated after index.md edits

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 14-homepage-discovery-fix*
*Context gathered: 2026-03-02*
