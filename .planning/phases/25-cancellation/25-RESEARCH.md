# Phase 25: Cancellation - Research

**Researched:** 2026-06-28
**Domain:** Cooperative cancellation of a non-interruptible thread-offload under anyio (asyncio + trio), driver-thread-safe `adbc_cancel`, invalidate-on-poison, shielded cleanup, `ExceptionGroup`/`except*` discipline
**Confidence:** HIGH

> **Read order for the planner.** This phase's `25-CONTEXT.md` is unusually strong: the discuss-phase session did real anyio/ADBC research plus a live DuckDB driver probe, and its decisions D-25-01..08 and Research Grounding are AUTHORITATIVE. This RESEARCH does not re-derive them. It (1) **verifies the four load-bearing anyio semantics in this session's live venv** (anyio 4.14.1, Python 3.14, trio 0.33.0) — especially the `ExceptionGroup` collapse behaviour that D-25-05 hinges on, (2) gives the planner a concrete `cancellable_offload` + `except*` recipe, (3) enumerates the observable signals and loop strategy for the Validation Architecture, and (4) maps every EDGE leg to a deterministic stub-harness driver. Where this RESEARCH and CONTEXT agree, CONTEXT wins on intent; this document adds the verified mechanics.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-25-01 — Cooperative cancel via a watcher task; `adbc_cancel()` is called from the loop thread.** A blocked worker cannot be interrupted by anyio directly. The only abort path is the driver's thread-safe `adbc_cancel()`, fired from a concurrent watcher task that receives the framework cancellation. Query/fetch methods route through a single `cancellable_offload` helper (task group: `_watcher` parks on `await done.wait()`, `_worker` runs the offload with `abandon_on_cancel=False` and `done.set()`s in `finally`; on cancel the watcher sets `cancelled_by_us`, fires `adbc_cancel()` inside `CancelScope(shield=True)`, and re-raises). This is the minimal correct structure — anyio offers no built-in interruptible offload. The offload stays `abandon_on_cancel=False` so the worker is always joined.

**D-25-02 — Distinguish "we cancelled it" by an explicit flag, NOT by exception type.** The probe showed a cancelled DuckDB `execute()` raises a plain `ProgrammingError("...INTERRUPT Error: Interrupted!")` — an ordinary `Error` subclass, not a dedicated cancelled type. The wrapper carries a `cancelled_by_us` flag (set when the watcher fires `adbc_cancel`). Sniffing exception type or message is NOT portable across the 13 backends and is BANNED.

**D-25-03 — Invalidate-on-cancel via `fairy.invalidate()`, offloaded and shielded.** A cancelled connection is genuinely poisoned ("Current transaction is aborted" on reuse), so it MUST be invalidated, never returned. `_ConnectionFairy.invalidate()` alone drives `pool.checkedout()` to 0; a following `close()` is a safe no-op. Cleanup: offload `fairy.invalidate()` inside `anyio.CancelScope(shield=True)`. `AsyncConnection` gains an `invalidate()` method.

**D-25-05 — `ExceptionGroup` / `except*` handling: cancellation wins, real ADBC errors preserved (EDGE-19/EDGE-03).** On the cancel path the worker's interrupt error and the watcher's `Cancelled` arrive together and the task group bundles them. The wrapper must (a) let the framework cancellation propagate so the caller's `fail_after`/`scope.cancel()` sees its expected exception type, (b) swallow the interrupt error when `cancelled_by_us` is set so the user never sees a spurious "Interrupted!", and (c) on the NON-cancel path, preserve a genuine `AdbcError` unchanged (Phase 24 EDGE-17 contract). The single subtlest part of the phase.

**D-25-06 — `get_cancelled_exc_class()` only; no `asyncio.CancelledError` in `_async/` (EDGE-28).** All cancel detection uses `anyio.get_cancelled_exc_class()`; the caught cancellation is always re-raised, never swallowed. Extend the Phase 23 `scan_async_package` AST guard to assert no `asyncio.CancelledError` reference appears anywhere in `_async/`.

**D-25-07 — Idempotent double-cancel during shielded cleanup (CANCEL-03/EDGE-04/EDGE-05).** A second cancellation arriving while the shielded cleanup runs must be a no-op against the cleanup: exactly one `adbc_cancel`, one `invalidate`, one surfaced cancel exception. The shield around the cleanup is what makes this hold; assert the counts explicitly.

**D-25-04 — Only the query/fetch methods opt in; check-in opts out; the rest have no offload.**
- **Cancellable (watcher machinery):** `AsyncCursor.execute`, `executemany`, `fetch_arrow_table`, `fetchone`/`fetchmany`/`fetchall`.
- **Shielded, deliberately NOT cancellable:** `AsyncConnection.close`/`__aexit__`/`AsyncCursor.close` — already `CancelScope(shield=True)` in Phase 24. Check-in must complete.
- **No offload at all:** `cursor()`, `description`, `rowcount`, `arraysize` (synchronous).
- **`commit`/`rollback`: NOT made cancellable in this phase** — they stay plain offloads.

### Claude's Discretion

- **D-25-08 — Helper placement.** Recommended: a new `src/adbc_poolhouse/_async/_cancel.py` housing `cancellable_offload`, leaving `_offload.py` as the un-aliased `to_thread.run_sync` chokepoint the AST guard matches. Folding into `_offload.py` is acceptable if it keeps the chokepoint literal intact. Planner decides.
- Exact wiring of `cancelled_by_us` and the `ExceptionGroup` unwrap (`except*` block vs catch + filter) — planner's call, as long as D-25-05's three guarantees hold.

### Deferred Ideas (OUT OF SCOPE)

