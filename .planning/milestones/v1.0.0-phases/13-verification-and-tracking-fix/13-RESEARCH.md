# Phase 13: Verification and Tracking Fix — Research

**Researched:** 2026-03-02
**Domain:** Planning documentation — VERIFICATION.md authoring, SUMMARY.md frontmatter, REQUIREMENTS.md tracking, justfile fix
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SQLT-01 | `SQLiteConfig` — Pydantic `BaseSettings`; `env_prefix="SQLITE_"`; `model_validator` raises `ValueError` for `uri=":memory:"` with `pool_size > 1` | Code confirmed in `_sqlite_config.py`; Phase 10 VERIFICATION.md is the tracking artifact needed |
| SQLT-02 | `translate_sqlite()` — pure function mapping `SQLiteConfig` fields to adbc_driver_manager kwargs | Code confirmed in `_sqlite_translator.py`; Phase 10 VERIFICATION.md is the tracking artifact needed |
| SQLT-03 | `sqlite` optional extra in pyproject.toml; included in `[all]` meta-extra; uv.lock updated | Confirmed in pyproject.toml and uv.lock; Phase 10 VERIFICATION.md is the tracking artifact needed |
| SQLT-04 | Unit tests for `SQLiteConfig` validation; unit tests for `translate_sqlite()` asserting exact kwargs dict; mock-at-`create_adbc_connection` test; integration test | 13 tests passing confirmed in 10-03-SUMMARY.md; Phase 10 VERIFICATION.md is the tracking artifact needed |
| SQLT-05 | `SQLiteConfig` exported from `__init__.py`; SQLite warehouse guide; API reference entry; `uv run mkdocs build --strict` passes | Listed in 10-04-SUMMARY.md requirements-completed; still shows Pending in REQUIREMENTS.md — needs checkbox update |
| DBC-02 | `justfile` recipe `install-foundry-drivers` — runs `dbc install mysql clickhouse` with `--level env` to scope drivers to active virtualenv | Current recipe uses `dbc install clickhouse` without `--pre`; ClickHouse is alpha (v0.1.0-alpha.1); `--pre` flag required |
</phase_requirements>

---

## Summary

Phase 13 is a pure documentation and tracking repair phase. All six requirements (SQLT-01 through SQLT-05 and DBC-02) have working code already in the repository — the v1.0 milestone audit confirmed this explicitly. The gaps are entirely in the planning tracking system: missing VERIFICATION.md files for Phases 10 and 11, missing `requirements-completed` frontmatter in three SUMMARY.md files, unchecked REQUIREMENTS.md checkboxes, and one broken justfile recipe.

The work is well-scoped. One plan (13-01) covers five discrete tasks: fix the justfile, patch three SUMMARY.md frontmatter blocks, tick five checkboxes in REQUIREMENTS.md, create Phase 10 VERIFICATION.md, and create Phase 11 VERIFICATION.md. The VERIFICATION.md authoring is the most substantial task — it requires reading the actual source files to confirm truths rather than fabricating them. The existing Phase 12 VERIFICATION.md is the canonical format template.

No new code is written in this phase. No library research is needed. The domain is entirely internal planning documentation — the patterns are established and the evidence base (code, tests, prior SUMMARYs) is fully available in the repository.

**Primary recommendation:** Follow the Phase 12 VERIFICATION.md format exactly. Verify truths by reading actual source files rather than relying solely on SUMMARY prose. All five SQLT requirements and the four audited DBC-01/DBC-03/MYSQL-01–04 requirements are code-confirmed — write VERIFICATION.md to record that evidence.

---

## Standard Stack

### Core

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| YAML frontmatter | Project convention | SUMMARY.md requirements-completed field | Established pattern in 10-04-SUMMARY.md and all Phase 11 SUMMARYs |
| Markdown | N/A | VERIFICATION.md format | Phase 9, 12 VERIFICATION.md files are the template |
| justfile | Project-installed | Foundry driver install recipe | Already used for install-dbc and install-foundry-drivers |

### No Installation Required

This phase installs nothing new. No `npm install`, `uv add`, or `dbc install` commands.

---

## Architecture Patterns

### VERIFICATION.md Structure

The canonical format is established by `12-VERIFICATION.md` (17/17 truths) and `09-VERIFICATION.md` (11/11 truths). Both use:

