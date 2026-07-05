# Phase 34: Async Metadata - Pattern Map

**Mapped:** 2026-07-04
**Files analyzed:** 6 (1 source modified + 4 new test files + 1 docs guide edited)
**Analogs found:** 6 / 6 (every artifact has an in-repo template; zero new machinery)

> RESEARCH.md (§Architecture Patterns) is authoritative and already names the analog
> templates. This map pins each to concrete line ranges verified against source, so the
> planner can cite "copy lines X–Y of file Z" directly in each PLAN action.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/adbc_poolhouse/_async/_connection.py` — `_SyncConnection` Protocol | model (structural type) | transform (typing bridge) | `_SyncCursor` Protocol in `_async/_cursor.py` L58–95 | exact |
| `_connection.py` — `adbc_get_info`, `adbc_get_table_types` (value, no args) | service method | request-response (value) | `AsyncConnection.commit` L245–266 / `rollback` L268–284 | exact |
| `_connection.py` — `adbc_get_table_schema` (value, kw-args) | service method | request-response (value) | `commit` + `AsyncCursor.adbc_ingest` `functools.partial` L550–564 | exact (composite) |
| `_connection.py` — `adbc_get_objects` / `adbc_get_statistics` / `adbc_get_statistic_names` (stream) | service method | streaming | `AsyncCursor.fetch_record_batch` in `_cursor.py` L566–626 | exact |
| `_connection.py` — `_noop_cancel` module fn | utility | — | `_pull` module fn in `_async/_reader.py` L96–121 | role-match (module-level guard-clean fn) |
| `tests/async/test_meta_signature.py` | test | — | `tests/async/test_ingest_signature.py` (whole file) | exact |
| `tests/async/test_meta_roundtrip.py` | test | request-response (value) | `tests/async/test_ingest_roundtrip.py` (whole file) | exact |
| `tests/async/test_meta_stream.py` | test | streaming | `tests/async/test_reader_lifetime.py` L54–127 (DuckDB legs only) | exact |
| `tests/async/test_meta_unsupported.py` | test | error-surfacing | `test_reader_lifetime.py::pytest.raises(ArrowInvalid)` L101/126 + `test_df_missing_dep.py` (native-error propagation) | role-match |
| `docs/src/guides/async.md` | docs | — | existing async.md caveat block L23–31 + prose sections | in-place edit (see RESEARCH §Docs Surface) |

## Pattern Assignments

### `_SyncConnection` Protocol (`_connection.py`, model / typing bridge)

**Analog:** `_SyncCursor` Protocol, `src/adbc_poolhouse/_async/_cursor.py` L58–95.

Mirror the structural-Protocol idiom exactly: driver-agnostic, declared not imported,
methods typed with precise returns. Add it to `_connection.py` (NOT `_cursor.py`).

**Protocol shape to copy** (`_cursor.py` L58–95, condensed):
```python
class _SyncCursor(Protocol):
    """Structural type for the sync ADBC dbapi cursor surface `AsyncCursor` offloads."""
    @property
    def description(self) -> object: ...
    def execute(self, operation: str, parameters: object = ..., /) -> object: ...
    def fetch_arrow_table(self) -> pyarrow.Table: ...
    def adbc_ingest(self, table_name: str, ..., *, catalog_name: str | None = ..., ...) -> int: ...
```

**New `_SyncConnection` (per RESEARCH §Pattern 3, signatures from §Standard Stack L84–96):**
```python
class _SyncConnection(Protocol):
    """Structural type for the sync ADBC dbapi Connection metadata surface (mirrors _SyncCursor)."""
    def adbc_get_info(self) -> dict[str | int, Any]: ...
    def adbc_get_objects(self, *, depth: Literal["all","catalogs","db_schemas","tables","columns"] = ...,
                         catalog_filter: str | None = ..., db_schema_filter: str | None = ...,
                         table_name_filter: str | None = ..., table_types_filter: list[str] | None = ...,
                         column_name_filter: str | None = ...) -> pyarrow.RecordBatchReader: ...
    def adbc_get_table_schema(self, table_name: str, *, catalog_filter: str | None = ...,
                              db_schema_filter: str | None = ...) -> pyarrow.Schema: ...
    def adbc_get_table_types(self) -> list[str]: ...
    def adbc_get_statistics(self, *, catalog_filter: str | None = ..., db_schema_filter: str | None = ...,
                            table_name_filter: str | None = ..., approximate: bool = ...) -> pyarrow.RecordBatchReader: ...
    def adbc_get_statistic_names(self) -> pyarrow.RecordBatchReader: ...
