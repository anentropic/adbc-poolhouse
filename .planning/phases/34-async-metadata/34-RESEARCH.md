# Phase 34: Async Metadata - Research

**Researched:** 2026-07-04
**Domain:** Async wrapper extension — offloading the six ADBC connection-level `adbc_get_*` metadata methods onto `AsyncConnection`
**Confidence:** HIGH

<user_constraints>
## User Constraints (from `/gsd-discuss-phase 34 --assumptions`)

> Assumptions mode wrote no CONTEXT.md; these locked decisions were supplied in the
> orchestrator brief and are authoritative. Research is scoped *within* them — do not
> relitigate.

### Locked Decisions

1. **Streaming readers → wrap in `AsyncRecordBatchReader` (option a).** Exactly three of the six methods return a sync `pyarrow.RecordBatchReader` — `adbc_get_objects`, `adbc_get_statistics`, `adbc_get_statistic_names`. Wrap each in the existing `AsyncRecordBatchReader` with the connection lifetime-lock (`_reader_open`), exactly as `AsyncCursor.fetch_record_batch` does. NOT eager materialization; NOT a raw sync reader (would dangle — Phase 29 Pitfall 7). Satisfies META-02's "surface native reader without eager materialization."

2. **Non-cancellable plain `offload`, NOT `cancellable_offload`, for the connection-level call.** These are connection-level; ADBC's `adbc_cancel` is cursor-level and the connection has none. Mirror `AsyncConnection.commit`/`rollback`. The `AsyncRecordBatchReader` constructor takes a cancel-hook arg — for connection-level metadata readers there is no cursor cancel, so pass a no-op / absent cancel and confirm the reader tolerates it. Document (in docstrings) that a surrounding timeout/cancel cannot abort an in-flight metadata call, same wording as commit/rollback.

3. **Access path via the SQLAlchemy fairy.** `_ConnectionFairy.__getattr__` proxies unknown attributes straight to the underlying dbapi ADBC `Connection`, so `self._fairy.adbc_get_info(...)` works with no `driver_connection` unwrap — same routing `AsyncConnection` already uses for commit/rollback/close.

