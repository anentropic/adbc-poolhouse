---
phase: quick-5
plan: 5
type: execute
wave: 1
depends_on: []
files_modified:
  - justfile
autonomous: true
requirements: []

must_haves:
  truths:
    - "`just serve` starts the dev server without error"
    - "Incremental rebuilds are faster because `--dirtyreload` is active"
    - "`mkdocs.yml` watch entries cover both source Python and docs directories (already correct — verify no regression)"
  artifacts:
    - path: "justfile"
      provides: "serve recipe with --dirtyreload flag"
      contains: "--dirtyreload"
  key_links:
    - from: "justfile serve recipe"
      to: "mkdocs.yml watch entries"
      via: "mkdocs serve CLI"
      pattern: "mkdocs serve.*--dirtyreload"
---

<objective>
Fix mkdocs hot-reload by adding `--dirtyreload` to the `just serve` recipe for faster incremental rebuilds.

Purpose: `--dirtyreload` tells mkdocs to only rebuild pages that changed, rather than the full site on every file-save. This makes the feedback loop much tighter during docs authoring.

Output: Updated `justfile` with `--dirtyreload` flag on the `serve` recipe.

Note: Both previously reported issues are already resolved — `mkdocs.yml` has correct `watch:` entries for `src/adbc_poolhouse` and `docs/src` (lines 8-10), and the justfile already uses `127.0.0.1` (line 7). The only remaining improvement is `--dirtyreload`.
</objective>

<execution_context>
@/Users/paul/.claude/get-shit-done/workflows/execute-plan.md
@/Users/paul/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@/Users/paul/Documents/Dev/Personal/adbc-poolhouse/justfile
@/Users/paul/Documents/Dev/Personal/adbc-poolhouse/mkdocs.yml
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add --dirtyreload to justfile serve recipe</name>
  <files>justfile</files>
  <action>
    Update the `serve` recipe in `justfile` to add the `--dirtyreload` flag to the `mkdocs serve` command.

    Current line:
    ```
    uv run mkdocs serve --dev-addr 127.0.0.1:{{port}}
    ```

    Updated line:
    ```
    uv run mkdocs serve --dev-addr 127.0.0.1:{{port}} --dirtyreload
    ```

    The `--dirtyreload` flag causes mkdocs to only rebuild the pages that changed (not the whole site) when a file is saved. This significantly reduces hot-reload latency during docs authoring.

    Do NOT change the `build` recipe — strict full builds should remain clean.

    Also confirm (read-only check, no changes needed) that `mkdocs.yml` retains its `watch:` block covering `src/adbc_poolhouse` and `docs/src`.
  </action>
  <verify>
    <automated>grep -n "dirtyreload" /Users/paul/Documents/Dev/Personal/adbc-poolhouse/justfile</automated>
    <manual>Optionally run `just serve` in the project root and confirm the server starts. Edit any `.md` file and confirm the page reloads in under 2 seconds (rather than a full rebuild).</manual>
    <sampling_rate>run immediately after writing justfile</sampling_rate>
  </verify>
  <done>`justfile` serve recipe contains `--dirtyreload`; `just serve` starts without error.</done>
</task>

</tasks>

<verification>
- `grep dirtyreload justfile` returns a match on the serve recipe line
- `grep -A3 "^watch:" mkdocs.yml` shows both `src/adbc_poolhouse` and `docs/src` entries (no regression)
- `uv run mkdocs build --strict` still passes (build recipe unchanged)
</verification>

<success_criteria>
`just serve` launches mkdocs with `--dirtyreload` active. File-save in `docs/src/` or `src/adbc_poolhouse/` triggers a partial rebuild (single page) rather than a full site rebuild.
</success_criteria>

<output>
After completion, create `.planning/quick/5-mkdocs-hot-reload-not-working/5-SUMMARY.md` with what was changed and why.
</output>
