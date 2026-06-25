---
phase: 21
plan: 03
type: execute
wave: 2
depends_on: [21-01]
files_modified:
  - docs/src/guides/quack.md
  - docs/src/guides/configuration.md
  - docs/src/index.md
  - mkdocs.yml
autonomous: true
requirements: [QUACK-13, QUACK-14, QUACK-15, QUACK-16, QUACK-17, QUACK-18]
requirements_addressed: [QUACK-13, QUACK-14, QUACK-15, QUACK-16, QUACK-17, QUACK-18]

must_haves:
  truths:
    - "User can read a per-warehouse guide at docs/src/guides/quack.md"
    - "Guide includes alpha-status admonition and upstream GitHub link"
    - "Install command includes --pre flag for the alpha driver"
    - "URI mode, decomposed mode, token/TLS, and env-var loading all documented with realistic snippets"
    - "Quack appears in configuration.md table, index.md backend listing, and mkdocs.yml nav"
    - "uv run mkdocs build --strict passes with zero warnings"
    - "Humanizer pass applied — no promotional language, AI vocabulary, em-dash overuse"
  artifacts:
    - path: "docs/src/guides/quack.md"
      provides: "Per-warehouse guide page with alpha warning, install, URI mode, decomposed mode, TLS/token, env vars, See also"
      contains: "https://github.com/gizmodata/adbc-driver-quack"
    - path: "docs/src/guides/configuration.md"
      provides: "Updated table row for QuackConfig with QUACK_ env prefix"
      contains: "QUACK_"
    - path: "docs/src/index.md"
      provides: "Quack listed in PyPI drivers table with --pre install command, plus alphabetical entry in PyPI-installed config listing"
      contains: "Quack"
    - path: "mkdocs.yml"
      provides: "Nav entry for guides/quack.md under Warehouse Guides"
      contains: "guides/quack.md"
  key_links:
    - from: "docs/src/guides/quack.md"
      to: "QuackConfig"
      via: "mkdocstrings cross-ref [QuackConfig][adbc_poolhouse.QuackConfig]"
      pattern: "\\[QuackConfig\\]\\[adbc_poolhouse\\.QuackConfig\\]"
    - from: "mkdocs.yml nav"
      to: "docs/src/guides/quack.md"
      via: "nav entry"
      pattern: "guides/quack.md"
---

<objective>
Deliver the documentation surface for the Quack backend per the project's docs quality gate (CLAUDE.md, phase >= 7).

Purpose: complete QUACK-13 through QUACK-18 — per-warehouse guide page, configuration table row, index listing, mkdocs nav, strict-build pass, and humanizer pass. Documentation is a completion requirement for every phase from Phase 7 onwards, not just plans labelled documentation.

Output:
- New `docs/src/guides/quack.md` mirroring `docs/src/guides/clickhouse.md` structure: alpha admonition, upstream link, `pip install --pre adbc-poolhouse[quack]`, URI-mode example, decomposed-mode example, token + TLS example, env-var section, See also footer.
- Quack row in `docs/src/guides/configuration.md` env_prefix table.
- Quack entry in `docs/src/index.md` (PyPI drivers table + PyPI-installed config listing).
- Nav entry in `mkdocs.yml` under Warehouse Guides.
- `uv run mkdocs build --strict` green.
- Humanizer pass applied to all new prose.

This plan depends on Plan 01 (QuackConfig must exist for mkdocstrings cross-refs to resolve under strict mode).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
@.claude/skills/adbc-poolhouse-docs-author/SKILL.md
@/Users/paul/.claude/skills/humanizer/SKILL.md
</execution_context>

<context>
@.planning/phases/21-quack-backend/21-CONTEXT.md
@.planning/phases/21-quack-backend/21-RESEARCH.md
@.planning/phases/21-quack-backend/21-VALIDATION.md
@CLAUDE.md
@docs/src/guides/clickhouse.md
@docs/src/guides/configuration.md
@docs/src/index.md
@mkdocs.yml
@src/adbc_poolhouse/_quack_config.py

