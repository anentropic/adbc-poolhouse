# Phase 33: Documentation - Research

**Researched:** 2026-07-04
**Domain:** Technical documentation (mkdocs + mkdocstrings) consolidation for the v1.5.0 async milestone
**Confidence:** HIGH

## Summary

Phase 33 is a **consolidation and verification** phase, not a from-scratch authoring phase. The
critical finding of this research is that the great majority of the DOCS-01..04 content **already
exists in the codebase**, because CLAUDE.md makes documentation a completion requirement of every
phase >= 7. Each of phases 29-32 shipped its own docstrings and guide prose as part of its own
completion:

- `docs/src/guides/async.md` already has full sections for Arrow streaming (committed `9223a31`,
  29-04), `adbc_ingest` with the mode table and the "`replace` **drops**" warning (`69aaf7c`, 30-02),
  and `fetch_df` / `fetch_polars` with the user-supplied / native-`ModuleNotFoundError` note
  (`8d968b5`, 31-02, plus a follow-up contradiction fix `f3e5ec9`).
- All four new `AsyncCursor` methods and `AsyncRecordBatchReader` already carry complete Google-style
  docstrings (Args/Returns/Raises + `Example:`).
- `docs/scripts/gen_ref_pages.py` already appends an explicit mkdocstrings reference block that renders
  `AsyncRecordBatchReader` and `AsyncCursor` (and `AsyncPool` / `AsyncConnection`).
- `.venv/bin/mkdocs build --strict` **currently passes** (only benign INFO relative-link notes and an
  injected third-party ad warning; no strict failures).

So the real Phase 33 work is: (1) an **audit** confirming DOCS-01..04 content is present and correct;
(2) fixing the small number of **stale / contradictory** statements that a milestone consolidation must
catch — most importantly the `index.md` line that still says "DataFrame fetches ... are not available
yet" when Phase 31 shipped them; (3) a **consolidated humanizer pass** over the async guide prose,
which was written piecemeal across four commits in three phases; and (4) re-confirming the strict build
gate stays green. Whether to also refresh the **changelog** (still 1.4.0-only) and **bump the version**
is an open scoping question for the planner.

**Primary recommendation:** Scope Phase 33 as *audit + reconcile + humanize*, not *author*. The single
highest-value correctness fix is the `index.md` "not available yet" contradiction (DOCS-03). Treat
`.venv/bin/mkdocs build --strict` as the hard completion gate and the humanizer pass over `async.md` as
the main prose deliverable.

## User Constraints

> No `33-CONTEXT.md` exists (no `/gsd-discuss-phase` was run for this phase). Constraints below are
> derived from the binding project gate in CLAUDE.md and the DOCS-01..04 requirement text. The planner
> must treat these with the same authority as locked decisions.

### Locked Decisions (from CLAUDE.md Documentation Quality Gate + REQUIREMENTS.md)
- Every plan in this phase MUST include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in its
  `<execution_context>` (CLAUDE.md, phases >= 7).
- Completion gate (all must hold before the phase is complete):
  - All new public symbols have Google-style docstrings (Args/Returns/Raises).
  - Key entry points have an `Example` block.
  - Any new consumer-facing behaviour is reflected in the relevant guide.
  - `uv run mkdocs build --strict` passes (under sandbox use `.venv/bin/mkdocs build --strict`).
  - Humanizer pass applied to all new or substantially rewritten prose.
- DOCS-02: the guide **and** API reference must document `adbc_ingest` with the `mode` Literal table
  and an explicit "`replace` drops the table" warning.
- DOCS-03: `fetch_df` / `fetch_polars` documented as user-supplied deps surfacing a native
  `ModuleNotFoundError` (no poolhouse pre-check or wrapping).

### Claude's Discretion
- Exact wording of the humanizer-pass edits, section ordering within `async.md`, and whether to add
  cross-links.
- Whether to fold the changelog refresh and version bump into this phase (see Open Questions).