```
---
phase: {phase-slug}
verified: {ISO datetime}
status: passed | human_needed
score: N/N must-haves verified
re_verification: false
---

# Phase N: Name — Verification Report

## Goal Achievement
### Observable Truths
| # | Truth | Status | Evidence |

## Required Artifacts
| Artifact | Expected | Status | Details |

## Key Link Verification
| From | To | Via | Status | Details |

## Requirements Coverage
| Requirement | Source Plan | Description | Status | Evidence |

## Anti-Patterns Found

## Human Verification Required (optional)

## Gaps Summary
```

**Key principle:** Truths are verified by reading actual source files, not by trusting SUMMARY prose. For Phase 10, this means reading `_sqlite_config.py`, `_sqlite_translator.py`, `_drivers.py`, `_translators.py`, `__init__.py`, test files, and `docs/src/guides/sqlite.md` to confirm each truth.

### SUMMARY.md Frontmatter Pattern

Three Phase 10 SUMMARY files are missing `requirements-completed`. The established pattern (from 10-04-SUMMARY.md and all Phase 11 SUMMARYs) is:

```yaml
---
plan: 10-01
phase: 10-sqlite-backend
status: complete
completed: 2026-03-01
requirements-completed:
  - SQLT-01
  - SQLT-02
---
```

The `requirements-completed` field is a YAML list of requirement IDs delivered by that specific plan.

**Mapping to apply:**
- 10-01-SUMMARY.md: add `requirements-completed: [SQLT-01, SQLT-02]` (SQLiteConfig + translate_sqlite())
- 10-02-SUMMARY.md: add `requirements-completed: [SQLT-03]` (sqlite extra in pyproject.toml)
- 10-03-SUMMARY.md: add `requirements-completed: [SQLT-04]` (full SQLite test suite)

### REQUIREMENTS.md Checkbox Pattern

Five checkboxes to change from `[ ]` to `[x]` in the SQLite section. The traceability table also needs its `Status` column entries changed from `Pending` to `Complete` for SQLT-01 through SQLT-05.

**Current state (from REQUIREMENTS.md):**
```markdown
- [ ] **SQLT-01**: `SQLiteConfig` ...
- [ ] **SQLT-02**: `translate_sqlite()` ...
- [ ] **SQLT-03**: `sqlite` optional extra ...
- [ ] **SQLT-04**: Unit tests ...
- [ ] **SQLT-05**: `SQLiteConfig` exported ...
```

**Target state:**
```markdown
- [x] **SQLT-01**: `SQLiteConfig` ...
- [x] **SQLT-02**: `translate_sqlite()` ...
- [x] **SQLT-03**: `sqlite` optional extra ...
- [x] **SQLT-04**: Unit tests ...
- [x] **SQLT-05**: `SQLiteConfig` exported ...
```

Traceability table rows for SQLT-01 through SQLT-05 currently show `Phase 13 | Pending` — these should be updated to `Phase 10 | Complete` once the VERIFICATION.md is created (the requirements belong to Phase 10, not Phase 13).

### justfile --pre Flag Fix

The ClickHouse Foundry driver is currently only available as an alpha release (`v0.1.0-alpha.1`). The `dbc` CLI requires the `--pre` flag to install pre-release packages. The guide at `docs/src/guides/clickhouse.md` already uses `--pre`; the justfile does not.

**Current justfile (lines 25-27):**
```just
install-foundry-drivers:
    dbc install mysql
    dbc install clickhouse
```

**Target state:**
```just
install-foundry-drivers:
    dbc install mysql
    dbc install --pre clickhouse
```

Only the `clickhouse` line needs `--pre`. MySQL is available as a stable release.

---

## What the Plan Must Build

### Task 1: Fix justfile DBC-02 (closes DBC-02)

Edit `justfile` to add `--pre` flag on the `dbc install clickhouse` line. Also update the comment to note `--pre` required for ClickHouse alpha driver.

### Task 2: Update Phase 10 SUMMARY.md frontmatter (closes SQLT-01–04 tracking)

Add `requirements-completed` YAML lists to three files:
- `.planning/phases/10-sqlite-backend/10-01-SUMMARY.md`: `[SQLT-01, SQLT-02]`
- `.planning/phases/10-sqlite-backend/10-02-SUMMARY.md`: `[SQLT-03]`
- `.planning/phases/10-sqlite-backend/10-03-SUMMARY.md`: `[SQLT-04]`

Note: 10-04-SUMMARY.md already has `requirements-completed: [SQLT-05]` — no change needed.

### Task 3: Update REQUIREMENTS.md (closes all checkbox gaps)