- **`commit`/`rollback` cancellation** — out of scope (D-25-04); revisit only if a requirement appears.
- **Streaming `RecordBatchReader` results** — v1.4.x; `fetch_arrow_table` stays fully materialized.
- **The `[async]` extra / PEP 562 lazy import / strict typing** — Phase 26.
- **Live dual-backend matrix (DuckDB + Snowflake cassette, asyncio + trio)** — Phase 27. Phase 25 proves correctness on the stub harness + DuckDB.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CANCEL-01 | On cancel/timeout of `execute`/`fetch_arrow_table`, `cursor.adbc_cancel()` is invoked from the loop thread to abort the in-flight C call | `cancellable_offload` watcher fires `adbc_cancel()` inside `CancelScope(shield=True)` in its `except get_cancelled_exc_class()` branch (D-25-01); verified anyio task-group cancel semantics below |
| CANCEL-02 | A cancelled connection is invalidated, not returned busy; `pool.checkedout() == 0` after a cancelled scope | `AsyncConnection.invalidate()` offloads `fairy.invalidate()` shielded; probe confirmed `invalidate()` drives `checkedout()` 1→0 (D-25-03). `PoolProxiedConnection.invalidate` verified present in venv |
| CANCEL-03 | `__aexit__` cleanup wrapped in `CancelScope(shield=True)` so the connection always returns/invalidates even cancelled mid-cleanup | Shield already shipped in Phase 24 for `close`/`__aexit__`; Phase 25 adds the invalidate path + idempotency under it (D-25-07) |
| CANCEL-04 | Deterministic cancellation tests prove no-leak under asyncio AND trio | Stub harness + dual-backend `anyio_backend` fixture (asyncio + trio MockClock) already wired; EDGE-29 tuple-equality assertion |
| EDGE-01 | Cancel before offload starts — no `execute`, no `adbc_cancel`, connection clean, cancel propagates | Outer `fail_after`/`cancel()` BEFORE entering `cancellable_offload`; assert stub `execute_call_count == 0`, `adbc_cancel_call_count == 0` |
| EDGE-02 | Cancel during blocked worker — `adbc_cancel` exactly once (shielded), worker joined, connection invalidated, `checkedout()==0`, cancel propagates | Core path; gate worker inside `execute` via `await_inside`, then cancel; assert `adbc_cancel_call_count == 1`, `invalidate` once |
| EDGE-03 | Framework cancel class never swallowed; exact `get_cancelled_exc_class()` instance escapes; no hang under trio | Verified: cancellation collapses to the caller's `TimeoutError`/cancel; watcher re-`raise`s; loop watchdog catches a hang |
| EDGE-04 | Double-cancel during shielded cleanup idempotent — one `adbc_cancel`, one invalidate, one cancel exception | D-25-07; shield makes the cleanup atomic against a second cancel; assert counts |
| EDGE-05 | Cancel during `__aexit__`/checkin still completes checkin under shield — `checkedout()==0` for conn and cursor | Phase 24 shield + invalidate path; cancel mid-`__aexit__`, assert `checkedout()==0` |
| EDGE-06 | `fail_after` timeout and explicit `scope.cancel()` handled identically (both → `adbc_cancel`+invalidate); only surfaced exception type differs | Verified: `fail_after`→`TimeoutError` (both backends), `scope.cancel()`→no surfaced exception; both still cancel the watcher |
| EDGE-07 | `move_on_after` on an already-finished op does nothing — `cancelled_caught` False, no `adbc_cancel`, no invalidate | Release the worker (happy path) before the deadline; assert `adbc_cancel_call_count == 0`, `move_on_after(...).cancelled_caught is False` |
| EDGE-19 | `ExceptionGroup`/`except*` preserves original ADBC errors, keeps cancellation distinguishable, `checkedout()==0` after | Verified: single-member EG unwrap preserves exact type + worker frame; cancel path collapses to cancellation |
| EDGE-28 | Cancel handling uses `get_cancelled_exc_class()` only; no `asyncio.CancelledError` in `_async/` | Extend `scan_async_package` with a `banned-asyncio-cancelled-error` rule (new AST rule) |
| EDGE-29 | The `(adbc_cancel_count, invalidate_count, checkedout_after)` tuple is equal under asyncio and trio | Parametrized EDGE-02 collects the tuple; a meta-assert compares the two legs |
| EDGE-09 (cancel-mid-block leg, from Phase 24 D-24-02) | A limiter token returns to `borrowed_tokens == 0` exactly once on the cancel path (×50 loop) | Transient-token model: `adbc_cancel` unblocks the worker, the offload returns, the token releases; assert `borrowed_tokens == 0` after a cancelled `cancellable_offload` |
</phase_requirements>

## Summary

Phase 25 wires cooperative cancellation onto Phase 24's non-interruptible offload. The mechanism is fully settled in CONTEXT (D-25-01..08) and grounded in the ADBC `cancel` thread-safety carve-out and a live DuckDB probe; the implementation surface is small: a new `cancellable_offload` helper (a two-task anyio task group), an `AsyncConnection.invalidate()` method, rewiring the six cursor query/fetch methods from `offload(...)` to `cancellable_offload(...)` with an invalidate-on-cancel cleanup, one new AST guard rule, and a focused EDGE suite. There is **no new concurrency primitive to invent** — anyio's task group, `Event`, `CancelScope(shield=True)`, and `get_cancelled_exc_class()` do all the work, and the Phase 23 harness (`BlockingStubCursor.adbc_cancel`, `await_inside`, `real_clock_watchdog`, the dual-backend `anyio_backend` fixture) already exposes every signal and gate the tests need.

The one genuinely subtle area is D-25-05, and this session's live probes (anyio 4.14.1 / Python 3.14 / trio 0.33.0) pin down the exact behaviour the planner must design to. **Two verified facts dominate the design:** (1) On the **cancel path**, when the outer scope is cancelled while `cancellable_offload` is parked, anyio collapses the task group's bundled exceptions back into the framework cancellation — the caller sees a clean `TimeoutError` (for `fail_after`, identical on both backends) or nothing (for `scope.cancel()`), and the worker's "Interrupted!" error is swallowed automatically by the cancellation machinery. The wrapper does **not** need to manually filter the interrupt off the cancel path; it needs to re-raise the cancellation (which the watcher already does) and let anyio collapse the group. (2) On the **non-cancel path**, a genuine worker `AdbcError` raised inside the task group comes out wrapped in a single-member `ExceptionGroup` — **NOT bare** — which would break the Phase 24 EDGE-17 contract (`pytest.raises(AdbcError)`) unless the wrapper unwraps it. Unwrapping a single-member group via `except*` (or `eg.exceptions[0]`) preserves the exact type and the off-loop worker frame in the traceback (verified). So the load-bearing wrapper logic is: *run the task group; if it raises an `ExceptionGroup` on the non-cancel path, unwrap and re-raise the inner ADBC error; otherwise let cancellation propagate.*

The highest **execution** risk is not the design — it is test flakiness. This is the milestone's highest-risk correctness item and MEMORY's loop-flaky-concurrency lesson applies directly: a single green run hid a ~33% deadlock in Phase 23. Every cancel test must run in a ×N loop (target 0 hangs), wrapped in the harness's `real_clock_watchdog` (NOT `anyio.fail_after` — under the trio `MockClock(autojump_threshold=0)` a virtual `fail_after` autojumps and trips spuriously the instant every task parks off-loop; this is already solved in `_edge_helpers.py`).

**Primary recommendation:** Implement `cancellable_offload` exactly as D-25-01 sketches; rewire the six cursor methods to call it and drive `self._owner.invalidate()` in their cancel-cleanup; unwrap a single-member `ExceptionGroup` on the non-cancel path to preserve EDGE-17; add the `banned-asyncio-cancelled-error` AST rule; build the EDGE suite on the existing stub harness driving every cancel via `BlockingStubCursor.adbc_cancel` and gating with `await_inside` + `real_clock_watchdog`; run every cancel test in a ×20 loop under both backends and assert the EDGE-29 tuple equality.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Receive framework cancellation while parked on an offload | Async watcher task (`cancellable_offload`) | anyio task group | Only a concurrent loop task can receive the cancel while the worker is blocked off-loop (D-25-01) |
| Abort the in-flight C call | ADBC driver `cursor.adbc_cancel()` | Async watcher (fires it, shielded, from loop thread) | The one thread-safe ADBC op; the documented interrupt path (Research Grounding) |
| Join the abandoned-state-free worker | Async `offload` (`abandon_on_cancel=False`) | — | Worker is always joined, never left in an unknown state (D-25-01) |
| Decide "this driver error is our cancel" | `cancelled_by_us` flag | — | Exception type/message is non-portable across 13 backends (D-25-02) |
| Invalidate the poisoned connection | Sync `_ConnectionFairy.invalidate()` (offloaded, shielded) | `AsyncConnection.invalidate()` | Probe-confirmed sufficient; drives `checkedout()`→0; no bespoke teardown (D-25-03) |
| Keep cleanup atomic vs a second cancel | `anyio.CancelScope(shield=True)` | — | Shield is what makes double-cancel idempotent (D-25-07) |
| Preserve a genuine ADBC error across the task group | `except*`/single-member-EG unwrap | — | Task group wraps a non-cancel worker error in an `ExceptionGroup`; unwrap restores EDGE-17 fidelity (verified) |
| Enforce no `asyncio.CancelledError` in `_async/` | Phase 23 `scan_async_package` (new rule) | — | Static guard; trio neutrality (D-25-06/EDGE-28) |

## Standard Stack

> **No new third-party packages.** Phase 25 uses only already-vetted dependencies, all verified live in the dev venv this session. The cancellation machinery is pure-anyio plus the SQLAlchemy fairy's existing `invalidate()`.