```

**cast-bridge pattern** — mirror `AsyncConnection.cursor` L239–242, which already casts the
fairy's proxied surface to a Protocol at the call site:
```python
# _connection.py L239-242 (VERIFIED template for the cast idiom)
sync_cursor = cast("_SyncCursor", self._fairy.cursor())
return AsyncCursor(sync_cursor, self._limiter, self)
```
Per-method usage in Phase 34: `sync_conn = cast("_SyncConnection", self._fairy)` at the top
of each of the six methods (the fairy is already `self._fairy`; no `.cursor()` call).

**Imports to add to `_connection.py`:** `functools` (runtime, like `_cursor.py` L35);
`Any` and `Literal` (add to the `typing` / `TYPE_CHECKING` imports, mirror `_cursor.py`
L36 + L47); runtime import of `AsyncRecordBatchReader` (mirror `_cursor.py` L42:
`from adbc_poolhouse._async._reader import AsyncRecordBatchReader`); `pyarrow` under
`TYPE_CHECKING` (mirror `_cursor.py` L51). `offload` and `cast` are already imported in
`_connection.py` (L38, L43). NOTE: do **not** import `cancellable_offload` — locked
decision #2 uses plain `offload` only.

---

### Value-returning methods: `adbc_get_info`, `adbc_get_table_types`, `adbc_get_table_schema`

**Analog:** `AsyncConnection.commit`, `_connection.py` L245–266 (and `rollback` L268–284).

**Core pattern to clone** (`_connection.py` L265–266, the entire body of `commit`):
```python
with self._offloading():
    await offload(self._fairy.commit, limiter=self._limiter)
```

Apply verbatim shape for the two no-arg methods, swapping the bound method and adding the
`cast` + return:
```python
async def adbc_get_info(self) -> dict[str | int, Any]:
    sync_conn = cast("_SyncConnection", self._fairy)
    with self._offloading():
        return await offload(sync_conn.adbc_get_info, limiter=self._limiter)
```

**Keyword forwarding** for `adbc_get_table_schema` — copy the `functools.partial` boundary
from `AsyncCursor.adbc_ingest`, `_cursor.py` L550–564:
```python
# _cursor.py L550-564 (VERIFIED functools.partial-through-offload template)
with self._owner._offloading():
    return await cancellable_offload(
        self._adbc_cancel,
        functools.partial(
            self._cursor.adbc_ingest, table_name, data,
            mode=mode, catalog_name=catalog_name,
            db_schema_name=db_schema_name, temporary=temporary,
        ),
        limiter=self._limiter,
        on_abort=self._owner.invalidate,
    )
```
Phase 34 adaptation: use **plain `offload`** (NOT `cancellable_offload`, no `on_abort`),
wrap `sync_conn.adbc_get_table_schema` in `functools.partial` with `table_name` positional +
`catalog_filter`/`db_schema_filter` keywords (see RESEARCH §Pattern 1 L182–194).

**Non-cancellable caveat docstring** — copy the wording from `commit` L253–259 verbatim
("Unlike the cursor's `execute`/`fetch*`, this call is **not** cooperatively cancellable…
a surrounding timeout or cancellation cannot abort an in-flight [call]").

---

### Streaming methods: `adbc_get_objects`, `adbc_get_statistics`, `adbc_get_statistic_names`

**Analog:** `AsyncCursor.fetch_record_batch`, `_cursor.py` L566–626.

**Core pattern to clone** (`_cursor.py` L607–626 — the guard span, post-span `_reader_open`,
and reader construction):
```python
# _cursor.py L607-626 (VERIFIED streaming-reader template)
with self._owner._offloading():  # foreign-tier guard: _in_use OR _reader_open
    sync_reader = await cancellable_offload(
        self._adbc_cancel,
        self._cursor.fetch_record_batch,
        limiter=self._limiter,
        on_abort=self._owner.invalidate,
    )
