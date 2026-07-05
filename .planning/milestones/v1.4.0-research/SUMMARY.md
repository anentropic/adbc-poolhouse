# Project Research Summary

**Project:** adbc-poolhouse v1.4.0 — Async API
**Domain:** Optional anyio thread-offload async layer over a shipped sync ADBC connection-pool library
**Researched:** 2026-06-25
**Confidence:** HIGH (stack, architecture, pitfalls confirmed from official ADBC spec + anyio docs; one GIL premise flagged for empirical validation)

## Executive Summary

adbc-poolhouse v1.4.0 adds an optional async API surface behind an `[async]` extra. The approach is thread-offload: every blocking ADBC / SQLAlchemy `QueuePool` call is dispatched to a worker thread via `anyio.to_thread.run_sync`, which yields real I/O concurrency because the ADBC C drivers release the GIL during query execution. This avoids the non-existent native async ADBC driver and the asyncio-bound `AsyncAdaptedQueuePool` path; the entire new runtime dependency surface is `anyio>=4.0.0` and nothing else. A new `src/adbc_poolhouse/_async/` package wraps the existing sync core without touching it: `_create_pool_impl`, config dispatch, the 13-backend `WarehouseConfig` Protocol, and the `_release_arrow_allocators` Arrow-cleanup reset event are all reused verbatim.

The four research streams converge tightly on the architecture. The only new concurrency primitive needed is a **dedicated `CapacityLimiter(pool_size + max_overflow)` per pool** — never anyio's shared 40-token global default — passed explicitly to every `to_thread.run_sync` call. ADBC permits serialized cross-thread access (not concurrent), so no thread-affinity is required by spec; `adbc_cancel` is the sole ADBC operation documented as thread-safe and is the key to cooperative cancellation. The async surface mirrors the sync API one-for-one (`create_async_pool` / `managed_async_pool` / `close_async_pool`; `AsyncConnection`; `AsyncCursor` with the full DBAPI execute/fetch set plus `fetch_arrow_table`), with `async with` / `await` added throughout and names kept identical so users transfer knowledge by adding `await`.

The #1 correctness risk — ahead of all others by a significant margin — is **cancellation**. Every surveyed reference library (asyncpg, SQLAlchemy, encode/databases) has shipped a connection-leak bug on cancellation. The solution is specific and well-defined: wire `adbc_cancel()` from the event-loop thread to interrupt in-flight C calls, join the worker thread before checkin, and shield `__aexit__` cleanup in `CancelScope(shield=True)`. A secondary risk is the **GIL-release premise for pyarrow materialization**: it is verified for driver I/O but unvalidated for `fetch_arrow_table` / `fetchall` Arrow-object construction, which may re-acquire the GIL and serialize concurrent large-result fetches. A feasibility spike benchmarking concurrent slow queries vs concurrent large fetches must precede the full implementation.

## Key Findings

### Recommended Stack

The async layer adds exactly one runtime dependency: `anyio>=4.0.0` (current stable 4.14.1), declared as `[project.optional-dependencies] async = ["anyio>=4.0.0"]`. anyio is the only backend-neutral option (asyncio and trio) with integrated `CapacityLimiter`, cooperative cancellation scopes, and a bundled pytest plugin — all load-bearing here. Python floor is 3.11; `ExceptionGroup`, `ParamSpec`, and `Self` are all stdlib so no `exceptiongroup` backport or direct `typing-extensions` dep is needed. For testing, the anyio built-in pytest plugin drives `@pytest.mark.anyio` tests; `pytest-asyncio` must not be added (asyncio-only, conflicts). `trio>=0.32.0` goes in the dev group only, behind `anyio[trio]`, for the dual-backend test matrix.

**Core technologies (new for v1.4.0):**
- `anyio>=4.0.0`: thread-offload, `CapacityLimiter`, cancellation scopes, bundled pytest plugin — the entire new runtime surface
- `anyio[trio]` (dev-only): trio backend for dual-backend test parametrization — proves neutrality, never a runtime dep

**Explicitly rejected:**
- `sqlalchemy[asyncio]` / `AsyncAdaptedQueuePool`: asyncio-bound (greenlet), does not replace the execute offload, breaks trio neutrality
- `greenlet` direct dep: only needed as SQLAlchemy's sync/async shim, which is not used
- `pytest-asyncio`: asyncio-only, conflicts with anyio plugin in auto mode
- `asyncio.to_thread` / `loop.run_in_executor`: bypasses anyio limiter, breaks trio

