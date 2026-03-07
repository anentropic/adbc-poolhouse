# Phase 7: Documentation and PyPI Publication - Research

**Researched:** 2026-02-26
**Domain:** MkDocs/mkdocstrings, Google docstrings, PyPI OIDC trusted publishing, git-cliff, GitHub Actions release workflow, Claude skill authoring
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Docs site structure:**
- Navigation: Getting Started / Guides / API Reference (three top-level sections)
- Theme: Material for MkDocs + mkdocstrings — auto-generates API ref from docstrings
- Guides section contains four pages: Pool lifecycle, Consumer patterns, Configuration reference, Snowflake-specific guide
- Changelog page included in the docs site, auto-generated from git-cliff output; appears in nav

**Docstring coverage:**
- Scope: all public classes + their public methods, module-level docstrings for each public module, public functions at module level — internal helpers (`_` prefix) are excluded
- Format: Google-style with Args, Returns, Raises sections on every covered symbol
- Examples block: key entry points only (e.g. `create_pool`, `PoolConfig`) — not every method
- Exceptions documented via Raises section inline per method (not a separate exceptions page)
- Quickstart guide: prose only, validated in CI by running it against a real DuckDB connection — not as a doctest

**Release workflow:**
- Trigger: git tag push (e.g. `v0.1.0`) — same pattern as cubano
- Pipeline: `build → (validate + changelog in parallel) → publish-testpypi → publish-pypi → deploy-docs`
- Added vs cubano: TestPyPI step — install from TestPyPI, smoke-test, then publish to real PyPI
- Wheel validations before publishing:
  1. `py.typed` marker present (unzip + grep)
  2. Public API imports succeed (`from adbc_poolhouse import create_pool, PoolConfig`)
  3. Version in package matches the git tag
  4. Both wheel and sdist install cleanly across Python 3.11 and 3.12 in isolated venvs
- Docs deploy to GitHub Pages on every tag, triggered after publish succeeds

**Docs-author skill:**
- Location: `.claude/skills/adbc-poolhouse-docs-author/SKILL.md`
- Four responsibilities:
  1. Write Google-style docstrings to the project's house standard (exact Args/Returns/Raises/Examples format)
  2. Update `mkdocs.yml` nav and create `.md` stub files when new modules are added
  3. Validate docs completeness before marking any phase done (checklist gate)
  4. Write and update consumer-facing guides (pool lifecycle, consumer patterns, quickstart)
- Audience: Python developers using async DB connections — FastAPI, SQLAlchemy-async, asyncpg patterns. Assume async Python familiarity; do not over-explain ADBC internals.
- Classification model: Lighter than Diataxis — three types only: Quickstart, How-to Guide, API Reference. Reference is auto-generated; Claude writes Quickstart and Guides.
- Humanizer pass: Required on all new prose or any page with >50% rewritten content — same patterns to eliminate as cubano's skill
- Quality checklist (must pass before marking a doc task done):
  - All new public symbols have Args/Returns/Raises
  - Key entry points have an Examples block
  - New consumer-facing behaviour reflected in the relevant guide
  - `uv run mkdocs build --strict` passes
  - Humanizer pass applied

