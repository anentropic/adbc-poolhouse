# Feature Research

**Domain:** Async cursor completion for a thread-offload async ADBC pool wrapper (adbc-poolhouse v1.5.0)
**Researched:** 2026-07-01
**Confidence:** HIGH — the four target methods and their exact signatures/semantics are confirmed against the ADBC dbapi source (`fetch_record_batch`, `fetch_df`, `fetch_polars`, `adbc_ingest`), and every P2 edge behaviour is restated directly from the shipped `ASYNC-EDGE-CASES.md` designs. One MEDIUM-confidence design tension is flagged (streaming reader lifetime vs. reset-event checkin).

## Scope Reminder

This milestone completes the async **cursor** surface only. v1.4.0 already ships `AsyncCursor` with `execute`, `executemany`, `fetchone`/`fetchmany`/`fetchall`, `fetch_arrow_table`, `close`, the async context manager, sync no-I/O properties (`description`/`rowcount`/`arraysize`), and the full `adbc_cancel` + shielded-checkin cancellation machinery. **Do not re-research those.**

The four new methods (`fetch_record_batch`, `adbc_ingest`, `fetch_df`, `fetch_polars`) **already exist on the wrapped sync `adbc_driver_manager.dbapi.Cursor`**. The async versions are **pure offload wrappers** — same pattern as the shipped `fetch_arrow_table`: bracket with the parent connection's `_offloading()` guard, dispatch through `cancellable_offload(self._adbc_cancel, self._cursor.<method>, ..., limiter=self._limiter, on_abort=self._owner.invalidate)`. No new poolhouse dependencies; pandas/polars stay user-supplied (ADBC raises if absent). No sync-core changes.

This research answers: **what "correct" looks like for each of the four methods, plus the P2 async edge-case behaviours** being landed alongside them.

## Confirmed sync API (the surface being wrapped)

From the ADBC dbapi source — verbatim signatures/semantics the async wrappers must preserve:

| Sync method | Signature / return | Key mechanics |
|-------------|--------------------|---------------|
| `fetch_record_batch()` | `→ pyarrow.RecordBatchReader` | Returns `self._results.reader._reader` — a **live reader tied to the statement** (`_stmt`). Batches are pulled on demand; each internal read uses `_blocking_call(reader.read_next..., self._stmt.cancel)`. Not eager. |
| `adbc_ingest(table_name, data, mode='create', *, catalog_name=None, db_schema_name=None, temporary=False)` | `→ int` (rows inserted, or `-1` if unknown) | `mode ∈ {'create','append','replace','create_append'}`; else `ValueError`. `data` bound via `__arrow_c_array__` (Table/RecordBatch) or `__arrow_c_stream__` (RecordBatchReader). Executes via `_blocking_call(self._stmt.execute_update, ..., self._stmt.cancel)`. |
| `fetch_df()` | `→ pandas.DataFrame` | `_blocking_call(self.reader.read_pandas, ..., self._stmt.cancel)` — pandas pulled in by pyarrow's `read_pandas`; raises if pandas absent. |
| `fetch_polars()` | `→ polars.DataFrame` | `import polars; polars.from_arrow(self.fetch_arrow())` under `_blocking_call(..., self._stmt.cancel)` — raises `ModuleNotFoundError` if polars absent. |

Two facts that shape the whole design:

1. **The sync methods already block AND already self-cancel via `self._stmt.cancel`.** Our `cancellable_offload` already fires `cursor.adbc_cancel` on scope-cancel, which is the same statement-level cancel. So the offload + cancel wiring is identical to `fetch_arrow_table` for `fetch_df`/`fetch_polars`/`adbc_ingest` — three genuinely trivial wrappers.
2. **`fetch_record_batch` is the one exception.** It returns a *live reader*, not a materialized result. This is the single non-trivial design item in the milestone (see the streaming section).

## Feature Landscape

### Table Stakes (Users Expect These)

