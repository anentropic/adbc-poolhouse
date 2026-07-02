---
gsd_state_version: 1.0
milestone: v1.5.0
milestone_name: Async Cursor Completion
status: executing
stopped_at: Completed 32-02-PLAN.md — EDGE-31/32/24 pinned on the streaming-pull + ingest offload paths, dual-backend, x20. test_edge_timeout_precision.py (EDGE-31 move_on_after deadline on a BLOCKED pull/ingest fires adbc_cancel once + invalidates; EDGE-32 deadline−ε op released by a real thread is NOT over-cancelled); test_edge_shutdown.py (EDGE-24 pending ingest/stream at task-group teardown raises no library-attributable warning, workers released in the teardown window; real duckdb drained-close raises nothing, checkedout()==0). 14 tests, 280 passed under x20 (0 hangs); basedpyright + ruff clean; mkdocs --strict rc 0; test-only, no production change. Deviation (Rule 1, both EDGE-31 legs): move_on_after(N>0) under the AUTOJUMPING virtual_clock, not literal move_on_after(0) — an expired scope is delivered at the first checkpoint before the worker dispatches (read/ingest_call_count==0, adbc_cancel==0) = the cancel-before-offload case (EDGE-08, 32-01), not a BLOCKED-op cancel. CONTINGENCY untriggered.
last_updated: "2026-07-02T21:13:57.000Z"
last_activity: 2026-07-02 -- Completed 32-02 (EDGE-31/32/24)
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 11
  completed_plans: 9
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-01)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 32 — P2 Edge Hardening

## Current Position

Phase: 32 (P2 Edge Hardening) — EXECUTING
Plan: 3 of 3
Status: Executing Phase 32 — 32-01 + 32-02 complete (EDGE-08/13/14/31/32/24); Wave 2 (32-03 gate) next
Last activity: 2026-07-02 -- Completed 32-02 (EDGE-31/32/24)

Progress: [██████████░░░░░░░░░░] 60% (3 of 5 phases complete: 29, 30, 31)

## Accumulated Context

### Roadmap (v1.5.0)

