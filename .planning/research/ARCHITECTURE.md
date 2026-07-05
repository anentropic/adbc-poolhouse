# Architecture Research

**Domain:** Completing the async cursor surface (v1.5.0) over the shipped v1.4.0 anyio thread-offload layer of adbc-poolhouse
**Researched:** 2026-07-01
**Confidence:** HIGH (grounded in the installed `adbc_driver_manager` 1.11.0 dbapi source, live DuckDB probes, and the v1.4.0 `_async/` source read directly)

> Scope: how the four v1.5.0 methods (`fetch_record_batch`, `adbc_ingest`, `fetch_df`, `fetch_polars`)
> plus the P2 edge-case suite integrate WITH the existing v1.4.0 async architecture. This document does
> NOT restate the v1.4.0 architecture (see `.planning/milestones/v1.4.0-research/ARCHITECTURE.md`); it
> assumes the offload chokepoint (`_offload.offload`), the cooperative-cancel task-group
> (`_cancel.cancellable_offload`), the transient-token limiter model, the `_in_use` aliasing guard, and
> the shielded check-in that fires `_release_arrow_allocators`. Every method here is a pure offload
> wrapper over a method that already exists on the wrapped sync ADBC cursor. No new deps, no sync-core
> changes.

---

## Settled Decisions (read this first)

| # | Question | Decision | Confidence |
|---|----------|----------|------------|
| 1 | `fetch_record_batch` lifetime vs checkin | **Do NOT hand back the live `RecordBatchReader`. Offload a drain-to-`RecordBatchReader`-of-materialized-batches (equivalently: return a `pyarrow.Table` via a streaming iterator that is fully consumed before checkin).** The public async streaming surface is an `AsyncRecordBatchReader` wrapper whose iteration is *bounded by the cursor lifetime* and which **drains-on-close**; the connection must not be checked in while a reader is live. See the dedicated section — this is the headline risk. | HIGH |
| 2 | `async for batch` granularity | **Per-batch offload.** Each `read_next_batch()` is one `cancellable_offload` through the pool limiter (transient token per pull), because each pull is an ADBC `_blocking_call` wired to `stmt.cancel`. Reader creation (`fetch_record_batch()` itself, cheap, no I/O) is a trivial offload. | HIGH |
| 3 | `adbc_ingest` granularity | **Single whole-operation `cancellable_offload`.** It is one blocking `execute_update` internally wired to `stmt.cancel`, so it maps exactly onto the existing cursor cancel path. It is I/O/GIL-releasing on the write side; binding large in-memory Arrow data is a pointer hand-off, not a copy. | HIGH |
| 4 | `fetch_df` / `fetch_polars` granularity | **Single `cancellable_offload` each.** Both fully materialize (drain the reader to a pandas/polars frame in the worker) and are internally `_blocking_call`-wired to `stmt.cancel`. Materialization re-acquires the GIL (SPIKE-02), so concurrent large conversions serialize — document, don't fix. | HIGH |
| 5 | contextvars boundary | **No new code needed; document + test only.** `offload` routes through `anyio.to_thread.run_sync`, which copies the task context into the worker and does NOT propagate worker mutations back. EDGE-13/14 are assertions over the existing chokepoint. | HIGH |
| 6 | `__del__` / loop-shutdown finalizers | **`__del__` must never `await`/offload.** Add a sync `__del__` on `AsyncCursor`/`AsyncConnection` that, if not closed, emits `ResourceWarning` and relies on the pool `reset` event (already fires on GC of the sync fairy) to reclaim Arrow memory. Never schedule a coroutine from `__del__`. | HIGH |
| 7 | New vs modified components | **New:** four methods on `AsyncCursor`, one `AsyncRecordBatchReader` async-iterator wrapper, two Protocol method additions on `_SyncCursor`, `__del__` finalizers. **Untouched:** `_offload.offload`, `_cancel.cancellable_offload`, `AsyncPool`, `AsyncConnection` core, the sync core, the cancellation machinery. | HIGH |
| 8 | Build order | reader-lifetime design + `AsyncRecordBatchReader` → `adbc_ingest` → `fetch_df`/`fetch_polars` → P2 edge suite. Dependency-ordered below. | HIGH |

