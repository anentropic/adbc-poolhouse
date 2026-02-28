---
phase: quick-3
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/src/guides/databricks.md
  - docs/src/guides/redshift.md
  - docs/src/guides/trino.md
  - docs/src/guides/mssql.md
  - docs/src/guides/teradata.md
autonomous: true
requirements: []
---

<objective>
Add hyperlink to Foundry installation guide in all Foundry driver pages.

Purpose: Users reading warehouse guides need direct access to the Foundry installation instructions instead of plain text.

Output: All Foundry driver pages (Databricks, Redshift, Trino, MSSQL, Teradata) with linked "Foundry installation guide" text.
</objective>

<execution_context>
@/Users/paul/.claude/get-shit-done/workflows/execute-plan.md
@.claude/skills/adbc-poolhouse-docs-author/SKILL.md
</execution_context>

<context>
@.planning/STATE.md
docs/src/guides/databricks.md (line 4)
docs/src/guides/redshift.md (line 4)
docs/src/guides/trino.md (line 4)
docs/src/guides/mssql.md (line 4)
docs/src/guides/teradata.md (line 8)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add Foundry installation guide hyperlinks to all warehouse guides</name>
  <files>
docs/src/guides/databricks.md
docs/src/guides/redshift.md
docs/src/guides/trino.md
docs/src/guides/mssql.md
docs/src/guides/teradata.md
  </files>
  <action>
In each of the five Foundry driver guides, replace the plain text "Follow your Foundry installation guide to install it" with a markdown hyperlink pointing to https://arrow.apache.org/adbc/current/driver/installation.html

Specific changes:

1. databricks.md line 4: Replace "Follow your Foundry installation guide to install it" with "Follow the [Foundry installation guide](https://arrow.apache.org/adbc/current/driver/installation.html) to install it"

2. redshift.md line 4: Same replacement as above

3. trino.md line 4: Same replacement as above

4. mssql.md line 4: Same replacement as above

5. teradata.md line 8: Same replacement as above

After editing, run mkdocs strict build to confirm no regressions.
  </action>
  <verify>
grep -l "Foundry installation guide" docs/src/guides/{databricks,redshift,trino,mssql,teradata}.md | wc -l returns 5 (all files contain the phrase)
grep -l "\[Foundry installation guide\]" docs/src/guides/{databricks,redshift,trino,mssql,teradata}.md | wc -l returns 5 (all files contain the hyperlink)
uv run mkdocs build --strict passes with no errors
  </verify>
  <done>All five Foundry driver pages have hyperlinked text "Foundry installation guide" pointing to https://arrow.apache.org/adbc/current/driver/installation.html, strict build passes</done>
</task>

</tasks>

<verification>
After task completion, verify that:
- Each of the five guide pages contains exactly one markdown hyperlink for the Foundry installation guide
- No other text changes were made
- mkdocs build --strict completes without errors or warnings
- Hyperlink target is correct and matches constraint URL exactly
</verification>

<success_criteria>
- All five Foundry driver pages (databricks.md, redshift.md, trino.md, mssql.md, teradata.md) contain the hyperlinked text
- Strict markdown build passes
- Users clicking the link are directed to the official Apache Arrow ADBC Foundry driver installation page
</success_criteria>

<output>
After completion, update `.planning/STATE.md` to log quick task #3 as complete in the Quick Tasks Completed table.
</output>