### Expected Features

**Must have — v1.4.0 launch (P1):**
- `create_async_pool` / `close_async_pool` / `managed_async_pool` — mirror of sync entry-point trio
- `await pool.connect()` returning `AsyncConnection` (async context manager, shielded `__aexit__`)
- `AsyncCursor` with `execute`, `executemany`, `fetchone`, `fetchmany`, `fetchall`, `close`
- `await cursor.fetch_arrow_table()` — headline Arrow-native differentiator
- `adbc_cancel` cancellation wiring (no-leak on cancel) — P1 correctness requirement
- `await commit()` / `await rollback()` on connection
- anyio backend-neutral throughout (asyncio + trio verified in CI)
- Generic over all 13 backends via existing Protocol — no per-backend async code

**Should have — v1.4.x after validation (P2):**
- `await cursor.fetch_record_batch()` + `async for batch` streaming (Arrow `RecordBatchReader`; trickier lifetime)
- `await cursor.adbc_ingest()` — bulk Arrow write offloaded
- `fetch_df()` / `fetch_polars()` async convenience wrappers

**Defer — v2+ (P3):**
- Async ADBC metadata methods (`adbc_get_table_schema`, `adbc_get_objects`)
- `adbc_prepare` / `adbc_execute_schema` async
- anyio-native checkout limiter replacing offloaded `QueuePool.connect()` — only if measured bottleneck

**Anti-features (never build):**
- Async ORM / query builder — out of scope by charter
- `AsyncAdaptedQueuePool` as foundation — asyncio-bound, wrong abstraction
- Built-in retry / reconnect — consumer-specific policy
- asyncio-only fast path — discards the trio differentiator

### Architecture Approach

The architecture is a thin wrap-and-offload layer in a new `_async/` package. `AsyncPool` holds one sync `QueuePool` (from `_create_pool_impl()`, reused verbatim) plus one dedicated `CapacityLimiter(pool_size + max_overflow)`. Every blocking call — checkout, execute, fetch, close — routes through a single `offload(fn, *args, limiter)` helper wrapping `anyio.to_thread.run_sync`. `AsyncConnection` and `AsyncCursor` wrap the ADBC dbapi objects with async context managers whose `__aexit__` routes through the same connection-return path as sync, ensuring the existing `_release_arrow_allocators` reset event fires symmetrically on async checkin. Cancellation: on cancel-scope trip, `cursor.adbc_cancel()` is called from the event-loop thread (sole ADBC thread-safe operation), the worker joins, the connection is invalidated. `__init__.py` guards async names behind PEP 562 `__getattr__` lazy import so `import adbc_poolhouse` is zero-cost and zero-failing for sync users without the extra.

**Major components:**
1. `_async/_offload.py` — `offload(fn, *args, limiter)` thin wrapper; single chokepoint for cancellation policy
2. `_async/_factory.py` + `_async/_pool.py` (`AsyncPool`) — calls `_create_pool_impl`, owns `CapacityLimiter`, offloads checkout/close
3. `_async/_connection.py` (`AsyncConnection`) — wraps checked-out connection; shielded `__aexit__` returns it to pool; `cursor()` sync-returning (no I/O)
4. `_async/_cursor.py` (`AsyncCursor`) — offloads all execute/fetch; wires `adbc_cancel` in cancel handler; shielded `close()`
5. `__init__.py` (modified) — PEP 562 lazy `__getattr__` for async exports; clear `ImportError` when anyio absent

### Critical Pitfalls

1. **Cancellation leaks the connection** — `abandon_on_cancel=True` without `adbc_cancel` leaves a thread running mid-query on a connection returned to the pool, causing silent corruption and pool exhaustion. Fix: call `cursor.adbc_cancel()` from the event-loop thread, join the worker, invalidate the connection. Shield `__aexit__` checkin with `CancelScope(shield=True)`. Highest-risk item; deserves its own dedicated phase.

2. **Using anyio's shared 40-token global limiter** — process-wide default is competed for by all `to_thread` callers; `pool_size + max_overflow > 40` silently throttles throughput; holding a checkout token while awaiting a second offload deadlocks under load. Fix: every pool owns `CapacityLimiter(pool_size + max_overflow)` passed explicitly to every `run_sync` call.

