---
phase: quick-9
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - DEVELOP.md
  - README.md
autonomous: true
requirements: [DOC-FIX]

must_haves:
  truths:
    - "DEVELOP.md references pytest-adbc-replay cassettes, not syrupy snapshots"
    - "README.md lists all 12 supported warehouses"
    - "README.md line 15 mentions SQLite alongside the other PyPI extras"
    - "mkdocs build --strict still passes"
  artifacts:
    - path: "DEVELOP.md"
      provides: "Updated Snowflake integration tests section"
      contains: "--adbc-record=once"
    - path: "README.md"
      provides: "Complete warehouse list"
      contains: "SQLite"
  key_links: []
---

<objective>
Fix three documentation gaps: stale syrupy references in DEVELOP.md, and missing backends in README.md.

Note: docs/src/index.md was listed as needing a FlightSQL addition, but inspection shows it already lists all 12 backends (6 PyPI + 6 Foundry). No changes needed there.

Purpose: Keep developer-facing docs accurate after the Phase 15 syrupy-to-cassettes migration and the Phase 10-12 backend additions.
Output: Corrected DEVELOP.md and README.md.
</objective>

<execution_context>
@.claude/skills/adbc-poolhouse-docs-author/SKILL.md
</execution_context>

<context>
@DEVELOP.md
@README.md
@CONTRIBUTING.md (has correct cassette recording pattern to mirror)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix stale syrupy references in DEVELOP.md and missing backends in README.md</name>
  <files>DEVELOP.md, README.md</files>
  <action>
**DEVELOP.md** — Replace lines 140-152 (the "Snowflake integration tests" subsection) with updated content that matches the pytest-adbc-replay cassette workflow. The section title stays "Snowflake integration tests". The corrected content:

```
### Snowflake integration tests

Tests requiring real credentials are gated behind the `snowflake` pytest marker and excluded from default runs.

\```bash
# Run Snowflake tests (requires SNOWFLAKE_* env vars)
uv run pytest --override-ini="addopts=" -m snowflake

# Record or update cassettes
uv run pytest --override-ini="addopts=" -m snowflake --adbc-record=once
\```

Cassettes are committed to `tests/cassettes/` and replayed in CI without credentials.
```

Key changes:
- Line 148 comment: "Record or update snapshots" becomes "Record or update cassettes"
- Line 149 flag: `--snapshot-update` becomes `--adbc-record=once`
- Line 152: "Snapshots are committed to `tests/`" becomes "Cassettes are committed to `tests/cassettes/`"

**README.md** — Two edits:

1. Line 15: Change the parenthetical from `(DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL)` to `(DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, SQLite)`. Add "and more" or just add SQLite to the list. The full sentence should read:
   ```
   Driver extras are available for each supported warehouse (BigQuery, DuckDB, FlightSQL, PostgreSQL, Snowflake, SQLite). See the [documentation](https://anentropic.github.io/adbc-poolhouse/) for the full list.
   ```
   List alphabetically to match docs/src/index.md table order.

2. Lines 39-49: Replace the "Supported warehouses" list with the full 12-backend list, organized into PyPI and Foundry groups:
   ```
   ## Supported warehouses

   **PyPI drivers:** BigQuery, DuckDB, FlightSQL, PostgreSQL, Snowflake, SQLite

   **Foundry-distributed drivers:** ClickHouse, Databricks, MSSQL / Azure SQL / Fabric, MySQL, Redshift, Trino
   ```
   This replaces the existing bullet list with a more compact format that clearly distinguishes PyPI from Foundry drivers, matching the structure in docs/src/index.md.
  </action>
  <verify>
    <automated>cd /Users/paul/Documents/Dev/Personal/adbc-poolhouse && grep -q "adbc-record=once" DEVELOP.md && grep -q "cassettes" DEVELOP.md && grep -q "SQLite" README.md && grep -q "ClickHouse" README.md && grep -q "MySQL" README.md && echo "All checks passed"</automated>
  </verify>
  <done>
    - DEVELOP.md lines 148-152 reference `--adbc-record=once` and cassettes (not syrupy snapshots)
    - README.md line 15 lists all 6 PyPI extras including SQLite
    - README.md supported warehouses section lists all 12 backends
    - No syrupy or --snapshot-update references remain in DEVELOP.md
  </done>
</task>

</tasks>

<verification>
- `grep -c "snapshot-update\|syrupy" DEVELOP.md` returns 0 (no stale references)
- `grep -c "SQLite" README.md` returns at least 1
- `grep -c "ClickHouse" README.md` returns at least 1
- `grep -c "MySQL" README.md` returns at least 1
- `uv run mkdocs build --strict` passes (README.md is not part of mkdocs, but run anyway to confirm no regressions)
</verification>

<success_criteria>
DEVELOP.md and README.md are accurate and consistent with docs/src/index.md and CONTRIBUTING.md. All 12 backends documented. No stale syrupy references remain.
</success_criteria>

<output>
After completion, create `.planning/quick/9-fix-docs-gaps-develop-md-stale-syrupy-re/9-SUMMARY.md`
</output>