# Set AFTER the span exits, success path ONLY (Pitfall 5 / Pitfall 3):
self._owner._reader_open = True
return AsyncRecordBatchReader(sync_reader, self._limiter, self._owner, self._adbc_cancel)
```

**Phase 34 adaptations (all from locked decisions #2 + Pitfall 1):**
1. Method lives on `AsyncConnection`, so `self._offloading()` and `self._reader_open` (no
   `self._owner.` indirection — the connection *is* the owner).
2. Replace `cancellable_offload(self._adbc_cancel, fn, …, on_abort=…)` with **plain**
   `offload(fn, limiter=self._limiter)` — connection has no `adbc_cancel` (locked #2).
3. Wrap the driver call in `functools.partial` when it has kw-only filters
   (`adbc_get_objects`, `adbc_get_statistics`); `adbc_get_statistic_names` is a bare bound
   method (no partial).
4. Construct `AsyncRecordBatchReader(sync_reader, self._limiter, self, _noop_cancel)` — the
   4th positional arg is the module-level `_noop_cancel`, NOT a cursor cancel.

**`_reader_open` timing is load-bearing** (Pitfall 3): set it AFTER the `with
self._offloading():` block, on the success path only. Copy the L614–618 comment rationale.

**`AsyncRecordBatchReader` constructor contract** — `_reader.py` L162–193: 4th positional arg
is `adbc_cancel: Callable[[], None]`, invoked ONLY on the cancel path inside `__anext__`
(L251–252), so a no-op is harmless (Pitfall 1). Do NOT omit it (TypeError) and do NOT pass
an `async` cancel ("coroutine never awaited").

---

### `_noop_cancel` module-level function (`_connection.py`, utility)

**Analog:** `_pull`, `src/adbc_poolhouse/_async/_reader.py` L96–121 — the codebase convention
for a **module-level** function kept out of a lambda "so it preserves the `cancellable_offload`
`TypeVarTuple` arity and keeps the `scan_async_package` source guard's matcher clean"
(`_reader.py` L109–110). Same reasoning applies here (RESEARCH §Alternatives L114).

```python
def _noop_cancel() -> None:
    """No-op cancel hook for connection-level metadata readers (no adbc_cancel exists)."""
```
Place at module level in `_connection.py`, alongside where `_SyncConnection` is declared.

---

### Test file: `tests/async/test_meta_signature.py`

**Analog:** `tests/async/test_ingest_signature.py` (whole file, 77 lines).

Clone the `inspect.signature` structure L47–67. For each of the six methods assert
`hasattr(AsyncConnection, name)` (L36 pattern) and that kw-only params of `adbc_get_objects`
/ `adbc_get_table_schema` / `adbc_get_statistics` are `KEYWORD_ONLY`, and `table_name` is
positional (mirror `_KEYWORD_ONLY` / `_POSITIONAL` constants L28–31 + the two loop tests
L39–67). Import target changes to `from adbc_poolhouse._async._connection import
AsyncConnection`. NO `@pytest.mark.anyio` needed — these are sync introspection tests (like
`test_ingest_signature.py`, which carries none).

---

### Test file: `tests/async/test_meta_roundtrip.py`

**Analog:** `tests/async/test_ingest_roundtrip.py` (whole file, 98 lines).

Clone the class + `@pytest.mark.anyio async def` + `duckdb_async_pool` fixture shape
(L33–66). Per RESEARCH §Concrete test designs L395:
- `adbc_get_info()` → `isinstance(x, dict)`
- `adbc_get_table_types()` → `isinstance(x, list)`
- create a table (reuse `adbc_ingest` or `execute CREATE`), `adbc_get_table_schema("t")` →
  `isinstance(x, pyarrow.Schema)`, field names match
- assert `duckdb_async_pool._pool.checkedout() == 0` after the `async with` (copy the
  `# noqa: SLF001` accessor from `test_reader_lifetime.py` L75).

Import `pyarrow` at top like `test_ingest_roundtrip.py` L26.

---

### Test file: `tests/async/test_meta_stream.py`

**Analog:** `tests/async/test_reader_lifetime.py` L54–127 (DuckDB `TestStream04DrainThenCheckin`
+ read-after-close legs; do NOT copy the Snowflake `TestEdge33Snowflake` legs — Pitfall 2).

Clone the `async with await ... as reader: / async for batch in reader:` drain pattern
(L69–76). Per RESEARCH §Concrete test designs L396:
- `async with await conn.adbc_get_objects(depth="tables") as reader:` → `reader.schema` is a
  `pyarrow.Schema`; `async for batch in reader:` yields `pyarrow.RecordBatch`; drain and
  `checkedout() == 0`.
- OPTIONAL busy-guard leg (Open Question 1, ~10 lines): a foreign `await conn.commit()` while
  the reader is live raises `ConnectionBusyError` — locks locked-decision #5 cheaply.

