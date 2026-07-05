# Phase 31: DataFrame Convenience - Pattern Map

**Mapped:** 2026-07-02
**Files analyzed:** 8 (2 source-edit targets counted once, 6 new/edited test + config files)
**Analogs found:** 8 / 8 (all in-repo; zero no-analog files)

This phase adds zero new machinery. Every file is a clone/extension of an
already-shipped artifact in the same file or the sibling test suite. The
dominant risk (per RESEARCH + CONTEXT) is *over-engineering* — adding
`find_spec`, `try/except ImportError`, or `functools.partial` that the analogs
do not have. The correct posture is: copy the analog, change only the three
things a reviewer should see on a diff (callable, return annotation, docstring).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/adbc_poolhouse/_async/_cursor.py` — `AsyncCursor.fetch_df` / `fetch_polars` (new methods) | wrapper/method | request-response (whole-op offload) | same file, `fetch_arrow_table` (`_cursor.py:341-369`) | exact |
| `src/adbc_poolhouse/_async/_cursor.py` — `_SyncCursor` Protocol members (edit) | protocol | request-response | same file, `fetch_arrow_table` Protocol member (`_cursor.py:77`) | exact |
| `src/adbc_poolhouse/_async/_cursor.py` — `TYPE_CHECKING` import block (edit) | config/typing | n/a | same file, existing `if TYPE_CHECKING:` block (`_cursor.py:43-52`) | exact |
| `pyproject.toml` — `[dependency-groups].dev` (edit) | config | n/a | same file, existing dev group (`pyproject.toml:46-63`) | exact |
| `tests/_async_harness/stubs.py` — `BlockingStubCursor.fetch_df` / `fetch_polars` (+ raising injection, counters) | test/stub | request-response | same file, `adbc_ingest` stub (`stubs.py:317-361`), `fetch_arrow_table` stub (`stubs.py:304-315`) | exact |
| `tests/async/test_df_roundtrip.py` + `test_df_lifetime.py` (new, positive/importorskip) | test | request-response | `tests/async/test_ingest_roundtrip.py` | exact |
| `tests/async/test_df_signature.py` (new, introspection + import-surface) | test | request-response | `tests/async/test_ingest_signature.py` | role-match |
| `tests/async/test_df_missing_dep.py` + `test_df_busy.py` + `test_df_cancel.py` (new, stub-backed, looped) | test | request-response (concurrency) | `tests/async/test_ingest_cancel.py`, `tests/async/test_reader_busy.py` | exact |

## Pattern Assignments

### `AsyncCursor.fetch_df` / `fetch_polars` — new methods (wrapper, whole-op offload)

**Analog:** `src/adbc_poolhouse/_async/_cursor.py:341-369` (`fetch_arrow_table`) — the
byte-for-byte template. NOT `adbc_ingest` (`:371-456`), which uses
`functools.partial` because it forwards args; `fetch_df`/`fetch_polars` take no
args, so the callable is a **bare method reference** exactly like
`fetch_arrow_table`.

**Core offload pattern to clone** (`_cursor.py:363-369`):
```python
with self._owner._offloading():  # noqa: SLF001
    return await cancellable_offload(
        self._adbc_cancel,
        self._cursor.fetch_arrow_table,   # ← swap to self._cursor.fetch_df / self._cursor.fetch_polars
        limiter=self._limiter,
        on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
    )
```

The **only** three differences a reviewer should see per method (CONTEXT D-31-03,
RESEARCH Pattern 1):
1. Callable: `self._cursor.fetch_df` / `self._cursor.fetch_polars` (bare ref, no `functools.partial`, no args).
2. Return annotation: `-> pandas.DataFrame` / `-> polars.DataFrame` (a runtime string via `from __future__ import annotations` at `_cursor.py:32`).
3. Docstring prose (Google-style, per CLAUDE.md + MEMORY docstring rules).

**Method signature shape** (mirrors `fetch_arrow_table:341`):
```python
async def fetch_df(self) -> pandas.DataFrame:
    """..."""
