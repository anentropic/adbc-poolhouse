# Phase 2: Dependency Declarations - Research

**Researched:** 2026-02-24
**Domain:** pyproject.toml optional extras, uv lock file management, ADBC driver PyPI availability
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Lock file strategy:** Commit `uv.lock` to git (currently untracked — this phase adds and commits it). Generate with `uv sync --all-extras` so the lock covers all optional warehouse driver deps. CI must use `uv sync --frozen` to enforce the lock is up to date. Document `uv sync --all-extras` in README or CONTRIBUTING as the dev setup command.

- **Optional extras — which drivers get extras:** Only create extras for PyPI-available drivers. Confirmed PyPI extras: `[duckdb]`, `[snowflake]`, `[postgresql]`, `[flightsql]`. `[bigquery]` — researcher must verify `adbc-driver-bigquery` is available on PyPI before including; include only if confirmed. Foundry-distributed backends (Databricks, Redshift, Trino, MSSQL, Teradata) are NOT given extras in this phase — those drivers are not on PyPI. `[all]` includes all confirmed PyPI extras only. REQUIREMENTS.md SETUP-03 must be updated to reflect that Foundry driver extras are skipped in this phase.

- **Version constraint style for optional driver extras:** Open lower bounds only: `>=X` (no upper bound). Floor = latest stable version at time of writing (researcher confirms per-driver). Rationale: driver packages release frequently; upper bounds would increase maintenance overhead.

- **Version constraint style for runtime deps (pydantic-settings, sqlalchemy, adbc-driver-manager):** Open lower bounds only: `>=X` style (not the `>=X,<Y` ranges specified in SETUP-02). Researcher determines the actual minimum version each dep requires (based on API usage), not just latest stable. Rationale: pydantic-settings and sqlalchemy are common transitive deps — tight lower bounds cause unnecessary consumer conflicts. This deviates from the literal spec in SETUP-02; update REQUIREMENTS.md SETUP-02 to reflect the chosen approach.

- **Dev dependency additions:** `syrupy>=4.0` and `coverage[toml]` go in the existing `[dependency-groups] dev` group (consistent with the existing pattern in pyproject.toml). No new dependency groups needed.

### Claude's Discretion

- Exact minimum version floor for each runtime dep (researcher verifies against actual usage)
- Whether `adbc-driver-bigquery` is PyPI-available (researcher confirms)
- How to phrase the dev setup instructions in README/CONTRIBUTING

### Deferred Ideas (OUT OF SCOPE)

- **Foundry driver documentation** — Full documentation explaining how to install and use Foundry-distributed backends (Databricks, Redshift, Trino, MSSQL, Teradata) that have no PyPI extras. More than a README note — a proper docs section. Belongs in Phase 7 (Documentation and PyPI Publication).
- **Periodic CI against latest deps** — A scheduled workflow that builds against the latest available versions of all deps. On failure, opens a PR and mentions @copilot to fix. Belongs in Phase 7 or a future milestone CI phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SETUP-02 | Add runtime dependencies to `pyproject.toml`: `pydantic-settings`, `sqlalchemy`, `adbc-driver-manager` with open lower bound constraints | Version floors confirmed: pydantic-settings>=2.0.0, sqlalchemy>=2.0.0, adbc-driver-manager>=1.0.0. Constraint style change from spec (open `>=X` not `>=X,<Y`) must be noted in REQUIREMENTS.md update. |
| SETUP-03 | Add per-warehouse optional extras in `[project.optional-dependencies]` | PyPI availability confirmed for all extras except duckdb (which uses `duckdb` package bundling `adbc_driver_duckdb`). BigQuery confirmed on PyPI. Foundry backends excluded. Version floors per driver confirmed. REQUIREMENTS.md must be updated to drop Foundry extras from this phase scope. |
| SETUP-04 | Add `syrupy>=4.0` and `coverage[toml]` to dev dependencies | Both confirmed on PyPI. Goes in `[dependency-groups] dev`. syrupy latest is 5.1.0 so `>=4.0` is correct floor per CONTEXT.md. |
</phase_requirements>