- Change SQLT-01 through SQLT-05 checkboxes from `[ ]` to `[x]`
- Update traceability table: SQLT-01–SQLT-05 rows should reference `Phase 10` and `Complete` status
- DBC-02 in REQUIREMENTS.md already shows `[ ]` — needs to become `[x]` once DBC-02 is verified (justfile fixed)

### Task 4: Create Phase 10 VERIFICATION.md

File: `.planning/phases/10-sqlite-backend/10-VERIFICATION.md`

Must verify these truths (derived from Phase 10 success criteria and SQLT requirements):

| # | Truth to verify | Source file to read |
|---|----------------|---------------------|
| 1 | `SQLiteConfig` exists in `_sqlite_config.py` with `env_prefix="SQLITE_"` | `src/adbc_poolhouse/_sqlite_config.py` |
| 2 | `SQLiteConfig(database=":memory:", pool_size=2)` raises `ValidationError` (in-memory guard) | `_sqlite_config.py` model_validator |
| 3 | `translate_sqlite()` returns `{"uri": config.database}` — uses `"uri"` key | `src/adbc_poolhouse/_sqlite_translator.py` |
| 4 | `_adbc_entrypoint()` returns `"AdbcDriverSqliteInit"` (PascalCase, not snake_case) | `_sqlite_config.py` |
| 5 | `SQLiteConfig` is in `_PYPI_PACKAGES` in `_drivers.py` (not `_FOUNDRY_DRIVERS`) | `src/adbc_poolhouse/_drivers.py` |
| 6 | `translate_config()` dispatches to `translate_sqlite()` in `_translators.py` | `src/adbc_poolhouse/_translators.py` |
| 7 | `from adbc_poolhouse import SQLiteConfig` succeeds; `'SQLiteConfig' in __all__` is True | `src/adbc_poolhouse/__init__.py` |
| 8 | `sqlite = ["adbc-driver-sqlite>=1.0.0"]` optional extra in `pyproject.toml` | `pyproject.toml` |
| 9 | `adbc-driver-sqlite` in `[all]` meta-extra | `pyproject.toml` |
| 10 | `adbc-driver-sqlite` in dev dependency group | `pyproject.toml` |
| 11 | `TestSQLiteConfig` class with 8 tests in `tests/test_configs.py` | `tests/test_configs.py` |
| 12 | `TestSQLiteTranslator` class with 3 tests in `tests/test_translators.py` | `tests/test_translators.py` |
| 13 | `TestSQLitePoolFactory` class with 2 tests in `tests/test_pool_factory.py` | `tests/test_pool_factory.py` |
| 14 | `docs/src/guides/sqlite.md` exists with content | `docs/src/guides/sqlite.md` |
| 15 | `mkdocs.yml` contains SQLite nav entry under Warehouse Guides | `mkdocs.yml` |
| 16 | `configuration.md` env_prefix table includes `SQLiteConfig / SQLITE_` | `docs/src/guides/configuration.md` |
| 17 | `docs/src/index.md` includes SQLite in install table and config class list | `docs/src/index.md` |

### Task 5: Create Phase 11 VERIFICATION.md

File: `.planning/phases/11-foundry-tooling-and-mysql-backend/11-VERIFICATION.md`

Must verify these truths:

**DBC-01/02/03 (justfile + DEVELOP.md):**

| # | Truth to verify | Source file |
|---|----------------|-------------|
| 1 | `install-dbc` recipe exists in justfile with `command -v dbc` guard | `justfile` |
| 2 | `install-foundry-drivers` recipe exists (note: DBC-02 is pending justfile --pre fix in this same phase) | `justfile` |
| 3 | DEVELOP.md contains Foundry Driver Management section | `DEVELOP.md` |

**MYSQL-01/02/03/04 (MySQLConfig + translate_mysql() + wiring + tests):**