---

## The Headline Risk: `RecordBatchReader` lifetime vs checkin (Q1)

### What the driver actually returns (verified)

`adbc_driver_manager.dbapi.Cursor.fetch_record_batch()` (v1.11.0) returns a **live** `pyarrow.lib.RecordBatchReader`:

```python
def fetch_record_batch(self) -> "pyarrow.RecordBatchReader":
    ...
    return self._results.reader._reader   # the real PyArrow C++ reader, bound to the statement
```

`self._results` is a `_RowIterator` holding `self._stmt` (the `AdbcStatement`) and an
`ArrowArrayStreamHandle`. The reader pulls batches lazily via `reader.read_next_batch()`, which under the
hood is `_blocking_call(self.reader.read_next_batch, ..., self._stmt.cancel)` — i.e. **each pull is a
fresh blocking C call into the still-open statement, and each is individually cancellable via
`stmt.cancel`.** The reader is NOT self-owning; it is a cursor over the live result stream.

### The concrete failure mode (probed on DuckDB, ADBC 1.11.0)

The v1.4.0 checkin path is load-bearing here. On checkin the pool `reset` event fires
`_release_arrow_allocators`, which **closes every open cursor on the connection**:

```python
for cur in list(getattr(dbapi_conn, "_cursors", [])):
    if not getattr(cur, "_closed", True):
        cur.close()          # -> _clear() -> self._results.close() -> reader.close(); stmt.close()
```

`Cursor.close()` calls `_clear()` which closes `self._results`, releasing the reader and the statement.
A live reader read AFTER that point is a use-after-free. Confirmed empirically:

```
reader = cur.fetch_record_batch()
b0 = reader.read_next_batch()      # ok  -> 2048 rows
cur.close()                        # simulates checkin closing cursors
reader.read_next_batch()           # -> ArrowInvalid: "Attempt to read from a stream that has already been closed"
```

Contrast with `fetch_arrow_table` (EDGE-21, already proven safe): it returns a **fully materialized,
self-owning `pyarrow.Table`** — reading `.num_rows` after checkin works because the buffers are copied out
of the stream. A `RecordBatchReader` has no such guarantee; it dangles the instant the statement closes.

Also probed: **drain-then-close is safe.** If the reader is fully drained into a `pyarrow.Table` (or a
list of batches) *before* `cur.close()`, the resulting object survives checkin (5000 rows read back after
`conn.close()`).

### Recommended design: `AsyncRecordBatchReader`, drain-bounded, never-live-across-checkin

The async streaming surface must NOT expose the raw dangling reader across the await/checkin boundary.
Ship a thin `AsyncRecordBatchReader` wrapper with these invariants:

1. **Creation is cheap and offloaded.** `await cursor.fetch_record_batch()` offloads
   `sync_cursor.fetch_record_batch()` (no I/O — it just imports the C stream and hands back the reader),
   holds the `_in_use` guard for that instant, and returns an `AsyncRecordBatchReader` bound to the same
   `AsyncCursor` (so it shares the limiter and the parent connection's `_in_use` guard).

2. **`async for batch in reader:` offloads each pull.** `__anext__` runs
   `cancellable_offload(self._cursor._adbc_cancel, reader.read_next_batch, ...)` — one transient token per
   batch, each pull individually cancellable, each guarded by the parent connection's `_in_use` flag (so
   two tasks pulling from the same reader, or a concurrent `execute`, get `ConnectionBusyError`). On
   `StopIteration` from the C reader the async iterator raises `StopAsyncIteration`.

