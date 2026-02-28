# Development Guide

This document provides guidance for developers working on adbc-poolhouse.

## Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) - Modern Python package and project manager
- Python 3.11 or later

### Initial Setup

```bash
# Install dependencies
uv sync --dev

# Install git hooks
prek install
```

## Quality Gates

All code must pass strict quality checks before committing. The unified command:

```bash
prek run --all-files  # Runs typecheck, lint, format, test
```

Or run individually:

```bash
# Type checking (strict mode)
uv run basedpyright

# Linting
uv run ruff check

# Format validation
uv run ruff format --check

# Auto-fix formatting and linting
uv run ruff format
uv run ruff check --fix

# Test suite
uv run pytest

# Test coverage
uv run pytest --cov=src/adbc_poolhouse --cov-report=term
```

### Quality Gate Details

- **basedpyright**: Strict type checking mode enabled. Tests may access private members (_private).
- **ruff check**: Linting rules (E, F, W, I, UP, B, SIM, TCH, D)
- **ruff format**: Code formatting with 100-char line length
- **pytest**: Test suite with coverage tracking

## Code Conventions

### Line Length
100 characters maximum

### Docstrings
Multi-line docstrings follow D213 format (summary on second line after opening quotes):

```python
def function():
    """
    Brief summary on the second line.

    More details here if needed.
    """
```

### Type Annotations
- Strict mode enabled - all code must be type-safe
- Avoid `# type: ignore` comments; prefer pyproject.toml-level exemptions
- Use `TYPE_CHECKING` blocks to avoid circular imports when needed

### Import Sorting
Automated via ruff isort (I rules) - runs as part of `ruff format`

## Development Workflow

1. Create a feature branch from `main`
2. Make code changes
3. Run quality gates: `prek run --all-files`
4. Commit with conventional commit format:
   ```
   <type>(<scope>): <message>

   Types: feat, fix, docs, chore, test, refactor, perf, style
   ```
5. Push to remote and create pull request
6. CI automatically runs on push and pull request

## Project Structure

```
adbc-poolhouse/
├── src/adbc_poolhouse/      # Package source (internal modules prefixed with _)
│   ├── __init__.py             # Public API exports
│   └── py.typed                # PEP 561 type marker
├── tests/                       # Test suite
│   ├── conftest.py             # Shared fixtures
│   └── __init__.py
├── docs/                        # Documentation source
│   ├── src/                     # Markdown pages
│   └── scripts/                 # mkdocs hooks (gen_ref_pages.py)
├── .github/                     # GitHub configuration
│   ├── workflows/
│   │   ├── ci.yml              # CI/CD pipeline
│   │   ├── docs.yml            # Documentation deployment
│   │   ├── pr.yml              # PR coverage reporting
│   │   └── release.yml         # PyPI release pipeline
│   └── dependabot.yml          # Dependency updates
├── pyproject.toml              # Build and tool configuration
├── mkdocs.yml                  # Documentation site config
├── justfile                    # Common dev tasks (just build, just serve)
├── uv.lock                     # Locked dependencies (committed)
├── .python-version             # Python version pin (pyenv/asdf)
├── .pre-commit-config.yaml     # Pre-commit hooks (prek)
├── .cliff.toml                 # Changelog generation (git-cliff)
├── .secrets.baseline           # detect-secrets baseline
├── LICENSE                     # MIT
├── README.md                   # User documentation
├── CONTRIBUTING.md             # Contributing guide
└── DEVELOP.md                  # This file
```

## Testing

- Tests located in `tests/` directory
- Use pytest for test discovery and execution
- Fixtures defined in `tests/conftest.py` for reuse
- Test naming convention: `test_<specific_behavior>`

### Snowflake integration tests

Tests requiring real credentials are gated behind the `snowflake` pytest marker and excluded from default runs.

```bash
# Run Snowflake tests (requires SNOWFLAKE_* env vars)
uv run pytest --override-ini="addopts=" -m snowflake

# Record or update snapshots
uv run pytest --override-ini="addopts=" -m snowflake --snapshot-update
```

Snapshots are committed to `tests/` and replayed in CI without credentials.

## Building and Distribution

### Build Locally

```bash
uv build
```

Creates wheel and source distribution in `dist/`:
- `.whl` - Wheel (binary)
- `.tar.gz` - Source distribution

### Publishing to PyPI

Automated on release tag push:

```bash
git tag v1.2.3
git push origin v1.2.3
```

This triggers the release workflow which:
1. Builds distributions
2. Validates across Python versions
3. Generates changelog
4. Publishes to PyPI

Requires PyPI Trusted Publishing setup in GitHub repository settings.

## Version Management

Version is defined in `pyproject.toml` only:

```toml
[project]
version = "1.0.1"
```

Not duplicated in `__init__.py` - maintain single source of truth.

## Common Tasks

### Add a new dependency

```bash
# Development dependency
uv add --group dev <package>

# Production dependency
uv add <package>
```

Then update your code and run quality gates.

### Update dependencies

```bash
# Update all dependencies
uv sync --upgrade --dev
```

### Build and serve docs

```bash
# Build docs site (strict mode)
just build

# Start dev server with hot-reload
just serve

# Custom port
just serve 8001
```

### Generate changelog

```bash
# Preview unreleased commits
git cliff --unreleased

# Write full changelog to file
git cliff --output CHANGELOG.md
```

## Troubleshooting

### Quality gate failures
If a quality gate fails during pre-commit, the commit is aborted. Fix the issue and commit again:

```bash
prek run --all-files  # Identify the failure
# Fix the code
prek run --all-files  # Verify fix
git add .
git commit -m "fix: message"
```

When hooks are installed (`prek install`), they run automatically before each commit.

### Type checking in IDE

If your IDE shows type errors but `basedpyright` passes:

1. Ensure your IDE uses Python 3.11+
2. Check that your IDE is using basedpyright, not mypy or pylance
3. Verify venv is activated properly

### Slow builds

```bash
# Clear uv cache if it grows large
uv cache clean
uv cache prune
```

## Questions?

Refer to official documentation:
- [uv](https://docs.astral.sh/uv/)
- [basedpyright](https://github.com/detachhead/basedpyright)
- [ruff](https://docs.astral.sh/ruff/)
- [pytest](https://docs.pytest.org/)
