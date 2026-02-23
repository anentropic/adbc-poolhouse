# Stack Research: adbc-poolhouse

**Research Date:** 2026-02-23
**Research Type:** Project Research — Stack dimension
**Milestone:** Greenfield — standard 2025 stack for a Python ADBC connection pooling library

---

## Summary

The design decisions already made in `_notes/design-discussion.md` are well-aligned with the 2025/2026 Python library ecosystem. The core choices — pydantic-settings for config, SQLAlchemy QueuePool for pooling, uv for tooling, basedpyright strict for type checking — are all confirmed as the right picks. There are no major stack decisions to reverse. The primary open questions are about version pinning strategy for runtime deps and whether to add syrupy and pytest-mock to the dev dependency group.

---

## Version Note

Runtime dependencies (pydantic-settings, sqlalchemy, adbc-driver-*) are not yet in `uv.lock` because `pyproject.toml` has `dependencies = []`. Versions below are based on known PyPI state at research date (2026-02-23). Dev toolchain versions are confirmed from `uv.lock` resolved 2026-02-23.

**Confidence key:**
- HIGH — confirmed from uv.lock or direct PyPI resolution at research date
- MEDIUM — from training data, release cadence known, version likely current
- LOW — from training data, less certainty about exact current version

---

## 1. Runtime Core Dependencies

### 1.1 pydantic-settings

**Recommendation:** `pydantic-settings>=2.7,<3`
**Confidence:** MEDIUM (pydantic-settings 2.x is stable; 2.7 released late 2024)

**Why:**
- `pydantic-settings` separates the settings/env-var concern from core Pydantic in v2, keeping the runtime dep footprint smaller for consumers who only want core Pydantic.
- `BaseSettings` reads from env vars automatically — warehouse credentials (SNOWFLAKE_ACCOUNT, etc.) come for free without custom loaders.
- Validation happens at object construction time, giving consumers immediate, actionable error messages before any network call is made.
- v2 is a full rewrite with dramatically better performance and richer type inference than v1. All new Python libraries in 2025 should use Pydantic v2.

**What NOT to use:**
- `pydantic` directly (without `pydantic-settings`) — you'd lose the env-var source integration and have to write your own settings loader.
- `pydantic v1` — EOL, no new features, worse type inference. Not compatible with basedpyright strict on Python 3.11+.
- `attrs` or `dataclasses` — no built-in env-var sources, no validators, require third-party glue to get field-level error messages.
- `dynaconf` / `python-decouple` — general-purpose settings libs, not typed config models. Poor fit for a typed public API that consumers directly instantiate.

**Design-discussion.md verdict:** CONFIRMED. Pydantic BaseSettings is the right choice.

---

### 1.2 sqlalchemy (pool submodule only)

**Recommendation:** `sqlalchemy>=2.0,<3`
**Confidence:** MEDIUM (SQLAlchemy 2.x stable since 2023; 2.0.x is current major)

**Why:**
- `QueuePool` is SQLAlchemy's battle-tested, thread-safe connection pool. It handles pre-ping health checks (`pool_pre_ping`), overflow management (`max_overflow`), idle connection recycling (`recycle`), and pool events — all features this library uses.
- SQLAlchemy 2.0 reworked its pool layer to be cleaner and more composable. The pool submodule (`sqlalchemy.pool`, `sqlalchemy.event`) is usable without the ORM, keeping this library lightweight.
- The alternative of building a hand-rolled thread-safe pool is non-trivial to get right (checkout timeouts, overflow counters, pre-ping on stale connections) and produces a pool no consumer will already know how to configure.
- `QueuePool` is widely deployed in production Python data infrastructure (Airflow, dbt-core, FastAPI with SQLModel) — consumers know its semantics.

**Import scope constraint (from PROJECT.md):** Only `sqlalchemy.pool` and `sqlalchemy.event` are imported. This is correct practice — it avoids pulling in ORM metadata, declarative base, etc. into a library that has no use for them.

**What NOT to use:**
- `connection-pool` (PyPI) — unmaintained, no health checks, no overflow.
- `aiomysql`-style async pools — ADBC dbapi is synchronous; async is explicitly out of scope for v1.
- A hand-rolled `threading.Semaphore`-based pool — reinventing QueuePool without its 15 years of production hardening.
- `pgbouncer` or external proxy pools — not relevant; this is a Python in-process pool.

**Design-discussion.md verdict:** CONFIRMED. `sqlalchemy.pool.QueuePool` with selective imports is the right choice.

---

### 1.3 adbc-driver-manager

**Recommendation:** `adbc-driver-manager>=1.0,<2` (runtime dep, always present)
**Confidence:** MEDIUM (Apache Arrow ADBC 1.x released mid-2024)

