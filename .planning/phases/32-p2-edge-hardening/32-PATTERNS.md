# Phase 32: P2 Edge Hardening - Pattern Map

**Mapped:** 2026-07-02
**Files analyzed:** 4 new test modules (test-only phase; no production files expected)
**Analogs found:** 4 / 4 (all exact — every new module clones a green sibling in `tests/async/`)

## Scope Note (read first)

This is a **test-only** phase. The four files to CREATE are async edge-test modules; every one of them clones an already-green analog verbatim and swaps only the offloaded method (`execute`/`fetch_arrow_table` → `adbc_ingest` / `fetch_df` / `fetch_polars` / `fetch_record_batch` pull). **No harness change is expected** — all four new-method stubs, their counters, and every fixture already exist. The single discretionary harness touch is the EDGE-13 contextvar worker-probe, for which a zero-change mechanism already exists (`BlockingStubCursor.register_on_enter` / `on_enter`, see Shared Pattern E).

The planner must preserve, in every new module, the four load-bearing conventions shared by all analogs (see Shared Patterns A–D): the `importlib` sibling-helper import block, `pytestmark = concurrency_marks`, `real_clock_watchdog` (never `anyio.fail_after`) as the hang guard, and `virtual_clock` as the deadline *trigger*.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `tests/async/test_edge_checkpoint.py` (EDGE-08) | test (unit, dual-backend) | event-driven (cancel-at-offload) | `tests/async/test_edge_cancel_depth.py::test_cancel_before_offload_is_clean` | exact (swap `execute`→`adbc_ingest`) |
| `tests/async/test_edge_contextvars.py` (EDGE-13/14) | test (unit, dual-backend) | transform (context copy-in/no-leak-back) | `tests/async/test_edge_cancel_depth.py` (import block + shape) + harness `register_on_enter` | role-match (simplest legs; no gating) |
| `tests/async/test_edge_timeout_precision.py` (EDGE-31/32) | test (integration, dual-backend, looped) | request-response + streaming (deadline precision) | `tests/async/test_reader_cancel.py` + `test_ingest_cancel.py` (EDGE-31) & `test_edge_cancel_depth.py::test_move_on_after_on_finished_op_is_noop` (EDGE-32) | exact |
| `tests/async/test_edge_shutdown.py` (EDGE-24) | test (integration, dual-backend, looped) | event-driven (loop-teardown cleanliness) | `tests/async/test_reader_resource.py` (warnings-capture) + `test_reader_cancel.py`/`test_ingest_cancel.py` (release-in-teardown gating) | role-match |

## Pattern Assignments

### `tests/async/test_edge_checkpoint.py` (EDGE-08)

**Analog:** `tests/async/test_edge_cancel_depth.py::test_cancel_before_offload_is_clean` (lines 90-116). Clone the choreography exactly; swap `cur.execute("SELECT 1")` for a new-method call (`cur.adbc_ingest("t", object())` per RESEARCH Code Example), and assert the new method's counter (`ingest_call_count`) stayed at 0. Mark trio as the discriminator (do NOT `del anyio_backend_name` if you want to assert the trio leg specifically; the analog deletes it because both legs assert identically — keep that, but note in a docstring that trio is the discriminating backend per RESEARCH §Pattern-1).

**Arrange/trigger/assert skeleton to clone** (`test_edge_cancel_depth.py:104-116`):
```python
async_conn, stub_conn = make_stub_async_connection()
cur = async_conn.cursor()
sc = stub_conn.cursors[0]
with real_clock_watchdog(stub_conn.cursors) as tripped:
    with anyio.CancelScope() as scope:
        scope.cancel()  # cancel BEFORE entering the offload; no intervening await
        await cur.execute("SELECT 1")   # <-- SWAP to: await cur.adbc_ingest("t", object())
assert tripped[0] is False
assert sc.execute_call_count == 0      # <-- SWAP to: sc.ingest_call_count == 0
assert sc.adbc_cancel_call_count == 0
assert stub_conn.invalidate_call_count == 0
assert sc.observed_cancel is False
```