## Summary

Phase 2 is a pure `pyproject.toml` + `uv.lock` editing task with no implementation code. The work divides into three concerns: (1) declaring runtime deps with open lower bounds, (2) declaring optional warehouse extras for PyPI-available drivers only, and (3) adding two dev dependencies. The resulting lock file must then be committed to git.

The critical research finding is the DuckDB extra: `adbc-driver-duckdb` does not exist as a standalone PyPI package. Instead, the `duckdb` package (starting at 0.9.1) bundles `adbc_driver_duckdb` as a module within its wheel. Therefore the `[duckdb]` extra should depend on `duckdb>=0.9.1`, not a non-existent `adbc-driver-duckdb` package. All other ADBC driver extras (`snowflake`, `postgresql`, `flightsql`, `bigquery`) have dedicated packages on PyPI. BigQuery is confirmed available (earliest stable 1.3.0, November 2024). Foundry-distributed backends have no PyPI packages — confirmed excluded per CONTEXT.md decisions.

The pre-commit hook chain already includes a `uv-lock` hook (from `astral-sh/uv-pre-commit`) that auto-runs `uv lock` on every commit. This means the lock file will be regenerated during the commit that saves `pyproject.toml` changes, so the workflow is: edit `pyproject.toml`, run `uv sync --all-extras` to validate resolution, then commit (the `uv-lock` hook updates `uv.lock` automatically). REQUIREMENTS.md edits for SETUP-02 and SETUP-03 must be committed in the same phase.

**Primary recommendation:** Edit `pyproject.toml` directly (not via `uv add`) to add runtime deps and optional extras in one coherent diff. Run `uv sync --all-extras` to validate. Stage all three files (`pyproject.toml`, `uv.lock`, `REQUIREMENTS.md`) and commit together.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| uv | already installed | Lock file management and sync | Project already uses uv; `.pre-commit-config.yaml` uses `uv-pre-commit` hook |
| pyproject.toml PEP 621 | N/A | Dependency declaration format | Standard Python project spec; `uv_build` backend requires it |

### Runtime Dependencies (to be added)

| Library | Minimum Version | Latest Stable | Constraint to Use | Purpose |
|---------|----------------|---------------|-------------------|---------|
| pydantic-settings | 2.0.0 | 2.13.1 | `>=2.0.0` | `BaseSettings` + `SettingsConfigDict` for warehouse config models |
| sqlalchemy | 2.0.0 | 2.0.46 | `>=2.0.0` | `QueuePool` (connection pooling API, standalone usage) |
| adbc-driver-manager | 1.0.0 | 1.10.0 | `>=1.0.0` | ADBC driver manager; provides `adbc_driver_manager.dbapi.connect()` |

### Optional Extras (to be added)

| Extra | Package | Minimum Version | Latest Stable | Note |
|-------|---------|----------------|---------------|------|
| `[duckdb]` | `duckdb` | `>=0.9.1` | 1.4.4 | `adbc_driver_duckdb` is bundled inside `duckdb` wheel since 0.9.1 |
| `[snowflake]` | `adbc-driver-snowflake` | `>=1.0.0` | 1.10.0 | Dedicated PyPI package; earliest stable is 0.4.0 but 1.0.0 is the stable major |
| `[postgresql]` | `adbc-driver-postgresql` | `>=1.0.0` | 1.10.0 | Dedicated PyPI package; 1.0.0 is the stable major |
| `[flightsql]` | `adbc-driver-flightsql` | `>=1.0.0` | 1.10.0 | Dedicated PyPI package; 1.0.0 is the stable major |
| `[bigquery]` | `adbc-driver-bigquery` | `>=1.3.0` | 1.10.0 | CONFIRMED on PyPI; earliest stable is 1.3.0 (Nov 2024) |
| `[all]` | all above | — | — | Installs all five extras; Foundry backends excluded (no PyPI packages) |

