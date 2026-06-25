# Feature Research

**Domain:** Async wrapper API for a sync ADBC connection-pool library (adbc-poolhouse v1.4.0)
**Researched:** 2026-06-25
**Confidence:** HIGH (reference APIs and ADBC/anyio mechanics from official docs; one architectural risk flagged)

## Scope Reminder

This research covers ONLY the NEW async surface for v1.4.0. The sync API
(`create_pool` / `close_pool` / `managed_pool`, the 13 configs, the
`WarehouseConfig` Protocol, raw `driver_path=` / `dbapi_module=` overloads)
is shipped and unchanged. The async layer is an OPTIONAL wrapper behind the
`[async]` extra, built on `anyio.to_thread.run_sync`, that adds awaitable
versions of pool / connection / cursor operations.

**Critical divergence from sync:** the sync library deliberately stops at
"pool hands you a connection, you execute yourself." Async CANNOT stop there —
the whole point of offloading is to move blocking I/O off the event loop, and
the blocking happens at *execute / fetch*, not at *checkout*. So the async
layer must wrap connection **and** cursor execute/fetch. This is the one place
where async is intentionally a bigger surface than sync.

## Reference API Survey (prior art)

| Library | Pool acquire | Execute | Fetch | Async iteration | Streaming | Cancellation safety |
|---------|--------------|---------|-------|-----------------|-----------|---------------------|
| **asyncpg** | `async with pool.acquire()` | `await conn.execute/fetch/fetchrow/fetchval` | record list / single | `async for r in conn.cursor(q)` | server-side cursor, prefetch | known leak risk on `CancelledError` (issue #464) |
| **psycopg3 async** | `async with pool.connection()` | `await cur.execute()` | `await cur.fetchone/many/all` | `async for r in cur` | `cur.stream(q)` → `AsyncIterator` | mirrors sync, "scatter await" |
| **aiosqlite** | `async with connect()` | `await db.execute()` | `await cur.fetchone/all` | cursor is async iterator | n/a (single shared thread/conn) | thread-per-connection proxy model |
| **SQLAlchemy 2.x asyncio** | `async with engine.connect()` | `await conn.execute()` → buffered `Result` | via Result | `async for r in result` | `await conn.stream()` → `AsyncResult` | greenlet bridge; **documented leak on cancel** (issue #8145) |
| **encode/databases** | `async with database.connection()` | `await db.execute()` | `await db.fetch_one/all` | `db.iterate()` → `async for` | `iterate()` | now in maintenance mode |
| **aiomysql** | `async with pool.acquire()` | `await cur.execute()` | `await cur.fetchone/many/all` | n/a primarily | SSCursor variant | wraps sync via executor |

**Convergent conventions across all of them (these are the norms we mirror):**
1. Pool / connection / cursor are all **async context managers** (`async with`).
2. Connection acquire is `await` (or `async with`); cursor creation is usually
   NOT awaited (no I/O) — psycopg3 explicitly keeps `cursor()` sync.
3. `execute` / `executemany` / `fetch*` are all `await`-ed.
4. Result iteration uses `async for row in cursor` (cursor is an async iterator).
5. Streaming/server-side reads are a SEPARATE method (`stream()` / `iterate()`),
   distinct from the buffered `fetchall()` path.
6. Naming mirrors the sync surface so users transfer knowledge by adding `await`.

## Feature Landscape

### Table Stakes (Users Expect These)

These are non-negotiable. An async DB wrapper without them feels broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `create_async_pool(config, ...)` | Mirror of sync `create_pool`; entry point | LOW | Wraps sync `create_pool`; pool construction itself is fast/non-blocking, so creation can be sync-under-the-hood, but offer `await` form for symmetry. Depends on `_create_pool_impl`. |
| `close_async_pool(pool)` | Mirror of sync `close_pool`; clean teardown | LOW | Offload `pool.dispose()` + `_adbc_source.close()` (both can block on driver). Depends on `close_pool`. |
| `managed_async_pool(config, ...)` | Mirror of sync `managed_pool` | LOW | `@asynccontextmanager`; create on enter, `close_async_pool` on exit (shielded). Depends on `managed_pool` pattern. |
| `await pool.connect()` → async connection | Async checkout is the core promise | MEDIUM | Offload sync `QueuePool.connect()` (checkout can block on pool timeout). Returns `AsyncConnection` wrapper. **Open design decision** (PROJECT.md): plain QueuePool offloaded vs anyio-native limiter. |
| Async connection as `async with` | Universal convention; cleanup on exit | MEDIUM | `__aenter__`/`__aexit__`; exit returns conn to pool. Cleanup MUST be cancellation-shielded (see Pitfall below). |
| `conn.cursor()` → async cursor | Get a cursor to execute against | LOW | Cursor creation does no I/O (matches ADBC + psycopg3) — keep it sync-returning, no `await`. Wrap ADBC dbapi `Cursor`. |
| `await cursor.execute(sql, params)` | THE blocking call to offload | MEDIUM | `anyio.to_thread.run_sync(cursor.execute, ...)`. ADBC releases GIL → real concurrency. Standard DBAPI method. |
| `await cursor.executemany(sql, seq)` | Batch param execution | LOW | Same offload pattern as `execute`. Standard DBAPI. |
| `await cursor.fetchone()` | Single-row fetch | LOW | Offload. Standard DBAPI. Returns row or None. |
| `await cursor.fetchmany(size)` | Bounded batch fetch | LOW | Offload. Standard DBAPI. |
| `await cursor.fetchall()` | Buffered full fetch | LOW | Offload. Standard DBAPI. The blocking row-materialization belongs off-loop. |
| Async cursor as `async with` | Cleanup releases Arrow readers | MEDIUM | `__aexit__` calls `close()` offloaded + shielded. Ties into existing `_release_arrow_allocators` reset hook. |
| `await cursor.close()` | Explicit cleanup | LOW | Offload `close()`. Must run even on cancel (shielded). |
| Exception propagation across thread | Errors must surface as if in-loop | LOW | `to_thread.run_sync` already re-raises in the awaiting task — verify ADBC `Error` subclasses propagate cleanly; no swallowing. |
| Cancellation that doesn't leak connections | Cancelled query must not poison the pool | **HIGH** | The hard problem. See "Cancellation" differentiator + Pitfall. Every reference lib has had leak bugs here. |
| `commit()` / `rollback()` (async) | Transaction control on connection | LOW | Offload connection-level `commit`/`rollback`. Standard DBAPI. ADBC is autocommit-by-default; still expose. |

### Differentiators (Competitive Advantage)

These set the library apart and align with its Arrow/ADBC core value. Most
async DB wrappers are row-oriented; this one is Arrow-native and ADBC-aware.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| `await cursor.fetch_arrow_table()` | Arrow-native bulk fetch off-loop — the headline ADBC feature | MEDIUM | Offload ADBC extension `fetch_arrow_table()`. Returns pyarrow.Table. The single most valuable async method for this library's audience. |
| `await cursor.fetch_record_batch()` + async batch iteration | Stream Arrow RecordBatches without buffering whole result | **HIGH** | ADBC `fetch_record_batch()` returns a `RecordBatchReader`. Wrap so `async for batch in ...` offloads each `read_next_batch()` to a thread. This is the streaming equivalent of psycopg3 `stream()` / SQLAlchemy `AsyncResult`. Big differentiator; also the trickiest (per-batch cancellation, reader lifetime vs connection checkin). |
| `adbc_cancel`-based cooperative cancellation | True query cancellation, not just abandon-the-thread | **HIGH** | anyio cannot kill a running thread; on cancel-scope trip, call `cursor.adbc_cancel()` (or `connection.adbc_cancel()`) so the C driver actually aborts the in-flight op. Wire via `anyio.from_thread.check_cancelled()` inside the worker OR an outer scope that fires `adbc_cancel` then awaits the abandoned thread. THE feature that makes async here correct rather than cosmetic. |
| `await cursor.adbc_ingest(table, data, mode=...)` | Bulk Arrow load offloaded — write-path symmetry | MEDIUM | ADBC extension. Bulk ingest is long-running and blocking → prime offload candidate. Accepts pyarrow Table/RecordBatch/Reader. Pairs naturally with the fetch_arrow path. |
| `await cursor.fetch_df()` / `fetch_polars()` | DataFrame convenience off-loop | LOW | Thin offload wrappers over ADBC extensions; cheap to add once `fetch_arrow_table` plumbing exists. Optional — gate on demand. |
| anyio backend-neutral (asyncio + trio) | Works under asyncio AND trio, unlike asyncpg/psycopg3/SQLAlchemy (asyncio-only) | MEDIUM | Using `anyio.to_thread` throughout (never raw `asyncio.to_thread`) buys trio support for free. Genuine differentiator vs every reference lib surveyed. Constrains design: no asyncio-specific primitives, no `AsyncAdaptedQueuePool`. |
| One async layer, all 13 backends | No per-driver async shim; generic over `WarehouseConfig` | MEDIUM | Because offload is driver-agnostic, the SAME wrapper covers all 13 backends. Reference libs are per-database. Depends on the existing Protocol + `_driver_api` facade. |
| `await cursor.adbc_prepare()` / `adbc_execute_schema()` | Prepared-statement + schema-only access, async | LOW | Thin offload wrappers; add if/when a consumer needs them. Low cost given the generic offload helper. |
| Connection-level async metadata (`adbc_get_table_schema`, `adbc_get_objects`) | Async catalog introspection | LOW-MEDIUM | Offload ADBC connection extensions. Useful for the planned Semantic ORM consumer. Add opportunistically. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Async ORM / query builder | "Make it like SQLAlchemy async / databases" | Out of scope by charter (sync lib is pool-only, ORM explicitly excluded). Massive surface, competes with SQLAlchemy/SQLModel. | Stay a pool+execute wrapper; consumers (Semantic ORM, dbt-open-sl) build their own query layers on top. |
| Native async ADBC driver shim | "Real async, not threads" | No native async ADBC driver exists; ADBC's C calls release the GIL so thread-offload already yields real concurrency. Building/maintaining a native shim is enormous and unnecessary. | Thread-offload via anyio is the deliberate, documented architecture (PROJECT.md feasibility basis). |
| Built-in retry / reconnect logic | "Handle transient failures for me" | Retry policy is consumer-specific (idempotency, backoff, budget). Baking it in hides failures and fights the pool's `recycle`. Sync lib has no retry; async shouldn't diverge. | Surface clean exceptions; let consumers wrap with their own retry (tenacity, etc.). Keep `recycle` as the only health mechanism. |
| Multi-pool routing / async registry | "Route queries across warehouses" | Explicitly out of scope in sync (consumers own the dict). No reason to add it only on the async side. | Consumers call `create_async_pool()` per warehouse and manage the mapping. |
| Auto-transaction / unit-of-work magic | "Wrap everything in a transaction" | ADBC defaults to autocommit; implicit transaction semantics surprise users and differ per backend. | Expose explicit `commit()`/`rollback()`; document autocommit behavior. No implicit `begin()`. |
| Asyncio-only fast path (drop trio) | "asyncio is all anyone uses; go native" | Throws away the backend-neutral differentiator and locks out trio/AnyIO-structured users; pulls in asyncio-specific leak patterns (SQLAlchemy #8145). | Commit to anyio everywhere. If asyncio-specific tuning is ever needed, do it behind anyio's backend detection, not by forking the API. |
| Reusing SQLAlchemy `AsyncAdaptedQueuePool` as the foundation | "SQLAlchemy already has an async pool" | It is asyncio-bound (greenlet) and does NOT replace the thread-offload; adopting it breaks trio support and inverts the architecture. | Treat it as a *reference* only (per PROJECT.md). Keep plain sync `QueuePool` + anyio offload, or an anyio-native checkout limiter. |
| Implicit cursor auto-fetch on execute (asyncpg `fetch()` style) | "One call to run + return rows" | ADBC/DBAPI separates execute from fetch; merging them hides the Arrow-vs-row choice that is this library's whole value. | Keep DBAPI execute → fetch split. Offer `fetch_arrow_table()` as the ergonomic Arrow path. |

## Feature Dependencies

```
[anyio offload helper: _run_sync_offloaded()]  <- foundational, everything below needs it
    |--requires--> [async cursor.execute/executemany]
    |                   |--requires--> [async fetchone/many/all]
    |                   |--requires--> [async fetch_arrow_table]
    |                   |                  |--enables--> [async fetch_record_batch + async batch iteration]
    |                   |--requires--> [async adbc_ingest]
    |--requires--> [await pool.connect() -> AsyncConnection]
    |                   |--requires--> [async connection ctx mgr (__aenter__/__aexit__)]
    |                   |                  |--requires--> [shielded cleanup on cancel]
    |                   |--requires--> [conn.cursor() -> AsyncCursor (sync-returning)]
    |--requires--> [create_async_pool / close_async_pool]
    |                   |--requires--> [managed_async_pool ctx mgr]
    |--requires--> [adbc_cancel cancellation wiring]
                        |--conflicts--> [abandon_on_cancel=True WITHOUT adbc_cancel]
                        |--enhances--> [every execute/fetch method]

[anyio backend-neutrality] --constrains--> [ALL of the above]  (no raw asyncio primitives)
[existing WarehouseConfig Protocol] --enables--> [generic over all 13 backends]
[existing _release_arrow_allocators reset hook] --interacts-with--> [async cursor cleanup]
```

### Dependency Notes

- **Everything requires the offload helper:** A single internal
  `_run_sync_offloaded(fn, *args)` over `anyio.to_thread.run_sync` is the
  foundation. Build and harden it first (cancellation policy lives here).
- **fetch_record_batch requires fetch_arrow_table plumbing:** Both need the
  Arrow reader lifecycle understood; the streaming reader is the harder superset.
- **Connection cleanup requires shielded cleanup:** `__aexit__` must return the
  connection to the pool even when the surrounding task is cancelled — otherwise
  the connection leaks (every reference lib has shipped this bug).
- **adbc_cancel conflicts with bare `abandon_on_cancel=True`:** anyio's
  `abandon_on_cancel` lets the *await* return on cancel but the *thread keeps
  running* the query. Without firing `adbc_cancel`, you abandon a thread that
  still holds the connection → leak. The two MUST be wired together: on cancel,
  fire `adbc_cancel`, then let the abandoned thread unwind. This is the single
  most important correctness dependency.
- **Cursor lifetime vs reset hook:** the existing sync `_release_arrow_allocators`
  reset event closes open cursors on checkin to free Arrow readers. The async
  connection's `__aexit__` (checkin) interacts with this — confirm a streaming
  `RecordBatchReader` is fully consumed or explicitly closed before checkin, or
  the reset hook closes it mid-stream.

## MVP Definition

### Launch With (v1.4.0 core)

Minimum to deliver a correct, useful async surface.

- [ ] `_run_sync_offloaded()` helper with cancellation policy — foundation for all
- [ ] `create_async_pool` / `close_async_pool` / `managed_async_pool` — entry trio mirroring sync
- [ ] `await pool.connect()` → `AsyncConnection` (async ctx mgr, shielded cleanup) — core promise
- [ ] `AsyncCursor` with `execute`, `executemany`, `fetchone`, `fetchmany`, `fetchall`, `close` — DBAPI table stakes
- [ ] `await cursor.fetch_arrow_table()` — the headline Arrow differentiator
- [ ] `adbc_cancel` cancellation wiring (no-leak on cancel) — correctness requirement, NOT optional
- [ ] `commit()` / `rollback()` async — transaction control
- [ ] anyio backend-neutral throughout (asyncio + trio tested) — the cross-cutting differentiator
- [ ] Generic over all 13 backends via existing Protocol — proves the design

### Add After Validation (v1.4.x)

- [ ] `await cursor.fetch_record_batch()` + `async for batch` streaming — trigger: a consumer needs to stream results larger than memory
- [ ] `await cursor.adbc_ingest()` async bulk load — trigger: write-path demand from dbt-open-sl / Semantic ORM
- [ ] `fetch_df()` / `fetch_polars()` async convenience — trigger: DataFrame-oriented consumer request

### Future Consideration (v2+)

- [ ] Async ADBC metadata methods (`adbc_get_table_schema`, `adbc_get_objects`) — defer: Semantic ORM may want async catalog introspection; cheap to add when concretely needed
- [ ] `adbc_prepare` / `adbc_execute_schema` async — defer: niche; add on demand
- [ ] anyio-native checkout limiter (vs offloaded QueuePool) — defer: only if offloaded-checkout proves a bottleneck under trio (this is the settled-in-research open design decision)

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `_run_sync_offloaded()` helper | HIGH | MEDIUM | P1 |
| `create/close/managed_async_pool` | HIGH | LOW | P1 |
| `await pool.connect()` + async conn ctx mgr | HIGH | MEDIUM | P1 |
| async `execute/executemany` | HIGH | MEDIUM | P1 |
| async `fetchone/many/all` | HIGH | LOW | P1 |
| async cursor ctx mgr + `close` | HIGH | MEDIUM | P1 |
| `adbc_cancel` cancellation (no-leak) | HIGH | HIGH | P1 |
| `fetch_arrow_table()` async | HIGH | MEDIUM | P1 |
| `commit/rollback` async | MEDIUM | LOW | P1 |
| anyio backend-neutral (trio support) | HIGH | MEDIUM | P1 |
| `fetch_record_batch()` + async streaming | HIGH | HIGH | P2 |
| `adbc_ingest()` async | MEDIUM | MEDIUM | P2 |
| `fetch_df` / `fetch_polars` async | MEDIUM | LOW | P2 |
| async ADBC metadata methods | LOW-MEDIUM | LOW | P3 |
| `adbc_prepare` / `adbc_execute_schema` | LOW | LOW | P3 |

**Priority key:** P1 = must have for v1.4.0 launch · P2 = v1.4.x once validated · P3 = future.

## Concrete Async Surface to Wrap (exact method set)

**Pool-level (module functions):** `create_async_pool`, `close_async_pool`,
`managed_async_pool` — signatures identical to sync, including the three
overloads (config / `driver_path=` / `dbapi_module=`) and keyword defaults.

**`AsyncConnection` (wraps ADBC dbapi `Connection`):**
- `await pool.connect()` returns it; `async with` scopes it (checkin on exit)
- `cursor()` → `AsyncCursor` (NOT awaited — no I/O)
- `await commit()`, `await rollback()`, `await close()`
- (P3) `await adbc_get_table_schema(...)`, `await adbc_get_objects(...)`, `await adbc_get_info()`
- `adbc_cancel()` used internally for cancellation wiring

**`AsyncCursor` (wraps ADBC dbapi `Cursor`):**
- `await execute(operation, parameters=None)`
- `await executemany(operation, seq_of_parameters)`
- `await fetchone()`, `await fetchmany(size=None)`, `await fetchall()`
- `await fetch_arrow_table()` (P1 differentiator)
- `await fetch_record_batch()` + `async for batch in ...` (P2 streaming)
- `await adbc_ingest(table_name, data, mode='create', ...)` (P2)
- `await fetch_df()`, `await fetch_polars()` (P2, optional)
- `await close()`
- `adbc_cancel()` used internally for cancellation wiring
- properties pass-through (sync, no I/O): `description`, `rowcount`, `arraysize`

## Symmetry With the Sync API (naming + conventions)

The async surface must read as "the sync API with `await` and `async with`
added." Concrete conventions, derived from the sync code and the prior-art norms:

| Sync | Async | Convention |
|------|-------|------------|
| `create_pool(config, ...)` | `create_async_pool(config, ...)` | `_async_` infix; identical signature/keywords (`pool_size`, `max_overflow`, `timeout`, `recycle`, `pre_ping`) and the same three overloads. |
| `close_pool(pool)` | `close_async_pool(pool)` | direct mirror. |
| `with managed_pool(...) as pool:` | `async with managed_async_pool(...) as pool:` | `@asynccontextmanager`; same call patterns. |
| `with pool.connect() as conn:` | `async with await pool.connect() as conn:` | `await` to acquire, `async with` to scope — matches psycopg3/SQLAlchemy. |
| `conn.cursor()` | `conn.cursor()` (NOT awaited) | cursor creation does no I/O — keep sync-returning like psycopg3 and ADBC. |
| `cursor.execute(...)` | `await cursor.execute(...)` | "scatter await" — same args, same order. |
| `cursor.fetch_arrow_table()` | `await cursor.fetch_arrow_table()` | identical name + `await`. Same for `fetchone/many/all`, `executemany`, `adbc_ingest`, `commit`, `rollback`. |
| iterate rows manually | `async for batch in cursor.fetch_record_batch()` | streaming uses `async for` (psycopg3 `stream` / SQLAlchemy `AsyncResult` convention). |

**Naming rules:**
- Public functions: `create_async_pool` / `close_async_pool` /
  `managed_async_pool` (decided in milestone context).
- Wrapper classes: `AsyncConnection` / `AsyncCursor` (matches psycopg3 naming
  exactly — strong precedent, instantly recognizable).
- Keep method NAMES identical to the sync/ADBC names — only add `await`. Do not
  rename `fetch_arrow_table` to something "async-y." Discoverability comes from
  sameness.
- Same keyword defaults as `create_pool` (`pool_size=5`, `max_overflow=3`,
  `timeout=30`, `recycle=3600`, `pre_ping=False`) — copy them verbatim.

## Dependencies on Existing Sync Components

| New async feature | Depends on existing |
|-------------------|---------------------|
| `create_async_pool` / `managed_async_pool` / `close_async_pool` | `_pool_factory._create_pool_impl`, `create_pool`, `close_pool` (offload + reuse, don't reimplement) |
| async connection/cursor wrappers | ADBC dbapi `Connection`/`Cursor` obtained via `_driver_api.create_adbc_connection` and the pool's checked-out connection |
| generic 13-backend coverage | `_base_config.WarehouseConfig` Protocol + the self-describing configs (no per-backend async code) |
| cursor cleanup | existing `_release_arrow_allocators` reset hook on the pool (must not double-close or close mid-stream) |
| exception propagation | ADBC `Error` hierarchy surfaced via `_driver_api`; `to_thread.run_sync` re-raise |
| type safety | basedpyright strict — all async public API fully typed (constraint from PROJECT.md) |

## Critical Pitfall (flag for ARCHITECTURE/PITFALLS research)

**Cancellation leaks the connection.** Every reference library surveyed
(asyncpg #464, SQLAlchemy #8145/#12099, the encode stack) has shipped a bug
where a cancelled task leaves a connection that never returns to the pool,
eventually exhausting it. Two compounding hazards here:

1. `anyio.to_thread.run_sync` cannot kill the worker thread. With
   `abandon_on_cancel=True` the await returns but the query keeps running on a
   connection you've "released" → corruption/leak. MUST pair with
   `cursor.adbc_cancel()` so the C driver actually aborts.
2. The async connection `__aexit__` (checkin) is itself an `await` and can be
   cancelled mid-cleanup. Cleanup must be shielded (anyio `CancelScope(shield=True)`)
   so the connection always returns to the pool.

This is the highest-risk area of the milestone and warrants its own design
section. It is a P1 correctness requirement, not a nice-to-have.

## Competitor Feature Analysis

| Feature | asyncpg / psycopg3 | SQLAlchemy 2.x asyncio | Our Approach |
|---------|--------------------|------------------------|--------------|
| Async transport | native async sockets | greenlet bridge over sync driver | anyio thread-offload over sync ADBC (GIL-releasing) |
| Backend support | one DB each | many DBs via dialects | all 13 ADBC backends, one generic layer |
| Event-loop neutrality | asyncio only | asyncio only | asyncio AND trio (anyio) |
| Arrow-native fetch | no (row-oriented) | no | `fetch_arrow_table` / `fetch_record_batch` is the headline |
| Cancellation | CancelledError (leak-prone) | CancelledError (documented leaks) | `adbc_cancel` + shielded checkin (real abort, no leak) |
| Streaming | server-side cursor / `stream()` | `AsyncResult` / `stream()` | `async for batch in fetch_record_batch()` |

## Sources

- ADBC dbapi API reference (Cursor/Connection method set, extensions) — https://arrow.apache.org/adbc/current/python/api/adbc_driver_manager.html — HIGH
- ADBC DBAPI/Driver Manager recipes — https://arrow.apache.org/adbc/current/python/recipe/driver_manager.html — HIGH
- anyio threads (to_thread.run_sync, abandon_on_cancel, from_thread.check_cancelled) — https://anyio.readthedocs.io/en/stable/threads.html — HIGH
- psycopg3 async (AsyncConnection/AsyncCursor, stream, "scatter await", cursor() not awaited) — https://www.psycopg.org/psycopg3/docs/advanced/async.html — HIGH
- asyncpg API reference (pool acquire/release, execute/fetch/fetchrow/fetchval, cursors) — https://magicstack.github.io/asyncpg/current/api/index.html — HIGH
- aiosqlite (proxy connection/cursor, async iterator, thread model) — https://aiosqlite.omnilib.dev/ — HIGH
- SQLAlchemy 2.x asyncio (AsyncEngine/AsyncConnection/AsyncResult, stream, greenlet) — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html — HIGH
- encode/databases (connect/execute/fetch_all/fetch_one/iterate/transactions) — https://www.encode.io/databases/ — MEDIUM (maintenance mode)
- SQLAlchemy async cancel-leak issue #8145 / asyncpg #464 (connection-leak-on-cancel pattern) — https://github.com/sqlalchemy/sqlalchemy/issues/8145 , https://github.com/MagicStack/asyncpg/issues/464 — HIGH
- adbc-poolhouse sync source (`_pool_factory.py`, `_driver_api.py`, `__init__.py`) — local, for mirroring — HIGH

---
*Feature research for: async wrapper API over sync ADBC connection pool (adbc-poolhouse v1.4.0)*
*Researched: 2026-06-25*
