# Phase 29: Arrow Streaming - Research

**Researched:** 2026-07-01
**Domain:** async streaming over a sync `pyarrow.RecordBatchReader`, offload + reader-lifetime binding
**Confidence:** HIGH (all five open questions resolved with live probes against the installed pyarrow 24.0.0 / adbc_driver_manager 1.11.0 / DuckDB driver, cross-checked against the actual `_async/` source)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-29-01..D-29-18 — verbatim, binding)

**Wrapper structure (STREAM-01/02/03)**
- **D-29-01:** New class `AsyncRecordBatchReader` in new file `src/adbc_poolhouse/_async/_reader.py`, mirroring `_cursor.py`. **Composition, not subclassing** — holds a reference to the sync `pyarrow.RecordBatchReader`; does NOT subclass it. Subclassing would leak pyarrow's synchronous `read_next_batch`/`__iter__` straight through, bypassing the limiter, the lifetime lock, and cancel-safety.
- **D-29-02:** Constructor `(sync_reader, limiter, owner)` — identical shape to `AsyncCursor.__init__(sync_cursor, limiter, owner)`. `owner` is the `AsyncConnection`, needed for `_reader_open` guard and `invalidate`.
- **D-29-03:** `AsyncCursor.fetch_record_batch()` offloads reader *creation* through `cancellable_offload` (holding `self._owner._offloading()`, `on_abort=self._owner.invalidate`), exactly like `fetch_arrow_table`, then wraps the returned sync reader in `AsyncRecordBatchReader(...)`.

**Reader surface (D-29-04):** "hide nothing safe to expose; replace every blocking member with its async twin, never leave it raw." No-I/O members pass through unchanged (`schema` = plain sync `@property`, following `description`/`rowcount`/`arraysize`). Blocking I/O replaced by async twins (`read_next_batch`→`__anext__`; sync `__iter__`/`__next__`→`__aiter__`/`__anext__`; sync `close`/`__enter__`/`__exit__`→async `close`/`__aenter__`/`__aexit__`).
- **D-29-05:** `__anext__` offloads one `read_next_batch()` pull via `cancellable_offload` (`on_abort=owner.invalidate`) and translates `StopIteration`→`StopAsyncIteration`. `StopIteration` must NOT cross the async boundary (becomes `RuntimeError`); worker catches it and signals exhaustion via a sentinel; `__anext__` raises `StopAsyncIteration` on the sentinel. (Confirm mechanism — DONE below.)
- **D-29-06:** `close()` offloads `sync_reader.close()` inside `anyio.CancelScope(shield=True)`, mirroring `AsyncCursor.close`.
- **D-29-07:** **Phase scope = iterate + close + schema only.** Do NOT add `await reader.read_all()` / `read_pandas()` twins.

**Connection lifetime lock — STREAM-06 = Model B (lifetime-held)**
- **D-29-08:** A live reader locks the parent connection for its **whole lifetime**, not just an in-flight pull. Per-call `_in_use` alone is insufficient: between pulls it reads False, so a concurrent op in the gap interleaves with a still-open Arrow stream on the same connection.
- **D-29-09:** Add a **persistent `_reader_open` guard on `AsyncConnection`**, distinct from `_in_use`. Set True when `fetch_record_batch()` hands back a live reader; cleared on `reader.close()`/`__aexit__`.
- **D-29-10:** **Two-tier entry guard.** Foreign callers (`execute`, another cursor, `commit`, …) reject with `ConnectionBusyError` if `_in_use` **OR** `_reader_open`. The reader's own pulls reject on `_in_use` only, **exempt** from `_reader_open` (reentrancy exemption). Each pull still brackets the per-call `_in_use` C-access guard.

**Done signal & lifetime binding (STREAM-04, EDGE-33)**
- **D-29-11:** "Done" signal = **explicit `close()`** (via `async with`), NOT iteration exhaustion. In pyarrow, drained ≠ freed. `async for` alone does NOT auto-close and does NOT clear `_reader_open`.
- **D-29-12:** Reader-lifetime binding is mostly free — the sync `reset` handler `_release_arrow_allocators` (`_pool_factory.py:407`) closes the underlying dbapi cursor on every checkin path, which closes the reader. Read-after-checkin therefore surfaces the driver's native closed-stream error naturally. The async reader adds only a thin `_detached` guard — NO weakref/registration machinery.
- **D-29-13:** A stale `_reader_open == True` is harmless: it lives on the `AsyncConnection`, thrown away at checkin (each `pool.connect()` wraps a fresh fairy in a fresh `AsyncConnection`). Checkin is the backstop eraser; close is the only clear. A drained-but-never-closed reader keeps the connection locked until checkin — which is why `async with reader:` is documented canonical.

**Cancel-safety (D-29-14 / STREAM-05):** cancel/timeout on a pull fires `adbc_cancel()` once from the loop thread and invalidates the connection (`on_abort=owner.invalidate`) so `pool.checkedout() == 0`, identical under asyncio+trio, reusing Phase 25 `cancellable_offload` unchanged.

