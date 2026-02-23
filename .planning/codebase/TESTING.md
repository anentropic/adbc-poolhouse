# Testing Patterns

**Analysis Date:** 2026-02-23

## Test Framework

**Runner:**
- pytest >= 8.0.0
- No separate `pytest.ini` or `pytest.ini.toml` — no `[tool.pytest.ini_options]` section in `pyproject.toml` yet (default configuration)

**Coverage Plugin:**
- `pytest-cov` >= 6.0.0

**Assertion Library:**
- pytest built-in assertions (no additional library)

**Run Commands:**
```bash
uv run pytest                                                          # Run all tests
uv run pytest --cov=src/adbc_poolhouse --cov-report=term              # With terminal coverage
uv run pytest --cov=src/adbc_poolhouse --cov-report=xml --cov-report=term  # XML + terminal (used in CI)
```

## Test File Organization

**Location:**
- Separate `tests/` directory at project root (not co-located with source)
- `tests/__init__.py` present — tests are a proper package

**Naming:**
- Test files: `test_<module_name>.py` — e.g., `tests/test_adbc_poolhouse.py`
- Test functions: `test_<specific_behavior>` — e.g., `def test_import()`

**Structure:**
```
tests/
├── __init__.py          # Makes tests a package
├── conftest.py          # Shared fixtures (currently empty placeholder)
└── test_adbc_poolhouse.py  # Module tests
```

## Test Structure

**Current pattern:**
```python
"""Basic tests for adbc_poolhouse."""

import adbc_poolhouse


def test_import():
    assert hasattr(adbc_poolhouse, "__all__")
```

**Suite organization:**
- Module-level docstring describing test scope
- Imports at top
- Plain functions (no class grouping yet)
- One assertion per test when practical

**Patterns:**
- Setup: via pytest fixtures in `tests/conftest.py`
- Teardown: via fixture `yield` + cleanup after yield
- Assertions: plain `assert` statements with pytest's assertion rewriting

## Fixtures

**Location:** `tests/conftest.py`

**Current state:** File exists as a placeholder with the comment `# Add your fixtures here`. No fixtures defined yet.

**Intended pattern** (per `tests/conftest.py` docstring):
```python
"""Shared pytest fixtures for adbc_poolhouse test suite."""

import pytest


@pytest.fixture
def some_fixture():
    # setup
    yield value
    # teardown
```

Fixtures in `conftest.py` are automatically available to all test files without importing.

## Mocking

**Framework:** No mocking library explicitly added yet. Standard pytest patterns expected:
- `unittest.mock` from the standard library, or
- `pytest-mock` (not yet in `pyproject.toml` — add as needed)

**What to mock (per design doc intent):**
- ADBC driver imports (drivers not installed in test environment)
- SQLAlchemy pool internals when testing pool configuration
- Network connections / warehouse authentication

**What NOT to mock:**
- Pydantic config model validation (test with real values)
- Core parameter translation logic (test the actual mapping)

## Coverage

**Requirements:** No minimum threshold enforced yet.

**Coverage target:**
```bash
uv run pytest --cov=src/adbc_poolhouse --cov-report=term
```
Coverage is measured over `src/adbc_poolhouse` only (not tests themselves).

**CI behavior:**
- On every push: tests run, no coverage report posted
- On every pull request: coverage runs with XML output and a comment is posted to the PR via `MishaKav/pytest-coverage-comment` action (`.github/workflows/pr.yml`)

**View Coverage:**
```bash
uv run pytest --cov=src/adbc_poolhouse --cov-report=term
uv run pytest --cov=src/adbc_poolhouse --cov-report=html  # Opens htmlcov/index.html
```

## Test Types

**Unit Tests:**
- Scope: individual functions and classes in isolation
- Location: `tests/test_<module>.py`
- Pattern: test one behavior per function, use fixtures for setup

**Integration Tests:**
- Scope: full connection pool creation against real or in-memory drivers (e.g., DuckDB)
- Location: `tests/test_<module>.py` (no separate integration directory yet)
- DuckDB is the primary driver for local integration testing (no credentials required)

**E2E Tests:**
- Not used — library produces a connection pool, consumers own execution

## CI Testing Matrix

Tests run across Python versions in CI (`.github/workflows/ci.yml`):

```yaml
matrix:
  python-version: ["3.11", "3.14"]
```

Both versions must pass. `fail-fast: false` so both results are always reported.

## Common Patterns

**Testing public API exports:**
```python
def test_import():
    assert hasattr(adbc_poolhouse, "__all__")
```

**Testing Pydantic config validation (expected pattern):**
```python
import pytest
from adbc_poolhouse import SnowflakeConfig

def test_snowflake_config_requires_account():
    with pytest.raises(ValueError):
        SnowflakeConfig()  # missing required fields
```

**Testing with DuckDB (no credentials needed):**
```python
from adbc_poolhouse import DuckDBConfig, create_pool

def test_create_duckdb_pool():
    config = DuckDBConfig(database=":memory:")
    pool = create_pool(config)
    assert pool is not None
```

**Async testing:** Not applicable — library is synchronous.

**Error testing:**
```python
import pytest

def test_missing_driver_raises_helpful_error():
    with pytest.raises(ImportError, match="adbc_driver_snowflake"):
        # attempt to create pool for driver that isn't installed
        ...
```

## Type Checking in Tests

- `basedpyright` includes `tests/` in its check scope (`include = ["src", "tests"]` in `pyproject.toml`)
- `reportPrivateUsage = false` — tests may access private members (`_private`) without type errors
- Tests must also be fully type-annotated to pass the pre-commit hook

---

*Testing analysis: 2026-02-23*
