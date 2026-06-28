# Phase 25: Cancellation - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning
**Source:** `/gsd-discuss-phase 25 --assumptions` session — deliberate research (anyio threads/cancellation docs, ADBC C/Java cancel spec, `dbapi.py` source) plus a live driver probe against `adbc_driver_duckdb` (`/tmp/claude/probe_cancel.py`). Decisions below are grounded in that research, not speculation.

<domain>
## Phase Boundary

A cancelled or timed-out async operation never poisons the pool. When an awaited `execute` / `fetch_arrow_table` is cancelled or times out mid-flight, the in-flight C call is aborted via `cursor.adbc_cancel()` (invoked once from the loop thread), the worker thread is joined, the connection is invalidated, and cleanup completes under a shield — identically under asyncio and trio. This is the milestone's highest-risk correctness item, isolated for focused design and explicit assertions.

**Delivers (requirements):** CANCEL-01, CANCEL-02, CANCEL-03, CANCEL-04, EDGE-01, EDGE-02, EDGE-03, EDGE-04, EDGE-05, EDGE-06, EDGE-07, EDGE-19, EDGE-28, EDGE-29, plus the EDGE-09 cancel-mid-block leg deferred from Phase 24 (D-24-02).

**Builds on:** Phase 24's offload chokepoint, `AsyncPool`/`AsyncConnection`/`AsyncCursor`, the `_in_use` aliasing guard, and the already-shipped shielded check-in; Phase 23's `BlockingStubCursor.adbc_cancel`, `run_blocking` gating, virtual clock, and `scan_async_package` AST guard.

</domain>

<decisions>
## Implementation Decisions

### Cancel mechanism (the core design)

- **D-25-01 — Cooperative cancel via a watcher task; `adbc_cancel()` is called from the loop thread.** A blocked worker cannot be interrupted by anyio directly (researched, see Research Grounding). The only abort path is the driver's thread-safe `adbc_cancel()`, and the only way the loop can fire it *while otherwise parked on the offload* is a concurrent task that receives the cancellation. The query/fetch methods route through a single `cancellable_offload` helper shaped like:

  ```python
  async def cancellable_offload(adbc_cancel, fn, *args, limiter):
      done = anyio.Event()
      result = {}
      cancelled_by_us = False
      async with anyio.create_task_group() as tg:
          async def _watcher():
              nonlocal cancelled_by_us
              try:
                  await done.wait()                 # event-driven, NOT polling
              except get_cancelled_exc_class():
                  cancelled_by_us = True
                  with anyio.CancelScope(shield=True):
                      adbc_cancel()                 # thread-safe; unblocks the worker
                  raise
          async def _worker():
              try:
                  result["v"] = await offload(fn, *args, limiter=limiter)  # abandon_on_cancel=False
              finally:
                  done.set()
          tg.start_soon(_watcher)
          tg.start_soon(_worker)
      return result["v"]
  ```

  This is the minimal correct structure, not a workaround — anyio offers no built-in interruptible offload. The offload stays `abandon_on_cancel=False` so the worker is always joined (never abandoned in an unknown state). The watcher's `await done.wait()` parks with zero cost until the worker finishes or a cancellation arrives; it is not a busy loop.

- **D-25-02 — Distinguish "we cancelled it" by an explicit flag, NOT by exception type.** The probe showed a cancelled DuckDB `execute()` raises a plain `adbc_driver_manager.ProgrammingError("...INTERRUPT Error: Interrupted!")` — an ordinary `Error` subclass, not a dedicated cancelled type, and the ADBC `ADBC_STATUS_CANCELLED` mapping is driver-specific. So the wrapper must carry a `cancelled_by_us` flag (set when the watcher fires `adbc_cancel`) to know the resulting driver error is the expected side-effect of our own cancel. Sniffing the exception type or message is NOT portable across the 13 backends and is banned.

