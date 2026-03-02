---
phase: 14-homepage-discovery-fix
plan: "14-01"
subsystem: docs
tags: [mkdocs, index, homepage, discovery, mysql, clickhouse]

requires: []
provides:
  - "docs/src/index.md ADBC drivers table restructured into PyPI and Foundry groups with sub-headers"
  - "ClickHouse row added to Foundry group linking to guides/clickhouse.md"
  - "MySQL row added to Foundry group linking to guides/mysql.md"
  - "Config class list updated to two-group structure (12 classes: 6 PyPI + 6 Foundry)"
  - "REQUIREMENTS.md MYSQL-05 and CH-05 marked complete"
affects: []

tech-stack:
  added: []
  patterns:
    - "Two-group table structure: bold sub-header rows separate PyPI and Foundry sections"
    - "Config class list mirrors table grouping: PyPI group then Foundry group, both alphabetical"

key-files:
  created: []
  modified:
    - docs/src/index.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "ClickHouse --pre flag stays in clickhouse.md guide only, not mentioned on homepage table"
  - "Sub-headers within table (bold rows with empty second column) used to separate PyPI and Foundry groups"
  - "Config class list rewritten as two separate sentences (PyPI group, Foundry group) mirroring table"

patterns-established:
  - "Three doc surfaces updated for every new backend: warehouse guide, configuration.md env_prefix table, index.md install table + config class list"

requirements-completed:
  - CH-05
  - MYSQL-05

duration: 5min
completed: 2026-03-02
---

# Phase 14: Homepage Discovery Fix Summary

**Added MySQL and ClickHouse to the homepage driver table and config class list, restructuring both into PyPI and Foundry groups.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-02T00:00:00Z
- **Completed:** 2026-03-02T00:00:00Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

### ADBC Drivers Install Table Restructured

Replaced the flat 10-row driver table with a two-group structure:

- **PyPI drivers group** (6 rows, alphabetical): Apache Arrow Flight SQL, BigQuery, DuckDB, PostgreSQL, Snowflake, SQLite
- **Foundry-distributed drivers group** (6 rows, alphabetical): ClickHouse, Databricks, MSSQL/Azure SQL/Fabric, MySQL, Redshift, Trino

ClickHouse and MySQL were absent before this change. Both now appear with the standard Foundry cell format: `Foundry-distributed — see [Foundry installation](guides/X.md)`.

### Config Class List Updated

The "First pool" section config class list was rewritten from a flat 10-class inline list to a two-group structure matching the table:

- PyPI-installed: `BigQueryConfig`, `DuckDBConfig`, `FlightSQLConfig`, `PostgreSQLConfig`, `SnowflakeConfig`, `SQLiteConfig`
- Foundry-distributed: `ClickHouseConfig`, `DatabricksConfig`, `MSSQLConfig`, `MySQLConfig`, `RedshiftConfig`, `TrinoConfig`

### REQUIREMENTS.md Updated

- MYSQL-05 checkbox: `[ ]` → `[x]` Complete
- CH-05 checkbox: `[ ]` → `[x]` Complete
- Traceability table: both rows updated from Pending to Complete
- Last updated footer updated with Phase 14 note

### Build Verified

`uv run mkdocs build --strict` passes with exit 0. Pre-existing INFO messages about `reference/` links are unrelated to this change.

## Issues Encountered

None.