3. **The reader lifetime is bound to the cursor, and the cursor's `__aexit__`/`close` drains-or-closes
   the reader FIRST.** The rule the whole design rests on: **a connection is never checked in while a
   reader is live.** Two enforcement layers:
   - The `AsyncCursor` tracks its outstanding reader (`self._reader`). `close()` (shielded) closes the
     reader before closing the cursor — the sync `cur.close()` already does this via `_clear()`, so no
     extra work; the wrapper just must not check the connection in behind the user's back while iterating.
   - Because the user drives checkin explicitly (`async with await pool.connect()`), the reader is created
     and consumed *inside* that block. The reader wrapper does not itself trigger checkin. If the user
     exits the `async with` mid-stream, `__aexit__` → shielded `fairy.close()` → `reset` event closes the
     cursor and reader deterministically; any later `__anext__` raises a clear typed error, not a segfault.

4. **Mid-stream checkin protection.** If the user checks the connection back in mid-stream (exits the
   context while a reader is un-drained), define the behaviour: the reader is closed by the `reset` event,
   and a subsequent `await reader.__anext__()` raises a clear typed error (a `PoolhouseError` subclass such
   as `ReaderClosedError`, or a re-raised `AdbcError`) — never a use-after-free. Add an explicit
   `_closed`/`_detached` flag on `AsyncRecordBatchReader` set on cursor close so the wrapper can raise a
   library-attributable error before ever touching the freed C reader.

5. **Cancellation mid-stream.** Each `__anext__` pull is a `cancellable_offload`, so a cancel/timeout
   landing during a `read_next_batch()` fires `adbc_cancel` (the watcher path), the poisoned connection is
   invalidated via `on_abort=self._owner.invalidate` (shielded), and the cancellation is re-raised —
   identical to `execute`/`fetch_arrow_table` today. After a mid-stream cancel the connection is invalid,
   so the reader is dead; the wrapper's `_detached` flag makes any further pull a clean typed error.

**Alternative considered and rejected: return a materialized `pyarrow.Table` from `fetch_record_batch`.**
That is just `fetch_arrow_table` under another name and defeats the purpose (streaming large results
without materializing the whole thing). The streaming value proposition requires a live reader; the design
above makes it safe by binding the reader's lifetime to the cursor and forbidding checkin-while-live,
rather than by materializing.

**Alternative considered and rejected: drain-eagerly-on-creation.** Draining the whole stream inside the
`fetch_record_batch()` offload would materialize everything (again defeating streaming) and hold one
limiter token for the entire drain. Rejected. Per-pull offload keeps memory bounded and cooperative
cancellation per batch.

> **The invariant to test (new EDGE for v1.5.0, extends EDGE-21):** a `RecordBatchReader` obtained from
> the async cursor, read after checkin, raises a clear library error — never a segfault or
> `ArrowInvalid` leaking from freed memory. And: a reader fully consumed *before* checkin yields correct
> data (drain-then-close). Both under asyncio and trio.

---

## Offload granularity per method (Q2)

| Method | Offload unit | Cancellable? | GIL during work | Rationale |
|--------|-------------|--------------|-----------------|-----------|
| `fetch_record_batch()` (creation) | 1 offload (trivial) | via `offload` (no adbc_cancel needed — no I/O) | n/a | Just imports the C stream handle; returns the wrapper. |
| `AsyncRecordBatchReader.__anext__` | 1 `cancellable_offload` **per batch** | yes — each `read_next_batch` is `_blocking_call(..., stmt.cancel)` | **released** during network/decode pull | Per-pull matches ADBC's own per-pull cancellability; keeps memory bounded; cooperative cancel per batch. |
| `adbc_ingest(...)` | 1 whole-operation `cancellable_offload` | yes — internally `_blocking_call(stmt.execute_update, ..., stmt.cancel)` | **released** on the C write; bind is a pointer hand-off | One indivisible write; maps exactly onto the existing cursor cancel path. Data size doesn't change granularity — the whole ingest is one statement. |
| `fetch_df()` | 1 whole-operation `cancellable_offload` | yes — `_blocking_call(reader.read_pandas, ..., stmt.cancel)` | **re-acquires GIL** during pandas construction (SPIKE-02) | Fully materializes; single offload returns a self-owning `pandas.DataFrame` safe after checkin (like `fetch_arrow_table`). |
| `fetch_polars()` | 1 whole-operation `cancellable_offload` | yes — `_blocking_call(lambda: polars.from_arrow(fetch_arrow()), ..., stmt.cancel)` | **re-acquires GIL** during polars construction | Same as `fetch_df`; returns self-owning `polars.DataFrame`. |