```

**Anti-patterns (RESEARCH "Anti-Patterns to Avoid" + Pitfall 1/2):**
- NO `functools.partial` (unlike `adbc_ingest:445`) — both methods are zero-arg.
- NO `_reader_open` lifetime lock / new reader class (unlike `fetch_record_batch:499-518`) — whole-op offload, connection checks in immediately.
- NO `find_spec` / `try/except ModuleNotFoundError` anywhere (D-31-05).
- NO runtime `import pandas`/`import polars` outside `TYPE_CHECKING`.
- NO shielded scope (unlike `close:533`) — this is a normal cancellable offload.

**Docstring model:** copy the structure of the `fetch_arrow_table` docstring
(`_cursor.py:342-361`) — Returns + the standard CANCEL-01/02 cancellation
paragraph + `Raises: ConnectionBusyError`. Add an `Example:` block (singular,
admonition) as `adbc_ingest` does (`_cursor.py:431-440`). Guide note per CONTEXT
Claude's Discretion: "`fetch_df`/`fetch_polars` require you to install
pandas/polars yourself."

---

### `_SyncCursor` Protocol members — edit (protocol)

**Analog:** `src/adbc_poolhouse/_async/_cursor.py:77` (`fetch_arrow_table` Protocol
member). Place the two new members beside the existing `fetch_arrow_table` /
`fetch_record_batch` / `adbc_ingest` members (`_cursor.py:77-88`).

**Existing members to sit alongside** (`_cursor.py:77-78`):
```python
def fetch_arrow_table(self) -> pyarrow.Table: ...
def fetch_record_batch(self) -> pyarrow.RecordBatchReader: ...
```

**Members to add** (D-31-06, RESEARCH Pattern 2 — `-> object`, NOT `pandas.DataFrame`,
to keep the Protocol driver-agnostic and free of stub coupling):
```python
def fetch_df(self) -> object: ...
def fetch_polars(self) -> object: ...
```

---

### `TYPE_CHECKING` import block — edit (typing/config)

**Analog:** `src/adbc_poolhouse/_async/_cursor.py:43-52` (the existing block).

**Existing block** (`_cursor.py:43-52`):
```python
if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType
    from typing import Literal

    import pyarrow
    from anyio import CapacityLimiter
    from typing_extensions import CapsuleType

    from adbc_poolhouse._async._connection import AsyncConnection
```

**Add** (D-31-07, RESEARCH Pattern 3 — never imported at runtime; resolves the
public string annotations under the dev-group basedpyright):
```python
    import pandas
    import polars
```
Guard-safe: the import-lint guard (`tests/_async_harness/guard.py`) does not scan
pandas/polars, and these are under `TYPE_CHECKING` regardless — `scan_async_package`
stays `[]` (PKG-03). `from __future__ import annotations` at `_cursor.py:32` is
already present; keep it so the annotation strings are never evaluated.

**Module docstring note:** `_cursor.py:1-30` enumerates the offloaded surface
("`execute`, `executemany`, ... `fetch_arrow_table`, `adbc_ingest`, `close`"). Add
`fetch_df`/`fetch_polars` to that list for accuracy (docs quality gate, CLAUDE.md).

---

### `pyproject.toml` `[dependency-groups].dev` — edit (config)

**Analog:** `pyproject.toml:46-63` (the existing dev group; note `pyarrow>=23.0.1`
already lives here at `:53`).

**Existing block** (`pyproject.toml:46-63`) already contains `pyarrow`, `pytest`,
`anyio`, `trio`, `basedpyright`, etc. Add two entries (D-31-08, RESEARCH Standard
Stack A1 — floors are dev-only, planner may leave unpinned per STACK.md):
```toml
    "pandas>=2.0",
    "polars>=1.0",
