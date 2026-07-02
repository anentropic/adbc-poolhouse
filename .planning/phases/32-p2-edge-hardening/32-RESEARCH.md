# Phase 32: P2 Edge Hardening - Research

**Researched:** 2026-07-02
**Domain:** Deterministic dual-backend (asyncio + trio) async edge-case tests over the anyio thread-offload async layer, extended to the four v1.5.0 cursor methods (`fetch_record_batch` streaming, `adbc_ingest`, `fetch_df`, `fetch_polars`) plus the `AsyncRecordBatchReader.__del__` finalizer surface.
**Confidence:** HIGH — every load-bearing anyio semantic (checkpoint at offload, contextvar copy-in / no-leak-back, `move_on_after(0)` delivery) was verified empirically against the *installed* anyio 4.14.1 / trio 0.33.0 in this repo's `.venv`, not just from docs; all test patterns are extensions of existing green tests read directly.

## Summary

Phase 32 is **test-only** (with a narrow, explicitly-scoped production contingency — see below). It closes the six deferred P2 EDGE requirements (EDGE-08, EDGE-13, EDGE-14, EDGE-24, EDGE-31, EDGE-32) by extending the *existing* chokepoint coverage — proven for the OLD methods (`execute` / `fetch_arrow_table`) in Phases 24/25 — onto the FOUR new-method offload paths (`fetch_record_batch` pull, `adbc_ingest`, `fetch_df`, `fetch_polars`) and the `AsyncRecordBatchReader` finalizer. No new public symbols ship. The harness (`BlockingStubCursor` / `BlockingStubReader` / `BlockingStubConnection`) already stubs all four methods with blocking gates + the locked counters; no harness extension is expected.

The three "assert-don't-add" requirements (EDGE-08, EDGE-13, EDGE-14) are **guarantees of `anyio.to_thread.run_sync` itself**, which every offload routes through the single `offload()` chokepoint. I verified all three directly against the installed anyio: (1) a cancel set before the offload with no intervening checkpoint is delivered *at* the offload boundary and `fn` never runs, on both backends (EDGE-08); (2) a contextvar set before the offload is visible in the worker (EDGE-13); (3) a worker's contextvar mutation does not leak back to the calling task (EDGE-14). Because these are anyio-level guarantees enforced at one chokepoint, they hold *uniformly* for all four new methods — the tests need only pin them on one representative new-method offload each (per the ROADMAP success criteria wording "asserted on a new-method offload").

The two timing requirements (EDGE-31 `move_on_after(0)` still cancels; EDGE-32 deadline−ε does not over-cancel) and the shutdown requirement (EDGE-24) are being proven for the **first time on the new paths**. These are the ones that could in principle surface a real gap. My assessment (detailed per-item below): all four new methods route through the *same* `cancellable_offload` / `offload` machinery already proven for `execute`, so no production change is expected — but the phase carries an explicit contingency per the locked discussion, and I call out exactly what a minimal fix would look like if a test goes red.

**Primary recommendation:** Add one new-method-parametrized test module per requirement group, cloning the choreography from the already-green analogs (`test_edge_cancel_depth.py` for EDGE-08/31/32, `test_reader_cancel.py` for the streaming-pull cancel window, `test_edge_resource.py` + `test_reader_resource.py` for EDGE-24/finalizers), plus two tiny contextvar tests (EDGE-13/14) that need no gating at all. Reuse `real_clock_watchdog` (never `anyio.fail_after` as watchdog), `virtual_clock` for deadline triggers, `await_inside` for entry gating, and `concurrency_marks` on every concurrency-sensitive test. Gate acceptance on the Linux CI x20 loop for the cancel/shutdown legs.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Checkpoint-at-offload delivery (EDGE-08) | anyio runtime (`to_thread.run_sync`) | Test assertion only | The offload's `async with limiter` acquire is the checkpoint; anyio normalises delivery on both backends. poolhouse adds no code — it asserts the guarantee. |
| contextvar copy-in / no-leak-back (EDGE-13/14) | anyio runtime (`to_thread.run_sync` via `copy_context`) | Test assertion only | anyio copies the current context into the worker and discards worker mutations. Guaranteed at the single chokepoint; tests pin it. |
| Timeout precision on the new paths (EDGE-31/32) | `cancellable_offload` / `offload` (existing) | Test assertion; contingency = production fix IN phase | The new methods reuse the same cancel machinery already proven for `execute`; the phase asserts identical behavior and holds a contingency if a gap surfaces. |
| Shutdown cleanliness mid-stream / mid-ingest (EDGE-24) | anyio backend teardown + `offload` (`abandon_on_cancel=False`) | Test assertion; trio nursery is the canary | A pending offload at loop shutdown must raise nothing library-attributable; trio's stricter nursery teardown is the discriminating backend. |
| Finalizer warn-only surface (`__del__`) | `AsyncRecordBatchReader.__del__` (exists, Phase 29) | Test assertion | The one finalizer this phase touches already exists; `AsyncCursor` needs none (EDGE-22/23 closed, cursor case covered by design). |

## Standard Stack

