# Phase 35: Async Prepared Statements - Pattern Map

**Mapped:** 2026-07-04
**Files analyzed:** 5 (2 source edits, 1 harness edit, ~5 new test modules, 2 docs edits)
**Analogs found:** 5 / 5 (every target has an exact same-repo analog — this phase is 100% reuse)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/adbc_poolhouse/_async/_cursor.py` (add `adbc_prepare` + `adbc_execute_schema` methods) | wrapper / cursor method | request-response (offload) | `AsyncCursor.execute` `_cursor.py:200-229` | exact (twin, minus `on_abort`) |
| `src/adbc_poolhouse/_async/_cursor.py` (extend `_SyncCursor` Protocol) | Protocol / structural type | — | `_SyncCursor.adbc_ingest`/`fetch_df` signatures `_cursor.py:75-95` | exact |
| `tests/_async_harness/stubs.py` (extend `BlockingStubCursor`) | test harness / stub | event-driven (blocking gate) | `BlockingStubCursor.adbc_ingest` `stubs.py:397-441` | exact |
| `tests/async/test_prep_signature.py` (new) | test | introspection | `tests/async/test_ingest_signature.py` | exact |
| `tests/async/test_prep_roundtrip.py` (new) | test | integration (DuckDB) | `tests/async/test_ingest_roundtrip.py` | exact |
| `tests/async/test_prep_no_execute.py` (new) | test | unit (blocking stub) | `tests/async/test_ingest_roundtrip.py` + stub counter | role-match |
| `tests/async/test_prep_unsupported.py` (new) | test | integration (DuckDB error) | `tests/async/test_meta_unsupported.py` | role-match |
| `tests/async/test_prep_cancel.py` (new) | test | concurrency (cancel) | `test_ingest_cancel.py` (cursor cancel) + `test_meta_cancel.py` (no-invalidate) | hybrid |
| `docs/src/guides/async.md` (caveat removal + snippet) | docs | — | `.planning/phases/34-async-metadata/34-03-PLAN.md` | exact |
| `docs/src/index.md:71` (stale clause fix) | docs | — | same 34-03 caveat-shrink pattern | role-match |

## Pattern Assignments

### `src/adbc_poolhouse/_async/_cursor.py` — the two new methods (wrapper, request-response)

**Analog:** `AsyncCursor.execute` at `_cursor.py:200-229` (the EXACT template — clone twice, swap callable + return type, DROP `on_abort`).

**The template to clone (`_cursor.py:221-229`):**
```python
with self._owner._offloading():  # noqa: SLF001 (intentional parent guard, see module docstring)
    await cancellable_offload(
        self._adbc_cancel,
        self._cursor.execute,
        operation,
        parameters,
        limiter=self._limiter,
        on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
    )
```

**Target `adbc_prepare` (D-35-02/04) — positional `operation`, `cast`, NO `on_abort`:**
```python
async def adbc_prepare(self, operation: bytes | str) -> pyarrow.Schema | None:
    with self._owner._offloading():  # noqa: SLF001
        return cast(
            "pyarrow.Schema | None",
            await cancellable_offload(
                self._adbc_cancel,
                self._cursor.adbc_prepare,
                operation,                # positional — NO functools.partial (D-35-02)
                limiter=self._limiter,
                # on_abort OMITTED (D-35-04): cancellable but non-poisoning
            ),
        )
```

**Target `adbc_execute_schema` (D-35-03/04) — forwards `operation` + `parameters` positionally:**
```python
async def adbc_execute_schema(
    self, operation: str, parameters: object = None
) -> pyarrow.Schema:
    with self._owner._offloading():  # noqa: SLF001
        return cast(
            "pyarrow.Schema",
            await cancellable_offload(
                self._adbc_cancel,
                self._cursor.adbc_execute_schema,
                operation,
                parameters,               # positional, exactly as execute forwards it
                limiter=self._limiter,
                # on_abort OMITTED (D-35-04)
            ),
        )
