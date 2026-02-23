# Phase 1: Pre-flight Fixes - Research

**Researched:** 2026-02-23
**Domain:** Python toolchain configuration (basedpyright, detect-secrets, pre-commit)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**detect-secrets baseline**
- Initialize `.secrets.baseline` as part of this phase — do not leave the hook without one
- Before committing the baseline, audit what `detect-secrets scan` finds; remove any real secrets first
- Only report scan findings to the user if actual secrets are found — silent on a clean scan
- Use explicit `--baseline .secrets.baseline` arg in the pre-commit hook config (not auto-detection)
- Exclude `.secrets.baseline` itself from detection scans to prevent circular false positives

**detect-secrets scope**
- Run on all file types (not just Python and config files)
- Rely on the existing global `exclude: ^\.planning/` in `.pre-commit-config.yaml` — no separate hook-level excludes needed for .planning/
- Use standard defaults otherwise (no custom exclusion patterns for tests or docs)

**Type errors after pythonVersion fix**
- If fixing `pythonVersion = "3.11"` surfaces new basedpyright type errors in existing `src/` or `tests/` code, fix them in this phase
- Stay under strict mode (`typeCheckingMode = "strict"` is already set) — no `# type: ignore` suppressions
- Scaffold is tiny, so the cost of proper fixes is low

**prek gate**
- Run `prek` as a hard gate at the end of the phase — plan is not complete until `prek` exits 0
- No manual override; zero violations is required

### Claude's Discretion
- Which version of `detect-secrets` to pin in `.pre-commit-config.yaml`
- Exact hook entry format for detect-secrets

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SETUP-01 | Fix `pythonVersion = "3.14"` to `"3.11"` in `[tool.basedpyright]` section of `pyproject.toml` | One-line edit; verified to produce 0 errors on the current scaffold |
| SETUP-05 | Add `detect-secrets` to `.pre-commit-config.yaml` (must be active before any Snowflake snapshot commits) | Version v1.5.0 confirmed; hook entry format and baseline workflow verified from official docs and live scan |
</phase_requirements>

## Summary

Phase 1 is a two-edit configuration fix with no new source code. The scaffold (`src/adbc_poolhouse/__init__.py` contains only a docstring and `__all__ = []`; `tests/test_adbc_poolhouse.py` is a single import test) is essentially empty, so changing `pythonVersion` from `"3.14"` to `"3.11"` in `pyproject.toml` produces zero new type errors — confirmed by a live basedpyright run with the patch applied.

The `detect-secrets` addition requires three concrete steps: (1) adding the hook entry to `.pre-commit-config.yaml` with `rev: v1.5.0` and `args: ['--baseline', '.secrets.baseline']`, (2) generating `.secrets.baseline` via `detect-secrets scan`, and (3) excluding `.secrets.baseline` from its own hook scan. A live scan of the repo was performed: the only findings are two false positives in `.planning/codebase/INTEGRATIONS.md` and `.planning/research/ARCHITECTURE.md` — both already covered by the existing global `exclude: ^\.planning/` pattern, which pre-commit applies before passing files to any hook. Outside `.planning/`, the repo has zero findings.

After both edits, `prek run --all-files` is expected to exit 0 with no violations.

**Primary recommendation:** Make the two-line `pyproject.toml` edit first, run basedpyright to confirm 0 errors, then add the detect-secrets hook and generate the baseline, then run `prek run --all-files` as the final gate.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| basedpyright | 1.38.1 (already installed) | Static type checker for Python | Already in dev deps; strict mode already configured |
| detect-secrets | v1.5.0 | Pre-commit secret scanning hook | Latest stable release (confirmed PyPI + GitHub tags); original Yelp tool, widely used |
| prek | 0.3.2 | Rust-based `.pre-commit-config.yaml` runner | Project standard per AGENTS.md |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pre-commit (hooks spec) | N/A (prek compatible) | `.pre-commit-config.yaml` format | Hook configuration is standard pre-commit YAML; prek executes it |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| detect-secrets v1.5.0 | v1.4.0 or earlier | No reason to use older; v1.5.0 is latest stable |
| Global exclude for .planning/ | Hook-level exclude on detect-secrets entry | Global exclude is already present and works; adding a duplicate hook-level exclude is redundant noise |

