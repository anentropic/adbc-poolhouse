---
phase: 02-dependency-declarations
verified: 2026-02-24T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 2: Dependency Declarations Verification Report

**Phase Goal:** All runtime and dev dependencies are declared in pyproject.toml, version-resolved with uv, and the lock file reflects the complete dependency graph
**Verified:** 2026-02-24
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from Success Criteria + Plan must_haves)

| #  | Truth                                                                                                                         | Status     | Evidence                                                                                                              |
|----|-------------------------------------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------------|
| 1  | `uv sync` succeeds with new lock file — pydantic-settings, sqlalchemy, adbc-driver-manager, syrupy, and coverage resolvable  | VERIFIED   | `uv sync --all-extras` resolves 82 packages, exits 0; all named packages confirmed in uv.lock                        |
| 2  | `pip install adbc-poolhouse[duckdb]` installs only the DuckDB extra (no other warehouse drivers)                             | VERIFIED   | `uv sync --extra duckdb --no-dev` installs duckdb only; grep for snowflake/postgresql/flightsql/bigquery: none found  |
| 3  | `pip install adbc-poolhouse[snowflake]` installs only the Snowflake extra                                                    | VERIFIED   | `uv sync --extra snowflake --no-dev` + `uv pip list` shows only adbc-driver-snowflake; no other warehouse drivers     |
| 4  | `pip install adbc-poolhouse[all]` installs all warehouse extras                                                               | VERIFIED   | `uv sync --all-extras` installs all five drivers; `[all]` uses self-referencing `adbc-poolhouse[extra]` pattern       |
| 5  | pyproject.toml has three runtime deps with open lower bounds (pydantic-settings>=2.0.0, sqlalchemy>=2.0.0, adbc-driver-manager>=1.0.0) | VERIFIED | tomllib parse confirms exact strings; no `>=X,<Y` ranges found anywhere in dep declarations                          |
| 6  | pyproject.toml has five optional extras plus [all] meta-extra using self-referencing pattern                                  | VERIFIED   | Six entries in `[project.optional-dependencies]`: duckdb, snowflake, postgresql, flightsql, bigquery, all; all use `adbc-poolhouse[extra]` in [all] |
| 7  | pyproject.toml [dependency-groups] dev includes syrupy>=4.0 and coverage[toml]                                               | VERIFIED   | Both present in dev list confirmed by tomllib parse                                                                    |
| 8  | REQUIREMENTS.md SETUP-02 reflects open-lower-bound constraint style (not >=X,<Y)                                             | VERIFIED   | Line 13 reads "open lower bounds only — no upper bound caps"; no `<Y` in SETUP-02 text                               |
| 9  | REQUIREMENTS.md SETUP-03 reflects PyPI-only extras with Foundry backends explicitly deferred                                 | VERIFIED   | Line 14 explicitly names Foundry backends (Databricks, Redshift, Trino, MSSQL, Teradata) as deferred to Phase 7      |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact                  | Expected                                                              | Status     | Details                                                                                                |
|---------------------------|-----------------------------------------------------------------------|------------|--------------------------------------------------------------------------------------------------------|
| `pyproject.toml`          | Runtime deps, optional extras, dev dep additions                      | VERIFIED   | All declarations present; TOML parses cleanly; no upper-bound violations                               |
| `uv.lock`                 | Universal cross-platform lock covering all optional warehouse driver deps | VERIFIED | 1603 lines, 82 packages; committed in `2044700`; contains all five warehouse driver names              |
| `.planning/REQUIREMENTS.md` | Corrected SETUP-02 and SETUP-03 descriptions                        | VERIFIED   | Both lines updated and checked; SETUP-02, SETUP-03, SETUP-04 all marked `[x]` and traceability shows Complete |

---

### Key Link Verification

| From                                          | To                                                      | Via                                          | Status   | Details                                                                          |
|-----------------------------------------------|---------------------------------------------------------|----------------------------------------------|----------|----------------------------------------------------------------------------------|
| `uv.lock`                                     | `pyproject.toml [project.optional-dependencies]`        | uv lock resolution covering all extras       | VERIFIED | `uv sync --frozen` exits 0; lock file encodes all five extras with marker guards |
| `pyproject.toml [project.optional-dependencies] all` | `pyproject.toml [project.optional-dependencies] duckdb/snowflake/postgresql/flightsql/bigquery` | self-referencing `adbc-poolhouse[extra]` pattern | VERIFIED | All five `adbc-poolhouse[extra]` references present in the `[all]` list          |

---

### Requirements Coverage

| Requirement | Source Plans  | Description                                                                   | Status    | Evidence                                                                                                 |
|-------------|---------------|-------------------------------------------------------------------------------|-----------|----------------------------------------------------------------------------------------------------------|
| SETUP-02    | 02-01, 02-02  | Runtime dependencies declared in pyproject.toml with open lower bounds        | SATISFIED | `pydantic-settings>=2.0.0`, `sqlalchemy>=2.0.0`, `adbc-driver-manager>=1.0.0` present; no upper bounds  |
| SETUP-03    | 02-01, 02-02  | Per-warehouse optional extras for PyPI-available drivers; Foundry deferred    | SATISFIED | Five extras declared; `[all]` meta-extra present; REQUIREMENTS.md updated to reflect scope               |
| SETUP-04    | 02-01, 02-02  | syrupy>=4.0 and coverage[toml] added to dev dependencies                      | SATISFIED | Both present in `[dependency-groups] dev`; confirmed by tomllib parse                                    |

No orphaned requirements found. All three requirement IDs from both PLAN frontmatter entries are satisfied with implementation evidence.

---

### Anti-Patterns Found

None. No TODO/FIXME/placeholder comments, empty implementations, or stub patterns found in pyproject.toml or uv.lock.

---

### Human Verification Required

None. All success criteria for this phase are mechanically verifiable:
- `uv sync` exit codes verified live
- Package declarations verified by TOML parse
- Extras isolation confirmed by inspecting installed packages after single-extra syncs
- Lock file contents verified by grep

---

### Additional Notes

**ROADMAP.md plan checkboxes not updated:** Lines 50-51 in ROADMAP.md still show `[ ]` for both `02-01-PLAN.md` and `02-02-PLAN.md`. The phase-level entry on line 16 correctly shows `[x]` and "completed 2026-02-23". The plan-level checkboxes are a minor documentation gap; they do not affect goal achievement and the code artifacts are fully verified.

**`uv sync --frozen` (CI gate):** Exits 0 — the lock file is consistent with pyproject.toml and ready for CI enforcement via `uv sync --frozen`.

---

## Summary

Phase 2 goal fully achieved. All three runtime dependencies, five optional warehouse extras, one `[all]` meta-extra, and two dev dependencies are declared in `pyproject.toml` with open lower bounds. The `uv.lock` file (1603 lines, 82 packages) is committed to git and reflects the complete dependency graph. Extras isolation is confirmed — installing a single warehouse extra does not pull in unrelated warehouse drivers. The CI-equivalent frozen sync (`uv sync --frozen`) exits 0. REQUIREMENTS.md accurately documents the constraint style and extras scope decisions. All three phase requirements (SETUP-02, SETUP-03, SETUP-04) are satisfied.

---

_Verified: 2026-02-24_
_Verifier: Claude (gsd-verifier)_