### Core
| Library | Version (verified live) | Purpose | Why Standard |
|---------|-------------------------|---------|--------------|
| `anyio` | `4.14.1` | `create_task_group`, `Event`, `CancelScope(shield=True)`, `get_cancelled_exc_class`, `fail_after`/`move_on_after` | Project-mandated neutrality; the cancel API is the whole mechanism `[VERIFIED: importlib.metadata + live API probe]` |
| `sqlalchemy` | `2.0.49` | `PoolProxiedConnection.invalidate()` — the poison-recovery path | `invalidate` confirmed present on `PoolProxiedConnection`; drives `checkedout()`→0 (CONTEXT probe) `[VERIFIED: dir(PoolProxiedConnection)]` |
| `adbc-driver-manager` | `1.11.0` | `cursor.adbc_cancel()` thread-safe interrupt; `Error` hierarchy | The ADBC `cancel` carve-out is the design linchpin `[VERIFIED: importlib.metadata + Research Grounding]` |
| `pyarrow` | (dev, via `[all]`) | `fetch_arrow_table` return type on the cancellable fetch path | Unchanged from Phase 24 |

### Supporting (test/dev only — all already present)
| Library | Version (verified) | Purpose | When to Use |
|---------|--------------------|---------|-------------|
| `trio` | `0.33.0` | Second anyio backend; `trio.testing.MockClock` virtual clock | Every cancel test, both legs (EDGE-29 tuple equality) `[VERIFIED]` |
| `aiotools` | `2.2.3` | asyncio-leg virtual clock (`VirtualClock().patch_loop()`) | `move_on_after`/`fail_after` deadline tests via `virtual_clock()` `[VERIFIED]` |
| `pytest` + anyio plugin | (existing) | `@pytest.mark.anyio` dual-backend parametrization | All async tests |
| `duckdb` / `adbc-driver-duckdb` | (via `[duckdb]`) | Real-driver cancel smoke (the probe target) | One real-driver leg confirming `adbc_cancel` + invalidate end-to-end |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Watcher task + `adbc_cancel` | `to_thread.run_sync(abandon_on_cancel=True)` | REJECTED (Research Grounding): abandons the worker in an unknown state — the exact poisoning we prevent. The thread keeps running; only its outcome is ignored |
| `cancelled_by_us` flag | Sniffing `ProgrammingError`/`"Interrupted!"` message | REJECTED (D-25-02): non-portable across 13 backends; `ADBC_STATUS_CANCELLED` mapping is driver-specific |
| `fairy.invalidate()` | Bespoke teardown (close + dispose dance) | REJECTED (D-25-03): probe showed `invalidate()` alone is sufficient and `checkedout()`→0; extra teardown is dead code |
| `from_thread.check_cancelled()` polling | (in the worker) | REJECTED (Research Grounding): useless — the worker is blocked in the driver's C call and never reaches a poll point |

**Installation:** No change. `uv sync` already provides anyio/trio/aiotools/duckdb via the dev group.

**Version verification (this session):**
```
anyio 4.14.1 · trio 0.33.0 · sqlalchemy 2.0.49 · aiotools 2.2.3 · adbc_driver_manager 1.11.0 · Python 3.14
PoolProxiedConnection.invalidate → present
anyio.get_cancelled_exc_class → present
```

## Package Legitimacy Audit

> **No new external packages are introduced by Phase 25.** Every library is a pre-existing, vetted dependency whose load-bearing API was verified live this session. The package-legitimacy seam was not re-run because no new third-party package is added.

| Package | Registry | Source Repo | Verdict | Disposition |
|---------|----------|-------------|---------|-------------|
| `anyio` | PyPI | github.com/agronholm/anyio | OK | Approved — cancel API (`get_cancelled_exc_class`, `CancelScope(shield=True)`, task group EG collapse) verified live `[VERIFIED]` |
| `sqlalchemy` | PyPI | github.com/sqlalchemy/sqlalchemy | OK | Approved — `PoolProxiedConnection.invalidate` verified present `[VERIFIED]` |
| `adbc-driver-manager` | PyPI | github.com/apache/arrow-adbc | OK | Approved — `adbc_cancel` thread-safety per upstream C/Java spec (Research Grounding) |
| `trio` / `aiotools` / `pyarrow` / `duckdb` | PyPI | (existing dev deps) | OK | Approved — existing dev deps |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
  await cur.execute(sql)  /  await cur.fetch_arrow_table()
            │
            ▼
  AsyncCursor method
   ├─ owner._enter_offload()          (set _in_use; aliasing guard, Phase 24)
   ├─ try:
   │     result = await cancellable_offload(
   │                   self._cursor.adbc_cancel,      # abort hook (loop-thread, thread-safe)
   │                   self._cursor.<fn>, *args,      # the blocking driver call
   │                   limiter=self._limiter)
   │     ──────────────────────────────────────────────────────────────────────
   │     │  cancellable_offload  (NEW: _async/_cancel.py)
   │     │  ┌───────────────────────────────────────────────────────────────┐
   │     │  │  done = anyio.Event();  cancelled_by_us = False                │
   │     │  │  async with create_task_group() as tg:                         │
   │     │  │    _watcher:  await done.wait()                                │
   │     │  │       except get_cancelled_exc_class():                        │
   │     │  │           cancelled_by_us = True                               │
   │     │  │           with CancelScope(shield=True): adbc_cancel()  ◀──────┼── fires the C-level
   │     │  │           raise                          (exactly once)        │   interrupt; unblocks
   │     │  │    _worker:   try: result = await offload(fn,*args,limiter=)   │   the worker thread
   │     │  │       finally: done.set()   (abandon_on_cancel=False → joined) │
   │     │  └───────────────────────────────────────────────────────────────┘
   │     │     ON CANCEL  → anyio COLLAPSES the bundled (Cancelled + interrupt)
   │     │                  back into the framework cancellation; caller sees
   │     │                  TimeoutError (fail_after) / nothing (scope.cancel)
   │     │     ON ERROR    → task group raises ExceptionGroup([AdbcError]);
   │     │                  wrapper UNWRAPS single member → re-raise bare (EDGE-17/19)
   │     │
   │  except get_cancelled_exc_class():                  # cancel cleanup
   │     with CancelScope(shield=True):
   │         await self._owner.invalidate()              # offload fairy.invalidate(), shielded
   │     raise                                            # re-raise the cancellation (never swallow)
   │  finally:
   │     owner._exit_offload()                            # clear _in_use
   │
   ▼
  AsyncConnection.invalidate()   (NEW)
     with CancelScope(shield=True):
         await offload(self._fairy.invalidate, limiter=self._limiter)
            │
            ▼
     sync QueuePool: checkedout() 1 → 0   (poisoned conn dropped, pool stays healthy)
```

Trace of the cancel use case (EDGE-02): `await cur.execute()` parks on the offload → outer `fail_after` fires → watcher receives `Cancelled`, sets `cancelled_by_us`, fires `adbc_cancel()` shielded (worker unblocks, offload returns/raises, token releases, worker joined) → watcher re-raises → task group + outer scope collapse to `TimeoutError` → cursor method's `except get_cancelled_exc_class()` invalidates the connection (shielded) and re-raises → `checkedout()==0`, `adbc_cancel_call_count==1`, `invalidate` once.

### Recommended Project Structure
```
src/adbc_poolhouse/_async/
├── _offload.py          # UNCHANGED literal to_thread.run_sync chokepoint (AST guard target)
├── _cancel.py           # NEW (D-25-08 recommended): cancellable_offload(adbc_cancel, fn, *args, limiter)
├── _connection.py       # MOD: add invalidate(); close/__aexit__ already shielded
└── _cursor.py           # MOD: execute/executemany/fetch* route through cancellable_offload + invalidate-on-cancel
tests/_async_harness/
└── guard.py             # MOD: add `banned-asyncio-cancelled-error` AST rule (EDGE-28)
tests/async/
├── test_edge_cancel_depth.py    # NEW: EDGE-01/02/03/04/05/06/07
├── test_edge_exceptiongroup.py  # NEW: EDGE-19
├── test_edge_backend_parity.py  # NEW: EDGE-29 tuple equality
├── test_edge_limiter.py         # MOD: add EDGE-09 cancel-mid-block leg (×50)
└── test_async_guard.py          # MOD: assert no asyncio.CancelledError in real _async/ (EDGE-28)
docs/src/guides/async.md         # MOD: cancellation/timeout section (docs gate, phase ≥7)
```

### Pattern 1: `cancellable_offload` — the watcher/worker task group (D-25-01)
**What:** A two-task anyio task group. The worker runs the existing `offload` (so the AST guard's `to_thread.run_sync` chokepoint stays in `_offload.py`, un-aliased); the watcher parks on an `Event` and, only if it receives a cancellation, fires `adbc_cancel()` shielded and re-raises.
**When to use:** Exactly the six cursor query/fetch methods (D-25-04). Never `commit`/`rollback`/`close`/`cursor()`.
```python
# src/adbc_poolhouse/_async/_cancel.py
# Source: CONTEXT D-25-01 (verbatim shape) + live anyio 4.14.1 task-group probe (this session)
from __future__ import annotations
from typing import TYPE_CHECKING, TypeVar
import anyio
from anyio import get_cancelled_exc_class
from adbc_poolhouse._async._offload import offload

