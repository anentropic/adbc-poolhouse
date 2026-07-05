# Phase 30: Async Bulk Write - Research

**Researched:** 2026-07-01
**Domain:** Async offload wrapper for ADBC bulk ingest — keyword-arg forwarding through a positional-variadic (`Unpack[_Ts]`) offload chokepoint
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-30-01:** `AsyncCursor.adbc_ingest` is a new method on the existing `AsyncCursor` in `src/adbc_poolhouse/_async/_cursor.py` — a byte-for-byte clone of the `fetch_arrow_table` offload shape (`_cursor.py:327`): one `with self._owner._offloading():` span wrapping a single `cancellable_offload(...)` that returns the driver's `int` row count. **No** new file, **no** reader class, **no** `_reader_open` lifetime lock — the connection checks back in the moment the offload completes.
- **D-30-02:** Return type is `int` (rows inserted, or driver-reported `-1` when the driver cannot count). Poolhouse returns it unchanged.
- **D-30-03:** The public API surfaces `mode`, `catalog_name`, `db_schema_name`, `temporary` as **keyword-only** (after `*`). The driver treats `mode` as positional-or-keyword and only the latter three as keyword-only; poolhouse tightens `mode` to keyword-only for a cleaner call site.
- **D-30-04:** `offload` / `cancellable_offload` forward arguments through a **positional variadic** (`Unpack[_Ts]`) and cannot forward keywords as written. Bind the arguments with **`functools.partial`** — wrap `self._cursor.adbc_ingest` into a zero-positional-arg partial closing over `table_name`, `data`, and the four keywords, then hand that partial to `cancellable_offload`. Do **not** widen the `offload`/`cancellable_offload` signature to accept `**kwargs`. (Researcher: confirm the partial-wrapped callable still cancels cleanly — `adbc_cancel` lives on the cursor object, unaffected by the partial — and does not trip the AST import-lint guard, PKG-03.)
- **D-30-05:** `mode: Literal["create", "append", "replace", "create_append"]`, default `"create"`, forwarded verbatim to the driver (no validation, no remapping). Docs MUST warn explicitly that `replace` **drops** the existing table.
- **D-30-06:** Type `data` as the precise Arrow union `pyarrow.RecordBatch | pyarrow.Table | pyarrow.RecordBatchReader | CapsuleType` — **not** `object`. This union probed **0 real diagnostics** under strict basedpyright (STACK.md:147); pyarrow members degrade to `Any`, so it stays strict-clean while self-documenting the accepted inputs. Poolhouse performs **zero conversion** — the Arrow object is handed to the driver untouched.
- **D-30-07:** `CapsuleType` is imported from `typing_extensions` under `TYPE_CHECKING` (matching ADBC's own choice; `types.CapsuleType` is 3.13+ only and the floor is 3.11).
- **D-30-08:** Extend the `_SyncCursor` structural Protocol (`_cursor.py:63`) with an `adbc_ingest(...) -> int` signature carrying the full argument union — exactly as `fetch_record_batch` was added in Phase 29. Keeps the async layer driver-agnostic and stub-testable; must stay basedpyright-strict-clean.
- **D-30-09:** Reuse `on_abort=self._owner.invalidate` (D-25-03) verbatim. A cancelled/timed-out ingest fires `adbc_cancel` once, invalidates the now-poisoned connection (shielded), and re-raises the cancellation, leaving `pool.checkedout() == 0` under asyncio and trio.
- **D-30-10:** `invalidate` recovers the **connection**; it does not and cannot roll back a **partially-applied write** in the database. That partial-table outcome is inherent to aborting mid-write and is **out of scope to fix** — document it, do not attempt compensation.
- **D-30-11:** `catalog_name`, `db_schema_name`, `temporary` are marked EXPERIMENTAL in the ADBC docstring (STACK.md:44). Surface them as-is with no added stability guarantee; note the EXPERIMENTAL status in the docstring.
- **D-30-12:** No sync-side `adbc_ingest` wrapper is added or needed. The sync surface is `create_pool`/`close_pool`/`managed_pool` returning a raw `sqlalchemy.pool.QueuePool`; sync users call native `adbc_ingest` on the raw ADBC cursor directly.

### Claude's Discretion
- Exact test-harness mechanism for a deterministic in-flight cancel (a blocking fake `adbc_ingest` on the stub cursor vs. a genuinely slow/large DuckDB ingest) — planner/researcher choose, following the Phase 23 harness precedent. **Research recommendation: extend `BlockingStubCursor` with a blocking `adbc_ingest` — see Pattern 2.**
- Docstring prose and Example-block wording (subject to the docs quality gate).

### Deferred Ideas (OUT OF SCOPE)
- `fetch_df` / `fetch_polars` DataFrame convenience — Phase 31 (independent read path; reuses this phase's whole-op offload shape, not its write semantics).
- P2 edge-hardening matrix (contextvars, trio-checkpoint, timeout precision, loop-shutdown, finalizers) extended across the ingest path — Phase 32.
- Any `[pandas]`/`[polars]`/`[dataframe]` extra — permanently ruled out (STACK.md:91); not this phase's concern.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGEST-01 | `await cursor.adbc_ingest(table_name, data, *, mode=..., catalog_name=None, db_schema_name=None, temporary=False)` returning the affected row count (single whole-operation offload) | Ground-truth driver signature verified (STACK.md:31, re-confirmed by introspection this session); `functools.partial` forwards the keyword-only args through `cancellable_offload`'s positional variadic — **verified strict-clean AND runtime-correct this session** (see Code Examples §1, Pattern 1). Clone of `fetch_arrow_table` at `_cursor.py:327`. |
| INGEST-02 | `mode` typed `Literal["create","append","replace","create_append"]` forwarded verbatim; docs warn `replace` **drops** the table | Real driver default is `"create"`; the four-member `Literal` matches the driver exactly (verified this session). Forwarded verbatim as a partial keyword. Docs mandate carried into DOCS-02 (Phase 33) but the docstring warning lands here. |
| INGEST-03 | `data` accepts `pyarrow.Table` / `RecordBatch` / `RecordBatchReader` / Arrow C-stream capsule without conversion | Precise union probed 0 diagnostics under strict basedpyright (STACK.md:147, re-verified). Pass-through: the partial closes over `data` untouched; DuckDB round-trip of a `pyarrow.Table` verified this session. |
| INGEST-04 | A cancelled/timed-out ingest fires `adbc_cancel` and **invalidates** the connection (`on_abort=invalidate`); `pool.checkedout()==0`, asyncio+trio parity | `cancellable_offload` already implements exactly this contract (`_cancel.py:41`); `adbc_cancel` lives on the cursor object and is passed as the 1st arg **unaffected by the partial** (verified: `cur.adbc_cancel` is a distinct bound method). Identical to `execute`/`fetch_arrow_table` (`_cursor.py:203/350`). |
</phase_requirements>

## Summary

Phase 30 adds a single method — `AsyncCursor.adbc_ingest` — that is a near-mechanical clone of the already-shipped `fetch_arrow_table` (`_cursor.py:327`). Both bracket the work in `with self._owner._offloading():` and dispatch a single `cancellable_offload(self._adbc_cancel, <callable>, ..., limiter=self._limiter, on_abort=self._owner.invalidate)`. A reviewer diffing the two methods should see only three differences: the callable (`functools.partial(self._cursor.adbc_ingest, ...)` vs. `self._cursor.fetch_arrow_table`), the return annotation (`int` vs. `pyarrow.Table`), and the docstring. There is **no** reader class and **no** `_reader_open` lifetime lock — unlike Phase 29, the operation is a single whole-op offload and the connection checks in the instant it returns. No new files, no signature changes to `_offload.py`/`_cancel.py`/`_connection.py`, no new runtime deps.

The phase's one genuinely new wrinkle — forwarding four **keyword-only** public arguments through the **positional-variadic** (`Unpack[_Ts]`) offload chokepoint — is fully resolved and **empirically verified this session**. `cancellable_offload(adbc_cancel, fn, *args, ...)` cannot forward keywords, but a `functools.partial` that binds `table_name`, `data`, and all four keywords into a **zero-positional-arg** callable satisfies `Callable[[Unpack[_Ts]], _T]` with `_Ts` inferred empty. This construct is (a) **strict-basedpyright-clean: 0 errors, 0 warnings** on the exact `partial + cancellable_offload + CapsuleType` shape; (b) **runtime-correct**: an actual DuckDB `create`+`append` round-trip returned the right `int` row counts; (c) **guard-clean**: `scan_async_package` returns `[]` for a file using `functools.partial` (PKG-03 forbids only `import asyncio`, unlimited `to_thread.run_sync`, and `asyncio.CancelledError` — never `functools`); and (d) **cancel-safe**: `adbc_cancel` is a separate bound method on the cursor object, wholly unaffected by wrapping `adbc_ingest` in a partial, so the existing abort/invalidate contract carries over unchanged.

**Primary recommendation:** Clone `fetch_arrow_table`, replace its callable with `functools.partial(self._cursor.adbc_ingest, table_name, data, mode=mode, catalog_name=catalog_name, db_schema_name=db_schema_name, temporary=temporary)`, annotate `-> int`, add `import functools` at module top, extend the `_SyncCursor` Protocol with the full `adbc_ingest` signature and add `CapsuleType` under the existing `TYPE_CHECKING` block. Follow the Phase 29 RED-first TDD rhythm (Protocol/signature test → DuckDB round-trip + mode-forwarding + pass-through tests → cancel/invalidate parity test on an extended `BlockingStubCursor`). No new production machinery.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bulk-write dispatch (offload the blocking C ingest off the loop) | Async wrapper (`AsyncCursor.adbc_ingest`) | Offload chokepoint (`_offload.offload`) | The only reason this method exists is that the native call blocks the event loop; the async layer wraps every cursor method for exactly this reason (CONTEXT domain). |
| Keyword→positional argument binding | Async wrapper (`functools.partial` at the call site) | — | `cancellable_offload` is positional-variadic by design (CR-01 arity contract); binding belongs at the caller, never by widening the shared chokepoint (D-30-04). |
| Actual bulk write / row counting / mode semantics | Driver (native `dbapi.Cursor.adbc_ingest`) | — | Poolhouse does zero conversion and no validation; the driver owns `create`/`append`/`replace`/`create_append` and the `-1` fallback (D-30-02/05/06). |
| Cancel + poison recovery | `cancellable_offload` watcher + `AsyncConnection.invalidate` | Driver `adbc_cancel` | Reused verbatim from Phase 25/29; the abort path is a cursor-object concern, not an ingest-specific one (D-30-09). |
| Concurrency rejection (`ConnectionBusyError`) | `AsyncConnection._offloading()` per-call `_in_use` guard | — | A whole-op ingest takes only the per-call tier; it never sets `_reader_open` (D-30-01 — no reader lifetime lock). |
| Sync-side bulk write | Driver (raw ADBC cursor via `QueuePool`) | — | The sync surface is a pool factory; there is no sync cursor wrapper to extend (D-30-12). |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `adbc-driver-manager` | `>=1.8.0` (installed `1.11.0`) | Provides native `dbapi.Cursor.adbc_ingest` | Already a core dep; method present well before the floor. Re-verified this session: signature matches STACK.md byte-for-byte. |
| `pyarrow` | `>=23.0.1` (installed `24.0.0`, core dep) | The `data` union member types (`Table`/`RecordBatch`/`RecordBatchReader`) | Already core; placeholder `py.typed` stub makes members degrade to `Any` → strict-clean annotations, no third-party stubs. |
| `anyio` | `>=4.13` (`[async]`, installed `4.14.1`) | Unchanged offload/limiter/cancel plumbing (`offload`, `cancellable_offload`) | Reused verbatim; no new anyio surface. |
| `functools` (stdlib) | — | `functools.partial` to bind ingest args into a zero-positional-arg callable | Stdlib; the canonical keyword→positional binding tool; guard-neutral. |
| `typing_extensions` | transitive (via anyio/pydantic) | `CapsuleType` under `TYPE_CHECKING` only | Matches ADBC's own import choice; `types.CapsuleType` is 3.13+, floor is 3.11. **Not** a direct runtime dep. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `adbc-driver-duckdb` | installed | Live round-trip test backend (`ingest → SELECT count(*)`) | Round-trip verification (INGEST-01/03) and the "genuinely slow ingest" cancel alternative (not recommended — see Pattern 2). |
| `trio` | `0.33.0` (dev) | asyncio+trio parity leg of every test | INGEST-04 parity; every async test runs under both backends via `anyio_backend_name`. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `functools.partial` binding at the call site | Widen `offload`/`cancellable_offload` to accept `**kwargs` | **Rejected by D-30-04.** Would touch the audited chokepoint, complicate the CR-01 arity contract, and add `**kwargs` to a signature every method shares. The partial is local, zero-cost, and verified clean. |
| `functools.partial` | An inline `lambda: self._cursor.adbc_ingest(table_name, data, mode=mode, ...)` | A lambda works at runtime and is guard-clean, but `partial` is the idiom SUMMARY.md:114 and the `fetchmany` comment (`_cursor.py:288`) point to, keeps `adbc_cancel` attribution obvious, and reads as "bind these args." Prefer `partial`. |
| Precise `data` union | `data: object` | `object` is also strict-clean but discards self-documentation; D-30-06 mandates the union (0 diagnostics, degrades to `Any`). |
| Extended `BlockingStubCursor.adbc_ingest` | A genuinely slow/large DuckDB ingest for the cancel test | Non-deterministic; a real ingest may finish before the cancel fires (flaky). The Phase 23 blocking-gate stub is deterministic. Recommend the stub (Pattern 2). |

**Installation:**
```bash
# No install changes. All deps already present. Verify only:
.venv/bin/python -c "import functools; import adbc_driver_manager.dbapi as d; import inspect; print(inspect.signature(d.Cursor.adbc_ingest))"
```

**Version verification (this session):**
```text
adbc-driver-manager  installed 1.11.0  — adbc_ingest signature matches STACK.md exactly ✓
pyarrow              installed 24.0.0  — placeholder py.typed stub; union → Any (strict-clean) ✓
anyio                installed 4.14.1  — offload/cancellable_offload unchanged ✓
functools            stdlib             — partial verified strict-clean + runtime-correct ✓
```

## Package Legitimacy Audit

> No external packages are installed by this phase. Every dependency is already present in the repo (`adbc-driver-manager`, `pyarrow`, `anyio` are shipped deps; `functools`/`typing` are stdlib; `typing_extensions` is transitive). No `npm`/`pip`/`cargo install` occurs.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none — no new installs)* | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
await cursor.adbc_ingest(table_name, data, *, mode, catalog_name, db_schema_name, temporary)
        │
        │  (loop thread)
        ▼
  with self._owner._offloading():          ── per-call _in_use guard (foreign caller → ConnectionBusyError)
        │                                     NOTE: does NOT set _reader_open (no reader lifetime lock)
        ▼
  bound = functools.partial(               ── binds all 6 args into a ZERO-positional-arg callable
      self._cursor.adbc_ingest,               (keyword-only args captured here, NOT forwarded through offload)
      table_name, data,
      mode=mode, catalog_name=…, db_schema_name=…, temporary=…)
        │
        ▼
  await cancellable_offload(                ── watcher task + worker task (anyio task group)
      self._adbc_cancel,   ◄──────────────┐   1st arg: cursor.adbc_cancel bound method
      bound,                               │            (SEPARATE from the partial — unaffected)
      limiter=self._limiter,               │
      on_abort=self._owner.invalidate)     │
        │                                  │
        ├─ success path ──► worker: offload → to_thread.run_sync(lambda: bound()) ─► driver adbc_ingest ─► int
        │                                                                                    │
        │                                                                          returns rows (or -1)
        │                                                                                    ▼
        │                                                            connection checks in immediately (no lock held)
        │
        └─ cancel/timeout path ──► watcher fires adbc_cancel() ONCE (shielded)
                                     ├─ worker's in-flight C call aborts (driver raises interrupt)
                                     ├─ await on_abort() = invalidate() → drops poisoned conn, checkedout()→0
                                     └─ re-raise the framework cancellation (never returns a value)
```

The partial is the entire novelty. Everything downstream of it (`cancellable_offload`, `offload`, the watcher/worker task group, `invalidate`) is Phase 25/29 machinery reused verbatim.

### Recommended Project Structure

```
src/adbc_poolhouse/_async/
├── _cursor.py        # MODIFY ONLY: add `import functools`; add `CapsuleType`+`Literal` under TYPE_CHECKING;
│                     #   extend _SyncCursor Protocol with adbc_ingest(...) -> int; add AsyncCursor.adbc_ingest
├── _cancel.py        # UNCHANGED (cancellable_offload reused)
├── _offload.py       # UNCHANGED (offload reused; audited chokepoint untouched)
├── _connection.py    # UNCHANGED (_offloading()/_in_use/invalidate reused as-is)
└── _reader.py        # UNTOUCHED (no reader involved)

tests/async/
├── test_ingest_*.py          # NEW: round-trip (DuckDB), mode forwarding, data pass-through
├── test_ingest_cancel.py     # NEW: in-flight cancel → adbc_cancel once + invalidate + checkedout()==0 (asyncio+trio)
tests/_async_harness/
└── stubs.py                  # MODIFY: add BlockingStubCursor.adbc_ingest (blocking gate) + call counters
```

### Pattern 1: Keyword-only args through the positional-variadic offload via `functools.partial`

**What:** Bind `table_name`, `data`, and the four keyword-only args into a zero-positional-arg partial, then pass the partial as the `fn` to `cancellable_offload`. `_Ts` is inferred empty; the offload's `lambda: fn(*args)` calls `bound()`.
**When to use:** Any time an offloaded call needs keyword arguments — this is the milestone-general answer (SUMMARY.md:114 flagged it as the Phase 2 open question; now resolved).
**Example:**
```python
# Source: verified strict-clean (0 errors) AND runtime-correct against DuckDB, this session.
# Clone of fetch_arrow_table (src/adbc_poolhouse/_async/_cursor.py:327).
async def adbc_ingest(
    self,
    table_name: str,
    data: pyarrow.RecordBatch | pyarrow.Table | pyarrow.RecordBatchReader | CapsuleType,
    *,
    mode: Literal["create", "append", "replace", "create_append"] = "create",
    catalog_name: str | None = None,
    db_schema_name: str | None = None,
    temporary: bool = False,
) -> int:
    with self._owner._offloading():  # noqa: SLF001 (intentional parent guard)
        return await cancellable_offload(
            self._adbc_cancel,
            functools.partial(
                self._cursor.adbc_ingest,
                table_name,
                data,
                mode=mode,
                catalog_name=catalog_name,
                db_schema_name=db_schema_name,
                temporary=temporary,
            ),
            limiter=self._limiter,
            on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
        )
```

### Pattern 2: Deterministic in-flight cancel via a blocking `BlockingStubCursor.adbc_ingest`

**What:** Extend the Phase 23 `BlockingStubCursor` (`tests/_async_harness/stubs.py`) with an `adbc_ingest` that records the call under the lock, then calls the existing `self._block()` gate — exactly as `execute`/`fetch_arrow_table` do. The stub's existing `adbc_cancel`/`release`/`close` sticky-release machinery already unblocks it.
**When to use:** The INGEST-04 cancel/invalidate parity test. A blocking stub is deterministic; a "genuinely slow DuckDB ingest" can finish before the cancel fires (flaky) — reject it.
**Example:**
```python
# Source: mirror BlockingStubCursor.fetch_arrow_table (stubs.py:301) and execute (stubs.py:287).
def adbc_ingest(
    self,
    table_name: str,
    data: object,
    mode: str = "create",
    *,
    catalog_name: str | None = None,
    db_schema_name: str | None = None,
    temporary: bool = False,
) -> int:
    """Record the ingest call, block until released/cancelled, then return a row count."""
    del table_name, data, mode, catalog_name, db_schema_name, temporary
    with self._lock:
        self.ingest_call_count += 1
    self._block()  # sticky-release gate — adbc_cancel/close/release unblock it (Phase 23 idiom)
    return 3
```
The test then gates on `cursor.entered`, cancels the surrounding scope (`move_on_after(0)` / `fail_after`), and asserts `cursor.adbc_cancel_call_count == 1`, the connection was invalidated, and `pool.checkedout() == 0` — under both `anyio_backend_name` values. This mirrors `tests/async/test_edge_cancel_onabort_failure.py` verbatim, swapping the blocked call from `execute`/`fetch` to `adbc_ingest`.

### Pattern 3: `_SyncCursor` Protocol extension (PKG-01 parity)

**What:** Add the full `adbc_ingest` signature to the structural Protocol at `_cursor.py:63`, mirroring how `fetch_record_batch` was added in Phase 29.
**When to use:** Required so the async layer stays driver-agnostic and the `BlockingStubCursor` structurally satisfies it.
**Example:**
```python
# Source: STACK.md:133 (probed 0 real diagnostics under strict basedpyright); re-verified this session.
class _SyncCursor(Protocol):
    ...  # existing members
    def adbc_ingest(
        self,
        table_name: str,
        data: pyarrow.RecordBatch | pyarrow.Table | pyarrow.RecordBatchReader | CapsuleType,
        mode: Literal["append", "create", "replace", "create_append"] = ...,
        *,
        catalog_name: str | None = ...,
        db_schema_name: str | None = ...,
        temporary: bool = ...,
    ) -> int: ...
```
Note the Protocol keeps `mode` as positional-or-keyword (matching the *driver*); only the *public* `AsyncCursor.adbc_ingest` tightens `mode` to keyword-only (D-30-03). Add `CapsuleType` and `Literal` to the existing `TYPE_CHECKING` block in the same file (`Literal` from `typing`, `CapsuleType` from `typing_extensions`).

### Anti-Patterns to Avoid

- **Widening `offload`/`cancellable_offload` with `**kwargs`:** Explicitly rejected (D-30-04). Touches the audited chokepoint and the CR-01 arity contract. Bind at the call site instead.
- **A reader lifetime lock (`_reader_open`) for ingest:** This is a whole-op offload; the connection checks in immediately. Setting `_reader_open` would permanently poison the connection. Do NOT copy the Phase 29 `_reader_open` set — copy only the `fetch_arrow_table` shape (which does NOT set it).
- **Validating or remapping `mode`:** Forward the `Literal` verbatim (D-30-05). The type checker enforces the four members statically; the driver owns semantics.
- **Converting or type-checking `data` at runtime:** Pure pass-through (D-30-06); the driver's Arrow binding raises clearly on bad input (EDGE-17: never caught or wrapped).
- **Catching the driver's error:** The single offload chokepoint re-raises native errors (`ProgrammingError` before `execute`, `AdbcError` on a bad ingest) with exact type/traceback (EDGE-17). Do not add `try/except`.
- **Attempting to roll back a partial write on cancel:** `invalidate` recovers the *connection*, not the *table* (D-30-10). Document the non-atomicity; do not build compensation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Keyword→positional argument binding | A hand-rolled tuple-spread / two-arm branch (like `fetchmany`) | `functools.partial` | With four keyword args a branch matrix is unmanageable; `partial` binds all six args in one call, strict-clean and guard-neutral (verified). |
| Cooperative cancel of a blocking C call | A bespoke watcher/abort task | `cancellable_offload` (`_cancel.py:41`) | Already implements the watcher/worker task group, the shielded once-only `adbc_cancel`, the `aborted_by_us` flag, and the WR-01..04 re-raise contract. |
| Poison recovery after a cancelled write | A manual `fairy.invalidate()` call | `on_abort=self._owner.invalidate` | The dedicated teardown limiter (WR-03) and shielded checkin are already wired; passing `invalidate` reuses all of it. |
| Concurrency rejection | A new lock | `self._owner._offloading()` | The `_in_use` check-and-set guard already yields `ConnectionBusyError` race-free on the single-threaded loop. |
| `CapsuleType` on 3.11 | A local capsule shim | `typing_extensions.CapsuleType` under `TYPE_CHECKING` | Matches ADBC; zero runtime cost; `types.CapsuleType` is 3.13+ only. |

**Key insight:** This phase is deliberately *not* novel. Every hard part (cancel, invalidate, offload discipline, concurrency guard, Arrow typing) was solved in Phases 24/25/29. The only new code is one method body and one Protocol line; the only new *idea* is `functools.partial`, and it is verified.

## Common Pitfalls

### Pitfall 1: Copying the `_reader_open` set from `fetch_record_batch` instead of the `fetch_arrow_table` shape
**What goes wrong:** If the implementer clones `fetch_record_batch` (`_cursor.py:357`) rather than `fetch_arrow_table` (`_cursor.py:327`), they inherit `self._owner._reader_open = True`, permanently locking the connection — every subsequent op raises `ConnectionBusyError` and the connection never fully checks in.
**Why it happens:** Both are "the newest methods"; Phase 29 is the most recent precedent.
**How to avoid:** D-30-01 is explicit — clone `fetch_arrow_table`. The diff between the two new methods is only callable/return-type/docstring. No `_reader_open`, no `AsyncRecordBatchReader`.
**Warning signs:** A second op after an ingest raising `ConnectionBusyError`; `checkedout()` not returning to 0 on the happy path.

### Pitfall 2: Passing the partial where `adbc_cancel` belongs (or vice versa)
**What goes wrong:** `cancellable_offload`'s **first** positional arg is `adbc_cancel` (the abort hook), the **second** is `fn` (the work). Swapping them means the abort path calls the ingest and the worker calls the cancel hook.
**Why it happens:** Two callables adjacent in the call.
**How to avoid:** Follow Pattern 1 exactly: 1st arg `self._adbc_cancel`, 2nd arg the `functools.partial(...)`. `self._adbc_cancel` is the cursor's own bound method (`_cursor.py:132`) and is **unaffected by the partial** — the partial wraps `adbc_ingest`, a different attribute. Verified this session: `cur.adbc_cancel` remains a distinct callable regardless of the partial.
**Warning signs:** Cancel test hangs (worker never aborts) or `adbc_cancel_call_count` stays 0.

### Pitfall 3: Forgetting `import functools` at module top
**What goes wrong:** `NameError: functools` at first ingest, or (if added under `TYPE_CHECKING`) a runtime failure since `partial` is used at runtime, not just in annotations.
**Why it happens:** The module currently imports only `anyio` at runtime; `functools` is new.
**How to avoid:** Add `import functools` to the **runtime** import block (not `TYPE_CHECKING`). `Literal` also moves to a runtime-or-TYPE_CHECKING position depending on usage; since `Literal` appears in a runtime default annotation with `from __future__ import annotations` (already present at `_cursor.py:31`), it can stay under `TYPE_CHECKING`. `functools.partial` is called at runtime → must be a runtime import.
**Warning signs:** basedpyright `reportUndefinedVariable`, or `NameError` at first call.

### Pitfall 4: `replace` mode silently drops the table with no warning in docs
**What goes wrong:** A user calls `mode="replace"` expecting an upsert/merge and loses the existing table's data.
**Why it happens:** ADBC's `replace` is drop-then-create; the name suggests row-level replacement.
**How to avoid:** INGEST-02 / D-30-05 mandate an explicit docstring warning: "`replace` **drops** the existing table and recreates it." The mode table belongs in the docstring here and in the guide (DOCS-02, Phase 33).
**Warning signs:** Review comment noting missing warning; `mkdocs build --strict` will not catch this (it is a prose requirement, gated by the docs-author humanizer/quality pass).

### Pitfall 5: Treating a cancelled ingest as if the table is clean
**What goes wrong:** Documentation or tests imply that after cancel+invalidate the database is unchanged. A partially-applied bulk load can leave rows written.
**Why it happens:** `invalidate` recovers the *connection*; users conflate that with transactional rollback.
**How to avoid:** D-30-10 — document the non-atomicity explicitly; do not attempt compensation. The test asserts connection-level recovery (`checkedout()==0`, `invalidate` fired), **not** table state after a partial write.
**Warning signs:** A test asserting row counts after a *cancelled* ingest (out of scope — only assert connection recovery).

## Common Operations (Code Examples)

### 1. The exact `functools.partial` + `cancellable_offload` call (verified strict-clean + runtime-correct)
```python
# Source: verified this session — basedpyright strict on the exact shape → "0 errors, 0 warnings, 0 notes";
# and a live DuckDB round-trip (create then append) returned int row counts 3 and 3.
bound = functools.partial(
    self._cursor.adbc_ingest,
    table_name,
    data,
    mode=mode,
    catalog_name=catalog_name,
    db_schema_name=db_schema_name,
    temporary=temporary,
)
return await cancellable_offload(
    self._adbc_cancel, bound, limiter=self._limiter, on_abort=self._owner.invalidate,
)
```

### 2. DuckDB round-trip verification (INGEST-01/03)
```python
# Source: run live this session against adbc_driver_duckdb — round-trip confirmed.
import pyarrow as pa
tbl = pa.table({"id": [1, 2, 3], "name": ["a", "b", "c"]})
n = await cursor.adbc_ingest("people", tbl, mode="create")   # -> 3
await cursor.execute("SELECT count(*) FROM people")
assert (await cursor.fetchone())[0] == 3
n2 = await cursor.adbc_ingest("people", tbl, mode="append")  # -> 3
await cursor.execute("SELECT count(*) FROM people")
assert (await cursor.fetchone())[0] == 6
```

### 3. Cancel-path assertion shape (INGEST-04, mirrors test_edge_cancel_onabort_failure.py)
```python
# Source: mirror tests/async/test_edge_cancel_onabort_failure.py, swapping execute→adbc_ingest.
# Under both anyio_backend_name values:
with anyio.move_on_after(0):            # or fail_after; gate on stub.entered first for determinism
    await cursor.adbc_ingest("t", data, mode="create")
assert stub.adbc_cancel_call_count == 1     # fired exactly once
assert pool.checkedout() == 0               # invalidate dropped the poisoned connection
```

## Runtime State Inventory

> Not applicable — this is a greenfield method addition (new code path), not a rename/refactor/migration. No stored data, live-service config, OS-registered state, secrets, or build artifacts carry any string this phase changes.

**Nothing found in any category:** None — verified: the phase adds one method + one Protocol line + one stub method; it renames nothing and migrates no persisted state.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Open question: how to pass keyword args through the `TypeVarTuple` offload boundary (SUMMARY.md:114 — "the `fetchmany` two-arm pattern or a `functools.partial`/lambda") | Resolved: `functools.partial` binds all args into a zero-positional-arg callable; verified strict-clean + runtime-correct + guard-clean | Phase 30 (this research) | The `fetchmany` two-arm branch (`_cursor.py:289`) does NOT generalize to four keyword args; `partial` is the general answer for the whole milestone (also relevant to any future keyword-bearing offload). |

**Deprecated/outdated:**
- The `fetchmany` explicit two-arm pattern (`_cursor.py:289`) is correct for its *single optional positional* arg but must NOT be imitated for `adbc_ingest`'s four keyword args — use `partial`.

## Assumptions Log

> Every load-bearing claim in this research was verified against the installed `.venv` (introspection), a live basedpyright strict probe, a live `scan_async_package` guard run, and a live DuckDB round-trip this session — or cited from `STACK.md`/`SUMMARY.md` (themselves HIGH-confidence, `.venv`-grounded project docs).

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Per-backend transactional recovery after a cancelled `adbc_ingest` is driver-dependent, not spec-guaranteed (partial write may persist) | Pitfall 5 / D-30-10 | LOW — already scoped OUT (document, don't fix). The connection-recovery assertion (`checkedout()==0`) is backend-independent and IS tested. Only table-state-after-cancel is undefined, and we assert nothing about it. |

**All other claims verified or cited — no user confirmation needed.** Specifically, the five open confirmations the orchestrator flagged are all resolved with HIGH confidence:
1. Partial-wrapped callable cancels cleanly + does NOT trip PKG-03 — **verified** (`adbc_cancel` is a separate bound method; `scan_async_package` returns `[]` for `functools.partial`).
2. Exact `cancellable_offload` call shape; no `**kwargs` widening needed — **verified** (zero-positional-arg partial satisfies `Unpack[_Ts]` with `_Ts` empty; strict-clean).
3. Deterministic cancel harness — **recommended**: extend `BlockingStubCursor.adbc_ingest` (Pattern 2), reject slow-DuckDB.
4. Exact driver signature / `data` union / `-1` / EXPERIMENTAL keywords — **verified** (introspection matches STACK.md).
5. `CapsuleType` from `typing_extensions` under `TYPE_CHECKING`, strict-clean — **verified** (0 errors in the probe).
6. Round-trip approach — **verified** (live DuckDB `create`+`append` round-trip).

## Open Questions

None blocking. All six orchestrator-flagged confirmations are resolved above with empirical verification. One residual, already-scoped item:

1. **Which backends leave a partial table on a cancelled ingest?**
   - What we know: DuckDB (in-memory, tested) and networked backends may differ; the connection is always recovered via `invalidate`.
   - What's unclear: exact per-backend table state after a mid-ingest abort.
   - Recommendation: Do not investigate (D-30-10 scopes it OUT). Document the non-atomicity caveat; assert only connection recovery.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `adbc-driver-manager` | Native `adbc_ingest` | ✓ | 1.11.0 | — |
| `pyarrow` | `data` union / round-trip fixtures | ✓ | 24.0.0 | — |
| `anyio` | offload/cancel plumbing | ✓ | 4.14.1 | — |
| `adbc-driver-duckdb` | Live round-trip test backend | ✓ | installed | Stub-only tests (but round-trip is the strongest INGEST-01/03 proof — keep DuckDB) |
| `trio` | asyncio+trio parity leg | ✓ | 0.33.0 | — |
| `functools` (stdlib) | `partial` | ✓ | stdlib | — |
| `typing_extensions` | `CapsuleType` (TYPE_CHECKING) | ✓ | transitive | — |
| `.venv/bin/basedpyright` | strict type gate | ✓ | 1.39.5 | — |
| `.venv/bin/mkdocs` | `--strict` docs gate (CLAUDE.md, phase ≥ 7) | ✓ | installed | — |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** none

## Validation Architecture

> `workflow.nyquist_validation` is `true` — this section is included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + anyio plugin (asyncio + trio backends via `anyio_backend_name`) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `.venv/bin/pytest tests/async/test_ingest_*.py -x -q` |
| Full suite command | `.venv/bin/pytest tests/async -q && .venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py && .venv/bin/pytest tests/test_pkg_import_guard.py tests/async/test_async_guard.py -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INGEST-01 | `adbc_ingest` returns the driver `int` row count; single whole-op offload; connection checks in immediately | integration (DuckDB) | `.venv/bin/pytest tests/async/test_ingest_roundtrip.py -x` | ❌ Wave 0 |
| INGEST-01 | `_SyncCursor` Protocol carries `adbc_ingest`; public method is keyword-only; strict-clean | unit + typecheck | `.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py` | ❌ Wave 0 |
| INGEST-02 | `mode` forwarded verbatim; each of the four `Literal` modes reaches the driver (esp. `replace`=drop, `create_append`) | integration (DuckDB) | `.venv/bin/pytest tests/async/test_ingest_modes.py -x` | ❌ Wave 0 |
| INGEST-03 | `data` pass-through: a `pyarrow.Table` (and `RecordBatch`) ingests and round-trips unchanged; zero conversion | integration (DuckDB) | `.venv/bin/pytest tests/async/test_ingest_roundtrip.py::test_data_passthrough -x` | ❌ Wave 0 |
| INGEST-04 | In-flight cancel → `adbc_cancel` fires once + `invalidate` + `checkedout()==0`; asyncio AND trio | unit (BlockingStubCursor) | `.venv/bin/pytest tests/async/test_ingest_cancel.py -x` (run in a loop, both backends) | ❌ Wave 0 |
| PKG-03 (re-verify) | Guard passes over `_async/` with `functools.partial` present | guard | `.venv/bin/pytest tests/test_pkg_import_guard.py tests/async/test_async_guard.py -q` | ✅ exists (re-run) |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/async/test_ingest_*.py -x -q && .venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py`
- **Per wave merge:** `.venv/bin/pytest tests/async -q` (full async suite — no existing call site regressed)
- **Phase gate:** Full suite green + `basedpyright` 0 errors + guard `[]` + `.venv/bin/mkdocs build --strict` (docs gate, CLAUDE.md phase ≥ 7) before `/gsd-verify-work`
- **Concurrency-test hygiene (MEMORY):** run `test_ingest_cancel.py` in a **loop** (e.g. `--count=20` via `pytest-repeat`), not once — single-shot verification missed a ~33% deadlock in Phase 23. Use `rc=$?` + grep for the pass line, never `if ! cmd` in a zsh for-loop (zsh `!` quirk).

### Wave 0 Gaps
- [ ] `tests/async/test_ingest_roundtrip.py` — covers INGEST-01, INGEST-03 (DuckDB create/append round-trip + data pass-through)
- [ ] `tests/async/test_ingest_modes.py` — covers INGEST-02 (all four modes; `replace`=drop, `create_append` semantics)
- [ ] `tests/async/test_ingest_cancel.py` — covers INGEST-04 (cancel → adbc_cancel once + invalidate + checkedout()==0, asyncio+trio, looped)
- [ ] `tests/_async_harness/stubs.py` — add `BlockingStubCursor.adbc_ingest` (blocking gate + `ingest_call_count`) — Pattern 2
- [ ] `tests/async/test_ingest_signature.py` (or fold into an existing signature test) — asserts the `_SyncCursor` Protocol + public keyword-only signature under basedpyright strict

*(No conftest/fixture gaps: existing `tests/async/conftest.py` already exposes `BlockingStubCursor`, the anyio backend param, and DuckDB pool fixtures used by the Phase 29 read-path round-trip tests.)*

## Security Domain

> `security_enforcement` is absent in config (= enabled). Included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface; the connection is already authenticated by the pool config (upstream). |
| V3 Session Management | no | No sessions; per-call transient-token model. |
| V4 Access Control | no | No access-control logic in poolhouse; the driver/DB enforces it. |
| V5 Input Validation | partial (by design: none added) | `data`/`mode`/`table_name` are pass-through to the driver, which validates and raises native errors (EDGE-17). poolhouse deliberately adds NO validation (D-30-05/06) — the driver is the trust anchor for Arrow binding and SQL identifiers. |
| V6 Cryptography | no | No crypto in this path. |
| V7 Error Handling & Logging | yes | Native driver errors propagate unchanged with exact type/traceback (EDGE-17); no swallowing, no re-wrapping — auditable failure surface. |

### Known Threat Patterns for the async ingest path

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| `table_name` as an untrusted identifier (potential injection if a caller interpolates user input) | Tampering | poolhouse passes `table_name` straight to the driver's `adbc_ingest`, which handles identifier binding; poolhouse does not construct SQL. Caller-side responsibility, consistent with the whole library's pass-through charter. Document that `table_name` is a driver-level identifier, not sanitized by poolhouse. |
| Concurrent C access to one connection (memory corruption) | Tampering | `_offloading()` per-call `_in_use` guard rejects a second in-flight op with `ConnectionBusyError` — race-free on the single-threaded loop. |
| Poisoned connection returned to the pool after a cancelled mid-write | Denial of Service (pool starvation) | `on_abort=self._owner.invalidate` drops the poisoned connection (shielded), `checkedout()→0` — the pool is never poisoned (INGEST-04). |
| Abort-the-abort (double cancellation during recovery) | Tampering | `cancellable_offload` fires `adbc_cancel` once inside `CancelScope(shield=True)` (D-25-07) — reused verbatim, no new surface. |
| Supply-chain (new package) | Tampering | None — no packages installed this phase (Package Legitimacy Audit: none). |

No new production machinery is introduced beyond one method body and one Protocol line, so this phase adds **no new attack surface** — it inherits the Phase 25/29 cancel/invalidate/guard mitigations verbatim.

## Sources

### Primary (HIGH confidence)
- Installed-package introspection this session: `.venv/bin/python -c "import inspect, adbc_driver_manager.dbapi as d; print(inspect.signature(d.Cursor.adbc_ingest))"` — signature matches STACK.md byte-for-byte.
- Live basedpyright strict probe this session on the exact `functools.partial + cancellable_offload + CapsuleType + _SyncCursor` shape → **"0 errors, 0 warnings, 0 notes"**.
- Live `scan_async_package` run this session over a `functools.partial` file → `[]` (guard passes; PKG-03 clean), and over real `src/adbc_poolhouse/_async` → `[]`.
- Live DuckDB round-trip this session (`adbc_driver_duckdb.dbapi`): `create`→3, `append`→total 6; `cursor.adbc_cancel` confirmed a distinct callable unaffected by the partial.
- `src/adbc_poolhouse/_async/_cursor.py` (`fetch_arrow_table:327`, `_SyncCursor:51`, `fetchmany` two-arm note:288), `_cancel.py:41` (`cancellable_offload` contract), `_offload.py:41` (`offload` chokepoint), `_connection.py` (`_offloading`/`_in_use`/`invalidate`) — read directly this session.
- `tests/_async_harness/stubs.py` (`BlockingStubCursor` sticky-release gate), `tests/_async_harness/guard.py` (PKG-03 rules: only asyncio-import / unlimited-`to_thread` / `asyncio.CancelledError`), `tests/async/test_edge_cancel_onabort_failure.py` (cancel-test template) — read this session.

### Secondary (project docs, HIGH confidence in context)
- `.planning/research/STACK.md` §`adbc_ingest` (lines 28–46) and §"pyarrow-stub reality" (149–165) — driver signature, `data` union strict-cleanliness, `CapsuleType`/`TYPE_CHECKING` decision.
- `.planning/research/SUMMARY.md` (lines 12–14, 106–116, 178) — "byte-for-byte copies of `fetch_arrow_table`"; the keyword-arg open question now resolved.
- `.planning/phases/30-async-bulk-write/30-CONTEXT.md` — locked decisions D-30-01..12.
- `.planning/REQUIREMENTS.md` — INGEST-01..04 definitions and out-of-scope rulings.
- `.planning/phases/29-arrow-streaming/29-02-PLAN.md` — RED-first TDD `must_haves` structure and verify-command precedent.
- `CLAUDE.md` / `MEMORY.md` — docs gate (phase ≥ 7, `mkdocs build --strict`), Google-style Markdown docstrings, loop-flaky-concurrency and zsh-`!` test hygiene, `.venv/bin/*` sandbox workaround.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all deps already installed; signature/partial/typing re-verified live this session.
- Architecture: HIGH — clone of a shipped, tested method; the one novelty (`partial`) verified strict-clean, runtime-correct, and guard-clean.
- Pitfalls: HIGH — root causes traced to specific source lines; the one MEDIUM residual (per-backend partial-write state) is explicitly scoped OUT (A1).

**Research date:** 2026-07-01
**Valid until:** 2026-07-31 (stable — no fast-moving deps; signatures pinned to installed 1.11.0/24.0.0/4.14.1)
