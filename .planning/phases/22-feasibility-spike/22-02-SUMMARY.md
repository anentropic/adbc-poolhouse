---
phase: 22-feasibility-spike
plan: 02
subsystem: planning
tags: [go-no-go, gil, async-feasibility, milestone-gate, packaging-hygiene]

# Dependency graph
requires:
  - phase: 22 plan 01
    provides: measured GIL-release medians (execute 2.77x, fetch 1.67x) + re-runnable benchmark
provides:
  - "22-GO-NO-GO.md: SPIKE-03 milestone gate — GO with a named materialization caveat"
  - "Locked claim/disclaim split: GIL released during execute (parallelism + inferred I/O concurrency) vs GIL-bound fetch_arrow_table materialization"
  - "Phase 24 offload-granularity guidance (whole-operation; CapacityLimiter governs cross-query concurrency)"
  - "Verified: benchmarks/ stays out of the built wheel"
affects: [24 (offload granularity gated by this doc), 27 (dual-backend matrix exercises the inferred I/O concurrency), 28 (async docs honesty handoff DOCS-01)]

# Tech tracking
tech-stack:
  added: []  # no new deps; uv build uses already-present uv_build backend
  patterns:
    - "Planning prose artifact under .planning/, NOT docs/src/ (Phase 28 owns the user guide)"
    - "Wheel-content assertion via zipfile namelist (benchmark-match == [])"

key-files:
  created:
    - .planning/phases/22-feasibility-spike/22-GO-NO-GO.md
  modified: []  # pyproject.toml NOT edited — no packaging glob leaked benchmarks/

key-decisions:
  - "Verdict is GO with a named materialization caveat — fetch serialization is a documented limit, not a NO-GO (22-RESEARCH Pitfall 5)"
  - "Terminology held precisely: PARALLELISM (GIL-released C-side work, measured) vs I/O CONCURRENCY (overlapping network waits, inferred)"
  - "Inference gap named explicitly: in-proc DuckDB has no network wait, so the spike proves GIL release but does not directly measure I/O concurrency"
  - "Phase 24 must offload at whole-operation granularity; do NOT split execute from fetch hoping to overlap (fetch serializes regardless)"

requirements-completed: [SPIKE-03]

# Metrics
duration: ~20min
completed: 2026-06-26
---

# Phase 22 Plan 02: SPIKE-03 go/no-go Summary

**The milestone gate is written: GO with a named `fetch_arrow_table` materialization caveat. The doc transcribes plan 01's two measured medians (execute 2.77x parallel, fetch 1.67x partial-serial), states what the async layer may claim (GIL released during `execute` → real C-side parallelism, inferred I/O concurrency) vs disclaim (large materialization is GIL-bound), names the parallelism-vs-I/O-concurrency inference gap, and gives Phase 24 whole-operation offload guidance. The kept `benchmarks/` directory is confirmed out of the built wheel.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2
- **Files created:** 1 (`22-GO-NO-GO.md`)
- **Files modified:** 0 (pyproject.toml untouched — no packaging glob leaked `benchmarks/`)

## Accomplishments

### Task 1 — wheel-exclusion verification (verify-only, no commit)

Built the wheel (`uv build --wheel`) and asserted via `zipfile` namelist that no `benchmark`-matching entry is present.

- Wheel: `adbc_poolhouse-1.3.1-py3-none-any.whl`
- `benchmark`-matching namelist entries: `[]`
- Top-level wheel entries: `adbc_poolhouse/`, `adbc_poolhouse-1.3.1.dist-info/`

`benchmarks/` lives outside `src/`, so the `uv_build` backend excludes it by default. No `pyproject.toml` edit was required — this confirms research assumption A2 and actively mitigates threat T-22-02 (spike code shipping to users). No file change, so no commit for this task (verify-only, exactly as the plan specified).

### Task 2 — `22-GO-NO-GO.md` (commit `02c38f9`)

Wrote the SPIKE-03 deliverable covering all 8 points of the Go/No-Go Document Contract:

