# Codebase Concerns

**Analysis Date:** 2026-02-23

## Tech Debt

**Empty public package — no implementation exists:**
- Issue: The library has zero implementation. `src/adbc_poolhouse/__init__.py` contains only a module docstring and `__all__ = []`. No config models, no pool creation, no driver detection — none of the core functionality described in `_notes/design-discussion.md` exists yet.
- Files: `src/adbc_poolhouse/__init__.py`
- Impact: The package cannot be used. All consumer APIs (`SnowflakeConfig`, `DuckDBConfig`, `create_pool`) are undeclared. Publishing to PyPI would produce a non-functional library.
- Fix approach: Implement the warehouse config models (Pydantic BaseSettings), parameter translation layer, driver detection, and `create_pool()` function as described in `_notes/design-discussion.md`.

**No runtime dependencies declared:**
- Issue: `pyproject.toml` has `dependencies = []` but the design requires `pydantic`, `adbc-driver-manager`, `sqlalchemy` (pool only), and ADBC driver packages.
- Files: `pyproject.toml` (line 10)
- Impact: Installing the published package gives consumers nothing usable. Downstream projects (`dbt-open-sl`, Semantic ORM) cannot import the library.
- Fix approach: Add `pydantic-settings`, `sqlalchemy` (with extras if needed for pool only), and `adbc-driver-manager` as runtime dependencies. ADBC drivers (`adbc-driver-snowflake`, `adbc-driver-duckdb`) should be optional extras.

**License mismatch between LICENSE file and design notes:**
- Issue: The `LICENSE` file is MIT. The `_notes/design-discussion.md` states the quality requirement is "Apache 2.0 license". These contradict each other.
- Files: `LICENSE`, `_notes/design-discussion.md` (line 148)
- Impact: Ambiguous license for consumers and contributors. Could matter when downstream projects (`dbt-open-sl`) specify their own licenses.
- Fix approach: Decide on the intended license and update both `LICENSE` and add a `license` field to `pyproject.toml` to make it machine-readable.

**`pyproject.toml` missing `license` field:**
- Issue: No `license` field in the `[project]` table of `pyproject.toml`. PEP 621 and PyPI both expect this. Dependabot and package scanners cannot determine the license.
- Files: `pyproject.toml`
- Impact: PyPI listing shows no license. Automated dependency license checks in consumer projects will flag the package as unknown.
- Fix approach: Add `license = { file = "LICENSE" }` or `license = { text = "MIT" }` to `[project]` in `pyproject.toml`.

## Known Bugs

**Unreplaced cookiecutter template variable breaks release workflow:**
- Symptoms: The release workflow's "Test wheel installation" step contains a literal `{{ cookiecutter.package_name }}` placeholder instead of `adbc_poolhouse`. This is a shell command that will fail with a syntax error or import the wrong module name.
- Files: `.github/workflows/release.yml` (line 67)
- Trigger: Any tag push matching `v[0-9]+.[0-9]+.[0-9]+` triggers the release workflow. The `validate` job's wheel smoke-test step will fail immediately.
- Workaround: Replace `{{ cookiecutter.package_name }}` with `adbc_poolhouse` on line 67.

## Security Considerations

**No security concerns at this stage:**
- The library has no implementation and no runtime dependencies. There are no credentials, no network calls, and no data handling. Security review is deferred to when the implementation exists.
- Files: `src/adbc_poolhouse/__init__.py`
- Current mitigation: N/A (no attack surface yet)
- Recommendations: When implementing, review ADBC connection string handling (avoid logging credentials), ensure Pydantic BaseSettings sources are ordered safely (env vars should override file-based config), and audit any `adbc_driver_manager` usage for path injection risks in Foundry driver loading.

## Performance Bottlenecks

**No performance bottlenecks at this stage:**
- No implementation exists to evaluate. Pool configuration defaults are documented in `_notes/design-discussion.md` and are reasonable (pool_size=5, max_overflow=3, recycle=3600s), but have not been implemented yet.

## Fragile Areas

**`docs/src/index.md` Quick Start section is a placeholder:**
- Files: `docs/src/index.md` (line 19)
- Why fragile: Contains `TODO: Add usage examples here.` If docs are built and published before the Quick Start is filled in, the site will ship incomplete documentation.
- Safe modification: Replace with real usage examples once `create_pool()` is implemented.
- Test coverage: None (documentation, not tested).