**`adbc_ingest` and GIL:** the driver binds the Arrow data (`bind`/`bind_stream` — a C pointer export,
not a data copy) then calls `execute_update` under `nogil`. So concurrent ingests get real parallelism on
the write side. Large `data` does not make the offload CPU-bound in Python; the bytes are already
materialized Arrow buffers handed to C by reference. No streaming-of-ingest is needed for v1.5.0.

**`fetch_df`/`fetch_polars` and the SPIKE-02 asymmetry:** SPIKE-02 established that ADBC execute/network
I/O releases the GIL but **pyarrow → pandas/polars materialization re-acquires it**, so N concurrent large
conversions serialize on the GIL rather than running in parallel. These two methods sit squarely on the
materialization side. Design consequence: **do not claim conversion-parallelism.** The offload still buys
the essential win (the loop is not blocked — other coroutines advance while one worker materializes,
EDGE-26), but throughput of concurrent large `fetch_df` calls is materialization-bound, not
connection-bound. This must be documented honestly in the async guide, consistent with the v1.4.0
DOCS-01 posture for `fetch_arrow_table`.

**Self-ownership after checkin:** `fetch_df` returns a `pandas.DataFrame` and `fetch_polars` a
`polars.DataFrame`, both fully materialized in the worker and self-owning — safe to read after checkin,
same category as `fetch_arrow_table` (EDGE-21). Only `fetch_record_batch` returns a live reader and needs
the special lifetime handling above.

---

## contextvars at the offload boundary (Q3 / EDGE-13/14)

**No new code.** `offload` calls `anyio.to_thread.run_sync`, whose documented semantics are exactly what
EDGE-13/14 require:

- **Copied in (EDGE-13):** "any context variables available on the task will also be available to the code
  running on the thread." A `ContextVar` set before `await cursor.execute(...)` is readable by the sync
  driver code (and any logging filter) in the worker. This is a *copy* of the current `contextvars.Context`
  at dispatch time.
- **No leak back (EDGE-14):** changes the worker makes (`cv.set(...)`) run in the worker's copy and **do
  not propagate back** to the awaiting task. After the offload returns, the task's `cv.get()` is unchanged.

**What the tests must assert (deterministic, both backends):**
- EDGE-13: set `cv.set("abc")`; offload a stub `fn` that reads `cv.get()` and records it; assert the stub
  observed `"abc"`.
- EDGE-14: set `cv.set("outer")`; offload a stub `fn` that does `cv.set("inner")`; after the await, assert
  `cv.get() == "outer"` on the task side.

**Why this is load-bearing for v1.5.0 specifically:** the new methods add more offload sites, but they all
route through the same single chokepoint, so the contextvars property holds for `adbc_ingest`,
`fetch_df`, `fetch_polars`, and every `__anext__` pull for free. The test locks in "we use anyio's
`to_thread`, never a hand-rolled thread or `run_in_executor`," which would silently drop context. The
`_mark_started` bridge in `cancellable_offload` runs on the loop thread (via `from_thread.run_sync`) and
touches no context var, so it does not perturb this.

---

## Resource lifetime / `__del__` and loop shutdown (Q4 / EDGE-22/23/24)

### `__del__` finalizers (EDGE-22/23)

The rule: **`__del__` is synchronous and must never `await`, offload, or schedule a coroutine.** The loop
may be gone at GC time; scheduling an offload raises "no running event loop," and creating-but-not-awaiting
a coroutine raises "coroutine was never awaited" (RuntimeWarning).

Design:
- Add `__del__` to `AsyncCursor` and `AsyncConnection` that:
  - if the object was never closed (`_closed`/`_in_use` bookkeeping says a resource is outstanding), emit
    a `ResourceWarning` ("AsyncCursor was not closed; use `async with` or `await cursor.close()`");
  - does **not** attempt any cleanup that needs the loop. Arrow memory is reclaimed independently: the sync
    fairy's own GC path and the pool `reset` event (`_release_arrow_allocators`) close the underlying
    cursors. The finalizer's job is to *warn*, not to clean up.