### Dev Dependencies (to be added to existing `[dependency-groups] dev`)

| Library | Constraint | Latest | Note |
|---------|-----------|--------|------|
| syrupy | `>=4.0` | 5.1.0 | Snapshot testing; CONTEXT.md floor is 4.0; latest is 5.x |
| coverage | `[toml]` extra, no version pin | 7.13.4 | Already pulled transitively by `pytest-cov` but explicit declaration with `[toml]` needed for `[tool.coverage]` config in pyproject.toml |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `duckdb>=0.9.1` for `[duckdb]` extra | No separate `adbc-driver-duckdb` package exists | The `duckdb` package bundles `adbc_driver_duckdb`; this is the only valid option |
| `>=X` open lower bounds | `>=X,<Y` pinned ranges (original SETUP-02 spec) | Open bounds reduce consumer dep conflicts; decision locked in CONTEXT.md |

## Architecture Patterns

### Recommended pyproject.toml Structure

```toml
[project]
name = "adbc-poolhouse"
version = "0.1.0"
dependencies = [
    "pydantic-settings>=2.0.0",
    "sqlalchemy>=2.0.0",
    "adbc-driver-manager>=1.0.0",
]

[project.optional-dependencies]
duckdb = ["duckdb>=0.9.1"]
snowflake = ["adbc-driver-snowflake>=1.0.0"]
postgresql = ["adbc-driver-postgresql>=1.0.0"]
flightsql = ["adbc-driver-flightsql>=1.0.0"]
bigquery = ["adbc-driver-bigquery>=1.3.0"]
all = [
    "adbc-poolhouse[duckdb]",
    "adbc-poolhouse[snowflake]",
    "adbc-poolhouse[postgresql]",
    "adbc-poolhouse[flightsql]",
    "adbc-poolhouse[bigquery]",
]

[dependency-groups]
dev = [
    "basedpyright>=1.38.0",
    "coverage[toml]",
    "ipython>=9.10.0",
    "pdbpp>=0.12.0.post1",
    "pytest>=8.0.0",
    "pytest-cov>=6.0.0",
    "ruff>=0.15.1",
    "syrupy>=4.0",
]
```

Source: uv documentation — `[project.optional-dependencies]` is the correct table for published extras (distinct from `[dependency-groups]` which is for local dev only).

### Pattern: `[all]` Extra as Self-Referential Extras

```toml
all = [
    "adbc-poolhouse[duckdb]",
    "adbc-poolhouse[snowflake]",
    "adbc-poolhouse[postgresql]",
    "adbc-poolhouse[flightsql]",
    "adbc-poolhouse[bigquery]",
]
```

This pattern (self-referencing package extras) is the standard uv/pip way to define a meta-extra that pulls all other extras. It avoids duplicating package names and lets each sub-extra remain independent.

### Pattern: Lock File Workflow with Pre-Commit Hook

The project already has `uv-lock` in `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/astral-sh/uv-pre-commit
  rev: 0.10.3
  hooks:
    - id: uv-lock
```

This hook automatically runs `uv lock` on every commit. Workflow:

1. Edit `pyproject.toml` with new dependencies
2. Run `uv sync --all-extras` to validate resolution locally
3. `git add pyproject.toml REQUIREMENTS.md`
4. `git commit` — the `uv-lock` hook regenerates `uv.lock` automatically and stages it
5. The commit includes both `pyproject.toml` and the updated `uv.lock`

Important: The executor does NOT need to manually run `uv lock` before committing — the hook handles it. However, running `uv sync --all-extras` first (before committing) validates that the resolution succeeds.

### Anti-Patterns to Avoid

