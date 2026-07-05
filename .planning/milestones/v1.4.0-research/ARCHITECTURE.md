# Architecture Research

**Domain:** Async API layer over a shipped sync ADBC connection-pool library (adbc-poolhouse v1.4.0)
**Researched:** 2026-06-25
**Confidence:** HIGH

> Scope: how an *optional* async surface (behind an `[async]` extra) integrates with the existing
> sync architecture. The sync API is frozen and unchanged. Every key decision below is grounded in
> the real source (`_pool_factory.py`, `_driver_api.py`, `_base_config.py`) and in the authoritative
> ADBC C header / Cython source and anyio docs (see Sources).

---

## Settled Decisions (read this first)

| # | Question | Decision | Confidence |
|---|----------|----------|------------|
| 1 | Offload model | New `_async/` package. Wrap each blocking call in `anyio.to_thread.run_sync`. Reuse `_create_pool_impl()` **verbatim** — pool construction stays sync; only checkout + cursor/conn methods are offloaded. | HIGH |
| 2 | Checkout-wait strategy | **Option (a): keep plain sync `QueuePool`, offload `pool.connect()` via `to_thread`.** Reject building an anyio-native limiter as the checkout gate. `AsyncAdaptedQueuePool` is **not used** (asyncio+greenlet-bound; would break trio neutrality and does not replace the execute offload). | HIGH |
| 3 | Thread/concurrency sizing | The async pool **owns a dedicated `CapacityLimiter`** sized to `pool_size + max_overflow`. Do **not** rely on anyio's shared 40-token default limiter — it is global and would let unrelated `to_thread` work starve DB checkouts (and vice-versa). | HIGH |
| 4 | Connection thread-affinity | **No thread-affinity.** ADBC explicitly permits serialized cross-thread access ("one thread may make a call, and once finished, another thread may make a call"). `to_thread` using different workers across awaits is **safe**, *provided one connection is never used concurrently from two tasks* — which the pool checkout already guarantees. | HIGH |
| 5 | Cancellation flow | On anyio cancellation, call `cursor.adbc_cancel()` / `conn.adbc_cancel()` from the event-loop thread. ADBC's cancel functions are the **documented exception** to the serialize rule: "This must always be thread-safe (other operations are not)." The blocked `execute` worker then returns `ADBC_STATUS_CANCELLED`; the connection is invalidated and returned to the pool. | HIGH |
| 6 | Build order | foundation (limiter + pool factory) → connection/cursor wrappers → cancellation → backend-generic verification → docs. Dependency-ordered below. | HIGH |

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  ASYNC SURFACE  (new, behind [async] extra — src/adbc_poolhouse/_async)│
│                                                                        │
│  create_async_pool()   managed_async_pool()   close_async_pool()       │
│        │                      │                       │                │
│        └──────────┬───────────┴───────────────────────┘                │
│                   ▼                                                     │
│            AsyncPool (wrapper)                                          │
│            - holds sync QueuePool  (from _create_pool_impl)             │
│            - holds dedicated anyio.CapacityLimiter(pool_size+overflow)  │
│            - async connect()  ── to_thread ──▶ pool.connect()          │
│                   │                                                     │
│                   ▼                                                     │
│            AsyncConnection (wrapper)                                    │
│            - wraps the checked-out sync ConnectionFairy / dbapi conn    │
│            - async cursor(), async close()                             │
│                   │                                                     │
│                   ▼                                                     │
│            AsyncCursor (wrapper)                                        │
│            - execute / executemany / fetchone / fetchmany / fetchall   │
│              / fetch_arrow_table  ── each via to_thread + limiter      │
│            - cancel scope wired to cursor.adbc_cancel()                 │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │  anyio.to_thread.run_sync(fn, limiter=…)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  EXISTING SYNC CORE  (UNCHANGED)                                       │
│  _pool_factory._create_pool_impl()  ──▶  sqlalchemy.pool.QueuePool     │
│       (creator = source.adbc_clone, reset = _release_arrow_allocators) │
│  _driver_api.create_adbc_connection()  (config dispatch lives here)    │
│  _base_config.WarehouseConfig (Protocol) / BaseWarehouseConfig         │
└───────────────────────────────┬──────────────────────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ADBC dbapi (C / Cython)  — every execute/fetch wrapped `with nogil:`  │
│  → GIL released → worker threads run DB I/O truly concurrently         │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | New / Modified |
|-----------|----------------|----------------|
| `_create_pool_impl()` | Build the sync `QueuePool` from config dispatch. **Reused unchanged** by the async factory. | **Unchanged** |
| `create_adbc_connection()` | Driver/config dispatch (Family A/A'/B). Runs once, synchronously, at pool creation. | **Unchanged** |
| `AsyncPool` | Own one sync `QueuePool` + one dedicated `CapacityLimiter`. Offload `connect()` and `close()`. | **New** |
| `AsyncConnection` | Wrap a checked-out connection; produce `AsyncCursor`; offload `close()`/`commit()`/`rollback()`. | **New** |
| `AsyncCursor` | Offload `execute`/`executemany`/`fetch*`/`fetch_arrow_table`; bind anyio cancel scope to `adbc_cancel`. | **New** |
| `create_async_pool` / `managed_async_pool` / `close_async_pool` | Public async entry points mirroring the sync trio. | **New** |
| `_release_arrow_allocators` (reset event) | Arrow cleanup on checkin. Fires identically for async-checked-out connections (it is a pool-level event). | **Unchanged — reused** |

---

## Recommended Project Structure

```
src/adbc_poolhouse/
├── __init__.py              # MODIFIED: lazy/extra-guarded re-export of async API
├── _pool_factory.py         # UNCHANGED (sync trio + _create_pool_impl)
├── _driver_api.py           # UNCHANGED (config dispatch)
├── _base_config.py          # UNCHANGED (Protocol)
├── _async/                  # NEW package — the entire async surface
│   ├── __init__.py          # public: create_async_pool, managed_async_pool, close_async_pool
│   ├── _factory.py          # async factory; calls _create_pool_impl, builds AsyncPool + limiter
│   ├── _pool.py             # AsyncPool (connect/close offload, owns CapacityLimiter)
│   ├── _connection.py       # AsyncConnection wrapper
│   ├── _cursor.py           # AsyncCursor wrapper (+ cancellation)
│   └── _offload.py          # tiny helper: run_sync(fn, *, limiter) thin wrapper + cancel glue
tests/
└── async/                   # NEW: async-specific tests (anyio pytest plugin, both backends)
```

### Structure Rationale

- **A dedicated `_async/` package, not a single `_async.py`:** the surface is four wrapper classes plus
  a factory and offload helper — co-locating keeps the import cost (and the `anyio` dependency) isolated
  so the sync path never imports anyio.
- **`__init__.py` guarded import:** importing the async names must not hard-fail when the `[async]`
  extra (and therefore `anyio`) is absent. Use a lazy `__getattr__` (PEP 562) on the package `__init__`
  that imports `_async` on first access and raises a clear `ImportError` ("install adbc-poolhouse[async]")
  if `anyio` is missing. This keeps `import adbc_poolhouse` zero-cost for sync users and basedpyright-strict clean.
- **Reuse, don't fork, `_create_pool_impl()`:** config dispatch (the Family A/A'/B signature detection in
  `_driver_api.py`) is genuinely hard logic. The async factory calls `_create_pool_impl(...)` to get a real
  `QueuePool`, then wraps it. Zero duplication of dispatch; one async layer covers all 13 backends via the Protocol.

