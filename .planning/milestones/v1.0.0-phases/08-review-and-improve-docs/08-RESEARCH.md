# Phase 8: review-and-improve-docs - Research

**Researched:** 2026-02-28
**Domain:** MkDocs documentation authoring, Python contextlib/contextmanager API design, git-cliff changelog generation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Phase Boundary**

Review and improve the documentation established in Phase 7 — quickstart (index.md), four guide pages, per-warehouse guides (new), and changelog. No new library capabilities are in scope.

**Already implemented (during discussion)**
- Removed "Snapshot testing in CI" section from `guides/snowflake.md` — internal concern, not user-facing
- Rewrote dbt profiles section in `guides/consumer-patterns.md` using `dbt.config.profile.Profile.from_raw_profiles` + `ProfileRenderer` — handles Jinja (`env_var()` calls); old raw YAML approach silently breaks with Jinja templates
- Renamed section to "Loading credentials from dbt"; added honest caveat that `from_raw_profiles` is internal dbt-core API, stable across 1.x

**index.md additions**
- After the "Installation" section: add a new section explaining that adbc-poolhouse also requires an ADBC driver for the target warehouse. Include a list of all supported warehouses with install commands and links (PyPI packages where available, Foundry path for Databricks/Redshift/Trino/MSSQL/Teradata)
- "First pool in five minutes" section: add a list of typed config class names (DuckDBConfig, SnowflakeConfig, BigQueryConfig, etc.) so readers can see all options at a glance

**Per-warehouse guide pages**
- Create one guide page per warehouse following the Snowflake guide structure: install the extra, required/notable fields with a code example, env var prefix, see-also
- All warehouses get a page: DuckDB, Snowflake (already exists), BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL, Teradata
- MSSQL and Teradata: stub pages only (install + env var prefix, no auth examples) — field coverage for these is best-effort and unverified
- Update mkdocs.yml nav to include all warehouse pages

**Public cleanup API**
- Add a public `close_pool(pool)` helper function to replace the current `pool.dispose()` + `pool._adbc_source.close()` two-step pattern
- Also expose as a context manager so callers can use `with managed_pool(config) as pool: ...`
- Update all docs (quickstart, pool-lifecycle guide, consumer patterns) to use the new public API — eliminate all references to `pool._adbc_source`

**Pool tuning documentation**
- `guides/pool-lifecycle.md`: add a "Tuning the pool" section with a brief summary of the available kwargs and their defaults
- `guides/configuration.md`: add a full kwargs table (pool_size, max_overflow, timeout, recycle, pre_ping) with types, defaults, and a sentence on when to change each

**Changelog**
- Wire `git-cliff` to generate `docs/src/changelog.md` from commit history
- Should produce an initial entry covering all commits to date

**Prose quality**
- Terse, technical voice — no hand-holding, trust the reader; keep existing style
- Apply humanizer pass to all new or substantially rewritten prose
- New per-warehouse pages follow the same structural pattern as the existing Snowflake guide

### Claude's Discretion
- Exact wording and structure of the ADBC driver install section on index.md
- Whether Foundry-path warehouses need extra explanation vs PyPI warehouses
- git-cliff configuration details (tag pattern, template)
- How to structure the context manager API (standalone function vs class)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

## Summary

Phase 8 is a pure documentation improvement phase. No new library features are being added except two public API additions that exist to clean up documentation: `close_pool(pool)` and `managed_pool(config)`. These additions exist because the existing pattern (`pool.dispose()` + `pool._adbc_source.close()`) exposes a private attribute (`_adbc_source`) and is a two-step operation that is easy to get wrong.

The bulk of work is: nine new per-warehouse guide pages (following the established Snowflake guide pattern), updates to three existing pages (index.md, pool-lifecycle.md, configuration.md), and wiring git-cliff to generate `docs/src/changelog.md`. All pages must pass `uv run mkdocs build --strict` and receive a humanizer pass.

One important gap to flag: **TeradataConfig does not exist in the codebase.** The CONTEXT.md decision lists Teradata as a warehouse requiring a stub page, but there is no `TeradataConfig` class, no `_teradata_config.py`, and no `TERADATA_` env prefix anywhere in the source. The stub page can only say the driver is Foundry-distributed and that the config class is not yet implemented. The planner must handle this carefully.

