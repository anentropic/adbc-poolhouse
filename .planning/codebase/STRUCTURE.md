# Codebase Structure

**Analysis Date:** 2026-02-23

## Directory Layout

```
adbc-poolhouse/
├── src/
│   └── adbc_poolhouse/       # Package source code (src layout)
│       ├── __init__.py       # Public API exports (currently empty __all__)
│       └── py.typed          # PEP 561 marker — package ships type info
├── tests/                    # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures (currently empty)
│   └── test_adbc_poolhouse.py # Tests (currently only smoke test)
├── docs/                     # Documentation source (MkDocs)
│   ├── src/                  # Markdown source files
│   │   └── index.md          # Docs homepage
│   └── scripts/
│       └── gen_ref_pages.py  # Auto-generates API reference pages from src
├── .github/
│   └── workflows/
│       ├── ci.yml            # CI: typecheck + lint + format + test on push
│       ├── pr.yml            # PR: coverage comment posted to pull requests
│       ├── docs.yml          # Docs: build and deploy to GitHub Pages on main
│       └── release.yml       # Release: build, validate, changelog, PyPI publish
├── _notes/                   # Design notes (not distributed)
│   └── design-discussion.md  # Origin story, scope decisions, architecture rationale
├── .planning/                # GSD planning documents (not distributed)
│   └── codebase/             # Codebase analysis docs
├── pyproject.toml            # Build config, dependencies, tool config (ruff, basedpyright)
├── uv.lock                   # Locked dependency manifest
├── mkdocs.yml                # MkDocs site configuration
├── .pre-commit-config.yaml   # Pre-commit hooks (ruff, basedpyright, uv-lock, blacken-docs)
├── .python-version           # Python version pin: 3.14 (for pyenv/asdf)
├── .cliff.toml               # git-cliff changelog generation config
├── AGENTS.md                 # Guidance for AI coding assistants
├── DEVELOP.md                # Developer guide (setup, quality gates, conventions)
├── README.md                 # User-facing documentation
└── LICENSE                   # MIT license
```

## Directory Purposes

**`src/adbc_poolhouse/`:**
- Purpose: All package source code, using PEP 517 src layout
- Contains: Python modules that form the public and private API
- Key files:
  - `src/adbc_poolhouse/__init__.py`: Public API surface — everything in `__all__` is the library interface
  - `src/adbc_poolhouse/py.typed`: Empty marker file signalling PEP 561 compliance (type info shipped)

**`tests/`:**
- Purpose: Pytest test suite, separate from source
- Contains: Test modules and shared fixtures
- Key files:
  - `tests/conftest.py`: Shared pytest fixtures (centralized, not co-located)
  - `tests/test_adbc_poolhouse.py`: Test modules named `test_<module_or_feature>.py`

**`docs/`:**
- Purpose: MkDocs documentation site source and build scripts
- Contains: Markdown content + Python script for auto-generating API reference
- Key files:
  - `docs/src/index.md`: Documentation homepage
  - `docs/scripts/gen_ref_pages.py`: Scans `src/` and auto-generates `reference/*.md` pages

**`.github/workflows/`:**
- Purpose: GitHub Actions CI/CD pipelines
- Contains: Four workflows covering different triggers (push, PR, main branch, release tag)

**`_notes/`:**
- Purpose: Design notes and decision records — not distributed in the package
- Contains: Pre-implementation design discussions
- Key files: `_notes/design-discussion.md` — full architecture rationale and scope decisions

## Key File Locations

**Entry Points:**
- `src/adbc_poolhouse/__init__.py`: Package entry point; all public symbols exported here

**Configuration:**
- `pyproject.toml`: Build backend (uv_build), project metadata, ruff + basedpyright tool config
- `mkdocs.yml`: Documentation site structure and mkdocstrings settings
- `.pre-commit-config.yaml`: Pre-commit hooks (linting, formatting, type checking, lockfile sync)
- `.cliff.toml`: Changelog generation configuration (conventional commits)
- `.python-version`: Python version pin for local dev (currently `3.14`)

**Core Logic:**
- `src/adbc_poolhouse/` (all new modules go here)

**Testing:**
- `tests/conftest.py`: Fixtures
- `tests/test_adbc_poolhouse.py`: Existing smoke test; add new `test_*.py` files here

**Documentation:**
- `docs/src/index.md`: Homepage
- `docs/scripts/gen_ref_pages.py`: API reference generator (runs during `mkdocs build`)

## Naming Conventions

**Files:**
- Source modules: `snake_case.py` (e.g. `snowflake_config.py`, `pool_factory.py`)
- Test files: `test_<feature_or_module>.py` (e.g. `test_snowflake_config.py`)
- No barrel re-exports in sub-modules — public surface defined in `__init__.py` only

**Directories:**
- Package name: `adbc_poolhouse` (snake_case, matching PyPI name `adbc-poolhouse`)
- All source under `src/` (src layout, not flat layout)

**Python symbols:**
- Functions: `snake_case`
- Classes/Config models: `PascalCase` (e.g. `SnowflakeConfig`, `DuckDBConfig`)
- Private helpers: `_snake_case` prefix (basedpyright `reportPrivateUsage = false` allows tests to access these)

## Where to Add New Code

**New warehouse config model:**
- Implementation: `src/adbc_poolhouse/<warehouse>_config.py`
- Export: Add to `__all__` in `src/adbc_poolhouse/__init__.py`
- Tests: `tests/test_<warehouse>_config.py`

**New core feature (e.g. pool factory, driver detection):**
- Implementation: `src/adbc_poolhouse/<feature>.py`
- Export (if public): Add to `__all__` in `src/adbc_poolhouse/__init__.py`
- Tests: `tests/test_<feature>.py`

**Shared test fixtures:**
- Location: `tests/conftest.py` (centralized, not per-file)

**Utilities / helpers:**
- Location: `src/adbc_poolhouse/_<name>.py` (private, prefixed with `_`)

**New public type or protocol:**
- Location: `src/adbc_poolhouse/_types.py` or inline in the relevant module
- Export via `__init__.py` if consumers need it

## Special Directories

**`_notes/`:**
- Purpose: Pre-implementation design notes and decision records
- Generated: No
- Committed: Yes
- Note: Not included in the built package distribution

**`.planning/`:**
- Purpose: GSD planning and codebase analysis documents
- Generated: By GSD map-codebase command
- Committed: Yes (excluded from pre-commit hooks via `exclude: ^\.planning/` in `.pre-commit-config.yaml`)

**`.venv/`:**
- Purpose: Local virtual environment managed by uv
- Generated: Yes (`uv sync --dev`)
- Committed: No (in `.gitignore`)

**`dist/`:**
- Purpose: Built wheel and source distribution artifacts
- Generated: Yes (`uv build`)
- Committed: No

**`site/`:**
- Purpose: Built MkDocs documentation site
- Generated: Yes (`mkdocs build`)
- Committed: No

---

*Structure analysis: 2026-02-23*