**Finalizers & typing**
- **D-29-15:** `__del__` on an un-closed reader emits `ResourceWarning` (never "coroutine was never awaited" `RuntimeWarning`); happy path (closed via context manager) emits neither. `__del__` cannot `await` — warn-only; actual release rides the reset event.
- **D-29-16:** An exception during shielded reader cleanup chains the body error via `__context__` and still releases/invalidates the connection.
- **D-29-17:** Add a `_SyncReader` structural `Protocol` alongside `_SyncCursor` (`schema` property, `read_next_batch`, `close`). Extend `_SyncCursor` with `fetch_record_batch` (PKG-01). All new async public API basedpyright-strict-clean (0 errors); AST import-lint guard passes over `_async/` (PKG-03).
- **D-29-18:** Document canonical usage `async with await cursor.fetch_record_batch() as reader:` then `async for batch in reader:`.

### Claude's Discretion (research resolves these below)
- Exact `StopIteration`→`StopAsyncIteration` sentinel mechanism — **RESOLVED: worker-side catch → module-level sentinel object.**
- Precise placement of the `_detached` guard + `_reader_open` reentrancy threading — **RESOLVED: a `from_reader: bool = False` keyword on the entry method.**
- `_reader_open` as bare bool vs counter — **RESOLVED: bare bool** (only one reader per connection is possible).

### Deferred Ideas (OUT OF SCOPE — ignore)
- `await reader.read_all()` / `read_pandas()` twins (not in STREAM-01..06; `read_pandas` overlaps Phase 31).
- `adbc_ingest` bulk write — Phase 30. `fetch_df` / `fetch_polars` — Phase 31.
- P2 edge-hardening matrix (contextvars, trio-checkpoint, timeout precision, loop-shutdown) — Phase 32.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STREAM-01 | `await cursor.fetch_record_batch()` → `AsyncRecordBatchReader` (creation offloaded) | `fetch_arrow_table` offload shape (`_cursor.py:325-353`) copied verbatim; wrap result in reader |
| STREAM-02 | `async for batch in reader:` per-pull offloaded | `__anext__` = `cancellable_offload(read_next_batch)`; sentinel mechanism resolved (Q1) |
| STREAM-03 | async CM; `close`/`__aexit__` offloaded + shielded, frees Arrow before checkin | `AsyncCursor.close` shielded idiom (`_cursor.py:355-372`) copied |
| STREAM-04 | reader lifetime bound to checkout; read-after-checkin → native closed-stream error, no UAF | `_release_arrow_allocators` (`_pool_factory.py:407-428`) + probe: `ArrowInvalid` "stream already closed" (Q2) |
| STREAM-05 | cancel/timeout pull → `adbc_cancel` once + invalidate, `checkedout()==0`, asyncio+trio | `cancellable_offload` `on_abort=owner.invalidate` (`_cancel.py:41-47`) reused unchanged |
| STREAM-06 | second in-flight op while reader live → `ConnectionBusyError` | two-tier guard `_in_use` OR `_reader_open` (Q3/Q5) |
| EDGE-20 | shielded-cleanup exception chains body error via `__context__`, still releases | close chaining pattern (Q4/D-29-16) |
| EDGE-22 | `__del__` of unclosed reader → `ResourceWarning`, never `RuntimeWarning` | warn-only `__del__`, no coroutine (Q4) |
| EDGE-23 | happy path (closed via CM) → neither warning | `_detached`/`_closed` flag gates `__del__` warning |
| EDGE-33 | read-after-checkin → native closed-stream error; drain-then-checkin → correct rows; DuckDB+Snowflake, asyncio+trio | probe (Q2) + `snowflake_async_pool` cassette fixture (conftest) |
| PKG-01 | `_SyncCursor` gains `fetch_record_batch`; `_SyncReader` added; strict 0 errors | Protocol extension pattern (`_cursor.py:50-74`) |
| PKG-03 | AST import-lint guard passes over `_async/`: no `import asyncio`, no bare `to_thread` | guard rules (`tests/_async_harness/guard.py:64-144`) |
</phase_requirements>

## Summary

Phase 29 adds `AsyncRecordBatchReader` — a composition wrapper over a sync `pyarrow.RecordBatchReader` obtained from the ADBC dbapi cursor's `fetch_record_batch()`. Every locked decision maps cleanly onto an idiom that already exists in `_cursor.py` / `_connection.py` / `_cancel.py`; the only genuinely new production machinery is the **two-tier connection guard** (`_reader_open` alongside `_in_use`) and the reader's own **`__del__` + `_detached` guard**. There are no new dependencies, no sync-core change, and every blocking call still routes through the single `offload` chokepoint.

The three design risks the CONTEXT flagged are all now settled by live probes against the installed stack (pyarrow **24.0.0**, adbc_driver_manager **1.11.0**, DuckDB driver):
1. **End-of-stream** — `RecordBatchReader.read_next_batch()` raises a bare Python `StopIteration` (`args=()`) at exhaustion. `StopIteration` crossing `anyio.to_thread.run_sync` becomes `RuntimeError("coroutine raised StopIteration")` under **both** asyncio and trio (probed). So the worker MUST catch `StopIteration` and return a module-level sentinel; `__anext__` raises `StopAsyncIteration` on the sentinel.
2. **Read-after-close / read-after-checkin** — both raise `pyarrow.lib.ArrowInvalid: Attempt to read from a stream that has already been closed` — a clean Python exception, never a segfault. The reset-event `cur.close()` closes the reader (confirmed: reading after `cursor.close()` raises the same `ArrowInvalid`). This gives STREAM-04 / EDGE-33 for free; poolhouse adds no bespoke error type.
3. **`_reader_open` reentrancy** — cleanest threading is a `from_reader: bool = False` keyword on a new connection entry method; the reader passes `from_reader=True` so its own pulls skip the `_reader_open` check while still taking the per-call `_in_use` guard.