An async ADBC cursor that already ships `fetch_arrow_table` is expected to also offer its immediate siblings. Missing them makes the async surface feel arbitrarily narrower than the sync cursor it wraps.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `await cursor.adbc_ingest(table, data, mode=...)` | Write-path symmetry — a cursor that can Arrow-fetch is expected to Arrow-ingest; the only bulk-write method on ADBC | LOW | Pure offload of the existing sync method through `cancellable_offload`. Forward `mode`, `catalog_name`, `db_schema_name`, `temporary` as keyword-only. Returns the `int` row count unchanged. Depends on: offload chokepoint, `_offloading()` guard, `on_abort=invalidate` (a cancelled ingest poisons the connection exactly like a cancelled execute). |
| `await cursor.fetch_df()` | Row-oriented consumers expect a DataFrame convenience; ADBC ships it, so its absence looks like a gap | LOW | Thin offload over `fetch_arrow_table`-equivalent + pandas conversion (all inside the worker). Materializing → self-owning DataFrame, safe after checkin. Depends on: offload chokepoint. pandas is user-supplied (ADBC/pyarrow raises if absent). |
| `await cursor.fetch_polars()` | Same as `fetch_df` for the polars audience; ADBC ships it | LOW | Identical shape to `fetch_df`; polars user-supplied (`ModuleNotFoundError` if absent). Depends on: offload chokepoint. |
| Materialized-result safety after checkin | Consistency with the shipped `fetch_arrow_table` contract (EDGE-21) | LOW | `fetch_df`/`fetch_polars` return fully-materialized, self-owning objects — safe to read after the connection checks in, same as `pyarrow.Table`. The reset event closing cursors does not invalidate them. |
| Clear "dependency not installed" surface | Users who skip pandas/polars must get an actionable error, not a confusing offload traceback | LOW | ADBC raises `ModuleNotFoundError`/`ImportError` inside the worker; the offload chokepoint re-raises it **unchanged, with the original type and traceback** (ACUR-06/EDGE-17 guarantee). No poolhouse wrapping, no swallowing. Documented as "pandas/polars is user-supplied, like the drivers." |
| The P2 edge-case suite (EDGE-08, 13/14, 20, 22/23, 24, 31/32) | The v1.4.0 P1 suite is green; these are the deferred hardening rows that complete the promised edge coverage | MEDIUM (test-only) | No production code beyond what the four methods need; these pin *existing* behaviour of the shipped layer. See the dedicated P2 section. |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| `await cursor.fetch_record_batch()` returning an **async-iterable Arrow stream** | Stream Arrow `RecordBatch`es off-loop without buffering the whole result — the async, backend-neutral equivalent of psycopg3 `stream()` / SQLAlchemy `AsyncResult`, but Arrow-native and over all 13 backends. No surveyed async DB lib offers Arrow streaming. | **HIGH** | The headline of this milestone. Maintainer wants BOTH `reader = await cursor.fetch_record_batch()` (offload the reader-acquisition) AND `async for batch in reader:` where each `read_next_batch()` is itself offloaded through the limiter with the same cancel wiring. The hard part is **reader lifetime vs. the reset-event checkin** — see the streaming design section. Depends on: offload chokepoint, `cancellable_offload` (per-batch), `_offloading()` guard, and the `_release_arrow_allocators` reset listener. |
| One offload pattern, four new methods, all 13 backends | Because offload is driver-agnostic, the same wrapper adds all four methods across every backend with zero per-backend code | LOW | Reuses v1.4.0's generic `WarehouseConfig` path. No new dispatch. |
| anyio backend-neutral streaming (asyncio + trio) | The `async for` streaming path works under both backends via the same `cancellable_offload`; no asyncio-specific streaming primitive | MEDIUM | Constrains the async-iterator design: no `asyncio.to_thread`, no asyncio-only idioms; each batch pull is an anyio offload under `_offloading()`. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Bundling pandas/polars as poolhouse extras (`[pandas]`/`[polars]`) | "`fetch_df` should just work out of the box" | Breaks the library's settled dependency philosophy — drivers, pandas, polars are all **user-supplied runtime deps**; ADBC itself does not bundle them. Adding extras invites version-conflict reports and bloats the install. | Keep pandas/polars user-supplied; let ADBC raise a clear `ModuleNotFoundError`; document it. No new extras (confirmed scope). |
| A synchronous, pre-materialized `fetch_record_batch` that eagerly drains the reader into a list of batches before returning | "Make streaming safe by reading it all up front" | Defeats the entire point of streaming (unbounded memory), and is strictly worse than the already-shipped `fetch_arrow_table`. | Offer the true lazy reader with a documented lifetime contract; if a user wants everything in memory, they already have `fetch_arrow_table`. |
| Auto-consuming / auto-closing the streaming reader inside the cursor's `__aexit__` or the checkin reset | "Don't make users manage the reader" | Silently draining or closing a reader the user still holds a reference to causes surprising truncation or use-after-checkin; the reset event closing the cursor mid-stream is exactly the hazard to design *against*, not to lean into. | Give the reader a defined lifetime tied to the cursor being open, document "consume before checkin," and make premature reads after checkin fail loudly rather than silently. |
| A `mode='upsert'` / merge convenience on `adbc_ingest` | "Ingest should handle updates" | ADBC exposes exactly four modes (`create`/`append`/`replace`/`create_append`); inventing an upsert means emulating merge logic the drivers don't provide, per-backend and fragile. | Expose the four ADBC modes verbatim; leave merge/upsert to consumer SQL. |
| Re-typing / validating `data` for `adbc_ingest` in the wrapper | "Catch bad input early" | The wrapper is a pure offload; ADBC already accepts anything with `__arrow_c_array__`/`__arrow_c_stream__` and raises clearly otherwise. Adding a poolhouse type gate duplicates ADBC and risks rejecting valid capsule objects. | Pass `data` straight through; let ADBC's binding + `ValueError` on bad `mode` be the contract. Type the param as `pyarrow.Table | RecordBatch | RecordBatchReader` for editor help, not runtime enforcement. |