**CLAUDE.md quality gate:**
- `CLAUDE.md` must instruct plan-phase to include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>` for all plans in phases >= 7

### Claude's Discretion
- Exact MkDocs configuration details (plugins, extensions, colour scheme)
- git-cliff configuration format (`cliff.toml`)
- Exact CI job names and step ordering within the release workflow
- How to handle ADBC driver-specific tabbed content in guides (if needed)

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TOOL-01 | Project-specific docs writing skill at `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — adapted from the cubano docs author skill | Cubano SKILL.md structure read and documented; adaptation points identified |
| TOOL-02 | `CLAUDE.md` instruction: for all plans in phases >= 7, include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>` | CLAUDE.md does not yet exist; content format clear from project conventions |
| DOCS-01 | API reference auto-generated via mkdocstrings — all public symbols documented with Google-style docstrings | mkdocs.yml already configures mkdocstrings with `docstring_style: google`; gen_ref_pages.py script already present; docstring audit shows most symbols need Args/Returns/Raises added |
| DOCS-02 | Quickstart guide — install + first working pool in under 5 minutes | docs/src/index.md exists but has TODO placeholder; needs full quickstart prose + DuckDB example |
| DOCS-03 | Consumer patterns — two complete examples: (a) Semantic ORM direct config pattern, (b) dbt-open-sl profiles.yml shim pattern | New guide file needed at docs/src/guides/consumer-patterns.md |
| DOCS-04 | Pool lifecycle guide — when and how to call `pool.dispose()`, fixture teardown pattern for tests, common mistake examples | New guide file needed at docs/src/guides/pool-lifecycle.md |
| DIST-01 | PyPI publication via OIDC trusted publisher — register on PyPI before first release using exact workflow filename | Registration steps documented; must be done manually on pypi.org and test.pypi.org before first tag push |
| DIST-02 | Release workflow validates `py.typed` presence in built wheel | py.typed already exists at `src/adbc_poolhouse/py.typed`; release.yml already has the check but has a cookiecutter placeholder bug to fix |
| DIST-03 | Release workflow generates changelog via `git-cliff` (`.cliff.toml` already present) | `.cliff.toml` present and complete; release.yml already has changelog job; needs TestPyPI step and docs deploy job added |
</phase_requirements>

---

## Summary

Phase 7 delivers a documented, pip-installable library. The good news: the project's docs and release infrastructure is already partially built — `mkdocs.yml` is fully configured, `gen_ref_pages.py` is in place, `.cliff.toml` is present, and `release.yml` has the core build/validate/changelog/publish structure. The work in this phase is completing what exists rather than building from scratch.

Three distinct workstreams exist. First, docstrings: `create_pool` already has full Google-style Args/Returns/Raises; the config classes have class-level docstrings and field attribute docstrings but most lack a formal Args block on `__init__` (though `mkdocstrings` with `merge_init_into_class: true` renders field docstrings correctly). The main gap is verifying mkdocstrings renders the field docs correctly and adding Examples blocks to the key entry points (`create_pool`, `DuckDBConfig`, `SnowflakeConfig`).

Second, the docs site needs structural completion: the current nav only has `Home / API Reference / Changelog` but CONTEXT requires `Getting Started / Guides / API Reference / Changelog`. The four guide pages and a Getting Started section need to be written as new `.md` files. Third, the `release.yml` has two concrete bugs to fix (cookiecutter placeholder, Python 3.14 matrix instead of 3.11/3.12) and three features to add (TestPyPI publish job, smoke-test-from-TestPyPI job, docs deploy on tag). PyPI OIDC trusted publisher registration must happen manually before the first tag push.

**Primary recommendation:** Work in four sequential tasks: (1) create TOOL-01/TOOL-02 (the skill and CLAUDE.md), (2) complete docstrings and verify `uv run mkdocs build --strict` passes, (3) write the four guide pages and update nav, (4) fix and extend the release.yml + register trusted publishers.

---

## Standard Stack

### Core (already installed)
| Library | Version (pyproject.toml) | Purpose | Why Standard |
|---------|--------------------------|---------|--------------|
| mkdocs | >=1.6.0 | Docs site builder | Industry standard for Python projects |
| mkdocs-material | >=9.7.0 | Material theme | Best-in-class Python docs theme |
| mkdocstrings[python] | >=0.26.0 | Auto-generates API ref from docstrings | Native Google-style docstring support via Griffe |
| mkdocs-gen-files | >=0.5.0 | Runs scripts at build time to generate .md files | Powers the gen_ref_pages.py auto-generation |
| mkdocs-literate-nav | >=0.6.0 | Uses SUMMARY.md for navigation | Allows gen_ref_pages.py to control API ref nav |
| mkdocs-section-index | >=0.3.0 | Makes section index pages work | Required for `reference/` section to render |

### Release tools (already installed/configured)
| Tool | Version | Purpose | Status |
|------|---------|---------|--------|
| git-cliff | 2.7.0 (pinned in release.yml curl) | Changelog generation from conventional commits | `.cliff.toml` present and complete |
| uv_build | >=0.9.18,<1.0.0 | Build backend | Already in pyproject.toml `[build-system]` |
| pypa/gh-action-pypi-publish | release/v1 | Publishes to PyPI/TestPyPI via OIDC | Already used in release.yml |

### Installation (already complete)
```bash
# Docs group already declared in pyproject.toml
uv sync --group docs