### Deferred Ideas (OUT OF SCOPE)
- Documenting async metadata (`adbc_get_objects`, etc.) and async prepared statements — these are
  explicitly *not implemented yet* and the guide already lists them as unavailable. Do not document
  them as available.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOCS-01 | Async guide documents Arrow streaming (`fetch_record_batch` → `async for` → close), reader-lifetime contract, honest concurrency framing | Already present: `async.md` lines 136-222 ("Streaming a result set batch by batch", "Always close the reader", "Reading after the reader is gone", "What streaming does and does not parallelize"). Audit for accuracy + humanize. |
| DOCS-02 | Guide + API reference document `adbc_ingest` with `mode` Literal table and "`replace` drops the table" warning | Guide: `async.md` lines 224-278 (mode table at 251-256, explicit "`replace` ... **drops**" at 258-260). Reference: `_cursor.py` docstring lines 512-533 render the same warning via mkdocstrings. Audit + humanize. |
| DOCS-03 | `fetch_df` / `fetch_polars` documented as user-supplied; missing dep → native `ModuleNotFoundError` | Guide: `async.md` lines 280-306 (user-supplied note + `ModuleNotFoundError` at 302-306). Docstrings: `_cursor.py` 385-402, 437-454. **Gap:** `index.md` line 71 still says DataFrame fetches "are not available yet" — a factual contradiction to fix. |
| DOCS-04 | API reference renders `AsyncRecordBatchReader` + four new `AsyncCursor` methods with Google-style docstrings (Args/Returns/Raises + Example); `mkdocs build --strict` passes; humanizer pass applied | Docstrings complete (see Symbol Inventory). Reference block present (`gen_ref_pages.py`). Strict build passes today. Remaining: humanizer pass + keep the gate green. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Narrative "how do I use streaming/ingest/DataFrames" | How-to guide (`docs/src/guides/async.md`) | Quickstart (`index.md`) async section | Goal-oriented task docs live in guides; index only teases + links |
| Per-symbol API contract (signatures, Args/Returns/Raises) | Docstrings in `src/adbc_poolhouse/_async/*.py` | — | mkdocstrings renders these; SKILL forbids hand-writing `reference/` pages |
| API reference rendering / nav wiring | `docs/scripts/gen_ref_pages.py` (gen-files + literate-nav) | `mkdocs.yml` mkdocstrings options | Reference pages are auto-generated at build time, not committed source |
| Build correctness gate | `mkdocs build --strict` | — | Strict mode turns broken refs / missing nav into failures |
| Milestone history | `docs/src/changelog.md` | `pyproject.toml` version | Consolidation point for what shipped in the milestone |

## Symbol Inventory (exact targets for the planner)

All symbols live under the private `_async` package and are intentionally NOT in `__all__` (D-28-02);
they are returned objects, documented at their real module paths by the explicit reference block.

### `AsyncRecordBatchReader` (Phase 29)
- **File:** `src/adbc_poolhouse/_async/_reader.py`
- **Class + docstring:** line 124 (class), 125-160 (class docstring — complete, with `Example:` at
  147-159). `__init__` docstring 169-187.
- **Public members rendered:** `schema` property (line 199-209), `__aiter__` (211-219), `__anext__`
  (221-260), `close` (262-...). Note dunders `__aiter__` / `__anext__` render because the reference
  block uses a per-block `filters: ["!^__"]` override — verify they still show after any edits.
- **Reader-lifetime contract (for DOCS-01 prose accuracy):** live reader locks its owning connection
  for its WHOLE lifetime; lock cleared by `close()`, NOT at drain (D-29-11); read-after-close or
  read-after-checkin surfaces native `pyarrow.lib.ArrowInvalid` (T-29-01), never a poolhouse type,
  never a segfault. `async with` is canonical; the `__del__` finalizer only warns (`ResourceWarning`).

### The four new `AsyncCursor` methods — VERIFIED
All in `src/adbc_poolhouse/_async/_cursor.py`. Confirmed exactly four:

