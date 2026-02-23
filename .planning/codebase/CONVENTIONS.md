# Coding Conventions

**Analysis Date:** 2026-02-23

## Naming Patterns

**Files:**
- Snake_case module names matching the package: `adbc_poolhouse/__init__.py`
- Test files prefixed with `test_`: `tests/test_adbc_poolhouse.py`
- Shared fixture file named `conftest.py`: `tests/conftest.py`

**Functions:**
- Snake_case: `test_import`, `create_pool` (per design docs)
- Test functions prefixed with `test_`: `def test_import()`

**Variables:**
- Snake_case throughout

**Types / Classes:**
- PascalCase: `SnowflakeConfig`, `DuckDBConfig`, `BigQueryConfig` (per design docs)
- Pydantic `BaseSettings` subclasses for all warehouse config models

**Modules:**
- Public API exported via `__all__` in `src/adbc_poolhouse/__init__.py`
- `__all__` is the authoritative list of public symbols; start empty and add explicitly

## Code Style

**Formatting:**
- Tool: `ruff format`
- Line length: 100 characters maximum
- Applied automatically via pre-commit hook and enforced in CI

**Linting:**
- Tool: `ruff check` with rule groups: `E, F, W, I, UP, B, SIM, TCH, D`
  - `E/F/W`: pycodestyle/pyflakes errors and warnings
  - `I`: isort-compatible import sorting
  - `UP`: pyupgrade — use modern Python syntax
  - `B`: flake8-bugbear — likely bugs and design issues
  - `SIM`: flake8-simplify — simplifiable code
  - `TCH`: flake8-type-checking — move type-only imports into `TYPE_CHECKING` blocks
  - `D`: pydocstyle — docstring conventions
- Auto-fix enabled on pre-commit: `ruff check --fix`

**Disabled rules (explicit exceptions in `pyproject.toml`):**
- `D1` series — docstrings not required everywhere
- `D202` — blank line after docstring allowed (common in tests)
- `D203` — overridden by D211 (no blank line before class docstring)
- `D212` — overridden by D213 (multiline summary on second line)
- `D401` — imperative mood not required for dunder methods
- `D413` — blank line after last section not required

## Docstrings

Use D213 format — summary on the second line after the opening triple-quotes:

```python
def function():
    """
    Brief summary on the second line.

    More details here if needed.
    """
```

Single-line docstrings for simple module-level entries:

```python
"""Connection pooling for ADBC drivers from typed warehouse configs."""
```

Docstrings are not required on every function (D1 is disabled), but public API must be documented.

## Type Annotations

**Strict mode:** All code is checked with `basedpyright` in `typeCheckingMode = "strict"`.

- Every function parameter and return value must be annotated
- Avoid `# type: ignore` comments; prefer pyproject.toml-level exemptions
- Use `TYPE_CHECKING` blocks to avoid circular imports:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some_module import SomeType
```

- `reportPrivateUsage = false` — tests may access private members (`_private`)
- `pythonVersion = "3.14"` in basedpyright config (targets latest Python features)

## Import Organization

**Order (automated via ruff `I` rules):**
1. Standard library imports
2. Third-party imports
3. Local/project imports

**Path aliases:** None — standard absolute imports only.

**Type-only imports:** Must use `TYPE_CHECKING` guard per the `TCH` ruff rule group:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
```

## Module Design

**Exports:**
- Always define `__all__` in `src/adbc_poolhouse/__init__.py`
- Start with empty `__all__ = []` and add public names explicitly as they are implemented
- Version is defined only in `pyproject.toml` — NOT duplicated in `__init__.py`

**Barrel files:**
- `src/adbc_poolhouse/__init__.py` acts as the single public API surface
- Internal submodules should not be imported directly by consumers

## Error Handling

- Provide helpful error messages when required ADBC drivers are not installed (per design doc)
- Do not silence exceptions silently; raise with informative messages
- No specific try/except pattern established yet (codebase is pre-implementation)

## Logging

- No logging framework configured yet; standard Python `logging` module expected
- No specific pattern established yet

## Comments

**When to comment:**
- Prefer self-documenting code over inline comments
- Use docstrings for public API documentation (mkdocstrings reads them for the docs site)
- Inline comments for non-obvious implementation decisions

**Conventional commits:**
- Commit messages use `<type>(<scope>): <message>` format
- Types: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `perf`, `style`
- Used to drive automated changelog generation via `git-cliff`

## Pre-commit Hooks

All hooks defined in `.pre-commit-config.yaml`. The `prek` wrapper runs them all:

```bash
prek run --all-files  # Run all quality gates
prek install          # Install git hooks
```

Individual hooks in order:
1. `trailing-whitespace`, `end-of-file-fixer`, `check-json`, `check-toml`, `check-yaml` (built-in)
2. `ruff` with `--fix` (linting + auto-fix)
3. `ruff-format` (formatting)
4. `uv-lock` (keep lockfile in sync)
5. `basedpyright` (strict type checking)
6. `blacken-docs` (format code blocks in docs, 100-char line length)

The `.planning/` directory is excluded from all pre-commit hooks.

---

*Convention analysis: 2026-02-23*
