---
gsd_state_version: 1.0
milestone: v1.4.0
milestone_name: Async API
status: executing
stopped_at: Completed 23-01-PLAN.md
last_updated: "2026-06-27T09:30:01.300Z"
last_activity: 2026-06-27 -- Completed 23-01 (async harness foundation)
progress:
  total_phases: 9
  completed_phases: 1
  total_plans: 6
  completed_plans: 4
  percent: 11
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-25)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 23 — test-harness-foundation

## Current Position

Phase: 23 (test-harness-foundation) — EXECUTING
Plan: 3 of 4 (23-01 complete)
Status: Ready to execute
Last activity: 2026-06-27 -- Completed 23-01 (async harness foundation)

Progress: [░░░░░░░░░░] 0% (0/7 phases)

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases planned | 7 (22–28) |
| Requirements | 63 (100% mapped) |
| Plans complete | 0 |
| Phase 22 P01 | 35min | 3 tasks | 5 files |
| Phase 22 P02 | ~20min | 2 tasks | 1 files |
| Phase 23 P01 | ~12min | 3 tasks | 4 files |
| Phase 23 P02 | 4min | 3 tasks | 4 files |

## Accumulated Context

### Decisions

All v1.0.0–v1.2.0 decisions recorded in PROJECT.md Key Decisions table.

v1.4.0 roadmap decisions:

- **Phase numbering continues monotonically from v1.3.0's Phase 21.1 → starts at Phase 22** (established project convention: monotonic across milestones).
- **Feasibility spike is Phase 22 and gates the milestone** (research SUMMARY strong recommendation): the GIL-release premise for pyarrow `fetch_arrow_table` materialization is MEDIUM-confidence and must be validated before the full surface is built. SPIKE-03 go/no-go explicitly gates Phase 24.
- **Test-harness foundation pulled forward to Phase 23** (before the wrappers): TEST-05's `BlockingStubCursor` + event-gating/virtual-clock helpers + import-lint guard are prerequisites for the EDGE suites in Phases 24–25, so the harness lands before the code it exercises to avoid churn.
- **Cancellation is its own Phase 25** (research SUMMARY: #1 correctness risk by a margin — every surveyed async DB library shipped a cancel-leak bug). Dedicated phase for focused design review and explicit no-leak assertions under asyncio + trio.
- **Structural EDGE tests co-located with the behaviour they test**: limiter/reentrancy/exception/lifetime/hygiene EDGE (09,10,11,12,15,17,18,21,25,26) → Phase 24 (Core); cancellation EDGE (01–07,19,28,29) → Phase 25; meta/test-infra EDGE (27,30) → Phase 27 (Testing).
- **EDGE-19 (ExceptionGroup/task-group) → Cancellation (Phase 25)** rather than Core, because it pins keeping cancellation distinguishable from real ADBC errors in a task group — a cancellation-correctness concern tied to CANCEL-04.
- **Only the 22 P1 EDGE ids are in scope**; P2 EDGE (08,13,14,16,20,22,23,24,31,32) are deferred to v1.4.x per REQUIREMENTS.md Future Requirements.
- **Async layer lives in a new `src/adbc_poolhouse/_async/` package and reuses the sync core unchanged** (`_create_pool_impl`, config dispatch, 13-backend Protocol, `_release_arrow_allocators` reset event).
- **Documentation is Phase 28 (consolidation point)**, but per-phase docstrings are a completion requirement throughout (CLAUDE.md docs gate applies to all phases ≥ 7; every v1.4.0 phase is well past that — include the docs-author skill in `<execution_context>`).
- [Phase ?]: GIL spike measured: execute parallelizes (2.77x@N=4, eff 0.69); fetch_arrow_table partially serializes (1.67x@N=4, eff 0.42) — confirms execute>>fetch asymmetry, GO with materialization caveat
- [Phase ?]: Benchmark uses raw threads only (Barrier+ThreadPoolExecutor), file-backed temp DuckDB, real create_pool checkout path; benchmarks/ stays outside src/
- [Phase ?]: Phase 22 SPIKE-03 go/no-go: GO with a named fetch_arrow_table materialization caveat; gates Phase 24
- [Phase ?]: Phase 24 offload granularity: whole-operation (one to_thread per execute, one per fetch); CapacityLimiter(pool_size+max_overflow) governs cross-query concurrency where the I/O-bound win is real
- [Phase ?]: Spike proves GIL release / CPU parallelism but INFERS I/O concurrency (in-proc DuckDB has no network wait); Phase 27 dual-backend matrix exercises real backends
- [Phase 23]: anyio/trio/aiotools added to [dependency-groups] dev only (D-07); runtime deps untouched so the shipped wheel gains no async dependency (zero-cost-sync-path goal)
- [Phase 23]: anyio_backend fixture lives in a NESTED conftest (tests/_async_harness/), no anyio_mode=auto — conftest fixtures propagate downward only, so the sync suite never loads the anyio plugin (Pitfall 4) and Plan 04 self-tests must sit at tests/_async_harness/test_harness.py
- [Phase 23]: anyio_backend is function-scoped — fresh trio MockClock(autojump_threshold=0) per test avoids virtual-clock state bleed
- [Phase ?]: stubs.py strictly anyio-free (D-03); anyio bridge lives only in gating.py (T-23-03)
- [Phase ?]: Dual-entered documented: threading.Event sync signal (stub) vs anyio.Event loop gate (run_blocking) — T-23-07/Pitfall 2

### Roadmap Evolution

- 22 phases completed across v1.0.0, v1.2.0, and v1.3.0 milestones (1–21, plus inserted 17.5 and 21.1).
- v1.4.0 adds 7 phases (22–28) for the optional async API behind an `[async]` extra.
- Phase ordering: Spike (22, gates) → Harness (23) → Core wrapper (24) → Cancellation (25) → Packaging (26) → Test matrix (27) → Docs (28).

### Blockers/Concerns

- **GIL / pyarrow materialization (MEDIUM confidence):** whether `fetch_arrow_table` / `fetchall` release the GIL during pyarrow object construction is unvalidated per-method. Phase 22 must resolve this before Phase 24 begins. If materialization serializes, document the limit honestly rather than re-architecting.
- **Cancellation connection leak (highest industry-wide risk):** Phase 24 must never return a possibly-busy connection on any path even before the full `adbc_cancel` join lands in Phase 25.
- **40-token global limiter:** the dedicated per-pool `CapacityLimiter` is a first-class Phase 24 requirement (CORE-02), not a Phase 27 load-test fix.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 10 | Rewrite integration tests to use pool API and wire up conftest fixtures | 2026-03-07 | 7721866 | Verified | [10-rewrite-integration-tests-to-use-pool-ap](./quick/10-rewrite-integration-tests-to-use-pool-ap/) |
| 260624-u45 | Fix DatabricksConfig dropping catalog/schema in to_adbc_kwargs (DBX-02 follow-up) | 2026-06-24 | f72517b | Verified | [260624-u45-databricks-catalog-schema](./quick/260624-u45-databricks-catalog-schema/) |

## Session Continuity

Last session: 2026-06-27T09:29:41.982Z
Stopped at: Completed 23-01-PLAN.md
Next step: Execute 23-02 (next Phase 23 plan — async harness modules / self-tests).
</content>