- The happy path (proper `async with` / `await close()`) sets a `_closed` flag so `__del__` emits nothing
  (EDGE-23: no `ResourceWarning` on the clean path, and no "coroutine never awaited" from library code).

**EDGE-23 (no stray coroutine warning):** because `cursor()` is a *synchronous* accessor and the reader
wrapper's iteration methods are the only new `async def`s, audit that no library code path creates a
coroutine it forgets to await. The full happy-path lifecycle under
`warnings.simplefilter("error", RuntimeWarning)` must raise nothing. The new `AsyncRecordBatchReader`
is the main new surface to check — its `__anext__`/`__aiter__` must always be awaited by the `async for`
machinery, never dropped.

### Loop shutdown with an open pool / pending offload (EDGE-24)

- A pending per-batch offload at loop teardown behaves exactly like a pending `execute` offload today: the
  worker is `abandon_on_cancel=False`, so anyio joins it; the sync pool can be GC'd; the worker must not
  call back into a dead loop. The `_mark_started` bridge uses `from_thread.run_sync`, which is only invoked
  while the loop is alive and the offload is in flight — it does not fire at shutdown for an un-dispatched
  worker.
- Test (EDGE-24): create a pool, start (do not await to completion) a blocked stream pull, exit the test
  scope so the backend tears down; assert no library-attributable exception and no "Task was destroyed but
  it is pending" from library code. Trio's nursery strictness is the canary. This is unchanged from the
  v1.4.0 EDGE-24 design — the new methods just add more offload sites that must obey the same discipline.

---

## New vs Modified Components (Q5)

### New

| Component | Responsibility | Notes |
|-----------|----------------|-------|
| `AsyncCursor.fetch_record_batch()` | Offload reader creation; return `AsyncRecordBatchReader` | Holds `_in_use` for the (instant) creation offload. |
| `AsyncRecordBatchReader` (new class, `_async/_reader.py`) | Async iterator over the live sync reader; per-batch `cancellable_offload`; `_detached` guard; drain-on-cursor-close | The one genuinely new *type*. Binds reader lifetime to the cursor; forbids read-after-checkin with a clear typed error. |
| `AsyncCursor.adbc_ingest(...)` | Single whole-operation `cancellable_offload` of `sync_cursor.adbc_ingest` | Signature mirrors the dbapi: `table_name`, `data`, `mode`, keyword-only `catalog_name`/`db_schema_name`/`temporary`. `TypeVarTuple` arity concern: keyword-only args after `data` — pass through explicitly like `fetchmany`'s two-arm pattern, or wrap in a `functools.partial`/lambda inside the wrapper so the offload sees a nullary/positional shape. |
| `AsyncCursor.fetch_df()` / `fetch_polars()` | Single `cancellable_offload` each; return self-owning frame | pandas/polars are user-supplied at runtime; ADBC raises `ImportError` if absent — surfaces unchanged through the chokepoint (no new poolhouse extra). |
| `_SyncCursor` Protocol additions | `fetch_record_batch`, `adbc_ingest`, `fetch_df`, `fetch_polars` method signatures | Structural additions so basedpyright-strict types the new offloads; return types are `pyarrow.RecordBatchReader` / `int` / `pandas.DataFrame` / `polars.DataFrame` under `TYPE_CHECKING`. |
| `__del__` on `AsyncCursor` / `AsyncConnection` | Emit `ResourceWarning` if unclosed; never await | EDGE-22/23. |

### Modified (minimal)

- `_SyncCursor` Protocol (add four method stubs).
- `AsyncCursor.__init__`/`close` to track the outstanding `AsyncRecordBatchReader` and close it first on
  shielded `close()` (the sync `_clear()` already does this — the wrapper just tracks the handle to set the
  `_detached` flag and raise clean errors).

### Untouched (do NOT change)

