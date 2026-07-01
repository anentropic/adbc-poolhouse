# Async Edge-Case Test Coverage

**Domain:** Deterministic edge-case tests for the anyio thread-offload async layer (adbc-poolhouse v1.4.0)
**Researched:** 2026-06-26
**Confidence:** HIGH on anyio/trio semantics (verified against current anyio 4.x docs, see Sources); HIGH on the offload/cancel design (grounded in ARCHITECTURE.md + sync source read directly).

> This document **extends** `PITFALLS.md` — it does not repeat the five headline correctness risks
> (cancellation-leak, 40-token limiter, GIL/materialization, Arrow allocator leak, asyncio-only idioms).
> It goes broader and deeper on *general* Python-async edge cases that a **thread-offload wrapper**
> specifically must defend against, and gives each one a concrete, deterministic pytest test
> (arrange / trigger / assert), runnable under both asyncio and trio, marked P1 (must-have for v1.4.0)
> or P2 (hardening, can slip to v1.4.x).
>
> The downstream consumer turns each `### EDGE-CANDIDATE` into one atomic `EDGE-NN` requirement; the
> consolidated paste-ready table is at the end.

---

## Verified anyio/trio semantics this whole document rests on

Five facts (all re-verified against current anyio docs, June 2026) that change how several of these
tests must be written. Getting these wrong is itself a pitfall, so they are stated up front:

1. **`to_thread.run_sync` is *shielded from cancellation by default*.** "By default, tasks are shielded
   from cancellation while they are waiting for a worker thread to finish." So a naive
   `with fail_after(t): await offload(...)` **does not interrupt the worker** — the await only returns
   *after the worker finishes*, then the cancellation is delivered. Cancellation only reaches the
   awaiting task promptly if `abandon_on_cancel=True` — but then "the thread will still continue
   running – only its outcome will be ignored." This is exactly why the design wires `adbc_cancel`
   instead of relying on either default. **Implication for tests:** a cancellation test that does not
   wire `adbc_cancel` will *appear to pass* (await eventually returns) while proving nothing about
   interruption — tests must assert the worker was actually unblocked, not merely that the await returned.

2. **`cancellable=` is a deprecated alias of `abandon_on_cancel=`** (both accepted; `cancellable`
   overrides if both passed). The async package must use `abandon_on_cancel=` and must *not* leak the
   old name. (Feeds the import/API-surface test.)

3. **anyio normalises cancellation to *level* semantics inside cancel scopes — on both backends.**
   The question's framing ("trio edge-triggered vs asyncio level-triggered") is inverted: *raw asyncio*
   is **edge**-triggered (CancelledError raised once, can be swallowed); *anyio cancel scopes / task
   groups* are **level**-triggered on both backends (the cancellation exception is re-raised at *every*
   checkpoint while the scope is cancelled). The real divergence to test is (a) trio's strict
   *checkpoint requirement* — cancellation is only delivered at a yield point, and trio guarantees every
   `await` is a checkpoint; (b) raw asyncio's edge behaviour leaking in if the code ever touches
   `asyncio.CancelledError` directly. Use `anyio.get_cancelled_exc_class()` everywhere.

4. **`to_thread.run_sync` copies the *current context* into the worker thread**; "any context variables
   available on the task will also be available to the code running on the thread," and changes made in
   the worker **do not** propagate back. This makes the contextvars tests fully deterministic (no race).

5. **Cleanup that must `await` inside an already-cancelled scope is cancelled at the first checkpoint**
   unless wrapped in `CancelScope(shield=True)`: "If you need to use `await` during finalization, you
   need to enclose it in a shielded cancel scope, or the operation will be cancelled immediately." And
   **"Always reraise the cancellation exception if you catch it. Failing to do so may cause undefined
   behavior."** Both are directly testable invariants.

A practical consequence used throughout: **prefer a controllable blocking primitive over real sleeps.**
Two deterministic mechanisms are assumed available to the test suite:

- **`BlockingStubConnection` / `BlockingStubCursor`** — an in-process fake implementing the dbapi surface
  (`execute`, `fetch_arrow_table`, `close`, `adbc_cancel`, `_cursors`, `_closed`) whose `execute` blocks
  on a `threading.Event` until either the test sets it *or* `adbc_cancel()` sets it and flips an
  `observed_cancel` flag. This gives a query that blocks **forever until released**, so a timeout/cancel
  is guaranteed to land *during* the block — no wall-clock racing. It also records call ordering so
  serialization can be asserted.
- **A real in-proc DuckDB pool** for the happy-path / leak / memory tests where a real driver matters,
  plus the existing Snowflake `pytest-adbc-replay` cassette for the backend-generic leg.

Where a test must wait for "the worker has actually started blocking," it uses a second
`threading.Event` (`entered`) the stub sets on entry and the test `await`s via `from_thread`-free
polling on an anyio event — never `sleep`.

Unless stated otherwise, **every test below is parametrized over `["asyncio", "trio"]`** via
`@pytest.mark.anyio` (the `anyio_backend` fixture), because the whole point is backend neutrality.

---

## 1. Cancellation semantics (depth)

### EDGE-CANDIDATE: Cancel delivered *before* the offload starts must not touch the driver

**Description:** If the surrounding scope is already cancelled when `await cursor.execute(...)` is
reached, the offload must never dispatch the sync call to a worker (no `execute` on the driver at all),
and the connection must remain clean.

**Why it bites:** A checkpoint at the *start* of the offload (the limiter acquire is a checkpoint) can
raise the cancellation *before* `to_thread.run_sync` ever runs `fn`. A wrapper that calls `adbc_cancel`
unconditionally in its `except` handler would then cancel a query that never ran — and on some drivers
`adbc_cancel` on an idle statement errors. Conversely a wrapper that assumes "if cancelled, a query was
running" mis-invalidates a perfectly good connection.