---

## Architectural Patterns

### Pattern 1: Wrap-and-offload (do not re-implement)

**What:** Each async method is a thin coroutine that offloads exactly one blocking sync call to a worker
thread via `anyio.to_thread.run_sync`, passing the pool's dedicated limiter.
**When:** Every blocking boundary — checkout, `execute`, `fetch*`, `fetch_arrow_table`, `close`.
**Trade-offs:** Minimal new logic, trivially correct, anyio-neutral (asyncio + trio). Cost is one
thread-hop per call; negligible vs. DB round-trip latency.

```python
# _async/_offload.py
from anyio import to_thread
from anyio import CapacityLimiter

async def offload(fn, /, *args, limiter: CapacityLimiter):
    # abandon_on_cancel=False (default): we handle cancellation explicitly
    # via adbc_cancel rather than abandoning the worker (see Pattern 3).
    return await to_thread.run_sync(lambda: fn(*args), abandon_on_cancel=False, limiter=limiter)

# _async/_cursor.py
class AsyncCursor:
    async def execute(self, sql, parameters=None):
        return await offload(self._cur.execute, sql, parameters, limiter=self._limiter)

    async def fetch_arrow_table(self):
        return await offload(self._cur.fetch_arrow_table, limiter=self._limiter)
```

### Pattern 2: Dedicated CapacityLimiter sized to the pool