<interfaces>
<!-- Cross-ref syntax (CRITICAL — Markdown, not RST). -->

mkdocstrings cross-reference format (Markdown):
- Class: `[QuackConfig][adbc_poolhouse.QuackConfig]`
- Function: `[create_pool][adbc_poolhouse.create_pool]`
- Attribute: `[QuackConfig.uri][adbc_poolhouse.QuackConfig.uri]`

WRONG (RST — will appear as rogue colons in output):
- `:class:`QuackConfig``
- `:func:`create_pool``
- `:meth:`to_adbc_kwargs``

Admonition syntax (MkDocs Material):
```
!!! warning "Alpha driver"
    The `adbc-driver-quack` package is an alpha release. APIs and behaviour may change.
```

Tabbed content for mode variants (per docs-author skill):
```
=== "URI mode"
    ...
=== "Decomposed mode"
    ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Write docs/src/guides/quack.md</name>
  <files>docs/src/guides/quack.md</files>
  <read_first>
    - docs/src/guides/clickhouse.md (FULL file — copy structure section-by-section; pay attention to alpha admonition, dual-mode tabbed content, env-var loading section, See also footer)
    - .claude/skills/adbc-poolhouse-docs-author/SKILL.md (voice, classification, humanizer pass requirements)
    - /Users/paul/.claude/skills/humanizer/SKILL.md (full checklist — apply during this task)
    - .planning/phases/21-quack-backend/21-CONTEXT.md "Documentation" section (required sections and content)
    - .planning/phases/21-quack-backend/21-RESEARCH.md "Documentation Strategy" section (structure outline)
    - src/adbc_poolhouse/_quack_config.py (source for accurate field descriptions and code examples)
  </read_first>
  <action>
    Create `docs/src/guides/quack.md` from scratch. Mirror `clickhouse.md` structure but adapt for Quack's single-token simplicity.

    Required structure (in order):

    1. **H1 title**: `# Quack`

    2. **Alpha admonition** (immediately under H1):
       ```
       !!! warning "Alpha driver"
           The [`adbc-driver-quack`](https://github.com/gizmodata/adbc-driver-quack) package is an alpha release (latest: `0.1.0a6` as of this writing). APIs and behaviour may change between releases.
       ```
       This satisfies QUACK-14 (admonition + upstream link in one block).

    3. **Brief intro paragraph** (2-3 sentences): describe what Quack is (DuckDB Quack remote protocol), what `QuackConfig` provides (URI XOR decomposed connection modes, optional token + TLS). Second-person voice ("you").

    4. **`## Install`**:
       ```
       ```bash
       pip install --pre adbc-poolhouse[quack]
       ```
       ```
       Followed by one sentence explaining why `--pre` is required (alpha driver; pip default excludes pre-releases unless flagged). The literal install command MUST contain `pip install --pre adbc-poolhouse[quack]` exactly — acceptance criteria greps for it.

    5. **`## Connection`**: one paragraph explaining the two modes and that mutual exclusion is enforced ([`ConfigurationError`][adbc_poolhouse.ConfigurationError] raised on both-set or neither-set). Use Markdown cross-ref syntax.

    6. **`### URI mode`** with a fenced ```python``` block:
       ```python
       from adbc_poolhouse import QuackConfig, create_pool

       config = QuackConfig(uri="quack://quack.example.com:8080")
       pool = create_pool(config)
       ```
       Note: `uri` is a plain `str`, not `SecretStr`, because the driver's URI cannot embed credentials (one-sentence callout).

    7. **`### Decomposed mode`** with a fenced ```python``` block:
       ```python
       from adbc_poolhouse import QuackConfig, create_pool

       config = QuackConfig(host="quack.example.com", port=8080)
       pool = create_pool(config)
       ```
       Mention that `port` is optional.

    8. **`### Authentication and TLS`** — show token + tls usage:
       ```python
       from pydantic import SecretStr
       from adbc_poolhouse import QuackConfig, create_pool

       config = QuackConfig(
           host="quack.example.com",
           port=8080,
           token=SecretStr("YOUR-TOKEN-HERE"),  # pragma: allowlist secret
           tls=True,
       )
       pool = create_pool(config)
       ```
       SECURITY: use `"YOUR-TOKEN-HERE"` (obvious placeholder), append `# pragma: allowlist secret` per security_context. NEVER use a real-looking token. Add a one-sentence note that the token is passed via the `adbc.quack.token` kwarg and is never embedded in the URI.

    9. **`## Loading from environment variables`**:
       Explain the `QUACK_` prefix. Show a `.env` snippet:
       ```bash
       QUACK_HOST=quack.example.com
       QUACK_PORT=8080
       QUACK_TOKEN=your-token-here  # pragma: allowlist secret
       QUACK_TLS=true
       ```
       Then a Python snippet:
       ```python
       from adbc_poolhouse import QuackConfig, create_pool

       config = QuackConfig()  # picks up QUACK_HOST, QUACK_PORT, etc.
       pool = create_pool(config)
       ```

    10. **`## See also`** footer:
        - `[Configuration overview](configuration.md)`
        - `[Pool lifecycle](pool-lifecycle.md)`
        - `[QuackConfig API reference][adbc_poolhouse.QuackConfig]` (mkdocstrings cross-ref)

    **Style requirements (per docs-author skill + CLAUDE.md):**
    - Second-person ("you"), direct and practical tone
    - All code snippets use realistic placeholder values that would actually run if the user substitutes their own values (no `<HOST>` angle-bracket placeholders — use `quack.example.com`)
    - Cross-refs MUST use Markdown form `[Name][module.path]`, NEVER RST `:class:` / `:func:` roles
    - No promotional language ("powerful", "seamlessly", "robust"), no AI vocabulary ("delve", "leverage"), no vague attributions ("this allows you to"), max one em dash per paragraph
    - Apply the humanizer pass before completing — read the humanizer skill checklist and revise as needed

    **Security requirements (from security_context):**
    - All tokens in examples are placeholders (`YOUR-TOKEN-HERE`, `your-token-here`) — never real-looking strings
    - Each token line has `# pragma: allowlist secret` appended (defends against detect-secrets pre-commit hook)
    - No real hostnames; use `quack.example.com`
  </action>
  <verify>
    <automated>test -f docs/src/guides/quack.md && grep -q 'https://github.com/gizmodata/adbc-driver-quack' docs/src/guides/quack.md && grep -q 'pip install --pre adbc-poolhouse\[quack\]' docs/src/guides/quack.md && grep -q '\[QuackConfig\]\[adbc_poolhouse.QuackConfig\]' docs/src/guides/quack.md && ! grep -E ':(class|func|meth|mod|obj):\`' docs/src/guides/quack.md</automated>
  </verify>
  <acceptance_criteria>
    - `test -f docs/src/guides/quack.md`
    - `grep -q '^# Quack' docs/src/guides/quack.md`
    - `grep -q '!!! warning' docs/src/guides/quack.md` (alpha admonition present)
    - `grep -q 'https://github.com/gizmodata/adbc-driver-quack' docs/src/guides/quack.md` (QUACK-14 upstream link)
    - `grep -q 'pip install --pre adbc-poolhouse\[quack\]' docs/src/guides/quack.md` (--pre flag verbatim)
    - `grep -q 'quack://' docs/src/guides/quack.md` (URI mode example)
    - `grep -q 'host=' docs/src/guides/quack.md` (decomposed mode example)
    - `grep -q 'tls=True' docs/src/guides/quack.md` (TLS example)
    - `grep -q 'QUACK_HOST' docs/src/guides/quack.md` (env-var section)
    - `grep -q '## See also' docs/src/guides/quack.md`
    - `grep -q '\[QuackConfig\]\[adbc_poolhouse.QuackConfig\]' docs/src/guides/quack.md` (Markdown cross-ref)
    - NO RST role syntax: `! grep -E ':(class|func|meth|mod|obj):\`' docs/src/guides/quack.md`
    - NO promotional language: `! grep -iE '\b(powerful|seamlessly|robust|comprehensive|effortlessly|delve|leverage)\b' docs/src/guides/quack.md`
    - All token placeholders have allowlist pragma: `grep -c 'pragma: allowlist secret' docs/src/guides/quack.md` returns >= 2
  </acceptance_criteria>
  <done>
    Guide file exists, all required sections present, mkdocstrings cross-refs use Markdown form, no RST roles, no promotional/AI vocabulary, humanizer pass applied, security placeholders in place.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Update configuration.md and index.md and mkdocs.yml</name>
  <files>docs/src/guides/configuration.md, docs/src/index.md, mkdocs.yml</files>
  <read_first>
    - docs/src/guides/configuration.md (full file — note env_prefix table format at lines 11-23; identify whether Foundry vs PyPI separation exists, around line 73)
    - docs/src/index.md (full file — note PyPI drivers table at lines 22-29 and the PyPI-installed config listing at line 42)
    - mkdocs.yml (full file — note Warehouse Guides nav block at lines 99-111; check existing ordering to decide alphabetical vs append)
    - docs/src/guides/quack.md (created in Task 1 — verify the cross-ref target matches)
    - .claude/skills/adbc-poolhouse-docs-author/SKILL.md (humanizer pass for new prose, however small)
  </read_first>
  <action>
    Three small surgical edits:

    **A) `docs/src/guides/configuration.md`** (per QUACK-15):
    Add a new row to the env_prefix table (around lines 11-23). Match the EXACT column format of existing rows. The row content:
    ```
    | [`QuackConfig`][adbc_poolhouse.QuackConfig] | `QUACK_` |
    ```
    Insert position: alphabetical with existing entries (between PostgreSQL and Redshift, or wherever the existing table convention dictates). If the table is sorted alphabetically by config class, follow that. If it groups Foundry vs PyPI, place Quack in the PyPI group.

    **B) `docs/src/index.md`** (per QUACK-16):
    Two edits:
    1. Add a row to the PyPI drivers table (around lines 22-29). Match format of existing rows. Content:
       ```
       | Quack | `pip install --pre adbc-poolhouse[quack]` |
       ```
       The `--pre` MUST appear because the driver is alpha.
    2. Add `QuackConfig` to the alphabetical PyPI-installed config listing on line 42. Insert between `PostgreSQLConfig` and `SnowflakeConfig` (or matching the existing alphabetical convention; if the listing reads `BigQueryConfig, DuckDBConfig, FlightSQLConfig, PostgreSQLConfig, SnowflakeConfig, SQLiteConfig` the new sequence is `BigQueryConfig, DuckDBConfig, FlightSQLConfig, PostgreSQLConfig, QuackConfig, SnowflakeConfig, SQLiteConfig`).

    Do NOT add an example for Quack on index.md (deferred per CONTEXT.md — listing only).

    **C) `mkdocs.yml`** (per QUACK-17):
    Add a new nav entry under the Warehouse Guides section (lines 99-111). Content:
    ```yaml
        - Quack: guides/quack.md
    ```
    Insert position: alphabetical with siblings if the existing block is alphabetical, otherwise append at the end of the Warehouse Guides block (matching the convention used for the most recent additions — ClickHouse and MySQL). Match the existing indentation EXACTLY (likely 4 or 6 spaces; copy from the line above).

    **Humanizer pass:** The new prose surface in these three edits is minimal (table rows + nav entry). If you add any new prose paragraphs, apply the humanizer checklist. For pure table rows, no humanizer pass needed.
  </action>
  <verify>
    <automated>grep -q 'QUACK_' docs/src/guides/configuration.md && grep -q 'QuackConfig' docs/src/index.md && grep -q 'pip install --pre adbc-poolhouse\[quack\]' docs/src/index.md && grep -q 'guides/quack.md' mkdocs.yml</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'QUACK_' docs/src/guides/configuration.md`
    - `grep -q 'QuackConfig' docs/src/guides/configuration.md`
    - `grep -q 'QuackConfig' docs/src/index.md`
    - `grep -q 'pip install --pre adbc-poolhouse\[quack\]' docs/src/index.md`
    - `grep -q '| Quack |' docs/src/index.md`
    - `grep -q 'guides/quack.md' mkdocs.yml`
    - `grep -q 'Quack:' mkdocs.yml`
  </acceptance_criteria>
  <done>
    All three doc surfaces updated. Quack visible in configuration table, index PyPI table + listing, and mkdocs nav.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: mkdocs strict build + humanizer review</name>
  <files></files>
  <read_first>
    - .claude/skills/adbc-poolhouse-docs-author/SKILL.md (quality checklist — Args/Returns/Raises, Examples block, mkdocs strict, humanizer pass)
    - /Users/paul/.claude/skills/humanizer/SKILL.md (full checklist — for the final pass)
    - docs/src/guides/quack.md (created in Task 1)
  </read_first>
  <action>
    Two-step quality gate:

    **Step 1: mkdocs strict build (QUACK-18 first half).**
    Run `uv run mkdocs build --strict`. Strict mode fails on:
    - Broken cross-refs (e.g. `[QuackConfig][adbc_poolhouse.QuackConfig]` if the symbol is not exported)
    - Pages present in `docs/src/` but absent from nav
    - YAML errors in `mkdocs.yml`

    If the build fails, diagnose and fix:
    - Cross-ref miss → confirm `QuackConfig` is in `adbc_poolhouse.__all__` (verify Plan 01 Task 2 completed)
    - Nav warning → confirm `mkdocs.yml` entry matches the actual file path
    - Markdown rendering errors → inspect the failing block in `quack.md`

    Re-run until clean. The build MUST exit 0.

    **Step 2: Humanizer pass (QUACK-18 second half).**
    Read `/Users/paul/.claude/skills/humanizer/SKILL.md` in full. Apply the checklist to:
    - `docs/src/guides/quack.md` (all new prose)
    - Any new prose paragraphs in `configuration.md` or `index.md` (table rows alone don't need it)
    - The class docstring in `src/adbc_poolhouse/_quack_config.py` (also subject to the humanizer rules per docs-author skill)

    Targets to eliminate:
    - Promotional language: "powerful", "seamlessly", "robust", "comprehensive", "effortlessly"
    - AI vocabulary: "delve", "leverage", "streamline", "it's worth noting", "ensure that"
    - Vague attributions: "this allows you to", "this enables", "this ensures"
    - Superficial -ing openers: "By defining X, you can Y" → rewrite directly
    - Rule of three: listing things in threes for rhetorical effect
    - Em dash overuse: max one per paragraph

    Edit and re-run `uv run mkdocs build --strict` after any prose edits to confirm nothing broke.

    Document the humanizer findings (even if "nothing to change") in the plan SUMMARY.
  </action>
  <verify>
    <automated>uv run mkdocs build --strict 2>&1 | tail -10 && ! grep -iE '\b(powerful|seamlessly|robust|comprehensive|effortlessly|delve|leverage|streamline)\b' docs/src/guides/quack.md</automated>
  </verify>
  <acceptance_criteria>
    - `uv run mkdocs build --strict` exits 0
    - `! grep -iE '\b(powerful|seamlessly|robust|comprehensive|effortlessly|delve|leverage|streamline)\b' docs/src/guides/quack.md`
    - `! grep -iE 'it.{1,3}s worth noting|ensure that|this allows you to|this enables' docs/src/guides/quack.md`
    - Maximum one em dash per paragraph in `quack.md` (manual review; document in SUMMARY)
    - Class docstring in `src/adbc_poolhouse/_quack_config.py` reviewed against same humanizer rules
  </acceptance_criteria>
  <done>
    Strict build green. Humanizer pass applied with findings documented. Phase 21 docs quality gate satisfied.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Documentation prose → reader copy-paste | Example snippets may be copied verbatim by users; placeholder credentials must not look real |
| mkdocs build → published HTML | Strict mode is the only automated gate against broken cross-refs and missing nav entries |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-21-08 | Information Disclosure | Token placeholders in docs examples | mitigate | All token values in code examples are obvious placeholders (`YOUR-TOKEN-HERE`, `your-token-here`); each line has `# pragma: allowlist secret` to satisfy detect-secrets. Verified by acceptance criterion grep count >= 2. |
| T-21-09 | Information Disclosure | Hostname placeholders | mitigate | All hostnames use `quack.example.com` (reserved per RFC 2606); no real-looking infrastructure references. |
| T-21-10 | Tampering | Broken cross-refs producing rogue HTML | mitigate | mkdocs strict build catches broken `[Name][module.path]` cross-refs and missing nav entries. Acceptance criterion runs the strict build. RST `:class:` / `:func:` roles would render as plain text (not broken HTML) but produce ugly output; grep guards against accidental RST in Task 1. |
| T-21-11 | Repudiation | Outdated docs after driver upgrade | accept | The alpha admonition explicitly notes the version snapshot. Future driver releases (e.g. `0.1.0a7`) may invalidate the version reference; documented as known risk in 21-RESEARCH.md Risks section. Out of scope for this phase. |
</threat_model>