- **D-25-03 — Invalidate-on-cancel via `fairy.invalidate()`, offloaded and shielded.** The probe confirmed a cancelled connection is genuinely poisoned (subsequent use fails with "Current transaction is aborted"), so it MUST be invalidated, never returned. The probe also confirmed `_ConnectionFairy.invalidate()` alone drives `pool.checkedout()` straight to 0, a following `close()` is a safe no-op, and the pool stays healthy. Cleanup is therefore: offload `fairy.invalidate()` inside `anyio.CancelScope(shield=True)`. No bespoke teardown dance is needed. `AsyncConnection` gains an `invalidate()` method for this.

- **D-25-05 — `ExceptionGroup` / `except*` handling: cancellation wins, real ADBC errors preserved (EDGE-19/EDGE-03).** On the cancel path the worker's offload raises the driver interrupt error (D-25-02) at roughly the same time the watcher re-raises the framework `Cancelled`; the task group bundles both into an `ExceptionGroup`. The wrapper must (a) let the framework cancellation propagate so the caller's `fail_after` / `scope.cancel()` sees its expected exception type, (b) swallow the interrupt error when `cancelled_by_us` is set so the user never sees a spurious "Interrupted!", and (c) on the NON-cancel path, preserve a genuine `AdbcError` unchanged (the Phase 24 EDGE-17 contract). This is the single subtlest part of the phase.

### Discipline & guards

- **D-25-06 — `get_cancelled_exc_class()` only; no `asyncio.CancelledError` in `_async/` (EDGE-28).** All cancel detection uses `anyio.get_cancelled_exc_class()`; the caught cancellation is always re-raised, never swallowed. Extend the Phase 23 `scan_async_package` AST guard to assert no `asyncio.CancelledError` reference appears anywhere in `_async/`.

- **D-25-07 — Idempotent double-cancel during shielded cleanup (CANCEL-03/EDGE-04/EDGE-05).** A second cancellation arriving while the shielded cleanup runs must be a no-op against the cleanup: exactly one `adbc_cancel`, one `invalidate`, one surfaced cancel exception. The shield around the cleanup is what makes this hold; assert the counts explicitly.

### Scope of what gets cancel machinery

- **D-25-04 — Only the query/fetch methods opt in; check-in opts out; the rest have no offload.**
  - **Cancellable (watcher machinery):** `AsyncCursor.execute`, `executemany`, `fetch_arrow_table`, `fetchone`/`fetchmany`/`fetchall` — these block in the driver and have a cursor-level `adbc_cancel`.
  - **Shielded, deliberately NOT cancellable:** `AsyncConnection.close` / `__aexit__` / `AsyncCursor.close` — already wrapped in `CancelScope(shield=True)` in Phase 24. Check-in must complete, never be cancelled.
  - **No offload at all:** `cursor()`, `description`, `rowcount`, `arraysize` (synchronous; no I/O).
  - **`commit` / `rollback`: NOT made cancellable in this phase.** They block but the EDGE table targets only `execute`/`fetch_arrow_table`; connection-level `adbc_cancel` exists if ever wanted later. They stay as plain offloads. (Revisit only if a requirement demands it.)

### Claude's Discretion (for the planner)

- **D-25-08 — Helper placement.** Recommended: a new `src/adbc_poolhouse/_async/_cancel.py` housing `cancellable_offload`, leaving `_offload.py` as the un-aliased `to_thread.run_sync` chokepoint the AST guard matches. Folding into `_offload.py` is acceptable if it keeps the chokepoint literal intact. Planner decides.
- Exact wiring of `cancelled_by_us` and the `ExceptionGroup` unwrap (a small `except*` block vs. catching + filtering) — planner's call, as long as D-25-05's three guarantees hold.

</decisions>

<specifics>
## Specific Ideas