- `_offload.offload` — the single chokepoint. All new methods route through it (directly or via
  `cancellable_offload`). The `scan_async_package` guard still audits exactly one `to_thread.run_sync` site.
- `_cancel.cancellable_offload` — reused verbatim for `adbc_ingest`, `fetch_df`, `fetch_polars`, and each
  per-batch pull. Its `on_abort=invalidate` + `on_dispatch` gating already give the correct
  never-started/really-started semantics.
- `AsyncPool`, the limiter sizing, the transient-token model.
- `AsyncConnection` core: `_in_use` guard, `_offloading()` context manager, shielded check-in,
  `invalidate` + `_teardown_limiter`.
- The sync core (`_pool_factory`, `_release_arrow_allocators`, config dispatch) — zero changes.
- The whole cancellation machinery (`adbc_cancel` wiring, invalidate-on-abort, shield discipline).

---

## Data Flow

### Streaming query flow (new)

```
async with await pool.connect() as conn:        # checkout offload (existing)
    cur = conn.cursor()                          # sync, no I/O (existing)
    await cur.execute(sql)                       # cancellable_offload (existing)
    reader = await cur.fetch_record_batch()      # NEW: trivial offload -> AsyncRecordBatchReader
    async for batch in reader:                   # NEW: per-batch cancellable_offload
        #        offload -> reader.read_next_batch()  (worker; _blocking_call w/ stmt.cancel; GIL released)
        process(batch)                           # batch is a materialized RecordBatch (self-owning)
    # exit context -> shielded fairy.close() -> reset event -> _release_arrow_allocators
    #   closes the cursor + reader deterministically.  reader now _detached; further pull = typed error.
```

### Cancellation mid-stream (new, but reuses existing machinery)

```
async for batch in reader:
   await reader.__anext__()  ──cancellable_offload──▶ read_next_batch()  ── blocked (nogil)
      │ (timeout / cancel)
      ▼
   watcher catches cancel ──shield──▶ adbc_cancel()  ──▶ read_next_batch returns CANCELLED
      ├─ aborted_by_us = True
      ├─ await on_abort() == conn.invalidate()   (shielded; pool checkedout -> 0)
      ▼
   reader._detached = True ; re-raise cancellation   (any later __anext__ = clean typed error)
```

---

## Anti-Patterns

### Anti-Pattern 1: Handing back the raw live `RecordBatchReader` across checkin
**What people do:** `return await offload(cur.fetch_record_batch)` and let the user iterate whenever.
**Why it's wrong:** the reader is bound to the statement; checkin's `reset` event closes the cursor and the
reader, so a read after checkin is a use-after-free (`ArrowInvalid: stream already closed`, probed).
**Do this instead:** wrap in `AsyncRecordBatchReader` bound to the cursor lifetime, forbid checkin while
live, and raise a clear typed error on read-after-detach.

### Anti-Pattern 2: One offload for the whole stream drain
**What people do:** drain the reader to a list inside the `fetch_record_batch` offload.
**Why it's wrong:** materializes everything (defeats streaming) and holds one limiter token for the entire
drain, blocking the pool.
**Do this instead:** per-batch offload via `__anext__`; each pull is a transient token and independently
cancellable.

### Anti-Pattern 3: `await` / offload inside `__del__`
**What people do:** try to close the cursor from `__del__` by scheduling a coroutine.
**Why it's wrong:** the loop may be gone → "no running event loop" / "coroutine was never awaited."
**Do this instead:** `__del__` only emits `ResourceWarning`; rely on the pool `reset` event for Arrow
reclamation.

### Anti-Pattern 4: Claiming `fetch_df`/`fetch_polars` parallelize
**What people do:** document DataFrame conversion as concurrent.
**Why it's wrong:** pandas/polars construction re-acquires the GIL (SPIKE-02); N concurrent large
conversions serialize.
**Do this instead:** document the materialization-bound limit; the win is a non-blocked loop, not
conversion throughput.