# Build and serve locally
uv run mkdocs build --strict
uv run mkdocs serve
```

---

## Architecture Patterns

### Existing Project Structure
```
adbc-poolhouse/
├── src/adbc_poolhouse/    # Package source (all modules already exist)
│   ├── py.typed           # EXISTS - PEP 561 marker
│   └── *.py               # All public + internal modules
├── docs/
│   ├── scripts/
│   │   └── gen_ref_pages.py  # EXISTS - auto-generates API ref pages
│   └── src/
│       └── index.md          # EXISTS - has TODO placeholder
├── mkdocs.yml             # EXISTS - fully configured
├── .cliff.toml            # EXISTS - conventional commits format
└── .github/workflows/
    ├── release.yml        # EXISTS - has bugs + missing steps
    └── docs.yml           # EXISTS - deploys on main push (will be secondary)
```

### What Phase 7 Must Add
```
.claude/
├── skills/
│   └── adbc-poolhouse-docs-author/
│       └── SKILL.md       # NEW - docs author skill (TOOL-01)
CLAUDE.md                  # NEW - project quality gate (TOOL-02)
docs/src/
├── getting-started.md     # NEW - or update index.md to be quickstart
├── guides/
│   ├── pool-lifecycle.md  # NEW - DOCS-04
│   ├── consumer-patterns.md # NEW - DOCS-03
│   ├── configuration.md   # NEW - config reference guide
│   └── snowflake.md       # NEW - Snowflake-specific guide
└── changelog.md           # NEW - included in nav, content from git-cliff output
```

### Pattern 1: mkdocstrings Field Docstrings (config classes)
**What:** Config classes use attribute docstrings (string immediately after field assignment). mkdocstrings with `merge_init_into_class: true` renders these as the field descriptions in API docs.
**When to use:** For Pydantic BaseSettings config classes where fields are class-level attributes.
**Example (already in use in the codebase):**
```python
# Source: src/adbc_poolhouse/_duckdb_config.py
class DuckDBConfig(BaseWarehouseConfig):
    """
    DuckDB warehouse configuration.

    Covers all DuckDB ADBC connection parameters. Pool tuning fields
    (pool_size, max_overflow, timeout, recycle) are inherited from
    BaseWarehouseConfig and loaded from DUCKDB_* environment variables.

    Example:
        DuckDBConfig(database='/data/warehouse.db', pool_size=5)
        DuckDBConfig()  # in-memory, pool_size=1 enforced by validator
    """
    database: str = ":memory:"
    """File path or ':memory:'. Env: DUCKDB_DATABASE."""