if TYPE_CHECKING:
    from collections.abc import Callable
    from anyio import CapacityLimiter

_T = TypeVar("_T")

async def cancellable_offload(
    adbc_cancel: Callable[[], None],
    fn: Callable[..., _T],
    *args: object,
    limiter: CapacityLimiter,
) -> _T:
    done = anyio.Event()
    result: dict[str, _T] = {}
    cancelled_by_us = False

    async def _watcher() -> None:
        nonlocal cancelled_by_us
        try:
            await done.wait()                    # event-driven park, NOT a poll
        except get_cancelled_exc_class():
            cancelled_by_us = True
            with anyio.CancelScope(shield=True):
                adbc_cancel()                    # thread-safe; unblocks the worker, fires ONCE
            raise                                # never swallow the cancellation (D-25-06)

    async def _worker() -> None:
        try:
            result["v"] = await offload(fn, *args, limiter=limiter)  # abandon_on_cancel=False
        finally:
            done.set()                           # release the watcher on the success/error path

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(_watcher)
            tg.start_soon(_worker)
    except BaseExceptionGroup as eg:             # NON-cancel path: worker raised a real error
        # The task group wraps a lone worker AdbcError in a single-member group.
        # Unwrap to preserve the exact type + worker frame (EDGE-17/EDGE-19). If our
        # own cancel produced the interrupt, anyio has already collapsed the cancel
        # path before reaching here, so a group that arrives here is a GENUINE error.
        if len(eg.exceptions) == 1:
            raise eg.exceptions[0] from None
        raise
    return result["v"]
```
> **Verified semantics (this session, anyio 4.14.1 / Py 3.14):**
> - **Cancel path:** outer `fail_after` while parked → caller sees a clean `TimeoutError` (the worker's "Interrupted!" is swallowed by anyio's cancel collapse). The `except BaseExceptionGroup` branch is **not** reached on the cancel path. `[VERIFIED: probe A]`
> - **Non-cancel path:** a lone worker `ValueError`/`AdbcError` arrives as `ExceptionGroup([err])` — bare unwrap restores it. `[VERIFIED: probe C]`
> - **Unwrap fidelity:** `eg.exceptions[0]` keeps the exact type and the off-loop worker frame in `__traceback__`. `[VERIFIED: probe E]`

### Pattern 2: Cursor method rewiring + invalidate-on-cancel (CANCEL-01/02, EDGE-02)
**What:** Each of the six cursor methods swaps `await offload(...)` for `await cancellable_offload(self._cursor.adbc_cancel, ...)`, and adds an `except get_cancelled_exc_class()` cleanup that invalidates the owning connection (shielded) and re-raises. The Phase 24 `_enter_offload`/`_exit_offload` guard stays.
```python
# src/adbc_poolhouse/_async/_cursor.py (execute shown; same shape for the other five)
# Source: CONTEXT D-25-01/03/06 + Phase 24 _cursor.py structure
async def execute(self, operation: str, parameters: object = None) -> None:
    self._owner._enter_offload()  # noqa: SLF001
    try:
        await cancellable_offload(
            self._cursor.adbc_cancel,
            self._cursor.execute,
            operation,
            parameters,
            limiter=self._limiter,
        )
    except get_cancelled_exc_class():
        with anyio.CancelScope(shield=True):
            await self._owner.invalidate()   # poison recovery (D-25-03)
        raise                                # re-raise cancellation, never swallow
    finally:
        self._owner._exit_offload()  # noqa: SLF001
```
> **Why invalidate lives in the cursor method, not in `cancellable_offload`:** `cancellable_offload` is connection-agnostic (it only knows the `adbc_cancel` callable and the blocking `fn`). The owning `AsyncConnection` is what must be invalidated, and only the cursor method holds that reference. Keeping `cancellable_offload` free of connection state also keeps it reusable and unit-testable in isolation.

### Pattern 3: `AsyncConnection.invalidate()` (D-25-03, CANCEL-02)
**What:** A new public method that offloads `fairy.invalidate()` inside a shield. Mirrors the existing shielded `close()`.
```python
# src/adbc_poolhouse/_async/_connection.py (NEW method)
# Source: CONTEXT D-25-03 + verified PoolProxiedConnection.invalidate
async def invalidate(self) -> None:
    """Drop a poisoned connection from the pool (offloaded, shielded)."""
    with anyio.CancelScope(shield=True):
        await offload(self._fairy.invalidate, limiter=self._limiter)
```
> Bypasses the `_in_use` guard for the same reason `__aexit__` does (Phase 24): a connection left marked busy by a cancelled in-flight call must still be reclaimable. The shield makes a second cancel arriving here a no-op (D-25-07 idempotency).

### Pattern 4: The new AST guard rule — no `asyncio.CancelledError` (EDGE-28, D-25-06)
**What:** Extend `_GuardVisitor` in `tests/_async_harness/guard.py` with a rule that flags any reference to `asyncio.CancelledError`. The existing `banned-asyncio-import` rule already catches `import asyncio`, but EDGE-28 wants the explicit *name* banned too (defence in depth, and to document intent).
```python
# tests/_async_harness/guard.py — new visit_Attribute on _GuardVisitor
def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
    # Flag `asyncio.CancelledError` (e.g. `except asyncio.CancelledError`).
    if node.attr == "CancelledError" and isinstance(node.value, ast.Name) and node.value.id == "asyncio":
        self.findings.append(Finding(self.path, node.lineno,
            "banned-asyncio-cancelled-error",
            "`asyncio.CancelledError` is banned in _async/; use anyio.get_cancelled_exc_class()"))
    self.generic_visit(node)
