# Phase 24: Core Async Wrapper - Context

**Gathered:** 2026-06-27 (carry-forward seed) · **Discussed:** 2026-06-27 (4 core design decisions locked)
**Status:** DISCUSSED — the four load-bearing design decisions (limiter model, EDGE-09 split,
connection-aliasing policy, backend-coverage method) are locked below. Everything else about the
wrapper surface remains Claude's discretion within ARCHITECTURE.md.
**Source:** Phase 23 code review + deferred fixes (`23-REVIEW-FIX.md`); `/gsd-discuss-phase 24 --assumptions` session.

<domain>
## Phase Boundary

Phase 24 builds the `AsyncPool`/`AsyncConnection`/`AsyncCursor` surface, the offload helper, and the
per-pool `CapacityLimiter`, plus the *structural* EDGE coverage assigned to it (EDGE-09, 10, 11, 12,
15, 17, 18, 21, 25, 26). The full cancellation machinery (`adbc_cancel`/invalidate/`CancelScope(shield=True)`
and EDGE-01..07/19/28/29) is **out of scope — it belongs to Phase 25**. Streaming `RecordBatchReader`
results are deferred to v1.4.x; `fetch_arrow_table` returns a fully-materialized `pyarrow.Table` only.

This file carries two layers: (1) the Phase 23 carry-forward items (harness contract, `entered`-timing
redesign, deferred WR/IN findings) that Phase 24 must honour, and (2) the four design decisions locked
during discuss-phase.
</domain>

<decisions>
## Phase 24 Design Decisions (locked 2026-06-27)

### D-24-01 — Limiter token model: TRANSIENT, borrowed per-offload (NOT held for connection lifetime)
**Decision:** Every offloaded call (`connect`, `execute`, `executemany`, `fetch*`, `fetch_arrow_table`,
`commit`, `rollback`, `close`) passes `limiter=pool._limiter` to `anyio.to_thread.run_sync` and borrows
a token **only for the duration of that one call**. An `AsyncConnection` holds **no** limiter token
between calls.

**Why this is the only correct model:** it simultaneously satisfies three otherwise-conflicting
requirements — every offload passes `limiter=` (EDGE-25 lint), no hold-and-wait deadlock (EDGE-11), and
a strict in-flight bound (EDGE-12). Safety is by construction: one `AsyncConnection` is used serially
(ADBC rule + checkout guarantee → ≤1 offload in flight per connection), and checked-out connections are
already capped at `pool_size + max_overflow` by the sync `QueuePool`. So concurrent in-connection
offloads ≤ bound = total tokens; the worst case (every checked-out connection executing at once) is
exactly `bound` offloads, which exactly fits.

**Rejected — Option B (hold a token from checkout to checkin):** N tasks each holding a connection hold
N tokens; each then `execute`s needing a token none will release → classic hold-and-wait deadlock
(EDGE-11). The only escape (in-connection offloads reuse the held token without re-acquiring) violates
the EDGE-25 lint rule and `CapacityLimiter`'s no-double-borrow-per-borrower rule. Do not build this.

**Planner note:** ARCHITECTURE.md's phrase *"a connection you hold already owns a token"* must be read as
"owns a **checkout slot**," NOT a retained limiter token. Correct that wording when planning to avoid
nudging the executor toward the deadlock-prone Option B. Accepted nuance: the checkout offload shares the
one limiter with query offloads, so under a flood a fresh `connect()` may wait on the limiter even when a
pool slot is free — progress-bounded, not a deadlock; EDGE-12's counter watches `execute` only, so the
asserted bound is unaffected.

### D-24-02 — EDGE-09 (token borrowed-then-released ×N) is SPLIT across Phase 24 / Phase 25
**Decision:**
- **Phase 24 owns, fully green:** EDGE-09 **success** + **error** legs (token returns to
  `borrowed_tokens == 0` after a normal return and after an `AdbcError`), and **EDGE-10** in full
  (cancel while *queued waiting to acquire* a token on a saturated limiter — no worker ever starts, no
  driver is touched, no `adbc_cancel` needed; pure async-layer behaviour).
- **Phase 25 owns:** EDGE-09's **cancel-mid-block** leg, riding on EDGE-02's `adbc_cancel` / join /
  invalidate wiring, tested against the real `abandon_on_cancel=False` production offload.

**Why:** `to_thread.run_sync` is shielded-from-cancel by default, so an honest "token released after a
cancel landed mid-execute" test *requires* the `adbc_cancel` wiring to unblock the worker — that wiring
is Phase 25. Forcing the cancel leg into Phase 24 would mean either an `abandon_on_cancel=True` probe
(does not reflect the `abandon_on_cancel=False` production path → low-fidelity) or pulling cancel
machinery forward. The token-accounting invariant for every path that does NOT need driver cancel is
delivered in Phase 24; the cancel leg is re-verified in Phase 25 where it can be honest.