- The watcher/worker pair must NOT fire `adbc_cancel` on the success path — the `done` event releases the watcher normally when the worker finishes, so `adbc_cancel` only runs in the watcher's `except get_cancelled_exc_class()` branch.
- Per the loop-flaky-concurrency lesson (MEMORY): verify every cancel/concurrency test in a loop (×N, 0 hangs), not a single green run, and wrap concurrency-sensitive bodies in `fail_after(watchdog)`. A single-shot pass hid a ~33% deadlock in Phase 23.
- Tests use event-gating / virtual clock only — no positive-duration `sleep` (EDGE-30 territory, enforced later in Phase 27 but honor it now).

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 25: Cancellation" — goal, depends-on, the five success criteria.
- `.planning/REQUIREMENTS.md` — CANCEL-01..04, EDGE-01..07, EDGE-19, EDGE-28, EDGE-29 (verbatim acceptance text).

### Prior-phase decisions this phase rides on
- `.planning/phases/24-core-async-wrapper/24-CONTEXT.md` — D-24-01 (transient token model), **D-24-02 (the EDGE-09 cancel-mid-block leg owed to this phase)**, D-24-03 (`ConnectionBusyError` aliasing), D-24-04 (structural genericity).
- `.planning/phases/24-core-async-wrapper/24-RESEARCH.md` — Pattern 1 (offload chokepoint), Pitfall 2 (single-shot test hides deadlock), the `abandon_on_cancel` history, and the explicit "cancellation machinery → Phase 25" deferral.
- `.planning/phases/24-core-async-wrapper/24-PATTERNS.md` — file/analog map for the async layer.

### Code being extended
- `src/adbc_poolhouse/_async/_offload.py` — the single `to_thread.run_sync(limiter=, abandon_on_cancel=False)` chokepoint; its docstring already names the Phase 25 cancel path as "built in a later phase."
- `src/adbc_poolhouse/_async/_cursor.py` — the query/fetch methods to make cancellable; `close` already shielded.
- `src/adbc_poolhouse/_async/_connection.py` — gains `invalidate()`; `close`/`__aexit__` already shielded.
- `tests/_async_harness/stubs.py` — `BlockingStubCursor.adbc_cancel()` (flips `observed_cancel`, releases the worker) and the LOCKED D-04 attribute contract the EDGE assertions read.
- `tests/_async_harness/gating.py` — `run_blocking(..., entered=, abandon_on_cancel=)` worker→loop bridge.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`offload` chokepoint** (`_offload.py`): `cancellable_offload` wraps it rather than replacing it — the un-aliased `anyio.to_thread.run_sync` call must stay literal so the AST guard keeps seeing it (RESEARCH Pitfall 5).
- **Harness already cancel-aware:** `BlockingStubCursor` exposes `adbc_cancel()` (releases the blocked worker + flips `observed_cancel`), `adbc_cancel_call_count`, `close_call_count`, the re-armable gate, and `register_on_enter` for concurrent workers. No new stub surface should be needed for the cancel EDGE cases — the contract was built in Phase 23 for exactly this.
- **`virtual_clock()` + `run_blocking(entered=...)`** give deterministic "worker is inside the block → now cancel/timeout" sequencing with no sleeps.

### Established Patterns
- **Shielded check-in already exists** — Phase 24 wrapped `close`/`__aexit__`/`cursor.close` in `CancelScope(shield=True)`. CANCEL-03's shield is therefore partly in place; Phase 25 adds the invalidate path and double-cancel idempotency on top, it does not re-implement the shield.
- **Transient-token model (D-24-01)** — the cancelled offload is mid-call holding exactly one limiter token; `adbc_cancel` unblocks the worker, the offload returns, the token releases. EDGE-09's cancel-mid-block leg asserts the token returns to `borrowed_tokens == 0` exactly once on this path.
- **Reject-don't-serialize aliasing (D-24-03)** — unchanged; cancellation does not introduce a per-connection lock.

### Integration Points
- `AsyncCursor.execute`/`executemany`/`fetch*` switch from calling `offload(...)` to `cancellable_offload(self._cursor.adbc_cancel, self._cursor.<fn>, ..., limiter=self._limiter)`, and on cancel drive `self._owner.invalidate()`.
- `AsyncConnection.invalidate()` offloads `fairy.invalidate()` under a shield; pairs with the existing `_in_use` lifecycle.