<verification>
- `test -f docs/src/guides/quack.md`
- `grep -q 'https://github.com/gizmodata/adbc-driver-quack' docs/src/guides/quack.md` (QUACK-14)
- `grep -q 'pip install --pre adbc-poolhouse\[quack\]' docs/src/guides/quack.md` (locked decision — alpha install)
- `grep -q '\[QuackConfig\]\[adbc_poolhouse.QuackConfig\]' docs/src/guides/quack.md` (Markdown cross-ref)
- `! grep -E ':(class|func|meth|mod|obj):\`' docs/src/guides/quack.md` (no RST roles)
- `grep -q 'QUACK_' docs/src/guides/configuration.md` (QUACK-15)
- `grep -q 'QuackConfig' docs/src/index.md` (QUACK-16)
- `grep -q 'guides/quack.md' mkdocs.yml` (QUACK-17)
- `uv run mkdocs build --strict` exits 0 (QUACK-18)
- `! grep -iE '\b(powerful|seamlessly|robust|comprehensive|effortlessly|delve|leverage|streamline)\b' docs/src/guides/quack.md` (humanizer)
</verification>

<success_criteria>
- QUACK-13: docs/src/guides/quack.md exists with all required sections — verified by grep matrix
- QUACK-14: Alpha warning admonition + upstream GitHub link present — verified by grep
- QUACK-15: configuration.md table row updated — verified by grep
- QUACK-16: index.md backend listing updated — verified by grep
- QUACK-17: mkdocs.yml nav entry added — verified by grep
- QUACK-18: mkdocs strict build passes; humanizer pass applied with documented findings — verified by build exit + humanizer grep
</success_criteria>

<output>
After completion, create `.planning/phases/21-quack-backend/21-03-SUMMARY.md` documenting:
- Files created/modified
- mkdocs strict build output (paste last 10 lines)
- Humanizer findings (specific phrases flagged and rewritten, or explicit "no changes needed" if clean on first pass)
- Final phase-completion checklist confirming all QUACK-01 through QUACK-18 are satisfied (cross-reference Plans 01, 02, 03 SUMMARYs)
</output>