**Primary recommendation:** Implement `close_pool` and `managed_pool` in `_pool_factory.py` first, export them from `__init__.py`, then update all existing doc pages to use the new API before writing new per-warehouse guide pages. This ensures the eliminated `_adbc_source` references are gone before new pages are written.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mkdocs | >=1.6.0 (already in pyproject.toml) | Build and validate docs | Already in use |
| mkdocs-material | >=9.5.0,<9.7.0 (pinned due to CI issue) | Theme with admonition/tabbed/superfences | Already in use |
| mkdocstrings[python] | >=0.26.0 | Auto-generate API reference from docstrings | Already in use |
| mkdocs-gen-files | >=0.5.0 | Run `gen_ref_pages.py` at build time | Already in use |
| mkdocs-literate-nav | >=0.6.0 | Nav from generated SUMMARY.md | Already in use |
| git-cliff | 2.7.0 (pinned in release.yml) | Generate changelog from git history | Already configured in `.cliff.toml` and `release.yml` |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| uv run mkdocs build --strict | N/A | Validate docs build | After every docs change |
| contextlib.contextmanager | stdlib | Implement `managed_pool` context manager | Building the context manager API |
| Python `__all__` | stdlib | Export new public API symbols | When adding `close_pool`, `managed_pool` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `contextlib.contextmanager` | `contextlib.AbstractContextManager` class | `@contextmanager` generator function is simpler and idiomatic for this use case; class only needed if subclassing is required |
| `git-cliff --unreleased` | `git-cliff` (no flags) | `--unreleased` is explicit and correct for a repo with no tags; no-flag form also works but less explicit |

**Installation:** All dependencies already installed. No new packages needed.

---

## Architecture Patterns

### Recommended Project Structure

No structural changes to the project. Additions only:

```
src/adbc_poolhouse/
├── _pool_factory.py    # Add close_pool() and managed_pool() here
└── __init__.py         # Add close_pool, managed_pool to __all__

docs/src/
├── index.md            # Update: ADBC driver section, config class list
├── changelog.md        # Update: wire git-cliff output here
└── guides/
    ├── pool-lifecycle.md     # Update: new public API, tuning section
    ├── configuration.md      # Update: full kwargs table with pre_ping
    ├── consumer-patterns.md  # Update: use close_pool instead of _adbc_source
    ├── snowflake.md          # Already complete — no changes needed
    ├── duckdb.md             # NEW
    ├── bigquery.md           # NEW
    ├── postgresql.md         # NEW
    ├── flightsql.md          # NEW
    ├── databricks.md         # NEW
    ├── redshift.md           # NEW
    ├── trino.md              # NEW
    ├── mssql.md              # NEW
    └── teradata.md           # NEW (stub only — no config class exists)
```

### Pattern 1: close_pool and managed_pool in _pool_factory.py

**What:** Two new public functions that wrap the two-step dispose pattern and expose a context manager.
**When to use:** Every place currently showing `pool.dispose()` + `pool._adbc_source.close()`.

```python
# Source: Python stdlib contextlib documentation
import contextlib
from typing import TYPE_CHECKING, Iterator

import sqlalchemy.pool

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig


def close_pool(pool: sqlalchemy.pool.QueuePool) -> None:
    """Dispose the pool and close the underlying ADBC source connection.

    Args:
        pool: A pool returned by ``create_pool``.
    """
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]


@contextlib.contextmanager
def managed_pool(
    config: WarehouseConfig, **kwargs: object
) -> Iterator[sqlalchemy.pool.QueuePool]:
    """Context manager that creates a pool and closes it on exit.

    Args:
        config: A warehouse config model instance (e.g. ``DuckDBConfig``).
        **kwargs: Forwarded to ``create_pool`` (pool_size, max_overflow, etc.).

    Yields:
        A configured ``sqlalchemy.pool.QueuePool``.
    """
    pool = create_pool(config, **kwargs)
    try:
        yield pool
    finally:
        close_pool(pool)
```

**Type notes:**
- `close_pool` needs `# type: ignore[attr-defined]` on `_adbc_source.close()` since `_adbc_source` is dynamically attached.
- `managed_pool` kwargs typing: `**kwargs: object` matches basedpyright strict mode for forwarding kwargs to `create_pool`. An alternative is to use `**kwargs: Any` with `# type: ignore`, or spell out all parameters explicitly. Spelling them out explicitly is the correct strict-mode approach and matches the existing `create_pool` signature.
- `managed_pool` should re-raise exceptions from the `with` block — `try/finally` (not `try/except`) ensures pool cleanup regardless of success or failure.

