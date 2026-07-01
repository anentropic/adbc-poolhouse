# Phase 30: Async Bulk Write - Pattern Map

**Mapped:** 2026-07-01
**Files analyzed:** 6 (1 production modify, 4 new tests, 1 harness modify)
**Analogs found:** 6 / 6 (every file has a strong in-repo analog; one novel wrinkle flagged)

This phase is deliberately non-novel: `AsyncCursor.adbc_ingest` is a near-mechanical
clone of `fetch_arrow_table` (`_cursor.py:327`). The only net-new *idea* is a
`functools.partial` binding of keyword-only args before `cancellable_offload` (no
existing analog — flagged below). Every other pattern is copied verbatim from
Phases 25/29.

## File Classification

| New/Modified File | Change | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|--------|------|-----------|----------------|---------------|
| `src/adbc_poolhouse/_async/_cursor.py` — `AsyncCursor.adbc_ingest` | ADD method | async wrapper (offload) | batch write / request-response | `fetch_arrow_table` (`_cursor.py:327`) | exact (clone) |
| `src/adbc_poolhouse/_async/_cursor.py` — `_SyncCursor.adbc_ingest` | ADD Protocol member | structural Protocol | signature only | `fetch_record_batch` line in `_SyncCursor` (`_cursor.py:74`) | exact (precedent) |
| `src/adbc_poolhouse/_async/_cursor.py` — imports | ADD `import functools`; `CapsuleType`/`Literal` under `TYPE_CHECKING` | config/imports | — | existing import blocks (`_cursor.py:31-48`) | exact |
| `tests/_async_harness/stubs.py` — `BlockingStubCursor.adbc_ingest` | ADD stub method + `ingest_call_count` | test harness | blocking gate | `BlockingStubCursor.fetch_arrow_table` (`stubs.py:301`) / `execute` (`stubs.py:287`) | exact (clone) |
| `tests/async/test_ingest_roundtrip.py` | NEW | test (integration) | batch write round-trip | `test_reader_stream.py` (DuckDB happy-path) | role-match |
| `tests/async/test_ingest_modes.py` | NEW | test (integration) | batch write, param forwarding | `test_reader_stream.py` (DuckDB happy-path) | role-match |
| `tests/async/test_ingest_cancel.py` | NEW | test (concurrency/cancel) | cancel → abort + invalidate | `test_reader_cancel.py` (`TestStream05CancelPull`) | exact (template) |
| `tests/async/test_ingest_signature.py` (optional; may fold into existing) | NEW | test (typecheck/unit) | Protocol signature | basedpyright gate on `_cursor.py` | role-match |

> Test-file split follows the RESEARCH.md Wave-0 gap list (30-RESEARCH.md:437-444). A
> planner may collapse `test_ingest_modes.py` / `test_ingest_signature.py` into the
> round-trip file; the *analog* per behavior is what matters below.

## Pattern Assignments

### `AsyncCursor.adbc_ingest` (async wrapper, batch-write) — `src/adbc_poolhouse/_async/_cursor.py`

**Analog:** `fetch_arrow_table` — `src/adbc_poolhouse/_async/_cursor.py:327-355`. Clone
this method body exactly; a reviewer diffing the two must see only three deltas:
the callable, the `-> int` return annotation, and the docstring (30-CONTEXT.md:119-121).

**Offload shape to clone** (`_cursor.py:349-355`):
```python
with self._owner._offloading():  # noqa: SLF001
    return await cancellable_offload(
        self._adbc_cancel,
        self._cursor.fetch_arrow_table,
        limiter=self._limiter,
        on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
    )
```

**The ONE delta — bind args with `functools.partial` (NET-NEW; see Shared Pattern A):**
The 2nd positional arg (`self._cursor.fetch_arrow_table`) becomes a partial that
closes over `table_name`, `data`, and the four keyword-only args. The 1st positional
arg (`self._adbc_cancel`) and the `limiter=` / `on_abort=` kwargs are copied verbatim.
`self._adbc_cancel` is a distinct bound method (`_cursor.py:132`), unaffected by the
partial (30-RESEARCH.md:288, Pitfall 2 — do NOT swap the two callables).

**Public signature** (keyword-only after `*`, D-30-03; from 30-RESEARCH.md:181-190):
```python
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
```