```

### Pattern 2: Google-Style Function Docstring (create_pool)
**What:** Public functions use Args/Returns/Raises sections with Google-style indentation.
**Example (already complete in codebase):**
```python
# Source: src/adbc_poolhouse/_pool_factory.py
def create_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    ...
) -> sqlalchemy.pool.QueuePool:
    """
    Create a SQLAlchemy QueuePool backed by an ADBC warehouse driver.

    [Description paragraph]

    Args:
        config: A warehouse config model instance (e.g. ``DuckDBConfig``).
        pool_size: Number of connections to keep in the pool. Default: 5.
        max_overflow: Extra connections allowed above pool_size. Default: 3.
        timeout: Seconds to wait for a connection before raising. Default: 30.
        recycle: Seconds before a connection is recycled. Default: 3600.
        pre_ping: Whether to ping connections before checkout. Default: False.

    Returns:
        A configured ``sqlalchemy.pool.QueuePool`` ready for use.

    Raises:
        ImportError: If the required ADBC driver is not installed.
        TypeError: If ``config`` is not a recognised warehouse config type.
    """
```

### Pattern 3: MkDocs Nav Structure (CONTEXT.md requirement)
**What:** `mkdocs.yml` nav must be reorganized from current 3-item flat structure to hierarchical structure with Getting Started, Guides, API Reference, Changelog.
**Current nav (needs changing):**
```yaml
nav:
  - Home: index.md
  - API Reference: reference/
  - Changelog: changelog.md
```
**Required nav:**
```yaml
nav:
  - Getting Started: index.md
  - Guides:
    - Pool Lifecycle: guides/pool-lifecycle.md
    - Consumer Patterns: guides/consumer-patterns.md
    - Configuration Reference: guides/configuration.md
    - Snowflake Guide: guides/snowflake.md
  - API Reference: reference/
  - Changelog: changelog.md
```

### Pattern 4: Release Workflow Pipeline (CONTEXT.md requirement)
**What:** `build → (validate + changelog in parallel) → publish-testpypi → publish-pypi → deploy-docs`
**Current pipeline:** `build → (validate + changelog in parallel) → publish-pypi` (missing TestPyPI, deploy-docs; has bugs)
**Required additions:**
```yaml
publish-testpypi:
  name: Publish to TestPyPI
  needs: [validate, changelog]
  runs-on: ubuntu-latest
  environment:
    name: testpypi
    url: https://test.pypi.org/p/adbc-poolhouse
  permissions:
    id-token: write
    contents: read
  steps:
    - uses: actions/download-artifact@v4
      with: { name: dist, path: dist/ }
    - uses: pypa/gh-action-pypi-publish@release/v1
      with:
        repository-url: https://test.pypi.org/legacy/

smoke-test-testpypi:
  name: Smoke-test from TestPyPI
  needs: [publish-testpypi]
  runs-on: ubuntu-latest
  steps:
    - uses: astral-sh/setup-uv@v7
    - name: Install from TestPyPI and smoke-test
      run: |
        uv venv smoke-env
        uv pip install --python smoke-env/bin/python \
          --index-url https://test.pypi.org/simple/ \
          --extra-index-url https://pypi.org/simple/ \
          adbc-poolhouse
        smoke-env/bin/python -c "from adbc_poolhouse import create_pool, DuckDBConfig; print('TestPyPI smoke OK')"

publish-pypi:
  needs: [smoke-test-testpypi]
  # ... (same as before but needs: smoke-test-testpypi not validate/changelog)

deploy-docs:
  name: Deploy docs to GitHub Pages
  needs: [publish-pypi]
  # ... uses actions/deploy-pages
```

### Pattern 5: Docs Author Skill Structure (mirrors cubano)
**What:** `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — same section headings as `cubano-docs-author/SKILL.md`, adapted for adbc-poolhouse.
**Cubano structure to mirror:**
- YAML frontmatter (name, description, allowed-tools)
- Audience section
- Voice section
- Workflow (Step 1: Classify, Step 2: Write per type, Step 3: Humanizer pass)
- Quality checklist

**Key adaptations from cubano:**
- Audience: Python async developers (FastAPI, SQLAlchemy-async) not data engineers
- Classification: Three types only (Quickstart, How-to Guide, API Reference) — not full Diataxis quadrants
- Tabbed content: ADBC driver variants if needed (not Snowflake vs Databricks SQL syntax)
- Quality checklist: From CONTEXT.md verbatim (5 items + `uv run mkdocs build --strict`)
- Humanizer pass: Same patterns to eliminate (same reference to global humanizer skill)