### Pattern 2: Per-Warehouse Guide Structure

**What:** Follows the existing `guides/snowflake.md` pattern exactly.
**When to use:** All nine new warehouse guide pages.

```markdown
# [Warehouse] guide

Install the [warehouse] extra:

```bash
pip install adbc-poolhouse[[extra]]
```

Or with uv:

```bash
uv add "adbc-poolhouse[[extra]]"
```

## [Auth methods / Connection]

[Config class name] supports [description]. [Code example with the config class.]

## Loading from environment variables

[Config class name] reads all fields from environment variables with the `[PREFIX]_` prefix:

```bash
export [PREFIX]_FIELD=value
```

```python
config = [Config]()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Consumer patterns](consumer-patterns.md) — ...
```

**Foundry page note:** For Databricks, Redshift, Trino, MSSQL — the "install" section cannot show `pip install adbc-poolhouse[[extra]]` because there is no PyPI extra for these. Instead: state the driver is not on PyPI and direct users to the Foundry installation guide.

**Teradata stub note:** No `TeradataConfig` class exists in the package. The Teradata page must be a genuine stub: "TeradataConfig is not yet implemented. The ADBC Teradata driver is distributed via the ADBC Driver Foundry, not PyPI." Do not invent fields or env prefixes that don't exist in code.

### Pattern 3: Per-Warehouse Guides in mkdocs.yml Nav

Update `nav:` in `mkdocs.yml` to add a "Warehouse Guides" sub-section under `Guides:`:

```yaml
nav:
  - Getting Started: index.md
  - Guides:
    - Pool Lifecycle: guides/pool-lifecycle.md
    - Consumer Patterns: guides/consumer-patterns.md
    - Configuration Reference: guides/configuration.md
    - Warehouse Guides:
      - Snowflake: guides/snowflake.md
      - DuckDB: guides/duckdb.md
      - BigQuery: guides/bigquery.md
      - PostgreSQL: guides/postgresql.md
      - FlightSQL: guides/flightsql.md
      - Databricks: guides/databricks.md
      - Redshift: guides/redshift.md
      - Trino: guides/trino.md
      - MSSQL: guides/mssql.md
      - Teradata: guides/teradata.md
  - API Reference: reference/
  - Changelog: changelog.md
```

### Pattern 4: git-cliff to populate docs/src/changelog.md

**What:** Run git-cliff to generate the changelog content and write it to `docs/src/changelog.md`.
**Key fact:** The repo has no tags yet (confirmed: `git tag` returns nothing). The `--unreleased` flag handles this case correctly.

```bash
# Install git-cliff (binary, not in pyproject.toml)
# Method 1: cargo install (if cargo available)
# Method 2: download pre-built binary (matches release.yml which uses v2.7.0)