**Primary recommendation:** Build `_reader.py` as a near-verbatim sibling of `_cursor.py`. Add `_reader_open` + a two-tier `_enter_offload(from_reader=...)` to `_connection.py`. Resolve exhaustion with a worker-side `StopIteration` catch returning a private sentinel. Resolve lifetime with the `_release_arrow_allocators` reset handler plus a thin `_detached`/`_closed` bool on the reader (guards only `__del__`'s warning discipline — the native `ArrowInvalid` is the read-after-checkin error, not a poolhouse-raised one).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Reader creation (`fetch_record_batch`) | AsyncCursor (`_cursor.py`) | AsyncConnection guard | Offloads sync `cursor.fetch_record_batch()`, sets `_reader_open` |
| Per-batch pull (`__anext__`) | AsyncRecordBatchReader (`_reader.py`) | offload chokepoint | Each `read_next_batch()` is a bounded, cancellable offload |
| Reader-lifetime lock | AsyncConnection (`_reader_open`) | pool reset event | Lifetime binding is a connection concern; teardown is the pool's |
| Read-after-checkin safety | sync core / driver | pool reset handler | The driver raises `ArrowInvalid`; the reset handler closes the cursor |
| Cancel/invalidate on pull | `cancellable_offload` (`_cancel.py`) | AsyncConnection.invalidate | Reused verbatim from Phase 25 |
| Finalizer warning | AsyncRecordBatchReader `__del__` | — | Warn-only; real release rides the reset event |

## Standard Stack

### Core (all already installed — no new deps)
| Library | Version (installed) | Purpose | Why Standard |
|---------|---------------------|---------|--------------|
| `pyarrow` | **24.0.0** [VERIFIED: `.venv/bin/python -c "import pyarrow"`] | `RecordBatchReader` surface being wrapped | Already a core dep (REQUIREMENTS §"No dependency or extras change") |
| `adbc_driver_manager` | **1.11.0** [VERIFIED: import] | exposes `cursor.fetch_record_batch()` | The sync DBAPI cursor poolhouse wraps |
| `anyio` | (installed; no `__version__` attr) [VERIFIED: import] | offload + `CancelScope(shield=True)` + task-group cancel | The async-neutrality substrate the whole layer rides |
| `adbc_driver_duckdb` | installed [VERIFIED: probe ran] | real-driver test backend | The happy-path + EDGE-33 DuckDB leg |

**Installation:** none. `uv sync` already provides all of the above. No `[project.dependencies]`, `[optional-dependencies]`, or `__init__.py` lazy-import change (PKG-02 is a Phase 31 concern; unaffected here).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| worker-side `StopIteration` catch → sentinel | rely on driver returning `None`/empty at end | REJECTED — `read_next_batch()` raises `StopIteration`, does not return `None` (probed); relying on driver-specific empty-batch behaviour is non-portable |
| `_reader_open` counter | bare bool | bool suffices — only one reader per connection is reachable (a second `fetch_record_batch` while `_reader_open` is True is itself rejected by the foreign-caller tier) |
| weakref/`finalize` registration | reset-event + `_detached` bool | REJECTED by D-29-12 — the reset handler already closes the cursor; registration machinery is redundant and heavier |

## Package Legitimacy Audit

No new packages are installed by this phase. All libraries used (`pyarrow`, `adbc_driver_manager`, `anyio`, `adbc_driver_duckdb`) are pre-existing project dependencies verified present in `.venv` this session.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
  user task                         loop thread                     worker thread
  ─────────                         ───────────                     ─────────────
  await cursor.fetch_record_batch()
        │
        ▼
  AsyncCursor.fetch_record_batch()
   ├─ owner._offloading()  ──────► _enter_offload()  [_in_use OR _reader_open? → ConnectionBusyError]
   └─ cancellable_offload(cursor.fetch_record_batch, on_abort=owner.invalidate)
                                          │  offload(limiter) ──────────────► sync cursor.fetch_record_batch()
                                          ◄──────────────────────────────────  returns sync RecordBatchReader
        │
        ▼   owner._reader_open = True     (set AFTER successful creation)
  AsyncRecordBatchReader(sync_reader, limiter, owner)
        │
  async for batch in reader:
        │
        ▼
  reader.__anext__()
   ├─ owner._offloading(from_reader=True) ► _enter_offload(from_reader=True) [_in_use only; _reader_open exempt]
   └─ cancellable_offload(_pull, on_abort=owner.invalidate)
                                          │  offload ─────────────────────►  _pull(): try read_next_batch()
                                          │                                    except StopIteration: return _EXHAUSTED
                                          ◄──────────────────────────────────  RecordBatch | _EXHAUSTED
        │
        ├─ batch is _EXHAUSTED → raise StopAsyncIteration   (does NOT clear _reader_open — D-29-11)
        └─ else → return batch

  async with ... as reader: __aexit__ → reader.close()
   └─ CancelScope(shield=True): offload(sync_reader.close); owner._reader_open = False; reader._detached = True

  ── on connection checkin (__aexit__/close/invalidate) ──
  pool 'reset' event → _release_arrow_allocators → cur.close() → reader's C-stream closed
        │
  later reader.read_next_batch() → pyarrow ArrowInvalid("stream already closed")   [native, clean]
```

### Recommended Project Structure
```
src/adbc_poolhouse/_async/
├── _offload.py       # unchanged — single to_thread chokepoint
├── _cancel.py        # unchanged — cancellable_offload reused verbatim
├── _cursor.py        # EXTEND: add fetch_record_batch(); extend _SyncCursor Protocol
├── _connection.py    # EXTEND: add _reader_open + two-tier _enter_offload(from_reader=)
└── _reader.py        # NEW: AsyncRecordBatchReader + _SyncReader Protocol
```

### Pattern 1: `fetch_record_batch` on AsyncCursor (mirror `fetch_arrow_table`)
**What:** Offload reader *creation*, then wrap. Set `_reader_open` only after success.
**When to use:** the STREAM-01 entry point.
**Example:**
```python
# _cursor.py — mirrors fetch_arrow_table (_cursor.py:325-353) exactly.
async def fetch_record_batch(self) -> AsyncRecordBatchReader:
    with self._owner._offloading():  # noqa: SLF001  (foreign-tier guard: _in_use OR _reader_open)
        sync_reader = await cancellable_offload(
            self._adbc_cancel,
            self._cursor.fetch_record_batch,
            limiter=self._limiter,
            on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
        )
    # Lock the connection for the reader's whole lifetime (D-29-08/09). Set OUTSIDE
    # the _offloading() span (which has already exited and cleared _in_use), and only
    # after successful creation so a cancelled/failed creation leaves _reader_open False.
    self._owner._reader_open = True  # noqa: SLF001
    return AsyncRecordBatchReader(sync_reader, self._limiter, self._owner)
```
Note the ordering subtlety: `_offloading()` sets and clears `_in_use` around the creation call; `_reader_open` is set *after* it exits. Do NOT hold `_offloading()` across the `_reader_open = True` write — they are two different guards with different lifetimes.

### Pattern 2: `__anext__` with worker-side exhaustion sentinel (RESOLVES Q1)
**What:** each pull is a cancellable offload; the worker catches `StopIteration` and returns a private sentinel so it never crosses the async boundary.
**Example:**
```python
# _reader.py — module level
class _Exhausted:
    """Private end-of-stream marker returned by the worker (D-29-05, Q1)."""
_EXHAUSTED = _Exhausted()

def _pull(sync_reader: _SyncReader) -> "pyarrow.RecordBatch | _Exhausted":
    # Runs on the WORKER thread. read_next_batch() raises a bare StopIteration at
    # end-of-stream (probed: args=()). StopIteration MUST NOT propagate through
    # to_thread.run_sync — it becomes RuntimeError("coroutine raised StopIteration")
    # under both asyncio and trio (probed). Catch it here and signal exhaustion by
    # value instead.
    try:
        return sync_reader.read_next_batch()
    except StopIteration:
        return _EXHAUSTED

class AsyncRecordBatchReader:
    async def __anext__(self) -> pyarrow.RecordBatch:
        with self._owner._offloading(from_reader=True):  # noqa: SLF001  (reader tier: _in_use only)
            batch = await cancellable_offload(
                self._adbc_cancel,
                _pull,
                self._reader,
                limiter=self._limiter,
                on_abort=self._owner.invalidate,
            )
        if batch is _EXHAUSTED:
            raise StopAsyncIteration  # does NOT close / clear _reader_open (D-29-11)
        return batch

    def __aiter__(self) -> AsyncRecordBatchReader:
        return self
```
`_pull` is a module-level function (not a lambda/bound method that captures `StopIteration` semantics loosely) so the `TypeVarTuple` arity in `cancellable_offload`/`offload` is preserved and the source guard sees a clean call. `_adbc_cancel` mirrors `AsyncCursor._adbc_cancel` (`_cursor.py:130-143`) — but the reader's cancel must target the **cursor's** `adbc_cancel`, not the reader's (the reader has none). See Landmine 6.

### Pattern 3: Two-tier connection guard (RESOLVES Q3/Q5 — the one new bit of machinery)
**What:** `_reader_open` lifetime flag + a `from_reader` exemption on the entry method.
**Example:**
```python
# _connection.py — extend __init__
self._in_use = False
self._reader_open = False  # D-29-09: a live reader locks the connection for its lifetime

def _enter_offload(self, *, from_reader: bool = False) -> None:
    # Per-call C-access guard (unchanged) PLUS the lifetime reader guard (new).
    if self._in_use:
        raise ConnectionBusyError
    # Foreign callers (execute, commit, another cursor, a NEW fetch_record_batch)
    # are also rejected while a reader is live. The reader's own pulls pass
    # from_reader=True to exempt themselves from this tier only (D-29-10 reentrancy).
    if self._reader_open and not from_reader:
        raise ConnectionBusyError
    self._in_use = True

@contextlib.contextmanager
def _offloading(self, *, from_reader: bool = False) -> Generator[None]:
    self._enter_offload(from_reader=from_reader)
    try:
        yield
    finally:
        self._exit_offload()
```
`_exit_offload` is unchanged (clears `_in_use` only — never `_reader_open`). `_reader_open` is set by `fetch_record_batch` and cleared by `reader.close()`; checkin (`__aexit__`) is the backstop (D-29-13) — a fresh `AsyncConnection` per `connect()` (`_pool.py:102`) means a stale `_reader_open=True` never survives to the next checkout. **Every existing `_offloading()` call site is unaffected** — `from_reader` defaults False, so `execute`/`fetch*`/`commit`/`close` keep their current foreign-tier semantics with no edit.

### Pattern 4: Shielded `close` + warn-only `__del__` (RESOLVES Q4)
```python
async def close(self) -> None:
    # Idempotent: a second close (or close after checkin) is a safe no-op, so
    # __aexit__ under an error path and an explicit close never double-fault.
    if self._detached:
        return
    self._detached = True
    with anyio.CancelScope(shield=True):
        try:
            await offload(self._reader.close, limiter=self._limiter)
        finally:
            # Clear the lifetime lock even if the offloaded close raised, so the
            # connection is never left permanently locked (EDGE-20). A body error
            # already on the stack chains via __context__ automatically.
            self._owner._reader_open = False  # noqa: SLF001

def __del__(self) -> None:
    # __del__ CANNOT await (D-29-15). If the reader was never closed, warn only —
    # actual C-stream release rides the pool reset event at checkin. Never create a
    # coroutine here (no self.close() call), which would raise the
    # "coroutine was never awaited" RuntimeWarning EDGE-22 forbids.
    if not self._detached:
        warnings.warn(
            f"{type(self).__name__} was not closed; use "
            "'async with await cursor.fetch_record_batch() as reader:'",
            ResourceWarning,
            stacklevel=2,
        )
```
`_detached` starts False in `__init__`; set True by `close()`. The happy path (closed via `__aexit__`) sets `_detached=True`, so `__del__` warns nothing (EDGE-23). An unclosed reader warns `ResourceWarning` and never touches a coroutine (EDGE-22).

### Anti-Patterns to Avoid
- **Subclassing `pyarrow.RecordBatchReader`** (D-29-01) — leaks sync `read_next_batch`/`__iter__`/`__next__` onto the loop, bypassing every guard. Compose.
- **Letting `StopIteration` propagate out of the worker** — becomes `RuntimeError` (probed). Always catch it worker-side.
- **Clearing `_reader_open` at iteration exhaustion** (D-29-11) — drained ≠ freed; only `close()`/checkin clears it.
- **Calling `self.close()` from `__del__`** — creates an un-awaited coroutine → `RuntimeWarning` (EDGE-22 violation).
- **Holding `_offloading()` across the `_reader_open = True` write** — `_reader_open` outlives the per-call span; keep them separate.
- **Aliasing the `read_next_batch` call through a lambda that re-imports `to_thread`** — irrelevant here (all offload goes through `_offload.py`), but keep `_pull` a plain module function so the guard's arity/attribute matching stays clean.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| End-of-stream detection | a bespoke "is drained" probe / peeking | worker-side `except StopIteration: return _EXHAUSTED` | `read_next_batch` already signals via `StopIteration`; peeking would double-pull |
| Read-after-checkin safety | weakref/`finalize`/registration | `_release_arrow_allocators` reset handler + native `ArrowInvalid` | D-29-12: the reset handler already closes the cursor; the driver raises cleanly |
| Cancel/abort on a pull | new cancel plumbing | `cancellable_offload(..., on_abort=owner.invalidate)` | Phase 25 machinery is drop-in; re-implementing risks the CR-01 race |
| Async-only closed-stream error | `ReaderClosedError` | native `pyarrow.lib.ArrowInvalid` | REQUIREMENTS non-goal: async mirrors the sync method's native errors |
| Off-loop dispatch | a raw `to_thread.run_sync` | `offload(...)` chokepoint | PKG-03 guard bans bare `to_thread`; single audited site (`_offload.py`) |

**Key insight:** almost nothing here is new. The reader is a structural copy of `AsyncCursor`; lifetime safety is a *policy* (set/clear a bool, lean on an existing reset handler), not a *mechanism*. The only novel code is ~10 lines of two-tier guard and the `__del__`/`_detached` warning discipline.

## Runtime State Inventory

This is a purely additive greenfield-within-a-package phase (new file + two small extensions); it renames/migrates nothing. Explicit per-category answer:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore keys, IDs, or collection names introduced or renamed. | none |
| Live service config | None — no external service configuration touched. | none |
| OS-registered state | None — no OS registrations. | none |
| Secrets/env vars | None new. (`SNOWFLAKE_ACCOUNT` is only monkeypatched in the existing cassette fixture — untouched.) | none |
| Build artifacts | None — no packaging/entry-point/`pyproject` change; `_reader.py` is picked up by the existing package glob. | none |

**Nothing found in any category — verified by inspecting the diff surface (one new module, two in-place method additions, one Protocol field). No rename, no migration.**

## Common Pitfalls

### Pitfall 1: `StopIteration` silently becoming `RuntimeError`
**What goes wrong:** letting the worker raise `StopIteration` at end-of-stream surfaces `RuntimeError("coroutine raised StopIteration")` to the user instead of terminating the `async for`.
**Why it happens:** PEP 479 / anyio wraps any `StopIteration` escaping a coroutine.
**How to avoid:** catch it in `_pull` and return `_EXHAUSTED`; raise `StopAsyncIteration` in `__anext__`.
**Warning signs:** a stream that "ends" with a `RuntimeError`; a hanging or mis-terminating `async for`.

### Pitfall 2: Releasing the lock at drain instead of close
**What goes wrong:** clearing `_reader_open` when `StopAsyncIteration` fires re-opens the concurrent-C-access hazard STREAM-06 forbids — the C-stream still sits on the cursor until `close()`.
**Why it happens:** intuition says "iterator exhausted ⇒ done."
**How to avoid:** only `close()`/checkin clears `_reader_open` (D-29-11). Document `async with` as canonical (D-29-18).
**Warning signs:** a concurrent op succeeding after a drained-but-unclosed reader; `checkedout()` accounting drift.

### Pitfall 3: `__del__` creating an un-awaited coroutine
**What goes wrong:** `__del__` calling `self.close()` (a coroutine) emits `RuntimeWarning: coroutine was never awaited`, failing EDGE-22.
**Why it happens:** the instinct to "clean up in the destructor."
**How to avoid:** `__del__` is warn-only (`ResourceWarning`); never call the async `close`. Real release rides the reset event.
**Warning signs:** `RuntimeWarning` in test output; a `<coroutine object ... close>` repr in a traceback.

### Pitfall 4: The reader firing the reader's own `adbc_cancel`
**What goes wrong:** `pyarrow.RecordBatchReader` has no `adbc_cancel`; the abort must target the owning **cursor**'s `adbc_cancel`.
**Why it happens:** copying `AsyncCursor._adbc_cancel` verbatim points at `self._cursor` — but the reader wraps a *reader*, not a cursor.
**How to avoid:** the reader must retain a reference to the sync **cursor** (or its `adbc_cancel`) for the abort hook. See Landmine 6 — this affects the constructor.
**Warning signs:** `AttributeError: 'RecordBatchReader' object has no attribute 'adbc_cancel'` on the cancel path.

### Pitfall 5: `_reader_open` set inside the creation `_offloading()` span
**What goes wrong:** setting `_reader_open=True` while still inside `_offloading()` (which holds `_in_use`) either dead-ends the exit (`_exit_offload` clears only `_in_use`, fine) or, if creation is cancelled, leaves `_reader_open` stuck True.
**How to avoid:** set `_reader_open=True` only *after* the `with self._owner._offloading():` block exits and only on the success path.
**Warning signs:** a connection permanently `ConnectionBusyError` after a cancelled `fetch_record_batch`.

## Code Examples

### End-of-stream probe result (VERIFIED, live)
```text
# pyarrow 24.0.0 + adbc_driver_duckdb, probed 2026-07-01
type: pyarrow.lib.RecordBatchReader        # mro: RecordBatchReader -> _Weakrefable -> object
schema type: Schema                        # .schema is a no-I/O property → sync passthrough
has __enter__/__exit__/close: True         # sync CM + close exist → replaced by async twins
END-OF-STREAM -> StopIteration args=()     # bare StopIteration, no message
read after reader.close()  -> pyarrow.lib.ArrowInvalid: Attempt to read from a stream that has already been closed
read after CURSOR  close() -> pyarrow.lib.ArrowInvalid: Attempt to read from a stream that has already been closed
reader is iterable: True   has __next__: True   # sync __iter__/__next__ present → replaced by __aiter__/__anext__
```

### StopIteration boundary probe (VERIFIED, live, both backends)
```text
--- asyncio ---  StopIteration -> RuntimeError: coroutine raised StopIteration
--- trio ---     StopIteration -> RuntimeError: coroutine raised StopIteration
```

### `_SyncReader` Protocol + `_SyncCursor` extension (D-29-17, PKG-01)
```python
# _reader.py  (mirrors _SyncCursor at _cursor.py:50-74)
class _SyncReader(Protocol):
    """Structural surface of the sync pyarrow.RecordBatchReader the async reader wraps."""
    @property
    def schema(self) -> pyarrow.Schema: ...
    def read_next_batch(self) -> pyarrow.RecordBatch: ...
    def close(self) -> None: ...

# _cursor.py — extend the existing _SyncCursor Protocol (add one line, PKG-01)
    def fetch_record_batch(self) -> pyarrow.RecordBatchReader: ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| materialize whole result (`fetch_arrow_table`) | stream via `RecordBatchReader` per-batch | this phase | lazy memory; but reader is cursor-bound → lifetime lock needed |
| per-call `_in_use` only | two-tier `_in_use` + `_reader_open` | this phase | closes the between-pulls concurrency gap (STREAM-06) |

**Deprecated/outdated:** none introduced. The `read_pandas`/`read_all` twins are deliberately *not* added (D-29-07) — not deprecated, just out of scope.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Snowflake cassette `fetch_record_batch` replays a real `RecordBatchReader` (the cassette was recorded for `snowflake_arrow_round_trip`) | EDGE-33 test map | If the recorded cassette lacks a streaming reader replay, the Snowflake leg of EDGE-33 may need a re-record; DuckDB leg is unaffected and fully verified. Planner should add a `checkpoint:human-verify` / early smoke on the Snowflake cassette. |

All other claims are `[VERIFIED]` by live probe against the installed stack or `[CITED]` from the actual source files (line-referenced). If A1's table is the only entry, no locked decision is at risk — only the Snowflake test-evidence path.

## Open Questions

1. **Snowflake cassette streaming replay (A1).**
   - What we know: `snowflake_async_pool` fixture (`tests/async/conftest.py`) replays `snowflake_arrow_round_trip` under `adbc_cassette`; the DuckDB EDGE-33 path is fully verified live.
   - What's unclear: whether the existing cassette recording includes a `fetch_record_batch`/reader interaction (vs. only `fetch_arrow_table`).
   - Recommendation: plan a Wave-0 smoke that opens the cassette pool and calls `fetch_record_batch`; if the cassette lacks the interaction, either re-record or scope the Snowflake EDGE-33 assertion to the read-after-checkin `ArrowInvalid` path that does not require live streaming rows. Do NOT block DuckDB coverage on it.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pyarrow | reader surface | ✓ | 24.0.0 | — |
| adbc_driver_manager | `fetch_record_batch` | ✓ | 1.11.0 | — |
| adbc_driver_duckdb | DuckDB test leg (EDGE-33) | ✓ | (import ok) | — |
| anyio | offload/cancel/shield | ✓ | (import ok) | — |
| adbc_driver_snowflake + cassette | Snowflake EDGE-33 leg | ? (fixture `importorskip`s) | — | skip cleanly; assert on `ArrowInvalid` path only (A1) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Snowflake driver/cassette — the fixture already `pytest.importorskip`s and `pytest.skip`s when absent, so CI stays green in a minimal env; DuckDB carries the mandatory coverage.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + `anyio` plugin (dual-backend via `@pytest.mark.anyio` + parametrized `anyio_backend` fixture) |
| Config file | `tests/async/conftest.py` (backend params, `duckdb_async_pool`, `snowflake_async_pool`, `make_stub_async_connection`) |
| Quick run command | `.venv/bin/pytest tests/async/test_reader_*.py -x -q` |
| Full suite command | `.venv/bin/pytest tests/async -q` then `.venv/bin/basedpyright` + `.venv/bin/python -c "from tests._async_harness.guard import scan_async_package; assert scan_async_package('src/adbc_poolhouse/_async/') == []"` |

Backends run under `@pytest.mark.anyio` with the `anyio_backend` fixture parametrized `["asyncio","trio"]` (trio leg gets a `MockClock(autojump_threshold=0)` for zero-wall-clock virtual deadlines). Concurrency/hang-prone tests must carry `tests.async._edge_helpers.concurrency_marks` (loop + timeout) — the MEMORY "loop flaky concurrency tests" discipline; single-shot passes miss ~33% deadlocks.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STREAM-01 | `fetch_record_batch` returns `AsyncRecordBatchReader`, creation offloaded off-loop | unit (stub) + integration (DuckDB) | `pytest tests/async/test_reader_stream.py -x` | ❌ Wave 0 |
| STREAM-02 | `async for` yields batches; each pull offloaded (thread-id ≠ loop, limiter bound) | integration (DuckDB) + stub | `pytest tests/async/test_reader_stream.py -x` | ❌ Wave 0 |
| STREAM-03 | `close`/`__aexit__` offloaded+shielded; frees before checkin | integration | `pytest tests/async/test_reader_close.py -x` | ❌ Wave 0 |
| STREAM-04 / EDGE-33 | read-after-checkin → native `ArrowInvalid`; drain-then-checkin → correct rows; DuckDB+Snowflake × asyncio+trio | integration (`duckdb_async_pool` + `snowflake_async_pool`) | `pytest tests/async/test_reader_lifetime.py -x` | ❌ Wave 0 |
| STREAM-05 | cancel/timeout pull → `adbc_cancel` once + invalidate; `checkedout()==0`; asyncio+trio | integration + stub (`BlockingStubCursor`) | `pytest tests/async/test_reader_cancel.py -x` | ❌ Wave 0 |
| STREAM-06 | second in-flight op while reader live → `ConnectionBusyError`; reader's own pulls exempt | stub (`make_stub_async_connection`) | `pytest tests/async/test_reader_busy.py -x` | ❌ Wave 0 |
| EDGE-20 | shielded-cleanup exception chains body via `__context__`, still releases/invalidates | stub (make `close` raise) | `pytest tests/async/test_reader_close.py::test_shielded_cleanup_chains -x` | ❌ Wave 0 |
| EDGE-22 | unclosed `__del__` → `ResourceWarning`, no `RuntimeWarning` | unit (`pytest.warns(ResourceWarning)` + `recwarn` asserts no `RuntimeWarning`) | `pytest tests/async/test_reader_resource.py -x` | ❌ Wave 0 |
| EDGE-23 | closed-via-CM happy path → neither warning | unit (`recwarn` empty) | `pytest tests/async/test_reader_resource.py -x` | ❌ Wave 0 |
| PKG-01 | `_SyncCursor.fetch_record_batch` + `_SyncReader` typed; strict 0 errors | static | `.venv/bin/basedpyright` | ✅ (basedpyright configured) |
| PKG-03 | import-lint guard green over `_async/` | static (existing guard) | `python -c "...scan_async_package('src/adbc_poolhouse/_async/')==[]"` | ✅ `tests/_async_harness/guard.py` |

**Key observables to assert (per CONTEXT):** `pool.checkedout() == 0` after a cancelled pull; exception class `pyarrow.lib.ArrowInvalid` (message "…stream that has already been closed") on read-after-checkin; `ResourceWarning` emitted / not emitted; `stub_cursor.adbc_cancel_call_count == 1`; `stub_conn.invalidate_call_count == 1` on cancel; `basedpyright` 0 errors; `scan_async_package(...) == []`.

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/async/test_reader_*.py -x -q`
- **Per wave merge:** `.venv/bin/pytest tests/async -q` + `.venv/bin/basedpyright`
- **Phase gate:** full `tests/async` green (looped for concurrency tests via `concurrency_marks`), `basedpyright` 0 errors, import-lint `[]`, `.venv/bin/mkdocs build --strict` (CLAUDE.md docs gate, phase ≥ 7).

### Wave 0 Gaps
- [ ] `tests/async/test_reader_stream.py` — STREAM-01/02 (creation + iteration, off-loop, limiter-bound)
- [ ] `tests/async/test_reader_close.py` — STREAM-03 + EDGE-20 (shielded close, `__context__` chaining)
- [ ] `tests/async/test_reader_lifetime.py` — STREAM-04/EDGE-33 (read-after-checkin `ArrowInvalid`, drain-then-checkin correct rows; DuckDB + Snowflake-cassette; extend `test_edge_resource.py` style)
- [ ] `tests/async/test_reader_cancel.py` — STREAM-05 (adbc_cancel-once + invalidate + `checkedout()==0`)
- [ ] `tests/async/test_reader_busy.py` — STREAM-06 (two-tier guard; reader-pull exemption)
- [ ] `tests/async/test_reader_resource.py` — EDGE-22/23 (`ResourceWarning`/`RuntimeWarning` discipline)
- [ ] Extend `BlockingStubCursor` (`tests/_async_harness/stubs.py`) with `fetch_record_batch()` returning a stub reader satisfying `_SyncReader` (a `schema` property, a `read_next_batch` that blocks-then-returns-batch / raises `StopIteration` on exhaustion, and `close`). Reuse the sticky-release + `entered`/`on_enter` gating so cancel/aliasing tests stay deterministic.
- [ ] No framework install needed — pytest/anyio present; `basedpyright` + import-lint guard already wired.

## Security Domain

`security_enforcement` is not disabled in config; but this phase adds no auth, no input parsing of untrusted data, no crypto, no network surface — it wraps an in-process Arrow C-stream. ASVS categories V2/V3/V4/V6 do not apply. V5 (input validation): the only inputs are already-typed method calls; no new user-string parsing. STRIDE: no new tampering/info-disclosure surface beyond what `fetch_arrow_table` already exposes. The one safety-relevant property (no use-after-free / segfault on read-after-checkin) is functionally validated by STREAM-04/EDGE-33 asserting a clean `ArrowInvalid` rather than a crash — that is the security-adjacent guarantee and it is covered in Validation Architecture.

## Sources

### Primary (HIGH confidence)
- Live probe, pyarrow 24.0.0 + adbc_driver_duckdb (`/tmp/claude/probe_reader.py`, ran 2026-07-01): `RecordBatchReader` surface, `StopIteration` end-of-stream, `ArrowInvalid` on read-after-close and read-after-cursor-close, iterator protocol presence.
- Live probe, anyio dual-backend (`/tmp/claude/probe_stopiter.py`): `StopIteration`→`RuntimeError("coroutine raised StopIteration")` under asyncio AND trio.
- `src/adbc_poolhouse/_async/_cursor.py:50-74,130-143,325-372` — `_SyncCursor`, `_adbc_cancel`, `fetch_arrow_table`, shielded `close` (copy templates).
- `src/adbc_poolhouse/_async/_connection.py:98-170,232-311` — `__init__`, `_enter/_exit/_offloading`, shielded `close`/`__aexit__`/`invalidate` (extension site).
- `src/adbc_poolhouse/_async/_cancel.py:41-47` — `cancellable_offload` signature (`on_abort=`) reused verbatim.
- `src/adbc_poolhouse/_async/_offload.py:41-109` — single `to_thread.run_sync` chokepoint.
- `src/adbc_poolhouse/_async/_pool.py:101-102` — fresh `AsyncConnection` per `connect()` (D-29-13 backstop).
- `src/adbc_poolhouse/_pool_factory.py:407-428` — `_release_arrow_allocators` reset handler (closes cursor → closes reader).
- `tests/_async_harness/guard.py:64-207` — import-lint rules (PKG-03).
- `tests/_async_harness/stubs.py` — `BlockingStubCursor` sticky-release harness to extend.
- `tests/async/conftest.py` — dual-backend fixture, `duckdb_async_pool`, `snowflake_async_pool` cassette, `make_stub_async_connection`.
- `tests/async/test_edge_resource.py`, `tests/async/test_stability_arrow.py` — lifetime-proof test templates.

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` / `.planning/ROADMAP.md` (Phase 29) — requirement text and success criteria.

### Tertiary (LOW confidence)
- Snowflake cassette streaming replay coverage (A1) — inferred from fixture, not probed (no Snowflake driver locally this session).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified by import; no new deps.
- Architecture (guards, sentinel, lifetime): HIGH — every pattern maps to a line-referenced existing idiom; the three risky behaviours probed live on both backends.
- Pitfalls: HIGH — each is grounded in a probe or an explicit source line.
- Snowflake EDGE-33 evidence path: LOW — cassette streaming replay unverified (A1); DuckDB path fully verified.

**Research date:** 2026-07-01
**Valid until:** 2026-07-31 (stable — pinned deps, in-repo patterns; re-probe if pyarrow or adbc_driver_manager is bumped)

## RESEARCH COMPLETE