Five phases, numbered 29–33 (monotonic continuation from v1.4.0's Phase 28). Dependency-ordered per the research consensus: highest-risk streaming first, then the trivial wrappers, then edge hardening, then docs.

- **Phase 29 — Arrow Streaming** (STREAM-01..06, EDGE-33/20/22/23, PKG-01, PKG-03): the headline and only genuine design risk. New `AsyncRecordBatchReader` wrapper; per-batch `cancellable_offload` in `__anext__`; reader lifetime bound to the checked-out connection; reset-event checkin closes the reader first so read-after-checkin surfaces the driver's native closed-stream error (no bespoke error type — D confirmed by maintainer). Introduces the `__aexit__`/`__del__` surface (EDGE-20/22/23) that later phases reuse. First `_SyncCursor` Protocol extension (PKG-01) and owns the import-lint gate (PKG-03).
- **Phase 30 — Async Bulk Write** (INGEST-01..04): `adbc_ingest`, single whole-op offload, `on_abort=invalidate`, typed `Literal` mode with the `replace`-drops-table warning. Implementation note: keyword-only args through the PEP 646 TypeVarTuple offload boundary — resolve via the existing explicit-arm/partial pattern (spike in phase planning).
- **Phase 31 — DataFrame Convenience** (DF-01..04, PKG-02): `fetch_df`/`fetch_polars`, trivial single-offload wrappers; native `ModuleNotFoundError` passes through unchanged; frames self-owning after checkin. PKG-02 (pandas/polars → dev group only) lands here — first phase needing them in tests.
- **Phase 32 — P2 Edge Hardening** (EDGE-08/13/14/24/31/32): test-only additions extending existing chokepoint coverage across the new paths, plus `__del__` finalizers. Reuses the Phase 23 `BlockingStubCursor` harness.
- **Phase 33 — Documentation** (DOCS-01..04): consolidation point — streaming guide, ingest mode table + replace warning, DataFrame user-supplied note, API reference for the new symbols, `mkdocs build --strict`, humanizer pass.

### Roadmap Decisions (v1.5.0)

- **Phase numbering continues monotonically from v1.4.0's Phase 28 → starts at Phase 29** (established project convention; no reset across milestones).
- **Streaming front-loaded (Phase 29)** — the reader-lifetime design is the single novelty; every other method is a straightforward reuse of the existing chokepoint. Its `__aexit__`/`__del__`/`_detached`/per-batch-cancel patterns are copied by Phases 30–31, so it goes first (all four researchers converged on this order).
- **No bespoke async error type** (maintainer governing principle): async methods mirror the sync method's native errors. The reset-event checkin already makes read-after-checkin a clean driver exception (STREAM-04), so no `ReaderClosedError` class ships. Likewise no `find_spec` pre-check for missing pandas/polars (DF-03) — the native `ModuleNotFoundError` propagates unchanged.
- **PKG-* are cross-cutting gates but assigned to one phase each for coverage**: PKG-01 + PKG-03 → Phase 29 (first Protocol extension / import-lint owner); PKG-02 → Phase 31 (first pandas/polars test need). basedpyright-strict + AST import-lint are enforced in every phase regardless.
- **Docs gate applies to every phase** (CLAUDE.md: docs-author skill in `<execution_context>` for all phases ≥ 7): per-method Google-style docstrings (Args/Returns/Raises + `Example:`) are a completion requirement in each phase, not just Phase 33. Phase 33 is the consolidation point (guides + API reference + strict build).
- **Only P2 EDGE ids in scope** (EDGE-08/13/14/20/22/23/24/31/32/33); the P1 suite shipped in v1.4.0. EDGE-16 remains permanently DROPPED (D-24-03: connection aliasing rejected via `ConnectionBusyError`).

### Carried-forward gotchas (from v1.4.0, still load-bearing)

- **Real-clock watchdog, not `anyio.fail_after`, for concurrency bodies** — a virtual `fail_after` autojumps under the trio MockClock the instant the worker blocks off-loop. Release gated workers from a REAL thread.
- **Loop-stability: run cancellation/concurrency tests ×20, assert 0 hangs** — single-shot missed a ~33% deadlock in Phase 23; DuckDB `adbc_cancel` intermittently wedges the C execute (~10–40% cold), so real-driver cancel legs prove the downstream invalidate invariant deterministically rather than racing the wedge.
- **Every async test parametrized over asyncio AND trio** (`@pytest.mark.anyio`); DuckDB in-proc + Snowflake `pytest-adbc-replay` cassette (one recorded interaction per cassette). No positive-duration sleeps in timeout tests (source-scanned).
- **`.venv/bin/<tool>` over `uv run <tool>`** for hooks/mkdocs under the sandbox; `.venv/bin/basedpyright` is authoritative (harness Pyright gives false import-resolution errors). `DISABLE_MKDOCS_2_WARNING=true` + exit-code (not grep) for the strict-build gate.
- **gsd-tools lacks mutation handlers** — edit STATE/ROADMAP/REQUIREMENTS by hand, commit via `query commit --files`.

### Blockers/Concerns

- **`fetch_record_batch` returns a LIVE reader** (confirmed use-after-free/`ArrowInvalid` on read-after-checkin, DuckDB-probed): the entire Phase 29 design rests on binding the reader lifetime to the checked-out connection and forbidding checkin-while-live. This is the milestone's one real risk — the closed-before-checkin ordering is pinned by `test_reader_lifetime.py` on DuckDB (mandatory). **Snowflake cassette leg is NOT available** (see A1 below).
- **A1 RESOLVED (Plan 29-01): the Snowflake cassette cannot replay a streaming `fetch_record_batch`.** `pytest-adbc-replay`'s `ReplayCursor` implements only `fetch_arrow_table` + row fetches (no `fetch_record_batch`); the cassette stores one materialized Arrow result. Both Snowflake reader legs in `test_reader_lifetime.py` are skipped (`@pytest.mark.snowflake` + class-level skip) and documented as a MANUAL-ONLY re-record follow-up (29-VALIDATION §Manual-Only). DuckDB carries mandatory EDGE-33 coverage and is not gated on Snowflake. `test_reader_cassette_smoke.py` fails loudly if a future replay plugin gains streaming support (the signal to re-enable). Green-wave TODO: delete the file-level pyright pragma block from the six RED test files once production symbols land.
- **Keyword-only args across the TypeVarTuple offload boundary** (Phase 30): RESOLVED (Plan 30-02). `functools.partial(self._cursor.adbc_ingest, table_name, data, mode=..., ...)` binds all six args into a zero-positional-arg callable that satisfies `Callable[[Unpack[_Ts]], _T]` with `_Ts` empty — strict-clean, runtime-correct, guard-clean. This is now the milestone-general answer for any future keyword-bearing offload (e.g. Phase 31 DataFrame fetches). No chokepoint widening was needed (D-30-04).

## Deferred Items

Items acknowledged and deferred at v1.4.0 milestone close on 2026-07-01:

| Category | Item | Status |
|----------|------|--------|
| quick_task | 1-check-with-gh-run-list-and-related-comma | unknown |
| quick_task | 2-add-a-justfile-with-recipes-for-build-an | unknown |
| quick_task | 3-docs-guides-foundry-drivers-need-a-link | unknown |
| quick_task | 5-mkdocs-hot-reload-not-working | unknown |
| quick_task | 6-improve-readme-and-add-project-homepage | missing |
| quick_task | 7-improve-readme-and-add-project-homepage | unknown |
| quick_task | 9-fix-docs-gaps-develop-md-stale-syrupy-re | unknown |
| quick_task | 10-rewrite-integration-tests-to-use-pool-ap | unknown |
| quick_task | 260624-u45-databricks-catalog-schema | unknown |
| tech_debt | _async/_cancel.py docstring drift (describes from_thread bridge not used) | non-functional |

Pre-v1.4.0 tracking cruft plus one non-functional docstring; run `/gsd-cleanup` to triage.

## Session Continuity

Last session: 2026-07-02T21:09:00Z
Stopped at: Completed 32-01-PLAN.md — EDGE-08/13/14 anyio-chokepoint guarantees pinned on new-method offloads. `tests/async/test_edge_checkpoint.py` (EDGE-08: cancel set before the `adbc_ingest` offload is delivered at the offload boundary, `ingest_call_count == 0`, dual-backend, trio discriminator noted, `concurrency_marks` + `real_clock_watchdog`). `tests/async/test_edge_contextvars.py` (EDGE-13 copy-in + EDGE-14 no-leak-back on `fetch_df`, `-k copied_in`/`no_leak`, no gating). 6 passed; 44 under `ADBC_ASYNC_REPEAT=20` with 0 hangs; basedpyright 0 errors; test-only (no production change). Commits 6dce5f2, aedbc2b. Deviation (Rule 3): `register_on_enter` keys its hook by the CALLING (loop) thread id while `_block` dispatches per-thread hooks by the WORKER thread id, so the contextvar probe used the shared `on_enter` fallback instead — resolved entirely in-test, no harness change.
Next step: Execute 32-02-PLAN.md — EDGE-31/32 (`move_on_after(0)` cancels a blocked streaming pull + ingest; a deadline−ε op is NOT over-cancelled) + EDGE-24 (loop-shutdown cleanliness mid-stream/mid-ingest + real drained-close), looped x20. Reuse `real_clock_watchdog` (never `anyio.fail_after` as watchdog), `virtual_clock` for the deadline trigger, `concurrency_marks` on every leg.