# Generate changelog from all commits (repo has no tags)
git-cliff --unreleased --output docs/src/changelog.md
```

The existing `changelog.md` has a stub comment: `<!-- Content below is generated by git-cliff at release time -->`. Replace the file with proper git-cliff output.

**cliff.toml is already configured.** The `.cliff.toml` in the repo root uses conventional commits, groups by type (Features/Bug Fixes/Documentation/etc.), and filters unconventional commits. All project commits use conventional commit format — the generated changelog will have entries.

**Note on what will be generated:** Because `filter_unconventional = true` in `.cliff.toml`, commits like `docs(08): capture phase context...` will be included under "Documentation", `feat(07-01): create...` under "Features", etc. The result will be a single "unreleased" section listing all grouped commits to date.

### Anti-Patterns to Avoid

- **Referencing `pool._adbc_source` in any docs:** This private attribute must not appear anywhere in user-facing documentation after this phase. All disposal patterns must use `close_pool(pool)`.
- **Hand-writing files in `docs/src/reference/`:** These are auto-generated by `gen_ref_pages.py`. Any hand-written reference file will be ignored or overwritten at build time.
- **Inventing Teradata config fields:** There is no `TeradataConfig` class in the package. The stub page must not invent field names, env var prefixes, or auth examples. Only what exists in source should appear in docs.
- **Using `--latest` with git-cliff:** The repo has no tags, so `--latest` would fail or produce empty output. Use `--unreleased` (covers all commits when no tags exist).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Context manager for pool lifecycle | Custom class with `__enter__`/`__exit__` | `@contextlib.contextmanager` generator function | Idiomatic Python, less code, easier to read |
| Changelog generation | Manual changelog writing | `git-cliff --unreleased --output docs/src/changelog.md` | Already configured; `.cliff.toml` is in place |
| API reference pages | Hand-written markdown in `docs/src/reference/` | `gen_ref_pages.py` + mkdocstrings | Auto-generates from source; hand-written pages would be overwritten |
| "Strict mode" docs validation | Custom link-checking script | `uv run mkdocs build --strict` | Built into mkdocs; catches broken cross-references, missing pages, and invalid config |

**Key insight:** The entire documentation toolchain is already in place. Phase 8 is content work (writing pages and updating existing ones) and two small API additions, not tooling setup.

---

## Common Pitfalls

### Pitfall 1: managed_pool kwargs forwarding with basedpyright strict mode

**What goes wrong:** Using `**kwargs: Any` or `**kwargs: object` in `managed_pool` and forwarding to `create_pool(**kwargs)` will trigger a basedpyright strict mode error because the call site loses type information.
**Why it happens:** basedpyright strict cannot verify that the untyped kwargs dict matches the typed signature of `create_pool`.
**How to avoid:** Either spell out all pool tuning parameters explicitly in `managed_pool`'s signature (matching `create_pool`), or use `# type: ignore[arg-type]` with a comment explaining why. The explicit signature approach is cleanest and consistent with the existing codebase style.
**Warning signs:** Pre-commit basedpyright step fails on the `managed_pool` implementation.

### Pitfall 2: mkdocs strict mode failing on new cross-references

**What goes wrong:** New per-warehouse guide pages link to each other or to configuration.md, but the link paths are wrong (e.g., `../configuration.md` vs `configuration.md`).
**Why it happens:** MkDocs resolves relative links from the page's location. Files in `docs/src/guides/` should use `configuration.md` (same directory), not `../guides/configuration.md`.
**How to avoid:** Follow the pattern in existing guides — every "See also" link in snowflake.md uses bare filenames like `configuration.md` and `consumer-patterns.md`. Copy this pattern.
**Warning signs:** `uv run mkdocs build --strict` fails with "Doc file ... contains a link ... that does not point to a valid file".

### Pitfall 3: mkdocs.yml nav listing pages that don't yet exist

**What goes wrong:** Adding nav entries for all ten warehouse guide pages before the files exist causes `mkdocs build --strict` to fail.
**Why it happens:** MkDocs strict mode treats missing nav files as errors.
**How to avoid:** Create all new guide files (even stubs) before or in the same commit as the nav update.
**Warning signs:** `uv run mkdocs build --strict` fails with "Config value 'nav': The file '...' was included in the navigation, but does not exist".

### Pitfall 4: Teradata stub page with invented content

**What goes wrong:** Writing a Teradata guide that lists fields like `TERADATA_HOST`, `TERADATA_USER`, etc. when no `TeradataConfig` class exists.
**Why it happens:** The previous REQUIREMENTS.md notes that Teradata field coverage is "best-effort and unverified" and referenced `TeradataConfig` as a planned implementation. It was never implemented.
**How to avoid:** The Teradata page must be an honest stub: state the config class is not yet available, the driver is Foundry-distributed, and direct users to file an issue or check GitHub for updates.
**Warning signs:** Any code block on the Teradata page that references `TeradataConfig` without it being importable from the package.

### Pitfall 5: close_pool not exported from __all__

**What goes wrong:** `close_pool` and `managed_pool` are added to `_pool_factory.py` but not added to `__init__.py`'s `__all__` list.
**Why it happens:** Easy to forget when adding new public symbols to an internal module.
**How to avoid:** Add `close_pool` and `managed_pool` to both the import list and `__all__` in `__init__.py` in the same commit as the implementation.
**Warning signs:** `from adbc_poolhouse import close_pool` raises `ImportError` after the change.

### Pitfall 6: git-cliff filtering out all commits