### Anti-Patterns to Avoid
- **Writing API reference manually**: `gen_ref_pages.py` auto-generates all `reference/*.md` files from source. Never hand-write files in `docs/src/reference/`.
- **Doctest-style Examples blocks**: Quickstart is validated by running against DuckDB in CI, not as doctests. Use plain code blocks, not `>>>` prompts, in prose guides.
- **Committing CHANGELOG.md to main**: The changelog is generated at release time as a CI artifact and used by the docs deploy step — it is not committed to the repo.
- **Using `PoolConfig` in import validation**: `PoolConfig` does not exist. The correct import check is `from adbc_poolhouse import create_pool, DuckDBConfig` (see Known Bug section below).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| API reference pages | Hand-write `docs/src/reference/*.md` | `gen_ref_pages.py` + mkdocstrings | Already configured; auto-generates from source |
| Changelog content | Write CHANGELOG.md manually | `git-cliff --latest` | `.cliff.toml` already configured; git-cliff reads conventional commit history |
| Wheel validation | Custom wheel inspection scripts | `unzip -l dist/*.whl \| grep py.typed` | Already in release.yml; simple and sufficient |
| TestPyPI publishing | Custom API token upload | `pypa/gh-action-pypi-publish@release/v1` with `repository-url` | Action handles OIDC exchange automatically |
| Docs deployment | Custom SSH/rsync to hosting | `actions/deploy-pages@v4` | GitHub Pages integration; already used in docs.yml |

**Key insight:** The hard part of this phase is content (docstrings, guide prose), not infrastructure. The toolchain is already in place.

---

## Common Pitfalls

### Pitfall 1: Cookiecutter Placeholder Bug in release.yml
**What goes wrong:** Line 67 of `release.yml` contains `import {{ cookiecutter.package_name }}` — a template placeholder that was never substituted. The wheel installation step will fail silently or raise a Python SyntaxError.
**Why it happens:** The project was bootstrapped from a cookiecutter template and this line was not updated.
**How to avoid:** Fix to `import adbc_poolhouse; print('Wheel installation OK')` before testing the workflow.
**Warning signs:** CI workflow step named "Test wheel installation" fails with unexpected errors.

### Pitfall 2: Python Matrix Version (3.14 vs 3.11/3.12)
**What goes wrong:** `release.yml` currently tests against `["3.11", "3.14"]` but CONTEXT.md specifies 3.11 and 3.12. Python 3.14 is not yet stable (as of Feb 2026) and `uv venv --python 3.14` may fail if the version is unavailable in the CI runner.
**How to avoid:** Change validate matrix to `["3.11", "3.12"]` per CONTEXT.md decision.

### Pitfall 3: PoolConfig Import Validation Error
**What goes wrong:** CONTEXT.md says the wheel validation should check `from adbc_poolhouse import create_pool, PoolConfig`. `PoolConfig` does not exist in the public API — `__all__` exports `create_pool`, all `*Config` classes, `WarehouseConfig`, `BaseWarehouseConfig`, `PoolhouseError`, `ConfigurationError`. The import validation will fail if `PoolConfig` is used.
**How to avoid:** Use `from adbc_poolhouse import create_pool, DuckDBConfig` as the import validation command.
**Confidence:** HIGH — verified against `src/adbc_poolhouse/__init__.py` `__all__` list.