**Deterministic test:** Arrange a `BlockingStubCursor`. Enter `with CancelScope() as scope: scope.cancel()`
*then* `await acur.execute(sql)`. Trigger: the pre-cancelled scope. Assert: `stub.execute_call_count == 0`
(driver never touched), `stub.adbc_cancel_call_count == 0`, the cancellation exception
(`anyio.get_cancelled_exc_class()`) propagates, and after exit `pool.checkedout() == 1` is *unchanged*
(the connection was never put mid-operation; it is still validly checked out and closeable). Both backends.

**Priority:** P1

### EDGE-CANDIDATE: Cancel delivered *during* the blocked worker invokes `adbc_cancel` exactly once and invalidates

**Description:** When cancellation lands while the worker is blocked inside `execute`, the wrapper must
call `adbc_cancel()` exactly once (from the loop thread, shielded), join the worker, invalidate the
connection, and re-raise.

**Why it bites:** This is the core cooperative-cancel path; `to_thread`'s default shielding means the
*only* way to unblock the worker is `adbc_cancel`. If the wrapper forgets it, the test hangs forever
(good — proves the wiring is load-bearing). If it calls it more than once, some drivers error.

**Deterministic test:** Arrange the `BlockingStubCursor` whose `execute` blocks on `event` and whose
`adbc_cancel` sets `event` + `observed_cancel=True`. Start `await acur.execute(sql)` inside
`with fail_after(...)`; wait (via an anyio event the stub sets on entry) until the worker is confirmed
blocked, then let the timeout fire (use a deterministic clock — see §9 — or trigger an explicit
`scope.cancel()` from a sibling task instead of a real timeout). Assert: `stub.observed_cancel is True`,
`stub.adbc_cancel_call_count == 1`, the connection's `_invalidate` was called, `pool.checkedout() == 0`
after the scope, and a cancellation exception (not a `TimeoutError`-wrapped-swallow) propagated. Both
backends. **This is the P1 anchor that CANCEL-01/02/03/04 ride on.**

**Priority:** P1

### EDGE-CANDIDATE: CancelledError is never swallowed by the offload/try-except

**Description:** No code path in the async layer may catch the framework cancellation class and *not*
re-raise it.

**Why it bites:** anyio docs: failing to reraise "may cause undefined behavior." A broad
`except Exception` in the offload helper (intended to map ADBC errors) will, on asyncio, swallow
`CancelledError` (it is `BaseException`, so a bare `except Exception` is safe — but a too-eager
`except BaseException` or `except (Exception, CancelledError)` is the trap), and under trio's level
model a swallowed cancel turns into a busy-loop or a hang.

**Deterministic test:** Static + behavioural. (a) Behavioural: wrap an offload whose `fn` raises the
backend cancel class (inject it) and assert it propagates unchanged out of `_offload`. (b) Cancel a real
blocked `execute` and assert the exact `anyio.get_cancelled_exc_class()` instance type is what escapes
(not a `RuntimeError`/`AdbcError` translation). Both backends — under trio, additionally assert the task
*actually finishes* (no hang) within a bounded `fail_after` watchdog.

**Priority:** P1

### EDGE-CANDIDATE: Double-cancel (cancel arrives again during the shielded cancel-cleanup) is idempotent

**Description:** While the shielded `adbc_cancel` + invalidate is running, the outer scope is still
cancelled (level semantics → re-raised at the next checkpoint). The cleanup must still complete exactly
once.

**Why it bites:** Under anyio level-cancellation, every checkpoint inside the (unshielded part of the)
handler re-raises. If the `adbc_cancel`/invalidate aren't fully inside `CancelScope(shield=True)`, the
second delivery interrupts cleanup → half-invalidated connection, possible double `adbc_cancel`.

**Deterministic test:** Cancel a blocked `execute`; have the stub's `adbc_cancel` itself hit a checkpoint
(call back via `from_thread` to a no-op) so a second cancellation *would* be delivered if unshielded.
Assert `adbc_cancel_call_count == 1`, invalidate ran once, `pool.checkedout() == 0`, exactly one
cancellation propagates. Both backends (this is where trio's strict re-delivery differs most from raw
asyncio).

**Priority:** P1

### EDGE-CANDIDATE: Cancel during `__aexit__` / checkin still returns or invalidates the connection

**Description:** Cancellation landing *inside* `AsyncConnection.__aexit__` (the offloaded checkin) must
not abandon the connection; checkin must complete under a shield.

**Why it bites:** "If you need to use `await` during finalization … enclose it in a shielded cancel
scope, or the operation will be cancelled immediately." The checkin is an offload (an `await`); if
unshielded and the scope is already cancelled, the connection never returns → permanent pool leak. This
is CANCEL-03 / ACONN-02 / ACUR-05.

**Deterministic test:** Arrange a happy connection. Inside `with CancelScope() as s:` open
`async with await pool.connect() as conn:` and `s.cancel()` right before the `async with` block exits
(or cancel from a sibling task scheduled to fire as the body completes). Assert the offloaded checkin
*still ran* (stub records `close`/reset fired) and `pool.checkedout() == 0` afterwards. Repeat for
`AsyncCursor.__aexit__`. Both backends.

**Priority:** P1

### EDGE-CANDIDATE: `fail_after` timeout vs explicit `scope.cancel()` are handled identically

**Description:** A timeout (`fail_after` raising `TimeoutError`) and an external `scope.cancel()` both
unblock the worker via `adbc_cancel` and invalidate — the only difference is the exception type that
ultimately escapes (`TimeoutError` vs the cancel class).

**Why it bites:** A wrapper that special-cases `TimeoutError` (or only catches the cancel class) will
leak on one of the two paths. `fail_after` internally cancels a scope then translates to `TimeoutError`
*only if its own `cancelled_caught`* — the wrapper sees the cancel class first, so its handler must key
off the cancel class, not `TimeoutError`.

**Deterministic test:** Two parametrized cases against the same blocked-`execute` arrangement: (i)
`with fail_after(deadline)` driven by a deterministic clock; (ii) sibling task calls `scope.cancel()`.
Assert *both* produce `adbc_cancel_call_count == 1`, invalidate, `pool.checkedout() == 0`; assert case
(i) surfaces `TimeoutError` and case (ii) surfaces the cancel class. Both backends.