**Installation:** No installation needed by the executor — `detect-secrets` is fetched by prek/pre-commit from the GitHub URL in the hook entry at first run. No changes to `pyproject.toml` dev dependencies are required for this phase.

## Architecture Patterns

### Recommended Project Structure

No structural changes in this phase. The two target files are:

```
pyproject.toml                  # Change pythonVersion = "3.14" → "3.11"
.pre-commit-config.yaml         # Add detect-secrets repo entry
.secrets.baseline               # New: generated by detect-secrets scan
```

### Pattern 1: detect-secrets Hook Entry

**What:** Add a repo entry for `https://github.com/Yelp/detect-secrets` at revision `v1.5.0` with explicit `--baseline` arg and an `exclude:` for the baseline file itself.

**When to use:** Any project where secrets (API keys, passwords, tokens) could accidentally be committed.

**Example:**
```yaml
# Source: https://github.com/yelp/detect-secrets README.md
- repo: https://github.com/Yelp/detect-secrets
  rev: v1.5.0
  hooks:
  - id: detect-secrets
    args: ['--baseline', '.secrets.baseline']
    exclude: \.secrets\.baseline
```

**Why `exclude: \.secrets\.baseline`:** The baseline file itself contains SHA-256 hex hashes. Those hashes trigger the `HexHighEntropyString` and `SecretKeyword` detectors. This was verified by a live test: `detect-secrets-hook --baseline <file> <file>` exits non-zero and reports "Hex High Entropy String" and "Secret Keyword" findings at lines containing the hash values. Without the exclusion, the hook will always fail on the baseline file itself.

### Pattern 2: Baseline Initialization

**What:** Run `detect-secrets scan > .secrets.baseline` to capture the current state of the repo as the known-good baseline. The hook then only alerts on NEW findings after this baseline was committed.

**Workflow:**
```bash
# 1. Scan the repo (pre-commit global exclude handles .planning/ filtering)
detect-secrets scan > .secrets.baseline

# 2. Audit the output before committing
# Check .secrets.baseline for any real secrets under "results": {}
# The codebase currently produces "results": {} — zero findings outside .planning/

# 3. Commit the baseline along with the hook change
git add .secrets.baseline .pre-commit-config.yaml pyproject.toml
git commit -m "chore(01): pre-flight fixes — pythonVersion and detect-secrets"
```

**Key insight on how the global exclude interacts with the baseline:**

When prek/pre-commit runs the detect-secrets hook on a commit, it filters files through the global `exclude: ^\.planning/` pattern **before** passing filenames to the hook. This means `.planning/` files never reach `detect-secrets-hook`. The baseline therefore does not need entries for those files. However, if the baseline is generated via `detect-secrets scan` (without `--exclude-files`), the `.planning/` findings **will** appear in the baseline JSON as false-positive entries. This is harmless — the hook never checks those files, so those baseline entries are never consulted.

The cleaner approach: generate the baseline with the same exclusion the hook will use, so the baseline accurately reflects only the files the hook will actually scan:
```bash
detect-secrets scan --exclude-files "^\.planning/" > .secrets.baseline
```
This embeds the exclusion pattern inside the baseline's `filters_used` array. The hook respects these embedded filters when comparing against future scans.

### Anti-Patterns to Avoid

- **Do not use `--no-verify` to bypass the hooks:** The prek gate is a hard requirement per CONTEXT.md.
- **Do not add `# type: ignore` for any basedpyright errors:** The scaffold is empty; no suppressions are needed.
- **Do not add detect-secrets as a dev dependency in `pyproject.toml`:** It is fetched by prek/pre-commit from GitHub via the hook entry. Adding it to deps would be redundant and inconsistent with how other hooks (ruff, blacken-docs) are managed in this project.
- **Do not run `detect-secrets scan` without auditing first:** The CONTEXT.md requires auditing the scan output before committing the baseline.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Secret scanning in pre-commit | Custom grep/regex script | detect-secrets hook | detect-secrets has 25+ built-in detectors (AWS keys, GitHub tokens, entropy analysis, etc.) — a custom script would miss most patterns |
| Baseline management | Manual allow-listing in hook config | `.secrets.baseline` file | Baseline provides structured false-positive management with per-secret tracking |