## The streaming design: `fetch_record_batch` + `async for`

This is the one non-trivial feature and the milestone's headline. The facts and the resulting contract:

**What the sync method actually returns.** `fetch_record_batch()` hands back `self._results.reader._reader` — a live `pyarrow.RecordBatchReader` backed by the statement's Arrow stream. It is **lazy**: batches are pulled from the driver on demand as you iterate. Each internal pull in ADBC is wrapped in `_blocking_call(..., self._stmt.cancel)`, i.e. it can block and is cancellable at the statement level.

**Maintainer's desired shape (both, not either):**

```python
reader = await cursor.fetch_record_batch()   # offload: acquire the reader
async for batch in reader:                    # each read_next_batch() offloaded
    process(batch)
```

**Design contract this implies (the load-bearing decisions for requirements):**

1. **Lazy, not eager.** `await cursor.fetch_record_batch()` offloads only the *acquisition* of the reader (cheap). It must NOT drain the stream. Each batch pull is a **separate offload** — so a long stream is a sequence of repeated offloads, each through the pool limiter and each bracketed by the connection's `_offloading()` guard. This is the correct behaviour and the reason it is a differentiator (true off-loop streaming) rather than a disguised `fetch_arrow_table`.
2. **Return a poolhouse async-iterable wrapper, not the raw `pyarrow.RecordBatchReader`.** The raw reader's `read_next_batch()` is sync and blocking; handing it back bare would let users block the loop. Wrap it in an `AsyncRecordBatchReader` (async iterator) whose `__anext__` offloads one `read_next_batch()` through `cancellable_offload` (fire `adbc_cancel` on scope-cancel, `on_abort=invalidate`), and whose `StopIteration`→`StopAsyncIteration` translation is explicit. `await cursor.fetch_record_batch()` returns this wrapper. (This mirrors psycopg3/SQLAlchemy exposing a distinct async-iterator type for streaming, not the raw server cursor.)
3. **Reader lifetime vs. the reset-event checkin is the headline risk (MEDIUM confidence, needs a pinned decision).** v1.4.0's `_release_arrow_allocators` reset listener closes the connection's cursors on checkin to free Arrow readers. A streaming reader is **use-after-free if read after the connection checks in** — exactly the hazard `fetch_arrow_table` was designed to dodge by materializing. The correct contract: the reader is valid only while its `AsyncCursor` / owning connection is still checked out; reading after checkin must fail loudly (a typed poolhouse error), never silently truncate or segfault. The async-iterator wrapper should detect a closed/checked-in owner and raise, not offload into a freed statement. **This is the one item to design explicitly in requirements** — everything else in the milestone is a copy of the `fetch_arrow_table` pattern.
4. **Concurrency guard still applies per batch.** Each `__anext__` offload holds the parent connection's `_offloading()` guard, so pulling batches from one reader in two tasks raises `ConnectionBusyError` (consistent with EDGE-15). A reader is single-task, like the cursor.
5. **Cancellation per batch reuses the shipped machinery.** A cancel mid-`read_next_batch` fires `adbc_cancel`, invalidates the connection (`on_abort`), and re-raises — identical to a cancelled `execute`. No new cancel logic; just applied at each pull.

## P2 async edge-case behaviours (restated from ASYNC-EDGE-CASES.md)

These pin **existing** behaviour of the shipped v1.4.0 layer (plus, where relevant, the new methods). Each runs under **both asyncio and trio** (except EDGE-27-style meta). Expected/correct behaviour each test asserts:

