# Phase 14: Homepage Discovery Fix - Research

**Researched:** 2026-03-02
**Domain:** MkDocs documentation — index.md table and prose edits
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Install table structure
- Reorganize the full ADBC drivers table into two groups: PyPI installable first, Foundry-distributed second
- Within each group, rows are alphabetical by warehouse name
- PyPI group: Apache Arrow Flight SQL, BigQuery, DuckDB, PostgreSQL, Snowflake, SQLite
- Foundry group: ClickHouse, Databricks, MSSQL / Azure SQL / Fabric, MySQL, Redshift, Trino

#### MySQL and ClickHouse table cells
- Both use the same Foundry pattern as existing Databricks/Redshift/Trino/MSSQL rows
- Cell format: `Foundry-distributed — see [Foundry installation](guides/X.md)`
- Alpha details for ClickHouse (including `--pre` flag) stay in the ClickHouse guide, not the homepage table

#### Config class list
- Mirror the table grouping: PyPI configs first (alphabetical), then Foundry configs (alphabetical)
- PyPI group: `BigQueryConfig`, `DuckDBConfig`, `FlightSQLConfig`, `PostgreSQLConfig`, `SnowflakeConfig`, `SQLiteConfig`
- Foundry group: `ClickHouseConfig`, `DatabricksConfig`, `MSSQLConfig`, `MySQLConfig`, `RedshiftConfig`, `TrinoConfig`

### Claude's Discretion
- Exact markdown formatting of the table restructure (header row, alignment)
- Whether to add a visual separator or sub-header between PyPI and Foundry groups (or keep one flat table)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CH-05 | `ClickHouseConfig` exported from `__init__.py`; ClickHouse warehouse guide page in docs; API reference entry; `uv run mkdocs build --strict` passes | ClickHouseConfig already exported and guide exists; index.md omission is the remaining gap |
| MYSQL-05 | `MySQLConfig` exported from `__init__.py`; MySQL warehouse guide page in docs; API reference entry; `uv run mkdocs build --strict` passes | MySQLConfig already exported and guide exists; index.md omission is the remaining gap |
</phase_requirements>

## Summary

Phase 14 is a targeted documentation edit with no library research required. The CONTEXT.md locks all structural decisions. The sole task is to edit `docs/src/index.md` in two places:

1. The ADBC drivers install table — add ClickHouse and MySQL rows in the correct positions within the Foundry group
2. The "First pool" config class list — add `ClickHouseConfig` and `MySQLConfig` in the correct alphabetical positions

Both warehouses already have guide pages (`docs/src/guides/clickhouse.md` and `docs/src/guides/mysql.md`). Both config classes are already exported from `__init__.py`. The gap is exclusively in `docs/src/index.md`.

After editing `index.md`, REQUIREMENTS.md must be updated to mark MYSQL-05 `[x]` Complete and update CH-05 traceability.

**Primary recommendation:** One-plan phase. Edit index.md, update REQUIREMENTS.md, run `uv run mkdocs build --strict`.

## Current State of index.md

### ADBC Drivers Install Table (current)

The table currently has 10 rows in one flat group — PyPI drivers with `pip install` commands and Foundry drivers with `Foundry-distributed — see [Foundry installation](guides/X.md)` cells. MySQL and ClickHouse are absent.

Current rows:
- DuckDB — `pip install adbc-poolhouse[duckdb]`
- Snowflake — `pip install adbc-poolhouse[snowflake]`
- BigQuery — `pip install adbc-poolhouse[bigquery]`
- PostgreSQL — `pip install adbc-poolhouse[postgresql]`
- Apache Arrow Flight SQL — `pip install adbc-poolhouse[flightsql]`
- SQLite — `pip install adbc-poolhouse[sqlite]`
- Databricks — Foundry-distributed
- Redshift — Foundry-distributed
- Trino — Foundry-distributed
- MSSQL / Azure SQL / Fabric — Foundry-distributed

### Config Class List (current)

Current prose lists 10 config classes in one flat inline list:
`DuckDBConfig`, `SQLiteConfig`, `SnowflakeConfig`, `BigQueryConfig`, `PostgreSQLConfig`, `FlightSQLConfig`, `DatabricksConfig`, `RedshiftConfig`, `TrinoConfig`, `MSSQLConfig`

MySQL and ClickHouse are absent.

## What Must Change

### Install Table — Add 2 Rows

Add to the Foundry group, alphabetically:
- `ClickHouse` → `Foundry-distributed — see [Foundry installation](guides/clickhouse.md)`
- `MySQL` → `Foundry-distributed — see [Foundry installation](guides/mysql.md)`