### Anti-Pattern 5: Adding a pandas/polars poolhouse extra
**What people do:** add `[dataframe]` extras pinning pandas/polars.
**Why it's wrong:** breaks the "drivers and frames are user-supplied runtime deps" charter; ADBC already
raises `ImportError` if absent.
**Do this instead:** let the `ImportError` from the worker surface unchanged through the chokepoint.

---

## Integration Points

### Internal boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `AsyncCursor ↔ AsyncRecordBatchReader` | wrapper holds parent cursor ref; shares limiter + `_in_use` guard | Reader pulls bracket the parent connection's `_in_use` (concurrent pull/execute → `ConnectionBusyError`). |
| `AsyncRecordBatchReader ↔ cancellable_offload` | per-batch `read_next_batch` offload, `on_abort=owner.invalidate` | Identical cancel semantics to `execute`. |
| `AsyncCursor.{adbc_ingest,fetch_df,fetch_polars} ↔ cancellable_offload` | single whole-op offload each | `stmt.cancel`-wired internally; maps onto the existing cancel path. |
| `_SyncCursor Protocol ↔ ADBC dbapi Cursor` | structural typing, 4 new method stubs | Return types under `TYPE_CHECKING`; keeps the layer driver-agnostic. |
| `reset` event ↔ live reader | `_release_arrow_allocators` closes cursor → closes reader | The mechanism that makes read-after-checkin unsafe; drives the `_detached` guard. |

### External / packaging

| Item | Decision | Notes |
|------|----------|-------|
| pandas / polars | **user-supplied runtime deps; no new extra** | ADBC raises `ImportError` if missing; surfaces unchanged. |
| New runtime deps | **none** | Pure offload wrappers over existing sync ADBC methods. |
| `[async]` extra | unchanged (`anyio` only) | No addition. |

---

## Suggested Build Order (Q8 — dependency-ordered)

1. **`fetch_record_batch` + `AsyncRecordBatchReader` (the headline).** Design and land the reader-lifetime
   wrapper first: creation offload, per-batch `cancellable_offload` in `__anext__`, `_detached` guard,
   drain-on-cursor-close, read-after-checkin typed error. Add the `_SyncCursor.fetch_record_batch` stub.
   *Verifies:* streaming works; read-after-checkin raises a clean error (new EDGE extending EDGE-21);
   mid-stream cancel invalidates and re-raises; both backends. This is the riskiest piece and everything
   else is simpler, so front-load it.
