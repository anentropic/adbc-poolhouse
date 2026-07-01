---
phase: 29-arrow-streaming
plan: 04
subsystem: docs
tags: [docs, async, arrow-streaming, mkdocs, mkdocstrings, guide, api-reference, humanizer]

# Dependency graph
requires:
  - phase: 29-03
    provides: AsyncRecordBatchReader + AsyncCursor.fetch_record_batch (the shipped API + docstrings this guide documents)
provides:
  - Arrow-streaming how-to section in docs/src/guides/async.md (canonical async with usage, reader-lifetime contract, honest concurrency framing)
  - AsyncRecordBatchReader + fetch_record_batch rendered in the API reference (gen_ref_pages.py async block extended)
affects: [33-documentation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Explicit async reference block in gen_ref_pages.py per private _async class (D-28-02 pattern extended to _reader.py)"
    - "How-to guide section for a streaming surface: canonical async with usage + lifetime contract + honest GIL framing"

key-files:
  created:
    - .planning/phases/29-arrow-streaming/29-04-SUMMARY.md
  modified:
    - docs/src/guides/async.md
    - docs/scripts/gen_ref_pages.py

key-decisions:
  - "Placed the streaming section after 'What actually runs in parallel' so the per-batch GIL framing builds on the fetch_arrow_table materialization discussion rather than repeating it"
  - "Registered AsyncRecordBatchReader as a fourth explicit async reference block (mirrors AsyncPool/Connection/Cursor); this also resolves the cross-module autoref the 29-03 cursor docstring deliberately left as plain text"
  - "Dropped Arrow streaming from the experimental 'not available yet' list now that fetch_record_batch ships"

requirements-completed: [STREAM-01, STREAM-02, STREAM-03, STREAM-04, EDGE-33, PKG-01]

# Metrics
duration: ~15min
completed: 2026-07-01
---

# Phase 29 Plan 04: Arrow Streaming Documentation Summary

**The async guide now documents Arrow streaming — canonical `async with await cursor.fetch_record_batch() as reader:` usage, the always-close reader-lifetime contract (a live reader locks its connection for its whole lifetime; read-after-checkin surfaces the driver's native `pyarrow.lib.ArrowInvalid`, no bespoke type), and honest per-batch-offload / GIL-reacquired concurrency framing — and `AsyncRecordBatchReader` + `AsyncCursor.fetch_record_batch` render in the API reference under a clean `mkdocs build --strict`.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-01
- **Tasks:** 2 (1 `auto` docs task committed; 1 `checkpoint:human-verify` auto-approved under the `--auto` chain)
- **Files modified:** 2 production docs files (guide + reference-generation script)

## Accomplishments

- **Streaming how-to section** added to `docs/src/guides/async.md` ("Streaming a result set batch by batch"): shows the canonical `async with await cursor.fetch_record_batch() as reader:` → `async for batch in reader:` form (D-29-18) in the guide's illustrative-snippet style, with three sub-sections — always close the reader, reading after the reader is gone, and what streaming does/does not parallelize.
- **Reader-lifetime contract documented honestly** (T-29-07 mitigation): a live reader locks its connection for its whole lifetime (foreign ops raise `ConnectionBusyError` until close), draining is not closing (the C stream stays on the cursor until `close`), and `async with` is the one path that guarantees close under drain / `break` / exception / cancellation. Read-after-checkin (or read-after-close) surfaces the driver's native `pyarrow.lib.ArrowInvalid` — poolhouse adds no bespoke error type, no segfault, no read of freed memory.
- **Honest concurrency framing** (no over-claiming): each `read_next_batch` pull is offloaded individually through the pool limiter and a cancelled pull aborts via the cursor's `adbc_cancel`, but batch materialization reacquires the GIL (cross-linked to the existing "What actually runs in parallel" section); a single reader yields batches one at a time, in order, and real overlap comes from separate readers on separate connections.
- **API reference renders the new symbols:** `gen_ref_pages.py` gained a fourth explicit async reference block for `AsyncRecordBatchReader` (mirroring the `AsyncPool`/`AsyncConnection`/`AsyncCursor` blocks, `filters: ["!^__"]`). The built reference now contains `AsyncRecordBatchReader` (32 occurrences, including `.schema` and `.close` member anchors) and `AsyncCursor.fetch_record_batch` (21 occurrences), rendered with Args/Returns/Raises + Example and no RST role syntax.
- **Experimental warning updated:** Arrow streaming removed from the "not available yet on the async side" list; reader cross-links added to the warning and the "See also" section.
- **Humanizer pass applied** to all new prose: no banned promotional/AI vocabulary (`powerful`/`seamless`/`leverage`/`ensure that`/`allows you to`/...), ≤ 1 em dash per paragraph (rewrote the `ConnectionBusyError` paragraph to drop a matched em-dash pair), no rule-of-three padding, direct second-person voice matching the rest of the guide.

## Task Commits

1. **Task 1: Document Arrow streaming in the async guide + confirm reference rendering** — `9223a31` (docs) — guide section + `gen_ref_pages.py` reference block + experimental-warning/See-also updates.
2. **Task 2: human-verify checkpoint** — no code commit; auto-approved under the `--auto` chain (see below).

## Checkpoint: human-verify (auto-approved under --auto)

This plan's `type="checkpoint:human-verify"` gate was **auto-approved** because the run is part of a `--auto` chain (`workflow._auto_chain_active: true`). All automated verification the checkpoint's `<how-to-verify>` describes was performed by the executor rather than a human:

- `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` exits 0 (Material-for-MkDocs 2.0 advisory is a non-fatal banner, not a strict warning).
- The built API reference (`site/reference/adbc_poolhouse/index.html`) renders `AsyncRecordBatchReader` (with `.schema` / `.close` member anchors) and `AsyncCursor.fetch_record_batch`, with Google-style Args/Returns/Raises + Example blocks and zero RST `:role:` colons.
- Humanizer scan: no banned vocabulary, ≤ 1 em dash per paragraph.

**For a later human reviewer to eyeball:** the subjective voice/readability of the new section (does it read like the rest of the guide), and the accuracy of the lifetime + concurrency framing against the shipped `_reader.py` behavior (whole-lifetime lock, drain ≠ close, native `ArrowInvalid`, per-batch GIL reacquisition). The prose was written directly from `_reader.py` / `_cursor.py` docstrings and 29-CONTEXT/29-RESEARCH, so it should match, but a human pass on tone remains a nice-to-have.

## Deviations from Plan

None — plan executed as written. The only judgement call was section placement (after "What actually runs in parallel" so the GIL framing composes with the existing materialization discussion instead of duplicating it), which the plan left to Claude's discretion ("match its existing voice, section structure").

## Issues Encountered

- **Pre-commit basedpyright panics under the command sandbox** (known uv-sandbox pitfall — a `system-configuration` NULL-object panic, documented in MEMORY and 29-03-SUMMARY). The Task 1 commit was made outside the sandbox with hooks enabled (never `--no-verify`); basedpyright and all other hooks passed.

## User Setup Required

None — documentation-only change.

## Next Phase Readiness

- The streaming surface is now documented; Phase 33 (consolidation documentation) inherits an accurate async guide + reference for the streaming API and can focus on cross-cutting narrative rather than first-pass coverage.
- The `gen_ref_pages.py` async-block pattern is established for the next private `_async` class that ships (Phase 30 `adbc_ingest` lives on `AsyncCursor`, already blocked; Phase 31 `fetch_df`/`fetch_polars` likewise) — extend the same way if a new returned class appears.

## Self-Check: PASSED

- FOUND: `docs/src/guides/async.md` contains `async with await cursor.fetch_record_batch`
- FOUND: `docs/scripts/gen_ref_pages.py` contains the `AsyncRecordBatchReader` reference block
- FOUND: built `site/reference/adbc_poolhouse/index.html` renders `AsyncRecordBatchReader` + `fetch_record_batch`
- FOUND: `.planning/phases/29-arrow-streaming/29-04-SUMMARY.md`
- FOUND commit: `9223a31`

---
*Phase: 29-arrow-streaming*
*Completed: 2026-07-01*