**Why:**
- `adbc_driver_manager` is the universal ADBC dbapi entry point. Both PyPI-packaged drivers and Foundry-installed drivers load through it — it is the stable interface regardless of which warehouse driver is installed.
- Even when using a PyPI driver like `adbc_driver_snowflake`, the `adbc_driver_manager.dbapi` interface is the cleanest way to obtain a dbapi-compatible connection for use with SQLAlchemy's `creator` argument.
- Required for the Foundry driver path (Databricks, Redshift, Trino, etc.) even in v1 since the architecture supports it.

**What NOT to use:**
- Importing `adbc_driver_snowflake` directly without `adbc_driver_manager` — it exposes a lower-level API without the standardized dbapi interface.
- `pyarrow` as a connection layer — it does not provide dbapi connection semantics and is a much heavier dependency.

**Design-discussion.md verdict:** CONFIRMED.

---

### 1.4 ADBC Driver Packages (optional extras)

**Recommendation:** Declare as optional extras, not hard runtime deps.

```toml
[project.optional-dependencies]
duckdb = ["duckdb>=1.0"]
snowflake = ["adbc-driver-snowflake>=1.0"]
bigquery = ["adbc-driver-bigquery>=1.0"]
postgresql = ["adbc-driver-postgresql>=1.0"]
flightsql = ["adbc-driver-flightsql>=1.0"]
```

**Confidence (versions):**
- `duckdb>=1.0` — HIGH (DuckDB 1.0 released June 2024, actively maintained, rapidly releasing)
- `adbc-driver-snowflake>=1.0` — MEDIUM
- `adbc-driver-bigquery`, `adbc-driver-postgresql`, `adbc-driver-flightsql` — MEDIUM (all part of Apache Arrow ADBC project, versioned together)

**Why optional extras:**
- A consumer using DuckDB only should not be forced to install Snowflake driver bits and vice versa.
- Foundry-installed drivers (Databricks, Redshift, etc.) are not on PyPI at all — there is no package to pin.
- Standard PyPI pattern for drivers: `pip install adbc-poolhouse[snowflake]` installs the Snowflake driver alongside the core library.

**What NOT to do:**
- Hard-depend on all drivers — forces consumers to install multi-MB driver binaries they don't use.
- Use `adbc-driver-duckdb` (a separate PyPI package) instead of `duckdb` — DuckDB bundles its own ADBC interface in the main `duckdb` package since 0.10.x; the separate `adbc-driver-duckdb` package is redundant and adds confusion.

**Design-discussion.md verdict:** CONFIRMED (optional extras pattern). Clarification: use `duckdb` directly, not `adbc-driver-duckdb`.

---

## 2. Testing Stack

### 2.1 pytest

**Current version in lockfile:** pytest 9.0.2 (confirmed HIGH)

**Why:** Standard Python test runner. No alternative considered. The 9.x line dropped Python 3.8 support and cleaned up several deprecated APIs — correct choice for a Python 3.11+ library.

**Pyproject spec:** `pytest>=8.0.0` (already in pyproject.toml, lockfile resolved to 9.0.2).

---

### 2.2 pytest-cov

**Current version in lockfile:** pytest-cov 7.0.0 (confirmed HIGH)

**Why:** Standard coverage plugin for pytest. 7.x requires pytest 7+ and coverage 7+. No alternative needed.

---

### 2.3 pytest-mock

**Recommendation:** Add `pytest-mock>=3.14` to dev dependencies
**Confidence:** MEDIUM

**Why:**
- Driver detection logic involves `importlib.import_module` calls that need to be intercepted in tests without actually installing drivers.
- `pytest-mock` wraps `unittest.mock` with a cleaner pytest-native `mocker` fixture. It avoids the boilerplate of manually patching and unpatching in every test.
- Without `pytest-mock`, test code will use `unittest.mock.patch` decorators or `with patch(...)` context managers — fine for a few tests, but the fixture-based API is more composable and readable.

**What NOT to use:**
- `responses` / `httpretty` — not relevant, no HTTP calls.
- `respx` — same, async HTTP not applicable.
- Raw `unittest.mock` — works, but `pytest-mock` is strictly more ergonomic and is the de facto standard in 2025.

---

### 2.4 syrupy

**Recommendation:** Add `syrupy>=4.0` to dev dependencies
**Confidence:** MEDIUM (syrupy 4.x is current)

**Why:**
- PROJECT.md specifies "Snowflake snapshot tests via syrupy (recorded locally with real creds, replayed in CI without credentials)."
- syrupy is the leading snapshot testing library for pytest in 2025. It stores snapshots in `__snapshots__` directories, supports multiple serialization formats (amber by default, also JSON), and integrates cleanly with pytest's assert rewriting.
- The Snowflake testing strategy explicitly depends on syrupy — it is not optional.
- syrupy 4.x added stable `SnapshotSession` API and better diff rendering on failure.