```
> Since `import asyncio` is already banned, a bare `CancelledError` reference would require a `from asyncio import CancelledError` — already caught by `visit_ImportFrom`. The new attribute rule covers the `asyncio.CancelledError` attribute-chain form for completeness and makes the EDGE-28 intent explicit and self-documenting. The EDGE-28 meta-test asserts `scan_async_package("src/adbc_poolhouse/_async/") == []`.

### Anti-Patterns to Avoid
- **Manually filtering the "Interrupted!" error off the cancel path.** Unnecessary and fragile — anyio's cancel collapse already swallows the worker error when the scope is cancelled. Sniffing the message to swallow it is the D-25-02-banned approach. Just re-raise the cancellation and let anyio collapse the group.
- **Returning the bare `ExceptionGroup` to the caller on the non-cancel path.** Breaks EDGE-17 (`pytest.raises(AdbcError)`). Always unwrap a single-member group.
- **`adbc_cancel()` on the success path.** The `done` event releases the watcher normally when the worker finishes; `adbc_cancel` only ever runs in the watcher's `except` branch (CONTEXT Specific Ideas). A success-path cancel would corrupt a completed result and inflate `adbc_cancel_call_count`.
- **Firing `adbc_cancel()` un-shielded.** A cancellation landing during the cancel itself could abort the abort. Wrap it in `CancelScope(shield=True)` (D-25-01).
- **Swallowing the framework cancellation.** Always `raise` after the cancel cleanup (D-25-06). Swallowing it hangs the caller's `fail_after` or breaks structured cancellation under trio.
- **Aliasing `to_thread.run_sync` into `_cancel.py`.** Keep the literal chokepoint in `_offload.py` only; `cancellable_offload` calls `offload`, never `to_thread.run_sync` directly (D-25-08 / Phase 24 Pitfall 5).
- **`anyio.fail_after` as the test watchdog.** Under the trio `MockClock(autojump_threshold=0)` it autojumps to its own deadline the instant tasks park and trips every run. Use the harness `real_clock_watchdog` (already built for exactly this).
- **Making `commit`/`rollback` cancellable.** Out of scope (D-25-04); they stay plain `offload`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Interrupt a blocked worker | A polling `from_thread.check_cancelled()` loop / a kill-thread hack | `adbc_cancel()` from the watcher | The worker is blocked in C and never polls; `adbc_cancel` is the one thread-safe abort (Research Grounding) |
| Recover a poisoned connection | A custom close+dispose+rebuild dance | `fairy.invalidate()` (offloaded, shielded) | Probe-confirmed sufficient; `checkedout()`→0; pool stays healthy (D-25-03) |
| Detect "our cancel" | Parse the driver error message | The `cancelled_by_us` flag | Message/type non-portable across 13 backends (D-25-02) |
| Make double-cancel idempotent | A manual "already cancelled" bool + lock | `CancelScope(shield=True)` around cleanup | The shield makes the cleanup atomic against a second cancel (D-25-07) |
| Distinguish cancel vs real error | Type/message sniffing | `cancelled_by_us` flag + anyio's automatic cancel collapse + single-member EG unwrap | anyio collapses cancel; the group only wraps genuine errors (verified) |
| Deterministic cancel timing in tests | `sleep`-based timing | `await_inside` (worker-inside poll) + `BlockingStubCursor.adbc_cancel` + `virtual_clock` | Already built (Phase 23/24); no wall-clock, no flake (EDGE-30 honored early) |
| A no-hang test watchdog | `anyio.fail_after` | `real_clock_watchdog` from `_edge_helpers.py` | `fail_after` autojumps under trio MockClock and trips spuriously |

**Key insight:** Like Phase 24, this phase's correctness is almost entirely *reuse* — anyio's task group + shield + `get_cancelled_exc_class`, the SQLAlchemy fairy's `invalidate()`, and the Phase 23 harness's `adbc_cancel`/`await_inside`/`real_clock_watchdog`. The only genuinely new code is the thin `cancellable_offload` glue, the `invalidate()` method, one AST rule, and the EDGE tests. Resist inventing any cancel primitive.

## Runtime State Inventory

> Phase 25 is a **greenfield code addition** to the new `_async/` package (one new helper module, one new method, one new AST guard rule, new tests, a docs section). It renames/migrates no existing runtime state. The five categories are answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore key/collection/ID is renamed or migrated. The cancel path invalidates a live pooled connection at runtime; it persists nothing. | None |
| Live service config | None — no external service (n8n, Datadog, Tailscale, etc.) references this code. | None |
| OS-registered state | None — no Task Scheduler / launchd / pm2 / systemd registration involved. | None |
| Secrets/env vars | None — no secret keys or env var names added or renamed. | None |
| Build artifacts / installed packages | No new package. `mkdocs` site rebuild needed for the new `AsyncConnection.invalidate` docstring + the cancellation guide section (docs gate). No `pyproject.toml` change (the `[async]` extra is Phase 26). | `.venv/bin/mkdocs build --strict` |

**Nothing found in the rename-sensitive categories** — verified: this phase adds a module, a method, a guard rule, and tests; it moves/renames no existing symbol, datastore key, or registration.

## Common Pitfalls

### Pitfall 1: Returning the wrapped `ExceptionGroup` on the non-cancel path (breaks EDGE-17)
**What goes wrong:** A genuine `AdbcError` raised by the worker exits the task group as `ExceptionGroup([AdbcError])`. Tests and callers doing `pytest.raises(AdbcError)` / `except AdbcError` miss it; EDGE-17 (already green from Phase 24) regresses.
**Why it happens:** anyio task groups bundle child-task exceptions into an `ExceptionGroup` even for a single member. `[VERIFIED: probe C — lone ValueError → ExceptionGroup]`
**How to avoid:** Catch `BaseExceptionGroup` from the task group and, when it has exactly one member, `raise eg.exceptions[0] from None`. This preserves the exact type AND the off-loop worker frame in the traceback `[VERIFIED: probe E]`.
**Warning signs:** EDGE-17 starts failing after the rewire; a caller's `except AdbcError` no longer fires; a test sees `ExceptionGroup` where it expected `ProgrammingError`.

### Pitfall 2: Single-shot cancel test "passes" but deadlocks ~1-in-3 (the MEMORY lesson)
**What goes wrong:** A cancel test passes once in the closeout run, then hangs intermittently in CI.
**Why it happens:** `abandon_on_cancel=False` means a missed `adbc_cancel`/`release` strands a non-cancellable worker; the task group then blocks forever at scope exit. Scheduling is nondeterministic, so a single green run got lucky. `[VERIFIED: MEMORY feedback_loop_test_flaky_concurrency; Phase 23 ~33% deadlock]`
**How to avoid:** Run every cancel/concurrency test in a ×N loop (target 20, 0 hangs), under BOTH backends. Wrap every test body in `real_clock_watchdog([stub_cursors])` so a stranded worker is force-released and the assertion trips fast instead of hanging. Honor the zsh `!` gotcha (MEMORY): use `rc=$?` + grep the pass line, never `if ! pytest` in the loop.
**Warning signs:** A cancel test green in isolation, hung under `-q` full-suite ordering; `real_clock_watchdog` tripping (`tripped[0] is True`).

### Pitfall 3: `anyio.fail_after` as the test watchdog autojumps under trio MockClock
**What goes wrong:** A `fail_after`-wrapped cancel test trips its own watchdog the instant every task parks off-loop on the trio leg, failing every run.
**Why it happens:** `trio.testing.MockClock(autojump_threshold=0)` (injected by the `anyio_backend` fixture) advances virtual time to the next deadline as soon as all tasks are blocked; a virtual `fail_after` watchdog is that next deadline. `[VERIFIED: _edge_helpers.py docstring; Phase 24 Plan 01 lesson]`
**How to avoid:** Use `real_clock_watchdog` (wall-clock side thread that `close()`s the stub) for "no test hangs"; use `virtual_clock()` + `anyio.fail_after`/`move_on_after` ONLY as the *cancellation trigger under test* (EDGE-06/07), never as the safety net.
**Warning signs:** Trio leg fails 100% with the watchdog tripping; asyncio leg passes.

### Pitfall 4: Firing `adbc_cancel` on the success path / more than once
**What goes wrong:** `adbc_cancel_call_count` is 2 (or 1 on a happy path), inflating EDGE-02/04/07 assertions and potentially corrupting a completed result.
**Why it happens:** Putting `adbc_cancel()` outside the watcher's `except` branch, or not relying on `done.set()` to release the watcher cleanly on success.
**How to avoid:** `adbc_cancel()` lives ONLY in `_watcher`'s `except get_cancelled_exc_class()` branch; the success/error path releases the watcher via `done.set()` so it never enters the except. The shield ensures the cancel fires exactly once even if a second cancel lands (D-25-07).
**Warning signs:** EDGE-07 (`move_on_after` on a finished op) sees `adbc_cancel_call_count == 1`; EDGE-04 sees `== 2`.

### Pitfall 5: Swallowing the framework cancellation (hangs the caller / breaks trio)
**What goes wrong:** The caller's `fail_after` never sees its `TimeoutError`; under trio, structured cancellation is left dangling and the test hangs.
**Why it happens:** The cursor method's `except get_cancelled_exc_class()` cleanup forgets to `raise` after invalidating, swallowing the cancel.
**How to avoid:** Always `raise` at the end of the cancel-cleanup branch (D-25-06). The cleanup (invalidate) is shielded; the re-raise is mandatory.
**Warning signs:** A cancel test hangs at the outer `fail_after`; `cancelled_caught` unexpectedly False; EDGE-03 fails.

### Pitfall 6: Invalidating on a non-cancel error path
**What goes wrong:** A connection is invalidated after a *genuine* `AdbcError` (e.g. a bad query) that did NOT cancel — over-invalidating healthy-but-errored connections and breaking EDGE-18's "errored connection still returns to the pool" contract.
**Why it happens:** Catching too broadly (`except Exception`) instead of `except get_cancelled_exc_class()` for the invalidate branch.
**How to avoid:** Invalidate ONLY in the `except get_cancelled_exc_class()` branch. A genuine `AdbcError` (unwrapped from the group) propagates normally and the Phase 24 `__aexit__` returns the connection via the reset path. `[Phase 24 EDGE-18 contract]`
**Warning signs:** EDGE-18 regresses; `invalidate_count` > 0 on a bad-query test that never cancelled.

## Code Examples

### EDGE-02: cancel during the blocked worker (core path, stub harness)
```python
# tests/async/test_edge_cancel_depth.py
# Source: CONTEXT D-25-01/03 + Phase 24 _edge_helpers (await_inside, real_clock_watchdog)
import anyio, pytest
from tests.async._edge_helpers import await_inside, real_clock_watchdog