3. **GIL-release unvalidated for pyarrow materialization** — ADBC execute/network I/O verifiably releases the GIL; pyarrow `RecordBatch` / `Table` construction may re-acquire it, serializing concurrent large-result fetches. This gates the design's concurrency claims. Fix: feasibility spike benchmarking concurrent slow queries vs concurrent large `fetch_arrow_table` calls before building the full surface.

4. **Arrow memory leak from un-closed async cursors** — `__del__` cannot `await close()` so GC-collected cursors leave native Arrow allocators live; RSS grows invisibly. Fix: `AsyncCursor` as mandatory async context manager; route checkin through the existing reset event so `_release_arrow_allocators` fires symmetrically.

5. **asyncio-only idioms silently break under trio** — `asyncio.Lock`, `asyncio.to_thread`, `loop.run_in_executor` all misbehave or error under trio. Fix: anyio primitives exclusively in `_async/`; ruff/import-linter rule banning `import asyncio` in that package; dual-backend CI from day one.

## Implications for Roadmap

### Phase 1: Feasibility Spike — GIL/Concurrency Validation
**Rationale:** The async layer's value proposition rests on the premise that ADBC releases the GIL during execute AND fetch/materialization. Execute/network I/O is inferred-safe from native driver construction; pyarrow object construction is explicitly MEDIUM confidence and unvalidated. Discovering a materialization bottleneck after building the full surface is high-cost to reframe. Spike first, build second.
**Delivers:** Benchmark of N concurrent slow queries (I/O-bound) vs N concurrent large `fetch_arrow_table` calls (materialization-bound), with wall-clock vs ideal-parallel measurements; written go/no-go on what async concurrency wins to claim and what to disclaim in docs.
**Addresses:** Pitfall 3 (GIL premise), Pitfall 12 (establishes deterministic test baseline)
**Research flag:** No additional research needed — pure empirical measurement with DuckDB in-proc.

### Phase 2: Core Async Wrapper — Foundation + Connection + Cursor
**Rationale:** With GIL premise validated (or bounded), build the offload helper, `CapacityLimiter`-owning `AsyncPool`, and `AsyncConnection` / `AsyncCursor` covering the full P1 DBAPI surface. All structural pitfalls except cancellation must be addressed here: dedicated limiter, offload-everything rule, symmetric Arrow cleanup, basedpyright-strict typing, PEP 562 guarded import.
**Delivers:** Working end-to-end async query (`create_async_pool` → `connect` → `execute` → `fetch_arrow_table` → checkin) on DuckDB; sync suite passes with anyio uninstalled; basedpyright strict passes on async module.
**Addresses:** `create_async_pool` / `managed_async_pool` / `close_async_pool`; full `AsyncCursor` DBAPI surface; `fetch_arrow_table`; `commit` / `rollback`; anyio backend-neutral (asyncio + trio CI)
**Avoids:** Pitfall 2 (thread-affinity), Pitfall 4 (leak on error path), Pitfall 5 (Arrow leak), Pitfall 6 (limiter mismatch), Pitfall 7 (event-loop block on checkout), Pitfall 8 (trio breakage), Pitfall 9 (typing gate)
**Research flag:** Standard anyio + ADBC patterns; well-documented. No research-phase needed.

