# Phase 28: Documentation - Context

**Gathered:** 2026-06-29 (assumptions session, `/gsd-discuss-phase 28 --assumptions`)
**Status:** Ready for planning — three load-bearing decisions locked below
**Source:** Assumptions analysis validated by user; no full discuss-phase run (user chose "just plan it")

<domain>
## Phase Boundary

Phase 28 is the **documentation consolidation + closeout** for the v1.4.0 async milestone. It is
**mostly gap-filling, not greenfield** — the per-phase docs gates in Phases 24/25 already shipped:

- `docs/src/guides/async.md` (203 lines): first-query walkthrough, "What actually runs in parallel"
  (the honest I/O-vs-materialization section), the aliasing antipattern, shielded cleanup, cancellation.
- `docs/src/index.md`: an Async section listing all three entry points + the `[async]` extra, linking
  the guide.
- The three entry-point functions (`create_async_pool`, `managed_async_pool`, `close_async_pool`) are in
  `__all__` + the `TYPE_CHECKING` block, so griffe/mkdocstrings already render them.

**In scope (the actual work):**
1. Add the experimental/incomplete caveat at every async entry point (D-28-01).
2. Make `AsyncPool`/`AsyncConnection`/`AsyncCursor` render in the API reference (D-28-02).
3. Fill the `configuration.md` async gap — it currently has ZERO async mentions (DOCS-03).
4. Add a v1.4.0 changelog entry (currently just `## [Unreleased]`), marking async experimental.
5. Audit `async.md`'s concurrency claims against `22-GO-NO-GO.md` (D-28-03); tighten any over-claims.
6. Docs quality gate: `mkdocs build --strict` + humanizer pass on new/rewritten prose (DOCS-04).

**Out of scope (deferred per REQUIREMENTS.md):** documenting streaming/`fetch_record_batch`,
`adbc_ingest`, `fetch_df`/`fetch_polars`, async metadata, async prepared statements as *available* —
these are v1.4.x/v2 deferrals and are exactly what makes the surface "incomplete".
</domain>

<decisions>
## Phase 28 Design Decisions (locked 2026-06-29)

### D-28-01 — Async support is documented as EXPERIMENTAL and INCOMPLETE at every entry point
**Decision:** Wherever the async feature is introduced, lead with an explicit experimental + incomplete
caveat — not a confident "here is the async API" framing. (Consistent with the code review labelling it
"PR #32, v1.4.0 experimental async API".)

Placement:
- **`async.md`** — a `!!! warning "Experimental"` admonition at the top, before "Install". States the
  API may change AND names what is **not** there yet (streaming/`fetch_record_batch`, `adbc_ingest`,
  `fetch_df`/`fetch_polars`, async metadata, async prepared statements), so "incomplete" is concrete.
- **`index.md`** — one line in the Async section flagging experimental status + linking the guide for the
  full caveat.
- **Changelog** — the v1.4.0 entry marks async as experimental.
- **Docstrings / API reference** — kept factual; no per-symbol caveat noise. The guide + index carry the
  status.

**Why:** the deferred-feature list is long and the API may still shift; an honest experimental banner
sets correct expectations and is the whole reason D-28-02 keeps the surface from hardening.

### D-28-02 — Async classes documented at their real `_async` path; NOT promoted to public exports
**Decision:** Satisfy DOCS-02 (document `AsyncPool`/`AsyncConnection`/`AsyncCursor`) by adding explicit
mkdocstrings blocks at their real module paths (e.g. `::: adbc_poolhouse._async.pool.AsyncPool`) on the
reference page — **option (a)**. Do **not** add them to `__all__` or the lazy PEP-562 exports.

**Why (a) over promoting to public exports (b) or a dedicated page (c)):**
- Users never *construct* these classes — they are returned objects from the entry-point functions. They
  do not belong in the constructible public API.
- The surface is experimental (D-28-01); promoting the classes to `__all__` would harden them into the
  public API contract prematurely.
