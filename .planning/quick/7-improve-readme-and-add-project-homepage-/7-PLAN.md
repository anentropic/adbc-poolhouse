---
phase: quick-7
plan: 7
type: execute
wave: 1
depends_on: []
files_modified:
  - README.md
  - pyproject.toml
autonomous: true
requirements:
  - QUICK-7
must_haves:
  truths:
    - "README.md gives a new visitor enough context to evaluate the library (tagline, what problem it solves, install command, minimal working example)"
    - "pyproject.toml has [project.urls] with Homepage, Documentation, Source, and Changelog entries"
    - "PyPI sidebar will show four clickable links when the next release is published"
    - "uv run mkdocs build --strict passes"
  artifacts:
    - path: "README.md"
      provides: "Consumer-facing README with install, quick example, and links to docs"
    - path: "pyproject.toml"
      provides: "[project.urls] table with four link entries"
  key_links:
    - from: "pyproject.toml [project.urls]"
      to: "https://anentropic.github.io/adbc-poolhouse/"
      via: "Homepage and Documentation keys"
      pattern: "Homepage|Documentation|Source|Changelog"
---

<objective>
Improve README.md to be a useful consumer-facing landing page and add [project.urls] to pyproject.toml so PyPI displays sidebar links.

Purpose: The current README.md is almost empty (install command + dev-only quality gate instructions). A visitor landing on PyPI or GitHub gets no context about what the library does or how to use it. The [project.urls] entries are entirely absent — no sidebar links appear on the PyPI package page.

Output: An improved README.md and a pyproject.toml with four URL entries (Homepage, Documentation, Source, Changelog).
</objective>

<execution_context>
@/Users/paul/.claude/get-shit-done/workflows/execute-plan.md
@/Users/paul/.claude/get-shit-done/templates/summary.md
@.claude/skills/adbc-poolhouse-docs-author/SKILL.md
</execution_context>

<context>
@.planning/STATE.md
@docs/src/index.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add [project.urls] to pyproject.toml</name>
  <files>pyproject.toml</files>
  <action>
Insert a [project.urls] table after the [project] table closing (after the `bigquery` extra or the `all` extra block — after the existing `[project.optional-dependencies]` block and before `[build-system]`). Add these four entries:

```toml
[project.urls]
Homepage = "https://anentropic.github.io/adbc-poolhouse/"
Documentation = "https://anentropic.github.io/adbc-poolhouse/"
Source = "https://github.com/anentropic/adbc-poolhouse"
Changelog = "https://anentropic.github.io/adbc-poolhouse/changelog/"
```

Place the block between `[project.optional-dependencies]` and `[build-system]`. Do not change any other content in pyproject.toml.
  </action>
  <verify>
    <automated>grep -c "project.urls" /Users/paul/Documents/Dev/Personal/adbc-poolhouse/pyproject.toml && grep "Homepage\|Documentation\|Source\|Changelog" /Users/paul/Documents/Dev/Personal/adbc-poolhouse/pyproject.toml | wc -l</automated>
  </verify>
  <done>pyproject.toml contains a [project.urls] section with four entries: Homepage, Documentation, Source, Changelog.</done>
</task>

<task type="auto">
  <name>Task 2: Rewrite README.md as a consumer-facing landing page</name>
  <files>README.md</files>
  <action>
Replace the entire README.md with a consumer-facing document. Follow the docs-author skill voice (direct, practical, second person, no promotional language, no AI vocabulary).

Structure:

1. **Title and tagline** — `# adbc-poolhouse` + one-sentence description of what it does ("One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool.")

2. **Installation** — `pip install adbc-poolhouse` with a note that driver extras exist (link to docs for the full table). Keep it brief.

3. **Quick example** — A complete working DuckDB example (no credentials required). Mirror the example from `docs/src/index.md` exactly (DuckDBConfig + create_pool + pool.connect() + close_pool). Add one-line comments to the key steps.

4. **Supported warehouses** — A compact list of the warehouse names (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL / Azure SQL / Fabric). One line, not a table.

5. **Links** — Four links using absolute URLs:
   - Documentation: https://anentropic.github.io/adbc-poolhouse/
   - Changelog: https://anentropic.github.io/adbc-poolhouse/changelog/
   - Source: https://github.com/anentropic/adbc-poolhouse
   - PyPI: https://pypi.org/project/adbc-poolhouse/

6. **License** — MIT (one line).

Remove the Development / Quality Gates / Setup section entirely — that content belongs in CONTRIBUTING or the developer's local knowledge, not the consumer README. The justfile (from quick task 2) already documents dev commands.

Apply the humanizer pass from the docs-author skill: no promotional language, no "powerful/seamless/robust", no "it's worth noting", no em dash overuse, no rule-of-three listing.
  </action>
  <verify>
    <automated>cd /Users/paul/Documents/Dev/Personal/adbc-poolhouse && uv run mkdocs build --strict 2>&1 | tail -5</automated>
  </verify>
  <done>README.md has a tagline, install command, working DuckDB example, warehouse list, four documentation links, and MIT license. mkdocs build --strict passes. Development/quality-gate content is removed.</done>
</task>

</tasks>

<verification>
After both tasks:

1. pyproject.toml has `[project.urls]` with Homepage, Documentation, Source, Changelog.
2. README.md has install command, working DuckDB example, links to docs.
3. `uv run mkdocs build --strict` passes (README.md is the readme= source; any broken syntax would fail build).
4. No promotional language or AI vocabulary in new README prose.
</verification>

<success_criteria>
- pyproject.toml contains `[project.urls]` with four entries matching the deployed docs and GitHub URLs
- README.md is readable as a standalone landing page: a new visitor understands what the library does and can run the example
- `uv run mkdocs build --strict` passes
</success_criteria>

<output>
After completion, create `.planning/quick/7-improve-readme-and-add-project-homepage-/7-SUMMARY.md`
</output>