### Phase 3: Cancellation — Cooperative Cancel + Connection Invalidation
**Rationale:** Cancellation is separated because it is the highest-risk correctness item, requires deterministic test infrastructure (a query that blocks predictably until cancelled), and involves the only ADBC cross-thread interaction (`adbc_cancel`). A dedicated phase means focused design review, explicit test assertions (`pool.checkedout() == 0` after cancel, driver reports `ADBC_STATUS_CANCELLED`), and shielded `__aexit__` that is verified rather than assumed.
**Delivers:** Full `adbc_cancel` wiring in `execute` / `fetch_arrow_table`; shielded `__aexit__` checkin; invalidate-on-uncertain-cancel; deterministic cancellation tests under asyncio and trio.
**Avoids:** Pitfall 1 (the #1 correctness risk), Pitfall 4 (cancellation-leg leak)
**Research flag:** No additional research needed; ARCHITECTURE.md has the concrete cancellation flow with code.

### Phase 4: Packaging + Extra Scoping
**Rationale:** The `[async]` extra scoping is cheap but high-stakes: anyio leaking into the always-installed path gives sync users an unwanted dep; a wrong import guard makes `import adbc_poolhouse` fail without the extra. Isolated phase with explicit test coverage (sync CI job with anyio uninstalled) prevents regression.
**Delivers:** `[async]` extra in `pyproject.toml`; `[all]` includes `async`; PEP 562 lazy import in `__init__.py` with clear `ImportError`; sync test job confirmed passing without anyio; version bump.
**Avoids:** Pitfall 10 (`[async]` mis-scoped), Pitfall 11 (API drift — compare public surfaces)
**Research flag:** Standard packaging; no research-phase needed.

### Phase 5: Dual-Backend Cassette Test Matrix
**Rationale:** Backend-generic correctness (all 13 backends, asyncio + trio) is the milestone's cross-cutting promise and is only fully verified by running the async suite across the existing cassette replay matrix. Last because it depends on the full surface being stable; adding cassette tests against an unstable surface requires constant rework.
**Delivers:** `@pytest.mark.anyio` parametrized over asyncio + trio; DuckDB (in-proc) + Snowflake (cassette) async suite; confirmed one async layer covers all 13 backends; memory-stability test for Arrow leak; limiter-sizing stress test.
**Avoids:** Pitfall 12 (flaky tests), Pitfall 8 (trio divergence surfaced late)
**Research flag:** Standard anyio pytest plugin dual-backend patterns; no research-phase needed.

### Phase 6: Documentation + Docs Quality Gate
**Rationale:** CLAUDE.md mandates docs as a completion requirement from Phase 7 onwards. This phase covers the async usage guide, API reference updates, and all new public symbol docstrings (Google-style, Args/Returns/Raises + Example sections). The GIL/materialization findings from Phase 1 must be reflected honestly — the async guide must distinguish I/O-bound wins from materialization-bound limits rather than claiming blanket parallelism.
**Delivers:** Async usage guide (honest about I/O-bound vs materialization limits); API reference for `AsyncPool` / `AsyncConnection` / `AsyncCursor` / entry-point functions; configuration/index updated; `uv run mkdocs build --strict` passes; humanizer pass on all new prose.
**Addresses:** Pitfall 3 (GIL caveat communicated), Pitfall 11 (docs as canonical surface spec)
**Research flag:** Docs-author skill required per CLAUDE.md. Standard mkdocstrings patterns; no research-phase needed.

### Phase Ordering Rationale

- **Spike first:** GIL/materialization validation gates what the async layer can honestly claim and whether the design needs adjusting before any production code is written.
- **Core wrapper before cancellation:** cancellation tests need stable execute/fetch wrappers to exercise; building both together creates a moving target for the hardest piece.
- **Packaging after core + cancellation:** guarding imports is only stable once the module structure is frozen.
- **Cassette tests near the end:** requires the full surface and packaging to be correct; validates the whole stack rather than individual components.
- **Docs last:** requires the full surface, confirmed behaviour, and GIL benchmark results to write honestly.

### Research Flags

Phases needing deeper research during planning:
- **Phase 1 (Feasibility Spike):** No external research needed; empirical benchmarking with DuckDB in-proc to avoid cassette setup overhead.

Phases with standard patterns (skip research-phase during planning):
- **Phase 2 (Core Async Wrapper):** anyio + ADBC thread-offload patterns fully documented; ARCHITECTURE.md has concrete code snippets for all three key patterns.
- **Phase 3 (Cancellation):** `adbc_cancel` + `CancelScope(shield=True)` pattern fully specified in ARCHITECTURE.md with a concrete code example and data-flow diagram.
- **Phase 4 (Packaging):** Standard `pyproject.toml` extras + PEP 562 `__getattr__` — no unknowns.
- **Phase 5 (Test Matrix):** anyio pytest plugin dual-backend parametrization documented in STACK.md.
- **Phase 6 (Docs):** Docs-author skill (per CLAUDE.md) + existing mkdocs/mkdocstrings setup; no new patterns.

### Watch Out For

Three issues have the highest probability of derailing the milestone if not addressed proactively:

1. **Cancellation connection leak** — the most common async DB library bug industry-wide. Do not ship Phase 2 without at minimum an invalidate-on-cancel placeholder; the full `adbc_cancel` join is Phase 3 but Phase 2 must never return a possibly-busy connection on any code path.
2. **40-token global limiter deadlock** — easy to miss in happy-path tests where `pool_size + max_overflow < 40` and no other `to_thread` work runs concurrently. The dedicated per-pool `CapacityLimiter` is a Phase 2 first-class requirement, not a Phase 5 load-testing fix.
3. **GIL / pyarrow materialization caveat** — if Phase 1 benchmarks show large `fetch_arrow_table` calls do not parallelize, the async guide must document this honestly and the implementation may need coarser offload chunks. Do not skip the spike and discover this in user issue reports.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyPI JSON API verified versions; anyio docs confirm all APIs; SQLAlchemy docs confirm `AsyncAdaptedQueuePool` rejection |
| Features | HIGH | ADBC dbapi reference covers full method set; prior-art survey across 6 async DB libraries; conventions converge |
| Architecture | HIGH | ADBC C header + Cython source + concurrency spec read directly; anyio limiter + cancellation from docs; existing source read directly |
| Pitfalls | HIGH (one MEDIUM) | ADBC thread-safety from spec; anyio cancel semantics from docs; GIL-release per-method MEDIUM — must validate empirically |

**Overall confidence:** HIGH

### Gaps to Address

- **GIL / pyarrow materialization (MEDIUM):** whether `fetch_arrow_table` and `fetchall` release the GIL during pyarrow object construction is not documented per-method. Phase 1 (Feasibility Spike) must resolve this before Phase 2 begins. If materialization serializes on the GIL, document concurrency limits rather than adjusting the architecture.
- **Cancellation test infrastructure:** deterministic cancellation tests require a query that blocks predictably until cancelled. Resolve during Phase 3 planning — DuckDB synthetic sleep or a custom pytest-adbc-replay cassette that holds a response.
- **Per-connection `anyio.Lock` necessity:** ARCHITECTURE.md concludes a lock is not required by spec (serialized cross-thread access safe; pool checkout guarantees single-owner). Confirm during Phase 2 that no realistic usage pattern (e.g., two coroutines racing on the same `AsyncConnection`) creates a concurrent-access window. Add the lock defensively if it can.

## Sources

### Primary (HIGH confidence)
- anyio.readthedocs.io/en/stable/threads.html — `to_thread.run_sync`, `abandon_on_cancel`, `CapacityLimiter`, 40-token global limiter
- anyio.readthedocs.io/en/stable/api.html — `CapacityLimiter`, `CancelScope`, `fail_after`, `from_thread`
- anyio.readthedocs.io/en/stable/testing.html — built-in pytest plugin, `@pytest.mark.anyio`, `anyio_backend` parametrization, conflict with `pytest-asyncio`
- arrow.apache.org/adbc/main/cpp/concurrency.html — "serialized access from multiple threads... do not allow concurrent access"
- arrow.apache.org/adbc/main/cpp/api/group__adbc-statement.html — `AdbcStatementCancel`: "must always be thread-safe (other operations are not)"
- arrow.apache.org/adbc/current/python/api/adbc_driver_manager.html — `Cursor.adbc_cancel()`, `Connection.adbc_cancel()`, `threadsafety=1`
- raw.githubusercontent.com/apache/arrow-adbc/main/c/include/arrow-adbc/adbc.h — C header cancel docstrings
- raw.githubusercontent.com/apache/arrow-adbc/main/python/adbc_driver_manager/adbc_driver_manager/_lib.pyx — `with nogil:` GIL-release; `cancel()` wiring
- docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html — `AsyncAdaptedQueuePool` greenlet dependency; `QueuePool` "not compatible with asyncio"
- PyPI JSON API — anyio 4.14.1, trio 0.33.0, pytest 9.1.1 version verification
- adbc-poolhouse source (direct read): `_pool_factory.py`, `_driver_api.py`, `_base_config.py`, `__init__.py`

### Secondary (MEDIUM confidence)
- ADBC GIL-release per-method — inferred from native (Rust/C/Go) driver construction; not explicitly documented per-method; flagged for empirical validation in Phase 1

### Prior-art reference (HIGH confidence)
- magicstack.github.io/asyncpg — pool acquire/release, cancel leak issue #464
- psycopg.org/psycopg3/docs/advanced/async.html — `AsyncConnection` / `AsyncCursor` naming, `cursor()` sync convention, "scatter await"
- github.com/sqlalchemy/sqlalchemy/issues/8145 — documented cancel-leak pattern
- aiosqlite.omnilib.dev — thread-per-connection proxy model reference

---
*Research completed: 2026-06-25*
*Ready for roadmap: yes*