- The Google-style docstrings already exist on the classes (written during Phase 24/25 gates), so the
  mkdocstrings blocks render real content immediately.
- A single recursive `::: adbc_poolhouse` will NOT pick up private-path classes — hence the explicit
  per-class blocks are required regardless.

**Planner note:** verify the chosen mkdocstrings paths actually resolve and render under
`mkdocs build --strict` (PEP-562 lazy `__getattr__` + private subpackage is the known risk). If griffe
cannot resolve `_async.*` paths cleanly, fall back to a dedicated async reference page that imports the
classes for documentation only — but try (a) first.

### D-28-03 — DOCS-01 honest-concurrency claims are sourced from the Phase 22 go/no-go, not memory
**Decision:** The "I/O-bound wins vs materialization-bound limits" wording in `async.md` must be
reconciled against the measured results in `.planning/phases/22-feasibility-spike/22-GO-NO-GO.md` — the
canonical source of what the async layer may honestly claim and what it must disclaim. Do not restate
concurrency wins from memory; quote/derive from the go/no-go contract.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Honest-concurrency source of truth
- `.planning/phases/22-feasibility-spike/22-GO-NO-GO.md` — measured GIL-release wins/disclaimers; the
  authority for DOCS-01's I/O-vs-materialization framing.

### Existing docs to extend (not rewrite)
- `docs/src/guides/async.md` — the async guide (add experimental admonition; audit concurrency claims).
- `docs/src/index.md` — Async section (add experimental flag line).
- `docs/src/guides/configuration.md` — **gap**: add the `[async]` extra + async entry points (DOCS-03).
- `docs/src/changelog.md` — add the v1.4.0 entry (currently bare `## [Unreleased]`).
- `docs/src/reference/adbc_poolhouse.md` — single `::: adbc_poolhouse`; add explicit async-class blocks.
- `mkdocs.yml` — nav already lists `guides/async.md`.

### Source under documentation
- `src/adbc_poolhouse/_async/` — `AsyncPool`/`AsyncConnection`/`AsyncCursor` (docstrings already present).
- `src/adbc_poolhouse/__init__.py` — `__all__`, the `TYPE_CHECKING` block, and the PEP-562 lazy
  `__getattr__` for the three entry points. Do NOT add the classes here (D-28-02).

### Process gates
- `CLAUDE.md` — Documentation Quality Gate (phases ≥7): docstrings, examples, `mkdocs build --strict`,
  humanizer pass are completion requirements.
- `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — project voice, Google-style docstrings
  (Markdown not RST, `Example:` singular for admonitions), humanizer pass. Include in execution_context.
</canonical_refs>

<specifics>
## Specific Ideas

- Build check under sandbox: prefer `.venv/bin/mkdocs build --strict` over `uv run mkdocs` (memory:
  uv-sandbox-workarounds).
- Docstring style is already established project-wide (Google-style, Markdown, `Example:` singular) — the
  reference work is wiring mkdocstrings, not rewriting docstrings.
- The "incomplete" feature list to name in the caveat is the REQUIREMENTS.md "Future Requirements
  (deferred)" block: Arrow streaming, async bulk write (`adbc_ingest`), DataFrame convenience
  (`fetch_df`/`fetch_polars`), async ADBC metadata, async prepared statements.
</specifics>

<deferred>
## Deferred Ideas

- Documenting any deferred async feature (streaming, ingest, dataframe, metadata, prepared statements) as
  available — these ship in v1.4.x/v2; Phase 28 only *names them as not-yet-present* in the caveat.
- A dedicated trio-vs-asyncio comparison section or sync→async migration guide — not required by
  DOCS-01..04; only add if planning surfaces a clear need.
</deferred>

---

*Phase: 28-documentation*
*Context gathered: 2026-06-29 via /gsd-discuss-phase 28 --assumptions (validated, planned directly)*
