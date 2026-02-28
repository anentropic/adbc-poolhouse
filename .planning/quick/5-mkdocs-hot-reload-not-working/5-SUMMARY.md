---
phase: quick-5
plan: 5
subsystem: docs-tooling
tags: [mkdocs, justfile, developer-experience, hot-reload]
dependency_graph:
  requires: []
  provides: [faster-docs-hot-reload]
  affects: [justfile]
tech_stack:
  added: []
  patterns: [mkdocs --dirtyreload]
key_files:
  created: []
  modified:
    - justfile
decisions:
  - "--dirtyreload on serve only — build recipe unchanged (strict full builds must be clean)"
metrics:
  duration: "~19s"
  completed: "2026-02-28"
  tasks_completed: 1
  files_modified: 1
---

# Quick Task 5: Fix mkdocs Hot-Reload (add --dirtyreload)

**One-liner:** Added `--dirtyreload` to `just serve` so mkdocs only rebuilds changed pages instead of the full site on every file-save.

## What Was Done

### Task 1: Add --dirtyreload to justfile serve recipe

Updated the `serve` recipe in `justfile`:

Before:
```
uv run mkdocs serve --dev-addr 127.0.0.1:{{port}}
```

After:
```
uv run mkdocs serve --dev-addr 127.0.0.1:{{port}} --dirtyreload
```

**Why:** Without `--dirtyreload`, mkdocs performs a full site rebuild on every file-save. With it, only the modified page is rebuilt — reducing rebuild time from several seconds to under a second during docs authoring.

**Scope:** Only the `serve` recipe was changed. The `build` recipe intentionally retains a clean full rebuild for strict mode correctness checks.

**Confirmed no regression:** `mkdocs.yml` watch entries remain intact:
- `src/adbc_poolhouse` (line 9)
- `docs/src` (line 10)

**Commit:** 32d6a6d

## Verification

- `grep dirtyreload justfile` matches line 7 of the serve recipe.
- `mkdocs.yml` watch block confirmed covering both `src/adbc_poolhouse` and `docs/src` — no regression.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `/Users/paul/Documents/Dev/Personal/adbc-poolhouse/justfile` contains `--dirtyreload` on the serve recipe line.
- Commit 32d6a6d exists in git log.
