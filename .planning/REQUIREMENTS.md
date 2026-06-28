# Requirements: adbc-poolhouse v1.4.0

**Milestone:** v1.4.0 — Async API
**Defined:** 2026-06-26
**Core Value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.

## v1.4.0 Requirements

Add an **optional** async API surface behind an `[async]` extra. Every blocking ADBC / SQLAlchemy `QueuePool` call is dispatched to a worker thread via `anyio.to_thread.run_sync` — real I/O concurrency because the ADBC C drivers release the GIL during query execution. The async layer wraps the existing sync core (`_create_pool_impl`, config dispatch, the 13-backend `WarehouseConfig` Protocol, the `_release_arrow_allocators` reset event) **without modifying it**, in a new `src/adbc_poolhouse/_async/` package. anyio is chosen for asyncio + trio neutrality. The sync API is shipped and unchanged.

Scope decisions for this milestone:

- **Feasibility spike gates the milestone** — validate the GIL-release premise for pyarrow materialization before building the full surface.
- **P2 differentiators deferred to v1.4.x** — `fetch_record_batch` streaming, `adbc_ingest`, `fetch_df`/`fetch_polars` are out of scope here (see Future Requirements).
- **Dedicated async edge-case test coverage** — a curated `EDGE-NN` suite (cancellation depth, limiter/backpressure, contextvars, reentrancy, exceptions, resource lifetime, event-loop hygiene, trio-vs-asyncio, timing) hardens the layer against the silent-leak failure modes endemic to async DB wrappers. Designs in `.planning/research/ASYNC-EDGE-CASES.md`.

### Feasibility Spike

- [x] **SPIKE-01**: A DuckDB benchmark measures wall-clock of N concurrent slow (I/O-bound) queries against ideal-parallel, demonstrating real GIL release during `execute`
- [x] **SPIKE-02**: A DuckDB benchmark measures N concurrent large `fetch_arrow_table` calls against ideal-parallel, quantifying whether pyarrow materialization parallelizes or serializes on the GIL
- [x] **SPIKE-03**: A written go/no-go records which concurrency wins the async layer can honestly claim (and what to disclaim), feeding offload-granularity and documentation decisions

### Concurrency Foundation

- [x] **CORE-01**: A single internal offload helper routes every blocking ADBC / `QueuePool` call through `anyio.to_thread.run_sync` with an explicit limiter argument — no bare `to_thread` calls anywhere in the async package
- [x] **CORE-02**: Each async pool owns a dedicated `anyio.CapacityLimiter` sized to `pool_size + max_overflow`; the shared process-global 40-token default limiter is never used
- [x] **CORE-03**: The async package uses anyio primitives only — `import asyncio` is banned there and enforced by a lint/import rule
- [x] **CORE-04**: The async layer is generic over all 13 backends via the existing `WarehouseConfig` Protocol — no per-backend async code

### Async Pool Lifecycle

- [x] **APOOL-01**: User can call `create_async_pool(config, ...)` to obtain an async pool; the signature mirrors `create_pool` (same keyword defaults `pool_size=5`, `max_overflow=3`, `timeout=30`, `recycle=3600`, `pre_ping=False`) and the same `config` / `driver_path=` / `dbapi_module=` overloads
- [x] **APOOL-02**: User can call `await close_async_pool(pool)` to dispose the pool and release driver resources, offloaded so it never blocks the event loop
- [x] **APOOL-03**: User can use `async with managed_async_pool(config, ...) as pool:` to create-and-auto-close a pool, with the close path shielded from cancellation

### Async Connection

- [x] **ACONN-01**: User can `await pool.connect()` to check out an `AsyncConnection`; the blocking checkout is offloaded through the pool's dedicated limiter
- [x] **ACONN-02**: `AsyncConnection` is an async context manager; exiting returns the connection to the pool, and checkin is shielded so it always completes even under cancellation
- [x] **ACONN-03**: `AsyncConnection.cursor()` returns an `AsyncCursor` synchronously (no I/O, no `await`), matching the ADBC / psycopg3 convention
- [x] **ACONN-04**: User can `await conn.commit()` and `await conn.rollback()` for transaction control (offloaded)
- [x] **ACONN-05**: User can `await conn.close()` to release the connection explicitly (offloaded, shielded)
- [x] **ACONN-06**: Async checkin routes through the existing reset path so `_release_arrow_allocators` fires symmetrically with the sync API — no Arrow allocator leak