| Method | Signature (line) | Returns | Key Raises | Docstring |
|--------|------------------|---------|-----------|-----------|
| `fetch_record_batch` | `async def fetch_record_batch(self) -> AsyncRecordBatchReader` (566) | `AsyncRecordBatchReader` (live stream, locks connection) | `ConnectionBusyError` | Complete + `Example:` (599-605) |
| `adbc_ingest` | `async def adbc_ingest(self, table_name, data, *, mode: Literal["create","append","replace","create_append"]="create", catalog_name=None, db_schema_name=None, temporary=False) -> int` (479-488) | `int` row count, `-1` when driver can't count | `ConnectionBusyError` | Complete + `Example:` (539-548); mode table in Args (518-523) with "`replace` **drops**" |
| `fetch_df` | `async def fetch_df(self) -> pandas.DataFrame` (376) | `pandas.DataFrame` (self-owning) | `ConnectionBusyError`, `ModuleNotFoundError` | Complete + `Example:` (404-410) |
| `fetch_polars` | `async def fetch_polars(self) -> polars.DataFrame` (427) | `polars.DataFrame` (self-owning) | `ConnectionBusyError`, `ModuleNotFoundError` | Complete + `Example:` (456-462) |

**Conclusion for DOCS-04:** the docstring authoring is effectively **already done** — this phase is
"wire into reference + verify render + humanize", NOT "write docstrings". The planner should frame
DOCS-04 tasks as *audit the rendered reference output* (build the site, confirm all four methods +
reader appear with Args/Returns/Raises/Example), not as new docstring work.

## Docs Structure & Mechanics

- **`docs_dir: docs/src`.** Three doc types (from SKILL): Quickstart (`index.md`), How-to guides
  (`docs/src/guides/`), API Reference (`docs/src/reference/` — **auto-generated, never hand-write**).
- **Reference generation:** `docs/scripts/gen_ref_pages.py` runs under the `gen-files` plugin. It walks
  `src/**/*.py`, skips any path part starting with `_`, and writes `::: <ident>` blocks. Because the
  async classes live under `_async`, they are skipped by the loop and instead injected via the hard-coded
  `_ASYNC_REFERENCE_BLOCK` appended to the top-level `adbc_poolhouse.md` package page. That block carries
  per-block `filters: ["!^__"]` (REPLACES the global `["!^_"]`, does not merge) so the single-underscore
  `_async._*` paths render while dunders are hidden — except the explicitly rendered `__anext__` etc.
- **Nav:** guides are listed explicitly in `mkdocs.yml`; `reference/` uses `literate-nav` via an
  auto-generated `reference/SUMMARY.md`. Adding a symbol requires no nav edit — it flows from the source.
- **mkdocstrings options (`mkdocs.yml`):** `docstring_style: google`, `docstring_section_style: table`,
  `merge_init_into_class: true`, `separate_signature: true`, `show_signature_annotations: true`,
  `members_order: source`, global `filters: ["!^_"]`. The `table` section style means Args/Returns/Raises
  render as tables — keep docstring section formatting parser-friendly.
- **Current `async.md` coverage (already written):** intro/mirroring, experimental warning (lists
  streaming/ingest/DataFrame as available; metadata + prepared statements as not), install, first query,
  "What actually runs in parallel" (concurrency benchmarks), streaming (3 subsections), bulk-loading (mode
  table + cancelled-ingest), DataFrame fetch, one-connection-per-task, shielded cleanup, cancellation, See
  also. It is comprehensive; the risk is tonal drift across the four authoring commits, not missing content.

## The mkdocs Strict Build Gate

- **Command (sandbox-safe):** `.venv/bin/mkdocs build --strict` (avoids the `uv run` sandbox prompt per
  MEMORY [[uv-sandbox-workarounds]]). CLAUDE.md/SKILL reference `uv run mkdocs build --strict`; both are
  equivalent, use the `.venv/bin` form under the command sandbox.
- **Current status: PASSES.** Verified this session. Output contains only:
  - INFO: "Doc file 'index.md' contains an unrecognized relative link 'reference/'" (and same for
    `async.md`, `configuration.md`) — benign; these are literate-nav/section-index directory links, not
    strict failures.
  - A large injected third-party "switch to ProperDocs" advertisement warning emitted by a dependency at
    build time. It is noise, not a build failure — the build still reports success. Do not chase it.
    (Can be silenced with `DISABLE_MKDOCS_2_WARNING=true` if it clutters CI logs.)
