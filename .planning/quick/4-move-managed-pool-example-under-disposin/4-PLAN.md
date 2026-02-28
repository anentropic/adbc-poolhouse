---
quick_task: 4
type: execute
requires: []
files_modified:
  - docs/src/guides/pool-lifecycle.md
autonomous: true
---

<objective>
Reorganize pool-lifecycle.md to move the `managed_pool` context manager example from "Pytest fixture pattern" section to directly under "Disposing the pool" as an alternative teardown pattern.

Purpose: Improve documentation flow — `managed_pool` is a teardown mechanism, not a pytest-specific pattern. Current placement after pytest examples is misleading.
Output: Reorganized pool-lifecycle.md with `managed_pool` example moved to logical location.
</objective>

<execution_context>
@.claude/skills/adbc-poolhouse-docs-author/SKILL.md
</execution_context>

<context>
@/Users/paul/Documents/Dev/Personal/adbc-poolhouse/docs/src/guides/pool-lifecycle.md
</context>

<tasks>

<task type="auto">
  <name>Move managed_pool example to Disposing the pool section</name>
  <files>docs/src/guides/pool-lifecycle.md</files>
  <action>
Restructure docs/src/guides/pool-lifecycle.md:

1. Keep "Disposing the pool" section (lines 18-28) with close_pool() example
2. Add `managed_pool` as an alternative immediately after close_pool() example (lines 29-31):
   - Prose: "For scripts and short-lived processes, use `managed_pool` as a context manager instead:"
   - Code block with managed_pool example (currently lines 50-60)

3. Trim "Pytest fixture pattern" section (currently lines 30-48):
   - Keep only the pytest fixture example (lines 34-46)
   - Remove the intro line about managed_pool (currently lines 50-51)
   - Update section intro to focus only on pytest patterns

4. Update "See also" section (line 103-106) — no changes needed, links remain valid

Result structure:
- Checking out and returning connections
- Disposing the pool
  - close_pool() approach
  - managed_pool() alternative (NEW location)
- Pytest fixture pattern
  - pytest.fixture example
- Tuning the pool
- Common mistakes
- See also

Apply humanizer pass to any prose moves. Ensure code blocks render correctly in mkdocs.
  </action>
  <verify>
cd /Users/paul/Documents/Dev/Personal/adbc-poolhouse && uv run mkdocs build --strict 2>&1 | grep -E "(ERROR|pool-lifecycle)" || echo "Build successful"
  </verify>
  <done>
- managed_pool example moved to "Disposing the pool" section
- managed_pool appears after close_pool() as alternative
- Pytest fixture section still includes pytest fixture example
- No broken links, no broken code blocks
- mkdocs build --strict passes
  </done>
</task>

</tasks>

<verification>
After completion, verify the reorganized page renders correctly and the section hierarchy makes sense:
- Prose flows logically from close_pool() to managed_pool() as alternatives
- Pytest section is self-contained and focused on test patterns
- All cross-references remain valid
</verification>

<success_criteria>
- docs/src/guides/pool-lifecycle.md restructured with managed_pool under "Disposing the pool"
- mkdocs build --strict passes without errors
- All code blocks and links intact
</success_criteria>

<output>
After completion, update .planning/STATE.md "Quick Tasks Completed" section with:
- Task 4: "move managed_pool example under Disposing the pool"
- Date: 2026-02-28
- Status: Complete
</output>