2. **`adbc_ingest`.** Single whole-op `cancellable_offload`; handle the keyword-only args (mirror
   `fetchmany`'s explicit-arm pattern or a lambda). Add the Protocol stub. *Verifies:* round-trip ingest →
   query on DuckDB; large-data ingest does not block the loop (EDGE-26 style); cancel mid-ingest
   invalidates.
3. **`fetch_df` / `fetch_polars`.** Two single-offload methods returning self-owning frames; Protocol
   stubs; skip-if-not-installed test guards. *Verifies:* self-owning-after-checkin (EDGE-21 category);
   `ImportError` surfaces unchanged when pandas/polars absent.
4. **P2 edge-case suite.** EDGE-08 (trio checkpoint delivery), EDGE-13/14 (contextvars), EDGE-20 (cleanup
   error chaining), EDGE-22/23 (`__del__` / no stray coroutine), EDGE-24 (loop shutdown), EDGE-31/32
   (timeout precision). Land `__del__` finalizers here (or in step 1 if EDGE-22 blocks). Most reuse the
   existing `BlockingStubCursor` harness; add stub methods for `fetch_record_batch`/`read_next_batch`,
   `adbc_ingest`, `fetch_df`/`fetch_polars`. *Verifies:* the whole surface under both backends.
5. **Docs (Phase ≥7 gate per CLAUDE.md).** Streaming + ingest + DataFrame guide sections; API-reference
   docstrings (Google-style, Args/Returns/Raises + `Example:`); honest materialization-bound caveat for
   `fetch_df`/`fetch_polars`; `.venv/bin/mkdocs build --strict`; humanizer pass.

**Ordering rationale:** the reader-lifetime design is the only genuinely novel risk and everything else is
a straightforward reuse of the existing chokepoint, so it goes first. `adbc_ingest` before the DataFrame
methods because it exercises the write path and the keyword-arg-arity concern in isolation. The P2 edge
suite last-but-one because it needs all four methods present to exercise them; `__del__` finalizers can
move earlier if EDGE-22/23 are gating. Docs last per the standing quality gate.

---

## Scaling Considerations

| Scale | Adjustments |
|-------|-------------|
| Streaming a large result | Per-batch offload keeps memory bounded (one batch resident at a time on the consumer side) and the loop responsive; token held only per pull. |
| Many concurrent streams | Each active pull borrows one transient token; bounded by `pool_size + max_overflow` (unchanged limiter). A held-but-idle reader (between pulls) holds NO token — consistent with the transient-token model. |
| Concurrent large `fetch_df`/`fetch_polars` | Materialization-bound (GIL, SPIKE-02); throughput does not scale with concurrency. Prefer `fetch_record_batch` streaming or `fetch_arrow_table` if conversion is the bottleneck. |
| Bulk `adbc_ingest` | Write side releases the GIL → real parallelism across connections; bind is a pointer hand-off, so large in-memory data does not add Python-side CPU cost. |

---

## Sources

- Installed `adbc_driver_manager` **1.11.0** dbapi source, read directly via `inspect.getsource`:
  `Cursor.fetch_record_batch` (returns `self._results.reader._reader`, a live `pyarrow.RecordBatchReader`),
  `_RowIterator` (holds `_stmt`; `read_next_batch`/`read_all`/`read_pandas`/`fetch_polars` each via
  `_blocking_call(..., self._stmt.cancel)`), `Cursor.close`/`_clear` (closes `_results` → reader + stmt),
  `adbc_ingest` (bind/bind_stream pointer hand-off + `_blocking_call(stmt.execute_update, ..., stmt.cancel)`),
  `fetch_df`/`fetch_polars` (self-owning frames) — **HIGH**
- Live DuckDB probe (`adbc_driver_duckdb.dbapi`, pyarrow 24.0.0): read-after-`cursor.close()` on a
  `fetch_record_batch` reader raises `ArrowInvalid: Attempt to read from a stream that has already been
  closed`; drain-then-close yields correct data surviving `conn.close()` — **HIGH (empirical)**
- adbc-poolhouse source read directly: `_async/_offload.py` (single chokepoint, `to_thread.run_sync`,
  transient token, `on_dispatch`), `_async/_cancel.py` (`cancellable_offload` watcher/worker task group,
  `on_abort`, `aborted_by_us`, `_mark_started` loop-thread bridge), `_async/_cursor.py` (`_SyncCursor`
  Protocol, `_offloading` guard, `fetch_arrow_table` reference wrapper), `_async/_connection.py`
  (`_in_use`, shielded check-in, `invalidate`, `_teardown_limiter`), `_pool_factory._release_arrow_allocators`
  (reset event closes all cursors on checkin) — **HIGH**
- anyio *Working with threads*: `to_thread.run_sync` copies the current context into the worker, worker
  mutations do not propagate back; default shielded-from-cancellation (drives EDGE-13/14, cancel design) —
  https://anyio.readthedocs.io/en/stable/threads.html — **HIGH**
- v1.4.0 research SPIKE-02 finding (materialization re-acquires GIL; concurrent large conversions
  serialize) — `.planning/milestones/v1.4.0-research/SUMMARY.md` — **HIGH**
- v1.4.0 architecture + REQUIREMENTS (offload model, transient-token limiter, cancellation flow, EDGE-21
  result-valid-after-checkin) — `.planning/milestones/v1.4.0-research/ARCHITECTURE.md`,
  `.planning/milestones/v1.4.0-REQUIREMENTS.md` — **HIGH**
- P2 edge-case designs (EDGE-08/13/14/20/22/23/24/31/32) — `.planning/research/ASYNC-EDGE-CASES.md` — **HIGH**

---
*Architecture research for: v1.5.0 async cursor completion over the v1.4.0 anyio thread-offload layer (adbc-poolhouse)*
*Researched: 2026-07-01*