- **What `--strict` actually catches** (the failure modes to guard against when editing): unresolved
  cross-reference links (`[text][adbc_poolhouse.symbol]` that don't resolve), missing/renamed
  mkdocstrings identifiers in `:::` blocks, broken internal Markdown links, and nav entries pointing at
  files that don't exist. Any edit that renames a symbol, moves a section anchor referenced by a
  `[..](#anchor)` link, or breaks a cross-ref will turn `--strict` red.

## Honest Concurrency Framing (technically-correct source of truth)

The guide's framing is already accurate and benchmark-backed; preserve these facts, do not soften them:

- Each blocking ADBC call is offloaded to one anyio worker thread. ADBC releases the GIL during its C
  calls, so `execute` across separate connections overlaps well (benchmarked ~2.77x / ~69% at 4-way on
  DuckDB during v1.4.0).
- **Materialization re-acquires the GIL.** `fetch_arrow_table` / `fetch_df` / `fetch_polars` and each
  streaming batch pull build Python/pyarrow objects, which partially serializes (benchmarked ~1.67x /
  ~42% at 4-way fetch). Streaming trades peak memory for a steady per-batch cost; it does NOT turn one
  reader into a parallel pipeline — batches from one reader arrive one at a time, in order. Real overlap
  = separate readers on separate connections.
- DuckDB benchmarks are in-process (no network wait) so they isolate GIL behaviour; a networked backend
  has genuine I/O to overlap.
- Concurrency is capped by a per-pool `anyio.CapacityLimiter` sized `pool_size + max_overflow`.
- Cancellation: a cancelled call fires `cursor.adbc_cancel()` once from the loop thread, then invalidates
  the poisoned connection (shielded) so `pool.checkedout()` stays correct; identical under asyncio/trio.
  A cancelled ingest recovers the *connection*, not the *table* (rows may be half-written; no rollback).

## Content-Specific Facts the Guide Must State (already present — verify unchanged)

- `adbc_ingest` `mode` Literal values: `create` (default; fails if exists), `append`, `create_append`,
  `replace`. **`replace` DROPS the existing table** and recreates it — not a row-level upsert. This must
  appear as both the guide table (`async.md` 251-260) and the docstring Args entry (`_cursor.py` 518-523).
- pandas/polars are user-supplied optional deps (not poolhouse dependencies). poolhouse never imports
  them; the driver imports them in the worker, so a missing install raises the native
  `ModuleNotFoundError` unchanged — no `find_spec` pre-check, no wrapping (DF-03).
- Row count from `adbc_ingest` is the driver's value, `-1` when it cannot count.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| API reference pages for the async classes | Hand-written `docs/src/reference/*.md` | The existing `_ASYNC_REFERENCE_BLOCK` in `gen_ref_pages.py` | SKILL forbids hand-writing reference; the generator already renders all four symbols |
| Re-writing docstrings | New Google-style docstrings from scratch | The already-complete docstrings in `_cursor.py` / `_reader.py` | They already meet the gate (Args/Returns/Raises + Example); rewriting risks regressions |
| "Is pandas installed?" doc caveat logic | A doc claim that poolhouse checks/handles the missing dep | Document the native `ModuleNotFoundError` pass-through | Matches actual behaviour (DF-03); a wrapping claim would be false |

## Common Pitfalls

### Pitfall 1: Treating this as an authoring phase and rewriting existing prose
**What goes wrong:** Re-authoring `async.md` sections that already exist produces churn, risks a
`--strict` break (moved anchors, broken cross-refs), and re-triggers a full humanizer pass over prose
that was already signed off.
**How to avoid:** Audit first. Diff intent against DOCS-01..04, edit only what is stale/contradictory or
tonally inconsistent. The one clearly-required content change is the `index.md` contradiction.

### Pitfall 2: Leaving the `index.md` "not available yet" contradiction
**What goes wrong:** `index.md` line 71 says "several features (DataFrame fetches, async metadata, and
prepared statements) are not available yet." DataFrame fetches shipped in Phase 31. This directly
contradicts `async.md`'s experimental block (which lists DataFrame convenience as available) and DOCS-03.
A milestone consolidation that ships this is factually wrong on the front page.
**How to avoid:** Update `index.md` to list only the genuinely-unavailable features (async metadata,
async prepared statements). This is a consumer-facing behaviour reflection → also a humanizer target.
**Warning signs:** grep `index.md` for "not available" / "DataFrame".