</code_context>

<research_grounding>
## Research Grounding (authoritative facts — researcher may deepen, need not re-derive)

**ADBC cancel is the one thread-safe operation (the design's linchpin).**
- C API (`AdbcStatementCancel`): *"This must always be thread-safe (other operations are not). It is not necessarily signal-safe."* Calling it from another thread to interrupt an in-progress execute is the documented, intended use — the single carve-out from ADBC's "serialized access only" rule.
- Java mirror (`AdbcStatement.cancel()`): *"This method must be thread-safe (other methods are not necessarily thread-safe). This can be used to interrupt execution of a method like executeQuery()."*
- Cancelled operation returns `ADBC_STATUS_CANCELLED` *"(It is not guaranteed to, for instance, the result set may be buffered in memory already.)"* → so a cancel may instead let the call **return a normal result**; the wrapper must discard a late result and still invalidate.
- Python `dbapi.py`: `Cursor.adbc_cancel()` → `self._stmt.cancel()`; `Connection.adbc_cancel()` → `self._conn.cancel()`.

**anyio gives no built-in interruptible offload.**
- `to_thread.run_sync` is *shielded from cancellation by default*, so a plain `try/except get_cancelled_exc_class()` around the offload never fires while the worker is blocked.
- `abandon_on_cancel=True` does not stop the thread — *"the thread will still continue running – only its outcome will be ignored"* — which abandons the connection in an unknown state (the exact poisoning we prevent). Rejected.
- The only cooperative hook, `from_thread.check_cancelled()`, requires the worker to poll — useless when it is blocked in the driver's C call.
- Conclusion: a concurrent cancel-point (the watcher) is the minimum viable structure. Versions in use: anyio 4.14.1, adbc_driver_manager 1.11.0, sqlalchemy 2.0.49.

**Live driver probe (`adbc_driver_duckdb`, `/tmp/claude/probe_cancel.py`):**
- `cur.adbc_cancel()` from the main thread returned in ~0s, raised nothing, and unblocked the worker immediately.
- The cancelled `execute()` RAISED `adbc_driver_manager.ProgrammingError` (MRO: `ProgrammingError → DatabaseError → Error → Exception`), message `"INVALID_ARGUMENT: INTERRUPT Error: Interrupted!"` — a plain error, no dedicated cancelled type → motivates D-25-02.
- Post-cancel reuse of the same connection FAILED ("Current transaction is aborted") → the connection is poisoned → motivates D-25-03.
- `fairy.invalidate()` alone moved `checkedout()` 1 → 0; `close()` after invalidate was a safe no-op; the pool was reusable afterward → confirms D-25-03's cleanup is sufficient.

</research_grounding>

<docs_gate>
## Documentation Requirement (completion gate, CLAUDE.md phases ≥ 7)

Plans MUST include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>`. Phase is not complete until: new public symbols (e.g. `AsyncConnection.invalidate`, any cancel-behaviour docs on `execute`/`fetch_arrow_table`) have Google-style docstrings (Args/Returns/Raises, Markdown not RST); cancellation behaviour is reflected in the async guide; `.venv/bin/mkdocs build --strict` passes; humanizer pass applied to new/rewritten prose.

</docs_gate>

<deferred>
## Deferred Ideas

- **`commit` / `rollback` cancellation** — out of scope (D-25-04); revisit only if a requirement appears.
- **Streaming `RecordBatchReader` results** — v1.4.x (per Phase 24 RESEARCH); `fetch_arrow_table` stays fully materialized.
- **The `[async]` extra / PEP 562 lazy import / strict typing** — Phase 26.
- **Live dual-backend matrix (DuckDB + Snowflake cassette, asyncio + trio)** — Phase 27. Phase 25 proves correctness on the stub harness + DuckDB; Phase 27 re-runs these cancel tests across backends.

</deferred>

---

*Phase: 25-cancellation*
*Context gathered: 2026-06-28*