### Async Cursor

- [x] **ACUR-01**: User can `await cursor.execute(operation, parameters=None)` (offloaded)
- [x] **ACUR-02**: User can `await cursor.executemany(operation, seq_of_parameters)` (offloaded)
- [x] **ACUR-03**: User can `await cursor.fetchone()`, `await cursor.fetchmany(size=None)`, and `await cursor.fetchall()` (offloaded)
- [x] **ACUR-04**: User can `await cursor.fetch_arrow_table()` returning a `pyarrow.Table` (offloaded) — the headline Arrow-native path
- [x] **ACUR-05**: `AsyncCursor` is an async context manager; `await cursor.close()` runs offloaded and shielded, freeing Arrow readers
- [x] **ACUR-06**: ADBC `Error` subclasses raised in the worker thread propagate to the awaiting task unchanged (no swallowing, correct type)
- [x] **ACUR-07**: Sync no-I/O cursor properties (`description`, `rowcount`, `arraysize`) pass through without `await`

### Cancellation

- [x] **CANCEL-01**: When an awaited `execute` / `fetch_arrow_table` is cancelled or times out, `cursor.adbc_cancel()` is invoked from the event-loop thread to abort the in-flight C call
- [x] **CANCEL-02**: A connection whose in-flight operation was cancelled is invalidated rather than returned busy, so the pool is never poisoned (`pool.checkedout() == 0` after a cancelled scope)
- [x] **CANCEL-03**: `__aexit__` cleanup is wrapped in `CancelScope(shield=True)` so the connection always returns or invalidates even when the surrounding task is cancelled mid-cleanup
- [x] **CANCEL-04**: Deterministic cancellation tests prove no-leak behaviour under both asyncio and trio

### Packaging & Type Safety