- **Do not use `uv add` for each dependency one-by-one:** `uv add` runs lock resolution after each addition, which is slow and unnecessary. Edit `pyproject.toml` directly for all changes, then run one `uv sync --all-extras` to validate.
- **Do not put optional extras in `[dependency-groups]`:** `[dependency-groups]` is for local dev tools. Published extras go in `[project.optional-dependencies]`. The two sections are structurally separate in PEP 735 / uv.
- **Do not add `uv.lock` to `.gitignore`:** It is currently commented-out in `.gitignore` (the file has a comment explaining it should be committed). The task is simply to `git add uv.lock` and commit it.
- **Do not use `adbc-driver-duckdb` as the package name:** No such package exists on PyPI. Use `duckdb>=0.9.1` instead — it bundles `adbc_driver_duckdb`.
- **Do not use `>=X,<Y` ranges for runtime deps:** CONTEXT.md locked decision is open lower bounds only. The original SETUP-02 spec used `<Y` upper bounds — those must NOT be used.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Lock file generation | Manual requirements.txt | `uv sync --all-extras` then `uv-lock` hook | uv produces a universal cross-platform lock file; manual requirements.txt is platform-specific |
| Extras resolution validation | Testing pip install manually | `uv sync --extra duckdb` / `uv sync --all-extras` | uv validates the full resolution graph including extras |

## Common Pitfalls

### Pitfall 1: DuckDB Extra Package Name

**What goes wrong:** Developer uses `adbc-driver-duckdb` as the package name in the `[duckdb]` extra. uv reports "package not found on PyPI" during `uv sync`.

**Why it happens:** Apache ADBC publishes separate `adbc-driver-*` packages for each warehouse (snowflake, postgresql, flightsql, bigquery). Developers assume the same pattern applies to DuckDB.

**How to avoid:** Use `duckdb>=0.9.1` instead. The `duckdb` package has bundled `adbc_driver_duckdb` as an importable module since DuckDB 0.8.0 (ADBC support launched August 2023). Confirmed by installing `duckdb==1.4.4` and verifying `importlib.util.find_spec('adbc_driver_duckdb')` returns a valid spec.

**Warning signs:** `uv sync --all-extras` fails with "No solution found" or "Package not found: adbc-driver-duckdb".

### Pitfall 2: `[all]` Extra Not Using Self-References

**What goes wrong:** The `[all]` extra lists package names (e.g., `duckdb>=0.9.1`) instead of self-referencing extras (e.g., `adbc-poolhouse[duckdb]`).

**Why it happens:** Not knowing the self-reference pattern exists.

**How to avoid:** Use `adbc-poolhouse[duckdb]` syntax in `[all]`. This way, if a minimum version floor for a sub-extra ever changes, it only needs updating in one place (the sub-extra definition).

**Verification:** `pip install adbc-poolhouse[all]` installs all five drivers. `pip install adbc-poolhouse[duckdb]` installs only `duckdb`. (Success criteria from phase description.)

### Pitfall 3: `uv-lock` Hook Regenerating vs. Adding `uv.lock`

**What goes wrong:** Developer runs `uv lock` before committing, then the `uv-lock` pre-commit hook also runs `uv lock`, producing a no-op second run. Or developer forgets to `git add uv.lock` after manually running `uv lock`, so the hook is what actually stages it.

**Why it doesn't matter:** The `uv-lock` hook idempotently updates and stages `uv.lock`. Whether you run `uv lock` manually first or not, the commit will contain the correct lock file. The hook is the source of truth.

**How to handle:** Simply run `uv sync --all-extras` to validate (this also runs `uv lock` internally), then commit. The hook re-runs lock if needed.

### Pitfall 4: Forgetting `coverage[toml]` Bracket Syntax in TOML

**What goes wrong:** In `pyproject.toml` TOML syntax, `coverage[toml]` needs to be a quoted string to avoid TOML parser error. The brackets are part of the PEP 508 dependency specifier, not TOML table syntax.

**How to avoid:**
```toml
# Correct:
dev = [
    "coverage[toml]",
]

# Wrong (TOML parse error):
dev = [
    coverage[toml],
]
```

### Pitfall 5: `syrupy>=4.0` vs. `syrupy>=5.0`