```

**The `cast` idiom** — copy from `fetch_df` (`_cursor.py:412-425`), which casts a `-> object` Protocol return back to the public type. The Protocol declares `-> object` (see below); the public method `cast`s. No runtime effect.

**`_adbc_cancel` resolver** — reused unchanged, `_cursor.py:151-164`. Tolerates a missing hook (a non-blocking backend). Pass `self._adbc_cancel` as the 1st positional arg to `cancellable_offload`.

**`cancellable_offload` signature** — `_cancel.py:41-47`. `on_abort: Callable[[], Awaitable[None]] | None = None` — omitting it IS the non-poisoning path (D-35-04). Positional args are forwarded through `*args: Unpack[_Ts]`.

**ANTI-PATTERN — do NOT clone `adbc_ingest` (`_cursor.py:479-564`):** it uses `functools.partial` for its keyword-only args. Both new methods forward plain positionals, so a partial adds noise and diverges from `execute` (D-35-02/03, RESEARCH Anti-Patterns).

**Imports** — `cast`, `cancellable_offload` are already imported at `_cursor.py:36,40`. `functools` (line 35) is NOT needed for these two methods. `pyarrow` is already in the `TYPE_CHECKING` block (`_cursor.py:51`). No new imports required.

---

### `src/adbc_poolhouse/_async/_cursor.py` — `_SyncCursor` Protocol extension (D-35-05)

**Analog:** the existing Protocol method lines `_cursor.py:75-95` (`execute`, `fetch_df`, `adbc_ingest` all typed `-> object` with `/` positional markers).

**Existing style to match (`_cursor.py:75,82`):**
```python
def execute(self, operation: str, parameters: object = ..., /) -> object: ...
def fetch_df(self) -> object: ...
```

**Add these two lines to the `_SyncCursor` Protocol body (after line 94, near `adbc_cancel`):**
```python
def adbc_prepare(self, operation: bytes | str, /) -> object: ...
def adbc_execute_schema(self, operation: str, parameters: object = ..., /) -> object: ...
```

Return type stays `-> object` to keep the layer driver-agnostic and stub-testable; the public method casts back. Must stay basedpyright-strict-clean (`.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py` → 0 errors).

---

### `tests/_async_harness/stubs.py` — `BlockingStubCursor` extension (harness, event-driven)

**Analog:** `BlockingStubCursor.adbc_ingest` at `stubs.py:397-441` — record call under lock, `self._block()`, return an injectable value.

**Counter-init pattern (`stubs.py:178-180`):**
```python
self.execute_call_count: int = 0
self.fetch_call_count: int = 0
self.ingest_call_count: int = 0
```
Add alongside these (in `__init__`, ~line 180): `self.prepare_call_count: int = 0`, `self.execute_schema_call_count: int = 0`, plus injectable results `self._prepare_result: object = None`, `self._execute_schema_result: object = None` (settable on `cursors[-1]`, mirroring `_fetch_df_raises` at `stubs.py:184`).

**The `adbc_ingest` blocking-method body to mirror (`stubs.py:437-441`):**
```python
del table_name, data, mode, catalog_name, db_schema_name, temporary
with self._lock:
    self.ingest_call_count += 1
self._block()
return 3
```

**Target additions (RESEARCH §Harness extension):**
```python
def adbc_prepare(self, operation: object = None) -> object:
    del operation
    with self._lock:
        self.prepare_call_count += 1
    self._block()
    return self._prepare_result           # injectable: sentinel pyarrow.Schema OR None

def adbc_execute_schema(self, operation: object = None, parameters: object = None) -> object:
    del operation, parameters
    with self._lock:
        self.execute_schema_call_count += 1
    self._block()
    return self._execute_schema_result    # injectable sentinel pyarrow.Schema
```

**CRITICAL invariant (PREP-02 no-execute proof):** neither method may touch `execute_call_count` — the no-execute test asserts `stub_cursor.execute_call_count == 0`. Cancel/close/release wiring is already handled by the sticky `_cancelled`/`_closed` flags in `_block` (`stubs.py:283-297`) and `adbc_cancel` (`stubs.py:443-467`); no new cancel code is needed in these methods (same as `adbc_ingest`).

**Public-attribute contract:** the `Attributes:` docstring block (`stubs.py:108-124`) lists every locked counter (`ingest_call_count`, `df_call_count`, ...); add `prepare_call_count` / `execute_schema_call_count` there to keep the D-04 hard-contract docstring complete.

---

### `tests/async/test_prep_signature.py` (new) — introspection RED

**Analog:** `tests/async/test_ingest_signature.py` (whole file) — `inspect.signature` over the public method + `hasattr` existence check.

Copy the `test_adbc_ingest_exists_on_async_cursor` shape (`test_ingest_signature.py:34-36`):
```python
def test_adbc_ingest_exists_on_async_cursor() -> None:
    assert hasattr(AsyncCursor, "adbc_ingest"), "AsyncCursor.adbc_ingest not defined yet"
