# Pitfalls Research

**Domain:** Adding an optional anyio thread-offload async API over a sync ADBC + SQLAlchemy QueuePool library (adbc-poolhouse v1.4.0)
**Researched:** 2026-06-25
**Confidence:** HIGH on the ADBC thread-safety + cancellation facts (official ADBC concurrency spec + dbapi reference), HIGH on anyio cancellation/limiter semantics (official anyio docs), MEDIUM on the GIL-release premise (load-bearing for the milestone, but not explicitly documented per-method — must be validated empirically).

This document is opinionated and specific to *this* change: wrapping `create_pool()` / `QueuePool.connect()` / cursor `execute`/`fetch*`/`fetch_arrow_table` with `anyio.to_thread.run_sync`, behind an `[async]` extra, generic across all 13 backends. Pitfalls are ordered by threat to **correctness** first (cancellation, thread-affinity, leaks), then concurrency throughput, then cosmetics (typing, testing).

## The Two Load-Bearing Facts (read first)

Everything below rests on two verified facts from the ADBC spec:

1. **ADBC objects are NOT thread-safe.** Official wording: *"Objects allow serialized access from multiple threads: one thread may make a call, and once finished, another thread may make a call. They do not allow concurrent access from multiple threads."* and *"Connections are not thread-safe... clients should take care to serialize accesses to a connection."* — [ADBC concurrency](https://arrow.apache.org/adbc/main/cpp/concurrency.html), [dbapi reference](https://arrow.apache.org/adbc/main/python/api/adbc_driver_manager.html). **Serialized cross-thread access is allowed; concurrent access is not.** This is the difference between "safe" and "unsafe" for the whole design.

2. **`adbc_cancel` is the single documented exception** — it *is* thread-safe and is explicitly designed to be called from another thread to interrupt an in-progress query: *"Cancel execution of an in-progress query. This can be called during AdbcStatementExecuteQuery... This must always be thread-safe (other operations are not)."* — [ADBC statement API](https://arrow.apache.org/adbc/main/cpp/api/group__adbc-statement.html). This is what makes cooperative cancellation over `to_thread` viable at all.

---

## Critical Pitfalls

### Pitfall 1: Cancelled await leaves the query running and the connection mid-operation (silent pool corruption)

**What goes wrong:**
A caller does `with anyio.fail_after(5): await acur.execute(slow_sql)` (or the surrounding task is cancelled). The await unblocks immediately, but **the ADBC call keeps running on its worker thread**. anyio is explicit: with `abandon_on_cancel=True`, *"the thread will still continue running – only its outcome will be ignored"* ([anyio threads](https://anyio.readthedocs.io/en/stable/threads.html)). The connection is now mid-`execute`. If the async wrapper's `finally` returns it to the QueuePool, the next checkout gets a connection with a live query on it → concurrent access from two threads → exactly the undefined behaviour ADBC forbids. If instead the wrapper closes/discards it, you leak the in-flight statement until the query finishes.

**Why it happens:**
Developers assume async cancellation == OS-thread interruption (true for native-async drivers like asyncpg, false for thread-offloaded sync code). The default `to_thread.run_sync` actually *shields* the thread from cancellation entirely, so a naïve wrapper makes timeouts silently not work; switching to `abandon_on_cancel=True` makes the await cancellable but abandons a still-running thread holding a pool connection.

**How to avoid:**
Wire `adbc_cancel` to the anyio cancel scope. The correct shape:
- Run the blocking call in the worker thread.
- In the event-loop task, race it against cancellation; on cancel, call `connection.adbc_cancel()` / `cursor.adbc_cancel()` from the loop thread (legal — cancel is the thread-safe exception). The native call then returns `ADBC_STATUS_CANCELLED` and the worker thread unwinds.
- Only after the worker thread has actually returned (cancelled or not) may the connection be returned to the pool. Use anyio structured concurrency so the offloaded call is *joined* before the scope exits, rather than abandoned.
- If `adbc_cancel` is unavailable or the join times out, **invalidate** the connection (`connection_record.invalidate()` / detach it) instead of returning a possibly-busy connection to the pool.
Concretely: prefer NOT using `abandon_on_cancel=True` blindly; instead structure a task group where one task runs the sync call and a cancellation handler calls `adbc_cancel`, then await the worker's completion.

**Warning signs:**
Timeouts that "work" (await returns fast) but warehouse query logs show the query ran to completion; intermittent "connection is busy"/concurrent-access errors after a timeout; pool slowly losing capacity under load with cancellations; tests that cancel and immediately reuse a connection passing only because the underlying op was fast.

**Phase to address:** Cancellation phase (dedicated, after the basic offload wrapper exists). This is the single highest-risk item; it deserves its own phase with deterministic cancellation tests (see Pitfall 12). Recovery cost if shipped wrong: HIGH (data races, intermittent corruption in production).

---

### Pitfall 2: Treating ADBC connection/cursor as thread-affine OR as concurrently-shareable — both are wrong

**What goes wrong:**
Two opposite mistakes, both fatal:
- *Over-strict:* assuming an ADBC connection is pinned to one OS thread (like SQLite default or some embedded drivers), and therefore trying to build per-thread connection affinity on top of `to_thread` (which deliberately reuses a pool of ~40 threads and gives no per-call thread guarantee).
- *Over-loose:* assuming "the GIL makes it safe" and letting two awaited offloads touch the *same* connection concurrently (e.g. two coroutines sharing one `AsyncConnection` both calling `execute`). ADBC explicitly forbids concurrent access; the GIL does **not** save you because the driver releases the GIL during the native call, so two threads genuinely run in the driver at once.

**Why it happens:**
The "objects allow serialized access from multiple threads" wording is subtle. It means: a connection *can* legally move between threads as long as calls never overlap. `to_thread` satisfies this *only if you also serialize calls per connection*. Developers conflate "thread-safe" with "concurrency-safe."

**How to avoid:**
- Treat ADBC objects as **migratable but strictly serialized**: never pin to a thread (that fights `to_thread`), but enforce one-in-flight-call-per-connection.
- Put a per-connection **anyio.Lock** inside the `AsyncConnection`/`AsyncCursor` wrapper. Every offloaded method acquires the lock before `to_thread.run_sync` and releases after. This guarantees serialized access regardless of which worker thread runs the call. (The cancellation handler calling `adbc_cancel` is the deliberate exception — it must NOT take the lock, since it runs concurrently by design.)
- Document that an `AsyncConnection` is single-logical-owner: one task uses it at a time; share the *pool*, not the connection.

**Warning signs:**
Sporadic segfaults / `ADBC_STATUS_INTERNAL` / corrupted Arrow buffers under concurrency; failures that vanish when `pool_size=1` or when tests run serially; "works on DuckDB, crashes on Snowflake" (driver-dependent tolerance to the violation).

**Phase to address:** Core async wrapper phase (the connection/cursor wrapper must ship the per-connection lock from day one, not bolt it on later).

---

### Pitfall 3: The GIL-release premise is unvalidated for the operations that matter

**What goes wrong:**
The milestone's entire justification is *"ADBC releases the GIL, so thread-offload yields real concurrency."* This is true for the native query execution in the Rust/C/Go drivers, but **result materialization on the Python side may not release it**: building Python row tuples in `fetchall()`, and especially pyarrow's construction of `RecordBatch`/`Table` objects in `fetch_arrow_table()`, run Python/C-API code that re-acquires the GIL. If a workload is fetch-heavy (large result sets converted to Arrow), the "parallel" offloads serialize on the GIL during materialization and you get little speedup while paying thread-hop overhead.

**Why it happens:**
"ADBC releases the GIL" gets over-generalized to "every ADBC method is parallel." The blocking *I/O/compute in the driver* releases it; the *Python object construction* around it does not, and that's often where the time goes for analytical result sets.

**How to avoid:**
- Validate empirically **before** building the full surface: a micro-benchmark in an early phase running N concurrent slow queries vs. N concurrent large-fetches, measuring wall-clock vs. ideal. Confirm execute/network-bound ops parallelize; measure how much fetch/Arrow-conversion ops do.
- Set honest expectations in docs: async wins are largest for **latency-bound / I/O-bound** queries (round-trips to Snowflake/BigQuery/Databricks), smaller for **CPU-bound large-result materialization**.
- Do NOT claim blanket parallelism in the async guide. Qualify per-operation.

**Warning signs:**
Benchmarks showing async no faster (or slower) than sync for `fetch_arrow_table` on big results; CPU pinned at one core during "concurrent" fetches; thread-hop overhead dominating for tiny queries.

**Phase to address:** Feasibility/spike phase at the very start of the milestone — this premise gates whether the design needs adjusting (e.g. documenting limits, or offloading in coarser chunks). MEDIUM confidence; treat as a must-verify.

---

### Pitfall 4: Connection not returned/invalidated on exception or cancellation (pool starvation)

**What goes wrong:**
The sync API returns connections via SQLAlchemy's `reset` event (the existing `_release_arrow_allocators` listener closes open cursors on every checkin/invalidate path). An async wrapper that does the checkout in `to_thread` but the cleanup in Python `finally` can desynchronize: an exception or cancellation between "checked out" and "wrapped in async context manager" leaks the raw `_ConnectionFairy` — it never returns to the pool. After `pool_size + max_overflow` such leaks, every `await pool.connect()` blocks for `timeout` then raises `TimeoutError`. Cancellation makes this worse because the `finally` may itself be interrupted if not shielded.

**Why it happens:**
There's a gap between the offloaded checkout completing and control returning to the event loop where the `async with` is established. Cancellation can land in that gap. Naïve `try/finally` in async code can have its cleanup cancelled.

**How to avoid:**
- Mirror the sync ownership model exactly: the `AsyncConnection.__aexit__` must call the same return path that the sync `_ConnectionFairy.close()` triggers, so the existing `reset` event (and thus `_release_arrow_allocators`) still fires. Async cleanup must be **symmetric** with the sync reset event, not a parallel ad-hoc path.
- Shield checkin/close from cancellation: wrap the return-to-pool in `with anyio.CancelScope(shield=True):` so a cancellation during `__aexit__` cannot abandon the connection.
- On any exception during async use, prefer `invalidate()` over `close()` if the connection may be mid-operation (ties into Pitfall 1).
- Provide `managed_async_pool()` / `acquire()` context managers so consumers can't forget cleanup; make the raw `await pool.connect()` return an object whose `__aexit__` is the only sanctioned return path.

**Warning signs:**
`QueuePool limit ... overflow ... reached, connection timed out` after running for a while; pool `.checkedout()` count never returning to 0; leaks appearing only on the error/cancel paths in tests, not the happy path.

**Phase to address:** Core async wrapper phase for the happy/exception path; the cancellation-shield aspect lands with the Cancellation phase.

---

### Pitfall 5: Arrow record batches / readers not freed → unbounded native memory growth

**What goes wrong:**
ADBC streams results through Arrow `RecordBatchReader`s held by open cursors (the sync code already knows this — `_release_arrow_allocators` iterates `dbapi_conn._cursors` and closes them on reset). In the async layer, if an `AsyncCursor` is GC'd without its `close()` being awaited/run, or if a partially-consumed `fetch_arrow_table` reader isn't released, native Arrow allocators stay alive. Across many short-lived async cursors this leaks C++/Rust-side memory invisible to Python's GC.

**Why it happens:**
Python `__del__` on the async wrapper can't reliably run the offloaded `close()` (you can't `await` in `__del__`, and the event loop may be gone). The sync safety net (reset event closing cursors) only fires when the connection actually returns to the pool — if the async wrapper holds the connection open across many cursor operations, batches accumulate before reset.

**How to avoid:**
- Make `AsyncCursor` an async context manager; close it in `__aexit__` via `to_thread`. Encourage `async with conn.cursor() as cur:`.
- Ensure the connection-return path still triggers the existing `reset` listener so any straggler cursors are closed (don't bypass it).
- For `fetch_arrow_table` / streaming readers, fully consume or explicitly close the reader inside the offloaded call; don't hand a live reader back across the await boundary unless you also give it an async-closing wrapper.
- Add a fallback `del`-time warning (not cleanup) if a cursor is GC'd un-closed, to surface leaks in tests.

**Warning signs:**
RSS climbing under sustained async load while Python heap stays flat; `pyarrow` allocator stats growing; leaks that disappear when forcing `pool.dispose()`.

**Phase to address:** Core async wrapper phase (cursor lifecycle), verified in the Testing phase with a memory-stability test.

---

### Pitfall 6: anyio default CapacityLimiter (40, process-wide) mismatched with pool size, plus deadlock from nested offloads

**What goes wrong:**
`to_thread.run_sync` defaults to a **single process-wide limiter of 40 tokens**, shared by *all* offloaded work in the app, not just this library ([anyio threads](https://anyio.readthedocs.io/en/stable/threads.html)). Three failure modes:
- *Throughput cap:* if a consumer sets `pool_size + max_overflow > 40` expecting that many concurrent queries, they're silently throttled to 40 worker threads (minus whatever else in their app uses `to_thread`).
- *Starvation:* unrelated `to_thread` usage elsewhere in the consumer's app competes for the same 40 tokens with this library's queries.
- *Deadlock via nesting / hold-while-offload:* if an offloaded function itself calls back to the loop and awaits another offload, or a task holds a checked-out connection (which consumed a token) and then awaits a *second* offload that needs a token while all 40 are held by tasks each waiting on the first — classic limiter deadlock. Holding a connection while awaiting another offload that needs the limiter is the realistic trigger here.

**Why it happens:**
The limiter is invisible and global. Pool sizing and thread-limiter sizing are two independent knobs that developers assume are the same. Nested offloads are easy to introduce accidentally (e.g. a cleanup that itself offloads).

**How to avoid:**
- Give the library its **own dedicated `CapacityLimiter`** sized to `pool_size + max_overflow`, passed explicitly to every `to_thread.run_sync(..., limiter=self._limiter)`. This isolates the library from the global 40-token pool and aligns thread budget with connection budget so a checked-out connection always has a token to make its next call. Store it on the async pool wrapper.
- Never nest offloads: an offloaded function must be pure sync (no re-entry into the loop, no second `to_thread`). Keep checkout, execute, and checkin as separate top-level offloads coordinated from the loop — not one mega-offload that internally offloads again.
- Document the relationship and let advanced users override the limiter; warn against setting `pool_size` far above the limiter.

**Warning signs:**
Concurrency plateauing at 40 regardless of `pool_size`; hangs that resolve when `pool_size` is reduced below ~40; deadlocks only under high concurrency with cleanup/cancellation in the mix; unrelated parts of the consumer app slowing when poolhouse is busy.

**Phase to address:** Core async wrapper phase (introduce the dedicated limiter with the first offload), stress-tested in the Testing phase.

---

### Pitfall 7: Blocking checkout on an exhausted pool blocks the entire event loop

**What goes wrong:**
SQLAlchemy `QueuePool.connect()` blocks (up to `timeout` seconds) when the pool is exhausted. If the async wrapper calls `pool.connect()` **directly** in a coroutine instead of via `to_thread`, that block freezes the whole event loop — every other coroutine (including ones that would release a connection) stalls, which can self-deadlock: the loop can't make progress to return a connection, so the blocking checkout never unblocks.

**Why it happens:**
`pool.connect()` looks cheap/instant in the common case (a free connection is available), so it's tempting to call it inline. The blocking only manifests under exhaustion, which is exactly the high-load case where it's catastrophic.

**How to avoid:**
- **Every** sync pool/connection/cursor call goes through `to_thread.run_sync` — no exceptions, including `connect()`, `close()`, `dispose()`. Audit for any bare sync call in async code.
- Because checkout is offloaded, it consumes a limiter token while blocking — size the limiter so blocked checkouts don't starve in-flight queries (ties to Pitfall 6). Consider exposing the SQLAlchemy `timeout` so a blocked checkout fails fast rather than holding a token for 30s.
- Add a lint/review rule: in the async module, importing or calling `QueuePool` methods outside a `to_thread` helper is forbidden.

**Warning signs:**
Whole service goes unresponsive under load (not just slow — fully stalled); event-loop "task took N seconds" warnings; deadlock under exhaustion that a larger pool merely postpones.

**Phase to address:** Core async wrapper phase (the offload helper that all calls route through is the prevention).

---

### Pitfall 8: asyncio-only idioms break under trio (the "anyio-neutral" promise is silently violated)

**What goes wrong:**
The milestone promises asyncio+trio neutrality. Reaching for `loop.run_in_executor`, `asyncio.get_event_loop()`, `asyncio.Lock`, `asyncio.wait_for`, `asyncio.to_thread`, or `concurrent.futures` directly will work under asyncio tests and **raise or misbehave under trio** (no asyncio loop exists; `asyncio.Lock` isn't a trio synchronization primitive; `asyncio.to_thread` bypasses the anyio limiter entirely). Mixing `asyncio.to_thread` with anyio also escapes the dedicated limiter from Pitfall 6.

**Why it happens:**
asyncio is the default mental model; its primitives are muscle memory. They appear to work because CI often runs asyncio first.

**How to avoid:**
- Use anyio primitives **exclusively**: `anyio.to_thread.run_sync`, `anyio.Lock`, `anyio.CancelScope`, `anyio.fail_after`, `anyio.from_thread` for any loop callback from a worker. No `import asyncio` in the library at all (enforce with a ruff/import-linter rule banning `asyncio` and `concurrent.futures` in the async module).
- Parametrize the entire async test suite over both backends (`@pytest.mark.anyio` with params `["asyncio", "trio"]`) so a trio break fails CI immediately (see Pitfall 12).
- Any cancellation/cancel-scope code must use anyio cancel scopes, not `asyncio.CancelledError` handling, since trio's cancellation exception differs.

**Warning signs:**
`RuntimeError: no running event loop`, `there is no current event loop`, or trio `TypeError`s only in the trio test leg; cancellation tests passing on asyncio but hanging on trio; `asyncio` appearing in the async module's imports.

**Phase to address:** Core async wrapper phase (set the "anyio-only" rule + import ban up front); enforced continuously by the dual-backend test matrix.

---

### Pitfall 9: Async wrappers typed loosely → basedpyright strict failures and a worse API than the sync side

**What goes wrong:**
Hand-typing each async wrapper as `async def execute(self, *args: Any, **kwargs: Any) -> Any` loses the precise signatures the sync API has and fails the project's basedpyright-strict gate (no implicit `Any`, no untyped returns). Conversely, a generic `to_thread` wrapper helper that returns the wrong awaitable type (`Awaitable` vs `Coroutine`, or losing `R`) produces cascading inference failures.

**Why it happens:**
Typing a function that turns `Callable[P, R]` into `Callable[P, Coroutine[Any, Any, R]]` needs `ParamSpec` + `Concatenate` and is unfamiliar. The 3-overload sync API (`config` / `driver_path` / `dbapi_module`) must be mirrored exactly on the async side, multiplying the surface.

**How to avoid:**
- Type the offload helper precisely: `async def _offload(fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R` (Python ≥3.11 has `ParamSpec`/`Concatenate` natively — no `typing_extensions` needed). Use `Concatenate` when the helper injects `self`/limiter.
- Return `R` from the helper (let `async def` make it a coroutine) rather than annotating a bare `Awaitable`; this preserves the result type for callers.
- Mirror the sync `@overload` sets on `create_async_pool` / `managed_async_pool` one-for-one so the three call patterns keep precise types.
- Run `basedpyright` in CI on the async module from the first commit; don't defer typing to a cleanup phase.

**Warning signs:**
`reportUnknownMemberType` / `reportAny` / `reportUnknownVariableType` from basedpyright on the async module; IDE autocomplete showing `Any` for awaited results; overloads on async functions not matching the sync ones.

**Phase to address:** Core async wrapper phase (typing is part of "done," per the project's strict gate). LOW correctness risk but HIGH gate-blocking risk.

---

## Moderate Pitfalls

### Pitfall 10: `[async]` extra mis-scoped — sync users pay for anyio, or async import fails silently

**What goes wrong:** anyio leaks into the always-installed import path (sync users now require anyio), or the async module imports at top level so `import adbc_poolhouse` fails when `[async]` isn't installed. **Avoid:** keep anyio imports inside the async submodule; guard the public async exports behind a lazy import / `try: import anyio` with a clear `ImportError("install adbc-poolhouse[async]")`; ensure the sync test job runs with anyio *not* installed to catch leakage. **Phase:** Packaging/extra phase.

### Pitfall 11: Async API drifts from sync API (parameters, defaults, behaviour diverge)
**What goes wrong:** `create_async_pool` defaults (`pool_size=5`, `max_overflow=3`, `timeout=30`, `recycle=3600`, `pre_ping=False`) silently diverge from `create_pool`, or the async cursor exposes a different method set. **Avoid:** define the async signatures by referencing the sync defaults (single source of truth); add a test asserting the async public surface mirrors the sync one. **Phase:** Core async wrapper phase + Docs phase.

### Pitfall 12: Async concurrency tests that are flaky or don't actually test cancellation
**What goes wrong:** Sleep-based "concurrency" tests pass/fail nondeterministically; cancellation tests that cancel an already-fast operation prove nothing (the op finished before the cancel). **Avoid:** use anyio's deterministic tools — `anyio.fail_after` with a driver/cassette that blocks predictably; for cancellation, assert the *driver* observed a cancel (`ADBC_STATUS_CANCELLED`) and the connection is cleanly back in the pool, not merely that the await returned. Run the existing pytest-adbc-replay cassettes under both asyncio and trio via `@pytest.mark.anyio` parametrization. Use anyio's `autojump_clock`/checkpoints rather than real `sleep` where possible. Avoid asserting on wall-clock timing for correctness. **Phase:** Testing phase.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| One mega-offload (checkout+execute+fetch+checkin in a single `to_thread`) | Trivial to write; no per-call lock needed | Cancellation can't interrupt mid-way; no concurrency *within* a connection lifecycle; nested-offload deadlock risk if cleanup offloads | Never for the real API; OK only as a throwaway feasibility spike |
| `abandon_on_cancel=True` everywhere instead of wiring `adbc_cancel` | Timeouts "work" immediately | Abandoned threads hold pool connections mid-query → corruption (Pitfall 1) | Never on connection-bearing calls; acceptable only for genuinely fire-and-forget pure-compute offloads |
| Reuse anyio's default global 40-token limiter | One less object to manage | Throughput cap + cross-app starvation + sizing mismatch (Pitfall 6) | Only for a prototype with `pool_size` ≪ 40 and no other `to_thread` users |
| `Any`-typed async wrappers to pass quickly | Fast to a green test run | basedpyright-strict gate fails; worse DX than sync API | Never (project gate forbids) |
| Closing connections instead of invalidating on cancel | Simpler cleanup | Throws away healthy pooled connections on every timeout → pool churn | Acceptable as a conservative interim until `adbc_cancel` join is proven |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| SQLAlchemy `QueuePool` | Reaching for `AsyncAdaptedQueuePool` as the foundation | It's asyncio-bound and does NOT provide thread-offload; use it only as a reference. Keep the sync `QueuePool` and offload around it (per PROJECT.md decision) |
| SQLAlchemy `reset` event | Building a parallel async cleanup path that bypasses `_release_arrow_allocators` | Route async checkin through the same connection-return path so the existing `reset` listener fires — symmetric with sync |
| ADBC `adbc_cancel` | Calling it under the per-connection lock (treating it like a normal op) | Cancel is the documented thread-safe exception — call it concurrently, WITHOUT the serialization lock, from the loop thread |
| ADBC connection | Sharing one `AsyncConnection` across concurrent tasks "because GIL" | Concurrent access is UB even with the GIL (driver releases it); one logical owner per connection + per-connection lock |
| anyio worker thread → loop | Using `asyncio.Event`/queues to signal from worker thread | Use `anyio.from_thread.run_sync`; raw asyncio primitives aren't trio-safe and aren't thread-safe to call into |
| pytest-adbc-replay cassettes | Assuming cassette replay is thread-safe under concurrent offloads | The monkeypatched dbapi may not tolerate concurrent calls; serialize per-connection in tests too, and verify the replay layer under the dual-backend matrix |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| GIL re-acquired during Arrow/row materialization | "Concurrent" big-result fetches don't parallelize; one core pinned | Set expectations: async wins on I/O-bound queries; benchmark fetch paths (Pitfall 3) | Fetch-heavy workloads with large `fetch_arrow_table` results |
| Thread-hop overhead on tiny queries | Async slower than sync for `SELECT 1`-style calls | Don't claim universal speedup; offload is for latency-bound work | Many tiny queries where round-trip ≪ thread-hop cost |
| Limiter < pool concurrency | Throughput plateaus at 40; checkouts queue | Dedicated limiter sized to `pool_size + max_overflow` (Pitfall 6) | `pool_size + max_overflow > 40` or shared global limiter |
| Holding connection while awaiting unrelated offload | Limiter tokens exhausted; deadlock under load | Don't await other offloads while holding a connection; keep offloads flat | High concurrency with nested async work |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging `db_kwargs` / connection strings when surfacing async errors | Credential leak in async stack traces | Reuse the sync error-handling discipline; never log resolved kwargs in the async layer |
| Returning a possibly-busy connection to the pool after cancel | Next task (possibly different tenant/credentials context) inherits a connection in an unknown state | Invalidate-on-uncertain-cancel (Pitfall 1/4); never return a connection whose worker thread hasn't joined |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Async guide implies blanket parallelism | Users expect CPU-bound fetch speedups they won't get | Document I/O-bound vs materialization honestly (Pitfall 3) |
| No `managed_async_pool()` / `async with` for connections | Users leak connections on the error path | Ship async context managers as the primary, sanctioned API |
| Unclear that one `AsyncConnection` = one task | Users share connections, hit UB | Document single-owner rule prominently in the async guide |
| Cancellation appears to work but query keeps running on the warehouse | Surprise warehouse costs / locks held | Make `adbc_cancel` wiring real and documented; note the cost of cancellation |

## "Looks Done But Isn't" Checklist

- [ ] **Cancellation:** await returns on timeout — but verify the *warehouse-side query actually stops* (not just the await). Check via a driver that reports `ADBC_STATUS_CANCELLED`.
- [ ] **Connection return on cancel:** happy-path checkin works — but verify checkin on the cancel and exception paths, with `pool.checkedout() == 0` afterwards.
- [ ] **trio leg:** asyncio tests green — but run the *same* suite under trio; cancellation especially diverges.
- [ ] **Limiter:** offloads work — but verify a *dedicated* limiter is used (not the global 40) and is sized to the pool.
- [ ] **Per-connection serialization:** single-task tests pass — but add a test that two coroutines sharing one connection are serialized (or rejected), not racing.
- [ ] **Arrow memory:** functional fetch works — but run a sustained loop and assert RSS/allocator stats stabilize.
- [ ] **Sync untouched:** async added — but run the sync suite with anyio *not installed* to prove zero impact and correct `[async]` gating.
- [ ] **Typing:** code runs — but `basedpyright` strict passes on the async module with no new `Any`.
- [ ] **Reset symmetry:** async cleanup runs — but confirm the existing `reset` listener (`_release_arrow_allocators`) still fires on async checkin.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cancelled query keeps running / pool corruption (1) | HIGH | Add `adbc_cancel` wiring + join-before-return; invalidate-on-uncertain; reproduce with a deterministic slow-query cassette/driver |
| Concurrent connection access (2) | HIGH | Add per-connection `anyio.Lock`; document single-owner; audit for shared `AsyncConnection` usage |
| GIL premise wrong for fetch (3) | MEDIUM | Re-scope docs/expectations; possibly chunk fetches; no code rewrite if offload still helps I/O-bound paths |
| Connection leak on error/cancel (4) | MEDIUM | Shield checkin; route through sync return path; add `checkedout()==0` assertions to tests |
| Arrow leak (5) | MEDIUM | Make cursor an async CM; ensure reset listener fires; add memory-stability test |
| Limiter mismatch/deadlock (6) | MEDIUM | Introduce dedicated limiter sized to pool; flatten nested offloads |
| Event-loop block on checkout (7) | LOW | Route `connect()` through `to_thread`; add import-ban lint |
| trio breakage (8) | LOW–MEDIUM | Replace asyncio primitives with anyio; add trio test leg |
| Typing gate (9) | LOW | Add `ParamSpec`/`Concatenate` helper; mirror overloads |

## Pitfall-to-Phase Mapping

Recommended phase order puts the feasibility spike first (validate the GIL premise), then the core wrapper (which must ship the lock, dedicated limiter, offload-everything rule, typing, and symmetric cleanup together), then a dedicated cancellation phase (highest correctness risk), then testing, then packaging/docs.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 3. GIL premise unvalidated | Phase A — Feasibility spike (first) | Benchmark: concurrent slow-query vs large-fetch wall-clock vs ideal |
| 2. Thread-affinity / concurrent access | Phase B — Core async wrapper | Test: two coroutines on one connection are serialized; stress on Snowflake-replay |
| 4. Leak on error path | Phase B — Core async wrapper | Test: exception during use → `pool.checkedout()==0` |
| 5. Arrow leak | Phase B — Core async wrapper | Sustained-load memory-stability test; reset listener fires on async checkin |
| 6. Limiter mismatch/deadlock | Phase B — Core async wrapper | Assert dedicated limiter sized to pool; high-concurrency stress without deadlock |
| 7. Event-loop block on checkout | Phase B — Core async wrapper | Import-ban lint; exhausted-pool test doesn't stall the loop |
| 8. trio divergence | Phase B — Core async wrapper | Dual-backend (asyncio+trio) test matrix green |
| 9. Typing under strict | Phase B — Core async wrapper | `basedpyright` strict passes; overloads mirror sync |
| 1. Cancellation correctness | Phase C — Cancellation (dedicated) | Deterministic test: cancel → warehouse query actually stops + clean checkin |
| 11. API drift | Phase B + Docs phase | Test asserting async surface mirrors sync defaults/methods |
| 10. `[async]` extra scoping | Phase D — Packaging/extra | Sync suite passes with anyio uninstalled; async import errors cleanly without extra |
| 12. Flaky/non-deterministic async tests | Phase E — Testing | Deterministic anyio clocks; dual-backend cassette replay; assert real cancellation |

## Sources

- [ADBC Concurrency and Thread Safety](https://arrow.apache.org/adbc/main/cpp/concurrency.html) — authoritative serialization rule: *"serialized access from multiple threads... do not allow concurrent access."* (HIGH)
- [adbc_driver_manager (Python dbapi reference)](https://arrow.apache.org/adbc/main/python/api/adbc_driver_manager.html) — *"Connections are not thread-safe... serialize accesses"*; `Connection.adbc_cancel()` / `Cursor.adbc_cancel()`; close-or-leak note. (HIGH)
- [ADBC Statement API — Cancel](https://arrow.apache.org/adbc/main/cpp/api/group__adbc-statement.html) — *"Cancel execution of an in-progress query... This must always be thread-safe (other operations are not)."* (HIGH)
- [anyio — Working with threads](https://anyio.readthedocs.io/en/stable/threads.html) — default 40-token process-wide limiter; `abandon_on_cancel`: *"the thread will still continue running – only its outcome will be ignored"*; `from_thread`. (HIGH)
- [PEP 612 — ParamSpec / Concatenate](https://peps.python.org/pep-0612/) and [typing docs](https://docs.python.org/3/library/typing.html) — typing sync→async wrappers. (HIGH)
- adbc-poolhouse source: `_pool_factory.py` (`_release_arrow_allocators` reset listener, `close_pool`, defaults), `_driver_api.py` (dbapi connect shapes) — basis for "symmetric cleanup" and per-backend genericity. (HIGH, direct read)
- ADBC GIL-release per operation: not explicitly documented per-method — premise inferred from native (Rust/C/Go) drivers releasing the GIL around blocking calls; flagged for empirical validation in Phase A. (MEDIUM)

---
*Pitfalls research for: anyio thread-offload async layer over sync ADBC + SQLAlchemy QueuePool (adbc-poolhouse v1.4.0)*
*Researched: 2026-06-25*