@pytest.mark.anyio
async def test_cancel_during_block_invalidates(make_stub_async_connection, anyio_backend_name):
    async_conn, stub_conn = make_stub_async_connection()
    cur = async_conn.cursor()
    stub_cursor = stub_conn.cursors[0]  # the BlockingStubCursor the worker blocks in
    with real_clock_watchdog([stub_cursor]) as tripped:
        with anyio.move_on_after(0):            # cancel scope that fires immediately
            await await_inside(lambda: stub_cursor.execute_call_count == 1)  # gate worker inside
            await cur.execute("SELECT 1")        # parks; the scope cancels it
    assert tripped[0] is False                   # no worker stranded
    assert stub_cursor.adbc_cancel_call_count == 1   # adbc_cancel fired EXACTLY once
    assert stub_conn.close_call_count >= 0           # invalidate path (stub records its own counter)
    # checkedout()==0 asserted on the real-driver variant; the stub variant asserts the cancel signals
```
> The exact gating choreography (which scope cancels, where `await_inside` sits relative to the offload) is the planner's to settle against the harness; the load-bearing assertions are `adbc_cancel_call_count == 1`, `invalidate` once, and `tripped[0] is False`. A real-driver DuckDB variant additionally asserts `pool.checkedout() == 0`.

### EDGE-06: `fail_after` vs `scope.cancel()` parity (only the surfaced type differs)
```python
# Source: live probe B (fail_after → TimeoutError on both backends) + probe D (scope.cancel → no surfaced exc)
@pytest.mark.anyio
async def test_fail_after_and_scope_cancel_both_abort(make_stub_async_connection, anyio_backend_name):
    # Leg 1: fail_after → caller sees TimeoutError
    a_conn, s_conn = make_stub_async_connection(); cur = a_conn.cursor(); sc = s_conn.cursors[0]
    with real_clock_watchdog([sc]):
        with virtual_clock(anyio_backend_name):
            with pytest.raises(TimeoutError):
                with anyio.fail_after(5):
                    await await_inside(lambda: sc.execute_call_count == 1)
                    await cur.execute("SELECT 1")
    assert sc.adbc_cancel_call_count == 1
    # Leg 2: explicit scope.cancel() → no exception surfaces, but adbc_cancel still fires (probe D)
    # ... symmetric, asserting adbc_cancel_call_count == 1 and no raised exception ...
```

### EDGE-19: a genuine ADBC error survives the task group unwrapped
```python
# Source: probe C (lone error → ExceptionGroup) + probe E (unwrap preserves type/frame)
@pytest.mark.anyio
async def test_real_adbc_error_unwrapped(duckdb_async_pool):
    from adbc_driver_manager import Error as AdbcError
    with pytest.raises(AdbcError):                       # NOT ExceptionGroup
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT * FROM does_not_exist")  # genuine error, no cancel
    assert duckdb_async_pool._pool.checkedout() == 0     # connection returned, not invalidated
```

### EDGE-29: asyncio↔trio tuple equality
```python
# Source: CONTEXT EDGE-29 — collect the signal tuple per backend, assert equal
# Each backend leg writes (adbc_cancel_count, invalidate_count, checkedout_after) into a
# module/session store keyed by backend; a final assertion compares the asyncio and trio tuples.
@pytest.mark.anyio
async def test_cancel_signal_tuple(record_cancel_tuple, make_stub_async_connection, anyio_backend_name):
    # run the canonical EDGE-02 cancel, then:
    record_cancel_tuple[anyio_backend_name] = (adbc_cancel_count, invalidate_count, checkedout_after)
    # a non-parametrized assertion (or a fixture finalizer) asserts both legs recorded the SAME tuple