| Edge | Group | Expected/correct behaviour the test pins | Depends on (v1.4.0 component) |
|------|-------|------------------------------------------|-------------------------------|
| **EDGE-08** | trio-vs-asyncio | A cancel set with **no intervening checkpoint** before `await cursor.execute(...)` is still delivered **at the offload boundary** on both backends: the limiter-acquire/thread-join are checkpoints, so anyio normalises delivery. Assert driver `execute_call_count == 0` and the cancel class propagates. trio is the discriminating leg (proves prompt delivery isn't dropped). | Offload chokepoint (limiter-acquire checkpoint), `cancellable_offload`. |
| **EDGE-13** | contextvars | A `ContextVar` set on the task **before** the offload is **visible inside the worker thread** (anyio copies the current context into the worker). Assert the stub, running in the worker, observed the caller's value. | `offload` uses anyio `to_thread.run_sync` (which copies context) — proves we never hand-roll a thread / use `asyncio.to_thread`. |
| **EDGE-14** | contextvars | A `cv.set(...)` performed **inside the worker** does **not** leak back to the task: after the await, the task still sees its original value (anyio does not propagate worker context changes back). Prevents cross-request context bleed. | Same offload chokepoint; asserts the no-leak-back property is preserved. |
| **EDGE-20** | exceptions | When the body raises (e.g. `ValueError`) **and** the offloaded cleanup (`close`/checkin) *also* raises (e.g. `AdbcError`), the **original body error is what escapes**, with the cleanup error **chained via `__context__`** (not masking it), and the connection is **still released/invalidated** (`checkedout() == 0`). Cleanup failure never hides the root cause nor leaks the connection. | Shielded `close` in `__aexit__`, `_offloading()` guard, `invalidate` path. |
| **EDGE-22** | resource lifetime | `__del__` of an **un-closed** `AsyncCursor`/`AsyncConnection` (GC'd without `close`) emits a `ResourceWarning` and **must not** attempt to `await`/offload (the loop may be gone). Assert: a `ResourceWarning` is emitted, **no** "coroutine was never awaited" `RuntimeWarning`, and **no** exception escapes `__del__`. Arrow memory is reclaimed by the pool reset, not by `__del__`. | Wrapper `__del__` must be sync-only (no coroutine creation); relies on pool reset for reclamation. |
| **EDGE-23** | resource lifetime | The **full happy-path** async lifecycle (create → connect → execute → fetch → checkin → close) emits **no** `RuntimeWarning: coroutine ... was never awaited` from library code. Every internal `async def` is awaited; the sync-returning `cursor()` never creates an un-awaited coroutine. Run under `simplefilter("error", RuntimeWarning)`. | All wrapper methods; the sync-returning `cursor()` boundary (ACONN-03). |
| **EDGE-24** | resource lifetime | An **open pool / pending offload at event-loop shutdown** (no `close_async_pool`) raises **no library-attributable exception** on teardown: a pending worker must not call back into a dead loop, and the sync pool can be GC'd. Assert clean teardown + no stray "Task was destroyed but it is pending". trio's nursery semantics act as the strict canary. | Offload chokepoint (no `from_thread` callback into a dead loop), pool teardown path. |
| **EDGE-31** | time/scheduling | `with move_on_after(0): await cursor.execute(blocking_sql)` — an **already-expired** deadline still cancels a blocked execute **cleanly**: `scope.cancelled_caught is True`, `adbc_cancel` called **exactly once** (worker actually unblocked), connection **invalidated**, `checkedout() == 0`. A zero/negative timeout is handled identically to "expired during the call," never crashing or leaking. | `cancellable_offload`, `adbc_cancel` wiring, `on_abort=invalidate`. |
| **EDGE-32** | time/scheduling | Timeout **precision**: an op completing at **deadline−ε** is **not** over-cancelled — `cancelled_caught is False`, `adbc_cancel_call_count == 0`, **normal checkin** (no invalidate, no pool churn). Guards against off-by-one deadline handling spuriously cancelling in-time ops. Uses a virtual clock. | Same cancel machinery; asserts it does *not* fire on sub-deadline completion (mirror of shipped EDGE-07). |

**Note (EDGE-16 is dead):** the v1.4.0 requirements record EDGE-16 as **N/A / DROPPED** — Phase 24 decision D-24-03 rejects connection aliasing with `ConnectionBusyError` instead of a per-connection lock, so the conditional "cancel bypasses the held lock" test no longer applies. Do not resurrect it.

## Feature Dependencies

```
[v1.4.0 offload chokepoint: offload() / cancellable_offload()]   <- foundational, all four methods reuse it
[v1.4.0 _offloading() connection guard]                          <- brackets every new offloaded call (ConnectionBusyError)
[v1.4.0 adbc_cancel + on_abort=invalidate cancellation]          <- every new blocking offload reuses it verbatim
[v1.4.0 _release_arrow_allocators reset listener]                <- interacts with the streaming reader lifetime

    ├── adbc_ingest        ──requires──> offload chokepoint, _offloading(), cancellable_offload   (trivial copy of fetch_arrow_table)
    ├── fetch_df           ──requires──> offload chokepoint, _offloading()                         (materialized → safe after checkin)
    ├── fetch_polars       ──requires──> offload chokepoint, _offloading()                         (materialized → safe after checkin)
    └── fetch_record_batch ──requires──> offload chokepoint, _offloading(), cancellable_offload (PER BATCH)
                           ──conflicts──> _release_arrow_allocators reset  (reader must not outlive checkin)
                           ──enables───> AsyncRecordBatchReader async-iterator wrapper (new type)

[P2 edge tests] ──pin behaviour of──> the shipped v1.4.0 layer (EDGE-08/13/14/20/22/23/24/31/32); test-only, no new prod code
```

### Dependency Notes

- **Three of four methods are trivial.** `adbc_ingest`, `fetch_df`, `fetch_polars` are byte-for-byte the `fetch_arrow_table` wrapper pattern: `with self._owner._offloading(): return await cancellable_offload(self._adbc_cancel, self._cursor.<method>, <args>, limiter=self._limiter, on_abort=self._owner.invalidate)`. They add **no** new architectural concept.
- **`fetch_record_batch` is the only design work.** It introduces one new type (`AsyncRecordBatchReader`) and one new invariant (reader validity tied to the checked-out connection, enforced against the reset listener). Everything else it needs already exists.
- **`adbc_ingest` invalidation semantics matter.** A cancelled ingest leaves the connection in an unknown write state → it MUST use `on_abort=invalidate` like `execute`, not a "return busy" path. Do not treat ingest as a read-only fetch.
- **DataFrame convenience is materialize-then-convert.** `fetch_df`/`fetch_polars` fully materialize inside the worker, so the returned DataFrame is self-owning and survives checkin (same EDGE-21 guarantee as `pyarrow.Table`). No reader-lifetime concern for these two.
- **P2 edge tests depend on existing infra, not new code.** They reuse the `BlockingStubCursor`, virtual-clock/event-gating harness, and import-lint guard already built in Phase 23 (TEST-05). The suite mostly pins current behaviour; the only production surface they might exercise is the new methods' cancel/cleanup paths (which reuse shipped machinery).

## MVP Definition

### Launch With (v1.5.0)

The full confirmed scope — all four methods plus the P2 suite.

- [ ] `await cursor.adbc_ingest(table_name, data, *, mode='create', catalog_name=None, db_schema_name=None, temporary=False)` — offload wrapper, `on_abort=invalidate`, returns `int` row count, four modes verbatim.
- [ ] `await cursor.fetch_df()` — offload wrapper; pandas user-supplied; materialized/self-owning.
- [ ] `await cursor.fetch_polars()` — offload wrapper; polars user-supplied; materialized/self-owning.
- [ ] `await cursor.fetch_record_batch()` → `AsyncRecordBatchReader` with `async for batch in ...` — lazy per-batch offload; reader-lifetime contract enforced against the reset listener. **The one design item.**
- [ ] P2 edge-case suite: EDGE-08, 13, 14, 20, 22, 23, 24, 31, 32 — deterministic, both backends, reusing the shipped harness.
- [ ] Docs: guide + API-reference entries for the four methods (docs-author skill required, phase ≥ 7 gate), including the "pandas/polars user-supplied" note and the streaming reader-lifetime caveat.

### Add After Validation (v2+)

- [ ] Async ADBC metadata (`adbc_get_table_schema`, `adbc_get_objects`, `adbc_get_info`) — deferred to v2+ per v1.4.0 requirements; trigger: Semantic ORM needs async catalog introspection.
- [ ] Async prepared statements (`adbc_prepare`, `adbc_execute_schema`) — deferred to v2+; niche.
- [ ] anyio-native checkout limiter (vs offloaded `QueuePool.connect()`) — only if offloaded checkout is a measured bottleneck.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| `fetch_record_batch()` + `async for` streaming | HIGH | HIGH | P1 (this milestone's headline) |
| `adbc_ingest()` async | MEDIUM-HIGH | LOW | P1 |
| `fetch_df()` async | MEDIUM | LOW | P1 |
| `fetch_polars()` async | MEDIUM | LOW | P1 |
| P2 edge suite (EDGE-08/13/14/20/22/23/24/31/32) | HIGH (correctness/hardening) | MEDIUM (test-only) | P1 |
| Async ADBC metadata methods | LOW-MEDIUM | LOW | P3 |
| `adbc_prepare` / `adbc_execute_schema` | LOW | LOW | P3 |

**Priority key:** P1 = must-have for v1.5.0 · P3 = future (v2+). (No P2 tier in this milestone — the four methods and the deferred edge suite ARE the whole scope.)

## Competitor Feature Analysis

| Feature | asyncpg / psycopg3 | SQLAlchemy 2.x asyncio | Our v1.5.0 approach |
|---------|--------------------|------------------------|---------------------|
| Streaming reads | server-side cursor / `cur.stream()` → async iterator | `conn.stream()` → `AsyncResult`, `async for` | `await cursor.fetch_record_batch()` → `AsyncRecordBatchReader`, `async for batch` — **Arrow-native**, per-batch offload, both backends |
| Bulk write | `copy_records_to_table` (asyncpg) / `cursor.copy()` (psycopg3) | ORM bulk ops / `executemany` | `await cursor.adbc_ingest(table, data, mode=...)` — Arrow capsule in, `int` rows out, four modes |
| DataFrame convenience | none native (row → user converts) | none native | `await cursor.fetch_df()` / `fetch_polars()` — thin Arrow-backed conveniences |
| Streaming lifetime safety | reader tied to open cursor/txn | result tied to open connection | reader tied to checked-out connection; **fails loudly** after checkin (vs. reset-event close) |
| Backend/loop neutrality | one DB, asyncio-only | many DBs, asyncio-only | all 13 ADBC backends, asyncio **and** trio |

## Sources

- ADBC dbapi `Cursor` source — `fetch_record_batch` returns `self._results.reader._reader` (live, statement-tied); `fetch_df` = `_blocking_call(reader.read_pandas, ..., _stmt.cancel)`; `fetch_polars` = `import polars; polars.from_arrow(...)`; `adbc_ingest` mode mapping (`create/append/replace/create_append`, else `ValueError`), `bind`/`bind_stream` on `__arrow_c_array__`/`__arrow_c_stream__`, returns `execute_update` row count — https://raw.githubusercontent.com/apache/arrow-adbc/main/python/adbc_driver_manager/adbc_driver_manager/dbapi.py — **HIGH**
- ADBC dbapi API reference — verbatim `adbc_ingest` signature + mode docstrings (`'append'` error-if-missing, `'create'` error-if-exists, `'create_append'` create-if-not-exists, `'replace'` drop-then-create), returns "number of rows inserted, or -1"; `fetch_record_batch` → `pyarrow.RecordBatchReader`; `fetch_df` → `pandas.DataFrame`; `fetch_polars` → `polars.DataFrame` — https://arrow.apache.org/adbc/current/python/api/adbc_driver_manager.html — **HIGH**
- `.planning/research/ASYNC-EDGE-CASES.md` — full P2 edge designs (EDGE-08, 13/14, 20, 22/23, 24, 31/32) restated above — local, **HIGH**
- `.planning/milestones/v1.4.0-REQUIREMENTS.md` — Future Requirements (the four deferred methods), P2 deferral list, EDGE-16 DROPPED (D-24-03) — local, **HIGH**
- `src/adbc_poolhouse/_async/_cursor.py` — the shipped `fetch_arrow_table` offload pattern the four wrappers copy (`_offloading()` guard, `cancellable_offload(self._adbc_cancel, ..., on_abort=self._owner.invalidate)`); EDGE-21 materialized-safety docstring — local, **HIGH**
- v1.4.0 FEATURES.md prior-art survey (psycopg3 `stream()`, SQLAlchemy `AsyncResult`, asyncpg cursors) — local, **HIGH**

---
*Feature research for: async cursor completion (fetch_record_batch, adbc_ingest, fetch_df, fetch_polars) + P2 edge suite — adbc-poolhouse v1.5.0*
*Researched: 2026-07-01*