**RESEARCH-provided variant (EDGE-08, verified this session)** wraps the awaited call in `pytest.raises(anyio.get_cancelled_exc_class())` — the analog does not, because a pre-cancelled `CancelScope` swallows the cancellation at scope exit. Prefer the analog's bare form unless the planner wants to assert the cancel identity surfaces (then use the RESEARCH form with a `task_group` instead of a self-cancelling scope). Either satisfies EDGE-08; the load-bearing assertion is `ingest_call_count == 0` (fn never ran).

---

### `tests/async/test_edge_contextvars.py` (EDGE-13/14)

**Analog:** the import block + `@pytest.mark.anyio` shape from `test_edge_cancel_depth.py`; the worker-probe mechanism from harness `BlockingStubCursor.register_on_enter` (Shared Pattern E). **No `real_clock_watchdog`, no `virtual_clock`, no `concurrency_marks`, no gating** — these are deterministic single-offload assertions (RESEARCH §Pattern-1: "EDGE-13/14 need NO gating").

**Verified worker body (RESEARCH Code Example, both backends):**
```python
import contextvars, anyio
_cv = contextvars.ContextVar("trace")

def _worker():          # runs on the worker thread
    seen = _cv.get("MISSING")
    _cv.set("inner")    # must NOT leak back
    return seen
# EDGE-13: seen == "outer" (copied in);  EDGE-14: caller _cv.get() == "outer" (no leak back)
```

