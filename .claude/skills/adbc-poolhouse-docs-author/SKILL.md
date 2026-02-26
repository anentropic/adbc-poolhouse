---
name: adbc-poolhouse-docs-author
description: Write adbc-poolhouse documentation. Applies project voice, Google-style docstrings, and humanizer pass. Use in PLAN.md execution_context for all phases >= 7.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
---

# adbc-poolhouse Docs Author Skill

## Audience

Python developers who use async DB connections — FastAPI, SQLAlchemy-async, asyncpg patterns. They are familiar with connection pools, DBAPI, and async Python. Do not over-explain ADBC internals. Do not over-explain Python basics.

## Voice

- Tone: Direct and practical — like HTTPX or SQLAlchemy docs
- Perspective: Second person ("you")
- Pages: Self-contained with a "See also" section at the bottom for cross-references

## Workflow

### Step 1 — Classify the doc type

Three types only (not full Diataxis):

| Type | User is... | Content | Path |
|------|-----------|---------|------|
| Quickstart | Getting started | Action, minimal | `docs/src/index.md` |
| How-to guide | Doing a specific task | Goal-oriented action | `docs/src/guides/` |
| API Reference | Working | Auto-generated — do not hand-write | `docs/src/reference/` |

Do NOT hand-write files in `docs/src/reference/` — `gen_ref_pages.py` auto-generates them from source.

### Step 2 — Write per type

**Quickstart** (`docs/src/index.md`):
- Install command, then a complete working code example (DuckDB, no credentials required)
- Prose only — not a doctest. Use plain code blocks (no `>>>` prompts)
- Validated in CI by running against a real DuckDB connection
- Under 5 minutes for a reader to follow from start to working pool

**How-to guides** (`docs/src/guides/`):
- Illustrative snippets showing the key concept — reader supplies their own setup
- Goal-oriented: one guide, one goal
- Use MkDocs tabbed content (`=== "Snowflake"` / `=== "DuckDB"`) for driver-specific variants
- All code examples must be realistic (no placeholder values that cannot run)

**Docstrings** (Google-style, applied to source files):
- All public classes + their public methods: class docstring + attribute docstrings (string immediately after field assignment for Pydantic config classes)
- Module-level docstrings for each public module (already exists in `__init__.py`)
- Public functions at module level: full Args/Returns/Raises sections
- Internal helpers (`_` prefix): excluded
- Examples block: key entry points only (`create_pool`, `DuckDBConfig`, `SnowflakeConfig`)
- Format:
  ```python
  def create_pool(config, *, pool_size=5):
      """One-line summary.

      Longer description if needed.

      Args:
          config: A warehouse config model instance (e.g. ``DuckDBConfig``).
          pool_size: Number of connections to keep open. Default: 5.

      Returns:
          A configured ``sqlalchemy.pool.QueuePool`` ready for use.

      Raises:
          ImportError: If the required ADBC driver is not installed.
      """
  ```

### Step 3 — Humanizer pass

After drafting any new prose or a major rewrite (>50% of a page changed), read `@/Users/paul/.claude/skills/humanizer/SKILL.md` and apply the full checklist.

Patterns most common in technical docs — eliminate these:
- **Promotional language** — "powerful", "seamlessly", "robust", "comprehensive", "effortlessly"
- **AI vocabulary** — "delve", "leverage", "streamline", "it's worth noting", "ensure that"
- **Vague attributions** — "this allows you to", "this enables", "this ensures"
- **Superficial -ing openers** — "By defining X, you can Y" → rewrite directly
- **Rule of three** — listing things in threes for rhetorical effect
- **Em dash overuse** — max one per paragraph

## Quality checklist

- [ ] All new public symbols have Args/Returns/Raises
- [ ] Key entry points have an Examples block
- [ ] New consumer-facing behaviour reflected in the relevant guide
- [ ] `uv run mkdocs build --strict` passes
- [ ] Humanizer pass applied