```

**Constraints (PKG-02, D-31-08):**
- Do NOT add a `[pandas]`/`[polars]`/`[dataframe]` extra (permanently ruled out, STACK.md:91).
- Do NOT touch `[project.dependencies]` or `[project.optional-dependencies]`.
- Run `uv sync` after the edit so `.venv` resolves the annotation for basedpyright.
- Version is still `1.4.0` in this file — the phase does not bump it.

---

### `BlockingStubCursor` extension — edit (test/stub)

**Analog:** `tests/_async_harness/stubs.py` — two existing stub methods are the
templates:
- `fetch_arrow_table` (`stubs.py:304-315`): the zero-arg blocking-then-return-`None` shape.
- `adbc_ingest` (`stubs.py:317-361`): the counter + `_block()` + return-a-value shape, with the docstring that explains the deterministic in-flight window.

**Blocking stub method shape to clone** (`stubs.py:304-315`, `fetch_arrow_table`):
```python
def fetch_arrow_table(self) -> object:
    """..."""
    with self._lock:
        self.fetch_call_count += 1
    self._block()
    return None
```

**Counter pattern to extend** (`stubs.py:160-164`, in `__init__`):
```python
self.execute_call_count: int = 0
self.fetch_call_count: int = 0
self.ingest_call_count: int = 0
```
Add `self.df_call_count: int = 0` and `self.polars_call_count: int = 0`
(RESEARCH Wave 0 Gaps). Document each new counter in the class `Attributes:` block
(`stubs.py:109-118`) — the D-04 LOCKED-name contract requires public counters be
documented.

**DF-03 raising injection** (RESEARCH Open Question #1 + Assumption A3 recommendation):
add optional ctor kwargs `fetch_df_raises: BaseException | None = None` /
`fetch_polars_raises: BaseException | None = None` on `__init__` (`stubs.py:138-153`).
The stub method bumps its counter, calls `self._block()` (so the error crosses the
**real** `to_thread.run_sync` boundary after `_block` releases — proving the
`_offload.py` EDGE-17 re-raise, not a synchronous raise), then raises the injected
exception if set:
```python
def fetch_df(self) -> object:
    with self._lock:
        self.df_call_count += 1
    self._block()
    if self._fetch_df_raises is not None:
        raise self._fetch_df_raises   # e.g. ModuleNotFoundError("No module named 'pandas'")
    return None
```
Do NOT wrap the raise — the test asserts the exact native `ModuleNotFoundError`
with `.name == "pandas"` reaches the caller (DF-03). No `_SyncCursor` conflict:
the Protocol members return `object`, and returning `None` from the stub already
satisfies `fetch_arrow_table` today.

**Also extend `_SyncReader`-style docstring discipline is N/A here** — no reader
class is added this phase (whole-op offload, D-31-03).

---

### Positive round-trip / lifetime tests — new (integration, importorskip)

**Analog:** `tests/async/test_ingest_roundtrip.py` (whole file).

**Test module shape to clone** (`test_ingest_roundtrip.py:22-37`):
```python
from __future__ import annotations
from typing import TYPE_CHECKING
import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

class TestIngest01RoundTrip:
    @pytest.mark.anyio
    async def test_create_then_append_round_trip(self, duckdb_async_pool: AsyncPool) -> None:
        ...
```

**Fixtures available (no new fixture needed):**
- `duckdb_async_pool` (`tests/async/conftest.py:87-106`) — real-driver DuckDB pool.
- `anyio_backend` (`conftest.py:58-84`) — dual-backend (asyncio + trio) parametrization; every `@pytest.mark.anyio` test runs on both.

**`importorskip` guard (RESEARCH Code Examples DF-01):**
```python
pandas = pytest.importorskip("pandas")   # skip cleanly where pandas is absent
...
df = await cur.fetch_df()
assert isinstance(df, pandas.DataFrame)
assert df.to_dict("list") == {"a": [1], "b": [2]}
```
`test_df_lifetime.py` (DF-04): read the frame AFTER `async with ... as conn:`
exits (connection checked in) — assert `df["a"].tolist() == [1]`, proving the
frame is self-owning (RESEARCH Code Examples DF-04).

**Round-trip usage pattern** (`test_ingest_roundtrip.py:48-57`) — `async with await
duckdb_async_pool.connect() as conn: cursor = conn.cursor(); await cursor.execute(...)`
then the fetch.

---

### Signature + import-surface test — new (unit + PKG-02)

**Analog:** `tests/async/test_ingest_signature.py` (whole file).

**Introspection pattern to clone** (`test_ingest_signature.py:34-36`):
```python
def test_adbc_ingest_exists_on_async_cursor() -> None:
    assert hasattr(AsyncCursor, "adbc_ingest"), "AsyncCursor.adbc_ingest not defined yet"
