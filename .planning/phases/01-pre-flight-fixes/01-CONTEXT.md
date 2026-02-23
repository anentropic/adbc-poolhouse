# Phase 1: Pre-flight Fixes - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Correct two broken toolchain config entries: change `pythonVersion = "3.14"` → `"3.11"` in `[tool.basedpyright]` in `pyproject.toml`, and add `detect-secrets` to `.pre-commit-config.yaml`. The phase ends when `prek` passes with zero violations on the existing codebase. No new source code is written in this phase.

</domain>

<decisions>
## Implementation Decisions

### detect-secrets baseline
- Initialize `.secrets.baseline` as part of this phase — do not leave the hook without one
- Before committing the baseline, audit what `detect-secrets scan` finds; remove any real secrets first
- Only report scan findings to the user if actual secrets are found — silent on a clean scan
- Use explicit `--baseline .secrets.baseline` arg in the pre-commit hook config (not auto-detection)
- Exclude `.secrets.baseline` itself from detection scans to prevent circular false positives

### detect-secrets scope
- Run on all file types (not just Python and config files)
- Rely on the existing global `exclude: ^\.planning/` in `.pre-commit-config.yaml` — no separate hook-level excludes needed
- Use standard defaults otherwise (no custom exclusion patterns for tests or docs)

### Type errors after pythonVersion fix
- If fixing `pythonVersion = "3.11"` surfaces new basedpyright type errors in existing `src/` or `tests/` code, fix them in this phase
- Stay under strict mode (`typeCheckingMode = "strict"` is already set) — no `# type: ignore` suppressions
- Scaffold is tiny, so the cost of proper fixes is low

### prek gate
- Run `prek` as a hard gate at the end of the phase — plan is not complete until `prek` exits 0
- No manual override; zero violations is required

### Claude's Discretion
- Which version of `detect-secrets` to pin in `.pre-commit-config.yaml`
- Exact hook entry format for detect-secrets

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for hook configuration.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-pre-flight-fixes*
*Context gathered: 2026-02-23*