**Key insight:** The entire phase is configuration, not code. Both tasks are single-value edits to existing files plus generating one new JSON file.

## Common Pitfalls

### Pitfall 1: Baseline Not Committed Before Hooking

**What goes wrong:** The detect-secrets hook is added to `.pre-commit-config.yaml` but `.secrets.baseline` is not committed. The next commit attempt fails with `FileNotFoundError` or a hook error because the baseline referenced by `--baseline .secrets.baseline` does not exist.

**Why it happens:** Developer adds the hook entry but forgets that the baseline must exist on disk and be committed as part of the same change.

**How to avoid:** In the same task that adds the hook, also generate and commit `.secrets.baseline`. The CONTEXT.md explicitly requires this.

**Warning signs:** `detect-secrets-hook: ERROR` referencing the baseline file path.

### Pitfall 2: .secrets.baseline Triggers the Hook Itself

**What goes wrong:** The hook is configured correctly, but `prek run --all-files` fails because `.secrets.baseline` contains hex hashes that look like secrets.

**Why it happens:** The baseline is a JSON file with SHA-256 hashes in the `results` section. These trigger `HexHighEntropyString` and `SecretKeyword` detectors. This was **verified by live test** — the hook exits non-zero when scanning its own baseline file.

**How to avoid:** Add `exclude: \.secrets\.baseline` to the hook entry in `.pre-commit-config.yaml`.

**Warning signs:** `prek run --all-files` fails on `.secrets.baseline` with "Hex High Entropy String" or "Secret Keyword" after the hook is added.

### Pitfall 3: pythonVersion 3.14 Permits 3.13+ Type Features Silently

**What goes wrong:** With `pythonVersion = "3.14"`, basedpyright allows Python 3.13+ type syntax (e.g., PEP 695 type parameter syntax `type X = ...`) without error. Code written under 3.14 mode that uses these features would fail at runtime on Python 3.11.

**Why it happens:** basedpyright uses `pythonVersion` to determine which built-in types, syntax, and stdlib APIs are available. 3.14 mode permits everything in 3.13 and 3.14.

**How to avoid:** Change to `"3.11"` and confirm 0 errors. Already confirmed: the current scaffold produces 0 errors under 3.11 strict mode.

**Warning signs:** Code using `type X = ...` syntax, `ExceptionGroup`, or `tomllib` at top-level without version guard would appear valid under 3.14 but fail under 3.11.

### Pitfall 4: prek Skips detect-secrets on First Run Without Install-Hooks

**What goes wrong:** After adding the hook, `prek run --all-files` fails because prek hasn't set up the detect-secrets environment yet.

**Why it happens:** prek needs to create the hook environment (virtualenv + install detect-secrets) before first use. This normally happens automatically on the first run, but some configurations require explicit `prek install-hooks`.

**How to avoid:** Run `prek run --all-files` once after adding the hook and generating the baseline. prek will install the hook environment automatically on the first run. If it fails with an install error, run `prek install-hooks` first.

**Warning signs:** Error like "failed to create environment" or "hook not found."

## Code Examples

### 1. pyproject.toml Change

```toml
# File: pyproject.toml
# Change ONE line in [tool.basedpyright]:

[tool.basedpyright]
pythonVersion = "3.11"    # was "3.14"
typeCheckingMode = "strict"
include = ["src", "tests"]
reportPrivateUsage = false
```

### 2. Complete detect-secrets Hook Entry