The `_LIFETIME_LOOPS` repeat + `concurrency_marks` structure (L38–42) is available if a
cancel/streaming leg is added; a plain happy-path drain does not require the loop gate, but
per the carried-forward gotcha run `ADBC_ASYNC_REPEAT=20` at wave merge for any streaming leg.

---

### Test file: `tests/async/test_meta_unsupported.py` (META-03)

**Analog (structure):** `test_reader_lifetime.py::pytest.raises(pyarrow.ArrowInvalid, …)`
L101 / L126 — the native-driver-error assertion idiom. **Analog (intent):**
`test_df_missing_dep.py` — surfacing a native error unchanged with no poolhouse wrapping
(DF-03 mirror of META-03).

Per RESEARCH §Concrete test designs L397 (both VERIFIED to raise on DuckDB):
```python
@pytest.mark.anyio
async def test_get_statistics_unsupported_duckdb(self, duckdb_async_pool: AsyncPool) -> None:
    async with await duckdb_async_pool.connect() as conn:
        with pytest.raises(adbc_driver_manager.NotSupportedError):
            await conn.adbc_get_statistics()
```
Same for `adbc_get_statistic_names()`. Import `adbc_driver_manager` at top. Assert
`checkedout() == 0` after to prove the failed call still checks in cleanly.

## Shared Patterns

### Two-tier offload guard (`_offloading()`)
**Source:** `AsyncConnection._offloading` / `_enter_offload`, `_connection.py` L149–224.
**Apply to:** all six new methods — each brackets its offload in `with self._offloading():`.
Already on the class; no new flag logic. Foreign tier (`_in_use` OR `_reader_open`) is the
default; the streaming trio set `_reader_open` AFTER the span (never inside).

### Single offload chokepoint
**Source:** `offload`, `_async/_offload.py` L41–46 (`offload(fn, *args, limiter=…)`).
**Apply to:** all six methods. Plain `offload` only (locked #2) — the source guard
(`scan_async_package`) forbids any other `to_thread` call; `functools.partial` (not
arg-spread) preserves the `TypeVarTuple` arity for kw-bearing methods.

### Non-cancellable-caveat docstring wording
**Source:** `commit` docstring, `_connection.py` L253–259.
**Apply to:** all six method docstrings — "not cooperatively cancellable; a surrounding
timeout/cancellation cannot abort an in-flight call." For the streaming trio ALSO document
the reader-lifetime lock (copy `fetch_record_batch` docstring `_cursor.py` L576–588) and the
per-pull-invalidate asymmetry (Pitfall 1 / A2): a cancelled pull invalidates the connection.

### Google-style Markdown docstrings + `Example:` (project gate)
**Source:** `adbc_ingest` docstring `_cursor.py` L489–548 (full Args/Returns/Raises + singular
`Example:` fenced ```python``` block). **Apply to:** all six public methods — CLAUDE.md +
MEMORY.md require Google-style **Markdown** (never RST `:func:`), `Example:` singular =
admonition. Docs-author skill (`@.claude/skills/adbc-poolhouse-docs-author/SKILL.md`) is
mandatory in each PLAN `<execution_context>` (phase ≥ 7).

### Test discipline (meta-guard)
**Source:** `test_meta_guard.py` + `tests/_async_harness/guard.py`.
**Apply to:** all four new test files — every `async def test_*` carries `@pytest.mark.anyio`,
NO `import asyncio`, NO positive-duration `sleep`. `duckdb_async_pool` + `anyio_backend`
fixtures already exist in `tests/async/conftest.py` (L58–107); no new fixtures needed.

## No Analog Found

None. Every artifact clones an existing, tested template.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| — | — | — | All six methods + four test files + the Protocol + the docs edit have exact or composite in-repo analogs (see table above). RESEARCH §Don't Hand-Roll L249–257 confirms "every building block already exists." |

## Metadata

**Analog search scope:** `src/adbc_poolhouse/_async/` (`_connection.py`, `_cursor.py`,
`_reader.py`, `_offload.py`), `tests/async/` (conftest + ingest/reader/df/meta-guard tests).
**Files scanned (read in full):** 8 — `_connection.py` (376 L), `_cursor.py` (670 L),
`_reader.py` (333 L), `_offload.py` (110 L), `conftest.py` (194 L), `test_ingest_signature.py`
(77 L), `test_ingest_roundtrip.py` (98 L), `test_reader_lifetime.py` (199 L); `test_meta_guard.py`
partial.
**Pattern extraction date:** 2026-07-04