No new packages. Every dependency this phase needs is already installed and version-verified against this repo's `.venv`:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anyio | 4.14.1 `[VERIFIED: importlib.metadata]` | Backend-neutral offload + cancel scopes; the guarantees EDGE-08/13/14 assert | The whole async layer is built on it; `pyproject.toml` pins `anyio>=4.13` |
| trio | 0.33.0 `[VERIFIED: importlib.metadata]` | The second backend + `MockClock` for virtual-time deadlines | Dual-backend is mandatory (D-06); `pyproject.toml` pins `trio>=0.31` |
| aiotools | 2.2.3 `[VERIFIED: importlib.metadata]` | `VirtualClock().patch_loop()` — the asyncio-leg virtual clock inside `virtual_clock()` | Already wired into `tests/_async_harness/clock.py`; pins `aiotools>=2.2` |
| pytest-repeat | (dev, present) `[VERIFIED: pyproject.toml]` | `@pytest.mark.repeat(N)` — the x-loop half of `concurrency_marks` | Codifies the "0-hang over N iterations" gate (MEMORY loop-flaky lesson) |
| pytest-timeout | (dev, present) `[VERIFIED: pyproject.toml]` | `@pytest.mark.timeout(S)` — turns a genuine hang into a hard failure | Backstop alongside `real_clock_watchdog` |

### Supporting (test harness — already built, reuse wholesale)
| Asset | Location | Purpose | When to Use |
|-------|----------|---------|-------------|
| `BlockingStubCursor` | `tests/_async_harness/stubs.py` | Blocking `execute`/`fetch_arrow_table`/`adbc_ingest`/`fetch_df`/`fetch_polars`/`fetch_record_batch` with locked counters | Every stub-driven leg |
| `BlockingStubReader` | `tests/_async_harness/stubs.py` | Blocking `read_next_batch` for the streaming-pull window | EDGE-08/24/31/32 on the streaming path |
| `BlockingStubConnection` | `tests/_async_harness/stubs.py` | `invalidate_call_count` + cursor handles | Any leg asserting invalidate/checkin |
| `make_stub_async_connection` | `tests/async/conftest.py` | Wraps a stub in a real `AsyncConnection` | Every stub-driven leg |
| `duckdb_async_pool` | `tests/async/conftest.py` | Real-driver pool for `checkedout()` / real-frame legs | EDGE-24 real-pool leg, deterministic-drain legs |
| `anyio_backend` | `tests/async/conftest.py` | asyncio + trio-with-`MockClock(autojump=0)` parametrization | Every `@pytest.mark.anyio` test |
| `await_inside` | `tests/async/_edge_helpers.py` | `sleep(0)`-poll until worker is inside the block | Entry gating (no sleeps) |
| `real_clock_watchdog` | `tests/async/_edge_helpers.py` | Wall-clock side-thread that `close()`s stubs on overrun | Fail-fast on hang (NOT the deadline trigger) |
| `concurrency_marks` | `tests/async/_edge_helpers.py` | `[repeat(N), timeout(S)]` | `pytestmark` on every concurrency-sensitive module |
| `virtual_clock` | `tests/_async_harness/clock.py` | Per-backend virtual clock so `fail_after`/`move_on_after` fire instantly | EDGE-31/32 deadline triggers |

**Installation:** None. `uv sync` already provides everything.

**Version verification (performed this session):**
```
importlib.metadata.version('anyio')   -> 4.14.1
importlib.metadata.version('trio')    -> 0.33.0
importlib.metadata.version('aiotools')-> 2.2.3
```

## Package Legitimacy Audit

Not applicable — this phase installs **no** external packages. All dependencies (anyio, trio, aiotools, pytest-repeat, pytest-timeout, pandas, polars) were vetted and installed in prior phases (22–31) and are pinned in `pyproject.toml`. No new install, no new registry lookup, no `[SLOP]`/`[SUS]` surface.

## Architecture Patterns

### System Architecture Diagram

How each EDGE requirement's test drives the production machinery (data/control flow, not files):

```
                          ┌─────────────────────────────────────────────┐
   test body (loop task)  │  AsyncCursor.{adbc_ingest,fetch_df,          │
   sets ContextVar /      │     fetch_polars}  OR  AsyncRecordBatchReader│
   arms stub / sets       │     .__anext__ (streaming pull)              │
   CancelScope/deadline   └───────────────┬─────────────────────────────┘
          │                               │  with owner._offloading():
          ▼                               ▼
   ┌──────────────┐              ┌────────────────────┐
   │ anyio_backend │             │ cancellable_offload │  (watcher + worker task group)
   │ asyncio | trio│             │  adbc_cancel + on_  │
   │ (+MockClock)  │             │  abort=invalidate   │
   └──────┬───────┘              └─────────┬──────────┘
          │                                │ offload(fn, limiter=, on_dispatch=)
          │                                ▼
          │                    ┌───────────────────────────────┐
          │   CHECKPOINT ─────▶│  async with limiter:          │◀── EDGE-08 delivery point
          │   (limiter acquire)│    on_dispatch()  (loop thread)│
          │                    │    to_thread.run_sync(         │
          │                    │      fn, limiter=inner,        │──▶ WORKER THREAD
          │                    │      abandon_on_cancel=False)  │    • sees copied-in ctxvar (EDGE-13)
          │                    └───────────────────────────────┘    • mutations discarded    (EDGE-14)
          │                                │                         • blocks on stub gate
          ▼                                ▼
   deadline fires (EDGE-31/32)      worker joined (never abandoned)
   / scope cancelled                       │
   / loop teardown (EDGE-24)               ▼
          └──────────────────▶ adbc_cancel() once (shielded) + invalidate() ─▶ checkedout()==0
```