### D-24-03 — Connection aliasing policy: REJECT with a clear typed error (NOT a per-connection lock)
**Decision:** Two tasks concurrently using one `AsyncConnection`/`AsyncCursor` is **rejected** with a
clear, typed library error — there is **no** per-connection `anyio.Lock` and no silent serialization.
Each `AsyncConnection` carries a cheap `_in_use` flag set around each offload; a second concurrent entry
raises the typed error immediately.

- **New exception:** `ConnectionBusyError(PoolhouseError)` (final name at the planner's discretion, but it
  MUST inherit `PoolhouseError` and be exported). Suggested message: *"This connection is already
  executing in another task; an ADBC connection allows serialized but not concurrent access. Check out a
  separate connection per task."*
- **EDGE-15** is satisfied by its own permissive form ("serialized **OR** a clear typed error"): assert
  the second concurrent caller raises `ConnectionBusyError`, no concurrency-violation flag is set, and
  `checkedout()` stays correct.
- **EDGE-16 is dropped** — it was conditional on the lock shipping. No lock → no "cancel must bypass the
  lock" deadlock surface to design around. (Remove/mark N/A when planning Phase 25.)

**Why reject over lock (full rationale):**
1. **Aliasing has no legitimate use case** — concurrent use of one connection is forbidden by ADBC. A
   loud failure surfaces the bug; a lock hides it.
2. **A per-call lock gives false comfort** — ADBC's serialization unit is the *individual C call*, not a
   transaction. A lock prevents the *crash* but still lets two tasks' statements interleave inside one
   open transaction (driver-safe, semantically garbage). Partial safety that reads as full safety.
3. **Symmetry with the sync pool** — verified in source (SQLAlchemy 2.0.49): the sync `QueuePool` has
   **no** per-connection lock. Its locks (`_pool` Queue, `_overflow_lock`) guard pool bookkeeping only;
   `_ConnectionFairy.cursor()` is a bare passthrough. Sync correctness comes from the
   **connection-per-thread** convention (single ownership), NOT from the GIL — the GIL is *released*
   during the `execute` C call, so it never serialised concurrent calls on a shared connection. Async is
   exactly symmetric: correctness from **connection-per-task** ownership; aliasing breaks it identically,
   the offload just makes "two concurrent C calls" literal via two worker threads.
4. **Precedent** — SQLAlchemy's own async connection/session *raises* on concurrent use rather than
   serialising. Async DB users already expect "connection in use → error."
5. The one async-specific concern (aliasing is *easier* to trip into accidentally via task groups /
   captured closures, and the failure is nastier) justifies a *defensive* loud error — not a behavioural
   serialization contract the sync side never offered.

**ROADMAP reconciliation — DONE (2026-06-27):** Phase 24 criterion #4 reworded from "serialize cleanly"
to "rejected with a clear typed error (`ConnectionBusyError`) — never silently serialized"; criterion #3
adjusted for the D-24-02 EDGE-09 split; `REQUIREMENTS.md` EDGE-15 tightened to the reject form; EDGE-16
marked N/A/dropped (no lock ships). (ACONN-03 is unrelated — it covers `cursor()` returning
synchronously, not aliasing; the aliasing requirement is EDGE-15.)