4. **Confirmed return types (REQUIREMENTS.md META-02 already corrected to match):** `adbc_get_info` → `dict`; `adbc_get_table_schema` → `pyarrow.Schema`; `adbc_get_table_types` → `list[str]`; the streaming trio → `pyarrow.RecordBatchReader` (wrapped per #1). Do NOT reintroduce the earlier error that called `adbc_get_info` Arrow-streaming or omitted `adbc_get_statistic_names`.

5. **Two-tier guard.** Each method brackets its offload with `self._offloading()` (the `_in_use` + `_reader_open` foreign tier), like commit/rollback. The three streaming methods set `_reader_open = True` AFTER the `_offloading()` span, on the success path only, exactly as `fetch_record_batch` does.

6. **No new error types, no `find_spec` pre-checks (META-03).** A backend that doesn't implement a method surfaces the driver's native error unchanged. Verified on DuckDB: `adbc_get_info`/`adbc_get_objects`/`adbc_get_table_schema`/`adbc_get_table_types` work; `adbc_get_statistics`/`adbc_get_statistic_names` raise `NotSupportedError` — that pair is a ready-made META-03 test on DuckDB. Streaming happy-path is exercised via `adbc_get_objects` on DuckDB.

### Claude's Discretion
- Whether to add STREAM-06-style busy/two-tier-guard and EDGE-33-style read-after-close tests for the streaming metadata readers (nice-to-have; the shared machinery makes them cheap). Test-file naming and split.
- Exact `_SyncConnection` Protocol shape and whether to cast inline vs. store a cast reference.

### Deferred Ideas (OUT OF SCOPE)
- Async prepared statements (`adbc_prepare`, `adbc_execute_schema`) → **Phase 35**.
- Async partitioned result sets (`adbc_execute_partitions`, `adbc_read_partition`) → deferred (niche Flight-SQL-only).
- Version bump to 1.5.0 + changelog entry → deferred release step after Phase 35 (per STATE.md).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| META-01 | All six `adbc_get_*` awaitable on the async connection, each a pure offload wrapper over the wrapped sync `dbapi.Connection` routed through the existing chokepoint + per-pool `CapacityLimiter` | Fairy proxy verified (§Access Path); offload/`_offloading` templates confirmed in `_connection.py` (commit/rollback). Wiring table in §Architecture Patterns |
| META-02 | Return types mirror sync — dict / `Schema` / list, streaming trio surfaces native `RecordBatchReader` without eager materialization; no invented error types, no `find_spec` | Exact signatures + return types verified against `adbc_driver_manager` 1.11.0 (§Standard Stack). `AsyncRecordBatchReader` reuse per locked decision #1 |
| META-03 | Unsupported metadata method surfaces the driver's native error unchanged | Verified: `adbc_get_statistics`/`adbc_get_statistic_names` raise `adbc_driver_manager.NotSupportedError` on DuckDB — ready-made test (§Validation Architecture) |
| META-04 | Async guide + API reference document the methods, caveat shrinks, `mkdocs build --strict` passes, humanizer pass | Docs surface mapped (§Docs Surface): async.md warning block lines 23-31 + a new guide section; API reference auto-renders via existing `AsyncConnection` mkdocstrings block — no `gen_ref_pages.py` change |
</phase_requirements>

## Summary

Phase 34 adds six awaitable metadata methods to `AsyncConnection`, each a thin offload wrapper over the sync ADBC `dbapi.Connection` reached through the SQLAlchemy fairy. There is **zero new async machinery**: the value-returning trio (`adbc_get_info`, `adbc_get_table_schema`, `adbc_get_table_types`) are structural clones of `AsyncConnection.commit`/`rollback` (plain `offload` inside `self._offloading()`), and the Arrow-streaming trio (`adbc_get_objects`, `adbc_get_statistics`, `adbc_get_statistic_names`) are structural clones of `AsyncCursor.fetch_record_batch` (plain `offload` to create the sync reader, then wrap in the existing `AsyncRecordBatchReader` with the `_reader_open` lifetime lock). All patterns already exist and are battle-tested from Phases 24/29.

The two genuine design points — both settled by the locked decisions and confirmed here — are (a) the **cancel hook** the streaming readers need: connection-level metadata has no `adbc_cancel`, so a no-op is passed, and the `AsyncRecordBatchReader` tolerates it because `adbc_cancel()` is only ever *called* on the cancel path and a no-op call is harmless; and (b) the **typing bridge**: the fairy is `sqlalchemy.pool.PoolProxiedConnection`, whose `__getattr__` types `adbc_get_*` as `Any`. A `_SyncConnection`-style structural `Protocol` (mirroring the existing `_SyncCursor`/`_SyncReader`) plus a `cast` gives strict-clean, self-documenting, arity-correct offload calls — the established codebase idiom.

The three keyword-bearing methods (`adbc_get_objects`, `adbc_get_table_schema`, `adbc_get_statistics`) forward their filters through the `TypeVarTuple` offload boundary with `functools.partial`, the milestone-general answer already proven in Phase 30 (`adbc_ingest`). Tests reuse the `duckdb_async_pool` fixture on the asyncio×trio axis; DuckDB carries all automated coverage (happy path for four methods + native-`NotSupportedError` META-03 for the statistics pair), and — as with the Phase 29 streaming legs — the Snowflake cassette cannot replay metadata, so any Snowflake leg is manual-only.

**Primary recommendation:** Clone `commit`/`rollback` for the three value-returning methods and `fetch_record_batch` for the three streaming methods; add a `_SyncConnection` Protocol + `cast` for strict-clean typed offload; pass a module-level `_noop_cancel` to each `AsyncRecordBatchReader`; test on DuckDB (four happy-path + two META-03 `NotSupportedError`); document by shrinking the async.md caveat and letting the existing `AsyncConnection` mkdocstrings block auto-render the new methods.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Metadata call dispatch (`adbc_get_*`) | Async wrapper (`AsyncConnection`) | Worker thread (offload) | The async surface owns awaitability + the `_in_use`/`_reader_open` guard; the blocking C call runs off-loop under the pool limiter |
| Actual metadata retrieval | Sync ADBC driver (via fairy `__getattr__`) | — | poolhouse never reimplements introspection; it forwards to the dbapi `Connection` untouched (META-01/02) |
| Streaming reader lifetime | `AsyncRecordBatchReader` + `AsyncConnection._reader_open` | Pool reset event (checkin) | Reader is a live C stream bound to the checked-out connection; the two-tier lock keeps foreign ops off it (STREAM-06 pattern) |
| Error surfacing | Sync driver → `offload` chokepoint (pass-through) | — | No async-specific error types; native `NotSupportedError`/`AdbcError` propagate unchanged (META-03) |
| Typing bridge | `_SyncConnection` Protocol + `cast` | basedpyright strict | Fairy proxies via `__getattr__` (`Any`); a structural Protocol restores precise types + offload arity |

## Standard Stack

### Core (already installed — no new packages)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `adbc_driver_manager` | 1.11.0 | Provides `dbapi.Connection.adbc_get_*` — the six methods being wrapped | [VERIFIED: `.venv/bin/python` introspection] Already the project's core driver-manager dep |
| `anyio` | (installed, `[async]` extra) | `offload`/`cancellable_offload`/`CapacityLimiter` chokepoint | [VERIFIED: codebase] The entire async layer is built on it |
| `pyarrow` | (core dep) | `Schema` + `RecordBatchReader` return types | [VERIFIED: driver signatures + `_reader.py`] Already core; imported under `TYPE_CHECKING` in `_cursor.py`/`_reader.py` |

**No `npm`/`pip`/`cargo` install step in this phase.** Every symbol used already ships. The `## Package Legitimacy Audit` section is therefore **N/A — no external packages are added**.

### Verified ADBC method signatures (`adbc_driver_manager` 1.11.0)

Introspected from the installed `adbc_driver_manager.dbapi.Connection` [VERIFIED: `inspect.signature`]:

```text
adbc_get_info(self) -> Dict[str | int, Any]
adbc_get_objects(self, *, depth: Literal['all','catalogs','db_schemas','tables','columns'] = 'all',
                 catalog_filter: str | None = None, db_schema_filter: str | None = None,
                 table_name_filter: str | None = None, table_types_filter: List[str] | None = None,
                 column_name_filter: str | None = None) -> pyarrow.RecordBatchReader
adbc_get_table_schema(self, table_name: str, *, catalog_filter: str | None = None,
                      db_schema_filter: str | None = None) -> pyarrow.Schema
adbc_get_table_types(self) -> List[str]
adbc_get_statistics(self, *, catalog_filter: str | None = None, db_schema_filter: str | None = None,
                    table_name_filter: str | None = None, approximate: bool = True) -> pyarrow.RecordBatchReader
adbc_get_statistic_names(self) -> pyarrow.RecordBatchReader
```

Classification for wiring:

| Method | Args | Returns | Category | Offload shape |
|--------|------|---------|----------|---------------|
| `adbc_get_info` | none | `dict[str \| int, Any]` | value | plain `offload(bound_method)` |
| `adbc_get_table_types` | none | `list[str]` | value | plain `offload(bound_method)` |
| `adbc_get_table_schema` | `table_name` + 2 kw-only | `pyarrow.Schema` | value | plain `offload(functools.partial(...))` |
| `adbc_get_objects` | 6 kw-only | `pyarrow.RecordBatchReader` | **stream** | plain `offload(functools.partial(...))` → wrap |
| `adbc_get_statistics` | 4 kw-only | `pyarrow.RecordBatchReader` | **stream** | plain `offload(functools.partial(...))` → wrap |
| `adbc_get_statistic_names` | none | `pyarrow.RecordBatchReader` | **stream** | plain `offload(bound_method)` → wrap |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `_SyncConnection` Protocol + `cast` | Direct `self._fairy.adbc_get_*()` (typed `Any`) | Both pass basedpyright strict (`reportAny` is OFF in this project's config — [VERIFIED: probe]). Direct-`Any` bypasses offload `TypeVarTuple` arity checks on the `functools.partial` args and loses self-documentation. The Protocol mirrors the established `_SyncCursor`/`_SyncReader` idiom — **prefer it** |
| Reuse `AsyncRecordBatchReader` unchanged | A no-invalidate reader variant | Locked decision #1 mandates reuse. A variant contradicts it and adds machinery for no requirement |
| No-op cancel via module-level `_noop_cancel` | `lambda: None` inline | A lambda passes the source guard (it only matches `to_thread.run_sync`/`asyncio`), but a named module-level function matches the codebase convention (`_pull` is module-level "to keep the guard matcher clean") and reads clearer |

## Architecture Patterns

### System Architecture Diagram

```
await conn.adbc_get_info()                 await conn.adbc_get_objects(depth="tables")
        │                                          │
        ▼                                          ▼
  AsyncConnection.adbc_get_info            AsyncConnection.adbc_get_objects
        │                                          │
  with self._offloading():   ◄── two-tier    with self._offloading():   ◄── foreign tier
        │   guard (_in_use +                       │   (_in_use OR _reader_open)
        │   _reader_open reject)                    │
        ▼                                          ▼
  offload(sync_conn.adbc_get_info,          sync_reader = offload(
          limiter=self._limiter)  ◄─ plain      functools.partial(sync_conn.adbc_get_objects, depth=...),
          NON-cancellable (commit/rollback      limiter=self._limiter)  ◄─ plain, NON-cancellable
          template)                              │
        │                                  (span exits → _in_use cleared)
        ▼                                          │
  anyio.to_thread.run_sync                 self._owner._reader_open = True   ◄── success path only
  (worker: dbapi.Connection                        │
   .adbc_get_info via fairy                        ▼
   __getattr__ proxy)                       AsyncRecordBatchReader(sync_reader, limiter,
        │                                        self, _noop_cancel)   ◄── no cursor cancel
        ▼                                          │
  returns dict ─────────────► caller       async for batch in reader:  ── each pull:
                                             cancellable_offload(_noop_cancel, _pull,
                                               reader, on_abort=owner.invalidate)
                                                   │
                                             reader.close() clears _reader_open (shielded)

  Unsupported (DuckDB adbc_get_statistics):
  worker raises adbc_driver_manager.NotSupportedError
        └─► offload re-raises exact type/traceback ─► caller (META-03, no wrapping)
```

### Recommended structure (files touched)

```
src/adbc_poolhouse/_async/
├── _connection.py    # ADD: _SyncConnection Protocol, _noop_cancel, the 6 methods;
│                     #      new runtime import of AsyncRecordBatchReader + functools
└── (no other source file changes)

tests/async/
├── test_meta_roundtrip.py    # happy path: get_info / get_table_schema / get_table_types
├── test_meta_stream.py       # get_objects streaming happy path (async for, schema, drain)
├── test_meta_unsupported.py  # META-03: get_statistics / get_statistic_names → NotSupportedError
└── test_meta_signature.py    # 6 methods exist on AsyncConnection; kw-only params kw-only

docs/src/guides/async.md      # shrink the caveat block; add a metadata section
# docs/scripts/gen_ref_pages.py — NO CHANGE (AsyncConnection block auto-renders new methods)
```

### Pattern 1: Value-returning metadata method (clone of `commit`/`rollback`)
**What:** Plain non-cancellable offload inside the two-tier guard; return the driver value unchanged.
**When to use:** `adbc_get_info`, `adbc_get_table_types` (no args); `adbc_get_table_schema` (via `functools.partial`).
**Example:**
```python
# Source: adapted from src/adbc_poolhouse/_async/_connection.py::commit (VERIFIED template)
async def adbc_get_info(self) -> dict[str | int, Any]:
    sync_conn = cast("_SyncConnection", self._fairy)
    with self._offloading():
        return await offload(sync_conn.adbc_get_info, limiter=self._limiter)

async def adbc_get_table_schema(
    self, table_name: str, *,
    catalog_filter: str | None = None, db_schema_filter: str | None = None,
) -> pyarrow.Schema:
    sync_conn = cast("_SyncConnection", self._fairy)
    with self._offloading():
        return await offload(
            functools.partial(
                sync_conn.adbc_get_table_schema, table_name,
                catalog_filter=catalog_filter, db_schema_filter=db_schema_filter,
            ),
            limiter=self._limiter,
        )
```

### Pattern 2: Streaming metadata method (clone of `fetch_record_batch`)
**What:** Plain non-cancellable offload creates the sync reader; on the success path set `_reader_open` AFTER the guard span; wrap in `AsyncRecordBatchReader` with a no-op cancel.
**When to use:** `adbc_get_objects`, `adbc_get_statistics`, `adbc_get_statistic_names`.
**Example:**
```python
# Source: adapted from src/adbc_poolhouse/_async/_cursor.py::fetch_record_batch (VERIFIED template)
async def adbc_get_objects(
    self, *, depth: Literal["all","catalogs","db_schemas","tables","columns"] = "all",
    catalog_filter: str | None = None, db_schema_filter: str | None = None,
    table_name_filter: str | None = None, table_types_filter: list[str] | None = None,
    column_name_filter: str | None = None,
) -> AsyncRecordBatchReader:
    sync_conn = cast("_SyncConnection", self._fairy)
    with self._offloading():          # foreign tier: _in_use OR _reader_open
        sync_reader = await offload(   # plain offload (NOT cancellable) — locked decision #2
            functools.partial(
                sync_conn.adbc_get_objects, depth=depth,
                catalog_filter=catalog_filter, db_schema_filter=db_schema_filter,
                table_name_filter=table_name_filter, table_types_filter=table_types_filter,
                column_name_filter=column_name_filter,
            ),
            limiter=self._limiter,
        )
    # AFTER the span (which cleared _in_use), success path only (Pitfall 5)
    self._reader_open = True
    # Connection has no adbc_cancel — pass the no-op; the reader tolerates it (see Pitfall 1)
    return AsyncRecordBatchReader(sync_reader, self._limiter, self, _noop_cancel)
```

### Pattern 3: The typing bridge (`_SyncConnection` Protocol)
**What:** Structural Protocol mirroring `_SyncCursor`, declaring the six methods with precise types; `cast` the fairy to it.
**Why:** `PoolProxiedConnection.__getattr__` types `adbc_get_*` as `Any` [VERIFIED: `reveal_type`]. The Protocol restores precise return types and lets the `functools.partial` args be arity-checked against the offload `TypeVarTuple`.
```python
class _SyncConnection(Protocol):
    """Structural type for the sync ADBC dbapi Connection metadata surface (mirrors _SyncCursor)."""
    def adbc_get_info(self) -> dict[str | int, Any]: ...
    def adbc_get_objects(self, *, depth: Literal[...] = ..., ...) -> pyarrow.RecordBatchReader: ...
    def adbc_get_table_schema(self, table_name: str, *, ...) -> pyarrow.Schema: ...
    def adbc_get_table_types(self) -> list[str]: ...
    def adbc_get_statistics(self, *, ...) -> pyarrow.RecordBatchReader: ...
    def adbc_get_statistic_names(self) -> pyarrow.RecordBatchReader: ...
```

### Anti-Patterns to Avoid
- **Using `cancellable_offload` for the connection-level metadata call.** The connection has no `adbc_cancel`; there is nothing to abort. Use plain `offload` (locked decision #2). [VERIFIED: `_connection.py` commit/rollback use plain `offload`]
- **Setting `_reader_open` inside the `_offloading()` span.** It must be set AFTER the span, success-path only, or a cancelled/failed creation leaves the connection permanently busy (Pitfall 5, D-29). [CITED: `_cursor.py::fetch_record_batch` comment]
- **Eager materialization of the streaming readers.** META-02 requires surfacing the native `RecordBatchReader`. Do not call `.read_all()`. [locked decision #1]
- **A `find_spec` pre-check or bespoke error type for unsupported backends.** META-03: let the native `NotSupportedError` propagate. [locked decision #6]
- **Adding a Snowflake automated metadata test.** The replay cursor cannot serve `adbc_get_*` (see Pitfall 2).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Off-loop dispatch of the blocking C call | A bespoke `to_thread` call | `offload(..., limiter=self._limiter)` | Single audited chokepoint; source guard forbids anything else |
| Streaming reader lifetime/close/`__del__` | A new reader class | `AsyncRecordBatchReader` (unchanged) | Locked decision #1; the `_reader_open` lock + shielded close + warn-only `__del__` are already proven (Phase 29) |
| Two-tier busy guard | New flag logic | `self._offloading()` / `_reader_open` | Already on `AsyncConnection`; commit/rollback/fetch_record_batch all use it |
| Keyword-arg forwarding through the offload boundary | Chokepoint widening | `functools.partial(bound_method, ...kwargs)` | D-30-04 milestone-general answer (Phase 30 `adbc_ingest`); strict-clean, arity-correct |
| Precise typing of the fairy's proxied methods | `getattr` + manual annotation | `_SyncConnection` Protocol + `cast` | Mirrors `_SyncCursor`; restores types lost to `PoolProxiedConnection.__getattr__ → Any` |

**Key insight:** Every building block this phase needs already exists and is tested. The phase is assembly, not invention — the risk is *deviating* from the established templates, not missing machinery.

## Common Pitfalls

### Pitfall 1: The `AsyncRecordBatchReader` cancel hook for a cursor-less reader
**What goes wrong:** `AsyncRecordBatchReader.__init__` requires `adbc_cancel: Callable[[], None]`, and its `__anext__` runs each pull through `cancellable_offload(self._adbc_cancel, _pull, ...)`. Connection-level metadata has no `adbc_cancel`.
**Why it happens:** The reader was designed for cursor-backed streams (`fetch_record_batch` threads in `cursor._adbc_cancel`).
**How to avoid:** Pass a **module-level no-op** `_noop_cancel() -> None: ...`. [VERIFIED via `_cancel.py` reading] `adbc_cancel()` is invoked **only on the cancel path**, inside the watcher's `except`, when `worker_started` is true — a no-op call is completely harmless. The worker runs `abandon_on_cancel=False`, so a cancelled in-flight metadata pull is **joined** (waited for), then the framework cancellation is re-raised.
**Consequence to document:** A surrounding timeout/cancel **cannot abort an in-flight metadata pull** (same caveat as commit/rollback) — the loop blocks until the pull returns. On that cancel path `on_abort=self.invalidate` (baked into `__anext__`) still fires, so a cancelled metadata-reader pull **invalidates the connection** — consistent with the cursor-reader STREAM-05 contract. This asymmetry (creation = non-cancellable plain offload; per-pull = `cancellable_offload` with invalidate, inherited from the shared reader) is expected and acceptable; call it out in the docstring.
**Warning signs:** A `TypeError` on `AsyncRecordBatchReader(...)` means the 4th positional arg was omitted; a "coroutine was never awaited" warning means someone tried to pass an `async` cancel.

### Pitfall 2: Snowflake cassette cannot replay metadata (mirrors Phase 29 A1)
**What goes wrong:** Writing a cassette-backed Snowflake metadata test that silently never runs — or worse, fails.
**Why it happens:** `pytest-adbc-replay`'s replay cursor/connection implements only `fetch_arrow_table` + row fetches; it has **no `adbc_get_*`** and the cassette stores one materialized Arrow result. [CITED: `test_reader_lifetime.py` A1 note + STATE.md Blockers/A1]
**How to avoid:** DuckDB carries **all** automated metadata coverage. Any Snowflake leg is MANUAL-ONLY (`@pytest.mark.snowflake` + module-level skip), exactly as the Phase 29 streaming legs. Do not gate the phase on Snowflake.
**Warning signs:** A metadata test requesting `snowflake_async_pool` that isn't skipped.

### Pitfall 3: `_reader_open` set inside the guard span
**What goes wrong:** The connection is left permanently `ConnectionBusyError`-locked after a failed/cancelled reader creation.
**Why it happens:** `self._offloading()` clears `_in_use` on exit but **never touches `_reader_open`** (owned by `reader.close()`/checkin). Setting `_reader_open` before the span exits, or on a failure path, strands the lock.
**How to avoid:** Set `self._reader_open = True` **after** the `with self._offloading():` block, on the success path only — copy `fetch_record_batch` exactly. [CITED: `_cursor.py` lines 607-618]
**Warning signs:** A test that creates a reader, hits an error, then can't reuse the connection.

### Pitfall 4: `Any`-typed fairy silently swallowing arity mistakes
**What goes wrong:** `self._fairy.adbc_get_objects(depth=..., bad_kwarg=...)` type-checks fine (it's `Any`) but fails at runtime.
**Why it happens:** `PoolProxiedConnection.__getattr__` returns `Any`; basedpyright can't see the real signature.
**How to avoid:** Route through the `_SyncConnection` Protocol + `cast`, so `functools.partial(sync_conn.adbc_get_objects, ...)` is checked against the declared signature.
**Warning signs:** A runtime `TypeError: unexpected keyword argument` that basedpyright didn't catch.

### Pitfall 5: `StopIteration` across the offload boundary (already handled — do not regress)
**What goes wrong:** A bare `StopIteration` from `read_next_batch()` becomes `RuntimeError` under asyncio/trio.
**Why it doesn't bite here:** The metadata streaming readers reuse `AsyncRecordBatchReader.__anext__`, whose module-level `_pull` already converts end-of-stream to the `_EXHAUSTED` sentinel. [VERIFIED: `_reader.py::_pull`] No new code needed — just don't bypass `AsyncRecordBatchReader`.

## Runtime State Inventory

> This phase adds new methods to an existing class. It renames/migrates nothing. Inventory is N/A, but stated explicitly per the researcher contract:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no persisted keys/IDs are introduced or renamed | none |
| Live service config | None — no external-service config touched | none |
| OS-registered state | None | none |
| Secrets/env vars | None | none |
| Build artifacts | None — pure source addition; no package rename or entry-point change | none |

## Code Examples

### Consumer usage (what the phase enables)
```python
# Source: intended public surface (mirrors sync ADBC + existing async guide voice)
async with await pool.connect() as conn:
    info = await conn.adbc_get_info()                     # dict
    schema = await conn.adbc_get_table_schema("people")   # pyarrow.Schema
    types = await conn.adbc_get_table_types()             # list[str]

    async with await conn.adbc_get_objects(depth="tables") as reader:
        async for batch in reader:                        # pyarrow.RecordBatch, each pull offloaded
            process(batch)
```

### Fairy proxy — verified working with no unwrap
```python
# Source: VERIFIED probe against DuckDB driver (2026-07-04)
raw = pool.connect()                 # sqlalchemy PoolProxiedConnection (the "fairy")
getattr(raw, "adbc_get_info")()      # -> dict   (proxied via _ConnectionFairy.__getattr__)
getattr(raw, "adbc_get_objects")()   # -> pyarrow.lib.RecordBatchReader
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| async layer omits connection metadata (v1.4.0/1.5.0 caveat) | six `adbc_get_*` offloaded onto `AsyncConnection` | Phase 34 (this) | Closes the metadata half of the async/sync parity caveat |
| `adbc_get_info` mislabeled Arrow-streaming; `adbc_get_statistic_names` omitted (earlier REQUIREMENTS draft) | corrected: `adbc_get_info` → dict; full six enumerated | REQUIREMENTS.md 2026-07-04 | Locked decision #4 — do not reintroduce |

**Deprecated/outdated:** None. `adbc_driver_manager` 1.11.0 is the installed, current driver-manager; the six signatures above are authoritative for this environment.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `adbc_get_info` returns a plain `dict` that is self-owning and safe after checkin (like `fetch_arrow_table`, not a live handle) | Standard Stack | LOW — DuckDB returned a `builtins.dict`; a driver returning a lazy view is not observed. Verified on DuckDB only |
| A2 | The `AsyncRecordBatchReader` per-pull `on_abort=invalidate` behavior is acceptable for metadata readers (a cancelled pull drops the connection) | Pitfall 1 | LOW — consistent with STREAM-05; flagged for planner/docstring so it is a conscious contract, not a surprise |
| A3 | No Snowflake-driver metadata behavior is verified (statistics support, return shapes) — only DuckDB was probed | Validation Architecture | LOW — Snowflake is manual-only regardless (Pitfall 2); DuckDB is the automated gate |

**Note:** These are LOW-risk, DuckDB-verified-vs-generalization gaps, not open design questions. The design itself is fully constrained by the locked decisions and verified templates.

## Open Questions (RESOLVED)

1. **Should the streaming metadata readers also get STREAM-06 (busy-while-live) and EDGE-33 (read-after-close → `ArrowInvalid`) tests?**
   - RESOLVED: 34-01 Task 3 includes the minimal busy-guard leg in `test_meta_stream.py`; 34-02 Task 2's behavior block covers it. Full EDGE-33 clone intentionally skipped (inherited from the shared reader).
   - What we know: the shared `AsyncRecordBatchReader` already enforces both; DuckDB's `adbc_get_objects` returns a real `pyarrow.RecordBatchReader`, so the behavior is inherited.
   - What's unclear: whether META requirements alone justify the extra tests, or they're gold-plating.
   - Recommendation: add a **minimal** `test_meta_stream.py` busy-guard assertion (a foreign `await conn.commit()` while a metadata reader is live raises `ConnectionBusyError`) — it's ~10 lines and locks locked-decision #5's guarantee cheaply. Skip a full EDGE-33 clone unless the planner wants belt-and-suspenders.

2. **`dict` value type annotation for `adbc_get_info`.**
   - RESOLVED: 34-02 `interface_contracts` specifies `-> dict[str | int, Any]`, mirroring the driver.
   - What we know: driver types it `Dict[str | int, Any]`.
   - Recommendation: mirror the driver — `-> dict[str | int, Any]` (import `Any`). `dict[str | int, object]` also passes strict; either is fine.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `adbc_driver_manager` | the six wrapped methods | ✓ | 1.11.0 | — |
| DuckDB backend (`adbc_driver_duckdb`) | automated tests (happy path + META-03) | ✓ | (installed; `duckdb_async_pool` fixture works) | — |
| `anyio` + `[async]` extra | offload layer | ✓ | installed | — |
| `pyarrow` | Schema/reader types | ✓ | core dep | — |
| Snowflake driver + cassette | (would back a Snowflake leg) | ✗ (metadata not replayable) | — | Manual-only; DuckDB carries all automated coverage |
| `.venv/bin/basedpyright` | strict type gate | ✓ | ≥1.38.0, strict mode | — |
| `.venv/bin/mkdocs` | `--strict` docs gate | ✓ | Material + mkdocstrings | prefer `.venv/bin/mkdocs` over `uv run` under sandbox |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** Snowflake metadata replay → manual-only (documented, non-blocking).

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — this section is required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 + `anyio` plugin (asyncio×trio axis via `anyio_backend` fixture) |
| Config file | `pyproject.toml` (`[tool.basedpyright]`, ruff, pytest markers: `anyio`, `snowflake`, `adbc_cassette`) |
| Quick run command | `.venv/bin/pytest tests/async/test_meta_*.py -x` |
| Full suite command | `.venv/bin/pytest tests/async -q` (loop gate: `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async -q` per carried-forward gotcha) |
| Type gate | `.venv/bin/basedpyright src/adbc_poolhouse/_async/_connection.py` (0 errors) |
| Docs gate | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` (exit 0, not grep) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| META-01 | all six awaitable on `AsyncConnection`, routed through offload+limiter | unit (signature + roundtrip) | `.venv/bin/pytest tests/async/test_meta_signature.py tests/async/test_meta_roundtrip.py -x` | ❌ Wave 0 |
| META-02 | `get_info`→dict, `get_table_schema`→`Schema`, `get_table_types`→list; `get_objects`→`AsyncRecordBatchReader` streamed (no eager materialization) | integration (DuckDB) | `.venv/bin/pytest tests/async/test_meta_roundtrip.py tests/async/test_meta_stream.py -x` | ❌ Wave 0 |
| META-03 | unsupported method surfaces native `NotSupportedError` unchanged | integration (DuckDB) | `.venv/bin/pytest tests/async/test_meta_unsupported.py -x` | ❌ Wave 0 |
| META-04 | guide + reference documented, strict build passes | docs gate | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` | n/a (build) |
| (cross) | `_async/` source stays guard-clean; strict types | meta-guard + basedpyright | `.venv/bin/pytest tests/async/test_meta_guard.py -x && .venv/bin/basedpyright src/adbc_poolhouse/_async/_connection.py` | ✅ exists (`test_meta_guard.py`, `test_async_guard.py`) |

### Concrete test designs (DuckDB, `@pytest.mark.anyio`, `duckdb_async_pool` fixture)

- **`test_meta_roundtrip.py`**: `adbc_get_info()` → `isinstance(x, dict)`; `adbc_get_table_types()` → `isinstance(x, list)`; create a table, `adbc_get_table_schema("t")` → `isinstance(x, pyarrow.Schema)` and field names match; assert `pool.checkedout() == 0` after checkin.
- **`test_meta_stream.py`**: `async with await conn.adbc_get_objects(depth="tables") as reader:` → `reader.schema` is a `pyarrow.Schema`; `async for batch in reader:` yields `pyarrow.RecordBatch`; drains and `pool.checkedout() == 0`. (Optional busy-guard leg per Open Question 1: a foreign `await conn.commit()` while the reader is live raises `ConnectionBusyError`.)
- **`test_meta_unsupported.py`** (META-03): `with pytest.raises(adbc_driver_manager.NotSupportedError): await conn.adbc_get_statistics()` and same for `adbc_get_statistic_names()`. [VERIFIED both raise on DuckDB]
- **`test_meta_signature.py`**: `hasattr(AsyncConnection, name)` for all six; `inspect.signature` asserts kw-only params of `adbc_get_objects`/`adbc_get_table_schema`/`adbc_get_statistics` are `KEYWORD_ONLY` and `table_name` is positional. (Mirror `test_ingest_signature.py`.)

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/async/test_meta_*.py -x` + `.venv/bin/basedpyright src/adbc_poolhouse/_async/_connection.py`
- **Per wave merge:** `.venv/bin/pytest tests/async -q` (+ `ADBC_ASYNC_REPEAT=20` if any cancel/streaming leg is added — carried-forward loop-stability gotcha)
- **Phase gate:** full async suite green + basedpyright 0 errors + `mkdocs build --strict` exit 0 before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/async/test_meta_signature.py` — META-01 signature/existence (RED first)
- [ ] `tests/async/test_meta_roundtrip.py` — META-01/02 value methods
- [ ] `tests/async/test_meta_stream.py` — META-02 streaming reader
- [ ] `tests/async/test_meta_unsupported.py` — META-03 native error
- [ ] No new fixtures needed — `duckdb_async_pool` + `anyio_backend` already exist in `tests/async/conftest.py`
- [ ] No framework install needed

*New test files must observe the `tests/async/` discipline (`@pytest.mark.anyio` on every async test, no `import asyncio`, no positive-duration `sleep`) or the existing `test_meta_guard.py` meta-guard fails.*

## Docs Surface (META-04)

| Location | Change | Notes |
|----------|--------|-------|
| `docs/src/guides/async.md` lines 23-31 (the "Experimental" warning) | Remove the **Async ADBC metadata** bullet (line 25); add metadata to the "What you get today" paragraph | Leave the prepared-statements bullet — Phase 35 removes it. Do NOT drop the whole warning block |
| `docs/src/guides/async.md` (new section) | Add a "Connection metadata" how-to section: `get_info`/`get_table_schema`/`get_table_types` + streaming `get_objects` example, with the "can't abort in-flight" + reader-lifetime note | Follow docs-author voice (second person, "See also"); illustrative snippets, MkDocs tabs if a driver variant helps |
| API reference | **No `gen_ref_pages.py` change.** The existing `::: adbc_poolhouse._async._connection.AsyncConnection` block (`members_order: source`, `filters: ["!^__"]`) auto-renders the six new **public** methods | [VERIFIED: `gen_ref_pages.py` reading] Contrast Phase 29, which needed a new class block. Here only docstrings drive the render |
| Docstrings (source) | Each of the six methods needs Google-style **Markdown** (not RST) docstring: Args/Returns/Raises + an `Example:` (singular) fenced `python` block | [CITED: MEMORY.md docstring style + SKILL.md]. Document the non-cancellable caveat (commit/rollback wording) and, for the streaming trio, the reader-lifetime lock (fetch_record_batch wording) |
| Humanizer pass | Apply to all new/rewritten prose | Per CLAUDE.md gate + SKILL.md Step 3 |
| `docs/src/changelog.md` | **Out of scope** — version bump + changelog is the deferred release step after Phase 35 (STATE.md) | Do not add here |

## Project Constraints (from CLAUDE.md)

- **Docs-author skill is mandatory:** include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in every PLAN's `<execution_context>` (phase ≥ 7).
- **Docs are a completion requirement for the phase**, not just doc tasks: all six new public methods need Google-style docstrings (Args/Returns/Raises + `Example:`); the async guide reflects the new behavior; `uv run mkdocs build --strict` (use `.venv/bin/mkdocs` under sandbox) passes; humanizer pass applied.
- **Docstring style (MEMORY.md):** Google-style, **Markdown** syntax (`` `create_pool` ``, never RST `:func:`), `Example:` singular = admonition with ` ```python ` fenced block.
- **Workflow gotchas (MEMORY.md):** trust git tags/pyproject over STATE frontmatter; prefer `.venv/bin/<tool>`; `.venv/bin/basedpyright` is authoritative (harness Pyright false import errors); loop concurrency tests ×20; edit STATE/ROADMAP/REQUIREMENTS by hand + `query commit --files` (gsd-tools lacks mutation handlers); GSD decision-coverage gate ignores `<threat_model>` cells — cite decisions in must_haves/truths, and `## Gaps Summary` should read "No gaps" cleanly.

## Security Domain

> `security_enforcement` not set to `false` — section included. This phase adds no auth, session, crypto, or new external input surface; it forwards driver introspection calls off-loop.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | connection auth handled at pool/config layer, unchanged |
| V3 Session Management | no | — |
| V4 Access Control | no | metadata visibility is the driver's/warehouse's concern |
| V5 Input Validation | minimal | `table_name`/filter args are forwarded to the driver untouched (same contract as `adbc_ingest` — poolhouse does not quote/sanitize; the driver owns identifier handling) |
| V6 Cryptography | no | — |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Identifier/filter injection via `table_name`/`*_filter` | Tampering | Forward to the driver unchanged; document (as `adbc_ingest` does) that poolhouse does not sanitize — the ADBC driver owns the metadata query |
| Connection left busy/poisoned after a cancelled metadata call | Denial of Service | Reuse of `_offloading()` + shielded `invalidate` (inherited from the reader) keeps `pool.checkedout()` correct; loop-stability ×20 gate for any cancel leg |

## Sources

### Primary (HIGH confidence)
- `adbc_driver_manager` 1.11.0 — `inspect.signature` of the six `dbapi.Connection.adbc_get_*` methods (exact args + return types) [VERIFIED]
- DuckDB behavior probe — which four methods succeed / which two raise `NotSupportedError`, and their return types [VERIFIED]
- Fairy `__getattr__` probe — `getattr(fairy, "adbc_get_*")()` works with no unwrap [VERIFIED]
- basedpyright strict probes — fairy metadata attrs resolve to `Any`; both direct-`Any` and Protocol+`cast` pass strict; `reveal_type` on `fairy.commit` vs `fairy.adbc_get_info` [VERIFIED]
- `src/adbc_poolhouse/_async/_connection.py`, `_cursor.py`, `_reader.py`, `_offload.py`, `_cancel.py` — templates + guard semantics [VERIFIED, read in full]
- `docs/scripts/gen_ref_pages.py`, `docs/src/guides/async.md`, `mkdocs.yml` — docs render path + caveat location [VERIFIED]
- `tests/async/conftest.py`, `test_ingest_roundtrip.py`, `test_ingest_signature.py`, `test_reader_lifetime.py`, `test_meta_guard.py`, `tests/_async_harness/guard.py` — test templates + guard discipline [VERIFIED]

### Secondary (MEDIUM confidence)
- STATE.md / ROADMAP.md / REQUIREMENTS.md — phase scope, A1 cassette resolution, carried-forward gotchas [CITED]
- MEMORY.md, CLAUDE.md, SKILL.md — docstring/docs conventions [CITED]

### Tertiary (LOW confidence)
- None. All load-bearing claims were tool-verified in this session.

## Metadata

**Confidence breakdown:**
- Standard stack / signatures: HIGH — introspected from the installed driver
- Architecture / wiring: HIGH — exact clones of verified in-repo templates (commit/rollback, fetch_record_batch)
- Pitfalls: HIGH — cancel-hook tolerance and `_reader_open` timing read directly from source
- DuckDB test behavior (META-03): HIGH — both unsupported methods verified to raise `NotSupportedError`
- Snowflake metadata behavior: N/A automated (manual-only, Pitfall 2)

**Research date:** 2026-07-04
**Valid until:** ~2026-08-04 (stable; re-verify signatures only if `adbc_driver_manager` is upgraded past 1.11.0)