### Pitfall 4: TestPyPI Trusted Publisher Must Be Pre-Registered
**What goes wrong:** The `publish-testpypi` job will fail with a 403 error if the trusted publisher is not registered on test.pypi.org before the first tag push.
**Why it happens:** OIDC trusted publishing requires pre-registration of the exact workflow filename. There is no fallback to API tokens when trusted publishing is configured.
**How to avoid:** Register trusted publishers on BOTH pypi.org and test.pypi.org before pushing the first tag. Required fields: repository owner (`anentropic`), repository name (`adbc-poolhouse`), workflow filename (`release.yml`), environment name (`pypi` / `testpypi`). Registration URLs: `https://pypi.org/manage/account/publishing/` and `https://test.pypi.org/manage/account/publishing/`.
**Warning signs:** OIDC exchange fails immediately on first release attempt.

### Pitfall 5: TestPyPI Install Requires Extra Index
**What goes wrong:** `pip install adbc-poolhouse` from TestPyPI fails because dependencies (pydantic-settings, sqlalchemy, etc.) are not on TestPyPI.
**How to avoid:** Use `--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/` so dependencies resolve from real PyPI.

### Pitfall 6: mkdocs --strict Fails on Missing Nav Pages
**What goes wrong:** Adding nav entries to `mkdocs.yml` for pages that don't have corresponding `.md` files causes `uv run mkdocs build --strict` to fail.
**How to avoid:** Create all guide `.md` files before updating `mkdocs.yml` nav, or update nav and files in the same commit. The build currently passes with the existing 3-item nav; adding Guides section entries without creating the files will break CI.

### Pitfall 7: gen_ref_pages.py Skips Private Modules
**What goes wrong:** Expecting `gen_ref_pages.py` to generate docs for internal modules (`_pool_factory.py`, `_drivers.py`, etc.). The script explicitly skips modules starting with `_`.
**Why it happens:** This is correct behavior — the script's `if any(part.startswith("_") for part in parts)` filter excludes all private modules.
**Impact:** Public API docs come from `__init__.py` imports, not from the internal modules directly. mkdocstrings renders the symbols via their public import paths.

### Pitfall 8: Docs Deploy in release.yml Needs GitHub Pages Permissions
**What goes wrong:** The `deploy-docs` job in `release.yml` needs `pages: write` and `id-token: write` permissions. If only declared at job level, they must be set correctly — the workflow-level `permissions: contents: read` does not grant Pages write.
**How to avoid:** Set `permissions` at the job level for `deploy-docs`, not at workflow level. Use the same pattern as `docs.yml` which already deploys successfully.

---

## Code Examples

### Google-Style Docstring for a Config Class (to apply to remaining classes)
```python
# Source: pattern from src/adbc_poolhouse/_duckdb_config.py (already complete)
class DuckDBConfig(BaseWarehouseConfig):
    """
    DuckDB warehouse configuration.

    Covers all DuckDB ADBC connection parameters. Pool tuning fields
    (pool_size, max_overflow, timeout, recycle) are inherited from
    BaseWarehouseConfig and loaded from DUCKDB_* environment variables.

    Example:
        DuckDBConfig(database='/data/warehouse.db', pool_size=5)
        DuckDBConfig()  # in-memory, pool_size=1 enforced by validator
    """
```

Note: Config class fields use attribute docstrings (string after assignment), not Args sections. `create_pool` is the primary function that needs Args/Returns/Raises — it already has them. Config classes need `Example:` blocks on `DuckDBConfig` and `SnowflakeConfig` only (key entry points per CONTEXT.md).