### D-24-04 — "Any of the 13 backends" is verified by STRUCTURAL genericity, not 13 live runs
**Decision:** The "13 backends" claim (Goal + criterion #5) is satisfied by:
- **Genericity (the binding part):** zero backend-specific code in `_async/` — the wrappers touch only the
  `WarehouseConfig` Protocol and the sync `QueuePool`. Proved by construction **plus a static check**
  (lint/AST/grep asserting no backend names or per-backend branching in `_async/`).
- **Real-driver smoke as the backend-generic leg:** DuckDB (real in-proc driver — required anyway for
  EDGE-21's real `pyarrow.Table` and the Arrow-lifetime/leak path) + the Snowflake `pytest-adbc-replay`
  cassette (driver-agnostic path without live creds).

The remaining 11 backends inherit coverage transitively via the Protocol + the existing sync suite.
**NOT in scope:** spinning up all 13 live drivers in this phase. (A live multi-backend smoke matrix, if
ever wanted, is a separate, flakier phase needing CI infra — note it as deferred, don't silently imply
it's covered.)

## User-Facing Documentation Requirement (for the docs gate)

The async guide MUST document the forbidden aliasing antipattern (drives D-24-03). Canonical wording for
the docs-author to adapt:

> **Do not share one async connection across concurrent tasks.** An ADBC connection permits *serialized*
> access (one call at a time) but **not concurrent** access. Each `AsyncConnection` belongs to exactly one
> task for its lifetime — check out a separate connection per task from the pool.
>
> ```python
> # ❌ FORBIDDEN — aliasing one connection across tasks
> async with await pool.connect() as conn:
>     cur = conn.cursor()
>     async with anyio.create_task_group() as tg:
>         tg.start_soon(run_query, cur)   # task A
>         tg.start_soon(run_query, cur)   # task B — concurrent use of the SAME connection
> # raises ConnectionBusyError: the second concurrent call is rejected
>
> # ✅ CORRECT — one connection per task
> async def worker(pool):
>     async with await pool.connect() as conn:   # each task checks out its own
>         cur = conn.cursor()
>         await cur.execute("SELECT 1")
>
> async with anyio.create_task_group() as tg:
>     tg.start_soon(worker, pool)
>     tg.start_soon(worker, pool)
> ```
>
> Why a hard error and not silent queuing: serialising the calls would still let two tasks' statements
> interleave inside one transaction (driver-safe, logically corrupt), and it hides a real bug. Failing
> loudly is the safe, debuggable behaviour. (The sync pool relies on the same connection-per-*thread*
> convention; the async layer simply enforces it with a clear error because task-group aliasing is easier
> to do by accident.)

## Implementation Decisions (carry-forward from Phase 23)

### Harness contract status (what Phase 24 inherits)
- **The Phase 23 stub/gating HARD CONTRACT (D-04/D-05) is the verified-green baseline**
  PLUS one additive change: `run_blocking(..., abandon_on_cancel: bool = False)` (WR-04).
  Default-false = non-cancellable offload; pass `True` for timeout EDGE cases.
- **`run_blocking` is NON-cancellable by default** (the worker is only unblocked by the
  test releasing/cancelling the stub). The timeout/cancel EDGE cases (Phase 25) that
  rely on `fail_after`/cancellation must pass `abandon_on_cancel=True` OR poke the stub.

### `entered`-timing redesign (REQUIRED before reusing the harness for concurrency assertions)
- **D-CF-01:** The loop-facing `entered` anyio.Event is signalled when the worker
  STARTS, *before* it enters the stub's lock-guarded blocked section. So `await
  entered` does NOT mean "the worker is inside execute." Asserting a stub invariant
  the instant `entered` fires races the worker, and — because the offload is
  non-cancellable — a missed assert **deadlocks the task group**. This caused a ~33%
  flaky deadlock in Phase 23 (fixed in `tests/_async_harness/test_harness.py`,
  commit `943c074`). Phase 24 EDGE tests MUST either: (a) reuse the `_await_inside`
  bounded-`sleep(0)` poll pattern after `await entered` and always release in a
  `finally`; OR (b) redesign `entered` to fire AFTER the worker is inside the blocked
  section (e.g. an `on_enter` callback the stub invokes inside `_block`, bridged to
  the anyio event), so `await entered` becomes a true "inside execute" signal.

### Deferred Phase 23 review findings to (re)consider here
- **WR-01 — re-armable cursor gate.** Phase 24 does `execute` then `fetch_arrow_table`
  on ONE cursor, so the stub gate must re-arm per blocking call. The Phase 23 auto-fix
  attempt deadlocked (it didn't coordinate with the `entered`-before-block timing) and
  was reverted. Implement re-arm together with the D-CF-01 `entered` redesign.
- **WR-02 — connection→cursor cancel/close propagation.** `BlockingStubConnection.close`/
  `adbc_cancel` are recording-only; add opt-in propagation (`propagate=True`) if an EDGE
  case (EDGE-09..12/15/18) needs connection-teardown to unblock cursor workers.
- **WR-03 — set `observed_cancel`/`closed` under the counter's lock** so a loop-thread
  reader of the cancel path can't observe a torn `(count, flag)` pair.
- **IN-03 — promote the stub's `_closed` to a documented public `closed` attribute** if
  consumers need to observe terminal close state.
- **IN-04 — keep the max-concurrent self-test deterministic** via the poll pattern above.

### Claude's Discretion
- The four load-bearing decisions (D-24-01..04) are locked above. Everything else about the wrapper
  design — method-by-method offload structure, the `_in_use` flag mechanics, exact exception name/message,
  overload shapes, file-internal helpers — is Claude's discretion within ARCHITECTURE.md's wrap-and-offload
  pattern and the Phase 23 harness contract.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/phases/23-test-harness-foundation/23-REVIEW-FIX.md` — what was fixed vs
  reverted/deferred in the Phase 23 review, with commit hashes.
- `.planning/phases/23-test-harness-foundation/23-REVIEW.md` — the full WR-01..04 / IN-01..04 findings.
- `tests/_async_harness/test_harness.py` — the `_await_inside` poll pattern (commit `943c074`).
- `tests/_async_harness/{stubs,gating}.py` — the current HARD CONTRACT surface.
- `.planning/research/ASYNC-EDGE-CASES.md` — the EDGE-NN designs Phase 24/25 implement.
</canonical_refs>

<deferred>
## Deferred Ideas

- None specific to this seed. (This whole file IS the carry-forward; discuss-phase adds Phase 24's own scope.)
</deferred>

---

*Phase: 24-core-async-wrapper*
*Carry-forward seed written 2026-06-27 from the Phase 23 review; extended 2026-06-27 with the four locked
design decisions (D-24-01..04) from the discuss-phase session.*