**Do NOT copy from `fetch_record_batch` (`_cursor.py:357`):** it sets the
`_reader_open` lifetime lock — copying that permanently poisons the connection
(30-RESEARCH.md Pitfall 1, lines 279-283). `adbc_ingest` is a whole-op offload; the
connection checks in the instant the offload returns. Clone `fetch_arrow_table`, which
does NOT set `_reader_open`.

**Docstring requirements** (docs quality gate, CLAUDE.md phase ≥ 7):
- Google-style Args/Returns/Raises (Markdown, not RST — MEMORY docstring style).
- `Returns:` documents the `int` row count (or driver `-1` when uncountable, D-30-02).
- `Raises: ConnectionBusyError` — mirror the `fetch_arrow_table` block (`_cursor.py:345-347`).
- **Mandatory `mode` warning:** "`replace` **drops** the existing table and recreates
  it." (INGEST-02 / D-30-05 / Pitfall 4, lines 297-301).
- Note `catalog_name` / `db_schema_name` / `temporary` are **EXPERIMENTAL** (D-30-11).
- Document non-atomicity: a cancelled ingest recovers the *connection*, not a
  *partial write* (D-30-10 / Pitfall 5).
- `Example:` (singular) block with a fenced ` ```python ` round-trip (30-RESEARCH.md:333-339).

---

### `_SyncCursor.adbc_ingest` (structural Protocol) — `src/adbc_poolhouse/_async/_cursor.py:51-76`

**Analog:** the `fetch_record_batch` Protocol line added in Phase 29 —
`_cursor.py:74` (`def fetch_record_batch(self) -> pyarrow.RecordBatchReader: ...`),
sitting in the `_SyncCursor` Protocol block (`_cursor.py:51-76`). Add the `adbc_ingest`
signature the same way (D-30-08).

**Existing Protocol block** (`_cursor.py:68-76`, showing the member style to extend):
```python
    def execute(self, operation: str, parameters: object = ..., /) -> object: ...
    def executemany(self, operation: str, seq_of_parameters: object, /) -> object: ...
    def fetchone(self) -> object: ...
    def fetchmany(self, size: int = ..., /) -> Sequence[object]: ...
    def fetchall(self) -> Sequence[object]: ...
    def fetch_arrow_table(self) -> pyarrow.Table: ...
    def fetch_record_batch(self) -> pyarrow.RecordBatchReader: ...
    def adbc_cancel(self) -> None: ...
    def close(self) -> None: ...
```

**Signature to add** (30-RESEARCH.md:243-252 — keeps `mode` positional-or-keyword to
match the *driver*; only the *public* method tightens `mode` to keyword-only):
```python
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

Must stay basedpyright-strict-clean (verified 0 diagnostics, 30-RESEARCH.md:477).

---

### Imports — `src/adbc_poolhouse/_async/_cursor.py:31-48`

**Analog:** the file's existing runtime + `TYPE_CHECKING` blocks.

**Current runtime imports** (`_cursor.py:31-39`):
```python
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import anyio

from adbc_poolhouse._async._cancel import cancellable_offload
from adbc_poolhouse._async._offload import offload
from adbc_poolhouse._async._reader import AsyncRecordBatchReader
```

**Current `TYPE_CHECKING` block** (`_cursor.py:41-48`):
```python
if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    import pyarrow
    from anyio import CapacityLimiter

    from adbc_poolhouse._async._connection import AsyncConnection
```

**Adds required:**
- `import functools` at module top (RUNTIME block, not `TYPE_CHECKING` — `partial` is
  called at runtime; Pitfall 3, 30-RESEARCH.md:291-295). Guard-clean: PKG-03 audits
  only `import asyncio` / unlimited `to_thread` / `asyncio.CancelledError`, never
  `functools` (30-RESEARCH.md:49, 378).
- `Literal` — annotation-only under `from __future__ import annotations` (already at
  `:31`), so it may live in the `TYPE_CHECKING` block (import from `typing`).
