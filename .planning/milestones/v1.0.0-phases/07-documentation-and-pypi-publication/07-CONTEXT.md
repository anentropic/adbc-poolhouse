# Phase 7: Documentation and PyPI Publication - Context

**Gathered:** 2026-02-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a documented, pip-installable library live on PyPI — with a Material for MkDocs docs site, Google-style docstrings across all public symbols, a git-cliff changelog, a tag-push release workflow, and an adbc-poolhouse-docs-author Claude skill that enforces documentation as a completion requirement for all future phases.

</domain>

<decisions>
## Implementation Decisions

### Docs site structure
- Navigation: **Getting Started / Guides / API Reference** (three top-level sections)
- Theme: **Material for MkDocs + mkdocstrings** — auto-generates API ref from docstrings
- Guides section contains four pages: Pool lifecycle, Consumer patterns, Configuration reference, Snowflake-specific guide
- **Changelog page included** in the docs site, auto-generated from git-cliff output; appears in nav

### Docstring coverage
- Scope: **all public classes + their public methods**, **module-level docstrings** for each public module, **public functions** at module level — internal helpers (`_` prefix) are excluded
- Format: **Google-style** with Args, Returns, Raises sections on every covered symbol
- Examples block: **key entry points only** (e.g. `create_pool`, `PoolConfig`) — not every method
- Exceptions documented via **Raises section inline per method** (not a separate exceptions page)
- Quickstart guide: **prose only**, validated in CI by running it against a real DuckDB connection — not as a doctest

### Release workflow
- Trigger: **git tag push** (e.g. `v0.1.0`) — same pattern as cubano
- Pipeline: `build → (validate + changelog in parallel) → publish-testpypi → publish-pypi → deploy-docs`
- Added vs cubano: **TestPyPI step** — install from TestPyPI, smoke-test, then publish to real PyPI
- Wheel validations before publishing:
  1. `py.typed` marker present (unzip + grep)
  2. Public API imports succeed (`from adbc_poolhouse import create_pool, PoolConfig`)
  3. Version in package matches the git tag
  4. Both wheel and sdist install cleanly across Python 3.11 and 3.12 in isolated venvs
- **Docs deploy to GitHub Pages** on every tag, triggered after publish succeeds

### Docs-author skill
- Location: `.claude/skills/adbc-poolhouse-docs-author/SKILL.md`
- Four responsibilities:
  1. Write Google-style docstrings to the project's house standard (exact Args/Returns/Raises/Examples format)
  2. Update `mkdocs.yml` nav and create `.md` stub files when new modules are added
  3. Validate docs completeness before marking any phase done (checklist gate)
  4. Write and update consumer-facing guides (pool lifecycle, consumer patterns, quickstart)
- **Audience:** Python developers using async DB connections — FastAPI, SQLAlchemy-async, asyncpg patterns. Assume async Python familiarity; do not over-explain ADBC internals.
- **Classification model:** Lighter than Diataxis — three types only: Quickstart, How-to Guide, API Reference. Reference is auto-generated; Claude writes Quickstart and Guides.
- **Humanizer pass:** Required on all new prose or any page with >50% rewritten content — same patterns to eliminate as cubano's skill (promotional language, AI vocabulary, vague attributions, em dash overuse)
- **Quality checklist** (must pass before marking a doc task done):
  - All new public symbols have Args/Returns/Raises
  - Key entry points have an Examples block
  - New consumer-facing behaviour reflected in the relevant guide
  - `uv run mkdocs build --strict` passes
  - Humanizer pass applied

### CLAUDE.md quality gate
- `CLAUDE.md` must instruct plan-phase to include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>` for **all plans in phases ≥ 7** — not just plans labelled as documentation tasks

### Claude's Discretion
- Exact MkDocs configuration details (plugins, extensions, colour scheme)
- git-cliff configuration format (`cliff.toml`)
- Exact CI job names and step ordering within the release workflow
- How to handle ADBC driver-specific tabbed content in guides (if needed)

</decisions>

<specifics>
## Specific Ideas

- Release workflow should be structurally identical to cubano's `release.yml` — adapt package name, import validation command (`adbc_poolhouse` not `cubano`), and add the TestPyPI step
- The docs-author skill structure should mirror `cubano-docs-author/SKILL.md` — same sections (Audience, Voice, Workflow, Quality checklist), adapted for adbc-poolhouse audience and lighter classification model

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-documentation-and-pypi-publication*
*Context gathered: 2026-02-26*
