---
phase: 14-homepage-discovery-fix
status: passed
verified: 2026-03-02
requirements: [CH-05, MYSQL-05]
---

# Phase 14: Homepage Discovery Fix — Verification

**Goal:** ClickHouseConfig and MySQLConfig are discoverable by new users landing on the homepage — both appear in the ADBC drivers install table and "First pool" config class list on index.md

**Verification Status:** PASSED

## Must-Haves Verification

### Truths

| Truth | Status | Evidence |
|-------|--------|---------|
| docs/src/index.md ADBC drivers install table contains a ClickHouse row pointing to guides/clickhouse.md | VERIFIED | `grep "ClickHouse.*guides/clickhouse.md" docs/src/index.md` → match on line 31 |
| docs/src/index.md ADBC drivers install table contains a MySQL row pointing to guides/mysql.md | VERIFIED | `grep "MySQL.*guides/mysql.md" docs/src/index.md` → match on line 34 |
| docs/src/index.md "First pool" config class list includes ClickHouseConfig and MySQLConfig in the Foundry group | VERIFIED | `grep "ClickHouseConfig\|MySQLConfig" docs/src/index.md` → line 44 shows both in Foundry group |
| uv run mkdocs build --strict exits 0 after changes | VERIFIED | Build exits 0 in 1.23 seconds; no ERRORs or WARNINGs |
| REQUIREMENTS.md shows [x] Complete for MYSQL-05 and CH-05 | VERIFIED | Both checkboxes [x]; traceability table shows Complete for both |

### Artifacts

| Artifact | Status | Evidence |
|----------|--------|---------|
| docs/src/index.md | VERIFIED | File exists; restructured table with PyPI (6 rows) and Foundry (6 rows) groups; config class list with 12 classes in two groups |
| .planning/REQUIREMENTS.md | VERIFIED | MYSQL-05 and CH-05 both marked [x]; traceability table Complete |

### Key Links

| Link | Status | Evidence |
|------|--------|---------|
| docs/src/index.md → guides/clickhouse.md | VERIFIED | `[Foundry installation](guides/clickhouse.md)` present on line 31 |
| docs/src/index.md → guides/mysql.md | VERIFIED | `[Foundry installation](guides/mysql.md)` present on line 34 |

## Success Criteria (from ROADMAP)

1. `docs/src/index.md` ADBC drivers install table includes rows for MySQL and ClickHouse with correct `dbc install` commands — **VERIFIED** (Foundry-distributed cell format, links to correct guide pages)
2. `docs/src/index.md` "First pool" config class list includes `MySQLConfig` and `ClickHouseConfig` — **VERIFIED** (both in Foundry group on line 44)
3. `uv run mkdocs build --strict` passes after changes — **VERIFIED** (exit 0)
4. REQUIREMENTS.md shows `[x]` Complete for MYSQL-05; CH-05 traceability updated — **VERIFIED** (both complete in checkboxes and traceability table)

## Requirement Coverage

| ID | Description (abbreviated) | Status |
|----|---------------------------|--------|
| CH-05 | ClickHouseConfig exported; guide exists; API reference; mkdocs passes | Complete |
| MYSQL-05 | MySQLConfig exported; guide exists; API reference; mkdocs passes | Complete |

Note: The export from `__init__.py` and guide pages (`guides/clickhouse.md`, `guides/mysql.md`) were completed in Phases 12 and 11 respectively. Phase 14 completes the final gap: the homepage discovery surface.

## Conclusion

Phase 14 achieves its goal. New users landing on the homepage can now discover MySQL and ClickHouse as supported backends. The ADBC drivers table is restructured into clear PyPI and Foundry groups, making it easy to understand the distinction between pip-installable and Foundry-distributed drivers. Both `MySQLConfig` and `ClickHouseConfig` appear in the config class list.