**What NOT to use:**
- `pytest-snapshot` — older, less maintained, simpler but less feature-rich.
- Manual JSON fixture files — works but requires custom diffing logic and is more brittle on schema changes.
- `VCR.py` / `pytest-recording` — designed for HTTP cassettes, not ADBC connection results; wrong abstraction.

---

## 3. Type Checking

### 3.1 basedpyright

**Current version in lockfile:** basedpyright 1.38.1 (confirmed HIGH)

**Why:**
- basedpyright is a community fork of pyright with stricter defaults, better ergonomics for library authors, and more aggressive inference. It's the correct choice for a library targeting basedpyright strict mode (already configured in pyproject.toml).
- `typeCheckingMode = "strict"` catches missing annotations, implicit `Any`, and unsafe operations that vanilla pyright's default mode misses.
- Pydantic v2 ships with a mypy plugin AND pyright stubs — both basedpyright and mypy will understand `BaseSettings` fields properly without any additional configuration.

**Pyright vs mypy:**
- basedpyright has much faster incremental analysis than mypy.
- basedpyright's error messages are more actionable.
- mypy is still widely used but basedpyright is the better choice for new greenfield projects with strict mode requirements in 2025.
- The project already has basedpyright configured — no reason to add mypy.

**Version caveat from CONCERNS.md:** `pythonVersion = "3.14"` in the basedpyright config should be set to `"3.11"` to type-check against the minimum supported Python version. This is an existing issue to fix before implementation starts.

---

## 4. Linting & Formatting

### 4.1 ruff

**Current version in lockfile:** ruff 0.15.2 (confirmed HIGH)

**Why:**
- Ruff replaces flake8, isort, pyupgrade, and pylint in a single fast Rust binary. The project already uses it (configured in pyproject.toml with rules E, F, W, I, UP, B, SIM, TCH, D).
- 0.15.x is the current stable series as of research date.
- The rule selection is correct for this project: UP (pyupgrade) ensures modern Python syntax, TCH moves type-only imports to `TYPE_CHECKING` blocks (important for library code), B catches likely bugs.

**No alternative needed.** Ruff is the unambiguous 2025 standard.

---

## 5. Build & Packaging

### 5.1 uv + uv_build

**Current build backend in pyproject.toml:** `uv_build>=0.9.18,<1.0.0`
**Confidence:** HIGH (uv_build is stable; 0.9.18 was current at project scaffold time)

**Why:**
- uv is the 2025 standard for Python project management (dep resolution, venv creation, script running). It replaces pip, pip-tools, virtualenv, and poetry in one binary.
- `uv_build` as the build backend produces PEP 517-compliant wheels and sdists. It's the natural complement to using uv as the project manager.
- Lock file (`uv.lock`) is already committed, ensuring reproducible dev environments.

**What NOT to use:**
- `setuptools` + `setup.py` — legacy, verbose, error-prone for src-layout projects.
- `poetry` — slower resolver than uv, less compatible with PEP 621 tooling.
- `hatch` — reasonable alternative but no advantage over uv for this project's scope.
- `flit` — simpler but less capable (no dependency groups, no lockfile).

**Design-discussion.md verdict:** CONFIRMED. Already in place.

---

### 5.2 PyPI Publishing

**Recommendation:** OIDC Trusted Publishing (already configured in release.yml)
**Confidence:** HIGH

**Why:**
- OIDC Trusted Publishing (via `pypa/gh-action-pypi-publish`) eliminates the need for a stored PyPI API token in GitHub Secrets. GitHub's OIDC token is exchanged for a short-lived PyPI token at publish time.
- Already set up in the release workflow — no changes needed.

---

## 6. Documentation

### 6.1 mkdocs-material

**Current version in pyproject.toml:** `mkdocs-material>=9.7.0`
**Confidence:** HIGH (9.7.x is current stable)

**Why:**
- The de facto standard for Python library documentation in 2025. Material theme provides search, versioning support, and a clean responsive layout.
- Already configured in this project.

### 6.2 mkdocstrings[python]

**Current version in pyproject.toml:** `mkdocstrings[python]>=0.26.0`
**Confidence:** HIGH

**Why:**
- Auto-generates API reference from Google-style docstrings. The project already uses Google docstring style (mkdocs.yml). No manual API reference maintenance required.
- Already configured.

**No alternatives needed.** The docs stack is complete and correct.

---

## 7. Pre-commit & CI

### 7.1 prek

**Why:** Rust-based pre-commit runner (wraps `.pre-commit-config.yaml`). Already installed and configured. The hook chain (trailing whitespace, ruff lint, ruff format, uv-lock, basedpyright, blacken-docs) is the correct set for this project.

