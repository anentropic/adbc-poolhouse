# Technology Stack

**Analysis Date:** 2026-02-23

## Languages

**Primary:**
- Python 3.14 - All source code (`src/adbc_poolhouse/`, `tests/`)

**Secondary:**
- TOML - Configuration (`pyproject.toml`, `.cliff.toml`)
- YAML - CI/CD workflows (`.github/workflows/`)
- Markdown - Documentation (`docs/src/`, `README.md`, `DEVELOP.md`)

## Runtime

**Environment:**
- Python 3.14 (pinned in `.python-version`)
- Minimum supported: Python 3.11 (`requires-python = ">=3.11"` in `pyproject.toml`)
- CI tests against: Python 3.11 and 3.14

**Package Manager:**
- uv (modern Python package and project manager by Astral)
- Lockfile: `uv.lock` (present and committed)

## Frameworks

**Core:**
- None yet - project is early-stage (v0.1.0), source is an empty package skeleton at `src/adbc_poolhouse/__init__.py`

**Planned Core Dependencies (from design docs):**
- `pydantic-settings` - Typed warehouse config models (SnowflakeConfig, DuckDBConfig, etc.)
- `adbc-driver-*` packages - Apache Arrow ADBC drivers (per-warehouse optional deps)
- `adbc-driver-manager` - Foundry driver loader (fallback for non-PyPI drivers)
- `sqlalchemy` (pool submodule only) - `QueuePool` for connection pooling (not the ORM)

**Testing:**
- pytest >= 8.0.0 - Test runner
- pytest-cov >= 6.0.0 - Coverage reporting

**Build/Dev:**
- uv_build >= 0.9.18 - Build backend (`pyproject.toml` build-system)
- ruff >= 0.15.1 - Linting and formatting
- basedpyright >= 1.38.0 - Strict static type checking
- ipython >= 9.10.0 - Interactive Python shell for development
- pdbpp >= 0.12.0 - Enhanced Python debugger
- prek - Pre-commit hook runner (Rust-based, wraps `.pre-commit-config.yaml`)

**Documentation:**
- mkdocs >= 1.6.0 - Documentation site generator (`mkdocs.yml`)
- mkdocs-material >= 9.7.0 - Material theme
- mkdocstrings[python] >= 0.26.0 - Auto-generates API reference from docstrings
- mkdocs-gen-files >= 0.5.0 - Scripted page generation (`docs/scripts/gen_ref_pages.py`)
- mkdocs-literate-nav >= 0.6.0 - Navigation from SUMMARY.md
- mkdocs-section-index >= 0.3.0 - Section index pages

## Key Dependencies

**Current runtime dependencies:**
- None (`dependencies = []` in `pyproject.toml`) - all planned, not yet implemented

**Planned critical dependencies (per `_notes/design-discussion.md`):**
- `pydantic-settings` - Config models with env-var support
- `sqlalchemy` (pool only) - `QueuePool` wrapping ADBC dbapi connections
- `adbc-driver-snowflake` - Snowflake ADBC driver (v1 production target)
- `duckdb` - DuckDB driver (v1 testing/dev target)
- `adbc-driver-manager` - Foundry driver manager for warehouse drivers not on PyPI

## Configuration

**Environment:**
- No `.env` file present
- Planned: Warehouse credentials via Pydantic BaseSettings (reads from env vars automatically)

**Build:**
- `pyproject.toml` - Single source of truth for project metadata, deps, tool config
- `uv.lock` - Dependency lockfile
- `.python-version` - Python version pin (3.14, used by uv/pyenv/asdf)

**Code Quality:**
- `pyproject.toml` `[tool.ruff]` - Line length 100, target Python 3.11
- `pyproject.toml` `[tool.ruff.lint]` - Enabled rule sets: E, F, W, I (isort), UP, B, SIM, TCH, D (docstrings)
- `pyproject.toml` `[tool.basedpyright]` - Strict mode, pythonVersion 3.14
- `.pre-commit-config.yaml` - Hooks: trailing-whitespace, end-of-file, JSON/TOML/YAML check, ruff, uv-lock, basedpyright, blacken-docs

**Documentation:**
- `mkdocs.yml` - MkDocs configuration, Google docstring style, Material theme
- Docstring convention: D213 (summary on second line of multi-line docstrings)

## Platform Requirements

**Development:**
- uv installed
- Python 3.11+
- prek installed (`uv tool install prek`) for pre-commit hooks

**Production:**
- Pure Python package - installable via `pip install adbc-poolhouse`
- PyPI distribution target: https://pypi.org/p/adbc-poolhouse
- PEP 561 compliant (py.typed marker at `src/adbc_poolhouse/py.typed`)

---

*Stack analysis: 2026-02-23*
