---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - .github/workflows/ci.yml
  - pyproject.toml
  - tests/test_pool_factory.py
autonomous: true
requirements: []

must_haves:
  truths:
    - "CI Tests job passes on all Python versions (no FFFFF in test_pool_factory.py)"
    - "Docs build passes with uv run mkdocs build --strict"
    - "TestCreatePoolDuckDB tests run against a real DuckDB connection without ImportError"
  artifacts:
    - path: ".github/workflows/ci.yml"
      provides: "CI workflow with duckdb extra installed"
    - path: "pyproject.toml"
      provides: "mkdocs pinned below 2.0 or mkdocs-material pinned to non-warning version"
  key_links:
    - from: ".github/workflows/ci.yml"
      to: "uv sync --extra duckdb"
      via: "Sync step installs duckdb optional dep so _duckdb C extension is available"
      pattern: "uv sync.*duckdb"
    - from: "pyproject.toml"
      to: "mkdocs<2.0"
      via: "Upper bound prevents mkdocs-material 9.7.x from emitting MkDocs 2.0 warning"
      pattern: "mkdocs<2\\.0"
---

<objective>
Fix two independent CI failures identified via gh run list:

1. **Test failure (all Python versions, both main and dependabot branches):** `TestCreatePoolDuckDB` — 5 tests raise `ImportError: DuckDB ADBC driver not found` because the CI `uv sync --locked --dev` step does not install the `duckdb` optional extra. The `_resolve_duckdb()` function calls `importlib.util.find_spec("_duckdb")` which returns `None` when the `duckdb` wheel (which bundles `_duckdb`) is not installed.

2. **Docs build failure (main branch):** `uv run mkdocs build --strict` aborts with "MkDocs 2.0 is incompatible with Material for MkDocs" — `mkdocs-material` 9.7.2 emits this as a WARNING and `--strict` treats any warning as fatal.

Purpose: Unblock CI so the release pipeline (plan 07-06) can proceed from a green main branch.

Output: Green CI on next push — tests pass on 3.11 + 3.14, docs build passes.
</objective>

<execution_context>
@/Users/paul/.claude/get-shit-done/workflows/execute-plan.md
@/Users/paul/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/paul/Documents/Dev/Personal/adbc-poolhouse/.planning/STATE.md
@/Users/paul/Documents/Dev/Personal/adbc-poolhouse/pyproject.toml
@/Users/paul/Documents/Dev/Personal/adbc-poolhouse/.github/workflows/ci.yml
@/Users/paul/Documents/Dev/Personal/adbc-poolhouse/.github/workflows/docs.yml
@/Users/paul/Documents/Dev/Personal/adbc-poolhouse/mkdocs.yml
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add duckdb extra to CI sync and fix docs strict-mode warning</name>
  <files>
    .github/workflows/ci.yml
    pyproject.toml
  </files>
  <action>
**Fix 1 — CI duckdb not installed:**

In `.github/workflows/ci.yml`, change the "Sync dependencies" step from:

```yaml
- name: Sync dependencies
  run: uv sync --locked --dev
```

to:

```yaml
- name: Sync dependencies
  run: uv sync --locked --dev --extra duckdb
```

This installs the `duckdb>=0.9.1` optional dependency (declared in `[project.optional-dependencies].duckdb`) so the `_duckdb` C extension is present and `importlib.util.find_spec("_duckdb")` returns a real spec instead of `None`.

**Fix 2 — mkdocs-material 9.7.2 warning in strict mode:**

`mkdocs-material` 9.7.2 emits the warning "MkDocs 2.0 is incompatible with Material for MkDocs" unconditionally (it's a banner, not a conditional check on the installed mkdocs version). The fix is to pin mkdocs-material below the version that introduced this warning.

In `pyproject.toml`, under `[dependency-groups].docs`, change:

```toml
"mkdocs-material>=9.7.0",
```

to:

```toml
"mkdocs-material>=9.5.0,<9.7.0",
```

The last mkdocs-material 9.5.x release (9.5.50, released 2025-01-21) is compatible with mkdocs 1.6.1 and does not emit the 2.0 incompatibility warning. The lower bound 9.5.0 preserves the same theme features used in mkdocs.yml (navigation.instant, toc.follow, content.code.copy etc — all available since 9.5).

After updating pyproject.toml, regenerate the lock file:

```
uv lock
```

This regenerates `uv.lock` with a compatible mkdocs-material 9.5.x version. The CI workflow uses `uv sync --locked --group docs` which will then install the pinned 9.5.x version.
  </action>
  <verify>
    <automated>
      uv run mkdocs build --strict 2>&1 | tail -5
      # Should show "Documentation built in X.XX seconds" with no warnings/errors
    </automated>
    <manual>
      After pushing: gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
      Both CI (Tests) and Docs jobs should be green.
    </manual>
  </verify>
  <done>
    - `uv run mkdocs build --strict` exits 0 locally with no MkDocs 2.0 warning
    - `uv run pytest tests/test_pool_factory.py` passes all 11 tests (no F results) — requires duckdb installed locally with `uv sync --extra duckdb`
    - CI shows green on next push: "Quality gates (3.11)" and "Quality gates (3.14)" both pass; "Build docs" passes
  </done>
</task>

</tasks>

<verification>
Local checks before pushing:

1. `uv lock` — regenerates uv.lock with mkdocs-material 9.5.x
2. `uv sync --locked --dev --extra duckdb` — installs duckdb locally matching CI
3. `uv run pytest tests/test_pool_factory.py -v` — all 11 tests pass (was 5 FFFFF + 6 passing, now all 11 pass)
4. `uv run mkdocs build --strict` — exits 0, no MkDocs 2.0 warning

Post-push:
- `gh run list --limit 5` — verify CI and Docs workflows pass
</verification>

<success_criteria>
- Zero failing tests in test_pool_factory.py on CI (was FFFFF..........)
- `uv run mkdocs build --strict` passes in CI Docs job (no strict-mode warning abort)
- Both CI and Docs GitHub Actions workflows green on main
</success_criteria>

<output>
After completion, create `.planning/quick/1-check-with-gh-run-list-and-related-comma/1-SUMMARY.md` with:
- What was fixed (two independent CI failures)
- Files changed
- Root causes
</output>
