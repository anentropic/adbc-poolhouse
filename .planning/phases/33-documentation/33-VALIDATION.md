---
phase: 33
slug: documentation
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-04
validated: 2026-07-05
---

# Phase 33 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. This is a
> documentation phase: the automated validation surface is the strict docs build.
> There is no unit-test harness for prose.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | mkdocs strict build (Material + mkdocstrings) — no docs-example test harness exists |
| **Config file** | `mkdocs.yml` + `docs/scripts/gen_ref_pages.py` |
| **Quick run command** | `.venv/bin/mkdocs build --strict` |
| **Full suite command** | `.venv/bin/mkdocs build --strict` (single gate) |
| **Estimated runtime** | ~5–15 seconds |

---

## Sampling Rate

- **After every prose/docstring edit:** Run `.venv/bin/mkdocs build --strict` (catches broken refs and unresolved `:::` symbols immediately)
- **After every plan wave:** Run `.venv/bin/mkdocs build --strict`
- **Before phase completion:** Strict build green **and** humanizer checklist complete **and** the `index.md` "not available yet" contradiction removed
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 33-01-xx | 01 | 1 | DOCS-01 | — | N/A | build/render | `.venv/bin/mkdocs build --strict` | ✅ | ✅ COVERED |
| 33-01-xx | 01 | 1 | DOCS-02 | — | N/A | build/render | `.venv/bin/mkdocs build --strict` | ✅ | ✅ COVERED |
| 33-01-xx | 01 | 1 | DOCS-03 | — | N/A | build + manual grep | `.venv/bin/mkdocs build --strict`; `grep -n "not available" docs/src/index.md` (must return nothing) | ✅ | ✅ COVERED |
| 33-02-xx | 02 | 1 | DOCS-04 | — | N/A | build/render + manual review | `.venv/bin/mkdocs build --strict`; visual check of generated `reference/` for the 4 methods + reader | ✅ | ✅ COVERED |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.* The strict-build harness exists
and passes today; no new test files are required.

Out of scope (flag as scope creep if proposed): adding a docs-example execution test harness.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Humanizer pass applied to new/rewritten prose | DOCS-04 | Prose quality is not machine-checkable | Apply the `humanizer` skill to every new or substantially rewritten section of `async.md` / `index.md`; confirm no AI-writing tells remain |
| `index.md` no longer claims DataFrame fetches are unavailable | DOCS-03 | Semantic contradiction, not a build error | `grep -n "not available" docs/src/index.md` returns nothing; the line now reflects that `fetch_df`/`fetch_polars` shipped in Phase 31 |
| Reference page visually renders all 4 methods + `AsyncRecordBatchReader` | DOCS-04 | mkdocstrings render fidelity | Inspect the generated reference page; confirm Args/Returns/Raises + Example blocks appear for each symbol |

---

## Validation Sign-Off

- [x] All tasks have an automated verify (`mkdocs build --strict`) or a documented manual verification
- [x] Sampling continuity: strict build run after each prose edit
- [x] Wave 0 covers all MISSING references (none — infra already present)
- [x] No watch-mode flags (`--strict` is a one-shot build)
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-07-05 — DOCS-01..04 complete, strict build green, 0 gaps

---

## Validation Audit 2026-07-05

Reconciled at v1.5.0 close (was frozen at plan-time `draft`/`pending`). DOCS-01..04
are all Complete in REQUIREMENTS.md; the single automated gate
(`.venv/bin/mkdocs build --strict`) exits 0, and the manual verifications
(humanizer pass, `index.md` "not available" contradiction removed, reference render)
were confirmed in the 33-01/33-02 SUMMARYs. 0 gaps.