**What goes wrong:** git-cliff generates an empty or near-empty changelog because `filter_unconventional = true` in `.cliff.toml` removes commits that don't follow conventional commit format.
**Why it happens:** Some commits in the project use non-standard prefixes or include scope notation that git-cliff's parsers don't recognise.
**How to avoid:** Inspect the generated changelog after running git-cliff; if it's sparse, review which commit messages match `^feat`, `^fix`, `^docs`, `^perf`, `^refactor`, `^style`, `^test`, or `^chore`. The project consistently uses conventional commits so this should be fine.
**Warning signs:** The generated `changelog.md` has fewer entries than expected given the 112-commit history.

---

## Code Examples

### close_pool implementation

```python
# Source: contextlib Python stdlib docs + existing _pool_factory.py patterns

def close_pool(pool: sqlalchemy.pool.QueuePool) -> None:
    """Dispose a pool and close its underlying ADBC source connection.

    Replaces the two-step pattern ``pool.dispose()`` followed by
    ``pool._adbc_source.close()``. Always call this instead of calling
    ``pool.dispose()`` directly to avoid leaving the ADBC source connection open.

    Args:
        pool: A pool returned by :func:`create_pool`.
    """
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]
```

### managed_pool implementation (explicit signature)

```python
# Source: contextlib Python stdlib docs

import contextlib
from collections.abc import Iterator

@contextlib.contextmanager
def managed_pool(
    config: WarehouseConfig,
    *,
    pool_size: int = 5,
    max_overflow: int = 3,
    timeout: int = 30,
    recycle: int = 3600,
    pre_ping: bool = False,
) -> Iterator[sqlalchemy.pool.QueuePool]:
    """Context manager that creates a pool and closes it on exit.

    The pool is created when the ``with`` block is entered and closed
    (via :func:`close_pool`) when the block exits, whether it exits normally
    or raises an exception.

    Args:
        config: A warehouse config model instance (e.g. ``DuckDBConfig``).
        pool_size: Number of connections to keep in the pool. Default: 5.
        max_overflow: Extra connections allowed above pool_size. Default: 3.
        timeout: Seconds to wait for a connection before raising. Default: 30.
        recycle: Seconds before a connection is recycled. Default: 3600.
        pre_ping: Whether to ping connections before checkout. Default: False.

    Yields:
        A configured ``sqlalchemy.pool.QueuePool``.

    Example:
        from adbc_poolhouse import DuckDBConfig, managed_pool

        with managed_pool(DuckDBConfig(database='/tmp/wh.db')) as pool:
            with pool.connect() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1')
    """
    pool = create_pool(
        config,
        pool_size=pool_size,
        max_overflow=max_overflow,
        timeout=timeout,
        recycle=recycle,
        pre_ping=pre_ping,
    )
    try:
        yield pool
    finally:
        close_pool(pool)
```

### Updated quickstart example (index.md)

```python
# After this phase, the quickstart dispose pattern becomes:
from adbc_poolhouse import DuckDBConfig, create_pool, close_pool

config = DuckDBConfig(database="/tmp/warehouse.db")
pool = create_pool(config)

with pool.connect() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT 42 AS answer")
    row = cursor.fetchone()
    print(row)  # (42,)

close_pool(pool)
```

Or with context manager:

```python
from adbc_poolhouse import DuckDBConfig, managed_pool

with managed_pool(DuckDBConfig(database="/tmp/warehouse.db")) as pool:
    with pool.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 42 AS answer")
        row = cursor.fetchone()
        print(row)  # (42,)
```

### git-cliff command to generate docs changelog

```bash
# Run from repo root (requires git-cliff installed)
git-cliff --unreleased --output docs/src/changelog.md
```

The `.cliff.toml` in the repo root is used automatically. No additional config is needed.

To install git-cliff for local use (not yet in pyproject.toml dev deps):

```bash
# Option 1: cargo (if Rust toolchain available)
cargo install git-cliff

# Option 2: brew (macOS)
brew install git-cliff

# Option 3: download binary matching release.yml (v2.7.0)
curl -L https://github.com/orhun/git-cliff/releases/download/v2.7.0/git-cliff-2.7.0-aarch64-apple-darwin.tar.gz | tar xz
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pool.dispose()` + `pool._adbc_source.close()` | `close_pool(pool)` | Phase 8 | Eliminates private attribute exposure in docs |
| `pool._adbc_source.close()` in pytest fixtures | `close_pool(pool)` in pytest fixtures | Phase 8 | Cleaner teardown pattern |
| No context manager | `managed_pool(config) as pool` | Phase 8 | Enables safe pool lifecycle in scripts and short-lived services |
| Stub changelog.md (link to GitHub Releases only) | Populated changelog.md from git-cliff | Phase 8 | Users can read changelog without leaving the docs site |