**What:** `AsyncPool` constructs `CapacityLimiter(pool_size + max_overflow)` and threads it through
every `run_sync`. Checkout offload and execute/fetch offload share *this* limiter.
**When to use:** Always, for the async pool. Never use the shared default 40-token limiter for DB work.
**Trade-offs:** Guarantees the number of in-flight DB worker threads can never exceed the number of
connections the pool can hand out, so there is no oversubscription and no head-of-line blocking from
unrelated `to_thread` callers in the host application.

```python
# _async/_pool.py
class AsyncPool:
    def __init__(self, sync_pool, pool_size, max_overflow):
        self._pool = sync_pool
        self._limiter = anyio.CapacityLimiter(pool_size + max_overflow)

    async def connect(self):
        fairy = await offload(self._pool.connect, limiter=self._limiter)
        return AsyncConnection(fairy, self._limiter)
```

> **Sizing rationale (Q3).** A checked-out connection is busy for the whole lifetime of a query, so the
> *steady-state* in-flight thread count equals the number of checked-out connections, bounded by
> `pool_size + max_overflow`. Sizing the limiter to exactly that bound means: (i) execute/fetch never
> queue behind the limiter (a connection you hold already "owns" a token via its checkout); (ii) checkout
> offload itself participates in the same bound, so a flood of `connect()` calls is throttled at the
> limiter rather than spawning unbounded threads. The shared 40-token default is rejected because it is
> process-global: another part of the host app doing `to_thread` work could exhaust it and deadlock DB
> checkouts, and our checkouts could starve theirs.

### Pattern 3: Cancellation via `adbc_cancel` from the loop thread

**What:** On anyio cancellation of an in-flight `execute`/fetch, call the cursor's (or connection's)
`adbc_cancel()` from the event-loop thread to unblock the worker, then invalidate the connection.
**When:** Any awaited DB call inside a cancel scope / timeout / task-group cancellation.
**Trade-offs:** True cooperative cancellation (the blocked C call actually returns), no abandoned-thread
leak. Requires a small amount of glue because `run_sync` by itself can only *abandon* (ignore the result
of) a thread, not interrupt it.

```python
# _async/_cursor.py — cancellation glue
async def execute(self, sql, parameters=None):
    try:
        return await offload(self._cur.execute, sql, parameters, limiter=self._limiter)
    except anyio.get_cancelled_exc_class():
        # Called from the loop thread while the worker is blocked in execute().
        # adbc_cancel is documented thread-safe vs. all other (non-thread-safe) ops.
        with anyio.CancelScope(shield=True):
            await to_thread.run_sync(self._cur.adbc_cancel)   # unblocks the worker
        self._conn._invalidate()                              # mark dirty -> pool discards
        raise
```

---

## Data Flow

### Query flow (async)

```
await pool.connect()
    │  offload ──▶ QueuePool.connect()      (worker thread; blocks if exhausted, bounded by timeout)
    ▼
AsyncConnection ──▶ await conn.cursor()  (cheap; may be sync or trivially offloaded)
    ▼
await cursor.execute(sql)
    │  offload ──▶ cursor.execute()        (worker thread; ADBC C call runs `with nogil:` → real concurrency)
    ▼
await cursor.fetch_arrow_table()
    │  offload ──▶ cursor.fetch_arrow_table()  (worker thread; GIL released during pull)
    ▼
async ctx exit ──▶ offload conn.close()/return to pool
    │
    ▼
pool `reset` event ──▶ _release_arrow_allocators (UNCHANGED, fires on checkin/invalidate/error)
```

### Cancellation flow (Q5, concrete)