**Priority:** P1

### EDGE-CANDIDATE: `move_on_after` on an *already-finished* op does not cancel or invalidate

**Description:** If `execute` completes *before* the deadline, `move_on_after`/`fail_after` must leave
`cancelled_caught == False`, must not call `adbc_cancel`, and must not invalidate the connection.

**Why it bites:** A wrapper that invalidates whenever it is *inside* a timeout scope (rather than only
when cancellation was actually caught) would needlessly churn the pool on every fast query under a
timeout. anyio: `cancelled_caught` is True "if timeout was reached" — False otherwise.

**Deterministic test:** `with move_on_after(large_deadline) as scope: await acur.execute(sql)` where the
stub's `execute` returns immediately (event pre-set). Assert `scope.cancelled_caught is False`,
`stub.adbc_cancel_call_count == 0`, connection *not* invalidated, `pool.checkedout()` returns to 0 only
via normal checkin. Both backends.

**Priority:** P1

### EDGE-CANDIDATE: trio checkpoint requirement — a cancel with no intervening checkpoint is still delivered at the offload boundary

**Description:** Under trio every `await` is a checkpoint; the offload's limiter-acquire and the
thread-join are checkpoints, so a cancel set just before the offload is delivered at the offload, not
silently dropped.

**Why it bites:** Trio raises if cancellation has nowhere to be delivered in some patterns; more
importantly, a code path that does pure-sync work with *no* checkpoint between setting a cancel and
returning would, under trio, defer delivery — a wrapper relying on prompt delivery could behave
differently on the two backends. This is the concrete "why every test runs under both" case.

**Deterministic test:** Set `scope.cancel()` then immediately `await acur.execute(sql)` with **no** other
await in between. Assert under *both* backends the cancellation is delivered at the offload entry
(driver `execute_call_count == 0`, cancel class propagates) — proving anyio normalises delivery. Mark
trio leg as the discriminating one.

**Priority:** P2

---

## 2. CapacityLimiter / backpressure edge cases

### EDGE-CANDIDATE: A token is borrowed-then-released exactly once across success, exception, and cancel paths

**Description:** Every offload that acquires a limiter token must release it once and only once, whether
the call succeeds, raises an ADBC error, or is cancelled mid-flight.

**Why it bites:** `to_thread.run_sync(limiter=L)` borrows a token for the duration; if the wrapper *also*
manually acquires for the cancel/`adbc_cancel` offload, or if an exception path skips release, the
limiter slowly leaks tokens → eventual deadlock that only shows under sustained error/cancel load.

**Deterministic test:** Use the pool's actual `CapacityLimiter` (`pool._limiter`). For each of the three
paths (success / `fn` raises `AdbcError` / cancelled-mid-block) run one offload and assert
`limiter.borrowed_tokens == 0` afterwards and `limiter.available_tokens == limiter.total_tokens`. Run the
three paths in a loop ×50 and assert the invariant holds every iteration (no slow leak). Both backends.

**Priority:** P1

### EDGE-CANDIDATE: Limiter token not leaked when acquire itself is cancelled while waiting

**Description:** If a task is cancelled while *waiting* to acquire a limiter token (pool saturated), it
must not end up holding/borrowing a token.

**Why it bites:** There was a historical anyio asyncio edge where a task cancelled while waiting could be
granted a token before the cancellation was delivered and fail to hand it to the next waiter. Even though
fixed upstream, the wrapper must not reintroduce it by manually acquiring outside `run_sync`. A leaked
token here permanently shrinks effective concurrency.

**Deterministic test:** Saturate the limiter (hold all `pool_size+max_overflow` tokens via blocked
stub-executes). Launch one more `await acur.execute(...)` that must queue on the limiter; cancel it while
queued (sibling `scope.cancel()`). Release the holders. Assert `limiter.borrowed_tokens` returns exactly
to the number still legitimately held, then to 0 after all release; assert a subsequent fresh checkout
acquires immediately (no permanently lost token). Both backends.

**Priority:** P1

### EDGE-CANDIDATE: Holding a connection while awaiting a *second* offload does not self-deadlock at the bound