1. **Verdict:** GO with a named materialization caveat; explicitly gates Phase 24.
2. **The two measured ratios** with N, dataset size, single/wall/ideal/serial times, and median-of-trials methodology — transcribed verbatim from 22-01-SUMMARY.md (execute 2.77x @ N=4, eff 0.69; fetch 1.67x @ N=4, eff 0.42), with the 8-core / CPython 3.14.2 standard-GIL machine caveat.
3. **Claim:** ADBC C path releases the GIL during `execute` → real parallelism of C-side work, and by inference real I/O concurrency on network backends.
4. **Disclaim:** not blanket parallelism; large `fetch_arrow_table` materialization is GIL-bound and approaches serialization across concurrent fetches.
5. **Inference gap, named:** in-proc DuckDB has no network wait, so the spike proves GIL release / CPU parallelism but infers I/O concurrency — it does not directly measure it. Phase 27's dual-backend matrix exercises real backends.
6. **Phase 24 offload granularity:** offload at whole-operation granularity (one `to_thread` per `execute`, one per `fetch_arrow_table`); do not split a single query's execute from its fetch. `CapacityLimiter(pool_size + max_overflow)` governs cross-query concurrency, where the I/O-bound win is real.
7. **Phase 28 doc-honesty handoff (DOCS-01):** async wins are largest for latency/I/O-bound queries, smaller for CPU-bound large-result materialization.
8. **Free-threaded note:** standard GIL build only; no-GIL out of scope and unmeasured.

A packaging-hygiene section records the Task 1 wheel verification. Docs-author voice (direct, second person) and a humanizer pass applied; Markdown only (no RST roles, no curly quotes). `mkdocs build --strict` still passes.

## Task Commits

1. **Task 1: wheel-exclusion verification** — no commit (verify-only; wheel built and inspected, no file change required).
2. **Task 2: 22-GO-NO-GO.md** — `02c38f9` (docs).

**Plan metadata:** see final docs commit.

## Files Created/Modified

- `.planning/phases/22-feasibility-spike/22-GO-NO-GO.md` (created, 93 lines) — the SPIKE-03 go/no-go milestone gate.

## Decisions Made

- **GO with caveat, not NO-GO.** The fetch serialization (1.67x, eff 0.42) is framed as a documented concurrency limit on large-result materialization plus offload guidance — never as a milestone blocker (22-RESEARCH Pitfall 5). The async win lives in network-wait overlap, which the execute result supports.
- **Terminology held to the locked CONTEXT framing.** Parallelism (measured, GIL-released C-side work) and I/O concurrency (inferred, overlapping network waits) are kept distinct throughout; the doc never claims the spike directly measured I/O concurrency.
- **Transcribed, not re-measured.** The medians come straight from plan 01's recorded run; no benchmark was re-run for this plan (the numbers are the empirical record, not a CI assertion).

## Deviations from Plan

None — plan executed exactly as written. Task 1 confirmed `benchmarks/` is already excluded from the wheel (no `pyproject.toml` edit needed, as the plan anticipated); Task 2 wrote the doc to the 8-point contract.

## Authentication Gates

None.

## Issues Encountered

- **Sandbox vs. `uv` / build tooling.** `uv build` and `mkdocs build --strict` panic under the command sandbox (the known system-configuration NULL-object / tokio panic noted in plan 01). Both were run with the sandbox disabled so the real build and strict-doc gate executed. No code or content change resulted.
- **`$TMPDIR` differs between sandboxed and non-sandboxed runs.** The wheel landed under the non-sandbox `/var/folders/.../T/wheel22/` rather than the sandbox `$TMPDIR`; the inspection script was widened to glob both locations. Cosmetic; the assertion (`benchmark`-match == `[]`) passed.

## Scope / Constraint Compliance

- No async/production code; the deliverable is a planning artifact under `.planning/`, not `docs/src/` (Phase 28 owns the user guide).
- `benchmarks/` confirmed out of the built wheel; no `pyproject.toml` change.
- Terminology, inference gap, claim/disclaim split, and Phase 24 offload guidance all present and held to the locked CONTEXT constraints.
- `mkdocs build --strict` passes; Markdown only (no RST `:role:`, no curly quotes); humanizer pass applied.

## Next Phase Readiness

- **Gate cleared for Phase 24.** The go/no-go fixes the concurrency claim the async layer may make and the offload granularity (whole-operation). Phase 24 can begin the `_async/` wrappers against this honest framing.
- **Phase 27** exercises the inferred I/O concurrency against real backends (the dual-backend matrix).
- **Phase 28** inherits the DOCS-01 doc-honesty handoff: async wins largest for I/O-bound queries, smaller for large-result materialization.

## Self-Check: PASSED

- `22-GO-NO-GO.md` exists on disk (93 lines, contains "GO", all 8 contract markers present: parallelism, I/O concurrency, infer, fetch_arrow_table, Phase 24).
- Task 2 commit `02c38f9` present in history.
- Wheel built clean of `benchmarks/`; `mkdocs build --strict` passes.

---
*Phase: 22-feasibility-spike*
*Completed: 2026-06-26*
