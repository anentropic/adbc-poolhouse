# Phase 24: Core Async Wrapper - Context

**Gathered:** 2026-06-27 (carry-forward seed)
**Status:** SEED — carry-forward only; NOT a complete context. Run `/gsd-discuss-phase 24` to complete it.
**Source:** Phase 23 code review + deferred fixes (`23-REVIEW-FIX.md`)

<domain>
## Phase Boundary

This is a **partial, pre-seeded** context capturing items deferred from the Phase 23
harness review so they are not lost. It does NOT yet cover Phase 24's own scope
(the `AsyncPool`/`AsyncConnection`/`AsyncCursor` surface, offload helper, per-pool
limiter, etc. — see ROADMAP Phase 24). `/gsd-discuss-phase 24` should extend this.
</domain>

<decisions>
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
- Everything else about Phase 24's actual wrapper design — to be filled in by discuss-phase.
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
*Carry-forward seed written 2026-06-27 from the Phase 23 review; complete via /gsd-discuss-phase 24.*