```
event-loop thread                         worker thread
─────────────────                         ─────────────
await cursor.execute(sql)  ───offload───▶  cursor.execute()  ── blocked in AdbcStatementExecuteQuery (nogil)
   │
   │  (timeout fires / task cancelled)
   ▼
catch cancelled exc
   │
   ├─ shield + to_thread(cursor.adbc_cancel())  ──▶  AdbcStatementCancel()  ← THREAD-SAFE by spec
   │                                                      │
   │                                                      ▼
   │                                         execute() returns ADBC_STATUS_CANCELLED → raises
   ├─ conn._invalidate()  (SQLAlchemy ConnectionFairy.invalidate)
   │      → pool will NOT reuse this connection; reset event still closes cursors
   ▼
re-raise cancelled exc  (no leak, no half-open connection reused)
```

> **Why this is safe and leak-free (Q5).** `AdbcStatementCancel`/`AdbcConnectionCancel` are the *only*
> ADBC operations the C header marks "must always be thread-safe (other operations are not)." So calling
> `adbc_cancel()` from the loop thread while the worker is mid-`execute()` is exactly the supported pattern.
> The worker's `execute` then returns an error promptly, releasing the worker thread (and its limiter token).
> We invalidate rather than check-in the connection so a possibly half-consumed result set / dirty statement
> is never reused; SQLAlchemy's pool discards it and the `reset` event still runs cursor cleanup. We do **not**
> use `abandon_on_cancel=True` as the primary mechanism, because abandoning leaks a busy worker thread that
> still holds the connection — `adbc_cancel` actively reclaims it instead.

---

## Connection Thread-Affinity — answered from evidence (Q4)

**Verdict: ADBC dbapi connections do NOT require thread-affinity. Serialized cross-thread use is safe.**

Evidence:

1. ADBC concurrency spec: *"In general, objects allow serialized access from multiple threads: one
   thread may make a call, and once finished, another thread may make a call."* No same-OS-thread
   requirement is stated anywhere in the spec or the C header.
2. dbapi module: `threadsafety = 1` ("threads may share the module, but not connections"). This is a
   *sharing* (concurrency) constraint, not an affinity constraint — it forbids two threads touching one
   connection *at once*, not the same connection on different threads *over time*.
3. The C header's per-object docstrings say operations "are not [thread-safe]" — i.e. must be serialized —
   with `Cancel` the sole explicit exception.

**Consequence for the wrapper design:** `to_thread.run_sync` may dispatch successive calls on different
worker threads, and that is fine, because (a) ADBC permits serialized cross-thread access and (b) a pool-
checked-out connection is owned by exactly one async task at a time, so two threads never touch it
concurrently. **No per-connection dedicated thread, no thread-pinning, no per-connection serialization
lock is required.** (If a future driver turns out to mis-handle cross-thread serialized access, the
fallback is a per-`AsyncConnection` `anyio.Lock` to serialize its calls — cheap to add, but not needed by spec.)

---

## Checkout-Wait Strategy — decision with rationale (Q2)

**Decision: Option (a) — plain sync `QueuePool`, offload `pool.connect()` through `to_thread`.**

Rationale:

- **Simplicity & correctness.** The sync pool already implements exhaustion waiting, `timeout`,
  `max_overflow`, recycle, and the Arrow `reset` event. Re-implementing checkout queueing in anyio
  duplicates battle-tested logic and risks subtle bugs (fairness, recycle, invalidation).
- **anyio-neutral.** Offloading the blocking checkout keeps the whole stack asyncio+trio neutral with no
  greenlet. The only cost is that a worker thread is briefly held during an exhausted-pool wait — but that
  wait is bounded by the existing `timeout` (default 30s) and, with the dedicated limiter sized to the
  pool, the number of threads parked in checkout-wait can never exceed the connection budget anyway.
- **The dedicated limiter already gives us the "anyio-native" benefit that option (b) was reaching for**
  (back-pressure that the event loop can see), without a second queueing mechanism. A task waiting on a
  checkout is either waiting on the limiter (event-loop-native) or briefly on a worker thread inside
  `QueuePool.connect` (bounded). We get back-pressure visibility without re-implementing the pool.