**`docs.yml` workflow uses `actions/checkout@v4` while all other workflows use `@v6`:**
- Files: `.github/workflows/docs.yml` (line 28), `.github/workflows/ci.yml` (line 24), `.github/workflows/pr.yml` (line 22), `.github/workflows/release.yml` (lines 20, 86)
- Why fragile: Version inconsistency means `docs.yml` may behave differently from other workflows. If `@v4` is eventually deprecated or has a security advisory, it will need a separate fix.
- Safe modification: Bump `docs.yml` to `actions/checkout@v6` to match all other workflows.
- Test coverage: CI will catch checkout failures, but not subtle behavioural differences between versions.

## Scaling Limits

**Not applicable at this stage.**
- No implementation exists. Pool scaling limits (SQLAlchemy QueuePool `pool_size`, `max_overflow`, `timeout`) are design-documented in `_notes/design-discussion.md` but not yet implemented.

## Dependencies at Risk

**`basedpyright` configured for Python 3.14, project requires Python 3.11:**
- Risk: `pyproject.toml` sets `pythonVersion = "3.14"` in `[tool.basedpyright]` but `requires-python = ">=3.11"`. Type checking runs against 3.14 semantics, but the package must support 3.11+. Features or syntax valid in 3.14 but not in 3.11 would pass type checking but fail at runtime for users on older Python versions.
- Files: `pyproject.toml` (lines 9 and 35)
- Impact: Potential runtime failures for users on Python 3.11, 3.12, or 3.13.
- Migration plan: Set `pythonVersion = "3.11"` in `[tool.basedpyright]` to type-check against the minimum supported Python version. Add multi-version CI testing (already scaffolded in `ci.yml` with matrix `["3.11", "3.14"]`).

**`MishaKav/pytest-coverage-comment@v1.1.51` is a pinned third-party action:**
- Risk: Pinned to a specific version by release tag (not SHA). If the tag is force-pushed or the action is abandoned, the PR coverage workflow could silently break or be compromised.
- Files: `.github/workflows/pr.yml` (line 38)
- Impact: Loss of PR coverage comments. Lower severity since it does not block CI.
- Migration plan: Pin to a full commit SHA for supply chain security hardening.

**`git-cliff` installed by curling a specific release tarball:**
- Risk: The changelog job in `release.yml` downloads `git-cliff v2.7.0` directly via `curl` from GitHub releases (line 92). This is not pinned to a hash and will silently use whatever is at that URL.
- Files: `.github/workflows/release.yml` (lines 91-92)
- Impact: Supply chain risk. A compromised or replaced release artifact would execute in the CI environment.
- Migration plan: Use the official `orhun/git-cliff-action` GitHub Action (with SHA pinning) instead of a raw `curl` install.

## Missing Critical Features

**All core library functionality is missing:**
- Problem: The entire library is unimplemented. Missing: Pydantic BaseSettings config models per warehouse type (`SnowflakeConfig`, `DuckDBConfig`, etc.), parameter translation functions (config fields → ADBC driver kwargs), driver detection logic (PyPI package import → `adbc_driver_manager` fallback), `create_pool()` function (SQLAlchemy QueuePool wrapping ADBC dbapi).
- Blocks: All consumer projects (`dbt-open-sl`, Semantic ORM) are blocked. PyPI publish would produce a non-functional package.

## Test Coverage Gaps

**Only a single smoke test exists:**
- What's not tested: Everything. The only test (`tests/test_adbc_poolhouse.py`) checks that `adbc_poolhouse` has an `__all__` attribute. No pool creation, no config validation, no driver detection, no parameter translation, no error handling paths are tested.
- Files: `tests/test_adbc_poolhouse.py`, `tests/conftest.py`
- Risk: Any implementation added without tests could be subtly broken with no safety net. The CI reports coverage but does not enforce a minimum threshold (`AGENTS.md`: "Coverage reported but not enforced").
- Priority: High. The design notes specify "thorough test coverage" as a quality requirement.

---

*Concerns audit: 2026-02-23*