### Pitfall 3: `--strict` breakage from moved section anchors
**What goes wrong:** `async.md` and the See-also block use `[text][adbc_poolhouse...]` cross-refs and
`(#what-actually-runs-in-parallel)` intra-page anchors. Renaming a heading breaks the anchor and turns
`--strict` red.
**How to avoid:** If you rename a heading referenced by an anchor link, update the link in the same edit.
Run `.venv/bin/mkdocs build --strict` after every prose edit, not just at the end.

### Pitfall 4: Em-dash overuse vs. the source's `---` convention
**What goes wrong:** The docstrings use ` --- ` (triple-hyphen em-dashes) heavily (~20 in `_cursor.py`,
~16 in `_reader.py`), and the guide uses em-dashes freely. The humanizer rule caps em-dashes at one per
paragraph.
**How to avoid:** The humanizer pass targets *guide prose* (new/rewritten). Docstrings were signed off in
prior phases — do not mass-rewrite them for em-dashes unless a docstring is substantially rewritten this
phase. Apply the em-dash cap to any prose you actually touch; don't open a docstring-wide sweep.

### Pitfall 5: Assuming a docs example-execution test harness exists
**What goes wrong:** SKILL.md says `index.md` is "validated in CI by running against a real DuckDB
connection", but there is **no docs-example test** in `tests/` and no `markdown-exec` / `mktestdocs` /
`pytest-examples` dependency in `pyproject.toml`. The only automated docs validation is
`mkdocs build --strict`.
**How to avoid:** Do not plan a task around an example-runner that doesn't exist. If example correctness
matters, either add such a harness explicitly (scope creep — flag it) or manually verify snippets. Treat
the strict build as the gate.

## State of the Art / Staleness Found

| Stale item | Current reality | Location | Action |
|------------|-----------------|----------|--------|
| "DataFrame fetches ... are not available yet" | Shipped in Phase 31 (`fetch_df`/`fetch_polars`) | `docs/src/index.md` line 71 | **Fix** — required by DOCS-03 (consumer-facing behaviour reflection) |
| Changelog stops at `[1.4.0]`; `[Unreleased]` empty | Streaming (29), ingest (30), DataFrame (31), P2 hardening (32) all shipped | `docs/src/changelog.md` | Recommend refresh (see Open Questions) |
| `version = "1.4.0"` | Milestone is v1.5.0 (branch `gsd/v1.5.0-async-cursor-completion`) | `pyproject.toml` line 3 | Version bump — flag; may belong to a release step, not docs |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Changelog refresh + version bump are candidate scope for this docs phase (not a separate release phase) | Open Questions | Low — planner decides; if excluded, milestone ships with a stale changelog/version |
| A2 | The injected "ProperDocs" build warning is cosmetic and not a `--strict` failure | Strict Build Gate | Low — verified build reports success this session; if CI treats stderr as failure, set `DISABLE_MKDOCS_2_WARNING=true` |
| A3 | No `33-CONTEXT.md` means no additional user-locked constraints beyond CLAUDE.md/REQUIREMENTS | User Constraints | Low — if a CONTEXT is added later, re-read it before planning |

## Open Questions (RESOLVED)

1. **Is the changelog + version bump in scope for Phase 33?**
   - What we know: DOCS-01..04 do not mention the changelog; the changelog is stale at 1.4.0 and
     `pyproject.toml` is still `1.4.0`; the branch is `v1.5.0`.
   - What's unclear: Whether this milestone has a separate release/versioning phase.
   - Recommendation: Include a changelog `[1.5.0]` (or `[Unreleased]`) entry summarizing STREAM/INGEST/DF
     as a low-cost consolidation win; leave the actual `pyproject` version bump + tag to the release step
     unless the planner confirms Phase 33 owns the release. Flag explicitly in the plan.
   - **RESOLVED (2026-07-04, user decision): OUT OF SCOPE.** Phase 33 is docs-only (DOCS-01..04). No
     changelog entry and no `pyproject.toml` version bump — both deferred to a separate release step.

