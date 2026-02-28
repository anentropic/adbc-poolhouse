---
phase: 08-review-and-improve-docs
plan: "05"
subsystem: docs
tags: [markdown, guides, databricks, redshift, trino, mssql, teradata, foundry]

# Dependency graph
requires:
  - phase: 08-review-and-improve-docs
    provides: Phase context, guide structure established by earlier plans

provides:
  - Databricks warehouse guide (Foundry driver, PAT auth, URI and decomposed fields, DATABRICKS_ prefix)
  - Redshift warehouse guide (Foundry driver, provisioned/serverless, URI and decomposed fields, REDSHIFT_ prefix)
  - Trino warehouse guide (Foundry driver, URI and decomposed fields, TRINO_ prefix)
  - MSSQL stub guide (Foundry driver, MSSQL_ prefix, no auth examples)
  - Teradata honest stub (not yet implemented, no invented fields or code examples)

affects:
  - 08-review-and-improve-docs plan 06 (nav update needs these five pages registered)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Foundry-distributed warehouse page structure (driver notice + install + connection + env vars + see also)
    - Honest stub pattern for unimplemented backends (note admonition, no code examples)
    - pragma allowlist secret on bash export lines containing example passwords

key-files:
  created:
    - docs/src/guides/databricks.md
    - docs/src/guides/redshift.md
    - docs/src/guides/trino.md
    - docs/src/guides/mssql.md
    - docs/src/guides/teradata.md
  modified:
    - docs/src/guides/postgresql.md
    - docs/src/guides/redshift.md
    - src/adbc_poolhouse/_pool_factory.py

key-decisions:
  - "pragma allowlist secret required on bash export lines (not just Python strings) when example passwords like s3cret are present"
  - "collections.abc moved to TYPE_CHECKING block in _pool_factory.py (ruff TC003 — only used as type annotation with __future__ annotations active)"

patterns-established:
  - "Foundry guide structure: driver notice paragraph → pip install (base only) → connection section → env vars → see also"
  - "Honest stub pattern: MkDocs admonition note + planned-future paragraph + see-also only, no config class references as importable"

requirements-completed: []

# Metrics
duration: 3min
completed: 2026-02-28
---

# Phase 08 Plan 05: Foundry Warehouse Guide Pages Summary

**Five Foundry-distributed warehouse guide pages (Databricks, Redshift, Trino, MSSQL, Teradata stub) with correct driver notices, env prefixes, and no invented fields.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-28T00:09:12Z
- **Completed:** 2026-02-28T00:11:52Z
- **Tasks:** 2
- **Files modified:** 8 (5 new guides + postgresql.md fix + redshift.md fix + _pool_factory.py fix)

## Accomplishments

- Created five warehouse guide pages for Foundry-distributed drivers, none of which have PyPI extras
- Databricks, Redshift, and Trino guides include URI and decomposed-field connection examples with correct env prefixes
- MSSQL is a partial guide (env prefix only, no auth examples, per CONTEXT.md decision) covering SQL Server, Azure SQL, Azure Fabric, and Synapse
- Teradata is an honest stub with MkDocs admonition, no code examples, and no invented fields — TeradataConfig does not exist in source

## Task Commits

Each task was committed atomically:

1. **Task 1: Create databricks.md and redshift.md** - `dffca41` (feat)
2. **Task 2: Create trino.md, mssql.md, and teradata.md** - `6a66c1c` (feat, includes auto-fixes)

**Plan metadata:** (final docs commit — see below)

## Files Created/Modified

- `docs/src/guides/databricks.md` - Databricks Foundry guide with PAT auth, URI and decomposed-field examples, DATABRICKS_ prefix
- `docs/src/guides/redshift.md` - Redshift Foundry guide with provisioned/serverless note, REDSHIFT_ prefix
- `docs/src/guides/trino.md` - Trino Foundry guide with URI and decomposed-field examples, TRINO_ prefix
- `docs/src/guides/mssql.md` - MSSQL stub guide with MSSQL_ prefix, covers SQL Server family
- `docs/src/guides/teradata.md` - Honest stub stating TeradataConfig is planned but not yet implemented
- `docs/src/guides/postgresql.md` - Added `# pragma: allowlist secret` to bash export line (auto-fix)
- `docs/src/guides/redshift.md` - Added `# pragma: allowlist secret` to REDSHIFT_PASSWORD bash export line (auto-fix)
- `src/adbc_poolhouse/_pool_factory.py` - Moved `collections.abc` import to TYPE_CHECKING block (ruff TC003 auto-fix)

## Decisions Made

- `pragma: allowlist secret` is required on bash `export` lines containing example passwords, not only on Python string literals. The detect-secrets hook catches both.
- `collections.abc` moved to the `TYPE_CHECKING` block in `_pool_factory.py` because it is only used as a return type annotation (`collections.abc.Iterator`) on `managed_pool`. With `from __future__ import annotations` active, annotations are strings at runtime and the import is not needed outside type checking.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fix ruff TC003: move collections.abc to TYPE_CHECKING block**
- **Found during:** Task 2 commit (pre-commit ruff hook)
- **Issue:** `import collections.abc` at module level in `_pool_factory.py` triggered ruff TC003 — only used as type annotation, not needed at runtime with `from __future__ import annotations`
- **Fix:** Moved `import collections.abc` inside the `if TYPE_CHECKING:` block
- **Files modified:** `src/adbc_poolhouse/_pool_factory.py`
- **Verification:** ruff hook passed on subsequent commit
- **Committed in:** `6a66c1c` (Task 2 commit)

**2. [Rule 3 - Blocking] Add pragma allowlist secret to bash export lines**
- **Found during:** Task 2 commit (pre-commit detect-secrets hook)
- **Issue:** `export POSTGRESQL_URI=...s3cret...` in `postgresql.md:33` (pre-existing, from plan 04) and new `MSSQL_PASSWORD=s3cret`, `REDSHIFT_PASSWORD=s3cret`, `TRINO_PASSWORD=s3cret` export lines triggered detect-secrets
- **Fix:** Added `# pragma: allowlist secret` to all bash export lines with example passwords across new and existing guides
- **Files modified:** `docs/src/guides/postgresql.md`, `docs/src/guides/redshift.md`, `docs/src/guides/mssql.md`, `docs/src/guides/trino.md`
- **Verification:** detect-secrets hook passed on subsequent commit
- **Committed in:** `6a66c1c` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking — pre-commit hook failures)
**Impact on plan:** Both auto-fixes essential to pass pre-commit hooks. No scope creep. The `_pool_factory.py` fix is a correctness improvement (type annotation hygiene). The pragma fixes are required for false-positive secret detection in example passwords.

## Issues Encountered

None beyond the auto-fixed pre-commit hook failures documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All five Foundry warehouse guide pages exist and are committed
- Plan 06 (nav update) can now register all five pages in mkdocs.yml
- `uv run mkdocs build --strict` verification is deferred to Plan 06 (which updates nav)

---
*Phase: 08-review-and-improve-docs*
*Completed: 2026-02-28*
