# Pitfalls Research

**Domain:** Adding four deferred async cursor methods (`fetch_record_batch` Arrow streaming, `adbc_ingest` bulk write, `fetch_df` / `fetch_polars` DataFrame convenience) plus the P2 async edge-case hardening suite to the existing v1.4.0 anyio thread-offload async layer over sync ADBC + SQLAlchemy `QueuePool` (adbc-poolhouse v1.5.0)
**Researched:** 2026-07-01
**Confidence:** HIGH on ADBC dbapi semantics (verified against the official `adbc_driver_manager` reference and the upstream `dbapi.py` source read directly — see Sources), HIGH on the v1.4.0 offload/cancel/limiter machinery (read from source: `_offload.py`, `_cancel.py`, `_cursor.py`, `_connection.py`, `guard.py`), HIGH on anyio semantics (carried from the v1.4.0 ASYNC-EDGE-CASES verification). MEDIUM on per-backend `adbc_ingest` transactional recovery (driver-dependent, empirically bounded, not spec-guaranteed).

> This document **extends** the v1.4.0 `PITFALLS.md` (the five headline risks — cancellation-leak, 40-token limiter, GIL/materialization, Arrow allocator leak, asyncio-only idioms). It does **not** restate them. It is scoped to what changes when the four new methods and the P2 edge tests are added to an *already-shipped* offload wrapper: the streaming-reader-lifetime cluster (the #1 new risk), ingest, DataFrame convenience, each P2 edge failure mode, and integration with the v1.4.0 chokepoint / limiter / cancel / lazy-import / guard machinery.

## The Load-Bearing New Fact (read first)

Read directly from upstream `adbc_driver_manager/dbapi.py` (Sources):

- **`fetch_record_batch()` returns `self._results.reader._reader` — a `pyarrow.RecordBatchReader` bound to the live ADBC statement handle**, not a self-owning buffer. Its docstring: *"This can only be called once. It must be called before any other method that consume data."* Unlike `fetch_arrow_table()` (which fully materializes a self-owning `pyarrow.Table`, safe after checkin — EDGE-21), a reader is a **cursor to C-side result state**. Every unread batch is native memory whose lifetime is the statement's. This single fact is the root of the entire streaming-reader pitfall cluster below and is the reason v1.4.0 deliberately shipped `fetch_arrow_table` and deferred `fetch_record_batch`.

Two corollaries that shape the design:

- **The v1.4.0 offload model is transient-token, one-offload-per-call.** `offload()` borrows a limiter token for the duration of one call and releases it (`_offload.py` docstring: "A token is borrowed only for the duration of this one call … so a connection holds no token between calls"). A streaming reader consumed batch-by-batch across many awaits does **not** fit that model without care — each `next(reader)` is a separate blocking C pull that must be its own offload.
- **ADBC's own `fetch_df`/`fetch_polars`/`fetch_record_batch` internally call `_blocking_call(..., self._stmt.cancel)`** — they already wire the driver's cancel. When we offload them we bypass that inner loop (it needs a running asyncio loop it will not have on a worker thread), so **our** `cancellable_offload` + `adbc_cancel` is what provides cancellation, exactly as for `execute`/`fetch_arrow_table`.

---

## Critical Pitfalls

### Pitfall 1: Streaming reader read after checkin — use-after-free of C-side result state (THE headline risk)

**What goes wrong:**
A consumer does `reader = await cursor.fetch_record_batch()` inside `async with await pool.connect() as conn:`, the block exits (connection checks in → the `reset` event `_release_arrow_allocators` closes the cursor and its statement), and *then* the consumer iterates `async for batch in reader`. The reader points at a statement handle that no longer exists. Best case: an ADBC error. Worst case: a read of freed native memory → segfault or corrupted Arrow buffers. This is the streaming analogue of the use-after-checkin that EDGE-21 proves is *safe* for the materialized `Table` — but for a reader it is **unsafe**, because the reader is not self-owning.

**Why it happens:**
v1.4.0 taught users (and the codebase, via the `AsyncCursor` module docstring) that "fetch results survive checkin." That is only true for `fetch_arrow_table`'s materialized `Table`. Developers pattern-match the streaming method to the same lifetime rule. The offload boundary makes it worse: the `await` invites the consumer to "grab the reader and deal with it later," across arbitrary suspension points including the `async with` exit.

**How to avoid:**
- **Do not hand a bare `pyarrow.RecordBatchReader` back across the await boundary.** Wrap it in an `AsyncRecordBatchReader` that (a) owns a reference to the `AsyncCursor`/`AsyncConnection` so the connection cannot be checked in while the reader is live, and (b) exposes `__aiter__`/`__anext__` where each `__anext__` offloads a single `reader.read_next_batch()` (or `next(reader)`) through the pool limiter with `cancellable_offload`.
- **Tie the reader's lifetime to an explicit async context manager**: `async with await cursor.fetch_record_batch() as reader: async for batch in reader:`. The reader's `__aexit__` drains/closes the reader (offloaded, shielded) *before* the connection is allowed to check in. Document that the connection stays checked out for the stream's lifetime (see Pitfall 3 — that is a real cost, not a bug).
- **Guard against checkin-while-live:** the `AsyncConnection.close`/`__aexit__` path must not silently strand an open reader. Either the reader holds the `_in_use` guard for its lifetime (rejecting a concurrent `close` with `ConnectionBusyError`), or checkin closes any straggler reader first (routing through the existing reset symmetry).
- **Never store the raw reader on a plain attribute a user can reach.** The only sanctioned exit is the wrapped async iterator.

**Warning signs:**
Segfaults / `ADBC_STATUS_INTERNAL` / "statement is closed" errors that appear only when the stream is consumed *after* the `async with` block; tests that "pass" because they consume the reader fully inside the block (the dangerous path — post-checkin consumption — is never exercised); DuckDB tolerates it, a networked backend crashes ("works on DuckDB, segfaults on Snowflake").

**Phase to address:**
Dedicated **Arrow-streaming phase** (the first new-method phase; it is the highest-risk item and its lifetime design gates the other three methods' patterns). Ship the `AsyncRecordBatchReader` wrapper + lifetime CM from day one. Verify with a DuckDB test that consumes the reader *after* the connection has checked in and asserts a clear, typed error (not a segfault) — plus a happy-path test that consumes fully inside the CM.

---

### Pitfall 2: Streaming reader not drained/closed before the `_release_arrow_allocators` reset fires → native Arrow allocator leak

**What goes wrong:**
A reader is partially consumed (or never consumed) and abandoned. The unread batches are native Arrow memory pinned by the open statement. If the cursor is closed and the connection reset *without* the reader being drained/closed, the sync `_release_arrow_allocators` reset listener closes the cursor — but a reader still referenced elsewhere (or GC'd late) can leave allocators alive, and repeated across many short-lived streams this grows RSS invisibly to the Python GC. This is v1.4.0 Pitfall 5 (Arrow leak), sharpened: `fetch_arrow_table` fully drains in one offload, so there is nothing to leak; a *reader* is leak-prone by construction.

**Why it happens:**
Streaming's whole point is *not* draining eagerly, so "partially consumed then abandoned" is the normal, expected shape (a `LIMIT`-style early break, an exception mid-loop). `__del__` can't reliably run the offloaded close (no loop, or loop gone — see EDGE-22). The reset listener only fires on connection checkin, which the reader deliberately delays.

**How to avoid:**
- The `AsyncRecordBatchReader.__aexit__` must **close the underlying reader** (offloaded, shielded, `CancelScope(shield=True)`, mirroring `AsyncCursor.close`) whether or not iteration finished — draining is not required, but *closing* is, so the C-side allocators are released promptly, not at some later reset.
- On the **exception/partial-iteration path**, `__aexit__` still closes the reader (the `async with` guarantees it); the body exception propagates, the close error (if any) is chained via `__context__`, never masks it (ties to EDGE-20).
- Keep the existing reset symmetry as the **safety net, not the primary path**: the connection checkin still fires `_release_arrow_allocators`, but the reader CM should have already closed things — the reset must never be the *only* thing that frees a stream.
- Add a `ResourceWarning` on `__del__` of an un-closed `AsyncRecordBatchReader` (EDGE-22 pattern) so a forgotten stream is surfaced in tests, not silently leaked.

**Warning signs:**
RSS climbing under sustained streaming load while the Python heap stays flat; `pyarrow` allocator stats growing across many `fetch_record_batch` lifecycles; leaks that vanish only on `pool.dispose()`; the memory-stability test (TEST-03 analogue) passing for `fetch_arrow_table` but not for the streaming path.

**Phase to address:**
Arrow-streaming phase (reader CM + close-in-`__aexit__`). Verify in the Testing phase with a streaming memory-stability loop (extend TEST-03) that partially-consumes-then-abandons the reader ×N and asserts allocator stats stabilize.

---

### Pitfall 3: The stream holds a pool connection (and its offload budget) for the entire iteration → limiter starvation / backpressure

**What goes wrong:**
Unlike `fetch_arrow_table` (one offload, token borrowed then released, connection idle-able), a streaming read **pins the connection for the whole consume duration** — the connection cannot check in until the reader is closed. If a consumer opens N long-lived streams on a pool sized to `pool_size + max_overflow == N`, all N connections are held; the N+1th `await pool.connect()` blocks (offloaded, but the checkout itself borrows a token and waits). Worse: because each `__anext__` batch-pull is its own offload borrowing a token, a task that holds a connection *and* is mid-stream is doing exactly the "hold a connection while awaiting another offload" pattern EDGE-11 exists to keep safe — a real hold-and-wait risk if the reader's per-batch offload contends for a token the held connection's own budget doesn't cover.

**Why it happens:**
`fetch_arrow_table` trained the mental model "an offload is a brief blip." Streaming inverts it: the "offload" is spread across the entire result set with the connection pinned throughout. Developers size pools for point queries and are surprised when a handful of slow streams exhausts the pool.

**How to avoid:**
- **Document the cost explicitly:** a `fetch_record_batch` stream holds its connection from `fetch_record_batch()` until the reader is closed. Streams are for backpressured consumption; they are not free the way a materialized fetch is. Advise consumers to size the pool for *concurrent open streams*, not just concurrent point queries.
- **Reuse the transient-token model per batch** — each `__anext__` offloads one `read_next_batch` through the pool limiter and releases the token between batches (the connection is held, but the *token* is not held between batches), so the reader does not permanently consume a limiter token, only the batch-pull does. This keeps the reader compatible with EDGE-11's "connection you hold already owns a token via its checkout" invariant — verify no second permanent token is needed.
- **Do not offload the whole `for batch in reader` loop as one mega-offload** — that would (a) defeat backpressure (the whole stream drains in one worker call), (b) make mid-stream cancellation impossible, and (c) is the "one mega-offload" tech-debt shortcut the v1.4.0 pitfalls already ban.

**Warning signs:**
`QueuePool limit … timed out` under a workload with several concurrent streams; pool `checkedout()` staying high for the stream's whole duration; a watchdog `fail_after` around a second checkout tripping while streams are open; throughput that collapses when point queries and streams share a pool.

**Phase to address:**
Arrow-streaming phase (per-batch transient-token design + the hold-and-wait check). Verify by extending EDGE-11 to the streaming path: hold a connection mid-stream, attempt another offload, assert no watchdog-tripping deadlock. Document in the async guide (Docs phase).

---

### Pitfall 4: Cancellation mid-stream leaves the C statement live — `adbc_cancel` + invalidate must still fire per batch

**What goes wrong:**
A `fail_after`/`move_on_after`/`scope.cancel` lands while a batch-pull (`read_next_batch`) is blocked in the driver. If the per-batch offload is a bare `offload()` (no `adbc_cancel` wiring), the worker is shielded by default (`abandon_on_cancel=False`) and the await hangs until the batch arrives — cancellation is a no-op, the classic v1.4.0 Pitfall 1. If instead the code abandons the worker, the statement keeps streaming on the warehouse and the connection is poisoned. Either way the connection must be **invalidated**, not returned busy, and the partially-consumed reader must be treated as dead.

**Why it happens:**
Streaming has *many* cancellation points (one per batch), not one. It is easy to wire `cancellable_offload` on the initial `fetch_record_batch()` call and forget that each subsequent `__anext__` is an equally-blocking C call needing the same treatment. The reader-close in `__aexit__` is also a cancellation point (must be shielded, like `AsyncCursor.close`).

**How to avoid:**
- **Route every batch-pull through `cancellable_offload`** with the cursor's `_adbc_cancel` hook and `on_abort=self._owner.invalidate` — identical to how `execute`/`fetch_arrow_table` already work in `_cursor.py`. A cancelled batch-pull fires `adbc_cancel` once (shielded), invalidates the connection, re-raises the cancellation.
- **A cancelled stream poisons the connection**: after mid-stream cancel, the connection is invalidated (`checkedout() == 0`), the reader is dead, and `__aexit__` must not try to re-close a reader on an already-invalidated connection (a `close` after `invalidate` is a probe-confirmed safe no-op per `_connection.py`, but the reader wrapper must not double-cancel).
- **Shield the reader-close in `__aexit__`** in `anyio.CancelScope(shield=True)`, mirroring `AsyncCursor.close`, so a cancellation arriving during stream teardown cannot abandon an open reader/statement.

**Warning signs:**
A timed-out stream whose warehouse query keeps running (visible in warehouse query logs); `checkedout()` not returning to 0 after a mid-stream cancel; a hang under trio when a batch-pull is cancelled (proves the per-batch `adbc_cancel` wiring is missing — the same load-bearing-hang signal as v1.4.0 EDGE-02); double `adbc_cancel` errors on drivers that reject it.

**Phase to address:**
Arrow-streaming phase (per-batch `cancellable_offload` + shielded reader-close). Verify with the `BlockingStubCursor` extended to a blocking `read_next_batch`: cancel mid-stream, assert `adbc_cancel` fired once, connection invalidated, `checkedout() == 0`, cancel propagates — under both backends.

---

### Pitfall 5: `adbc_ingest` offloaded as one blocking call — GIL-release and cancellation semantics differ from execute

**What goes wrong:**
`adbc_ingest(table, data, mode=...)` bulk-writes a `RecordBatch`/`Table`/`RecordBatchReader`/Arrow capsule. It is offloaded as one blocking call, which is correct *shape*, but two hazards: (a) the **GIL-release premise** verified for `execute` (network I/O `with nogil:`) is not automatically true for the *write path* — feeding a large in-memory `Table` to the driver may spend real time in Python/C-API Arrow traversal that re-acquires the GIL, so concurrent ingests may serialize on the GIL exactly like large-result materialization (v1.4.0 SPIKE-02 showed materialization partially serializes; ingest is the write-side mirror and was **not** spiked). (b) A large ingest is a *long* single offload — cancellation mid-ingest hits the same `adbc_cancel` path, but the *recovery* is backend-specific (Pitfall 6).

**Why it happens:**
"ADBC releases the GIL" gets over-generalized to every method including writes. The spike measured reads, not writes. And ingest *looks* like just another offloaded cursor call, so it is easy to wire it as a plain `offload()` and inherit neither the cancel wiring nor honest concurrency expectations.

**How to avoid:**
- **Route ingest through `cancellable_offload`** (with `_adbc_cancel` + `on_abort=invalidate`), not bare `offload()` — a long ingest must be interruptible, and a cancelled ingest poisons the connection.
- **Set honest concurrency expectations in docs:** do not claim concurrent ingests parallelize. Frame ingest wins as "off the event loop" (the loop stays responsive) rather than "N ingests run in parallel." If a cheap DuckDB micro-measurement is available, record write-side GIL behavior the way SPIKE-02 recorded read-side; otherwise disclaim explicitly.
- **Pass a `RecordBatchReader` as `data` only with reader-lifetime care** (Pitfall 7) — the reader is consumed inside the single offload, on the worker thread, so it must be fully owned by that call and not touched from the loop concurrently.

**Warning signs:**
Concurrent ingests showing no speedup and one core pinned during "parallel" writes; the event loop *staying* responsive (good — that is the real win) but throughput not scaling with concurrency; a cancelled large ingest whose rows keep landing.

**Phase to address:**
**Ingest phase** (after streaming establishes the reader-lifetime pattern). Wire `cancellable_offload`; document honest expectations (Docs phase). Optionally extend the spike micro-benchmark to the write path.

---

### Pitfall 6: `adbc_ingest` mode misuse and partial-apply cancellation — silent wrong-table and non-transactional recovery

**What goes wrong:**
Two distinct traps. (a) **Mode confusion**: the four modes have sharp, easily-swapped semantics (verified from source): `append` = error if table absent; `create` = error if table exists (the default!); `create_append` = create-if-absent then insert; `replace` = **drop existing table** then create. A consumer expecting "insert into my table" who leaves the default `create` gets an error if the table exists; one who reaches for `replace` to "make sure it's there" silently **drops and recreates**, losing data. The async wrapper must forward `mode` verbatim and its default must match the sync ADBC default (`create`) — a divergent default is a data-loss footgun. (b) **Partial-apply on cancel**: a cancelled ingest is invalidated by our machinery, but whether the *already-written rows* roll back is **backend-specific** — some backends stage-and-commit (clean rollback), others stream rows (partial data remains). Our `invalidate` cleans the *pool*, not the *table*.

**Why it happens:**
`mode` is a single keyword with severe consequences and a non-obvious default (`create`, not `append`). Developers assume async cancellation = transactional rollback (true for a native-async driver inside a transaction, not guaranteed for a mid-stream ADBC bulk write). The wrapper is a pure pass-through, so it is tempting to not document either hazard.

**How to avoid:**
- **Forward `mode` exactly and default to `create`** (the ADBC dbapi default), typed as `Literal['append', 'create', 'replace', 'create_append']` so basedpyright rejects a typo'd mode at call sites. Do not invent a "friendlier" default.
- **Document the mode table verbatim** in the ingest docstring/guide (especially `replace` = drop) — this is a UX-safety requirement, not optional prose.
- **Document that a cancelled ingest does NOT guarantee rollback** — the connection is invalidated and safe to discard, but the target table may hold partial data depending on the backend; consumers who need atomicity should wrap ingest in an explicit transaction (`commit`/`rollback`) on a backend that supports it, or ingest to a staging table.

**Warning signs:**
"Table already exists" errors from the default `create` mode surprising users who wanted append; a `replace` that silently emptied a table; partial rows in the target after a timed-out ingest; tests that only exercise ingest into a fresh table (never the mode-collision or cancel-partial paths).

**Phase to address:**
Ingest phase (typed `Literal` mode, verbatim forwarding, mode-table docs). Verify with tests for each mode's error/success semantics against DuckDB, plus a documented (possibly xfail-annotated) note on partial-apply. Docs phase for the mode-safety and non-atomicity callouts.

---

### Pitfall 7: `fetch_df` / `fetch_polars` surface a raw `ModuleNotFoundError` from deep inside ADBC/pyarrow instead of an actionable error

**What goes wrong:**
Verified from upstream source: `fetch_df` delegates to `reader.read_pandas()`, which raises a raw `ModuleNotFoundError`/`ImportError` from **inside pyarrow's internals** when pandas is absent; `fetch_polars` does `import polars` inside the method and raises a bare `ModuleNotFoundError` from that line. Offloaded, this error crosses the worker→loop boundary *unchanged* (that is exactly what the `offload` chokepoint guarantees for `AdbcError` — EDGE-17 — and it applies equally to `ModuleNotFoundError`). The consumer gets `ModuleNotFoundError: No module named 'polars'` with a traceback pointing into ADBC/pyarrow, not into poolhouse, with no hint that pandas/polars is a user-supplied runtime dep they must install.

**Why it happens:**
The methods are pure pass-throughs; the natural implementation just offloads `self._cursor.fetch_df` and lets the error propagate (which the chokepoint faithfully does). Nobody adds a pre-check because "it's just a wrapper." The result is a confusing error for exactly the users this convenience method targets.

**How to avoid:**
- **Pre-check the optional dependency before offloading** and raise a clear, actionable error naming the missing package — e.g. `find_spec("pandas") is None → raise ImportError("cursor.fetch_df() requires pandas; install it with `pip install pandas`")`. This mirrors how the library already treats drivers ("ADBC raises if absent") but upgrades the message from a raw deep import error to a one-line install instruction. Consistent with PKG-03's precedent (clear ImportError naming the missing piece).
- **Do the check on the loop thread before the offload** (a `find_spec` is cheap, non-blocking) so the error is raised synchronously with a poolhouse-attributable frame, not from a worker thread deep in pyarrow.
- **Do NOT catch-and-rewrap the offloaded error** as a fallback — that would risk clobbering a *genuine* runtime error from a partially-broken pandas install; the pre-check is the clean path, the chokepoint passes everything else through unchanged.
- **`fetch_df` returns pandas via pyarrow's `read_pandas`; `fetch_polars` does `polars.from_arrow`** — both ultimately materialize (see Pitfall 8), so the same GIL caveat applies.

**Warning signs:**
Users filing "No module named 'polars'" issues with tracebacks that never mention poolhouse; the convenience method being *less* friendly than raw ADBC; a test that only runs with pandas/polars installed (never asserts the clear-error path when absent).

**Phase to address:**
**DataFrame-convenience phase.** Ship the pre-check + actionable `ImportError` from the first commit. Verify with a test that runs with pandas/polars *uninstalled* (or `find_spec` monkeypatched to `None`) and asserts the poolhouse-attributable error message names the extra/package.

---

### Pitfall 8: `fetch_df` / `fetch_polars` materialization partially serializes on the GIL — do not claim parallelism

**What goes wrong:**
SPIKE-02 (v1.4.0) established that pyarrow `Table` materialization partially serializes on the GIL. `fetch_df` (pyarrow → pandas) and `fetch_polars` (Arrow → polars via `from_arrow`) are *more* materialization, not less — a full Arrow pull plus a DataFrame conversion, both Python/C-API heavy. Concurrent `fetch_df` calls will serialize on the GIL during conversion and show little speedup, even though the underlying network pull parallelizes. The honest concurrency story is identical to `fetch_arrow_table`'s materialization caveat, arguably sharper.

**Why it happens:**
DataFrame convenience *looks* like a fetch, and "async fetch = parallel fetch" is the over-generalized premise the v1.4.0 docs already had to walk back for `fetch_arrow_table`.

**How to avoid:**
- **Reuse the v1.4.0 honest-concurrency framing verbatim**: async wins are largest for latency/I/O-bound work; DataFrame materialization is CPU/GIL-bound and partially serializes. Do not add a blanket "N concurrent DataFrames run in parallel" claim.
- **Frame the win as loop-liveness**: `await cursor.fetch_df()` keeps the event loop responsive while a big DataFrame is built off-loop — that is the real, honest benefit, distinct from throughput parallelism.

**Warning signs:**
Benchmarks showing concurrent `fetch_df` no faster than serial; one core pinned during "concurrent" DataFrame builds; docs implying speedup that users don't observe.

**Phase to address:**
DataFrame-convenience phase (code is a thin wrapper; the deliverable is honest docs). Docs phase reflects the caveat, reusing the SPIKE-02 language.

---

### Pitfall 9: pandas/polars accidentally enter poolhouse's runtime deps or import graph

**What goes wrong:**
Adding `fetch_df`/`fetch_polars` tempts a top-level `import pandas`/`import polars` (for a type annotation, an `isinstance` check, or a helper), or a new `[dataframe]` extra, or listing them in `[async]`/`[all]`. Any of these makes users who never touch DataFrames pay for pandas/polars — a heavy, transitive-dep-laden import — and breaks the "zero-cost for non-users" invariant the library holds for drivers. Even a `TYPE_CHECKING`-only import is fine; a *runtime* top-level import is the trap.

**Why it happens:**
Type annotations want `-> pandas.DataFrame`; the natural reflex is a top-level import. The PEP 562 lazy-import machinery protects `import adbc_poolhouse` from pulling `anyio`, but does not automatically protect the `_async` submodule from pulling pandas once someone adds an import there.

**How to avoid:**
- **Import pandas/polars ONLY under `TYPE_CHECKING`** for annotations (`if TYPE_CHECKING: import pandas`), returning `"pandas.DataFrame"` as a string forward-ref — exactly the pattern `_cursor.py` already uses for `pyarrow`.
- **Never add pandas/polars to any extra.** They stay user-supplied runtime deps (charter: "pandas/polars stay user-supplied … consistent with how the library treats drivers"). `[async]` remains anyio-only (PKG-01).
- **Add a guard-style test** asserting `import adbc_poolhouse` and even `import adbc_poolhouse._async` succeed with pandas AND polars uninstalled — the analogue of PKG-04's "sync suite passes with anyio absent." This is the zero-cost proof.
- The optional-dep pre-check (Pitfall 7) uses `importlib.util.find_spec`, which does **not** import the module — so it is safe on the zero-cost path.

**Warning signs:**
`import adbc_poolhouse` (or the async submodule) failing or slowing when pandas/polars is absent; pandas appearing in the dependency tree of a consumer who only uses `execute`; basedpyright resolving `pandas.DataFrame` via a runtime import rather than a `TYPE_CHECKING` block.

**Phase to address:**
DataFrame-convenience phase (TYPE_CHECKING-only imports, no new extra). Verify with a no-pandas/no-polars import test in the Testing phase (extend the PKG-04 pattern).

---

## P2 Edge-Case Failure Modes (each test pins one; from ASYNC-EDGE-CASES.md)

Each row: the mistake the test guards against, the warning sign, the prevention, and the owning phase. These are the deferred P2 items (EDGE-08, 13/14, 20, 22/23, 24, 31/32) plus the new streaming/ingest edge coverage. They cluster into an **Edge-hardening phase** unless noted, but several are cheapest to write *alongside* the method that motivates them.

### EDGE-08 — trio checkpoint delivery at the offload boundary (no intervening checkpoint)

- **Mistake:** Assuming a cancel set with no `await` between it and `await cursor.execute(...)` is delivered promptly under trio the way it is under asyncio. Trio delivers cancellation only at a checkpoint; if the wrapper did pure-sync work with no checkpoint, delivery would differ across backends.
- **Warning sign:** A cancel-before-offload test passing on asyncio but the trio leg behaving differently (driver touched, or cancel not delivered at entry).
- **Prevention:** The offload's limiter-acquire (`async with limiter`) is a checkpoint on both backends — verified in `_offload.py`. The test sets `scope.cancel()` then immediately `await execute(...)` with no intervening await and asserts on *both* backends the driver's `execute_call_count == 0` and the cancel class propagates. This proves anyio normalizes delivery; trio is the discriminating leg.
- **Owning phase:** Edge-hardening phase (backend-parity guard; no production change expected, but it locks the invariant against future refactors of the offload entry).

### EDGE-13 / EDGE-14 — contextvars copied into the worker; worker mutations do not leak back

- **Mistake:** Building a bespoke thread (or reaching for `asyncio.to_thread`/`run_in_executor`) that drops the caller's `ContextVar` context, or a refactor that shares context so a worker's `cv.set(...)` bleeds back into the caller — cross-request contamination for consumers (dbt-open-sl, Semantic ORM) that set trace/request vars.
- **Warning sign:** Structured logging in the driver layer losing trace correlation across the offload (EDGE-13); a caller's context var mysteriously changing after an `await` (EDGE-14).
- **Prevention:** Keep using `anyio.to_thread.run_sync` (via the single `offload` chokepoint) — anyio copies the current context into the worker and does not propagate worker mutations back. EDGE-13 sets `cv` before an offload whose `fn` reads it and asserts the worker observed it; EDGE-14 has the worker `cv.set("inner")` and asserts the caller still reads `"outer"` after the await. The new methods route through the *same* `offload`, so they inherit this for free — the tests lock it in against a future non-anyio offload.
- **Owning phase:** Edge-hardening phase (contextvar parity; cheap, backend-parametrized, no production change).

### EDGE-20 — cleanup exception must not mask the body error (chain via `__context__`)

- **Mistake:** In `__aexit__` (connection checkin, cursor close, or the new **reader `__aexit__`**), if the offloaded `close`/`invalidate` itself raises while the body already raised, letting the cleanup error *replace* the body error (hiding the root cause), or bailing on the cleanup error and *leaking* the connection/reader.
- **Warning sign:** A `ValueError` from user code surfacing as an unrelated `AdbcError` from close; `checkedout()` not returning to 0 when both the body and cleanup raised.
- **Prevention:** `__aexit__` closes/invalidates unconditionally (shielded) and lets the original body exception propagate with the cleanup error chained via `__context__` — never masking. `_cancel.py` already models the "surface the actionable error, don't mask" discipline (the `abort_error` handling). The **new reader `__aexit__` must follow the same rule** (this is Pitfall 2's exception path). Test: body raises `ValueError`, stub `close` raises `AdbcError`; assert `ValueError` escapes, close-error is in `__context__`, `checkedout() == 0`.
- **Owning phase:** Owned by whichever `__aexit__` is newest — the **Arrow-streaming phase** for the reader CM (write the EDGE-20 test *with* the reader), plus the Edge-hardening phase for the existing connection/cursor `__aexit__`.

### EDGE-22 / EDGE-23 — `__del__` warns, never "coroutine never awaited"; happy path emits no `RuntimeWarning`

- **Mistake:** Giving the new `AsyncRecordBatchReader` (or any new wrapper) a `__del__` that tries to `await`/offload its close — impossible in `__del__` (no running loop, or loop gone), producing "coroutine was never awaited" / "no running event loop" noise, or crashing at interpreter shutdown. Or accidentally creating an un-awaited coroutine internally (e.g. a coroutine method called without `await` from a sync path).
- **Warning sign:** `RuntimeWarning: coroutine '...' was never awaited` in logs from library code; exceptions escaping `__del__`; noise at interpreter shutdown for an un-closed reader.
- **Prevention:** `__del__` must **only emit a `ResourceWarning`** (a clear leak signal) and rely on the pool reset to reclaim Arrow memory — never schedule an offload. The new reader wrapper especially needs this since a forgotten stream is the common leak (Pitfall 2). EDGE-23: run the full happy-path streaming/ingest/DataFrame lifecycle under `warnings.simplefilter("error", RuntimeWarning)` and assert no "coroutine never awaited" from library code (guards against a coroutine method accidentally called without `await`).
- **Owning phase:** Arrow-streaming phase for the reader's `__del__` (it introduces the new un-closeable-in-`__del__` object); Edge-hardening phase for the happy-path `RuntimeWarning` sweep across all four new methods.

### EDGE-24 — open pool / pending offload at loop shutdown raises no library-attributable noise

- **Mistake:** A pending batch-pull or ingest offload (or an open stream holding a connection) at event-loop shutdown that tries to signal a dead loop (e.g. a `from_thread` bridge — note `cancellable_offload` uses `from_thread.run_sync` for the `on_dispatch` flag), raising "Task was destroyed but it is pending" / "no running event loop" attributable to poolhouse.
- **Warning sign:** Stray `RuntimeError`/"Task was destroyed" at teardown when a stream or ingest was mid-flight; trio (stricter nursery semantics) surfacing it as the canary.
- **Prevention:** The existing shutdown discipline (shielded checkin, non-abandoned workers) already covers `execute`/`fetch`; extend the EDGE-24 test to a **mid-stream** and **mid-ingest** shutdown — create the pool, start (don't complete) a blocked batch-pull/ingest, exit the test scope, assert no library-attributable exception. The `from_thread` bridge in `cancellable_offload` must tolerate a torn-down loop for the new long-running calls.
- **Owning phase:** Edge-hardening phase, but the *scenarios* must cover the new streaming/ingest paths — so co-schedule after both methods exist.

### EDGE-31 / EDGE-32 — `move_on_after(0)` boundary and deadline−ε over-cancellation

- **Mistake:** EDGE-31: treating an already-expired `move_on_after(0)` as a no-op that skips the `adbc_cancel`/cleanup (leaving a blocked batch-pull/ingest live). EDGE-32: an off-by-one in deadline handling that cancels an op completing at deadline−ε, needlessly invalidating a healthy connection and churning the pool.
- **Warning sign:** EDGE-31: a `move_on_after(0)` around a blocked stream that hangs or leaves `checkedout() != 0`. EDGE-32: fast streams/ingests spuriously invalidated under a timeout that they actually beat.
- **Prevention:** The `cancellable_offload` design already keys cleanup off *actual* cancellation delivery (the `worker_started` + watcher model), not off "inside a timeout scope" — so a sub-deadline completion sets no `aborted_by_us` and skips `adbc_cancel`/invalidate (EDGE-32), and an expired `move_on_after(0)` delivers at the first checkpoint and runs the full `adbc_cancel`+invalidate (EDGE-31). The **new per-batch offloads and the ingest offload inherit this** — the tests must assert it for the streaming/ingest paths, not just `execute`. Use the virtual clock / event gating (EDGE-30 discipline; no positive-duration sleeps).
- **Owning phase:** Edge-hardening phase, parametrized over the new methods (the machinery is unchanged; the coverage extends to streaming/ingest).

---

## Integration Pitfalls with v1.4.0 Machinery

### Pitfall 10: Breaking the AST import-lint guard (accidental `asyncio` import or bare `to_thread`)

- **What goes wrong:** A new-method implementation reaches for `asyncio` (e.g. `asyncio.to_thread` for the DataFrame conversion, or `asyncio.CancelledError` in a cancel handler), or calls `anyio.to_thread.run_sync` directly instead of routing through `offload()`, or uses `to_thread.run_sync(...)` without an explicit `limiter=`. `scan_async_package` (read from `guard.py`) flags `banned-asyncio-import`, `banned-asyncio-cancelled-error`, and `to_thread-without-limiter`, and the EDGE-25/28 meta-tests assert its findings list is empty.
- **Prevention:** All four new methods offload **only** through the single `offload` / `cancellable_offload` chokepoint in `_offload.py`/`_cancel.py` — never call `to_thread.run_sync` directly (the guard's matcher is name-based; the one sanctioned literal lives in `_offload.py`). Use `anyio.get_cancelled_exc_class()`, never `asyncio.CancelledError`. Keep the `anyio.to_thread.run_sync` attribute chain un-aliased. Run `scan_async_package("src/adbc_poolhouse/_async/")` and assert `== []` as part of each new-method phase's gate.
- **Warning sign:** The EDGE-25 meta-test failing with a `banned-asyncio-import` / `to_thread-without-limiter` finding pointing at a new-method file.
- **Owning phase:** Every new-method phase (guard runs continuously); the guard itself is unchanged.

### Pitfall 11: Bypassing the offload chokepoint / limiter for the new methods

- **What goes wrong:** A per-batch streaming pull, an ingest, or a DataFrame conversion that does not route through `offload()` (borrowing the pool token) — e.g. a bare `to_thread`, an inline sync call on the loop, or a fresh un-limited `CapacityLimiter` — escapes the `pool_size + max_overflow` bound (CORE-02) and either blocks the loop (CORE-01) or over-admits concurrency.
- **Prevention:** Every blocking call in the new methods goes through `offload`/`cancellable_offload` with the pool's `self._limiter` (the cursor already holds it). The streaming per-batch model borrows a transient token per `read_next_batch` and releases it between batches. Poison-recovery (`invalidate`) uses the dedicated 1-token teardown limiter (WR-03), not the pool limiter — so a cancelled stream/ingest recovery does not deadlock behind the worker it just aborted; the new reader wrapper must reuse `AsyncConnection.invalidate`, not roll its own.
- **Warning sign:** EDGE-12 (strict-bound) failing when streams/ingests run; the thread-identity check (EDGE-25) showing a new-method call on the loop thread; a fresh limiter appearing in a new-method file.
- **Owning phase:** Arrow-streaming and Ingest phases (get the offload routing right at construction); verified by extending EDGE-12/25 to the new methods.

### Pitfall 12: Breaking the PEP 562 lazy-import zero-cost sync path

- **What goes wrong:** A new import in the `_async` graph that pulls a heavy or optional dep eagerly (pandas/polars — Pitfall 9; or a top-level `pyarrow` where a `TYPE_CHECKING` ref suffices) so `import adbc_poolhouse` regresses from zero-cost, or the lazy `__getattr__`/`_LAZY_ASYNC_NAMES` set drifts if the new methods add public entry points at the package top level.
- **Prevention:** The new methods are *cursor methods*, not new top-level entry points — they need **no** change to `__init__.py`'s `_LAZY_ASYNC_NAMES` or `__getattr__`. Keep pyarrow/pandas/polars imports `TYPE_CHECKING`-only. Preserve PKG-02/04: `import adbc_poolhouse` succeeds with anyio absent; the sync suite passes with anyio (and now pandas/polars) uninstalled.
- **Warning sign:** The PKG-04 sync-without-anyio CI job failing; `import adbc_poolhouse` importing pandas; a new name leaking into the eager `__all__`.
- **Owning phase:** DataFrame-convenience phase (highest risk — the DataFrame types tempt eager imports); guarded by the existing no-anyio import test extended to no-pandas/no-polars.

### Pitfall 13: basedpyright-strict regressions from `RecordBatchReader` / DataFrame typing

- **What goes wrong:** Typing the new surface loosely — `fetch_record_batch(self) -> Any`, an un-parameterized reader, `fetch_df() -> "pandas.DataFrame"` with pandas imported at runtime, or the `adbc_ingest` `data` param as `object` — trips basedpyright strict (`reportAny`, `reportUnknownMemberType`) or gives a worse API than the sync side. The `_SyncCursor` Protocol in `_cursor.py` must gain the four new method signatures (structurally typed, driver-agnostic).
- **Prevention:** Extend the `_SyncCursor` Protocol with `fetch_record_batch() -> pyarrow.RecordBatchReader`, `fetch_df() -> pandas.DataFrame`, `fetch_polars() -> polars.DataFrame`, and `adbc_ingest(table_name, data, mode, ...) -> int`, all under `TYPE_CHECKING` string annotations. Type `mode` as the exact `Literal['append','create','replace','create_append']`. Type the `data` param as the ADBC union (`RecordBatch | Table | RecordBatchReader | <capsule>`). Return precise types (the `AsyncRecordBatchReader` wrapper, `pandas.DataFrame`, `polars.DataFrame`, `int`). Run `basedpyright` strict on the new files from the first commit (project gate).
- **Warning sign:** `reportAny`/`reportUnknownMemberType` on the new methods; IDE showing `Any` for an awaited DataFrame; the `_SyncCursor` Protocol missing a new method (a `cast` papering over it). Note the MEMORY caveat: trust `.venv/bin/basedpyright` (0 errors) over harness Pyright's false import-resolution errors.
- **Owning phase:** Each new-method phase (typing is part of "done"); the Protocol extension lands with the first new method.

### Pitfall 14: mkdocs `--strict` autoref failures for new symbols

- **What goes wrong:** New public symbols (`AsyncRecordBatchReader`, the four methods) with cross-references (`[...][adbc_poolhouse._async...]`) that don't resolve, missing from the API-reference nav, or docstrings with RST `:role:` syntax (the MEMORY-documented rogue-colon trap) — `uv run mkdocs build --strict` fails, and per CLAUDE.md docs are a completion requirement for every phase ≥ 7.
- **Prevention:** Add each new public symbol to the mkdocstrings API reference; use Markdown (not RST) in docstrings; use `Example:` (singular) with fenced `python` blocks for the admonition (per MEMORY); verify every autoref resolves. Run `.venv/bin/mkdocs build --strict` (sandbox-safe per MEMORY) as a phase gate. Include the docs-author skill (`@.claude/skills/adbc-poolhouse-docs-author/SKILL.md`) in every phase ≥ 7 execution context.
- **Warning sign:** `mkdocs build --strict` reporting an unresolved autoref or a symbol missing from the reference; rogue colons in rendered docstrings from RST `:func:` syntax.
- **Owning phase:** Each new-method phase (docs are a per-phase completion gate); a consolidated Docs pass for the streaming guide + honest-concurrency updates.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Return the bare `RecordBatchReader` across the await boundary | No wrapper to write; "just offload `fetch_record_batch`" | Use-after-checkin segfaults (Pitfall 1), native leak (Pitfall 2), no per-batch cancel (Pitfall 4) | **Never** — the reader wrapper is the feature |
| Offload the whole `for batch in reader` loop as one mega-offload | Trivial; no per-batch plumbing | Defeats backpressure, un-cancellable mid-stream, holds the token for the whole drain | **Never** for the real API; only a throwaway spike |
| Let `fetch_df`/`fetch_polars` surface the raw deep `ModuleNotFoundError` | Zero code — pure pass-through | Confusing error for exactly the target users (Pitfall 7) | Only until the pre-check lands — treat as a same-phase must-fix |
| Top-level `import pandas`/`import polars` for the return annotation | `-> pandas.DataFrame` "just works" | Breaks zero-cost sync path; every user pays for pandas (Pitfall 9) | **Never** — use `TYPE_CHECKING` string refs |
| Default `adbc_ingest` mode to `append` "because it's friendlier" | Fewer "table exists" errors | Diverges from ADBC default (`create`); silent behavior mismatch vs raw ADBC | **Never** — mirror the sync/ADBC default exactly |
| Skip per-batch `cancellable_offload`; wire cancel only on the initial `fetch_record_batch` | Less plumbing | A mid-stream timeout hangs or leaves the statement live (Pitfall 4) | **Never** on a connection-bearing streaming call |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| ADBC `fetch_record_batch` | Treating the returned reader like `fetch_arrow_table`'s self-owning `Table` | It is bound to the live statement handle (`self._results.reader._reader`); wrap it, tie lifetime to the connection, close in `__aexit__` |
| ADBC `_blocking_call(..., self._stmt.cancel)` inside `fetch_df`/`fetch_record_batch` | Assuming ADBC's own cancel loop works on the worker thread | It needs a running loop it won't have on the worker; **our** `cancellable_offload` + `adbc_cancel` is the cancellation path |
| ADBC `adbc_ingest` mode | Using `replace` to "ensure the table exists" | `replace` **drops** the table first; use `create_append` for create-if-absent-then-insert |
| pyarrow `read_pandas` (backing `fetch_df`) | Expecting a clear "install pandas" error | Raises a raw `ModuleNotFoundError` from pyarrow internals; pre-check with `find_spec` and raise an actionable error first |
| v1.4.0 `offload` chokepoint | Calling `anyio.to_thread.run_sync` directly for a new method | Route through `offload`/`cancellable_offload` so the `scan_async_package` guard still audits one site and the limiter is honored |
| v1.4.0 `AsyncConnection.invalidate` | Rolling a bespoke poison-recovery for a cancelled stream/ingest | Reuse `invalidate` (dedicated teardown limiter, WR-03) so recovery never deadlocks behind the aborted worker |
| SQLAlchemy `reset` event (`_release_arrow_allocators`) | Relying on it as the *only* thing that frees a reader | It is the safety net; the reader `__aexit__` must close the reader promptly and symmetrically |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Stream pins a connection for its whole lifetime | Pool exhausted with few concurrent streams; `checkedout()` stays high | Document the cost; size pool for concurrent open streams (Pitfall 3) | Several concurrent long-lived streams on a small pool |
| Concurrent `adbc_ingest` serializes on the GIL during Arrow traversal | "Parallel" ingests no faster; one core pinned | Frame the win as loop-liveness, not throughput; don't claim parallelism (Pitfall 5) | Write-heavy workloads with large in-memory tables |
| Concurrent `fetch_df`/`fetch_polars` serialize on GIL during DataFrame conversion | Concurrent DataFrame builds no faster than serial | Reuse the SPIKE-02 materialization caveat; document honestly (Pitfall 8) | Fetch-heavy DataFrame workloads |
| Per-batch offload overhead on a fine-grained stream | Streaming slower than a single `fetch_arrow_table` for small results | Note that `fetch_arrow_table` is better for results that fit in memory; streaming is for backpressure | Many tiny batches where thread-hop ≫ pull cost |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging `data` contents or `table_name` when surfacing an `adbc_ingest` error | Leaking ingested row data / schema into stack traces | Reuse the sync error-handling discipline; the chokepoint passes the error through un-augmented — do not add logging of the payload |
| Returning a poisoned connection after a cancelled ingest/stream | Next task inherits a connection with an aborted transaction / partial ingest | Invalidate-on-cancel (existing machinery); never return a connection whose worker hasn't joined |
| Partial-apply ingest leaving rows in a shared table after a timeout | Downstream reads see half-written data across tenants | Document non-atomicity (Pitfall 6); advise staging-table or explicit-transaction ingest for atomic needs |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Reader dangles after `async with` exit | Segfault / opaque "statement closed" on post-block consumption | Reader is its own `async with`; document that the stream holds the connection |
| Raw `ModuleNotFoundError` from `fetch_df`/`fetch_polars` | User can't tell pandas/polars is a user-supplied dep | Pre-check + actionable `ImportError` naming the package (Pitfall 7) |
| `adbc_ingest(mode='replace')` silently drops a table | Data loss | Document the mode table verbatim (esp. `replace` = drop); typed `Literal` |
| Docs imply concurrent ingests / DataFrames parallelize | Users expect throughput they won't get | Honest per-operation concurrency framing (Pitfalls 5, 8) |
| Cancellation of a stream/ingest appears clean but the warehouse op ran / partial rows remain | Surprise cost / partial data | Real `adbc_cancel` wiring per batch (Pitfall 4) + non-atomicity note (Pitfall 6) |

## "Looks Done But Isn't" Checklist

- [ ] **fetch_record_batch:** reader returned and iterable — but verify consuming it *after* the `async with` block raises a clear typed error, not a segfault (Pitfall 1).
- [ ] **fetch_record_batch:** happy stream drains — but verify a *partially-consumed-then-abandoned* reader releases Arrow allocators (memory-stability loop, Pitfall 2).
- [ ] **fetch_record_batch:** cancel works on the first pull — but verify a mid-stream (Nth batch) cancel fires `adbc_cancel` once, invalidates, `checkedout()==0`, under **both** backends (Pitfall 4).
- [ ] **fetch_record_batch:** stream works on one connection — but verify holding it mid-stream while awaiting another offload doesn't self-deadlock at the bound (EDGE-11 extension, Pitfall 3).
- [ ] **adbc_ingest:** ingests into a fresh table — but verify each `mode` (append/create/replace/create_append) does the documented thing, and `replace` really drops (Pitfall 6).
- [ ] **adbc_ingest:** default mode set — but verify it is `create` (the ADBC default), not a divergent "friendlier" default (Pitfall 6).
- [ ] **adbc_ingest:** cancellation invalidates the connection — but document that partial rows may remain (backend-specific; not transactional) (Pitfall 6).
- [ ] **fetch_df / fetch_polars:** works with pandas/polars installed — but verify the *absent* case raises a poolhouse-attributable `ImportError` naming the package, not a raw deep `ModuleNotFoundError` (Pitfall 7).
- [ ] **fetch_df / fetch_polars:** methods added — but verify `import adbc_poolhouse` (and `_async`) still succeed with pandas AND polars uninstalled (Pitfall 9).
- [ ] **All four:** offloaded — but verify each routes through `offload`/`cancellable_offload` with the pool limiter (thread-id check EDGE-25; strict-bound EDGE-12) (Pitfall 11).
- [ ] **All four:** typed — but verify `basedpyright` strict (via `.venv/bin/basedpyright`) passes and the `_SyncCursor` Protocol gained the new signatures (Pitfall 13).
- [ ] **All four:** documented — but verify `mkdocs build --strict` passes with the new autorefs and the honest-concurrency framing (Pitfall 14).
- [ ] **Guard:** new code merged — but verify `scan_async_package("src/adbc_poolhouse/_async/") == []` (no asyncio import, no bare to_thread) (Pitfall 10).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Reader use-after-checkin (1) | HIGH | Add the `AsyncRecordBatchReader` lifetime wrapper; tie to connection; add post-checkin-consumption test; reproduce segfault on a networked backend |
| Reader Arrow allocator leak (2) | MEDIUM | Close reader in `__aexit__`; add streaming memory-stability loop; `ResourceWarning` on `__del__` |
| Stream connection starvation (3) | MEDIUM | Document the hold cost; per-batch transient-token; extend EDGE-11 to streaming |
| Mid-stream cancel leaves statement live (4) | HIGH | Wire per-batch `cancellable_offload` + `adbc_cancel` + invalidate; shield reader-close; reproduce with a blocking `read_next_batch` stub |
| Ingest GIL / cancel framing (5) | LOW–MEDIUM | Route ingest through `cancellable_offload`; re-scope docs; optional write-side micro-benchmark |
| Ingest mode misuse / partial-apply (6) | MEDIUM | Typed `Literal` mode; verbatim default; document `replace`=drop and non-atomicity |
| Raw ModuleNotFoundError from DataFrame methods (7) | LOW | Add `find_spec` pre-check + actionable ImportError; test the absent path |
| DataFrame materialization framing (8) | LOW | Reuse SPIKE-02 caveat in docs |
| pandas/polars in import graph (9) | LOW | Move to `TYPE_CHECKING`; drop any new extra; add no-pandas/no-polars import test |
| Guard / chokepoint / lazy-import / typing / docs regressions (10–14) | LOW | Route through existing chokepoint; TYPE_CHECKING imports; run guard + basedpyright + mkdocs --strict as phase gates |

## Pitfall-to-Phase Mapping

Recommended phase order: **Arrow-streaming first** (highest risk; its reader-lifetime design informs the ingest/DataFrame patterns and introduces the new `__aexit__`/`__del__` edge surfaces), then **Ingest**, then **DataFrame-convenience**, then a consolidated **Edge-hardening** phase for the remaining P2 items, then **Docs** (honest-concurrency + streaming guide). Several P2 edge tests are cheapest to write *inside* the method phase that motivates them (noted below).

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Reader use-after-checkin | Arrow-streaming | Post-checkin consumption raises a clear typed error (DuckDB), not a segfault |
| 2. Reader Arrow leak | Arrow-streaming (verify: Testing) | Partial-consume-then-abandon ×N; allocator stats stabilize |
| 3. Stream connection starvation | Arrow-streaming | EDGE-11 extended to a held mid-stream connection; watchdog never trips |
| 4. Mid-stream cancel | Arrow-streaming | Blocking `read_next_batch` stub; Nth-batch cancel → one `adbc_cancel`, invalidate, `checkedout()==0`, both backends |
| EDGE-20 (reader `__aexit__` chain) | Arrow-streaming | Body `ValueError` + reader-close `AdbcError` → `ValueError` escapes, chained, `checkedout()==0` |
| EDGE-22/23 (reader `__del__`) | Arrow-streaming | Un-closed reader → `ResourceWarning`, no "coroutine never awaited", no crash |
| 5. Ingest GIL / cancel | Ingest | Ingest routed through `cancellable_offload`; honest docs; optional write micro-benchmark |
| 6. Ingest mode / partial-apply | Ingest | Per-mode semantics test (esp. `replace`=drop); documented non-atomicity |
| 7. DataFrame raw ImportError | DataFrame-convenience | Absent-pandas/polars path raises poolhouse-attributable ImportError |
| 8. DataFrame materialization framing | DataFrame-convenience (verify: Docs) | Docs reflect the GIL caveat |
| 9. pandas/polars in import graph | DataFrame-convenience | `import adbc_poolhouse`/`_async` succeed with pandas+polars absent |
| EDGE-08 (trio checkpoint delivery) | Edge-hardening | Cancel-before-offload; driver untouched on both backends |
| EDGE-13/14 (contextvars) | Edge-hardening | Worker sees caller's cv; worker mutation doesn't leak back |
| EDGE-24 (loop-shutdown noise) | Edge-hardening (scenarios cover streaming+ingest) | Mid-stream / mid-ingest teardown raises no library-attributable exception |
| EDGE-31/32 (deadline boundary) | Edge-hardening (extended to new methods) | `move_on_after(0)` cancels a blocked pull cleanly; deadline−ε not over-cancelled |
| 10. Import-lint guard | every new-method phase | `scan_async_package(_async/) == []` |
| 11. Bypassing chokepoint/limiter | Arrow-streaming + Ingest | EDGE-12/25 extended to new methods |
| 12. Lazy-import zero-cost path | DataFrame-convenience | PKG-04 job extended to no-pandas/no-polars |
| 13. basedpyright-strict typing | every new-method phase | `.venv/bin/basedpyright` strict = 0 errors; `_SyncCursor` Protocol extended |
| 14. mkdocs --strict autoref | every new-method phase + Docs | `mkdocs build --strict` passes |

## Sources

- [adbc_driver_manager (Python dbapi reference)](https://arrow.apache.org/adbc/main/python/api/adbc_driver_manager.html) — `fetch_record_batch() -> RecordBatchReader`, `fetch_df() -> pandas.DataFrame`, `adbc_ingest(table_name, data, mode=Literal['append','create','replace','create_append'], *, catalog_name, db_schema_name, temporary) -> int`; mode semantics (append=error-if-absent, create=error-if-exists, create_append=create-if-absent-then-insert, replace=drop-then-create); returns rows inserted or -1. (HIGH)
- Upstream `apache/arrow-adbc` `python/adbc_driver_manager/adbc_driver_manager/dbapi.py` read directly: `fetch_record_batch` returns `self._results.reader._reader` (bound to the statement, "can only be called once"); `fetch_df` delegates to `read_pandas` via `_blocking_call(..., self._stmt.cancel)` → raw `ModuleNotFoundError` from pyarrow if pandas absent; `fetch_polars` does an in-method `import polars` → raw `ModuleNotFoundError`; `adbc_ingest` maps `mode` to `_lib.INGEST_OPTION_MODE_*` and calls `set_options`. (HIGH)
- adbc-poolhouse source read directly: `_async/_offload.py` (single chokepoint, transient-token model, `on_dispatch` CR-01), `_async/_cancel.py` (`cancellable_offload`, watcher/worker task group, `worker_started`, `aborted_by_us`, `on_abort=invalidate`, shielded `adbc_cancel`), `_async/_cursor.py` (`_SyncCursor` Protocol, `fetch_arrow_table` materialized-Table pattern, shielded `close`), `_async/_connection.py` (`_in_use` guard, `invalidate` with dedicated teardown limiter WR-03, shielded checkin), `tests/_async_harness/guard.py` (`scan_async_package` rules: banned-asyncio-import, to_thread-without-limiter, banned-asyncio-cancelled-error), `__init__.py` (PEP 562 `__getattr__` / `_LAZY_ASYNC_NAMES`). (HIGH)
- `.planning/research/ASYNC-EDGE-CASES.md` — P2 edge designs (EDGE-08, 13/14, 20, 22/23, 24, 31/32) and the verified anyio/trio semantics they rest on. (HIGH)
- v1.4.0 `.planning/milestones/v1.4.0-research/PITFALLS.md` + `SUMMARY.md` — SPIKE-02 finding that pyarrow materialization partially serializes on the GIL (basis for the ingest/DataFrame honest-concurrency caveats); the five headline v1.4.0 risks this document extends. (HIGH)
- v1.4.0 `REQUIREMENTS.md` — shipped invariants the new methods must not break: EDGE-21 (result-valid-after-checkin, materialized only), ACONN-06 (reset symmetry), CORE-01/02/03 (offload discipline), PKG-01/02/04 (extra scoping + zero-cost sync path). (HIGH)
- Project `MEMORY.md` / `CLAUDE.md` — basedpyright via `.venv/bin/basedpyright` (harness Pyright false import errors), `mkdocs build --strict` via `.venv/bin/mkdocs`, Google-style Markdown docstrings (no RST roles), docs-author skill as a per-phase completion gate ≥ Phase 7. (HIGH)

---
*Pitfalls research for: v1.5.0 async cursor completion (fetch_record_batch, adbc_ingest, fetch_df, fetch_polars + P2 async edge-case tests) over the v1.4.0 anyio thread-offload async layer of adbc-poolhouse.*
*Researched: 2026-07-01*