### 7.2 GitHub Actions

The CI pipeline is already scaffolded:
- `ci.yml`: push → prek quality gates + pytest, matrix Python 3.11/3.14
- `pr.yml`: PR → pytest with coverage comment
- `docs.yml`: push to main → build + deploy MkDocs
- `release.yml`: semver tag → build wheel, validate, generate changelog via git-cliff, publish to PyPI

**Known issue to fix (from CONCERNS.md):** `release.yml` line 67 contains `{{ cookiecutter.package_name }}` — must be replaced with `adbc_poolhouse` before any release.

---

## 8. What the Stack Does NOT Include (and Why)

| Rejected option | Why rejected |
|---|---|
| `asyncio`-based async pool | ADBC dbapi is synchronous. Async out of scope for v1. |
| `threading.local` session management | Consumers own pool lifecycle; library has no global state. |
| `structlog` / `loguru` | Standard `logging` module is sufficient for a library. Heavy logging frameworks are appropriate for applications, not libraries. |
| `rich` for error messages | Overkill for a focused library. Plain Python exceptions with clear messages are better. |
| `click` / `typer` CLI | This is a library, not a CLI tool. No entry points. |
| `cryptography` (for Snowflake key-pair auth) | Auth logic is delegated to the ADBC driver. Private key handling is passed through as a config field value; the driver performs the actual crypto. If key parsing is needed at config construction time, `cryptography` may need to be added as an optional dep — defer until implementation. |
| `tenacity` retry logic | Retry-on-connection-failure is handled by SQLAlchemy pool's `pool_pre_ping` mechanism. No additional retry library needed. |

---

## 9. Full pyproject.toml Dependencies (Recommended)

Based on the above research, the complete `pyproject.toml` runtime and dev dependency block should be:

```toml
[project]
dependencies = [
    "pydantic-settings>=2.7,<3",
    "sqlalchemy>=2.0,<3",
    "adbc-driver-manager>=1.0,<2",
]

[project.optional-dependencies]
duckdb = ["duckdb>=1.0"]
snowflake = ["adbc-driver-snowflake>=1.0"]
bigquery = ["adbc-driver-bigquery>=1.0"]
postgresql = ["adbc-driver-postgresql>=1.0"]
flightsql = ["adbc-driver-flightsql>=1.0"]
all = [
    "duckdb>=1.0",
    "adbc-driver-snowflake>=1.0",
    "adbc-driver-bigquery>=1.0",
    "adbc-driver-postgresql>=1.0",
    "adbc-driver-flightsql>=1.0",
]

[dependency-groups]
dev = [
    "basedpyright>=1.38.0",
    "ipython>=9.10.0",
    "pdbpp>=0.12.0.post1",
    "pytest>=8.0.0",
    "pytest-cov>=6.0.0",
    "pytest-mock>=3.14",
    "ruff>=0.15.1",
    "syrupy>=4.0",
]
```

**Notes:**
- `adbc-driver-manager` is a hard runtime dep (not optional) because it is the universal loader for both PyPI and Foundry drivers.
- `duckdb` extra is what consumers use for local/dev/test, not a hard dep.
- `syrupy` goes in `dev` not a separate `test` group (the project currently uses a single `dev` group).
- The `all` extra enables `pip install adbc-poolhouse[all]` for convenience.

---

## 10. Decision Log: Confirmed vs. Open

| Decision from design-discussion.md | Status | Notes |
|---|---|---|
| Pydantic BaseSettings for config | CONFIRMED | pydantic-settings v2, `>=2.7,<3` |
| SQLAlchemy QueuePool | CONFIRMED | sqlalchemy `>=2.0,<3`, pool submodule only |
| adbc-driver-manager as universal loader | CONFIRMED | `>=1.0,<2` as hard runtime dep |
| ADBC drivers as optional extras | CONFIRMED | One extra per warehouse |
| `duckdb` for v1 dev/test | CONFIRMED | Use `duckdb` package directly, not `adbc-driver-duckdb` |
| syrupy for Snowflake snapshot tests | CONFIRMED | `>=4.0` in dev group |
| uv + uv_build for packaging | CONFIRMED | Already in place |
| basedpyright strict mode | CONFIRMED | Fix `pythonVersion = "3.11"` before implementation |
| ruff for lint + format | CONFIRMED | Already in place |
| pytest + pytest-cov | CONFIRMED | Already in place (9.0.2, 7.0.0) |
| pytest-mock for unit tests | NEW ADDITION | Not in design-discussion.md; necessary for driver detection tests |
| OIDC Trusted Publishing | CONFIRMED | Already in release.yml |

---

*Research by Claude Code — 2026-02-23*