```
For DF: assert `hasattr(AsyncCursor, "fetch_df")` / `"fetch_polars"`, and that both
take no args beyond `self` via `inspect.signature` (simpler than ingest — no
keyword-only checks needed).

**PKG-02 import-surface assertion (RESEARCH Validation table, Pitfall 2):** assert
`import adbc_poolhouse` succeeds with pandas/polars absent. This is env-free today
(the `.venv` has no pandas/polars) — a plain `importlib.import_module("adbc_poolhouse")`
in the test body proves the runtime surface is untouched.

**Header note convention:** `test_ingest_signature.py:11-14` documents that the
authoritative Protocol-coverage gate is `.venv/bin/basedpyright` over `_cursor.py`,
and this file is the runtime companion. Reuse that framing for the DF signature test.

---

### Missing-dep / busy / cancel tests — new (stub-backed, dual-backend, looped)

**Analogs:**
- `tests/async/test_ingest_cancel.py:27-58` — the concurrency preamble (imports, `pytestmark`, stub-factory type alias) to copy VERBATIM.
- `tests/async/test_reader_busy.py:24-43` — the lighter busy-guard preamble.

**Concurrency preamble to clone VERBATIM** (`test_ingest_cancel.py:44-54`):
```python
# `tests/async/` cannot be imported with a dotted path (`async` is a reserved
# keyword), so the sibling helper module is loaded via importlib.
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate.
pytestmark = _helpers.concurrency_marks
```
Helper exports confirmed in `tests/async/_edge_helpers.py`: `concurrency_marks`
(`:56`), `real_clock_watchdog` (`:63`), `await_inside` (`:105`).

**Stub factory fixture (no new fixture — reuse):** `make_stub_async_connection`
(`tests/async/conftest.py:155-194`) returns `(async_connection, stub_connection)`;
the `BlockingStubCursor` is reachable via `stub_conn.cursors[-1]`.

**Cancel-test drive pattern** (`test_ingest_cancel.py:80-90`): gate on a call-count
predicate via `await_inside`, then `tg.cancel_scope.cancel()`, under
`real_clock_watchdog` — NOT `anyio.fail_after` (autojumps under the trio MockClock,
RESEARCH Pitfall 3 / MEMORY platform-dependent lost-wakeup). For DF, gate on
`stub_conn.cursors[-1].df_call_count >= 1` (or `polars_call_count`). Assert parity:
`stub_cursor.adbc_cancel_call_count == 1`, `stub_conn.invalidate_call_count == 1`,
`pool.checkedout() == 0` (real DuckDB leg).

**Busy-test pattern** (`test_reader_busy.py:49-65`): while one op is in flight,
a foreign op raises `ConnectionBusyError` (imported from `adbc_poolhouse`,
`test_reader_busy.py:32`). For DF: gate `fetch_df`/`fetch_polars` inside the stub,
then a second offloaded op on the same connection must raise `ConnectionBusyError`.

**DF-03 missing-dep pattern** (RESEARCH Code Examples DF-03 — the recommended,
env-independent mechanism):
```python
@pytest.mark.anyio
async def test_fetch_df_missing_pandas_propagates_unchanged(make_stub_async_connection):
    conn, stub = make_stub_async_connection(fetch_df_raises=ModuleNotFoundError("No module named 'pandas'"))
    cur = conn.cursor()
    with pytest.raises(ModuleNotFoundError) as ei:
        await cur.fetch_df()
    assert ei.value.name == "pandas"                 # exact native error
    assert not isinstance(ei.value, PoolhouseError)  # no wrapping (DF-03)
