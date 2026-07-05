---
phase: 33-documentation
plan: 01
subsystem: docs
tags: [mkdocs, mkdocstrings, async, documentation, humanizer]

# Dependency graph
requires:
  - phase: 29-arrow-streaming
    provides: AsyncRecordBatchReader + the streaming guide prose audited here
  - phase: 30-async-bulk-write
    provides: adbc_ingest mode table + replace-drops warning audited here
  - phase: 31-dataframe-convenience
    provides: fetch_df / fetch_polars (shipped) — the fact that made the index.md claim stale
provides:
  - Corrected index.md async availability statement (DataFrame fetches no longer listed as unavailable)
  - Verified-accurate async.md streaming / ingest / DataFrame prose (audit confirmed against 33-RESEARCH)
  - Humanized index.md availability paragraph aligned with the async.md experimental block
affects: [33-02 API-reference render audit, v1.5.0 release notes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Audit-not-author: verify existing prose against a research source of truth, edit only stale/contradictory/tonally-inconsistent text (Pitfall 1)"

key-files:
  created: []
  modified:
    - docs/src/index.md

key-decisions:
  - "async.md required no content edit — the three DOCS sections were already accurate and consistent, so re-authoring was skipped (Pitfall 1)"
  - "DOCS-02 reference half and DOCS-04 belong to plan 33-02; only DOCS-01 and DOCS-03 are marked fully complete here"

patterns-established:
  - "Front-page availability wording mirrors the guide's authoritative experimental block rather than maintaining a second independent list"

requirements-completed: [DOCS-01, DOCS-03]

# Metrics
duration: ~12min
completed: 2026-07-04
---

# Phase 33 Plan 01: Async prose reconcile + humanize Summary

**Fixed the index.md front-page contradiction that still called DataFrame fetches unavailable, audited the async guide's streaming/ingest/DataFrame prose against the research as already-accurate, and humanized the corrected availability paragraph — strict build green throughout.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-04T~01:34:00Z
- **Completed:** 2026-07-04T01:46:00Z
- **Tasks:** 3 (2 producing commits, 1 audit-only)
- **Files modified:** 1 source file (`docs/src/index.md`) + 3 planning files

## Accomplishments
- Removed the `index.md` line-71 contradiction: DataFrame fetches (shipped Phase 31) are no longer listed as unavailable; only async ADBC metadata and async prepared statements are named as not-yet-shipped, matching `async.md` lines 18-32. The literal string `not available` no longer appears in `index.md`.
- Audited the three `async.md` DOCS sections against `33-RESEARCH.md` and confirmed every required fact is present and unsoftened: the four-mode `adbc_ingest` table, the "`replace` **drops** the table" warning, the native-`ModuleNotFoundError` DataFrame note, and the reader-lifetime / `pyarrow.lib.ArrowInvalid` streaming contract with honest concurrency framing.
- Humanized the corrected `index.md` availability paragraph: dropped the vague "several features (...)" quantifier and the rule-of-three, naming the two deferred surfaces directly.
- `.venv/bin/mkdocs build --strict` exits 0 after every prose edit (baseline was green; stayed green).

## Task Commits

1. **Task 1: Fix the index.md DataFrame-availability contradiction (DOCS-03)** — `60a0569` (docs)
2. **Task 2: Audit + reconcile async.md streaming / ingest / DataFrame prose (DOCS-01/02/03)** — no commit (audit-only; prose already accurate, see Deviations)
3. **Task 3: Humanizer pass over the index.md availability paragraph (DOCS-04 humanizer clause)** — `7a43e2c` (docs)

**Plan metadata:** committed with this SUMMARY + STATE.md + ROADMAP.md + REQUIREMENTS.md

## Files Created/Modified
- `docs/src/index.md` — corrected + humanized the async availability paragraph (line 71); code example and all other sections unchanged
- `.planning/ROADMAP.md` — marked 33-01 complete, phase 33 progress 1/2 In progress
- `.planning/REQUIREMENTS.md` — DOCS-01 and DOCS-03 marked complete; DOCS-02 noted guide-half done / reference-half pending in 33-02
- `.planning/STATE.md` — position, counters, and session continuity updated

## Decisions Made
- **async.md needed no content edit.** The audit (Task 2) confirmed the streaming, ingest, and DataFrame sections already match the research's technically-correct source of truth, the em-dashes were already within the one-per-paragraph cap, and grep found no promotional/AI-vocabulary/copula-avoidance/negative-parallelism tells. Re-authoring correct, previously-signed-off prose would be churn and risk a `--strict` break via moved anchors (Pitfall 1 / Pitfall 3). This is the plan's explicitly-blessed "audit finds prose already correct" outcome.
- **Requirement accounting split by plan.** The plan frontmatter lists DOCS-01..04, but ROADMAP assigns DOCS-04 and the DOCS-02 API-reference half to plan 33-02. This plan delivers the guide/front-page side only, so only DOCS-01 (streaming guide, no reference half) and DOCS-03 (DataFrame guide note) are marked fully complete. DOCS-02 is recorded as guide-half-complete; DOCS-04 stays pending for 33-02.

## Deviations from Plan

### Auto-fixed Issues
None — no bugs, missing functionality, or blocking issues were encountered.

### Scope note (not a deviation from correctness, documented for traceability)
Task 2 was scoped by the plan as an audit that "may be limited to humanizer touch-ups" and explicitly allows a no-edit outcome. The audit found the three async.md DOCS sections already accurate and consistent, so Task 2 produced no file change and therefore no commit. All Task 2 verification assertions passed (`replace`, `drop`, `ModuleNotFoundError`, `ArrowInvalid` present; strict build exit 0).

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** Plan executed as written; the guide audit landed on the plan's anticipated no-edit path.

## Issues Encountered
None. The pre-commit hooks (trailing-whitespace, end-of-file, blacken-docs, detect-secrets) passed on both commits.

## Known Stubs
None — no placeholder values, TODOs, or unwired data introduced (docs-only edit).

## Threat Flags
None — no new endpoints, auth paths, file access, or schema surface. The T-33-01 destructive-`replace` warning and T-33-02 false-availability mitigations from the plan's threat register are both satisfied: the `replace`-drops warning is intact and unsoftened, and the index.md false-availability claim is removed.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Guide-side documentation (DOCS-01/02/03) is reconciled, humanized, and strict-build-green.
- Ready for 33-02: the API-reference render-fidelity audit (DOCS-04) + the DOCS-02 reference half, which builds the site and confirms the async docstrings render with Args/Returns/Raises/Example.
- No blockers.

## Self-Check: PASSED
- FOUND: docs/src/index.md (modified; `not available` grep empty; `have not shipped yet` present at line 71)
- FOUND: docs/src/guides/async.md (audited, unchanged)
- FOUND commit: 60a0569 (Task 1)
- FOUND commit: 7a43e2c (Task 3)
- `.venv/bin/mkdocs build --strict` exit 0

---
*Phase: 33-documentation*
*Completed: 2026-07-04*