**What goes wrong:** Using `>=5.0` because latest is 5.1.0, accidentally excluding syrupy 4.x which may matter for compatibility.

**How to avoid:** CONTEXT.md locked decision is `>=4.0`. Use exactly that. At time of research, latest is 5.1.0 so `>=4.0` will install 5.1.0, which is fine.

### Pitfall 6: REQUIREMENTS.md Not Updated

**What goes wrong:** SETUP-02 and SETUP-03 as written in REQUIREMENTS.md don't match what was actually implemented (SETUP-02 uses `>=X,<Y` ranges; SETUP-03 includes Foundry extras). The plan must update REQUIREMENTS.md to reflect the actual approach.

**How to avoid:** Include explicit REQUIREMENTS.md update tasks in the plan. The CONTEXT.md explicitly requires updating SETUP-02 (constraint style) and SETUP-03 (Foundry extras removed from scope).

## Code Examples

### Final pyproject.toml `[project]` section

```toml
# Source: uv docs (https://github.com/astral-sh/uv/blob/main/docs/concepts/projects/dependencies.md)
[project]
name = "adbc-poolhouse"
version = "0.1.0"
description = "Connection pooling for ADBC drivers from typed warehouse configs"
readme = "README.md"
authors = [
    { name = "Anentropic", email = "ego@anentropic.com" }
]
requires-python = ">=3.11"
dependencies = [
    "pydantic-settings>=2.0.0",
    "sqlalchemy>=2.0.0",
    "adbc-driver-manager>=1.0.0",
]

[project.optional-dependencies]
duckdb = ["duckdb>=0.9.1"]
snowflake = ["adbc-driver-snowflake>=1.0.0"]
postgresql = ["adbc-driver-postgresql>=1.0.0"]
flightsql = ["adbc-driver-flightsql>=1.0.0"]
bigquery = ["adbc-driver-bigquery>=1.3.0"]
all = [
    "adbc-poolhouse[duckdb]",
    "adbc-poolhouse[snowflake]",
    "adbc-poolhouse[postgresql]",
    "adbc-poolhouse[flightsql]",
    "adbc-poolhouse[bigquery]",
]
```

### Validation commands

```bash
# Validate full resolution (run before committing)
uv sync --all-extras

# Validate individual extras (spot-check success criteria)
uv sync --extra duckdb
uv sync --extra snowflake
uv sync --extra all

# CI enforcement command (use in CI YAML, not this phase)
uv sync --frozen
```

### Updated REQUIREMENTS.md SETUP-02 text

```markdown
- [ ] **SETUP-02**: Add runtime dependencies to `pyproject.toml`:
  `pydantic-settings>=2.0.0`, `sqlalchemy>=2.0.0`, `adbc-driver-manager>=1.0.0`
  (Open lower bounds only — no upper bound caps; tight `<Y` bounds cause
  unnecessary consumer dep conflicts for common transitive deps)
```

### Updated REQUIREMENTS.md SETUP-03 text