```
NOTE: the current `make_stub_async_connection` factory (`conftest.py:182`) is
**zero-arg** (`_factory()`). To pass `fetch_df_raises=`, the planner must either
(a) extend the factory to forward kwargs to `BlockingStubCursor`, or (b) set the
attribute on `stub_conn.cursors[-1]` after building. RESEARCH Open Question #1
recommends the ctor-kwarg on `BlockingStubCursor` + a factory that forwards; the
planner fixes the exact wiring. This is the one place a conftest/factory signature
change may be needed.

## Shared Patterns

### The offload bracket (applies to both new methods)
**Source:** `src/adbc_poolhouse/_async/_cursor.py:363-369` (`fetch_arrow_table`)
```python
with self._owner._offloading():  # noqa: SLF001
    return await cancellable_offload(
        self._adbc_cancel,
        self._cursor.<native_method>,
        limiter=self._limiter,
        on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
    )
```
Reused verbatim: `_offloading()` sets `_in_use` → `ConnectionBusyError` on concurrent
use (busy-guard, D-31 parity); `on_abort=self._owner.invalidate` is the D-25-03/D-31-09
poison recovery. `# noqa: SLF001` is required (intentional parent-guard access, per
module docstring `_cursor.py:1-30`).

### Google-style docstrings + Markdown (applies to all new public symbols)
**Source:** CLAUDE.md docs quality gate + MEMORY docstring rules.
- Args/Returns/Raises, Google-style (mkdocstrings parser).
- Markdown syntax in docstrings, NOT RST (`` `create_pool` `` not `` :func:`create_pool` ``).
- `Example:` (singular) = admonition box with ` ```python ` fenced block (as `adbc_ingest:431-440`).
- Any consumer-facing behaviour reflected in the relevant guide; `uv run mkdocs build --strict` (or `.venv/bin/mkdocs build --strict` under sandbox) must pass; humanizer pass on new prose.

### Dual-backend + RED-first (applies to all new test files)
**Source:** `tests/async/conftest.py:58-84` (`anyio_backend`) + `test_ingest_roundtrip.py:16-19` (RED-first header).
Every `@pytest.mark.anyio` test runs on asyncio + trio automatically. Wave-0 tests
FAIL until the methods land — that RED is the acceptance signal. Concurrency-marked
tests additionally loop + timeout (MEMORY loop-flaky-concurrency lesson); verify
loops with `rc=$?` + grep, never `if ! cmd` (MEMORY zsh `!` gotcha).

### Type gate (applies to source edits)
**Source:** RESEARCH Validation table + MEMORY IDE-vs-.venv.
Authoritative gate is `.venv/bin/basedpyright` (strict, `src`+`tests`) — 0 errors.
Ignore harness Pyright "reportMissingImports: pandas/polars" false positives; they
resolve once `uv sync` has pulled the dev-group deps. Import-lint gate:
`scan_async_package` over `src/adbc_poolhouse/_async/` returns `[]` (PKG-03).

## No Analog Found

None. Every file in this phase clones or extends an existing in-repo artifact.
The planner should NOT fall back to RESEARCH.md generic patterns — the concrete
analogs above are the source of truth.

## Metadata

**Analog search scope:** `src/adbc_poolhouse/_async/`, `tests/async/`,
`tests/_async_harness/`, `pyproject.toml`.
**Files scanned (read in full or targeted):** `_cursor.py` (563 lines),
`stubs.py` (820 lines), `test_ingest_roundtrip.py`, `test_ingest_signature.py`,
`test_ingest_cancel.py` (preamble), `test_reader_busy.py` (preamble),
`tests/async/conftest.py`, `pyproject.toml:40-69`, `_edge_helpers.py` (grep).
**Pattern extraction date:** 2026-07-02