### TestPyPI Publish + Smoke-Test Jobs
```yaml
# Source: https://docs.pypi.org/trusted-publishers/using-a-publisher/
# and https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/

publish-testpypi:
  name: Publish to TestPyPI
  needs: [validate, changelog]
  runs-on: ubuntu-latest
  timeout-minutes: 10
  environment:
    name: testpypi
    url: https://test.pypi.org/p/adbc-poolhouse
  permissions:
    id-token: write
    contents: read
  steps:
    - name: Download distributions
      uses: actions/download-artifact@v4
      with:
        name: dist
        path: dist/
    - name: Publish to TestPyPI
      uses: pypa/gh-action-pypi-publish@release/v1
      with:
        repository-url: https://test.pypi.org/legacy/

smoke-test-testpypi:
  name: Smoke-test from TestPyPI
  needs: [publish-testpypi]
  runs-on: ubuntu-latest
  timeout-minutes: 10
  steps:
    - name: Set up uv
      uses: astral-sh/setup-uv@v7
      with:
        enable-cache: false
    - name: Install from TestPyPI and smoke-test
      run: |
        uv venv smoke-env
        uv pip install \
          --python smoke-env/bin/python \
          --index-url https://test.pypi.org/simple/ \
          --extra-index-url https://pypi.org/simple/ \
          adbc-poolhouse
        smoke-env/bin/python -c "from adbc_poolhouse import create_pool, DuckDBConfig; print('TestPyPI smoke OK')"
```

### Deploy Docs Job (add to release.yml after publish-pypi)
```yaml
# Source: pattern from .github/workflows/docs.yml (already working on main)
deploy-docs:
  name: Deploy docs to GitHub Pages
  needs: [publish-pypi]
  runs-on: ubuntu-latest
  timeout-minutes: 10
  permissions:
    contents: read
    pages: write
    id-token: write
  concurrency:
    group: docs-deploy
    cancel-in-progress: true
  environment:
    name: github-pages
    url: ${{ steps.deployment.outputs.page_url }}
  steps:
    - name: Checkout
      uses: actions/checkout@v6
      with:
        fetch-depth: 0
    - name: Set up uv
      uses: astral-sh/setup-uv@v7
      with:
        enable-cache: true
        cache-dependency-glob: "uv.lock"
    - name: Sync docs dependencies
      run: uv sync --locked --group docs
    - name: Build docs
      run: uv run mkdocs build --strict
    - name: Upload pages artifact
      uses: actions/upload-pages-artifact@v3
      with:
        path: site/
    - name: Deploy to GitHub Pages
      id: deployment
      uses: actions/deploy-pages@v4
```

### Quickstart DuckDB Example (for docs/src/index.md / getting-started.md)
```python
# This pattern validates the quickstart in CI against a real DuckDB connection
from adbc_poolhouse import DuckDBConfig, create_pool

# File-backed database (shareable across pool connections)
config = DuckDBConfig(database="/tmp/warehouse.db")
pool = create_pool(config)

# Use a connection
with pool.connect() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT 42 AS answer")
    row = cursor.fetchone()
    print(row)  # (42,)

# Teardown
pool.dispose()
pool._adbc_source.close()
```

### Docs Author Skill Frontmatter (SKILL.md)
```yaml
---
name: adbc-poolhouse-docs-author
description: Write adbc-poolhouse documentation. Applies project voice, Google-style docstrings, and humanizer pass. Use in PLAN.md execution_context for all phases >= 7.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
---
```