- `CapsuleType` from `typing_extensions`, under `TYPE_CHECKING` (D-30-07; matches
  ADBC's choice, `types.CapsuleType` is 3.13+, floor is 3.11).

---

### `BlockingStubCursor.adbc_ingest` (test harness) — `tests/_async_harness/stubs.py`

**Analog:** `BlockingStubCursor.fetch_arrow_table` (`stubs.py:301-312`) and `execute`
(`stubs.py:287-299`). Clone the record-under-lock → `self._block()` → return pattern.

**`fetch_arrow_table` stub to mirror** (`stubs.py:301-312`):
```python
def fetch_arrow_table(self) -> object:
    """
    Record the call, block until released, then return `None`.

    Returns:
        `None`. Later phases inject a real `pyarrow.Table` where a result is
        needed; the bare fake returns `None`.
    """
    with self._lock:
        self.fetch_call_count += 1
    self._block()
    return None
```

**`execute` stub, showing the counter+block idiom** (`stubs.py:287-299`):
```python
def execute(self, operation: str, parameters: object = None) -> None:
    del operation, parameters
    with self._lock:
        self.execute_call_count += 1
        self.execute_thread_ids.append(threading.get_ident())
    self._block()
```

**New stub to add** (30-RESEARCH.md:215-231; the sticky-release gate — `adbc_cancel` /
`close` / `release` already unblock `_block()`, `stubs.py:314-373`):
```python
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
    self._block()
    return 3
```

**Also add** `self.ingest_call_count: int = 0` in `__init__` beside the existing
counters (`stubs.py:158-161`: `execute_call_count` / `fetch_call_count` /
`adbc_cancel_call_count` / `close_call_count`), and document it in the class-attributes
docstring block (`stubs.py:109-112`). The stub already exposes `adbc_cancel`
(`stubs.py:314`) with the sticky-`_cancelled` latch (`stubs.py:330`), so the new method
needs no cancel wiring of its own. `mode` stays positional-or-keyword here to match the
driver/Protocol (only the public method tightens it).

---

### `tests/async/test_ingest_cancel.py` (concurrency/cancel test) — NEW

**Analog:** `tests/async/test_reader_cancel.py` — `TestStream05CancelPull`
(`test_reader_cancel.py:53-127`) for the stub cancel + timeout legs, and
`TestStream05CancelDrainsPool::test_invalidate_drains_pool_duckdb`
(`test_reader_cancel.py:130-159`) for the `checkedout()==0` DuckDB drain leg. This is
the closest existing template for INGEST-04. Swap the blocked call from a reader pull
to `adbc_ingest`.

**Stub cancel-leg skeleton to clone** (`test_reader_cancel.py:56-90`):
```python
async_conn, stub_conn = make_stub_async_connection()
cur = async_conn.cursor()
with real_clock_watchdog(stub_conn.cursors) as tripped:
    async with anyio.create_task_group() as tg:
        tg.start_soon(functools.partial(_drive_ingest, cur))  # blocked adbc_ingest
        try:
            await await_inside(lambda: stub_conn.cursors[-1].ingest_call_count >= 1)
            tg.cancel_scope.cancel()
        finally:
            for c in stub_conn.cursors:
                c.release()
assert tripped[0] is False
assert stub_conn.cursors[-1].adbc_cancel_call_count == 1  # cursor cancel fired once
assert stub_conn.invalidate_call_count == 1               # poison-recovery once
```

**Mandatory harness discipline (copy the module preamble from
`test_reader_cancel.py:24-47`):**
- `pytestmark = _helpers.concurrency_marks` — x-loop repeat + timeout. A single green
  run is NOT acceptance; run in a loop (MEMORY loop-flaky-concurrency; 30-RESEARCH.md:435).
- Import helpers via `importlib.import_module("tests.async._edge_helpers")` — `async`
  is a keyword, so no dotted import (`test_reader_cancel.py:40-45`). Exports:
  `await_inside`, `real_clock_watchdog`, `concurrency_marks`; `virtual_clock` from
  `tests._async_harness.clock`.
- `real_clock_watchdog` (NOT `anyio.fail_after`) for the hang backstop — `fail_after`
  autojumps under the trio `MockClock` (`test_reader_cancel.py:16-18`).
- `await_inside(...)` event-gating (no sleeps) to wait until the worker is inside the
  blocked `adbc_ingest` before cancelling.
- Run under BOTH backends via `anyio_backend_name` (asyncio + trio, D-30-09).
- zsh `!` caveat: in loop verification use `rc=$?` + grep for the pass line, never
  `if ! cmd` (MEMORY).

**Timeout leg** clones `test_timeout_during_pull_aborts_and_invalidates`
(`test_reader_cancel.py:92-127`) with `virtual_clock` + `anyio.fail_after`.

**DuckDB drain leg** clones `test_invalidate_drains_pool_duckdb`
(`test_reader_cancel.py:133-159`): drive `conn.invalidate()` directly (do NOT race a
live `adbc_cancel` against an in-flight DuckDB ingest — best-effort, can wedge the
worker) and assert `pool._pool.checkedout()` goes `1 → 0`. Assert ONLY connection
recovery, never table state after a cancelled ingest (D-30-10 / Pitfall 5).

---

### `tests/async/test_ingest_roundtrip.py` + `test_ingest_modes.py` (integration) — NEW

**Analog:** `tests/async/test_reader_stream.py` (`test_reader_stream.py:40-70`) — the
DuckDB happy-path structure: `duckdb_async_pool` fixture → `await pool.connect()` →
`cur = conn.cursor()` → `await cur.execute(...)` → assert. Same fixture, same
`async with await ... .connect() as conn:` shape.

**Round-trip body to write** (INGEST-01/03; 30-RESEARCH.md:332-339):
```python
import pyarrow as pa
tbl = pa.table({"id": [1, 2, 3], "name": ["a", "b", "c"]})
n = await cursor.adbc_ingest("people", tbl, mode="create")   # -> 3
await cursor.execute("SELECT count(*) FROM people")
assert (await cursor.fetchone())[0] == 3
n2 = await cursor.adbc_ingest("people", tbl, mode="append")  # -> 3
await cursor.execute("SELECT count(*) FROM people")
assert (await cursor.fetchone())[0] == 6
```

- **`test_ingest_roundtrip.py`** covers INGEST-01 (int row count, whole-op offload) and
  INGEST-03 (`pyarrow.Table` / `RecordBatch` pass-through, zero conversion). Add a
  `test_data_passthrough` case (30-RESEARCH.md:427).
- **`test_ingest_modes.py`** covers INGEST-02 — exercise all four `Literal` modes
  reaching the driver, especially `replace` (drop-then-create) and `create_append`.
- Both use the `duckdb_async_pool` fixture (`tests/async/conftest.py:87`) and run under
  both backends via `anyio_backend` (`conftest.py:58`). No new fixtures needed
  (30-RESEARCH.md:444).

---

### `tests/async/test_ingest_signature.py` (typecheck/unit) — NEW or folded

**Analog:** the basedpyright strict gate over `_cursor.py` (validation command
`.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py`, 30-RESEARCH.md:425).
Assert the `_SyncCursor` Protocol carries `adbc_ingest`, the public method is
keyword-only, and the `BlockingStubCursor` structurally satisfies the Protocol
(strict-clean). May fold into an existing signature test rather than a new file.

## Shared Patterns

### Pattern A — Keyword-only args through the positional-variadic offload via `functools.partial` (NET-NEW)

**Source:** No existing in-repo analog. `cancellable_offload` (`_cancel.py:41-47`)
forwards args through a positional variadic:
```python
async def cancellable_offload(
    adbc_cancel: Callable[[], None],
    fn: Callable[[Unpack[_Ts]], _T],
    *args: Unpack[_Ts],  # noqa: UP044
    limiter: CapacityLimiter,
    on_abort: Callable[[], Awaitable[None]] | None = None,
) -> _T:
```
It **cannot forward keywords**. The `fetchmany` two-arm branch (`_cursor.py:284-302`)
is the *closest sibling* but handles a single optional positional arg and does NOT
generalize to four keyword args (30-RESEARCH.md:362-365). Do NOT imitate it here.

**Apply to:** `AsyncCursor.adbc_ingest` only (this phase). The general answer for any
future keyword-bearing offload (SUMMARY.md:114).

**Shape** (verified strict-clean + runtime-correct, 30-RESEARCH.md:315-326):
```python
functools.partial(
    self._cursor.adbc_ingest,
    table_name,
    data,
    mode=mode,
    catalog_name=catalog_name,
    db_schema_name=db_schema_name,
    temporary=temporary,
)
```
Bind into a **zero-positional-arg** partial → `_Ts` infers empty → satisfies
`Callable[[Unpack[_Ts]], _T]`. Do NOT widen `offload`/`cancellable_offload` with
`**kwargs` (D-30-04, rejected — touches the audited chokepoint). Prefer `partial` over
a `lambda` (30-RESEARCH.md:88).

### Pattern B — Cooperative cancel + poison recovery (reused verbatim)

**Source:** `cancellable_offload(self._adbc_cancel, fn, limiter=self._limiter,
on_abort=self._owner.invalidate)` — every offloaded method uses it identically
(`fetch_arrow_table` `_cursor.py:350-354`; `fetchall` `_cursor.py:320-324`).

**Apply to:** `AsyncCursor.adbc_ingest`. Copy the four arguments unchanged; only the
2nd (`fn`) becomes the partial. `on_abort=self._owner.invalidate` gives the D-25-03
poison recovery: a cancelled/timed-out ingest fires `adbc_cancel` once (shielded),
invalidates the poisoned connection, re-raises the cancellation, leaving
`checkedout()==0` (INGEST-04 / D-30-09).

### Pattern C — Per-call concurrency guard (reused verbatim)

**Source:** `with self._owner._offloading():  # noqa: SLF001` — wraps the offload in
every method (`_cursor.py:349`, `:319`, `:284`).

**Apply to:** `AsyncCursor.adbc_ingest`. Copy the `_offloading()` span (with the
`# noqa: SLF001` intentional-parent-guard comment) — it yields `ConnectionBusyError`
on a concurrent second op. Do NOT set `_reader_open` (that is `fetch_record_batch`
only; Pitfall 1). The connection checks in the instant the span exits.

### Pattern D — No worker-exception re-wrapping (reused verbatim)

**Source:** module docstring EDGE-17 contract (`_cursor.py:26-28`); the single
`offload` chokepoint re-raises native errors with exact type/traceback.

**Apply to:** `AsyncCursor.adbc_ingest`. Add NO `try/except`. A driver
`ProgrammingError` / `AdbcError` on a bad ingest propagates unchanged (30-RESEARCH.md:262).
No runtime validation of `data` or `mode` — pure pass-through (D-30-05/06).

### Pattern E — Concurrency-test hygiene (reused verbatim across cancel tests)

**Source:** `test_reader_cancel.py:24-47` preamble + `_edge_helpers.py:54-59`
(`concurrency_marks`).

**Apply to:** `test_ingest_cancel.py`. `pytestmark = _helpers.concurrency_marks`
(x-loop repeat via `ADBC_ASYNC_REPEAT` + `timeout`); `importlib` helper load;
`real_clock_watchdog` not `fail_after`; `await_inside` gating; both backends. Loop the
run, grep for the pass line (never `if ! cmd` in zsh; MEMORY).

## No Analog Found

| File / Concern | Role | Data Flow | Reason |
|----------------|------|-----------|--------|
| `functools.partial` keyword→positional binding (Shared Pattern A) | async wrapper | argument binding | No prior offloaded method needed keyword args; the `fetchmany` two-arm branch (`_cursor.py:284`) handles only a single optional positional and does NOT generalize. This is the phase's sole net-new construct — verified strict-clean + runtime-correct + guard-clean this research session (30-RESEARCH.md:49). |

Everything else in this phase has an exact or role-matched in-repo analog.

## Metadata

**Analog search scope:** `src/adbc_poolhouse/_async/` (production), `tests/async/`,
`tests/_async_harness/` (harness + stubs).
**Files scanned (read this session):** `_cursor.py` (imports, `_SyncCursor`, `fetchmany`,
`fetchall`, `fetch_arrow_table`, `fetch_record_batch`), `_cancel.py` (`cancellable_offload`
signature/contract), `stubs.py` (`BlockingStubCursor` counters, `execute`,
`fetch_arrow_table`, `adbc_cancel`, `close`, `release`, `fetch_record_batch`),
`test_edge_cancel_onabort_failure.py`, `test_reader_cancel.py`, `test_reader_stream.py`,
`conftest.py`, `_edge_helpers.py`.
**Pattern extraction date:** 2026-07-01