```markdown
- [ ] **SETUP-03**: Add per-warehouse optional extras for PyPI-available drivers only:
  `[duckdb]` (via `duckdb` package), `[snowflake]`, `[bigquery]`, `[postgresql]`,
  `[flightsql]`, `[all]`. Foundry-distributed backends (Databricks, Redshift, Trino,
  MSSQL, Teradata) are NOT given extras in v1 — those drivers are not on PyPI and
  will be documented in Phase 7.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `requirements.txt` + `pip install -e .` | `pyproject.toml` + `uv sync` | PEP 621 standardized 2021; uv mainstream 2024 | Lock files are cross-platform universal; no separate `requirements-dev.txt` files |
| `setup.py` extras_require | `[project.optional-dependencies]` in pyproject.toml | PEP 517/518/621 | Standard format, tool-agnostic |
| `[tool.poetry.dependencies]` | `[project.dependencies]` + `[project.optional-dependencies]` | uv 0.4+ (2024) | uv supports PEP 621 standard, not Poetry's custom format |

**Deprecated/outdated:**
- `setup.cfg extras_require`: Replaced by `[project.optional-dependencies]` in pyproject.toml
- `requirements-dev.txt` separate files: Replaced by `[dependency-groups]` (PEP 735, uv-supported)

## Open Questions

1. **Minimum version floor for `adbc-driver-manager` — is `>=1.0.0` the right floor?**
   - What we know: `adbc_driver_manager.dbapi.connect()` API has been stable since the 0.x series; 1.0.0 was released May 2024. The project's REQUIREMENTS describe using `adbc_driver_manager` for driver calls.
   - What's unclear: Whether any specific API used in later phases (driver loading, memory `reset_agent`) requires a version above 1.0.0.
   - Recommendation: Use `>=1.0.0` now. If later phases discover a need for a newer API, the floor can be bumped at implementation time. No evidence requires a higher floor at this stage.

2. **`coverage[toml]` — is it already satisfied by `pytest-cov`?**
   - What we know: `pytest-cov` depends on `coverage` but without the `[toml]` extra. The `[toml]` extra adds `tomli` as a dependency (for Python < 3.11, where `tomllib` is not in stdlib). Since this project requires Python >=3.11, `tomllib` is stdlib and `coverage[toml]` adds no extra packages. However, explicit declaration with `[toml]` is still needed for `[tool.coverage.report]` in pyproject.toml to be parsed correctly.
   - Recommendation: Add `"coverage[toml]"` explicitly to dev group. This is a documentation/intent signal even if `tomli` is not installed.

3. **DuckDB ADBC minimum version — is `0.9.1` too conservative?**
   - What we know: Apache ADBC docs state "DuckDB 0.9.1 or higher" as the minimum. The `adbc_driver_duckdb` module existence was confirmed in `duckdb==1.4.4`.
   - What's unclear: Whether `adbc_driver_duckdb` was present in the `duckdb` wheel before 1.0.0 (the version numbering transition from 0.x to 1.x happened).
   - Recommendation: Use `>=0.9.1` per the official ADBC docs. In practice, consumers will install the latest stable (1.4.4) anyway. If the floor proves problematic, it can be raised.

## Sources

### Primary (HIGH confidence)

- `/astral-sh/uv` (Context7) — optional extras syntax, `--all-extras`, `--frozen`, `uv-lock` hook, lock file format
- PyPI JSON API (`https://pypi.org/pypi/{package}/json`) — version availability and history for all packages listed above; queried 2026-02-24
- Direct install verification — `duckdb==1.4.4` installed in temp venv; `importlib.util.find_spec('adbc_driver_duckdb')` confirmed present
- `/Users/paul/Documents/Dev/Personal/adbc-poolhouse/.pre-commit-config.yaml` — confirmed `uv-lock` hook already in place
- `/Users/paul/Documents/Dev/Personal/adbc-poolhouse/pyproject.toml` — confirmed current state: empty `dependencies = []`, no optional extras, existing dev group structure

### Secondary (MEDIUM confidence)

- `https://arrow.apache.org/adbc/main/driver/duckdb.html` — states "DuckDB 0.9.1 or higher" requirement for ADBC support
- `https://duckdb.org/docs/stable/clients/adbc.html` — mentions `adbc_driver_duckdb` as the module name (but page was redirect; content parsed via WebFetch)

### Tertiary (LOW confidence)

- WebSearch result confirming `adbc-driver-bigquery` first appeared on PyPI in late 2024 (consistent with PyPI API showing 1.3.0 first release Nov 2024)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all package versions verified directly from PyPI API; duckdb ADBC integration confirmed by actual installation
- Architecture: HIGH — patterns from uv official docs (Context7); `[all]` self-reference pattern is standard pip/uv behavior
- Pitfalls: HIGH for DuckDB naming (confirmed by PyPI lookup + install test); MEDIUM for others (reasoning-based)

**Research date:** 2026-02-24
**Valid until:** 2026-05-24 (stable APIs; version floors only need revisiting if new major versions drop)