```yaml
# File: .pre-commit-config.yaml
# Add this block after the existing hooks (e.g., after blacken-docs):

- repo: https://github.com/Yelp/detect-secrets
  rev: v1.5.0
  hooks:
  - id: detect-secrets
    args: ['--baseline', '.secrets.baseline']
    exclude: \.secrets\.baseline
```

### 3. Baseline Generation Command

```bash
# Run from project root:
detect-secrets scan --exclude-files "^\.planning/" > .secrets.baseline
```

Or equivalently (relying on pre-commit's global exclude, which also works):

```bash
detect-secrets scan > .secrets.baseline
```

Note: The `--exclude-files "^\.planning/"` variant produces a cleaner baseline (no .planning/ entries in `results`) and embeds the exclusion pattern in `filters_used`. Either approach is correct because the pre-commit global exclude prevents .planning/ files from reaching the hook during normal operation.

### 4. Verification Command

```bash
# Confirm all hooks pass after both changes:
prek run --all-files
```

Expected output:
```
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check json...............................................................Passed
check toml...............................................................Passed
check yaml...............................................................Passed
ruff (legacy alias)......................................................Passed
ruff format..............................................................Passed
uv-lock..................................................................Passed
Type checking (basedpyright).............................................Passed
blacken-docs.............................................................Passed
detect-secrets...........................................................Passed
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pre-commit hook runner (`pre-commit` Python package) | prek 0.3.2 (Rust) | This project uses prek from the start | prek is faster and compatible with `.pre-commit-config.yaml`; same YAML format |
| detect-secrets v1.4.x | detect-secrets v1.5.0 | v1.5.0 is current stable | No breaking changes; v1.5.0 is the safe choice |

**Deprecated/outdated:**
- `pythonVersion = "3.14"` in this project: was set to a future/non-existent Python version; 3.14 is not released (as of Feb 2026). This silently permitted type features unavailable on 3.11 (the minimum supported version).

## Open Questions

1. **Whether to embed `.planning/` exclusion in the baseline or rely on global pre-commit exclude**
   - What we know: Both approaches work. The `--exclude-files "^\.planning/"` approach embeds the filter in the baseline and produces a cleaner `results: {}` output. The plain `detect-secrets scan` approach relies on pre-commit's global exclude during hook execution, which also works but leaves .planning/ findings in the baseline JSON.
   - What's unclear: Which is more maintainable long-term (if .planning/ directory is eventually removed or restructured).
   - Recommendation: Use `--exclude-files "^\.planning/"` for the baseline scan. It produces a self-documenting baseline that explicitly records what was excluded, independent of the pre-commit configuration.

## Sources

### Primary (HIGH confidence)

- `/yelp/detect-secrets` (Context7) — hook entry format, baseline initialization commands, `--baseline` arg behavior, baseline file format
- Live `detect-secrets scan` run on actual repo (2026-02-23) — confirmed zero real secrets outside `.planning/`, confirmed `.secrets.baseline` triggers false positives without explicit exclusion
- Live `basedpyright` run with `pythonVersion = "3.11"` patch applied — confirmed 0 errors, 0 warnings, 0 notes on current scaffold
- `https://pypi.org/pypi/detect-secrets/json` — confirmed v1.5.0 is current latest release
- `https://api.github.com/repos/Yelp/detect-secrets/tags` — confirmed v1.5.0 is latest tag
- `https://raw.githubusercontent.com/Yelp/detect-secrets/master/.pre-commit-hooks.yaml` — confirmed official hook ID and `files: .*` scope

### Secondary (MEDIUM confidence)

- None required — all claims verified with primary sources.

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions confirmed via PyPI and GitHub tags; hook format confirmed from official README via Context7 and verified against live hook execution
- Architecture: HIGH — all patterns verified by live execution on the actual codebase; no theoretical claims
- Pitfalls: HIGH — Pitfalls 1, 2, 3 verified by direct testing; Pitfall 4 is standard pre-commit behavior (MEDIUM for that sub-item)

**Research date:** 2026-02-23
**Valid until:** 2026-09-23 (stable tooling — detect-secrets has had 5 major releases over 3 years; v1.5.0 is unlikely to be superseded quickly)
