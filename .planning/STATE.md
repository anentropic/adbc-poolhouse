---
gsd_state_version: 1.0
milestone: v1.4.0
milestone_name: Async API
status: executing
stopped_at: Completed 26-01-PLAN.md ([async] extra + relock + metadata test)
last_updated: "2026-06-28T09:00:00.000Z"
last_activity: 2026-06-28 -- Completed Phase 26 Plan 01 (PKG-01)
progress:
  total_phases: 9
  completed_phases: 4
  total_plans: 20
  completed_plans: 18
  percent: 44
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-25)

**Core value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.
**Current focus:** Phase 26 — Packaging & Extra Scoping

## Current Position

Phase: 26 (Packaging & Extra Scoping) — EXECUTING
Plan: 2 of 4
Status: Executing Phase 26 (26-01 complete)
Last activity: 2026-06-28 -- Completed Phase 26 Plan 01 (PKG-01)

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
| Phase 23 P03 | 25m | 2 tasks | 2 files |
| Phase 23 P04 | 10min | 3 tasks | 1 files |
| Phase 24 P01 | 30min | 2 tasks | 3 files |
| Phase 24 P02 | 7min | 2 tasks | 7 files |
| Phase 24 P03 | 6min | 2 tasks | 2 files |
| Phase 24 P04 | ~25min | 3 tasks | 10 files |
| Phase 24 P05 | ~12min | 2 tasks | 4 files |
| Phase 25 P01 | 9min | 2 tasks | 4 files |
| Phase 25 P02 | 15min | 2 tasks | 4 files |
| Phase 25 P03 | ~95min | 2 tasks | 3 files |
| Phase 25 P04 | ~7min | 2 tasks | 2 files |
| Phase 26 P01 | ~10min | 2 tasks | 3 files |

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
- [Phase ?]: D-05 guard shipped as scan_async_package(root)->list[Finding]; aliased run_sync re-import is an accepted, test-locked limitation
- [Phase 23]: A1 RESOLVED (positive): anyio asyncio move_on_after honours aiotools VirtualClock().patch_loop(); asyncio virtual-clock leg passes — no event-gating fallback needed for the asyncio timeout leg
- [Phase 23]: Dual-backend harness self-tests live INSIDE tests/_async_harness/ (anyio_backend propagates downward); tg.start_soon binds entered=/limiter= via functools.partial; virtual-clock proofs use a real time.monotonic() watchdog (a nested virtual fail_after autojumps to its own deadline first under MockClock)
- [Phase ?]: [Phase 24]: entered bridged via the stub's on_enter hook fired INSIDE _block (D-CF-01) — fixes the WR-01 re-arm deadlock at the root, making await entered a true 'inside the block' signal
- [Phase ?]: [Phase 24]: on_enter is a single-worker attribute PLUS a per-thread register_on_enter registry — a single shared attribute deadlocked test_max_concurrent (two workers on one cursor, last-writer-wins clobber)
- [Phase ?]: [Phase 24]: re-arm watchdog is a real time.monotonic() side thread that close()s the stub, NOT anyio.fail_after (a virtual fail_after autojumps under the trio MockClock the instant the worker blocks off-loop)
- [Phase ?]: [Phase 24]: PEP 695 generic syntax rejected for a TypeVar — project pins pythonVersion=3.11; PEP 695 needs 3.12+
- [Phase ?]: [Phase 24]: backend config names appear only in docstring Example: blocks; zero in executable _async/ code (D-24-04 verified by AST identifier scan)
- [Phase ?]: [Phase 24]: AsyncConnection/AsyncCursor shipped as typed contracts (raise NotImplementedError) so connect() is typeable; Plan 03 fills bodies against the frozen interface
- [Phase 24]: Plan 03 settled Open Q1/A3 — the SQLAlchemy _ConnectionFairy proxies commit/rollback/cursor/close straight to the dbapi connection (probed on DuckDB); no driver_connection unwrap needed
- [Phase 24]: AsyncCursor lives in its own module src/adbc_poolhouse/_async/_cursor.py (split out of _connection.py); _SyncCursor structural Protocol types the driver-agnostic dbapi cursor surface, with a single cast at AsyncConnection.cursor() to bridge SQLAlchemy's narrower DBAPICursor type
- [Phase 24]: _in_use is a plain bool check-and-set (no await between read and write), never a lock — 2nd concurrent caller is rejected with ConnectionBusyError, not queued (D-24-03 implemented); EDGE-15/18/21 behavioral proofs deferred to Plan 04
- [Phase ?]: [Phase 24]: Plan 04 verification backbone — happy-path lifecycle (both backends + Snowflake cassette) + EDGE-09/10/11/12/15/17/18/21/25/26 all green and x20 loop-stable (0 hangs); EDGE-09 cancel-mid-block correctly absent (D-24-02)
- [Phase ?]: [Phase 24]: tests/async cannot be imported by dotted path (async is a keyword) — sibling helpers loaded via importlib; real-clock watchdog (not anyio.fail_after) used for concurrency bodies per the MockClock autojump gotcha
- [Phase ?]: [Phase 24]: Async docs gate closed — guide quotes Phase 22 SPIKE numbers honestly (execute ~2.77x@N=4, fetch_arrow_table ~1.67x@N=4, in-process DuckDB caveat); aliasing antipattern + ConnectionBusyError documented (D-24-03)
- [Phase ?]: [Phase 24]: AsyncPool/AsyncConnection/AsyncCursor are NOT top-level exports — guide cross-refs only the exported factory fns + ConnectionBusyError; method-level mkdocstrings refs fail autorefs --strict, use inline code
- [Phase 25]: BlockingStubConnection gained lock-guarded invalidate()/invalidate_call_count (D-04 LOCKED contract); the seam AsyncConnection.invalidate() -> self._fairy.invalidate() (D-25-03) that stub-backed EDGE-02/04/05/29 assert by name
- [Phase 25]: AST guard gained banned-asyncio-cancelled-error rule (_GuardVisitor.visit_Attribute, EDGE-28/D-25-06); real _async/ scan stays clean; D-03 preserved (stubs.py still pure-threading)
- [Phase 25]: strict basedpyright pre-commit gate forces RED+GREEN co-commit when a RED test references a not-yet-existing attribute (Task 1); RED verified via pytest before GREEN landed
- [Phase 25]: cancellable_offload (watcher/worker task group) + AsyncConnection.invalidate (shielded, bypasses _in_use) shipped; six AsyncCursor query/fetch methods rewired; close untouched (D-25-04); to_thread.run_sync stays literal in _offload.py (scan []) 
- [Phase 25]: invalidate moved INTO cancellable_offload via an on_abort shielded callback, gated on a worker_started flag (set on the worker thread = entered-driver boundary) — the verbatim RESEARCH cursor-except design deadlocked on a saturated-limiter queued-cancel and over-invalidated never-poisoned connections (EDGE-01/07); fix keeps TestEdge10 green and x20 loop-stable
- [Phase 25]: adbc_cancel resolved lazily via getattr in AsyncCursor._adbc_cancel — the pytest-adbc-replay ReplayCursor (D-24-04 cassette backend) lacks adbc_cancel; eager attribute access crashed the Snowflake leg on the success path
- [Phase 25]: method-level mkdocstrings autoref to _async._connection.AsyncConnection.invalidate fails --strict (the gen_ref_pages.py skips any _-prefixed module path) — confirms the Phase-24 lesson; guide names invalidate in inline code, not a cross-ref link
- [Phase 25]: 25-02's cancellable_offload leaked the driver interrupt on the REAL cancel path — anyio does NOT collapse the bundle as research assumed; the aborted DuckDB worker RAISES ProgrammingError, surfaced as a single-member ExceptionGroup that escaped past fail_after. Fixed in 25-03 with a cancelled_by_us flag that swallows the interrupt and yields one cancellation checkpoint so the caller's TimeoutError/scope.cancel surfaces (D-25-02/05). Stub legs never hit this (stub adbc_cancel returns the worker cleanly)
- [Phase 25]: DuckDB's adbc_cancel against an in-flight query is best-effort AND intermittently WEDGES the worker thread inside the C execute (~10-40% of cold runs, faulthandler-confirmed) — an unfixable driver-level hang. The real-driver EDGE-02 leg therefore proves the downstream invariant (AsyncConnection.invalidate drains checkedout() to 0) deterministically instead of racing the wedge-prone cancel; the cancel->abort->invalidate wiring is proven on the stub during leg, real cancel-during-checkin on the trio-stable checkin_duckdb leg
- [Phase 25]: real-time-sensitive cancel/finish legs release the gated worker from a REAL thread (waiting on the stub's entered threading.Event), because a loop-side releaser is starved under the trio MockClock autojump (EDGE-07)
- [Phase 25]: EDGE-19 pins the 25-02 single-member-EG unwrap on a real DuckDB pool — a genuine AdbcError escapes cancellable_offload BARE (pytest.raises(AdbcError) AND not isinstance(excinfo.value, BaseExceptionGroup)); after a NON-cancel error the connection returns via the reset path (_pool.checkedout()==0), NOT invalidated (invalidate-only-on-cancel, Pitfall 6 / EDGE-18)
- [Phase 26]: [async] extra pins anyio>=4.13 (D-02, NOT >=4.0.0) matching the dev-group floor → resolves to 4.14.1; [all] gains adbc-poolhouse[async]; no new third-party package introduced (T-26-01 accept). uv.lock relocked so Plan 04's --locked no-anyio install stays coherent. Metadata test (tests/test_pkg_extra.py) is anyio-free (importlib.metadata only) so it collects under the no-anyio CI job
- [Phase 25]: EDGE-09 cancel-mid-block leg (D-24-02 owed from Phase 24) lands — gate a stub worker inside execute, cancel the scope so the watcher fires adbc_cancel, assert adbc_cancel_call_count==1 + borrowed_tokens==0 after the cancelled offload (transient token released exactly once), x50, both backends, x20 loop-stable; a belt-and-braces finally release keeps the group fail-fast (never a hang) without changing the happy cancel path

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

Last session: 2026-06-28T09:00:00.000Z
Stopped at: Completed 26-01-PLAN.md ([async] extra + relock + metadata test)
Next step: Execute Phase 26 Plan 02 (PKG-05 — TypeVarTuple/Unpack tightening of offload/cancellable_offload).
</content>
