# Phase 27: Dual-Backend Test Matrix - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the async layer (built in Phases 24–25, packaged in 26) is **backend-generic
and backend-neutral**: every async test runs under both asyncio AND trio, across
DuckDB (in-proc) and the Snowflake pytest-adbc-replay cassette, plus an Arrow
memory-stability proof, a limiter-sizing stress proof, and meta-guards that
enforce the no-`asyncio` / no-positive-`sleep` discipline.

Requirements in scope: **TEST-01, TEST-02, TEST-03, TEST-04, EDGE-27, EDGE-30**.

**This is a test-layer phase.** All work lives in `tests/` (primarily
`tests/async/` and `tests/_async_harness/`). No `src/adbc_poolhouse/_async/`
production code changes — if a test cannot pass without a source change, that is a
signal to stop and raise it, not to edit the frozen async surface.

Out of scope (other phases): the async usage guide / API reference (Phase 28,
DOCS-01..04); any P2 EDGE ids (08,13,14,16,20,22,23,24,31,32 — deferred to
v1.4.x); streaming / ingest / dataframe surfaces (Future Requirements).

</domain>

<decisions>
## Implementation Decisions

### EDGE-27 — meta-guard, not a normalization sweep (A1)
- **D-27-01:** Satisfy EDGE-27 with a **meta-test that source-scans `tests/async/`**
  asserting: no `import asyncio`, no `@pytest.mark.asyncio`, and every async test
  function is anyio-parametrized (requests `anyio_backend` / `anyio_backend_name`,
  directly or via a fixture). Implement the scan as a callable in the harness
  (extend `tests/_async_harness/guard.py`) so the meta-test just asserts its
  result is clean — mirrors the Phase 23/25 `scan_async_package` pattern.
- **D-27-02:** Do **NOT** rewrite the ~10 existing EDGE test files into a single
  uniform parametrization shape. They already request `anyio_backend`, run under
  both loops, and are ×20 loop-stable. Fix **only** any file the meta-scan flags
  as a violator. *Rationale: a blanket sweep risks reintroducing the lost-wakeup /
  MockClock-autojump landmines those tests were hardened against (see Phase 24/25
  LEARNINGS).*
- **D-27-03:** In EDGE-27, "both backends" = the **asyncio/trio** axis (the anyio
  sense, per the requirement text). The DuckDB/Snowflake axis is TEST-02 (D-27-04).

### TEST-01/02 — backend matrix shape (A2)
- **D-27-04:** Add a `snowflake_async_pool` cassette fixture mirroring the existing
  `duckdb_async_pool` (`tests/async/conftest.py`), backed by the **existing Phase 25
  pytest-adbc-replay cassette assets — no live Snowflake**. If a needed cassette
  recording is missing, record it once via the established replay flow rather than
  hitting a live warehouse.
- **D-27-05:** The **DuckDB × Snowflake cross-product applies to the read-path
  surface only** — happy-path lifecycle (connect → execute → `fetch_arrow_table`
  → checkin) and the ACUR fetch surface — each parametrized ×{asyncio, trio}.
- **D-27-06:** **Stub-gated mechanics stay DuckDB+stub only** (limiter, aliasing,
  cancel-depth, loop-hygiene). The cassette `ReplayCursor` is replay-only: it
  cannot block-gate a worker and lacks `adbc_cancel` (Phase 25), so it cannot back
  a deterministic gating test. TEST-02 is satisfied by the surface tests passing
  green on **both** real backends, not by forcing every EDGE test through the
  cassette.

### TEST-03 — Arrow memory-stability metric (A3)
- **D-27-07:** Primary signal is **`pyarrow.total_allocated_bytes()` delta** across
  **N ≥ 100** async cursor cycles (open → execute → `fetch_arrow_table` → checkin)
  on the real DuckDB pool, asserting the post-drop (and explicit `gc.collect()`)
  delta returns to baseline / stays bounded — i.e. **no monotonic growth**. NOT
  process RSS (non-deterministic → forces a flaky tolerance).
- **D-27-08:** Belt-and-braces second assertion: the existing `_release_arrow_allocators`
  reset path fired **once per checkin** (the ACONN-06 symmetric-cleanup invariant),
  proven by counting reset-event invocations across the N cycles.
- **D-27-09:** Run the stability test ×{asyncio, trio}.

### TEST-04 — limiter-sizing stress (A4)
- **D-27-10:** Primary proof is a **stub-gated deterministic flood** reusing the
  EDGE-12 pattern: launch **4× (`pool_size + max_overflow`)** workers, gate them
  inside `execute`, assert observed **running-max == `pool_size + max_overflow`**
  (bound never exceeded) and that every queued worker eventually runs (no
  starvation). Add a small **real-DuckDB smoke flood** for realism.
- **D-27-11:** Deadlock detection uses a **real-clock `time.monotonic()` watchdog
  thread** that fails the test if the flood does not drain — **never
  `anyio.fail_after`** (it autojumps to its own deadline under the trio MockClock;
  Phase 24/25 landmine).

### Claude's Discretion
- **EDGE-30:** Extend the harness guard with a rule banning **positive-duration
  `sleep(...)` literals** (`anyio.sleep`, `trio.sleep`, `asyncio.sleep`,
  `time.sleep` with a `> 0` literal arg) in `tests/async/` timeout/cancel tests,
  exposed as a callable the meta-test asserts is clean. `sleep(0)` checkpoints are
  allowed (used by EDGE-26).