The critical insight the diagram encodes: **all four new methods converge on the same `offload()` chokepoint**, so EDGE-08/13/14 (anyio guarantees at that chokepoint) hold for all of them by construction, and EDGE-31/32 reuse the same `cancellable_offload` cancel path already proven for `execute`.

### Recommended Test Structure
```
tests/async/
├── test_edge_checkpoint.py     # EDGE-08: cancel-at-offload on a new-method offload (both backends)
├── test_edge_contextvars.py    # EDGE-13 + EDGE-14: copy-in + no-leak-back on a new-method offload
├── test_edge_timeout_precision.py # EDGE-31 (move_on_after(0)) + EDGE-32 (deadline-ε) on streaming pull + ingest
└── test_edge_shutdown.py       # EDGE-24: open pool / pending offload at loop shutdown, mid-stream + mid-ingest
```
(Names are a suggestion; the planner may fold EDGE-31/32 and EDGE-08 into existing modules. Keep new-method coverage discoverable by `-k` selectors like `ingest`/`stream`/`df`/`polars`.)

### Pattern 1: Assert an anyio guarantee on a new-method offload (EDGE-08/13/14)
**What:** Drive one new-method offload and assert the anyio-level invariant. EDGE-13/14 need NO gating, NO watchdog, NO virtual clock — they are deterministic single-offload assertions.
**When to use:** EDGE-08 (needs a pre-set cancel scope), EDGE-13/14 (contextvars).
**Example (EDGE-13/14 — verified working against installed anyio this session):**
```python
# Source: verified against anyio 4.14.1 / trio 0.33.0 in this repo's .venv
import contextvars
import pytest
from tests._async_harness.stubs import BlockingStubCursor  # has fetch_df/fetch_polars/adbc_ingest

_cv = contextvars.ContextVar("trace")

@pytest.mark.anyio
async def test_contextvar_copied_in_and_no_leak_back(
    make_stub_async_connection, anyio_backend_name
) -> None:
    del anyio_backend_name
    async_conn, stub_conn = make_stub_async_connection()
    cur = async_conn.cursor()
    sc = stub_conn.cursors[0]
    seen: dict[str, object] = {}
    # Inject a worker-side reader of the contextvar via the stub's on_enter hook OR
    # a small wrapper; simplest: assert copy-in by having the worker record cv.get().
    # (BlockingStubCursor records counters; for the ctxvar read, a thin fn passed to
    # a bare offload of a stub method that reads the module cv is the cleanest — see
    # note below on the smallest deterministic mechanism.)
    _cv.set("outer")
    # ... offload a new-method call (e.g. fetch_df) whose worker reads _cv.get()
    # EDGE-13: worker observed "outer";  EDGE-14: after the offload, _cv.get() == "outer"
```
**Implementation note (smallest deterministic mechanism):** The contextvar copy-in/no-leak-back is a property of `offload()` / `to_thread.run_sync`, not of any particular ADBC method. The most deterministic pinning is to offload a *representative new-method* call whose **worker body reads/mutates the contextvar**. Two viable mechanisms, pick per Claude's discretion:
- **(a) A stub whose `fetch_df` reads a module `ContextVar` on entry** (extend the stub's worker body by ONE line, or pass a `on_enter`-style probe) and records what it saw; the test sets the var before `await cur.fetch_df()` and asserts the recorded value == the set value (EDGE-13), then asserts the caller's `cv.get()` is unchanged after the offload (EDGE-14). This keeps the assertion on a real new-method path.
- **(b) Call `offload()` directly** with a `fn` that reads/mutates the contextvar, tagging it as "the same chokepoint every new method routes through." Less end-to-end but zero harness change. The ROADMAP says "asserted on a new-method offload," so prefer (a) if a one-line stub probe is acceptable; otherwise (b) with a comment that the chokepoint is shared.

### Pattern 2: Deadline precision on a blocked new-method op (EDGE-31/32)
**What:** `move_on_after(0)` must still cancel a *blocked* streaming pull / ingest (fires `adbc_cancel`, invalidates); an op completing at deadline−ε must NOT be cancelled.
**When to use:** EDGE-31 (streaming pull + ingest), EDGE-32 (streaming pull + ingest).
**Example (EDGE-31 — clone of the reader-cancel window; timeout trigger under `virtual_clock`):**
```python
# Source: cloned from tests/async/test_reader_cancel.py::test_timeout_during_pull_...
@pytest.mark.anyio
async def test_move_on_after_zero_cancels_blocked_pull(
    make_stub_async_connection, anyio_backend_name
) -> None:
    async_conn, stub_conn = make_stub_async_connection()
    cur = async_conn.cursor()
    stub_conn.cursors[-1].record_batch_batches = [object()]  # first pull BLOCKS
    with (
        real_clock_watchdog(stub_conn.cursors) as tripped,   # NEVER fail_after as watchdog
        virtual_clock(anyio_backend_name),
    ):
        reader = await cur.fetch_record_batch()
        sc = stub_conn.cursors[-1]
        with anyio.move_on_after(0) as scope:                # already-expired deadline
            await reader.__anext__()
    assert tripped[0] is False
    assert scope.cancelled_caught is True
    assert sc.adbc_cancel_call_count == 1     # worker was unblocked via the cursor's cancel
    assert stub_conn.invalidate_call_count == 1
```
**EDGE-32 (deadline−ε NOT over-cancelled):** release the stub worker (happy path) from a REAL side thread the instant it is `entered`, so the op *completes* before a large virtual deadline fires; assert `scope.cancelled_caught is False`, `adbc_cancel_call_count == 0`, `invalidate_call_count == 0`. This is the streaming/ingest twin of the already-green `test_move_on_after_on_finished_op_is_noop` (EDGE-07). The releaser MUST be a real thread (see Pitfall 2) — under the trio `MockClock` a loop-side releaser is starved.

### Pattern 3: Loop-shutdown cleanliness (EDGE-24)
**What:** Create a pool, start (but do not await to completion) a blocked new-method offload — mid-stream (a blocked `read_next_batch`) or mid-ingest (a blocked `adbc_ingest`) — then let the test scope tear down. Assert no library-attributable exception surfaces; capture warnings for stray "Task was destroyed but it is pending" / "coroutine was never awaited". trio's nursery strictness is the canary.
**When to use:** EDGE-24 (mid-stream + mid-ingest).
**Example (shape — extend `test_edge_resource.py` discipline):**
```python
@pytest.mark.anyio
async def test_pending_ingest_at_shutdown_raises_nothing(
    make_stub_async_connection, anyio_backend_name
) -> None:
    async_conn, stub_conn = make_stub_async_connection()
    cur = async_conn.cursor()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        async with anyio.create_task_group() as tg:
            tg.start_soon(functools.partial(cur.adbc_ingest, "t", object()))
            await await_inside(lambda: stub_conn.cursors[0].ingest_call_count == 1)
            for c in stub_conn.cursors:      # release so teardown joins the worker cleanly
                c.release()
    # No library-attributable exception; trio nursery teardown is the strict canary.
    offending = [w for w in caught
                 if "was never awaited" in str(w.message)
                 or "Task was destroyed" in str(w.message)]
    assert offending == []
```
**Design caution for EDGE-24:** Because `offload()` is `abandon_on_cancel=False`, a truly *un-released* blocked worker will make the enclosing task group / test scope **wait to join** at teardown — which under the zero-hang loop gate is itself a hang, not a clean shutdown. The deterministic pattern is to **release the stub in the teardown window** (as above) so the worker joins cleanly and the assertion is about "no stray exception/warning," not "the loop tore down while a C call was genuinely mid-flight." For the real-driver leg, use `duckdb_async_pool` and let the pool close on fixture teardown with a still-open (but drained) connection; assert `pool.close()` raises nothing. Racing a genuinely-wedged worker at shutdown is NOT deterministic (same wedge caveat as the live-`adbc_cancel` legs) and must not be asserted.

### Anti-Patterns to Avoid
- **`anyio.fail_after` as the watchdog.** Under the trio `MockClock(autojump_threshold=0)` a virtual `fail_after` autojumps to its own deadline the instant every task is blocked off-loop, tripping every run. Use `real_clock_watchdog` for the fail-fast watchdog; `fail_after`/`move_on_after` under `virtual_clock` are ONLY the cancellation *trigger under test*.
- **Releasing a gated worker from a loop task under `MockClock`.** Virtual time autojumps to the deadline while the loop is parked on the off-loop worker, starving a loop-side releaser → the "op finished first" (EDGE-32) leg must release from a REAL side thread waiting on the stub's `entered` `threading.Event` (see `_release_when_entered` in `test_edge_cancel_depth.py`).
- **Positive-duration sleeps in timeout tests.** Banned and source-scanned (EDGE-30, shipped). Use `anyio.sleep(0)` checkpoints + event gating only.
- **Single-shot acceptance for cancel/shutdown legs.** A ~33% deadlock hid behind one lucky pass in Phase 23. Apply `concurrency_marks` and gate on the x20 Linux loop.
- **Adding a bespoke async error type or new finalizer.** Out of scope (D-29 governing principle). The only finalizer this phase touches is the *existing* `AsyncRecordBatchReader.__del__`; `AsyncCursor` needs none.
- **`await`-ing the stub's `threading.Event` on the loop.** Dual-`entered` trap: the stub's `entered` is a `threading.Event` (sync self-test signal); the loop-facing gate is a distinct `anyio.Event`. Poll via `await_inside` on the lock-guarded counters instead.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Wait until a worker is inside the block | A `sleep`-based poll | `await_inside(predicate)` | Event-gated, no wall-clock, settles under both backends |
| Fail fast on a hung worker | `anyio.fail_after` watchdog | `real_clock_watchdog` | `fail_after` autojumps under trio `MockClock` |
| Fire a virtual deadline | Real `time.sleep` + real `fail_after` | `virtual_clock(backend)` + `anyio.fail_after`/`move_on_after` | Instant, deterministic on both backends |
| Release a happy-path op under MockClock | A loop-side releaser task | Real side thread on `entered.wait()` | Loop releaser is starved by autojump |
| x-loop / hang gate | A hand-rolled `for` loop in the test | `concurrency_marks` (`pytest-repeat` + `pytest-timeout`) | Codified, env-controlled, CI-tunable |
| Blocking stub for a new method | A new fake | The existing `BlockingStubCursor.{adbc_ingest,fetch_df,fetch_polars,fetch_record_batch}` | Already has gates + locked counters |
| Assert contextvar copy semantics | A custom thread + `run_in_executor` | `offload()` (which uses `to_thread.run_sync`) | anyio's `copy_context` is the guarantee under test; a custom thread would break it |

**Key insight:** Everything Phase 32 needs already exists and is battle-tested. The risk is *re-inventing* a gating/clock mechanism that then behaves differently on the trio leg. Clone the closest green analog verbatim and swap only the offloaded method.

## Runtime State Inventory

Not applicable — Phase 32 is test-only (plus a contingency production fix that would be a code edit, not a state migration). No rename/refactor/migration. No stored data, live-service config, OS-registered state, secrets, or build artifacts are touched.
- **Stored data:** None — no datastore keys/collections/ids changed.
- **Live service config:** None.
- **OS-registered state:** None.
- **Secrets/env vars:** The tests read `ADBC_ASYNC_REPEAT` / `ADBC_ASYNC_TIMEOUT_S` (existing, `_edge_helpers.py`); no new env var, no secret.
- **Build artifacts:** None — no packaging change.

## Common Pitfalls

### Pitfall 1: The `fail_after`-as-watchdog autojump trap
**What goes wrong:** A test uses `anyio.fail_after(5)` to guard against a hang; under the trio `MockClock(autojump_threshold=0)` it fires the instant every task blocks off-loop, so the test "fails" spuriously on the trio leg every run.
**Why it happens:** `MockClock` autojumps virtual time to the nearest deadline when the loop is idle waiting on an off-loop worker.
**How to avoid:** `real_clock_watchdog` for the fail-fast guard (measures real time on a side thread); `virtual_clock` + `fail_after`/`move_on_after` ONLY as the deadline *trigger under test*.
**Warning signs:** A test that passes on asyncio but fails/hangs only on trio; a `TimeoutError` that fires "too fast."

### Pitfall 2: MockClock starves a loop-side happy-path releaser (EDGE-32)
**What goes wrong:** The EDGE-32 "deadline−ε, not over-cancelled" leg releases the blocked op from a loop task; under `MockClock` virtual time jumps to the deadline before the loop-side releaser runs, so the op is cancelled anyway and the assertion inverts.
**Why it happens:** The loop is parked on the off-loop worker; autojump advances to the deadline before scheduling the releaser coroutine.
**How to avoid:** Release from a REAL side thread that waits on the stub's `entered` `threading.Event` (copy `_release_when_entered` from `test_edge_cancel_depth.py`).
**Warning signs:** `cancelled_caught is True` when you expected `False`; `adbc_cancel_call_count == 1` on a leg that should be a clean completion.

### Pitfall 3: `abandon_on_cancel=False` turns "shutdown with pending offload" into a join-hang (EDGE-24)
**What goes wrong:** The EDGE-24 test starts a blocked offload and lets the scope tear down expecting a clean shutdown, but the non-cancellable offload makes the task group WAIT to join the worker → the test hangs (and the x20 gate fails), rather than proving "no exception at shutdown."
**Why it happens:** `offload()` is deliberately `abandon_on_cancel=False` (a connection is never abandoned mid-op); the only way to unblock the worker is to release it (or `adbc_cancel`).
**How to avoid:** Release the stub in the teardown window so the worker joins cleanly, then assert on the absence of stray exceptions/warnings. For the real leg, close the pool with a drained connection. Do NOT try to assert shutdown while a worker is genuinely wedged mid-C-call.
**Warning signs:** The shutdown test hangs under the loop gate; `real_clock_watchdog` trips.

### Pitfall 4: The dual-`entered` object mixup
**What goes wrong:** A test `await`s `stub.entered.wait()` (a `threading.Event`) on the event loop and either blocks the loop or reintroduces the worker-entry race.
**Why it happens:** The stub's `entered` (sync self-test signal) and the loop-facing gate share a name but are different objects.
**How to avoid:** On the loop, poll via `await_inside(lambda: stub.<counter> >= 1)`; never await the stub's `threading.Event`.
**Warning signs:** A hang at the gate; a flaky "worker not inside yet" assertion.

### Pitfall 5: Streaming-path cancel needs a PENDING batch to open a window
**What goes wrong:** A cancel/timeout test on `fetch_record_batch` arms nothing, so the default empty reader exhausts on the first pull (no block) and there is no window to cancel — the test asserts `adbc_cancel_call_count == 1` and fails because the pull never blocked.
**Why it happens:** `BlockingStubReader` with no batches raises `StopIteration` immediately; only a reader with `record_batch_batches = [object()]` (or `batches=[...]`) blocks per-pull.
**How to avoid:** Set `stub_conn.cursors[-1].record_batch_batches = [object()]` BEFORE `await cur.fetch_record_batch()` (exactly as `test_reader_cancel.py` does).
**Warning signs:** `read_call_count` advances but the pull never blocks; the cancel window is missed.

## Code Examples

### EDGE-08: cancel set before a new-method offload is delivered at the offload boundary (verified this session)
```python
# Source: verified against installed anyio 4.14.1 / trio 0.33.0; mirrors
# test_edge_cancel_depth.py::test_cancel_before_offload_is_clean (EDGE-01) but on a NEW method.
@pytest.mark.anyio
async def test_cancel_before_ingest_delivered_at_offload(
    make_stub_async_connection, anyio_backend_name
) -> None:
    del anyio_backend_name
    async_conn, stub_conn = make_stub_async_connection()
    cur = async_conn.cursor()
    sc = stub_conn.cursors[0]
    with real_clock_watchdog(stub_conn.cursors) as tripped:
        with anyio.CancelScope() as scope:
            scope.cancel()                      # cancel BEFORE the offload; no intervening await
            with pytest.raises(anyio.get_cancelled_exc_class()):
                await cur.adbc_ingest("t", object())
    assert tripped[0] is False
    assert sc.ingest_call_count == 0            # driver never touched — delivered at the checkpoint
    assert sc.adbc_cancel_call_count == 0
    assert stub_conn.invalidate_call_count == 0
```
Note: I confirmed empirically that with a pre-set cancel and no intervening checkpoint, `to_thread.run_sync`'s `fn` never runs and the cancel surfaces at the offload on BOTH backends. The `async with limiter` acquire inside `offload()` is that checkpoint. The trio leg is the discriminator (it guarantees every `await` is a checkpoint) — mark it so.

### EDGE-13/14: contextvar copy-in + no-leak-back (verified this session, both backends)
```python
# Source: verified — anyio.to_thread.run_sync copies the current context into the worker
# (copy_context) and discards worker mutations. Output on both backends:
#   seen_in_worker == "outer"      (EDGE-13: copied in)
#   caller cv.get() == "outer"     (EDGE-14: no leak back)   (worker set "inner", discarded)
import contextvars, anyio
_cv = contextvars.ContextVar("trace")
def _worker():          # runs on the worker thread
    seen = _cv.get("MISSING")
    _cv.set("inner")    # must NOT leak back
    return seen
async def main():
    _cv.set("outer")
    seen = await anyio.to_thread.run_sync(_worker)   # in the real test: route via a new-method offload
    return seen, _cv.get("MISSING")
# In the phase test, wire _worker's read/mutate into a new-method offload path per Pattern 1(a).
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `cancellable=` kwarg on `to_thread.run_sync` | `abandon_on_cancel=` (both accepted; `cancellable` deprecated, warns) | anyio 4.1.0 | The offload chokepoint already uses `abandon_on_cancel=False`; tests must not reintroduce `cancellable=`. `[VERIFIED: anyio 4.14.1 source read this session — the deprecation warning is live]` |
| Prove edge cases on old methods only | Extend proven chokepoint coverage onto the four new-method paths | Phase 32 (this) | Zero new machinery; the guarantees hold at the shared chokepoint |

**Deprecated/outdated:**
- `cancellable=` alias — do not use in any new test; `abandon_on_cancel=` only. (The production `offload()` already complies.)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The four new methods need **no** production change for EDGE-08/13/14/31/32/24 because they route through the same `offload`/`cancellable_offload` chokepoint already proven for `execute`. | Summary / Responsibility Map | LOW — if a test goes red, the locked contingency lands a minimal fix IN Phase 32 (see contingency section). The chokepoint-sharing is verified by reading `_reader.py`/`_cursor.py` (all call `cancellable_offload`/`offload`), so the risk is confined to a path-specific quirk. |
| A2 | The harness needs no extension — all four new-method stubs + counters (`ingest_call_count`, `df_call_count`, `polars_call_count`, `record_batch_batches`, `adbc_cancel_call_count`, `invalidate_call_count`) already exist. | Standard Stack | LOW — verified by reading `stubs.py`. Only possible gap: a contextvar *read* probe in the stub worker body for EDGE-13 (one line, or use Pattern 1(b)). Flagged as Claude's discretion. |
| A3 | EDGE-24 is best proven by releasing the worker in the teardown window (clean join) + asserting no stray exception/warning, NOT by racing a genuinely-wedged worker at shutdown. | Pattern 3 / Pitfall 3 | MEDIUM — if the reviewer expects a genuinely-mid-flight-at-shutdown assertion, the deterministic version is weaker. But a wedged-worker race violates the zero-hang gate (same rationale as the live-`adbc_cancel` deviation already accepted in Phases 25/29). |

## Open Questions

1. **EDGE-13 stub probe vs. bare-`offload` mechanism**
   - What we know: The contextvar guarantees hold at the `offload()` chokepoint (verified). The ROADMAP says "asserted on a new-method offload."
   - What's unclear: Whether to add a one-line contextvar read to the stub's `fetch_df` worker body (Pattern 1(a), most end-to-end) or assert via a direct `offload()` call with a comment that the chokepoint is shared (Pattern 1(b), zero harness change).
   - Recommendation: Prefer 1(a) if a one-line stub probe passes review; else 1(b). Either satisfies EDGE-13/14. This is Claude's discretion.

2. **EDGE-24 real-driver leg scope**
   - What we know: The stub leg deterministically proves "no stray exception/warning at teardown with a released worker." The real `duckdb_async_pool` leg proves `pool.close()` with an open-but-drained connection raises nothing.
   - What's unclear: Whether to attempt any real mid-stream/mid-ingest-at-shutdown leg beyond the drained-close (would risk a nondeterministic wedge).
   - Recommendation: Stub legs for mid-stream + mid-ingest (deterministic); one real drained-close leg. Do not race a wedged worker. Mark trio as the canary leg.

## Discovered-Necessity Contingency (per locked decision #3)

Per-item assessment of whether a **production** change is plausibly needed if a test empirically reveals a gap, and what the minimal fix would be. The default expectation is **no production change** (all paths share the proven chokepoint), but the phase carries these as explicit contingency tasks:

| EDGE | Plausible gap | Minimal fix (contingency, lands IN Phase 32) |
|------|---------------|-----------------------------------------------|
| EDGE-08 | A new-method path somehow reaches the driver before the checkpoint (would require it to bypass `offload`). | None expected. If red: ensure the method routes its dispatch through `cancellable_offload`/`offload` (it already does — fix would be a mis-wired call site). |
| EDGE-13/14 | A path builds its own thread or uses `run_in_executor` instead of `to_thread.run_sync` (would drop the context). | None expected. If red: replace the offending dispatch with `offload()` (the single chokepoint). Verified: `_reader.py`, `_cursor.py` all use `offload`/`cancellable_offload`. |
| EDGE-31 | `move_on_after(0)` on a blocked pull/ingest fails to fire `adbc_cancel` (worker not unblocked). | None expected (reuses `execute`'s proven cancel path). If red: the fix is in `cancellable_offload`'s watcher/`on_dispatch` gating — but that is shared, so a same-fix would ripple to `execute` too (unlikely to have regressed). |
| EDGE-32 | An op completing at deadline−ε is spuriously cancelled/invalidated (over-cancel). | None expected. If red: audit `cancelled_caught` gating in the cancel path; shared machinery, so treat as a real bug and fix at the chokepoint. |
| EDGE-24 | A pending offload at loop shutdown raises a library-attributable exception (e.g. a `from_thread` callback into a dead loop). | None expected for the current design (`offload` uses `async with limiter` + `on_dispatch` on the loop thread, no `from_thread` bridge on the hot path). If red: ensure no worker→loop callback runs after teardown; the fix would guard the `on_dispatch`/watcher bridge. Note: `_cancel.py` docstring mentions a `from_thread` bridge but `_offload.py` runs `on_dispatch` synchronously on the loop thread (`async with limiter`), so the classic dead-loop-callback trap does not apply — this is the load-bearing reason EDGE-24 is expected clean. |

**Planner action:** carry one `checkpoint`-style contingency note per EDGE group: "if the RED test cannot be made GREEN by test-only means, the minimal production fix above lands in this phase, not a later milestone." Sequence tests RED-first (Phase 29/30/31 rhythm) so a genuine gap surfaces before any GREEN claim.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| anyio | All tests | ✓ | 4.14.1 | — |
| trio | Dual-backend leg | ✓ | 0.33.0 | — |
| aiotools | asyncio virtual clock | ✓ | 2.2.3 | — |
| DuckDB driver | EDGE-24 real-pool leg, deterministic-drain legs | ✓ (used across the suite) | (in-proc) | Stub legs cover the wiring; DuckDB is the real-pool proof |
| pandas / polars | `fetch_df`/`fetch_polars` positive legs (if any real-frame EDGE leg) | ✓ (dev group) | pandas>=2.0, polars>=1.0 | `importorskip`; stub `fetch_df`/`fetch_polars` need no real frame |
| Snowflake driver / cassette | Not needed this phase | n/a | — | EDGE suite is DuckDB + stub; no Snowflake leg required (streaming cassette can't replay — A1, Phase 29) |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None blocking — Snowflake is not needed for these six EDGE items.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — this section is required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + anyio pytest plugin (`@pytest.mark.anyio`) + pytest-repeat + pytest-timeout |
| Config file | `pyproject.toml` (dev group deps); async fixtures in `tests/async/conftest.py` |
| Quick run command | `.venv/bin/pytest tests/async/test_edge_*.py -x -q` |
| Full suite command | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/ -q` (the x20 loop gate; run on Linux CI for the cancel/shutdown legs) |

### Phase Requirements → Test Map (Nyquist sampling)
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EDGE-08 | Cancel set before a new-method offload is delivered at the offload boundary; `fn` never runs; both backends (trio = discriminator) | unit (dual-backend) | `.venv/bin/pytest tests/async/test_edge_checkpoint.py -x` | ❌ Wave 0 |
| EDGE-13 | contextvar set before a new-method offload is visible in the worker | unit (dual-backend) | `.venv/bin/pytest tests/async/test_edge_contextvars.py -k copied_in -x` | ❌ Wave 0 |
| EDGE-14 | worker contextvar mutation does not leak back to the caller after the offload | unit (dual-backend) | `.venv/bin/pytest tests/async/test_edge_contextvars.py -k no_leak -x` | ❌ Wave 0 |
| EDGE-31 | `move_on_after(0)` still cancels a blocked streaming pull / ingest (`adbc_cancel` once, invalidate) | integration (dual-backend, looped) | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_edge_timeout_precision.py -k move_on_after_zero` | ❌ Wave 0 |
| EDGE-32 | op completing at deadline−ε is NOT over-cancelled (no `adbc_cancel`, no invalidate, clean return) — streaming pull + ingest | integration (dual-backend, looped) | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_edge_timeout_precision.py -k deadline_epsilon` | ❌ Wave 0 |
| EDGE-24 | open pool / pending offload at loop shutdown (mid-stream + mid-ingest) raises no library-attributable exception; trio nursery canary | integration (dual-backend, looped) | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_edge_shutdown.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/async/test_edge_*.py -x -q` (fast, single iteration)
- **Per wave merge:** `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/ -q` (the 0-hang loop gate)
- **Phase gate:** Full async suite green under the x20 loop on **Linux CI** (the real gate for EDGE-24/31/32 — cancel/lost-wakeup races can pass 20/20 on macOS but hang on Linux, per MEMORY platform-dependent-lost-wakeup) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/async/test_edge_checkpoint.py` — EDGE-08 (both backends; trio discriminator marked)
- [ ] `tests/async/test_edge_contextvars.py` — EDGE-13 + EDGE-14 (no gating needed; simplest legs)
- [ ] `tests/async/test_edge_timeout_precision.py` — EDGE-31 + EDGE-32 on streaming pull + ingest (`virtual_clock` triggers, `real_clock_watchdog` guard, `concurrency_marks`)
- [ ] `tests/async/test_edge_shutdown.py` — EDGE-24 mid-stream + mid-ingest, warnings-capture, trio canary, `concurrency_marks`
- [ ] Framework install: none — pytest-repeat/pytest-timeout/anyio/trio/aiotools all present
- [ ] Possible one-line stub probe for EDGE-13 contextvar read (Claude's discretion, Pattern 1(a)); otherwise none

*(No new fixtures required: `make_stub_async_connection`, `duckdb_async_pool`, `anyio_backend`, `await_inside`, `real_clock_watchdog`, `virtual_clock`, `concurrency_marks` all exist and are reused.)*

## Security Domain

> `security_enforcement` is not disabled in config; included for completeness.

This is a **test-only** phase over an in-process ADBC offload layer. No new attack surface, no auth/session/access-control/crypto, no network I/O, no untrusted input parsing.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no auth code) |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | no | Tests use fixed literals / `object()` sentinels; no untrusted input |
| V6 Cryptography | no | — (no crypto) |
| V7 Error Handling & Logging | yes (indirect) | The phase *asserts* correct error/cancel propagation (no swallowing, no library-attributable exception at shutdown) — a robustness property, not a new control |

### Known Threat Patterns for {async offload test layer}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cancellation swallowed → resource leak / hang | Denial of Service | Assert `adbc_cancel` fires + invalidate + no swallow (existing D-25-06 discipline; extended to new paths) |
| Pending offload callback into a dead loop at shutdown | Denial of Service | EDGE-24 asserts no library-attributable exception; `offload` runs `on_dispatch` on the loop thread (no dead-loop `from_thread` bridge on the hot path) |
| Context bleed across tasks via leaked contextvar | Information Disclosure | EDGE-14 asserts worker mutations do not leak back (anyio `copy_context` guarantee) |

No new mitigations are introduced; the phase *verifies* existing ones on the new paths.

## Sources

### Primary (HIGH confidence)
- Installed `anyio` 4.14.1 — `to_thread.run_sync` source read directly (`abandon_on_cancel`/`cancellable` deprecation live); contextvar copy-in + no-leak-back + checkpoint-at-offload **verified empirically on both backends this session** (three standalone `anyio.run` probes) — HIGH
- Repo source read directly: `_async/_offload.py`, `_async/_cancel.py`, `_async/_reader.py` (all new-method paths route through the shared `offload`/`cancellable_offload` chokepoint) — HIGH
- Repo test suite read directly: `test_edge_cancel_depth.py`, `test_reader_cancel.py`, `test_edge_resource.py`, `test_reader_resource.py`, `test_edge_backend_parity.py`, `test_edge_loophygiene.py` (the green analogs to clone) — HIGH
- Harness read directly: `tests/_async_harness/stubs.py`, `clock.py`, `gating.py`; `tests/async/conftest.py`, `_edge_helpers.py` (confirms all four new-method stubs + counters + fixtures exist) — HIGH
- `.planning/research/ASYNC-EDGE-CASES.md` — the full per-EDGE designs (EDGE-08/13/14/24/31/32 descriptions + deterministic-test recipes) — HIGH
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` §Phase 32, `.planning/STATE.md`, Phase 29/31 CONTEXT.md — requirement definitions, success criteria, locked decisions, carried-forward gotchas — HIGH

### Secondary (MEDIUM confidence)
- `.venv/bin/python importlib.metadata.version(...)` — exact installed versions (anyio 4.14.1, trio 0.33.0, aiotools 2.2.3) — HIGH for the versions; MEDIUM only in that anyio behavior across a future minor could drift (mitigated by the empirical probes)

### Tertiary (LOW confidence)
- None — no claim in this document rests on WebSearch or unverified training knowledge; the anyio guarantees were checked against the installed runtime rather than the docs alone.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all versions read from the installed `.venv`
- Architecture (chokepoint-sharing, test patterns): HIGH — every path and analog read directly from source
- anyio guarantees (EDGE-08/13/14): HIGH — verified empirically on both backends this session
- Timing/shutdown (EDGE-24/31/32 "no production change expected"): MEDIUM-HIGH — reuses proven machinery, but these are first-time-on-new-paths; the explicit contingency covers the residual risk
- Pitfalls: HIGH — all four are documented, carried-forward project learnings with green-test evidence

**Research date:** 2026-07-02
**Valid until:** 2026-08-01 (stable — pinned deps, internal test layer; revisit only on an anyio major/minor bump that touches `to_thread` semantics)