**Mechanism (Claude's discretion — RESEARCH Open Question 1):**
- **Pattern 1(a) — preferred, on a real new-method path:** set the module `ContextVar` before `await cur.fetch_df()`, and route the worker-side read through `stub_cursor.register_on_enter(probe)` (Shared Pattern E). The `on_enter` hook fires **from inside `_block` on the worker thread** (`stubs.py:747-749`), so a probe that does `seen.append(_cv.get("MISSING"))` there records the copied-in value (EDGE-13); after the offload returns, assert the caller's `_cv.get() == "outer"` (EDGE-14). Requires **zero stub edits** — `register_on_enter` already exists. Release the stub in a `finally` so the `fetch_df` worker returns.
- **Pattern 1(b) — zero-harness, chokepoint-direct:** `await offload(_worker, limiter=anyio.CapacityLimiter(1))` directly (import from `adbc_poolhouse._async._offload`, as `test_edge_cancel_depth.py:502` does), with a comment that this is the shared chokepoint every new method routes through. Less end-to-end; use only if the `register_on_enter` probe is rejected in review.

**`offload` import precedent** (`test_edge_cancel_depth.py:502`):
```python
offload = importlib.import_module("adbc_poolhouse._async._offload").offload
```

---

### `tests/async/test_edge_timeout_precision.py` (EDGE-31/32)

**Analogs:** `test_reader_cancel.py::test_timeout_during_pull_aborts_and_invalidates` (lines 93-127, streaming pull) and `test_ingest_cancel.py::test_timeout_during_ingest_aborts_and_invalidates` (lines 96-127, ingest) for EDGE-31; `test_edge_cancel_depth.py::test_move_on_after_on_finished_op_is_noop` (lines 319-351) for EDGE-32. Set `pytestmark = concurrency_marks` (Shared Pattern B).

**EDGE-31 — `move_on_after(0)` still cancels a blocked pull** (clone `test_reader_cancel.py:107-127`, swap `fail_after(5)` → `move_on_after(0)` per RESEARCH §Pattern-2). **Pitfall 5:** arm a pending batch BEFORE `fetch_record_batch()` or the pull never blocks:
```python
async_conn, stub_conn = make_stub_async_connection()
cur = async_conn.cursor()
stub_conn.cursors[-1].record_batch_batches = [object()]   # <-- Pitfall 5: pending batch opens the window
with (
    real_clock_watchdog(stub_conn.cursors) as tripped,     # NEVER fail_after as watchdog
    virtual_clock(anyio_backend_name),
):
    reader = await cur.fetch_record_batch()
    sc = stub_conn.cursors[-1]
    with anyio.move_on_after(0) as scope:                   # already-expired deadline
        await reader.__anext__()
assert tripped[0] is False
assert scope.cancelled_caught is True
assert sc.adbc_cancel_call_count == 1
assert stub_conn.invalidate_call_count == 1
```
The ingest twin is identical but swaps the reader pull for `await cur.adbc_ingest(...)` gated inside a `task_group` (clone `test_ingest_cancel.py::_drive_ingest`, lines 163-165).

**EDGE-32 — op finishing at deadline−ε is NOT over-cancelled** (clone `test_edge_cancel_depth.py:319-351`). The releaser MUST be a REAL side thread (`_release_when_entered`, Shared Pattern C / Pitfall 2 — a loop-side releaser is starved under `MockClock`):
```python
releaser = threading.Thread(target=_release_when_entered, args=(sc,), daemon=True)
releaser.start()
# ... start the gated new-method op, let the real thread release it before the large deadline fires
assert scope.cancelled_caught is False
assert sc.adbc_cancel_call_count == 0
assert stub_conn.invalidate_call_count == 0
```
Copy `_release_when_entered` **verbatim** from `test_edge_cancel_depth.py:73-84`.

---

### `tests/async/test_edge_shutdown.py` (EDGE-24)

**Analogs:** `test_reader_resource.py` (lines 55-113) for the `warnings.catch_warnings(record=True)` + `simplefilter("always")` + offending-warning-filter idiom; `test_reader_cancel.py:80-90` / `test_ingest_cancel.py:84-91` for the **release-in-teardown** gating (Pitfall 3 — `abandon_on_cancel=False` turns an unreleased worker into a join-hang). Set `pytestmark = concurrency_marks`.

**RESEARCH shape (mid-ingest at shutdown), clone this:**
```python
async_conn, stub_conn = make_stub_async_connection()
cur = async_conn.cursor()
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    async with anyio.create_task_group() as tg:
        tg.start_soon(functools.partial(cur.adbc_ingest, "t", object()))
        await await_inside(lambda: stub_conn.cursors[0].ingest_call_count == 1)
        for c in stub_conn.cursors:      # release so teardown JOINS the worker cleanly (Pitfall 3)
            c.release()
offending = [w for w in caught
             if "was never awaited" in str(w.message)
             or "Task was destroyed" in str(w.message)]
assert offending == []
```
**Offending-warning filter idiom** (from `test_reader_resource.py:107-113`) — clone the list-comprehension shape, widen to the two shutdown strings above. trio's nursery strictness is the canary leg (RESEARCH §Pattern-3); keep both backends.

**Mid-stream twin:** same shape but `tg.start_soon(_drain_one, reader)` after arming `record_batch_batches = [object()]` and gate on `read_call_count >= 1` (see `test_reader_cancel.py::_pull_started`, lines 167-171).

**Real-driver leg (drained close):** use `duckdb_async_pool`; open a connection, run a real op, drain it, and assert `await pool.close()` (or fixture teardown) raises nothing. Model on `test_reader_cancel.py::test_invalidate_drains_pool_duckdb` (lines 133-159) for the real-pool `checkedout()` discipline. Do NOT race a genuinely-wedged worker (RESEARCH Pitfall 3 / A3).

---

## Shared Patterns

### A. Sibling-helper import block (ALL four new modules)
**Source:** `test_edge_cancel_depth.py:59-70`, `test_reader_cancel.py:41-47`, `test_ingest_cancel.py:44-51`
**Apply to:** every new module. `tests/async/` cannot be imported dotted (`async` is a keyword), so helpers load via `importlib`:
```python
import functools, importlib, threading
import anyio, pytest
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
virtual_clock = importlib.import_module("tests._async_harness.clock").virtual_clock
pytestmark = _helpers.concurrency_marks
```
(EDGE-13/14 module omits `virtual_clock`, `real_clock_watchdog`, and `pytestmark` — it needs no gating.)

### B. `concurrency_marks` on every concurrency-sensitive module
**Source:** `tests/async/_edge_helpers.py:56-59` — `[pytest.mark.repeat(ADBC_ASYNC_REPEAT), pytest.mark.timeout(ADBC_ASYNC_TIMEOUT_S)]`
**Apply to:** `test_edge_checkpoint.py`, `test_edge_timeout_precision.py`, `test_edge_shutdown.py`. Codifies the x20 loop / 0-hang gate (MEMORY loop-flaky lesson). **Not** on `test_edge_contextvars.py`.

### C. `real_clock_watchdog` as the hang guard — NEVER `anyio.fail_after`
**Source:** `tests/async/_edge_helpers.py:62-102`; releaser `_release_when_entered` at `test_edge_cancel_depth.py:73-84`
**Apply to:** every gated leg (`with real_clock_watchdog(stub_conn.cursors) as tripped:` … `assert tripped[0] is False`). Under trio `MockClock(autojump_threshold=0)` a virtual `fail_after` autojumps and trips every run (Pitfall 1). The EDGE-32 happy-path release MUST come from a REAL side thread (`_release_when_entered`), never a loop task (Pitfall 2).

### D. `virtual_clock` as the deadline TRIGGER only
**Source:** `tests/_async_harness/clock.py:36-77`; used at `test_reader_cancel.py:113-116`, `test_edge_cancel_depth.py:383-386`
**Apply to:** EDGE-31/32 timeout legs. `with virtual_clock(anyio_backend_name):` makes `anyio.move_on_after`/`fail_after` fire instantly on both backends. It is the trigger under test, never the watchdog (that stays Shared Pattern C).

### E. New-method stub surface (the harness the new tests drive — NO change expected)
**Source:** `tests/_async_harness/stubs.py`
**Apply to:** all legs. The four new-method stubs + counters already exist:
| Method (stub) | Counter | Location |
|---------------|---------|----------|
| `BlockingStubCursor.adbc_ingest` | `ingest_call_count` | `stubs.py:397-441` |
| `BlockingStubCursor.fetch_df` | `df_call_count` | `stubs.py:340-371` |
| `BlockingStubCursor.fetch_polars` | `polars_call_count` | `stubs.py:373-395` |
| `BlockingStubCursor.fetch_record_batch` → `BlockingStubReader` | `read_call_count` (reader), `record_batch_batches` (cursor default) | `stubs.py:504-551`, reader `755-794` |
| `BlockingStubCursor.adbc_cancel` / `close` / `release` | `adbc_cancel_call_count` / `close_call_count` | `stubs.py:443-502` |
| `BlockingStubConnection.invalidate` | `invalidate_call_count` | `stubs.py:890-893` |

All new-method stubs park on the SAME sticky-release `_block` gate as `execute`, so `adbc_cancel`/`close`/`release` unblock them through existing machinery. **EDGE-13 worker probe:** `BlockingStubCursor.register_on_enter(callback)` (`stubs.py:232-261`) registers a per-thread hook that `_block` fires **on the worker thread, inside the blocked section** (`stubs.py:747-749`) — the clean, zero-edit place to read the copied-in contextvar. Returns a cleanup callable; call it in a `finally`.

### F. Fixtures (all exist — no new fixtures)
**Source:** `tests/async/conftest.py`
- `make_stub_async_connection` (lines 155-194) → `(async_conn, stub_conn)`; stub cursors via `stub_conn.cursors[...]`.
- `duckdb_async_pool` (lines 87-106) → real-driver pool, closed on teardown; use for EDGE-24 real drained-close and any real-frame leg.
- `anyio_backend` (lines 58-84) → asyncio + trio-with-`MockClock(autojump_threshold=0)`; every `@pytest.mark.anyio` test runs once per backend. Function-scoped (fresh clock per test).

## No Analog Found

None. Every new module has an exact or role-match sibling in `tests/async/`. This is a coverage-extension phase: the choreography is proven; only the offloaded method changes.

## Metadata

**Analog search scope:** `tests/async/` (38 modules) + `tests/_async_harness/` (stubs, clock, gating, conftest)
**Files scanned (read in full or targeted):** `32-RESEARCH.md`, `_edge_helpers.py`, `test_reader_cancel.py`, `test_edge_resource.py`, `test_reader_resource.py`, `test_edge_cancel_depth.py`, `test_ingest_cancel.py`, `test_edge_backend_parity.py`, `conftest.py`, `clock.py`, `stubs.py` (structure + method bodies + `register_on_enter`)
**Pattern extraction date:** 2026-07-02