- **Loop-stability gate:** every new or meta-flagged-and-fixed test passes a **×20
  loop (0 hangs)** before the phase is considered complete — the project's
  flaky-concurrency rule.
- **Test layout:** new tests as `tests/async/test_matrix_*.py` / `test_stability_*.py`
  / `test_limiter_stress_*.py` (final names at planner discretion), consistent with
  the existing `tests/async/test_edge_*.py` naming.
- **CI:** ensure the new tests run in the existing dual-backend job; keep them out
  of the PKG-04 no-anyio job (they require anyio at collection, like the rest of
  `tests/async/`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` §Testing (TEST-01..05) and §Async Edge-Case Test
  Coverage (EDGE-27, EDGE-30) — the locked scope for this phase
- `.planning/ROADMAP.md` → "Phase 27: Dual-Backend Test Matrix" — goal + success criteria

### Edge-case designs
- `.planning/research/ASYNC-EDGE-CASES.md` — full designs for EDGE-27 and EDGE-30
  (and the EDGE-12 limiter-bound pattern TEST-04 reuses)

### Prior-phase landmines & patterns (read before writing concurrency tests)
- `.planning/phases/26-packaging-extra-scoping/26-LEARNINGS.md` — lost-wakeup
  diagnosis, MockClock-autojump-vs-real-watchdog gotcha, sticky-cancel latch design
- `.planning/phases/24-core-async-wrapper/24-CONTEXT.md` — D-24-02 (cancel-mid-block
  deferral), D-24-03 (aliasing rejection, no per-connection lock)
- `.planning/phases/25-cancellation/25-CONTEXT.md` — cancellable_offload, invalidate-on-cancel,
  cassette `ReplayCursor` lacks `adbc_cancel`

### Existing harness & fixtures (the assets this phase builds on)
- `tests/async/conftest.py` — `anyio_backend` (asyncio/trio param), `duckdb_async_pool`,
  `make_stub_async_connection`
- `tests/_async_harness/conftest.py` — nested `anyio_backend`, the no-anyio-leak rationale
- `tests/_async_harness/stubs.py` — `BlockingStubCursor` / `BlockingStubConnection`
  (block-gating, `entered`, max-concurrent, sticky cancel latch)
- `tests/_async_harness/guard.py` + `tests/test_async_guard.py` — `scan_async_package`
  guard the EDGE-27/EDGE-30 meta-tests extend

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `anyio_backend` fixture (`tests/async/conftest.py`): already parametrizes
  asyncio + trio, function-scoped, trio `MockClock(autojump_threshold=0)`. The
  asyncio/trio axis (TEST-01, EDGE-27) is free — tests only need to request it.
- `duckdb_async_pool` fixture: real file-backed DuckDB `AsyncPool`, closed on
  teardown — the template for the new `snowflake_async_pool` cassette fixture.
- `make_stub_async_connection`: real `AsyncConnection` over a `BlockingStubConnection`
  — backs the limiter-stress flood (TEST-04) and any gated mechanics.
- `scan_async_package` / `tests/_async_harness/guard.py`: the AST source-scan the
  EDGE-27 and EDGE-30 meta-guards extend (no new scanner framework needed).
- EDGE-12 (`tests/async/test_edge_limiter.py`): the running-max == bound + 4× flood
  pattern TEST-04 reuses.
- EDGE-21 (`tests/async/test_edge_resource.py`): existing `total_allocated`/allocator
  reference — closest analog for the TEST-03 stability loop.

### Established Patterns
- **Real-clock watchdog, never virtual `fail_after`** for any test that gates a
  worker off-loop — a virtual `fail_after` autojumps to its own deadline under the
  trio MockClock the instant the worker blocks (Phase 24/25).
- **×20 loop-stability gate** before declaring concurrency work done (0 hangs).
- **Backend axis kept off the cassette for gating tests** — `ReplayCursor` can't
  block a worker and has no `adbc_cancel`.
- Nested `anyio_backend` conftest keeps the **sync suite anyio-free** (PKG-04) —
  do not hoist async fixtures to the root conftest.

### Integration Points
- New cassette fixture plugs into the same pytest-adbc-replay machinery used by the
  Phase 25 Snowflake legs.
- New meta-tests call into `tests/_async_harness/guard.py` (extended), asserted
  from `tests/async/` and/or `tests/test_async_guard.py`.

</code_context>

<specifics>
## Specific Ideas

User asked to review all gray-area assumptions in one pass rather than a
turn-by-turn discussion, and accepted the recommended call on all four areas
(A1 light-touch meta-guard, A2 cassette = read-path surface only, A3
`total_allocated_bytes` delta, A4 stub-gated flood + real-clock watchdog) plus the
cross-cutting discretion items. No competing "I want it like X" references raised.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (P2 EDGE ids and the streaming/ingest/
dataframe surfaces remain deferred to v1.4.x per REQUIREMENTS.md Future Requirements;
docs consolidation remains Phase 28.)

</deferred>

---

*Phase: 27-Dual-Backend Test Matrix*
*Context gathered: 2026-06-28*
</content>
</invoke>