```
> Implementation note for the planner: the cleanest way to assert cross-leg equality is a session-scoped dict fixture that both parametrized legs write into, plus one assertion that runs after both have populated it (e.g. a `request.addfinalizer` on the session, or a dedicated non-parametrized test that reads the dict). Keep both legs' setup byte-identical so the only variable is the backend.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `except asyncio.CancelledError` | `except anyio.get_cancelled_exc_class()` | n/a (project rule) | asyncio-only catch is a no-op under trio; banned + AST-guarded (D-25-06/EDGE-28) |
| `to_thread.run_sync(cancellable=True)` to "cancel" | watcher task + `adbc_cancel` + `abandon_on_cancel=False` | anyio 4.x renamed `cancellable`→`abandon_on_cancel`; neither actually interrupts the worker | `abandon_on_cancel=True` only ignores the outcome (leaks the worker); rejected (Research Grounding) |
| Catch a bare child-task exception | Catch `BaseExceptionGroup` + unwrap | Py 3.11+ / anyio 4.x task groups always bundle | Single-member groups must be unwrapped to keep type fidelity (verified) |

**Deprecated/outdated:**
- `cancellable=` kwarg — already `abandon_on_cancel=` (Phase 24).
- Any `asyncio.*` reference inside `_async/` — banned and AST-guarded (now incl. `asyncio.CancelledError`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A real DuckDB `cursor.adbc_cancel()` called from the watcher (loop thread) unblocks the worker the same way the CONTEXT probe showed it does from a foreign main thread | Pattern 1/2 | LOW — Research Grounding confirms `adbc_cancel` is thread-safe and intended for cross-thread interrupt; the watcher runs on the loop thread, a different thread from the worker. A real-driver EDGE-02 leg validates it end-to-end |
| A2 | On the cancel path, anyio's collapse of the bundled (Cancelled + worker interrupt) means the cursor method's `except get_cancelled_exc_class()` (not the `except BaseExceptionGroup`) is the branch that fires | Pattern 1/2 | LOW — `[VERIFIED: probe A]` for `fail_after`; the cursor-method-level catch order should be `except get_cancelled_exc_class()` BEFORE any group catch. Planner must order the excepts so cancellation is checked first |
| A3 | `fairy.invalidate()` offloaded under a shield is safe to call after the worker has been joined (offload returned) on the cancel path | Pattern 3 | LOW — CONTEXT probe confirmed `invalidate()` is sufficient and a following `close()` is a no-op; the worker is always joined (`abandon_on_cancel=False`) before cleanup |
| A4 | The `BlockingStubConnection` exposes (or trivially gains) an `invalidate()` the `AsyncConnection.invalidate()` offload can call for stub-backed cancel tests | Test design / Wave 0 | MEDIUM — `BlockingStubConnection` currently has `close`/`adbc_cancel`/`cursor` but NO `invalidate` (verified in stubs.py). Wave 0 must add a stub `invalidate()` (increment an `invalidate_call_count`, set a flag) to drive EDGE-02/04/05/29 on the stub harness. This is the one harness gap |

## Open Questions

1. **Does `BlockingStubConnection` need an `invalidate()` method, or should stub cancel tests assert via the real DuckDB pool only?**
   - What we know: `BlockingStubConnection` has `close`/`adbc_cancel`/`cursor` + counters, but NOT `invalidate` `[VERIFIED: stubs.py]`. `AsyncConnection.invalidate()` will call `self._fairy.invalidate()`, which the stub must expose for stub-backed cancel tests.
   - What's unclear: whether to add `invalidate()` + `invalidate_call_count` to the stub (clean, matches the D-04 LOCKED-contract style) or assert the invalidate signal only on the real-driver leg.
   - Recommendation: add `invalidate()` + `invalidate_call_count` to `BlockingStubConnection` in a Wave-0 task (one method, lock-guarded counter, mirroring `close`). This keeps EDGE-02/04/05/29 deterministic on the stub harness and lets the tuple-equality (EDGE-29) read a clean `invalidate_count`. Treat as the single harness extension this phase needs.

2. **In the cursor method, what is the correct `except` ordering so cancellation is handled before a non-cancel group?**
   - What we know: on the cancel path anyio collapses to the framework cancellation (`get_cancelled_exc_class()`); on the non-cancel path a genuine error arrives as an `ExceptionGroup` (verified). The unwrap of the group happens inside `cancellable_offload`, so the cursor method should mostly see either a bare cancellation or a bare unwrapped `AdbcError`.
   - What's unclear: whether any residual group can reach the cursor method (it should not, given the unwrap in `cancellable_offload`).
   - Recommendation: keep the unwrap in `cancellable_offload` (Pattern 1) so the cursor method only ever catches `get_cancelled_exc_class()` for the invalidate path and lets a bare `AdbcError` propagate. Verify with EDGE-19 (bare `AdbcError`) and EDGE-02 (bare cancellation).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `anyio` | `cancellable_offload`, shields, `get_cancelled_exc_class` | ✓ | 4.14.1 | — |
| `trio` | trio leg of every cancel test (EDGE-29) | ✓ | 0.33.0 | — |
| `aiotools` | asyncio virtual clock (`virtual_clock`) for EDGE-06/07 | ✓ | 2.2.3 | event-gating only |
| `sqlalchemy` | `fairy.invalidate()` poison recovery | ✓ | 2.0.49 (`invalidate` present) | — |
| `adbc-driver-manager` | `cursor.adbc_cancel()` real-driver leg | ✓ | 1.11.0 | stub harness covers the signal logic |
| `duckdb` (`[duckdb]`) | real-driver cancel smoke (CANCEL-01/02 end-to-end) | ✓ (dev `[all]`) | via extra | stub harness (signal-level) |
| `mkdocs` + strict | docs gate (phase ≥7) | ✓ | docs group | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none material — all required deps are present.

> Sandbox note (MEMORY): prefer `.venv/bin/<tool>` over `uv run <tool>` for mkdocs/hooks/pytest to avoid sandbox prompts — e.g. `.venv/bin/mkdocs build --strict`, `.venv/bin/pytest`.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json`, so this section is REQUIRED and feeds VALIDATION.md. This is the milestone's highest-risk correctness item; the sampling strategy below is deliberately strict (×N loop, watchdog, dual-backend).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` + anyio pytest plugin; dual-backend via the `anyio_backend` fixture (asyncio + trio MockClock), already in `tests/async/conftest.py` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (no separate pytest.ini) |
| Quick run command | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -x -q` |
| Full suite command | `.venv/bin/pytest -q` (sync + harness + async, both backends) |
| Loop-run (REQUIRED) | `for i in $(seq 1 20); do .venv/bin/pytest tests/async -q; rc=$?; [ "$rc" -ne 0 ] && break; done` — 0 hangs/failures across 20 runs (use `rc=$?`, never `if ! pytest`, per the zsh-`!` MEMORY gotcha) |
| No-hang watchdog | `tests/async/_edge_helpers.py::real_clock_watchdog` (wall-clock; NOT `anyio.fail_after` — autojumps under trio MockClock) |

### Observable Signals the cancel tests MUST assert

The cancel path is asserted entirely through signals the harness already records (D-04 LOCKED contract) plus the limiter/pool observables:

| Signal | Source | Asserted value (canonical cancel) |
|--------|--------|-----------------------------------|
| `adbc_cancel_call_count` | `BlockingStubCursor` (lock-guarded) | `== 1` on EDGE-02/06; `== 0` on EDGE-01/07; `== 1` (not 2) on EDGE-04 double-cancel |
| `observed_cancel` | `BlockingStubCursor` | `True` after a cancelled block; `False` on EDGE-07 (op finished first) |
| `invalidate_call_count` | `BlockingStubConnection` (**NEW — Wave 0**, Open Q1) | `== 1` after a cancelled scope (EDGE-02/04/05); `== 0` on EDGE-01/07 and on a genuine `AdbcError` (Pitfall 6) |
| `pool.checkedout()` | real-driver DuckDB pool | `== 0` after a cancelled scope (CANCEL-02, EDGE-02/05) |
| `pool._limiter.borrowed_tokens` | `AsyncPool._limiter` | `== 0` after a cancelled `cancellable_offload` (EDGE-09 cancel-mid-block leg, ×50) |
| Surfaced exception identity | caller `pytest.raises(...)` | `TimeoutError` for `fail_after`; nothing for `scope.cancel()`; the bare `get_cancelled_exc_class()` instance escapes (EDGE-03); a bare `AdbcError` (not `ExceptionGroup`) on the non-cancel path (EDGE-19) |
| `(adbc_cancel_count, invalidate_count, checkedout_after)` tuple | aggregate per backend | EQUAL under asyncio and trio (EDGE-29) |
| `real_clock_watchdog` `tripped[0]` | wall-clock side thread | `False` (no worker stranded) in every cancel test |
| `scan_async_package(_async/)` | AST guard | `== []` incl. the new `banned-asyncio-cancelled-error` rule (EDGE-28) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EDGE-01 | cancel before offload starts — no `execute`, no `adbc_cancel`, clean | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k before -q` | ❌ Wave 0 |
| EDGE-02 / CANCEL-01/02 | cancel during block — `adbc_cancel`×1, invalidate, `checkedout()==0` | unit (stub) + integration (DuckDB) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k during -q` | ❌ Wave 0 |
| EDGE-03 | framework cancel class escapes; no trio hang | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k escapes -q` | ❌ Wave 0 |
| EDGE-04 / CANCEL-03 | double-cancel idempotent — one `adbc_cancel`, one invalidate, one cancel exc | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k double -q` | ❌ Wave 0 |
| EDGE-05 | cancel during `__aexit__`/checkin — `checkedout()==0` conn+cursor | unit (stub) + integration | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k checkin -q` | ❌ Wave 0 |
| EDGE-06 | `fail_after` vs `scope.cancel()` parity (type differs only) | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k parity -q` | ❌ Wave 0 |
| EDGE-07 | `move_on_after` on finished op — `cancelled_caught` False, no `adbc_cancel` | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k finished -q` | ❌ Wave 0 |
| EDGE-19 | genuine `AdbcError` unwrapped from EG; `checkedout()==0` | integration (DuckDB) | `.venv/bin/pytest tests/async/test_edge_exceptiongroup.py -q` | ❌ Wave 0 |
| EDGE-09 (cancel leg) | `borrowed_tokens==0` after cancelled offload (×50) | unit (stub) | `.venv/bin/pytest tests/async/test_edge_limiter.py -k cancel_token -q` | ⚠️ file exists; cancel leg ❌ |
| EDGE-28 / CANCEL-04 | no `asyncio.CancelledError` in `_async/`; guard meta empty | static (AST) | `.venv/bin/pytest tests/async/test_async_guard.py -q` + extend guard | ⚠️ guard exists; new rule ❌ |
| EDGE-29 / CANCEL-04 | `(adbc_cancel, invalidate, checkedout)` tuple equal asyncio↔trio | unit (stub) | `.venv/bin/pytest tests/async/test_edge_backend_parity.py -q` | ❌ Wave 0 |
| CANCEL-01/02 (real driver) | end-to-end cancel→`adbc_cancel`→invalidate→`checkedout()==0` on DuckDB | integration | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k duckdb -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/async -x -q` + `.venv/bin/ruff check` + `.venv/bin/basedpyright`.
- **Per wave merge:** full suite `.venv/bin/pytest -q` (both backends) **run in a ×20 loop** for the cancel waves — 0 hangs required (MEMORY: single-shot missed a 33% deadlock; verify with `rc=$?` + grep the pass line, never `if ! pytest`).
- **Phase gate:** full suite green + ×20 loop clean + `.venv/bin/basedpyright` 0 errors + `.venv/bin/ruff check`/`format --check` clean + `.venv/bin/mkdocs build --strict` passes (docs gate, phase ≥7) + `scan_async_package("src/adbc_poolhouse/_async/") == []` incl. the new rule.

### Wave 0 Gaps
- [ ] **Harness:** add `invalidate()` + `invalidate_call_count` (lock-guarded, D-04 style) to `BlockingStubConnection` in `tests/_async_harness/stubs.py` (Open Q1) — **prerequisite** for stub-backed EDGE-02/04/05/29.
- [ ] **Guard:** add the `banned-asyncio-cancelled-error` rule to `tests/_async_harness/guard.py` (Pattern 4) and a self-test for it.
- [ ] `tests/async/test_edge_cancel_depth.py` — EDGE-01/02/03/04/05/06/07 (stub + a DuckDB real-driver leg).
- [ ] `tests/async/test_edge_exceptiongroup.py` — EDGE-19 (DuckDB bare-`AdbcError` unwrap).
- [ ] `tests/async/test_edge_backend_parity.py` — EDGE-29 tuple equality (session-scoped dict + cross-leg assert).
- [ ] Extend `tests/async/test_edge_limiter.py` with the EDGE-09 cancel-mid-block ×50 leg.
- [ ] Extend `tests/async/test_async_guard.py` to assert the new rule fires on synthetic `asyncio.CancelledError` and that real `_async/` stays clean.
- [ ] Docs: cancellation/timeout section in `docs/src/guides/async.md` + `AsyncConnection.invalidate` docstring (docs gate).

*(If no other gaps: the existing `duckdb_async_pool`, `make_stub_async_connection`, `await_inside`, `real_clock_watchdog`, and `virtual_clock` cover everything else — no new fixtures/helpers beyond the stub `invalidate()` and the guard rule.)*

## Security Domain

> `security_enforcement` is not present in `.planning/config.json`; treating as enabled. This phase adds no authn/authz/crypto/input-parsing surface — it is internal concurrency-control plumbing.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | DB creds flow unchanged through existing `WarehouseConfig`; no change |
| V3 Session Management | no | No sessions/tokens introduced |
| V4 Access Control | no | No access-control surface |
| V5 Input Validation | no | No new user-input parsing; `operation`/`parameters` pass through the dbapi unchanged (parameterized queries already the norm) |
| V6 Cryptography | no | No crypto — never hand-rolled here |
| V7 Error Handling & Logging | yes (light) | The cancel path must NOT leak a poisoned connection (resource-exhaustion / availability hardening): `invalidate()` ensures a cancelled connection is dropped, not silently reused with aborted-transaction state (D-25-03). EDGE-02/05 assert `checkedout()==0` |

### Known Threat Patterns for {anyio thread-offload cancellation}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Pool exhaustion via leaked connections on cancel/timeout | Denial of Service | Invalidate-on-cancel (`fairy.invalidate()`), shielded so it always completes; `checkedout()==0` asserted (CANCEL-02) |
| Reuse of a poisoned (aborted-transaction) connection serving stale/incorrect data | Tampering / Information | Mandatory invalidate, never return-busy (probe-confirmed poisoning, D-25-03); never sniff to "recover" a connection |
| Stranded non-cancellable worker hanging the loop (availability) | Denial of Service | `abandon_on_cancel=False` + `adbc_cancel` join; `real_clock_watchdog` proves no hang; ×20 loop proves no intermittent deadlock |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/25-cancellation/25-CONTEXT.md` — D-25-01..08 + Research Grounding (ADBC cancel spec, anyio offload facts, the live DuckDB probe). AUTHORITATIVE.
- `.planning/REQUIREMENTS.md` — CANCEL-01..04, EDGE-01..07/19/28/29 verbatim acceptance text `[VERIFIED]`.
- `.planning/ROADMAP.md` §Phase 25 — goal + five success criteria `[VERIFIED]`.
- `.planning/phases/24-core-async-wrapper/{24-CONTEXT,24-RESEARCH,24-PATTERNS}.md` — D-24-01..04, the offload chokepoint, Pitfall 2 (single-shot deadlock), the EDGE-09 split (D-24-02), the shielded-checkin already shipped `[VERIFIED]`.
- `src/adbc_poolhouse/_async/{_offload,_cursor,_connection}.py` — the exact code being extended; shielded `close`/`__aexit__` already present `[VERIFIED: source read]`.
- `tests/_async_harness/{stubs,gating,guard,clock}.py` + `tests/async/{conftest,_edge_helpers}.py` — the reusable harness: `BlockingStubCursor.adbc_cancel`/counters, `await_inside`, `real_clock_watchdog`, `virtual_clock`, `scan_async_package`, dual-backend `anyio_backend` `[VERIFIED: source read]`.
- **Live venv probes (this session):** anyio 4.14.1 task-group ExceptionGroup collapse on cancel (probe A) and on error (probe C); `fail_after`→`TimeoutError` on both backends (probe B); `scope.cancel()`→no surfaced exception (probe D); single-member EG unwrap preserves type + worker frame (probe E); `PoolProxiedConnection.invalidate` present; `get_cancelled_exc_class` present `[VERIFIED]`.
- `CLAUDE.md` + user MEMORY — docs gate, Google/Markdown docstrings, sandbox `.venv/bin`, loop-flaky-concurrency, zsh-`!` loop gotcha `[VERIFIED]`.

### Secondary (MEDIUM confidence)
- ADBC C/Java `cancel` thread-safety spec (quoted in CONTEXT Research Grounding) — `[CITED: via CONTEXT]`; not re-fetched this session because CONTEXT's quotes are authoritative and version-pinned.

### Tertiary (LOW confidence)
- A1/A3 (real-driver `adbc_cancel` from the loop thread; shielded `invalidate` post-join) — directly validated by a real-driver EDGE-02 leg.
- A4 (stub `invalidate()` Wave-0 add) — a mechanical harness extension; low design risk.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libs pre-existing; cancel API + `invalidate` verified live.
- Architecture / mechanism: HIGH — D-25-01..08 settled in CONTEXT and grounded in a live probe; the one subtle area (D-25-05) was re-verified by five live anyio probes this session.
- Test design: HIGH — every signal and gate already exists in the Phase 23/24 harness; the one gap (stub `invalidate()`) is identified and trivial.
- Pitfalls: HIGH — drawn from the verified probes + the Phase 23/24 postmortems + MEMORY, not speculation.

**Research date:** 2026-06-28
**Valid until:** ~2026-07-28 (stable internal design; anyio 4.14.1 / trio 0.33.0 are the only external moving parts and both are pinned in the lock).
