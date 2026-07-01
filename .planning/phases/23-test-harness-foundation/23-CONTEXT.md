# Phase 23: Test Harness Foundation - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning
**Source:** discuss-phase (assumptions mode) — decisions locked in conversation

<domain>
## Phase Boundary

This phase builds the **deterministic, backend-neutral test harness** that every later
async/EDGE test rides on — built *before* the wrappers it exercises (Phase 24+) so harness
churn never blocks correctness work. Three deliverables, all test-only (never shipped in `src/`):

1. `BlockingStubCursor` / `BlockingStubConnection` fakes.
2. Event-gating + virtual-clock helpers usable under both asyncio and trio.
3. A source-scan / import-lint guard exposed as a callable check.

The `_async/` source package does **not** exist yet (Phase 24 creates it), so the harness must
be self-contained — it cannot import the async wrappers.

**Sole requirement:** TEST-05.
</domain>

<decisions>
## Implementation Decisions

### Virtual clock
- **D-01:** The virtual-clock helper is a **first-class Phase 23 deliverable**, not deferred. It
  is a **single backend-dispatching façade**: on the trio leg, `trio.testing.MockClock(autojump_threshold=0)`
  injected at the runner via the `anyio_backend` fixture options; on the asyncio leg,
  `aiotools.VirtualClock().patch_loop()` used as an in-body context manager. (The two halves are
  structurally different — runner-level injection vs in-body patch — so the façade dispatches on
  `anyio_backend_name`.)
- **D-02:** **Event-gating is the primary mechanism** for cancel-path determinism (a
  forever-blocking stub released by the test or by `adbc_cancel`, plus a sibling task calling
  `scope.cancel()`). The virtual clock covers the deadline/timeout paths (e.g. EDGE-06 P1, and the
  P2 timeout-precision cases) so Phase 25 does not have to invent timing infrastructure mid-flight.

### Stub fakes
- **D-03:** `BlockingStubCursor` / `BlockingStubConnection` are **pure-`threading` fakes with zero
  async code** — being sync-only is what makes them framework-neutral. They implement the dbapi
  surface (`execute`, `fetch_arrow_table`, `close`, `adbc_cancel`). `execute`/`fetch_arrow_table`
  block on a `threading.Event`; `adbc_cancel()` releases that event **and** flips `observed_cancel`.
- **D-04:** The stub records exactly what the EDGE table needs: per-call **thread-id**, **call
  counts**, **`observed_cancel`**, an **`entered`** signal (set on worker entry), and
  **`max_concurrent_in_execute`** (counter incremented on entry / decremented on exit under a lock).

### Import-lint / source-scan guard
- **D-05:** The guard is an **AST/source-scan callable returning a findings list** (so a later EDGE
  test can assert it is empty). Rules: ban `import asyncio` and ban bare `to_thread.run_sync(...)`
  **without** a `limiter=` argument, scoped to the `_async/` package. It **scans a configurable
  path** and **no-ops gracefully on an absent/empty dir** (because `_async/` does not exist until
  Phase 24). It is **tested against synthetic fixture source strings**, not the real (empty) package.

### Test infrastructure
- **D-06:** Phase 23 stands up the **`anyio_backend` parametrization** (`["asyncio", "trio"]`) in a
  test conftest, and adds **harness self-tests** that exercise both legs (block→release and
  block→`adbc_cancel`→unblock) with no real sleeps.
- **D-07:** Add **`anyio`, `trio`, and `aiotools`** as **dev/test-only dependencies**. The runtime
  `[async]` extra stays **deferred to Phase 26** — adding anyio to runtime now would contradict the
  zero-cost-sync-path goal.

### Claude's Discretion
- Exact harness module layout under `tests/` (e.g. `tests/_async_harness/`, `tests/async_/conftest.py`,
  or a flat `tests/harness.py`) — planner's choice, consistent with the existing flat `tests/` layout.
- The precise bridge for the `entered` signal from worker thread → loop without a real sleep
  (anyio `Event` set via `from_thread`, or a poll on an anyio `Event`) — planner/researcher to pin.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Harness design spec (authoritative)
- `.planning/research/ASYNC-EDGE-CASES.md` — the design bible for this harness: the five verified
  anyio/trio semantics, the exact stub attributes, the import-lint rules, and the consolidated
  EDGE-NN table (see especially "Shared test infrastructure these requirements imply").

### Feasibility / gating
- `.planning/phases/22-feasibility-spike/22-GO-NO-GO.md` — the GO verdict (with materialization
  caveat) that gates this milestone.

### Requirements / scope
- `.planning/REQUIREMENTS.md` — TEST-05 (the sole requirement for this phase) and the EDGE-NN table.
- `.planning/ROADMAP.md` — Phase 23 section (goal + 3 success criteria) and downstream Phases 24/25/27
  that consume this harness.
</canonical_refs>

<specifics>
## Specific Ideas

- **Plan-time caveat to verify:** confirm anyio's trio backend actually forwards a
  `{"clock": MockClock(autojump_threshold=0)}` option through to `trio.run` via the `anyio_backend`
  fixture, against the *installed* anyio version — do not take it on faith.
- The stub contract (attribute names in D-04) and the guard signature (D-05) become a **hard contract**
  for Phases 24 (EDGE-09/10/11/12/15/17/18/25/26), 25 (EDGE-01..07/28/29), and 27 (meta-guards).
- `BlockingStubCursor` backs EDGE-01..12, 15, 17, 25, 26, 28, 29, 31, 32; the virtual-clock/event-gating
  harness backs EDGE-06, 30, 31, 32; the guard backs EDGE-25, 27, 28.
</specifics>

<deferred>
## Deferred Ideas

- **Actual async wrappers** (`AsyncPool`/`AsyncConnection`/`AsyncCursor`, offload helper, per-pool
  limiter) — Phase 24.
- **Behavioral EDGE-NN tests** that run the harness against real wrapper behaviour — land with the
  phase that owns each behaviour (24/25), not here.
- **Cancellation logic** (`adbc_cancel` wiring, shielded checkin, invalidate-on-cancel) — Phase 25.
- **Meta-guard that asserts every async test is dual-parametrized** (EDGE-27/EDGE-30 as suite-level
  assertions) — Phase 27 owns meta-guards. Phase 23 ships only the *callable guard infrastructure*.
- **Real-backend / dual-backend matrix tests** (DuckDB + Snowflake cassette) — Phase 27.
- **The `[async]` runtime extra + PEP 562 lazy import** — Phase 26.

</deferred>

---

*Phase: 23-test-harness-foundation*
*Context gathered: 2026-06-27 via discuss-phase (assumptions mode); decisions locked in conversation.*