```
For Phase 35 assert `hasattr(AsyncCursor, "adbc_prepare")` and `hasattr(AsyncCursor, "adbc_execute_schema")`. Simpler than ingest: both new methods forward positionals, so there is **no** keyword-only assertion to make — just existence + awaitability (and basedpyright-strict as the authoritative Protocol-coverage gate, per the module docstring `test_ingest_signature.py:11-14`).

---

### `tests/async/test_prep_roundtrip.py` (new) — DuckDB positive for `adbc_prepare`

**Analog:** `tests/async/test_ingest_roundtrip.py::TestIngest01RoundTrip` (`test_ingest_roundtrip.py:33-65`) — `@pytest.mark.anyio`, `duckdb_async_pool` fixture, `async with await pool.connect()`.

Skeleton to adapt:
```python
@pytest.mark.anyio
async def test_prepare_round_trip(self, duckdb_async_pool: AsyncPool) -> None:
    async with await duckdb_async_pool.connect() as conn:
        cursor = conn.cursor()
        result = await cursor.adbc_prepare("SELECT * FROM t WHERE id = ?")
        assert isinstance(result, (pyarrow.Schema, type(None)))  # Pitfall 2: do NOT assert non-null
    assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001  (no reader lifetime lock)
```
The `pool.checkedout() == 0` after-scope assertion is copied from `test_ingest_cancel.py:156-158`. `adbc_prepare` needs a table to reference — create it first via `adbc_ingest`/`execute` as in the ingest round-trip.

---

### `tests/async/test_prep_no_execute.py` (new) — stub value + `execute_call_count == 0`

**Analog:** the `make_stub_async_connection` fixture usage in `test_ingest_cancel.py:80-83` (checkout stub, grab `stub_conn.cursors[-1]`) combined with the injectable-result stub method above.

Design (RESEARCH Test design notes):
1. Inject a sentinel: `stub_conn.cursors[-1]._execute_schema_result = <a pyarrow.Schema>`.
2. `result = await cur.adbc_execute_schema("SELECT 1")` — release the stub gate so it returns.
3. Assert `result is <sentinel>` **and** `stub_cursor.execute_call_count == 0` (the PREP-02 no-execute proof). DuckDB cannot host this leg — it raises `NotSupportedError`.

---

### `tests/async/test_prep_unsupported.py` (new) — DuckDB native-error passthrough (EDGE-17)

**Analog:** `tests/async/test_meta_unsupported.py` (the metadata `NotSupportedError`-passthrough leg — same DuckDB-raises-native pattern the async guide describes at `docs/src/guides/async.md:344-346`).

```python
@pytest.mark.anyio
async def test_execute_schema_unsupported_passthrough(self, duckdb_async_pool: AsyncPool) -> None:
    async with await duckdb_async_pool.connect() as conn:
        cursor = conn.cursor()
        with pytest.raises(adbc_driver_manager.NotSupportedError):
            await cursor.adbc_execute_schema("SELECT 1")
```
This doubles as the PREP-02 "no invented error type" assertion — the driver's native `NOT_IMPLEMENTED: AdbcStatementExecuteSchema not implemented` surfaces unwrapped through the single offload chokepoint.

---

### `tests/async/test_prep_cancel.py` (new) — deterministic cancel, non-poisoning (D-35-04)

**Hybrid analog — the phase's one real test:**
- **Cursor-cancel structure** from `test_ingest_cancel.py:61-95` (`real_clock_watchdog`, `await_inside`, `concurrency_marks`, task-group cancel, `finally: c.release()`).
- **Non-poisoning assertion** from `test_meta_cancel.py:103-107`: assert `invalidate_call_count == 0` (NOT `== 1`).

The critical difference from `test_ingest_cancel.py`: ingest asserts `invalidate_call_count == 1` (`test_ingest_cancel.py:94`), but Phase 35 asserts **`== 0`** because `on_abort` is omitted. Copy the gate + cancel scaffold, gate on `prepare_call_count >= 1` (or `execute_schema_call_count >= 1`) instead of `ingest_call_count >= 1`, then assert:
```python
assert tripped[0] is False
assert stub_cursor.adbc_cancel_call_count == 1  # cancellable (fired once)
assert stub_conn.invalidate_call_count == 0     # non-poisoning (D-35-04) — NOT 1
```
Harness discipline is load-bearing (MEMORY carried-forward gotchas): use `real_clock_watchdog` (a wall-clock side thread), NEVER `anyio.fail_after` as the watchdog (it autojumps under the trio `MockClock`); run under `ADBC_ASYNC_REPEAT=20`, both backends, 0 hangs (the timeout leg may still use `virtual_clock` + `anyio.fail_after` as the *trigger*, as in `test_ingest_cancel.py:96-127`).

---

### `docs/src/guides/async.md` + `docs/src/index.md:71` (docs, PREP-03)

**Analog:** `.planning/phases/34-async-metadata/34-03-PLAN.md` — the caveat-shrink + humanizer + strict-build pattern.

**Caveat block to remove entirely (`docs/src/guides/async.md:23-32`):** prepared statements is now the **last** bullet in the "not available yet" block (line 25). Per D-35-08 the whole `- It is also incomplete...` block goes, and the "What you get today" paragraph (lines 27-31) is updated to include the two new methods. (34-03 only shrank the block; Phase 35 removes it — the block is now a single bullet.)

**`docs/src/index.md:71` stale clause:** currently reads "async ADBC metadata **and** prepared statements have not shipped yet". Metadata shipped in Phase 34, so the ENTIRE clause is stale — drop it, not just the prepared-statements half (D-35-08).

**Add a short "prepare then execute" snippet** (Claude's Discretion, RESEARCH recommends it) as a plain fenced ```python block — NEVER wrapped in `!!! example` (MEMORY: authored docs use plain fenced blocks; the box is for prose callouts). Follow the existing guide section shape, e.g. the `adbc_ingest` section (`docs/src/guides/async.md:226-242`).