| # | Truth to verify | Source file |
|---|----------------|-------------|
| 4 | `MySQLConfig` exists in `_mysql_config.py` with `env_prefix="MYSQL_"` | `src/adbc_poolhouse/_mysql_config.py` |
| 5 | `MySQLConfig` URI-first mode: `MySQLConfig(uri="...")` constructs | `_mysql_config.py` model_validator |
| 6 | `MySQLConfig` decomposed mode: `MySQLConfig(host=..., user=..., database=...)` constructs | `_mysql_config.py` |
| 7 | `MySQLConfig()` with no args raises `ConfigurationError` | `_mysql_config.py` |
| 8 | `translate_mysql()` returns `{"uri": ...}` with Go DSN format | `src/adbc_poolhouse/_mysql_translator.py` |
| 9 | `MySQLConfig` in `_FOUNDRY_DRIVERS` as `("mysql", "mysql")` | `src/adbc_poolhouse/_drivers.py` |
| 10 | `translate_config()` dispatches to `translate_mysql()` | `src/adbc_poolhouse/_translators.py` |
| 11 | `from adbc_poolhouse import MySQLConfig` succeeds | `src/adbc_poolhouse/__init__.py` |
| 12 | `TestMySQLConfig` (9 tests), `TestMySQLTranslator` (6 tests), `TestMySQLPoolFactory` (1 test) | test files |
| 13 | `docs/src/guides/mysql.md` exists | `docs/src/guides/mysql.md` |
| 14 | `configuration.md` includes `MySQLConfig / MYSQL_` row | `docs/src/guides/configuration.md` |
| 15 | `mkdocs.yml` has MySQL nav entry | `mkdocs.yml` |

**MYSQL-05 handling note:** MYSQL-05 (index.md homepage entries) was claimed completed by 11-04-SUMMARY.md but the audit found MySQLConfig absent from `docs/src/index.md`. This gap is assigned to Phase 14, not Phase 13. The Phase 11 VERIFICATION.md should note MYSQL-05 as "pending Phase 14 gap closure" rather than SATISFIED.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| VERIFICATION.md format | Custom format | Phase 12 and Phase 9 VERIFICATION.md templates | Consistent format is what the audit process reads |
| Requirement status tracking | New tracking schema | Existing REQUIREMENTS.md checkbox + traceability table pattern | Already established, just needs checkbox updates |

---

## Common Pitfalls

### Pitfall 1: Fabricating verification evidence
**What goes wrong:** Writing "VERIFIED" in VERIFICATION.md without reading the actual source file — using SUMMARY prose as the evidence source instead of the code.
**Why it happens:** SUMMARY files are easier to read than source files; they claim completion.
**How to avoid:** For every "VERIFIED" in the truths table, cite the actual file path and line number (or content) that was read.
**Warning signs:** Evidence column says "per SUMMARY.md" rather than a file path and line reference.

### Pitfall 2: Wrong phase assignment in traceability table
**What goes wrong:** REQUIREMENTS.md traceability table currently shows SQLT-01–05 assigned to "Phase 13 | Pending". After this phase, they should reference "Phase 10 | Complete" — the phase where the code was actually built.
**Why it happens:** The gap closure phases were created after the fact and assigned as placeholder phases in the traceability table.
**How to avoid:** Update the phase column to "Phase 10" and status to "Complete" for SQLT-01–05. Phase 13 is the verification phase, not the implementation phase.

### Pitfall 3: DBC-02 checkbox in REQUIREMENTS.md
**What goes wrong:** DBC-02 currently shows `[ ]` Pending in REQUIREMENTS.md. It can be marked `[x]` Complete only after the justfile fix is confirmed. Do the justfile fix first, then tick the checkbox.
**Why it happens:** The requirement states `--level env` scoping, but the actual implementation uses automatic VIRTUAL_ENV detection and `--pre` for ClickHouse. The requirement text needs careful reading — the intent is met even if the exact flag differs.
**How to avoid:** Mark DBC-02 complete after confirming the justfile correctly installs Foundry drivers with ClickHouse's `--pre` requirement satisfied.

### Pitfall 4: MYSQL-05 scope creep
**What goes wrong:** Trying to fix the index.md MySQL/ClickHouse homepage entries as part of Phase 13.
**Why it happens:** The audit report lists it as a gap; it's tempting to fix everything at once.
**How to avoid:** MYSQL-05 and CH-05 homepage entries are explicitly assigned to Phase 14 (Homepage Discovery Fix). Phase 13 VERIFICATION.md for Phase 11 should note MYSQL-05 as pending Phase 14 rather than trying to satisfy it here.

### Pitfall 5: Incorrect entrypoint string in VERIFICATION.md
**What goes wrong:** Writing `"adbc_driver_sqlite_init"` (snake_case) in the verification truth when the actual entrypoint is `"AdbcDriverSqliteInit"` (PascalCase).
**Why it happens:** The original plan spec used snake_case; the 10-03-SUMMARY.md documents the correction but it's easy to miss.
**How to avoid:** Read `_sqlite_config.py` directly to confirm the entrypoint string — 10-03-SUMMARY.md documents that snake_case raises `dlsym symbol-not-found`.

---

## Code Examples

### justfile Fix Pattern