The CONTEXT.md decision to reorganize into two groups (PyPI first, Foundry second with a separator) is a structural improvement that happens simultaneously with adding the two rows.

### Config Class List — Add 2 Class Names

Replace the current 10-class flat list with the two-group structure from CONTEXT.md:

PyPI configs (alphabetical): `BigQueryConfig`, `DuckDBConfig`, `FlightSQLConfig`, `PostgreSQLConfig`, `SnowflakeConfig`, `SQLiteConfig`

Foundry configs (alphabetical): `ClickHouseConfig`, `DatabricksConfig`, `MSSQLConfig`, `MySQLConfig`, `RedshiftConfig`, `TrinoConfig`

### REQUIREMENTS.md — Mark 2 Requirements Complete

- MYSQL-05: change `- [ ]` to `- [x]`
- CH-05: change `- [ ]` to `- [x]`
- Update traceability table entries for both to show "Complete"
- Update `Last updated` footer line

## Architecture Patterns

### Foundry Table Cell Format

Exact pattern used by existing rows (verified from current index.md):
```
Foundry-distributed — see [Foundry installation](guides/X.md)
```

Where `X` is the guide name: `databricks`, `redshift`, `trino`, `mssql`, `clickhouse`, `mysql`.

### Two-Group Table Structure

CONTEXT.md prescribes grouping. Two approaches are both valid:

**Option A — Sub-headers (recommended for discoverability):**
```markdown
| Warehouse | Install command |
|---|---|
| **PyPI drivers** | |
| BigQuery | `pip install adbc-poolhouse[bigquery]` |
| ... | ... |
| **Foundry-distributed drivers** | |
| ClickHouse | Foundry-distributed — see [Foundry installation](guides/clickhouse.md) |
| ... | ... |
```

**Option B — Flat table, alphabetical within groups (simpler):**
No visual separators; PyPI rows first (alphabetical), Foundry rows second (alphabetical), no sub-headers.

Either is acceptable per CONTEXT.md's Claude's Discretion note. Sub-headers improve scannability.

### Config Class List Grouping

Current format is a single inline comma-separated list. The new list should mirror the two-group structure. Two options:

**Option A — Two lines in prose:**
```
PyPI-installed: `BigQueryConfig`, `DuckDBConfig`, `FlightSQLConfig`, `PostgreSQLConfig`, `SnowflakeConfig`, `SQLiteConfig`.
Foundry-distributed: `ClickHouseConfig`, `DatabricksConfig`, `MSSQLConfig`, `MySQLConfig`, `RedshiftConfig`, `TrinoConfig`.
```

**Option B — Continued inline comma list with a grouping note:**
All 12 config classes in one list, alphabetical, with a sentence noting which are Foundry-distributed.

Per CONTEXT.md decisions, grouping must mirror the table. Option A is cleaner and directly mirrors the table structure.

## Common Pitfalls

### Pitfall 1: Wrong Foundry guide path for ClickHouse
The clickhouse guide is at `guides/clickhouse.md`. Do NOT use `guides/foundry.md` or any generic path.

### Pitfall 2: ClickHouse `--pre` flag on homepage
CONTEXT.md explicitly locks: "Alpha details for ClickHouse (including `--pre` flag) stay in the ClickHouse guide, not the homepage table." Homepage cell uses the standard Foundry-distributed format only.

### Pitfall 3: mkdocs build failure on broken links
After editing, run `uv run mkdocs build --strict` to catch any broken Markdown link targets. The link text `[Foundry installation](guides/clickhouse.md)` must resolve correctly relative to `docs/src/`.

### Pitfall 4: REQUIREMENTS.md last-updated line
The last line includes a timestamp. Update it to today's date (2026-03-02) when marking MYSQL-05 and CH-05 complete.

## Sources

### Primary (HIGH confidence)
- `docs/src/index.md` — direct file read, current state verified
- `docs/src/guides/mysql.md` — confirmed guide exists and uses `guides/mysql.md` path
- `docs/src/guides/clickhouse.md` — confirmed guide exists, confirms `--pre` flag stays in guide
- `.planning/REQUIREMENTS.md` — MYSQL-05 and CH-05 confirmed as `[ ]` open
- `.planning/phases/14-homepage-discovery-fix/14-CONTEXT.md` — all locked decisions read directly

## Metadata

**Confidence breakdown:**
- What to change: HIGH — direct file inspection of current index.md state
- Where to change: HIGH — CONTEXT.md locks all structural decisions
- Pitfalls: HIGH — derived from locked decisions and existing patterns

**Research date:** 2026-03-02
**Valid until:** Implementation date (static file edits, no moving targets)