**Rejected — Option (b) anyio-native limiter as the checkout gate:** adds a second source of truth for
"how many connections are out" that must be kept perfectly in sync with the sync pool's own counters;
divergence causes either spurious waits or oversubscription. Not worth it. (We *do* use a CapacityLimiter,
but as the *thread* budget — Pattern 2 — not as a replacement for the pool's checkout queue.)

**`AsyncAdaptedQueuePool` verdict (reference only, NOT used):** SQLAlchemy's `AsyncAdaptedQueuePool`
swaps the pool's internal wait primitive for an asyncio-based one driven via **greenlet** (the
`greenlet_spawn`/`await_only` bridge). It is **asyncio-bound** (breaks trio neutrality, a hard project
constraint), and — critically — it only changes *checkout waiting*; it does **nothing** for the actual
blocking `execute`/`fetch` C calls, which still must be offloaded to threads. So it solves the smaller
half of the problem at the cost of the neutrality constraint. Use it as a reference for "how SQLAlchemy
thinks about async checkout," not as a foundation.

---

## Scaling Considerations

| Scale | Architecture adjustments |
|-------|--------------------------|
| Light (few concurrent queries) | Defaults fine: `pool_size=5, max_overflow=3` → limiter of 8. |
| Many concurrent async tasks | Raise `pool_size`/`max_overflow`; the limiter auto-tracks because it is sized from them. Watch DB-side connection limits. |
| High fan-out across pools | Each `AsyncPool` owns its own limiter, so multiple pools don't contend on a shared thread budget; total worker threads ≈ Σ(pool_size+overflow). Keep an eye on host thread count. |

### Scaling priorities

1. **First bottleneck:** connection count / DB server limits — tune `pool_size`, not the limiter directly.
2. **Second bottleneck:** total OS worker threads if many large pools coexist — the per-pool limiter keeps
   this proportional and predictable.

---

## Anti-Patterns

### Anti-Pattern 1: Using the default anyio thread limiter for DB work
**What people do:** call `to_thread.run_sync(...)` with no `limiter=`.
**Why it's wrong:** the 40-token default is process-global and shared with all other `to_thread` users in
the host app; DB checkouts and unrelated CPU offload can starve each other or deadlock.
**Instead:** pass the pool's dedicated `CapacityLimiter` to every DB offload.

### Anti-Pattern 2: `abandon_on_cancel=True` as the cancellation mechanism
**What people do:** rely on anyio abandoning the worker on cancel.
**Why it's wrong:** the worker keeps running, still holding the connection and a limiter token → leak;
the connection may return to the pool in a half-open state.
**Instead:** call `adbc_cancel()` (thread-safe by spec) to actively unblock the worker, then invalidate
the connection.

### Anti-Pattern 3: Sharing one checked-out connection across concurrent tasks
**What people do:** await two `execute`s on the same `AsyncConnection` from two tasks at once.
**Why it's wrong:** ADBC `threadsafety=1` forbids concurrent access to one connection; two workers would
touch it simultaneously.
**Instead:** one `AsyncConnection` per task; the pool hands out distinct connections. (Optionally guard
with a per-connection `anyio.Lock` for defense-in-depth.)

### Anti-Pattern 4: Forking `_create_pool_impl` / config dispatch into the async layer
**What people do:** re-derive driver path / kwargs in the async factory.
**Why it's wrong:** duplicates the Family A/A'/B signature-detection logic and the 13-backend coverage.
**Instead:** call `_create_pool_impl(...)` and wrap its `QueuePool`.

---

## Integration Points

### Internal boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `_async/_factory.py ↔ _pool_factory._create_pool_impl` | direct sync call | Reuse; do not duplicate dispatch. Factory passes the same pool-tuning kwargs through. |
| `AsyncPool ↔ sqlalchemy QueuePool` | wraps instance; offloads `connect`/`dispose` | The `reset` event (`_release_arrow_allocators`) is registered by `_create_pool_impl` and fires unchanged. |
| `AsyncCursor ↔ adbc dbapi Cursor` | offload + `adbc_cancel()` | `adbc_cancel` is the only call made from the loop thread while a worker is busy. |
| `__init__.py ↔ _async` | PEP 562 lazy `__getattr__` | Guards the `anyio` import behind the `[async]` extra; clear `ImportError` if missing. |
| `close_async_pool ↔ close_pool` | offload `close_pool(pool)` | Reuse sync `close_pool` (dispose + source.close) inside a thread. |

### External / packaging

