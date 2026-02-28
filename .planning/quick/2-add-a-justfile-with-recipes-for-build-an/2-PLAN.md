---
phase: quick-2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - justfile
autonomous: true
requirements: []
must_haves:
  truths:
    - "Running `just build` produces the docs site without errors"
    - "Running `just serve` starts the dev server on the default port (8000)"
    - "Running `just serve 9000` starts the dev server on port 9000"
  artifacts:
    - path: "justfile"
      provides: "build and serve recipes using uv run mkdocs"
  key_links:
    - from: "justfile serve recipe"
      to: "uv run mkdocs serve"
      via: "--dev-addr flag with port argument"
      pattern: "mkdocs serve.*dev-addr"
---

<objective>
Add a justfile to the project root with two recipes: `build` (build the MkDocs site in strict mode) and `serve` (start the MkDocs dev server, accepting an optional port argument that defaults to 8000).

Purpose: Give contributors a single discoverable entry point for docs tasks without memorising `uv run mkdocs` flags.
Output: `justfile` at project root.
</objective>

<execution_context>
@/Users/paul/.claude/get-shit-done/workflows/execute-plan.md
@/Users/paul/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create justfile with build and serve recipes</name>
  <files>justfile</files>
  <action>
Create `justfile` at the project root with:

1. A `build` recipe that runs `uv run mkdocs build --strict` — mirrors the docs quality gate command from CLAUDE.md.

2. A `serve` recipe that accepts an optional `port` argument defaulting to `8000` and runs `uv run mkdocs serve --dev-addr 0.0.0.0:{{port}}`.

Use just's default argument syntax: `serve port="8000"`.

Do not add a shebang or set `set shell`. Keep it minimal — no `[group]` annotations, no aliases, just the two recipes.

Example file content:

```
# Build the docs site (strict mode)
build:
    uv run mkdocs build --strict

# Serve the docs dev server (default port 8000)
serve port="8000":
    uv run mkdocs serve --dev-addr 0.0.0.0:{{{{port}}}}
```

Note: in justfile syntax `{{port}}` is the variable interpolation — write it literally as `{{port}}` in the file (not escaped).
  </action>
  <verify>
    <automated>cd /Users/paul/Documents/Dev/Personal/adbc-poolhouse && just --list</automated>
    <manual>Confirm `just --list` shows both `build` and `serve` recipes with their descriptions.</manual>
  </verify>
  <done>
`just --list` shows `build` and `serve`. `just build` exits 0 and produces the docs site. `just serve 9000` would start the dev server on port 9000 (no need to actually start it to verify the recipe exists).
  </done>
</task>

</tasks>

<verification>
Run `just --list` from the project root — both `build` and `serve` should be listed.
Run `just build` — should exit 0 (same as `uv run mkdocs build --strict`).
</verification>

<success_criteria>
- `justfile` exists at project root
- `just build` runs `uv run mkdocs build --strict` and exits 0
- `just serve` defaults to port 8000
- `just serve 9000` would use port 9000
</success_criteria>

<output>
After completion, create `.planning/quick/2-add-a-justfile-with-recipes-for-build-an/2-SUMMARY.md`
</output>