- [x] **PKG-01**: An `[async]` optional-dependency extra adds `anyio>=4.13` and nothing else; `[all]` includes it
- [ ] **PKG-02**: `import adbc_poolhouse` succeeds with anyio not installed; async names are guarded by a PEP 562 `__getattr__` lazy import so the sync path stays zero-cost
- [ ] **PKG-03**: Accessing an async symbol without anyio installed raises a clear `ImportError` naming the `[async]` extra
- [ ] **PKG-04**: The existing sync test suite passes with anyio uninstalled (a CI job proves there is no hard async dependency)
- [x] **PKG-05**: All async public API is fully typed under basedpyright strict, using ~~`ParamSpec`/`Concatenate`~~ **PEP 646 `TypeVarTuple`/`Unpack`** (mechanism corrected in Phase 26 RESEARCH: ParamSpec does not compile — keyword-only params cannot follow `*args: P.args`; `TypeVarTuple` is anyio's own approach) to type-check the offload-boundary args (Phase 26 Plan 02)

### Testing

- [ ] **TEST-01**: The async suite runs parametrized over asyncio and trio via the anyio pytest plugin (`@pytest.mark.anyio`)
- [ ] **TEST-02**: The async layer is exercised against DuckDB (in-proc) and Snowflake (pytest-adbc-replay cassette) to prove backend-generic coverage
- [ ] **TEST-03**: An Arrow memory-stability test confirms no allocator growth across many async cursor lifecycles
- [ ] **TEST-04**: A limiter-sizing stress test confirms no deadlock or starvation when concurrency exceeds `pool_size`
- [x] **TEST-05**: A shared deterministic test harness exists — a `BlockingStubCursor` (blocks on a `threading.Event` released only by the test or by `adbc_cancel`; records thread-id, call counts, max-concurrent-in-execute) plus event-gating/virtual-clock helpers and a source-scan/import-lint guard — so edge-case tests need no real sleeps

### Async Edge-Case Test Coverage

Deterministic tests (arrange/trigger/assert) for the failure modes specific to a thread-offload anyio wrapper. Each runs under **both** asyncio and trio unless noted. Full designs in `.planning/research/ASYNC-EDGE-CASES.md`. Note: `anyio.to_thread.run_sync` is cancellation-shielded by default, so every cancellation test asserts the worker was *actually* unblocked (e.g. `adbc_cancel` fired), never merely that the `await` returned.

_Cancellation depth_

- [x] **EDGE-01**: Cancel delivered *before* the offload starts — driver `execute` is never called, no `adbc_cancel`, the connection stays clean, and the cancel exception propagates
- [x] **EDGE-02**: Cancel *during* the blocked worker — `adbc_cancel` is called exactly once (shielded), the worker is joined, the connection is invalidated, `checkedout() == 0`, and the cancel exception propagates
- [x] **EDGE-03**: The framework cancel class is never swallowed by the offload/try-except — the exact `get_cancelled_exc_class()` instance escapes and there is no hang under trio
- [x] **EDGE-04**: A double-cancel during shielded cleanup is idempotent — one `adbc_cancel`, one invalidate, one cancel exception
- [x] **EDGE-05**: Cancel during `__aexit__`/checkin still completes checkin under shield — `checkedout() == 0` for both connection and cursor
- [x] **EDGE-06**: `fail_after` timeout and explicit `scope.cancel()` are handled identically (both → `adbc_cancel` + invalidate); only the surfaced exception type differs
- [x] **EDGE-07**: `move_on_after` on an already-finished op does nothing — `cancelled_caught` is False, no `adbc_cancel`, no invalidate

_Limiter / backpressure_

- [x] **EDGE-09**: A limiter token is borrowed-then-released exactly once across success, error, and cancel paths (×50 loop, `borrowed_tokens == 0` after)
- [x] **EDGE-10**: A limiter token is not leaked when acquire itself is cancelled while queued on a saturated limiter; concurrency fully recovers
- [x] **EDGE-11**: Holding a connection while awaiting a second offload does not self-deadlock at the bound (serialized on the held token or a clear error; a watchdog never trips)
- [x] **EDGE-12**: In-flight concurrency is strictly bounded — observed running-max `== pool_size + max_overflow` under a 4× flood

_Reentrancy_

- [x] **EDGE-15**: Two tasks sharing one `AsyncConnection`/`AsyncCursor` raise a clear typed error (`ConnectionBusyError`) — never silently serialized, never a concurrent-access violation; `checkedout()` stays correct (Phase 24 decision D-24-03: reject, no per-connection lock)

_Exceptions_

- [x] **EDGE-17**: An ADBC error from the worker propagates with exact type and original traceback intact across the thread boundary
- [x] **EDGE-18**: An exception in `__aenter__`/post-checkout leaks no connection (`checkedout() == 0`, no cumulative leak over N iterations)
- [x] **EDGE-19**: An `ExceptionGroup`/`except*` from a task group preserves the original ADBC errors and keeps cancellation distinguishable; `checkedout() == 0` after

_Resource lifetime_

- [x] **EDGE-21**: A materialized `fetch_arrow_table` result is valid after checkin (no use-after-checkin) — the result is a `pyarrow.Table`, not a live reader bound to the connection

_Event-loop hygiene_

- [x] **EDGE-25**: Every blocking DB call runs off the loop thread (captured worker thread-id ≠ loop thread-id), with a lint asserting no `asyncio` import and no bare `to_thread` without the limiter in `_async/`
- [x] **EDGE-26**: A long blocked offload does not starve the loop — a concurrent coroutine advances across `sleep(0)` checkpoints while the offload blocks

_trio-vs-asyncio_

- [ ] **EDGE-27**: Every async test is parametrized over asyncio AND trio — no `@pytest.mark.asyncio`, no `asyncio` import in the async test package
- [x] **EDGE-28**: Cancellation handling uses `get_cancelled_exc_class()` only — a trio cancel of a blocked execute *does* run `adbc_cancel` + invalidate; no `asyncio.CancelledError` in `_async/`
- [x] **EDGE-29**: Cancel-scope behaviour is identical across backends — the `(adbc_cancel_count, invalidate_count, checkedout_after)` tuple is equal under asyncio and trio

_Timing_

- [ ] **EDGE-30**: Timeout/cancel tests use a virtual clock or event gating — no positive-duration `sleep` in timeout tests (enforced by a source scan)

### Documentation

- [ ] **DOCS-01**: An async usage guide shows `create_async_pool` → `connect` → `execute` → `fetch_arrow_table` → checkin, honest about I/O-bound vs materialization-bound concurrency (per SPIKE findings)
- [ ] **DOCS-02**: API reference documents `AsyncPool`, `AsyncConnection`, `AsyncCursor`, and the three entry-point functions with Google-style docstrings (Args/Returns/Raises + Example)
- [ ] **DOCS-03**: Configuration / index pages list the `[async]` extra and the async entry points
- [ ] **DOCS-04**: `uv run mkdocs build --strict` passes; humanizer pass applied to all new or substantially rewritten prose

## Future Requirements (deferred)

Deferred to v1.4.x once the P1 core is validated:

- **Arrow streaming** — `await cursor.fetch_record_batch()` + `async for batch in ...` (`RecordBatchReader` lifetime vs reset-event checkin needs dedicated design)
- **Async bulk write** — `await cursor.adbc_ingest(table, data, mode=...)`
- **DataFrame convenience** — `await cursor.fetch_df()` / `await cursor.fetch_polars()`

Deferred to v2+:

- **Async ADBC metadata** — `adbc_get_table_schema`, `adbc_get_objects`, `adbc_get_info`
- **Async prepared statements** — `adbc_prepare`, `adbc_execute_schema`
- **anyio-native checkout limiter** — replacing offloaded `QueuePool.connect()`, only if offloaded checkout proves a measured bottleneck

P2 async edge-case tests (designs in `.planning/research/ASYNC-EDGE-CASES.md`), folded into v1.4.x hardening once the P1 suite is green:

- **EDGE-08** — trio checkpoint delivery at the offload boundary with no intervening checkpoint
- **EDGE-13 / EDGE-14** — contextvars copied into the worker; worker mutations do not leak back
- **EDGE-16** — ~~`adbc_cancel` bypasses a held per-connection lock~~ — **N/A / DROPPED** (Phase 24 decision D-24-03 rejects aliasing with `ConnectionBusyError` instead of locking; no per-connection lock ships, so this conditional requirement no longer applies)
- **EDGE-20** — an exception during cleanup does not mask the body error (chained via `__context__`); connection still released
- **EDGE-22 / EDGE-23** — `__del__` of an un-closed cursor/connection emits `ResourceWarning`, never "coroutine never awaited"; happy path emits no `RuntimeWarning`
- **EDGE-24** — open pool / pending offload at loop shutdown raises no library-attributable exception
- **EDGE-31 / EDGE-32** — `move_on_after(0)` still cancels a blocked execute cleanly; an op completing at deadline−ε is not over-cancelled

## Out of Scope

Explicit exclusions for the async layer (with reasoning):

- **Async ORM / query builder** — out of scope by charter; the sync lib is pool-only. Consumers (Semantic ORM, dbt-open-sl) build their own query layers on top
- **Native async ADBC driver shim** — no native async ADBC driver exists; thread-offload over the GIL-releasing C calls already yields real concurrency. A native shim is enormous and unnecessary
- **Built-in retry / reconnect** — retry policy is consumer-specific (idempotency, backoff, budget); baking it in hides failures. `recycle` stays the only health mechanism
- **Multi-pool routing / async registry** — out of scope in sync too; consumers call `create_async_pool()` per warehouse and own the mapping
- **Implicit transactions / unit-of-work** — ADBC defaults to autocommit; implicit `begin()` surprises users and differs per backend. Only explicit `commit()` / `rollback()` are exposed
- **asyncio-only fast path** — would discard the trio differentiator and pull in asyncio-specific leak patterns. anyio everywhere
- **`AsyncAdaptedQueuePool` / `sqlalchemy[asyncio]` / `greenlet` as foundation** — asyncio-bound, does not replace the execute offload, breaks trio neutrality. Reference only

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SPIKE-01 | Phase 22 | Complete |
| SPIKE-02 | Phase 22 | Complete |
| SPIKE-03 | Phase 22 | Complete |
| TEST-05 | Phase 23 | Complete |
| CORE-01 | Phase 24 | Complete |
| CORE-02 | Phase 24 | Complete |
| CORE-03 | Phase 24 | Complete |
| CORE-04 | Phase 24 | Complete |
| APOOL-01 | Phase 24 | Complete |
| APOOL-02 | Phase 24 | Complete |
| APOOL-03 | Phase 24 | Complete |
| ACONN-01 | Phase 24 | Complete |
| ACONN-02 | Phase 24 | Complete |
| ACONN-03 | Phase 24 | Complete |
| ACONN-04 | Phase 24 | Complete |
| ACONN-05 | Phase 24 | Complete |
| ACONN-06 | Phase 24 | Complete |
| ACUR-01 | Phase 24 | Complete |
| ACUR-02 | Phase 24 | Complete |
| ACUR-03 | Phase 24 | Complete |
| ACUR-04 | Phase 24 | Complete |
| ACUR-05 | Phase 24 | Complete |
| ACUR-06 | Phase 24 | Complete |
| ACUR-07 | Phase 24 | Complete |
| EDGE-09 | Phase 24 | Complete |
| EDGE-10 | Phase 24 | Complete |
| EDGE-11 | Phase 24 | Complete |
| EDGE-12 | Phase 24 | Complete |
| EDGE-15 | Phase 24 | Complete |
| EDGE-17 | Phase 24 | Complete |
| EDGE-18 | Phase 24 | Complete |
| EDGE-21 | Phase 24 | Complete |
| EDGE-25 | Phase 24 | Complete |
| EDGE-26 | Phase 24 | Complete |
| CANCEL-01 | Phase 25 | Complete (25-03) |
| CANCEL-02 | Phase 25 | Complete (25-03) |
| CANCEL-03 | Phase 25 | Complete (25-03) |
| CANCEL-04 | Phase 25 | Complete (25-03) |
| EDGE-01 | Phase 25 | Complete (25-03) |
| EDGE-02 | Phase 25 | Complete (25-03) |
| EDGE-03 | Phase 25 | Complete (25-03) |
| EDGE-04 | Phase 25 | Complete (25-03) |
| EDGE-05 | Phase 25 | Complete (25-03) |
| EDGE-06 | Phase 25 | Complete (25-03) |
| EDGE-07 | Phase 25 | Complete (25-03) |
| EDGE-19 | Phase 25 | Complete |
| EDGE-28 | Phase 25 | Complete (25-01 AST rule; 25-02/03 behavioral trio-cancel; 25-05 async-side meta-assert scan_async_package(_async/)==[]) |
| EDGE-29 | Phase 25 | Complete (25-03) |
| PKG-01 | Phase 26 | Complete (26-01) |
| PKG-02 | Phase 26 | Pending |
| PKG-03 | Phase 26 | Pending |
| PKG-04 | Phase 26 | Pending |
| PKG-05 | Phase 26 | Complete (Plan 02) |
| TEST-01 | Phase 27 | Pending |
| TEST-02 | Phase 27 | Pending |
| TEST-03 | Phase 27 | Pending |
| TEST-04 | Phase 27 | Pending |
| EDGE-27 | Phase 27 | Pending |
| EDGE-30 | Phase 27 | Pending |
| DOCS-01 | Phase 28 | Pending |
| DOCS-02 | Phase 28 | Pending |
| DOCS-03 | Phase 28 | Pending |
| DOCS-04 | Phase 28 | Pending |