| Item | Decision | Notes |
|------|----------|-------|
| `[async]` extra | adds `anyio>=4.0` only | Sync path never imports anyio. |
| basedpyright strict | async wrappers fully typed | ADBC types stay suppressed only in `_driver_api.py`; wrappers type against the dbapi stubs/`Any` at the boundary. |
| Tests | `anyio` pytest plugin, parametrized over asyncio **and** trio backends; cover DuckDB (in-proc) + Snowflake cassette | Proves trio-neutrality and backend-generic behaviour. |

---

## Suggested Build Order (Q6 — dependency-ordered)

1. **Foundation.** `_async/_offload.py` (`offload` helper) + `_async/_factory.py` + `AsyncPool` owning a
   dedicated `CapacityLimiter`; `create_async_pool` / `managed_async_pool` / `close_async_pool` calling
   `_create_pool_impl` and `close_pool`. *Verifies:* pool creation + offloaded checkout work on both anyio
   backends for one backend (DuckDB).
2. **Connection + cursor wrappers.** `AsyncConnection`, `AsyncCursor` with `execute`/`executemany`/
   `fetch*`/`fetch_arrow_table` offloaded through the pool's limiter. *Verifies:* end-to-end async query;
   Arrow `reset` cleanup still fires on checkin.
3. **Cancellation.** Wire anyio cancel scopes → `cursor.adbc_cancel()` / `conn.adbc_cancel()` from the loop
   thread; invalidate-on-cancel. *Verifies:* a timeout interrupts a long `execute` and the connection does
   not leak (limiter token reclaimed, no half-open reuse).
4. **Backend-generic verification.** Run the async suite across the Protocol for the cassette backends
   (Snowflake) + in-proc backends (DuckDB/SQLite); confirm one async layer covers all 13 via config dispatch.
   Parametrize tests over asyncio **and** trio to lock in neutrality.
5. **Docs.** Async usage guide + configuration/index/API-reference updates; Google-style docstrings on all
   new public symbols; `mkdocs build --strict` (Phase ≥7 quality gate per CLAUDE.md).

---

## Sources

- ADBC C/C++ Concurrency & Thread Safety — "objects allow serialized access from multiple threads" (drives Q4) — https://arrow.apache.org/adbc/main/cpp/concurrency.html — **HIGH**
- ADBC `adbc.h` header (main): `AdbcConnectionCancel` / `AdbcStatementCancel` docstrings — *"This must always be thread-safe (other operations are not)"* (drives Q5) — https://raw.githubusercontent.com/apache/arrow-adbc/main/c/include/arrow-adbc/adbc.h — **HIGH**
- ADBC `_lib.pyx` (Cython) — every execute/fetch C call wrapped `with nogil:`; `cancel()` → `AdbcStatementCancel`/`AdbcConnectionCancel` (confirms GIL release + cancel wiring) — https://raw.githubusercontent.com/apache/arrow-adbc/main/python/adbc_driver_manager/adbc_driver_manager/_lib.pyx — **HIGH**
- ADBC `dbapi.py` — `Cursor.adbc_cancel()` / `Connection.adbc_cancel()`; `threadsafety = 1`, `apilevel = "2.0"` — https://raw.githubusercontent.com/apache/arrow-adbc/main/python/adbc_driver_manager/adbc_driver_manager/dbapi.py — **HIGH**
- ADBC `adbc_driver_manager` API reference — `adbc_cancel` semantics, "connections may not be shared" — https://arrow.apache.org/adbc/current/python/api/adbc_driver_manager.html — **HIGH**
- anyio threads guide — default worker-thread limiter = 40 (shared); `abandon_on_cancel`; worker may differ per call — https://anyio.readthedocs.io/en/stable/threads.html — **HIGH**
- anyio API — `to_thread.run_sync(func, *args, abandon_on_cancel, limiter)`; `CapacityLimiter(total_tokens)`; `current_default_thread_limiter()` (drives Q1/Q3) — https://anyio.readthedocs.io/en/stable/api.html — **HIGH**
- Existing source read directly: `src/adbc_poolhouse/_pool_factory.py`, `_driver_api.py`, `_base_config.py`, `__init__.py`, `pyproject.toml` — **HIGH**

---
*Architecture research for: async layer over sync ADBC pool library (adbc-poolhouse v1.4.0)*
*Researched: 2026-06-25*