### CLAUDE.md Content Pattern
```markdown
# adbc-poolhouse — Project Instructions

## Documentation Quality Gate

For all plans in phases >= 7, include the docs-author skill in execution_context:

@.claude/skills/adbc-poolhouse-docs-author/SKILL.md

Documentation is a completion requirement for every phase from Phase 7 onwards,
not only plans explicitly labelled as documentation tasks.
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| API token in GitHub Secrets for PyPI | OIDC trusted publisher (no token stored) | More secure; tokens auto-expire; no secret rotation needed |
| Manual CHANGELOG.md | git-cliff from conventional commits | Automated; consistent format; already configured |
| Docs deploy on every main push | Docs deploy on tag push (after publish) | Versioned releases align code and docs |
| Writing API docs as hand-maintained `.rst` or `.md` | mkdocstrings with gen_ref_pages.py | Auto-generated from source; always in sync |

**Deprecated/outdated:**
- `setup.py` / `setup.cfg`: Project uses `uv_build` + `pyproject.toml` — do not add setup.py
- `twine upload`: Project uses `pypa/gh-action-pypi-publish` — do not add twine to workflow
- Sphinx: Project chose MkDocs — do not add Sphinx configuration

---

## Open Questions

1. **`PoolConfig` import in CONTEXT.md wheel validation**
   - What we know: CONTEXT.md says `from adbc_poolhouse import create_pool, PoolConfig` but `PoolConfig` does not exist in `__all__`
   - What's unclear: Whether the user intended `DuckDBConfig`, `SnowflakeConfig`, or a generic config alias that should be created
   - Recommendation: Use `from adbc_poolhouse import create_pool, DuckDBConfig` in release.yml validation (DuckDB is the always-available driver for smoke tests); note the discrepancy in plan comments

2. **Changelog page content source**
   - What we know: CONTEXT.md says changelog page is "auto-generated from git-cliff output; appears in nav" but git-cliff runs at release time as a CI artifact, not committed to the repo
   - What's unclear: How the static `docs/src/changelog.md` stays current between releases
   - Recommendation: Create a static `docs/src/changelog.md` that is committed to the repo and updated as part of the release workflow (download the changelog artifact and commit it, or maintain it manually). Alternatively, use mkdocs-include-markdown-plugin to include a committed CHANGELOG.md. The simplest approach: commit CHANGELOG.md to the repo root and symlink/include it in docs. Plan should decide: the release.yml could commit CHANGELOG.md back to main after generating it, or docs/src/changelog.md can be a manually maintained placeholder that references the GitHub releases page.

3. **Version matching check in validate job**
   - What we know: CONTEXT.md requires "version in package matches the git tag" as wheel validation step
   - What's unclear: How to extract the version from the wheel metadata to compare against `GITHUB_REF_NAME`
   - Recommendation: `unzip -p dist/*.whl "*/METADATA" | grep "^Version:" | cut -d' ' -f2` compared against `${GITHUB_REF_NAME#v}` (strips `v` prefix from tag)

---

## Sources

### Primary (HIGH confidence)
- Direct file inspection: `mkdocs.yml`, `pyproject.toml`, `release.yml`, `docs.yml`, `.cliff.toml`, `gen_ref_pages.py`, `src/adbc_poolhouse/__init__.py`, `src/adbc_poolhouse/_pool_factory.py`, all config modules — verified current state of infrastructure
- `/Users/paul/Documents/Dev/Personal/cubano/.claude/skills/cubano-docs-author/SKILL.md` — cubano skill structure confirmed
- `/Users/paul/.claude/skills/humanizer/SKILL.md` — humanizer skill patterns confirmed

### Secondary (MEDIUM confidence)
- [PyPI Trusted Publishers docs](https://docs.pypi.org/trusted-publishers/using-a-publisher/) — OIDC fields and TestPyPI configuration verified
- [Python Packaging User Guide — GitHub Actions publishing](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/) — publish-to-testpypi job YAML pattern verified
- [mkdocstrings Python docs](https://mkdocstrings.github.io/python/) — Google docstring format confirmed
- [Griffe docstring guide](https://mkdocstrings.github.io/griffe/guide/users/recommendations/docstrings/) — Args/Returns/Raises formatting confirmed

### Tertiary (LOW confidence)
- git-cliff setup-git-cliff action alternative (kenji-miyake/setup-git-cliff@v1) — project already uses curl binary install, no change needed

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all tools already declared in pyproject.toml; versions verified from file
- Architecture patterns: HIGH — current state fully inspected from actual project files
- Pitfalls: HIGH for bugs (verified from file inspection); MEDIUM for TestPyPI registration flow (verified from official docs)
- Release workflow: HIGH for existing structure; MEDIUM for new jobs (based on official PyPA guide)

**Research date:** 2026-02-26
**Valid until:** 2026-03-28 (stable tooling; PyPI OIDC API unlikely to change)