**Docstrings** — Google-style, Markdown (not RST), singular `Example:` admonition with a fenced ```python block, per CLAUDE.md + MEMORY. The `execute`/`adbc_ingest` docstrings (`_cursor.py:200-220`, `:489-548`) are the in-file voice template. API reference auto-renders both new symbols via the existing `AsyncCursor` mkdocstrings block (`filters: ["!^__"]`) — no nav or `:::` edit.

**Build gate:** `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` — check the exit code, not grep (34-03 acceptance). Humanizer pass on all new/rewritten prose.

## Shared Patterns

### Offload chokepoint + non-poisoning cancel (D-35-04)
**Source:** `cancellable_offload` `src/adbc_poolhouse/_async/_cancel.py:41-47`
**Apply to:** both new methods
```python
async def cancellable_offload(
    adbc_cancel: Callable[[], None],
    fn: Callable[[Unpack[_Ts]], _T],
    *args: Unpack[_Ts],
    limiter: CapacityLimiter,
    on_abort: Callable[[], Awaitable[None]] | None = None,  # OMIT → non-poisoning path
) -> _T:
```
Omitting `on_abort` means a cancelled call fires `adbc_cancel` once (worker-started gate) then re-raises the cancellation with NO `invalidate` — the exact two-axis point (cancellable AND non-poisoning) the phase introduces.

### Concurrency guard
**Source:** `AsyncConnection._offloading()` via `with self._owner._offloading():` (`_cursor.py:221`, every method)
**Apply to:** both new methods — reused unchanged; concurrent cursor use → `ConnectionBusyError`. Note the `# noqa: SLF001` on that line (intentional parent-guard reach-through, documented in the module docstring `_cursor.py:16-27`).

### Driver-agnostic Protocol + cast
**Source:** `_SyncCursor.fetch_df` `-> object` (`_cursor.py:82`) → public `cast("pandas.DataFrame", ...)` (`_cursor.py:417`)
**Apply to:** both new methods — Protocol returns `object`, public method casts to `pyarrow.Schema | None` / `pyarrow.Schema`.

### Native-error passthrough (EDGE-17)
**Source:** `_cancel.py` module docstring + non-cancel unwrap path `_cancel.py:240-245`
**Apply to:** `adbc_execute_schema` unsupported-backend leg — the single offload chokepoint re-raises the driver's native error (`NotSupportedError`) with exact type/traceback. Do NOT catch, wrap, or `find_spec`-pre-check (D-35-06).

## No Analog Found

_None._ Every target file has an exact or near-exact same-repo analog. This phase is the simplest in the milestone (100% reuse); the planner should not fall back to RESEARCH.md abstractions — the concrete analogs above cover every file.

## Metadata

**Analog search scope:** `src/adbc_poolhouse/_async/`, `tests/async/`, `tests/_async_harness/`, `docs/src/`, `.planning/phases/34-async-metadata/`
**Files scanned:** `_cursor.py`, `_cancel.py`, `stubs.py`, `async.md`, `index.md`, `test_ingest_{signature,roundtrip,cancel}.py`, `test_meta_{signature,cancel}.py`, `34-03-PLAN.md`
**Pattern extraction date:** 2026-07-04