**Deprecated/outdated after this phase:**
- `pool._adbc_source.close()`: still works internally but should not appear in any documentation
- The two-step `pool.dispose()` + `pool._adbc_source.close()` pattern: replaced by `close_pool(pool)`

---

## Open Questions

1. **TeradataConfig does not exist**
   - What we know: No `_teradata_config.py`, no `TeradataConfig` class, no `TERADATA_` env prefix anywhere in the source.
   - What's unclear: The CONTEXT.md decision says to create a stub Teradata page. A stub page for a non-existent config class is unusual and could mislead users.
   - Recommendation: The stub page should be upfront about the class not existing yet: "TeradataConfig is planned but not yet implemented. The ADBC Teradata driver is distributed via the ADBC Driver Foundry." Do not list fields, env var prefixes, or code examples.

2. **git-cliff installation for local development**
   - What we know: git-cliff is not in pyproject.toml (not in dev deps), only installed as a binary in the release.yml GitHub Actions workflow (v2.7.0).
   - What's unclear: Should git-cliff be added to pyproject.toml dev deps (there is no Python package for git-cliff — it is a Rust binary), or should the plan include a step to install it via cargo/brew before running?
   - Recommendation: The plan should include a one-time local install step (`brew install git-cliff` or download the binary) then run the command, then commit the result. Do not add git-cliff to pyproject.toml — it is a Rust binary and not installable via pip/uv.

3. **managed_pool signature: explicit params vs **kwargs**
   - What we know: basedpyright strict mode (active in this project) rejects untyped `**kwargs` forwarding in many cases.
   - What's unclear: Should `managed_pool` repeat all five pool kwargs explicitly, or use `**kwargs: Any` with a type: ignore?
   - Recommendation: Spell out all five kwargs explicitly (matching `create_pool`'s signature). This is consistent with the existing codebase style and avoids type-ignore comments.

---

## Validation Architecture

> Nyquist validation: `workflow.nyquist_validation` is not set in `.planning/config.json` — skipping this section.

(The config.json does not have `workflow.nyquist_validation: true`; the workflow block only has `research`, `plan_check`, `verifier`, and `auto_advance` keys.)

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection — `src/adbc_poolhouse/__init__.py`, `_pool_factory.py`, `_base_config.py`, `_duckdb_config.py`, `_bigquery_config.py`, `_mssql_config.py`, `_databricks_config.py`
- Direct codebase inspection — `docs/src/index.md`, `docs/src/guides/snowflake.md`, `docs/src/guides/pool-lifecycle.md`, `docs/src/guides/consumer-patterns.md`, `docs/src/guides/configuration.md`
- Direct codebase inspection — `mkdocs.yml`, `.cliff.toml`, `.github/workflows/release.yml`, `pyproject.toml`
- `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — project docs skill (voice, workflow, quality checklist)
- `.planning/phases/08-review-and-improve-docs/08-CONTEXT.md` — locked decisions

### Secondary (MEDIUM confidence)
- git-cliff official docs (https://git-cliff.org/docs/usage/examples/) — `--unreleased` flag behaviour, `--output` flag
- Python stdlib contextlib documentation — `@contextmanager` pattern

### Tertiary (LOW confidence)
- WebSearch: git-cliff behaviour with repos that have no tags — confirmed `--unreleased` is the correct flag, but not tested against this specific repo

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all tools already in use in the project; verified by direct inspection
- Architecture: HIGH — patterns derived from existing code and docs; `close_pool`/`managed_pool` design is standard Python stdlib contextmanager usage
- Pitfalls: HIGH — derived from direct inspection of the codebase (TeradataConfig absence confirmed, basedpyright strict mode confirmed, mkdocs strict mode confirmed)
- git-cliff usage: MEDIUM — flags verified via official docs fetch; not tested locally (git-cliff not installed)

**Research date:** 2026-02-28
**Valid until:** 2026-03-30 (stable toolchain; mkdocs-material pinned; git-cliff v2.7.0 pinned in CI)