**Description:** A task that holds a checked-out connection (one token's worth) and then awaits another
offload needing a token must not deadlock when concurrency equals the limiter bound.

**Why it bites:** Limiter sized to `pool_size+max_overflow`. If N tasks each hold a connection (N tokens)
and each then awaits a *second* independent offload, all N block forever waiting for a token none will
release → classic hold-and-wait deadlock. The design's rule is "keep offloads flat — don't await another
offload while holding a connection," but it must be *proven* either safe-by-construction or guarded.

**Deterministic test:** With `pool_size+max_overflow == N`, check out N connections concurrently (N
tokens). From within each held connection, attempt a second offload that needs a token, all under a
`fail_after(watchdog)`. Assert *either* the design serialises execute on the *same* token (no second
token needed → no deadlock, `fail_after` does not fire) *or* a clear documented error is raised — but
never a watchdog-tripping hang. Both backends. (This test pins the invariant from ARCHITECTURE.md's
"a connection you hold already owns a token via its checkout".)

**Priority:** P1

### EDGE-CANDIDATE: In-flight concurrency is strictly bounded by the limiter under stress

**Description:** Under a flood of concurrent queries, the number simultaneously executing on the driver
never exceeds `pool_size+max_overflow`.

**Why it bites:** Validates CORE-02 / TEST-04. A bug (e.g. accidentally using the default 40-token
limiter, or per-call limiters) would let more than the bound run at once → driver concurrency violations,
or oversubscription of threads.

**Deterministic test:** Instrument the stub to increment a shared counter on `execute` entry and
decrement on exit, recording the running max under a lock. Launch `4 × (pool_size+max_overflow)`
concurrent `execute`s (gated so they all block until released, then released together). Assert observed
`running_max == pool_size+max_overflow` exactly (not less → real parallelism up to the bound; not more →
strict bound). Both backends.

**Priority:** P1

---

## 3. contextvars propagation

### EDGE-CANDIDATE: contextvars set on the task are visible inside the worker thread

**Description:** A `ContextVar` set by the caller before `await cursor.execute(...)` must be readable by
the sync code running in the worker (the driver / a logging filter relying on it).

**Why it bites:** Consumers (dbt-open-sl, Semantic ORM) may set request/trace context vars; if the
offload dropped the context, structured logging in the driver layer loses correlation. anyio *does* copy
the context — but a wrapper that builds its own thread (or uses `asyncio.to_thread`/`run_in_executor`)
would lose it. This test locks in "use anyio's `to_thread`, which copies context."

**Deterministic test:** Define `cv = ContextVar("trace")`. Set `cv.set("abc")`; `await offload(fn, ...)`
where `fn` reads `cv.get()` and stores it on the stub. Assert the stub observed `"abc"`. Both backends.

**Priority:** P2

### EDGE-CANDIDATE: contextvar mutations inside the worker do not leak back to the task

**Description:** If the worker (or driver) calls `cv.set(...)`, that change must not be visible to the
awaiting task after the offload returns.

**Why it bites:** anyio: changes in the worker "do not propagate back." If a future refactor introduced a
shared context, a driver setting a var would corrupt the caller's context → cross-request bleed. Pinning
the no-leak-back property prevents that regression.

**Deterministic test:** Set `cv.set("outer")`; `await offload(fn)` where `fn` does `cv.set("inner")`.
After the await, assert `cv.get() == "outer"`. Both backends.

**Priority:** P2

---

## 4. Reentrancy / connection aliasing

### EDGE-CANDIDATE: Two tasks concurrently using the *same* `AsyncConnection`/`AsyncCursor` are serialized or clearly rejected

**Description:** ADBC forbids concurrent access to one connection. If two tasks share one
`AsyncConnection` and both `await execute`, the wrapper must either serialize them (per-connection
`anyio.Lock`) or raise a clear error — never let two workers touch the connection at once.

**Why it bites:** "objects allow serialized access … do **not** allow concurrent access." The GIL does
not save you (driver releases it). ARCHITECTURE.md leaves the per-connection lock as a "fallback, not
needed by spec" — but the *aliasing* case (same wrapper object, two tasks) is a real misuse that needs a
defined, tested behaviour.

**Deterministic test:** Share one `AsyncConnection`'s cursor between two tasks in a task group; both call
`await acur.execute(sql)` against the `BlockingStubCursor` that records concurrent entry (increments a
counter on entry, asserts it never exceeds 1, records a violation flag if it does). Release both.
Assert: the stub's `max_concurrent_in_execute == 1` (serialized) **or** the second call raised a clear,
typed "connection busy / not shareable" error. Assert no violation flag set under either backend. This is
the test that decides+pins whether the per-connection lock ships in v1.4.0.

**Priority:** P1

### EDGE-CANDIDATE: `adbc_cancel` runs concurrently with the held lock (cancel must NOT take the serialization lock)

**Description:** If a per-connection lock is used, the cancel path must bypass it — `adbc_cancel` is the
documented thread-safe exception and must run *while* `execute` holds the lock, or cancellation
deadlocks.

**Why it bites:** A wrapper that acquires the per-connection lock in *every* method, including the cancel
handler, deadlocks: `execute` holds the lock (blocked in the worker), the cancel handler waits for the
same lock → nobody unblocks. This is a subtle interaction *introduced by* the §4 fix above.

**Deterministic test:** Only meaningful if the lock is adopted. Block `execute` (holding the per-conn
lock); cancel it; assert `adbc_cancel` is invoked (and the stub's `observed_cancel` flips) *despite* the
lock being held — i.e. cancel did not block on the lock. `fail_after` watchdog guards against the
deadlock-hang. Both backends.

**Priority:** P2 (conditional on the lock shipping)

---

## 5. Exception handling

### EDGE-CANDIDATE: ADBC error raised in the worker propagates with type and traceback intact across the thread boundary

**Description:** An `adbc_driver_manager.Error` subclass raised inside the worker must reach the awaiting
task as the *same* exception type, with the original traceback preserved (not re-wrapped, not a bare
`RuntimeError`). (ACUR-06.)

**Why it bites:** `to_thread.run_sync` re-raises the worker exception on the loop side; a wrapper that
catches-and-re-raises can clobber the type or lose the `__traceback__`/`__cause__` chain, making consumer
error handling (`except ProgrammingError`) silently break.

**Deterministic test:** Stub `execute` raises a specific `AdbcError` subclass with a marker message.
`with pytest.raises(ThatExactSubclass) as ei: await acur.execute(sql)`. Assert
`str(ei.value)` contains the marker, `ei.value.__traceback__` includes a frame from inside the stub's
`execute` (proving traceback crossed the boundary), and the type is *exactly* the subclass (not a parent
or wrapper). Both backends.

**Priority:** P1

### EDGE-CANDIDATE: Exception inside `__aenter__` (partial acquisition) leaks no connection

**Description:** If `AsyncConnection.__aenter__` (or the offloaded checkout) raises after a connection was
checked out but before the context is fully established, the connection must be returned/invalidated —
not leaked.

**Why it bites:** There is a gap between "checkout offload completed" and "async context established."
An error in that gap (e.g. building the wrapper, or a cancellation) abandons the raw fairy → pool leak
after `pool_size+max_overflow` occurrences. (Pitfalls 4, escalated to the `__aenter__` boundary.)

**Deterministic test:** Force a failure in the post-checkout step (monkeypatch the wrapper constructor or
inject an error after `pool.connect()` returns) inside `async with await pool.connect()`. Assert
`pool.checkedout() == 0` afterwards (the checked-out connection was reclaimed), and that the injected
error propagates. Repeat ×N in a loop and assert the pool still hands out connections (no cumulative
leak). Both backends.

**Priority:** P1

### EDGE-CANDIDATE: ExceptionGroup / `except*` from task groups carries DB errors correctly

**Description:** When multiple concurrent async queries fail inside one `anyio` task group, the resulting
`ExceptionGroup` (or `BaseExceptionGroup`) must contain the original ADBC errors, splittable by
`except*`.

**Why it bites:** anyio task groups raise grouped exceptions; on Python 3.11+ this is native
`ExceptionGroup`. A wrapper that swallows or flattens errors would break consumers using `except*`. Also,
a cancellation mixed with a real error in the same group must keep both (the cancel class and the
AdbcError) distinguishable.

**Deterministic test:** In one task group, launch two `execute`s: one stub raises `AdbcError`, the other
blocks then is cancelled by the group when the first fails. Use `try/except*`: assert one branch catches
the `AdbcError` (real failure) and the cancellation is handled by the group machinery (no leaked second
error). Assert `pool.checkedout() == 0` after the group. Both backends — `ExceptionGroup` shape is a
known asyncio/trio divergence point, so this *must* run under both.

**Priority:** P1

### EDGE-CANDIDATE: Exception during cleanup (close/reset) does not mask the original error and does not leak

**Description:** If the offloaded `close`/checkin itself raises during `__aexit__` while the body already
raised, the original body exception must surface (or be chained), and the connection must still be
released.

**Why it bites:** ADBC `close` can raise; an `__aexit__` that lets the cleanup error replace the real
error hides the root cause, and an `__aexit__` that bails on cleanup error leaks the connection.

**Deterministic test:** Body raises `ValueError`; stub `close` raises `AdbcError`. Assert the `ValueError`
is what escapes (cleanup error chained via `__context__`, not masking), and `pool.checkedout() == 0`
(connection invalidated despite the close error). Both backends.

**Priority:** P2

---

## 6. Resource lifetime

### EDGE-CANDIDATE: An Arrow table/reader result outliving checkin is safe (no use-after-checkin)

**Description:** A `pyarrow.Table` returned by `fetch_arrow_table` must remain valid after the connection
is checked in; conversely a streaming reader handed back across the await boundary must not be read after
the connection's reset closed its cursors.

**Why it bites:** `_release_arrow_allocators` closes cursors on checkin (reset event). A fully-materialized
`pyarrow.Table` is self-owning and safe; but a *reader* (deferred to v1.4.x) read after checkin is
use-after-free. For v1.4.0 we must prove the *materialized* path is safe and that no live reader escapes.

**Deterministic test (DuckDB, real driver):** `await acur.fetch_arrow_table()` for a known table inside a
`managed_async_pool` block; let the connection check in (exit the block); then read `table.num_rows` /
`table.to_pydict()` and assert correct values *after* checkin (table survives). Additionally assert that
`fetch_arrow_table` does **not** return an unconsumed `RecordBatchReader` (type check: result is
`pyarrow.Table`, satisfying ACUR-04). Both backends.

**Priority:** P1

### EDGE-CANDIDATE: `__del__` of an un-closed async cursor/connection warns and does not crash the loop

**Description:** GC of an `AsyncCursor`/`AsyncConnection` that was never closed must not attempt to
`await`/offload in `__del__` (the loop may be gone) — it should at most emit a `ResourceWarning` and rely
on the pool reset to reclaim Arrow memory.

**Why it bites:** "you can't `await` in `__del__`, and the event loop may be gone." A `__del__` that tries
to schedule an offload raises "no running event loop" or "coroutine was never awaited," polluting logs or
crashing at interpreter shutdown.

**Deterministic test:** Create an `AsyncCursor`, drop the last reference without closing, force
`gc.collect()`. Assert (via `pytest.warns(ResourceWarning)` or a captured warning) a clear leak warning is
emitted, that **no** coroutine-never-awaited warning appears, and no exception escapes `__del__`. Backend-
agnostic (can run on asyncio leg only, but include both for safety).

**Priority:** P2

### EDGE-CANDIDATE: Misuse that drops a coroutine triggers "coroutine was never awaited" only by user error, never internally

**Description:** The library itself must never create a coroutine it forgets to await (every internal
`async def` call is awaited); the warning should only ever be the consumer's fault.

**Why it bites:** A wrapper that, e.g., calls `self._close()` (a coroutine) without `await` in a sync
`__exit__` or callback silently no-ops *and* emits "coroutine was never awaited" — a real, subtle bug
class for offload wrappers that mix sync and async surfaces (note `cursor()` is sync-returning).

**Deterministic test:** Run the full happy-path async lifecycle under
`warnings.catch_warnings(record=True)` with `warnings.simplefilter("error", RuntimeWarning)`. Assert no
`RuntimeWarning: coroutine ... was never awaited` is raised from library code. Both backends.

**Priority:** P2

### EDGE-CANDIDATE: Unclosed pool / pending offload at event-loop shutdown does not raise

**Description:** If a consumer's loop shuts down with a pool still open (no `close_async_pool`), teardown
must not raise from the library (the sync pool can be GC'd; pending worker threads must not call back into
a dead loop).

**Why it bites:** A worker that uses `from_thread.run_sync` to signal the loop after the loop is gone
raises. Pending offloads at shutdown are a classic "unclosed resource at loop teardown" trap.

**Deterministic test:** Within an anyio test, create a pool, start (but do not await to completion) a
blocked `execute`, then exit the test scope so the backend tears down. Assert teardown raises no
exception attributable to the library (the test simply completes cleanly; combine with a warnings filter
to catch stray "Task was destroyed but it is pending"). Both backends. (Primarily an asyncio concern;
trio's nursery semantics make this stricter, so trio acts as the canary.)

**Priority:** P2

---

## 7. Event-loop hygiene

### EDGE-CANDIDATE: No blocking sync DB call ever runs on the event-loop thread

**Description:** Every blocking pool/connection/cursor call must be dispatched off-loop; none may run
inline on the loop thread.

**Why it bites:** CORE-01/03. A bare `pool.connect()` or `cur.execute()` on the loop freezes every other
task (Pitfall 7). The test must *prove* offload, not assume it.

**Deterministic test (thread-identity instrumentation):** Record the loop thread id at test start
(`threading.get_ident()` inside the running task). Instrument the stub's `execute`/`fetch_arrow_table`/
`close`/`connect` to capture `threading.get_ident()` on entry. Run a full lifecycle and assert *every*
blocking call's captured thread id `!= loop_thread_id` (it ran on a worker). Both backends. Complement
with a static AST/import-linter check that `import asyncio` and bare `to_thread.run_sync` without
`limiter=` do not appear in `_async/` (covers CORE-01/CORE-03; one test asserting the lint rule's
findings list is empty).

**Priority:** P1

### EDGE-CANDIDATE: A long offload does not starve unrelated loop tasks

**Description:** While one offload is blocked in a worker, other coroutines on the loop continue to make
progress (the loop is not blocked).

**Why it bites:** Confirms the offload genuinely frees the loop. If a bug made `execute` run inline, a
concurrent heartbeat coroutine would stall.

**Deterministic test:** Start a blocked `execute` (stub blocks on event). Concurrently run a coroutine
that increments a counter across several `anyio.sleep(0)` checkpoints (no real sleep). Assert the counter
advances past a threshold *while* the offload is still blocked (the loop kept ticking), then release the
stub. Both backends.

**Priority:** P1

---

## 8. trio vs asyncio divergences

### EDGE-CANDIDATE: Whole async suite is parametrized over asyncio AND trio (no asyncio-only fixtures)

**Description:** Every async test runs under both backends via the `anyio_backend` parametrization; no
test or fixture pins asyncio.

**Why it bites:** TEST-01. CI often runs asyncio first; an asyncio-only fixture (or an `asyncio`-specific
primitive) hides trio breakage until much later. The suite-level guarantee is itself a requirement.

**Deterministic test:** A meta-test / conftest assertion: collect the async test items and assert each is
parametrized with both `"asyncio"` and `"trio"` (e.g. inspect the `anyio_backend` params), and that the
`anyio_backend_name` fixture takes both values across the run. Plus: grep-style test asserting no
`@pytest.mark.asyncio` and no `asyncio` import in the async test package.

**Priority:** P1

### EDGE-CANDIDATE: Raw `asyncio.CancelledError` is never referenced; only `get_cancelled_exc_class()`

**Description:** Cancellation handling keys off `anyio.get_cancelled_exc_class()`, never
`asyncio.CancelledError` — otherwise trio's `Cancelled` is missed and trio cancellation silently fails to
be handled.

**Why it bites:** A handler `except asyncio.CancelledError` passes asyncio tests and is a no-op under trio
(trio raises `trio.Cancelled`, a different class) → the `adbc_cancel`/invalidate path never runs on trio
→ pool leak on trio only.

**Deterministic test:** Combination of the §1 "swallow" test run under trio (proves the handler catches
trio's class) plus a static check that `asyncio.CancelledError` / `import asyncio` are absent from
`_async/`. The behavioural half: cancel a blocked execute under **trio** and assert the
`adbc_cancel`/invalidate path *did* run (it would not if the handler caught only asyncio's class).

**Priority:** P1

### EDGE-CANDIDATE: Cancel-scope semantics identical under both backends (level cancellation normalised)

**Description:** A cancel scope cancelled while a worker is blocked produces identical observable
behaviour (one `adbc_cancel`, one invalidate, `checkedout()==0`) on both backends despite asyncio's
native edge model.

**Why it bites:** anyio normalises to level cancellation inside scopes, but only if the wrapper uses anyio
scopes throughout. Any leakage of raw asyncio cancellation would diverge. This is the assertion that
neutrality actually holds end-to-end.

**Deterministic test:** Run the §1 "cancel during blocked worker" test and capture
`(adbc_cancel_call_count, invalidate_count, checkedout_after)` as a tuple; assert the tuple is *equal*
across the asyncio and trio parametrizations (compare via a session-scoped record, or simply assert the
exact same expected tuple under both legs).

**Priority:** P1

---

## 9. Time / scheduling

### EDGE-CANDIDATE: Cancellation/timeout tests use a deterministic clock or event gating, not real sleeps

**Description:** Timeout tests must be driven by anyio's virtual time (the autojump-style deterministic
clock the test backend provides) or by event gating, so they neither flake nor consume wall-clock.

**Why it bites:** Sleep-based timing flakes under CI load (Pitfall 12). anyio supports a fake/virtual
clock; on asyncio via the test runner and on trio via `trio.testing.MockClock` / the anyio backend
option. Where a virtual clock isn't uniformly available across both backends, event-gating
(`threading.Event` + anyio `Event`) replaces sleeps entirely.

**Deterministic test:** Audit-style: the cancellation/timeout tests above must contain no
`anyio.sleep(>0)` / `time.sleep`. Enforce with a test that scans the async test module source for
`sleep(` with a positive literal in timeout tests (allow `sleep(0)` checkpoints). Functionally, the
`fail_after` cases advance a controllable clock to the deadline rather than waiting real time.

**Priority:** P1

### EDGE-CANDIDATE: `move_on_after` deadline already passed → body still runs at least one checkpoint, op invalidated cleanly

**Description:** Edge timing: a `move_on_after` whose deadline is already in the past must still cleanly
cancel a blocked execute (deliver at the first checkpoint), invalidate, and `checkedout()==0` — it must
not skip the `adbc_cancel`/cleanup.

**Why it bites:** A zero/negative timeout is a real consumer footgun; the wrapper must handle "already
expired" identically to "expired during the call," not crash or leak.

**Deterministic test:** `with move_on_after(0): await acur.execute(blocking_sql)`. Assert
`scope.cancelled_caught is True`, `adbc_cancel_call_count == 1` (worker was unblocked), invalidate ran,
`pool.checkedout() == 0`. Both backends.

**Priority:** P2

### EDGE-CANDIDATE: Timeout precision does not over-cancel fast ops (no `adbc_cancel` on sub-deadline completion)

**Description:** An op finishing just under the deadline must not be cancelled — `cancelled_caught` False,
no `adbc_cancel`. (Sharper, virtual-clock version of the §1 "already-finished" test.)

**Why it bites:** Off-by-one in deadline handling could cancel ops that actually completed in time,
churning the pool and surprising users with spurious `TimeoutError`s.

**Deterministic test:** With a virtual clock, complete the stub `execute` at deadline−ε; assert
`cancelled_caught is False`, `adbc_cancel_call_count == 0`, normal checkin. Both backends.

**Priority:** P2

---

## Consolidated EDGE-NN requirements (paste-ready for REQUIREMENTS.md)

Suggested new category: **Async Edge-Case Test Coverage (EDGE-NN)**. Each row is one atomic, testable
requirement. "Backends" = runs under both asyncio and trio. P1 = must-have for v1.4.0; P2 = hardening,
may slip to v1.4.x. The "Ties to" column links existing requirements so the roadmapper can co-locate.

| ID | Requirement (deterministic test) | Group | Pri | Backends | Ties to |
|----|----------------------------------|-------|-----|----------|---------|
| **EDGE-01** | Cancel delivered *before* offload starts: driver `execute` never called, no `adbc_cancel`, connection stays clean, cancel exc propagates | Cancellation | P1 | both | CANCEL-01 |
| **EDGE-02** | Cancel *during* blocked worker: `adbc_cancel` called exactly once (shielded), worker joined, connection invalidated, `checkedout()==0`, cancel exc propagates | Cancellation | P1 | both | CANCEL-01/02/03/04 |
| **EDGE-03** | Framework cancel class is never swallowed by the offload/try-except; exact `get_cancelled_exc_class()` instance escapes; no hang under trio | Cancellation | P1 | both | CANCEL-04 |
| **EDGE-04** | Double-cancel during shielded cleanup is idempotent: one `adbc_cancel`, one invalidate, one cancel exc | Cancellation | P1 | both | CANCEL-03 |
| **EDGE-05** | Cancel during `__aexit__`/checkin still completes checkin under shield; `checkedout()==0` (connection + cursor) | Cancellation | P1 | both | CANCEL-03, ACONN-02, ACUR-05 |
| **EDGE-06** | `fail_after` timeout and explicit `scope.cancel()` handled identically (both → `adbc_cancel`+invalidate); only the surfaced exc type differs | Cancellation | P1 | both | CANCEL-01/02 |
| **EDGE-07** | `move_on_after` on an already-finished op: `cancelled_caught False`, no `adbc_cancel`, no invalidate | Cancellation | P1 | both | CANCEL-02 |
| **EDGE-08** | trio checkpoint delivery: cancel set with no intervening checkpoint is still delivered at the offload boundary on both backends | trio-vs-asyncio | P2 | both | TEST-01 |
| **EDGE-09** | Limiter token borrowed-then-released exactly once across success/error/cancel paths (×50 loop, `borrowed_tokens==0`) | Limiter | P1 | both | CORE-02, TEST-04 |
| **EDGE-10** | Limiter token not leaked when acquire is cancelled while queued on a saturated limiter; concurrency fully recovers | Limiter | P1 | both | CORE-02, TEST-04 |
| **EDGE-11** | Holding a connection while awaiting a second offload does not self-deadlock at the bound (serialized on the held token or clear error; watchdog never trips) | Limiter | P1 | both | CORE-02, TEST-04 |
| **EDGE-12** | In-flight concurrency strictly bounded: observed running-max `== pool_size+max_overflow` under 4× flood | Limiter | P1 | both | CORE-02, TEST-04 |
| **EDGE-13** | contextvars set on the task are visible inside the worker thread | contextvars | P2 | both | CORE-01 |
| **EDGE-14** | contextvar mutations inside the worker do not leak back to the task | contextvars | P2 | both | CORE-01 |
| **EDGE-15** | Two tasks sharing one `AsyncConnection`/`AsyncCursor` are serialized (max-concurrent-in-execute ==1) or raise a clear typed error; no concurrency violation | Reentrancy | P1 | both | CORE-04, ACONN-03 |
| **EDGE-16** | `adbc_cancel` runs despite a held per-connection lock (cancel bypasses the lock; no deadlock) | Reentrancy | P2† | both | CANCEL-01 |
| **EDGE-17** | ADBC error from worker propagates with exact type + original traceback across the thread boundary | Exceptions | P1 | both | ACUR-06 |
| **EDGE-18** | Exception in `__aenter__`/post-checkout leaks no connection (`checkedout()==0`, no cumulative leak over N) | Exceptions | P1 | both | ACONN-01/02 |
| **EDGE-19** | ExceptionGroup/`except*` from a task group preserves original ADBC errors and keeps cancel distinguishable; `checkedout()==0` after | Exceptions | P1 | both | CANCEL-04, TEST-01 |
| **EDGE-20** | Exception during cleanup does not mask the body error (chained via `__context__`); connection still released | Exceptions | P2 | both | ACONN-05, ACUR-05 |
| **EDGE-21** | Materialized `fetch_arrow_table` result is valid after checkin (no use-after-checkin); result is a `pyarrow.Table`, not a live reader | Resource lifetime | P1 | both | ACUR-04, ACONN-06 |
| **EDGE-22** | `__del__` of an un-closed async cursor/connection emits a `ResourceWarning`, no "coroutine never awaited", no exception | Resource lifetime | P2 | both | ACUR-05, ACONN-05 |
| **EDGE-23** | Full happy-path lifecycle emits no "coroutine was never awaited" `RuntimeWarning` from library code | Resource lifetime | P2 | both | ACONN-03 |
| **EDGE-24** | Open pool / pending offload at loop shutdown raises no library-attributable exception (trio nursery as canary) | Resource lifetime | P2 | both | APOOL-02 |
| **EDGE-25** | Every blocking DB call runs off the loop thread (captured worker thread id != loop thread id) + lint asserts no `asyncio` import / no bare `to_thread` w/o limiter in `_async/` | Event-loop hygiene | P1 | both | CORE-01, CORE-03 |
| **EDGE-26** | A long blocked offload does not starve the loop: a concurrent coroutine advances across `sleep(0)` checkpoints while the offload blocks | Event-loop hygiene | P1 | both | CORE-01 |
| **EDGE-27** | Meta: every async test is parametrized over asyncio AND trio; no `@pytest.mark.asyncio`, no `asyncio` import in async test package | trio-vs-asyncio | P1 | n/a | TEST-01 |
| **EDGE-28** | Cancellation handling uses `get_cancelled_exc_class()` only; trio cancel of a blocked execute *does* run `adbc_cancel`+invalidate; no `asyncio.CancelledError` in `_async/` | trio-vs-asyncio | P1 | both (trio is the discriminator) | CORE-03, CANCEL-04 |
| **EDGE-29** | Cancel-scope behaviour identical across backends: `(adbc_cancel_count, invalidate_count, checkedout_after)` tuple equal under asyncio and trio | trio-vs-asyncio | P1 | both | CANCEL-04, TEST-01 |
| **EDGE-30** | Timeout/cancel tests use a virtual clock or event gating — no positive-duration `sleep` in timeout tests (enforced by source scan) | Time/scheduling | P1 | both | TEST-04 |
| **EDGE-31** | `move_on_after(0)` (already-expired) still cancels a blocked execute cleanly: `cancelled_caught True`, one `adbc_cancel`, invalidate, `checkedout()==0` | Time/scheduling | P2 | both | CANCEL-02 |
| **EDGE-32** | Timeout precision: op completing at deadline−ε is not cancelled (`cancelled_caught False`, no `adbc_cancel`, normal checkin) | Time/scheduling | P2 | both | CANCEL-02 |

† EDGE-16 is conditional: only required if the per-connection `anyio.Lock` (from EDGE-15) is adopted.

**P1 count: 19 · P2 count: 13.** The 19 P1 items are the must-have edge-coverage for v1.4.0; they
cluster on the dedicated **Cancellation** phase (EDGE-01..07, 28, 29), the **Core wrapper** phase
(EDGE-09..12, 15, 17, 18, 25, 26), the **Exceptions/task-group** surface (EDGE-19), the **Testing** phase
meta-guards (EDGE-27, 30), and the **fetch_arrow_table** path (EDGE-21).

### Shared test infrastructure these requirements imply (one fixture-build task)

- `BlockingStubCursor` / `BlockingStubConnection` — dbapi-shaped fake: `execute`/`fetch_arrow_table`
  block on a `threading.Event`; `adbc_cancel` releases the event + flips `observed_cancel`; records
  per-call thread id, call counts, max-concurrent-in-execute, and an `entered` event. Backs EDGE-01..12,
  15, 17, 25, 26, 28, 29, 31, 32.
- A virtual-clock / event-gating harness usable under both backends (anyio backend option or
  `trio.testing.MockClock` for the trio leg; event gating where uniform virtual time isn't available).
  Backs EDGE-06, 30, 31, 32.
- A small `import-linter` / AST rule (`asyncio`-banned, bare-`to_thread`-banned in `_async/`) surfaced
  as a test. Backs EDGE-25, 27, 28.

---

## Sources

- anyio — *Working with threads* — default 40-token limiter; `to_thread.run_sync` is shielded from
  cancellation by default; `abandon_on_cancel=True` "the thread will still continue running – only its
  outcome will be ignored"; **current context copied to the worker**, changes don't propagate back;
  `from_thread.run_sync` for loop callbacks — https://anyio.readthedocs.io/en/stable/threads.html — **HIGH**
- anyio — *Cancellation and timeouts* — `get_cancelled_exc_class()`; **level** cancellation in anyio
  scopes vs asyncio's **edge** model; "Always reraise the cancellation exception if you catch it. Failing
  to do so may cause undefined behavior"; finalization needing `await` "must be enclosed in a shielded
  cancel scope, or the operation will be cancelled immediately"; `cancelled_caught` True only if the
  timeout was reached; `current_effective_deadline()` — https://anyio.readthedocs.io/en/stable/cancellation.html — **HIGH**
- anyio — *API reference* — `to_thread.run_sync(func, *args, abandon_on_cancel=False, cancellable=None,
  limiter=None)` with `cancellable` a **deprecated alias** of `abandon_on_cancel`; `from_thread.run` /
  `from_thread.run_sync(func, *args, token=None)`; `CapacityLimiter` referenced as the thread budget —
  https://anyio.readthedocs.io/en/stable/api.html — **HIGH**
- anyio — *CapacityLimiter* methods/attrs (`acquire`/`acquire_on_behalf_of`, `release`/
  `release_on_behalf_of` raising `RuntimeError` if not borrowed, `borrowed_tokens`/`available_tokens`/
  `total_tokens`) and the historical cancel-while-acquiring token-handoff fix —
  https://anyio.readthedocs.io/en/stable/synchronization.html + anyio releases — **HIGH (API), MEDIUM (the
  exact historical-bug shape — treated as a regression test, not a current defect)**
- trio — *Core functionality* — every `await` is a checkpoint / cancellation point; a scope cancelled
  just as a function finishes may not raise `Cancelled`; the cancel flag stays True even when delivered
  too late — https://trio.readthedocs.io/en/stable/reference-core.html — **HIGH**
- ADBC concurrency spec + statement API — serialized cross-thread access allowed, concurrent forbidden;
  `adbc_cancel` is the documented thread-safe exception — (carried from PITFALLS.md / ARCHITECTURE.md
  Sources) — **HIGH**
- adbc-poolhouse source read directly: `_pool_factory.py` (`_release_arrow_allocators` reset listener
  closing `_cursors`; `close_pool` = `dispose()` + `_adbc_source.close()`; defaults
  `pool_size=5/max_overflow=3/timeout=30/recycle=3600/pre_ping=False`) — basis for the checkin-symmetry,
  Arrow-lifetime, and `checkedout()` assertions — **HIGH**

---
*Async edge-case test research for: anyio thread-offload async layer over sync ADBC + SQLAlchemy QueuePool
(adbc-poolhouse v1.4.0). Extends PITFALLS.md; verified against current anyio 4.x / trio docs, 2026-06-26.*