```just
# Install MySQL and ClickHouse Foundry ADBC drivers into the active virtualenv.
# dbc detects VIRTUAL_ENV automatically — no --level flag required.
# ClickHouse requires --pre: only alpha v0.1.0-alpha.1 is currently published.
# Two separate calls: dbc install with multiple args is not confirmed by official docs.
install-foundry-drivers:
    dbc install mysql
    dbc install --pre clickhouse
```

The comment should be updated to document why `--pre` is needed.

### SUMMARY.md frontmatter with requirements-completed

```yaml
---
plan: 10-01
phase: 10-sqlite-backend
status: complete
completed: 2026-03-01
requirements-completed:
  - SQLT-01
  - SQLT-02
---
```

Insert the `requirements-completed` block after the `completed` field and before the closing `---`.

### REQUIREMENTS.md traceability table update

```markdown
| SQLT-01 | Phase 10 | Complete |
| SQLT-02 | Phase 10 | Complete |
| SQLT-03 | Phase 10 | Complete |
| SQLT-04 | Phase 10 | Complete |
| SQLT-05 | Phase 10 | Complete |
| DBC-02 | Phase 11 | Complete |
```

---

## State of the Art

| Old State | Current State | Gap | Fix |
|-----------|--------------|-----|-----|
| Phase 10 unverified — no VERIFICATION.md | Code fully implemented, tests passing | Planning doc gap only | Create `.planning/phases/10-sqlite-backend/10-VERIFICATION.md` |
| Phase 11 unverified — no VERIFICATION.md | Code fully implemented, tests passing | Planning doc gap only | Create `.planning/phases/11-foundry-tooling-and-mysql-backend/11-VERIFICATION.md` |
| SQLT-01–05 showing `Pending` in REQUIREMENTS.md | Code wired and tested | Checkbox not updated after Phase 10 | Change `[ ]` to `[x]` for all five |
| 10-01, 10-02, 10-03 SUMMARY missing `requirements-completed` | 10-04-SUMMARY has the field | Omission during Phase 10 execution | Add frontmatter to three files |
| `dbc install clickhouse` missing `--pre` | ClickHouse guide correctly uses `--pre` | justfile not updated when `--pre` requirement discovered | Add `--pre` to justfile |

---

## Open Questions

None. All information needed to plan and execute this phase is present:

1. The code state is confirmed by the v1.0 audit (integration checker)
2. The VERIFICATION.md format is established (Phase 9 and Phase 12 templates)
3. The SUMMARY.md frontmatter pattern is established (10-04, all Phase 11 files)
4. The justfile fix is unambiguous (add `--pre` to ClickHouse install line)
5. The REQUIREMENTS.md changes are mechanical (checkbox + traceability table)

The only judgement call is confirming each truth in the VERIFICATION.md by actually reading source files — this is by design, not a gap.

---

## Sources

### Primary (HIGH confidence)

- `.planning/v1.0-MILESTONE-AUDIT.md` — authoritative gap list from gsd-auditor + integration checker
- `.planning/phases/12-clickhouse-backend/12-VERIFICATION.md` — canonical VERIFICATION.md format template
- `.planning/phases/09-infrastructure-and-databricks-fix/09-VERIFICATION.md` — alternative template (human_needed status)
- `.planning/phases/10-sqlite-backend/10-01-SUMMARY.md` through `10-04-SUMMARY.md` — Phase 10 implementation evidence
- `.planning/phases/11-foundry-tooling-and-mysql-backend/11-01-SUMMARY.md` through `11-04-SUMMARY.md` — Phase 11 implementation evidence
- `justfile` — current recipe state confirming missing `--pre`
- `.planning/REQUIREMENTS.md` — current checkbox and traceability state

### Secondary (MEDIUM confidence)

- `.planning/ROADMAP.md` Phase 13 description — success criteria are authoritative
- `docs/src/guides/clickhouse.md` — confirms `--pre` is documented in the guide (not read in this research, but confirmed in audit evidence)

---

## Metadata

**Confidence breakdown:**
- What needs to be built: HIGH — audit report is explicit about every gap
- VERIFICATION.md format: HIGH — two existing templates in the repository
- SUMMARY.md frontmatter pattern: HIGH — established in 10-04 and Phase 11 files
- justfile fix: HIGH — `--pre` requirement documented in ClickHouse guide and audit
- Scope boundary (MYSQL-05/CH-05 excluded): HIGH — ROADMAP.md is explicit

**Research date:** 2026-03-02
**Valid until:** Indefinitely — this phase has no external dependencies; all evidence is internal to the repository
