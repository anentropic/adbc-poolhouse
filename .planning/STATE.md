---
gsd_state_version: 1.0
milestone: v1.5.0
milestone_name: Async Cursor Completion
status: "Phase 32 CLOSED — all six EDGE requirements (08/13/14/24/31/32) green x20 on macOS + Linux CI; test-only, zero production change. Next: Phase 33 (Documentation)"
stopped_at: "Completed 32-03-PLAN.md — Phase 32 CLOSED. Wave-2 gate plan: proved the four Wave 1 modules hold together in the full async suite under `ADBC_ASYNC_REPEAT=20` on macOS (2702 passed, 0 hangs, no cross-test interaction, no regression) and — authoritatively — on Linux CI (run 28622475955, Python 3.11 + 3.14, 0 hangs), closing the platform-dependent lost-wakeup gate for EDGE-24/31/32. Task 2 blocking human-verify checkpoint APPROVED (contingency confirmed NOT fired; both Wave 1 SUMMARYs state zero production change). Import-lint (PKG-03) + basedpyright-strict + `mkdocs --strict` (exit 0) all green. Task 3 docs gate ran in reduced test-only form: no RST roles in the new modules, no new public symbol, no guide edit — no file change, no commit (the passing strict build IS the gate). All six EDGE requirements (08/13/14/24/31/32) complete; zero production change across the whole phase (the new-method offloads share the already-proven `cancellable_offload`/`offload` chokepoint)."
last_updated: "2026-07-04T00:38:33.421Z"
last_activity: 2026-07-04 -- Phase 33 planning complete
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 11
  completed_plans: 11
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-01)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 32 — P2 Edge Hardening

## Current Position

Phase: 33
Plan: Not started
Status: Phase 32 CLOSED — all six EDGE requirements (08/13/14/24/31/32) green x20 on macOS + Linux CI; test-only, zero production change. Next: Phase 33 (Documentation)
Last activity: 2026-07-04 -- Phase 33 planning complete

Progress: [████████████████░░░░] 80% (4 of 5 phases complete: 29, 30, 31, 32)

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

Last session: 2026-07-02T22:26:00Z
Stopped at: Completed 32-03-PLAN.md — Phase 32 CLOSED. Wave-2 gate plan: proved the four Wave 1 modules hold together in the full async suite under `ADBC_ASYNC_REPEAT=20` on macOS (2702 passed, 0 hangs, no cross-test interaction, no regression) and — authoritatively — on Linux CI (run 28622475955, Python 3.11 + 3.14, 0 hangs), closing the platform-dependent lost-wakeup gate for EDGE-24/31/32. Task 2 blocking human-verify checkpoint APPROVED (contingency confirmed NOT fired; both Wave 1 SUMMARYs state zero production change). Import-lint (PKG-03) + basedpyright-strict + `mkdocs --strict` (exit 0) all green. Task 3 docs gate ran in reduced test-only form: no RST roles in the new modules, no new public symbol, no guide edit — no file change, no commit (the passing strict build IS the gate). All six EDGE requirements (08/13/14/24/31/32) complete; zero production change across the whole phase (the new-method offloads share the already-proven `cancellable_offload`/`offload` chokepoint).
Next step: Execute Phase 33 — Documentation (DOCS-01..04): Arrow streaming guide (reader-lifetime contract + honest concurrency framing), `adbc_ingest` mode Literal table + explicit `replace`-drops-the-table warning, DataFrame user-supplied note, API reference for `AsyncRecordBatchReader` + the four new `AsyncCursor` methods, `mkdocs build --strict` gate, humanizer pass. This is the docs consolidation point; run `/gsd-plan-phase 33` to plan it.