2. **Does the `index.md` async code example need updating beyond the "not available" line?**
   - What we know: The example uses `fetch_arrow_table`, which is fine. Only the availability sentence is
     wrong.
   - Recommendation: Minimal edit — correct the availability list; optionally add a one-line pointer to
     the new streaming/ingest/DataFrame sections. Keep the quickstart short.
   - **RESOLVED (planned): minimal edit only.** Plan 33-01 Task 1 scopes the change to correcting the
     availability sentence; the code example is left unchanged.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| mkdocs (`.venv/bin/mkdocs`) | strict build gate | ✓ | mkdocs>=1.6 (material 9.5-9.8) | — |
| mkdocstrings[python] | reference rendering | ✓ | >=0.26 | — |
| mkdocs-gen-files / literate-nav / section-index | reference nav | ✓ | pinned in pyproject | — |
| humanizer skill | prose pass | ✓ | `/Users/paul/.claude/skills/humanizer/SKILL.md` (present) | — |
| docs-author skill | required in execution_context | ✓ | `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` | — |

**Missing dependencies with no fallback:** None.
**No new packages are installed by this phase** — the Package Legitimacy Audit and Runtime State
Inventory sections are omitted (docs-only, no dependency changes, no rename/refactor).

## Validation Architecture

> `workflow.nyquist_validation: true`. For a docs phase, the automated validation surface is the strict
> build; there is no unit-test harness for prose.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | mkdocs strict build (no docs-example test harness exists) |
| Config file | `mkdocs.yml` + `docs/scripts/gen_ref_pages.py` |
| Quick run command | `.venv/bin/mkdocs build --strict` |
| Full suite command | `.venv/bin/mkdocs build --strict` (single gate) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOCS-01 | Streaming guide + reader render correctly | build/render | `.venv/bin/mkdocs build --strict` | ✅ |
| DOCS-02 | Ingest mode table + reference render | build/render | `.venv/bin/mkdocs build --strict` | ✅ |
| DOCS-03 | DataFrame docs + no `index.md` contradiction | build + manual grep | `.venv/bin/mkdocs build --strict`; `grep -n "not available" docs/src/index.md` | ✅ (grep manual) |
| DOCS-04 | Reference renders all 4 methods + reader; humanizer applied | build/render + manual review | `.venv/bin/mkdocs build --strict`; visual check of generated `reference/adbc_poolhouse.md` | ✅ |

### Sampling Rate
- **Per prose edit:** `.venv/bin/mkdocs build --strict` (catches broken refs immediately).
- **Phase gate:** strict build green + humanizer checklist complete + `index.md` contradiction gone.

### Wave 0 Gaps
- None — the strict build harness exists and passes today. No new test files required. (Optional, out of
  scope: adding a docs-example execution test — flag as scope creep if considered.)

## Sources

### Primary (HIGH confidence — verified this session in-repo)
- `docs/src/guides/async.md` (full read) — existing DOCS-01/02/03 prose
- `src/adbc_poolhouse/_async/_cursor.py` lines 376-645 — four method signatures + complete docstrings
- `src/adbc_poolhouse/_async/_reader.py` lines 124-283 — `AsyncRecordBatchReader` docstrings
- `docs/scripts/gen_ref_pages.py` — reference generation + `_ASYNC_REFERENCE_BLOCK`
- `mkdocs.yml` — nav, mkdocstrings options
- `.venv/bin/mkdocs build --strict` — verified PASS this session
- `.planning/REQUIREMENTS.md` — DOCS-01..04 + STREAM/INGEST/DF completion status
- `docs/src/index.md` (lines 60-96), `docs/src/changelog.md`, `pyproject.toml` — staleness findings
- `git log` on `async.md` and the async source files — provenance of existing docs

### Secondary / Tertiary
- None required — all findings verified directly against the repository.

## Metadata

**Confidence breakdown:**
- Symbol inventory / docstring state: HIGH — read directly from source with line numbers.
- Docs structure / reference mechanics: HIGH — read `gen_ref_pages.py` + `mkdocs.yml`; build verified.
- Strict build gate status: HIGH — executed `.venv/bin/mkdocs build --strict`, confirmed pass.
- Scope (changelog/version bump): MEDIUM — inferred; flagged as Open Question for the planner.

**Research date:** 2026-07-04
**Valid until:** 2026-08-03 (stable docs tooling; re-verify the strict build if any async source symbol
is renamed before planning).
