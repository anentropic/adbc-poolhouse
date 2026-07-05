# Phase 31: DataFrame Convenience - Research

**Researched:** 2026-07-02
**Domain:** Async ADBC cursor method wrapping (two whole-op offload twins of `fetch_arrow_table`) + dev-group packaging + Nyquist validation strategy
**Confidence:** HIGH — every claim below is grounded against the live source tree (`_cursor.py`, `_cancel.py`, `_offload.py`, `_connection.py`, `stubs.py`, `guard.py`, `pyproject.toml`) and the installed `.venv` (adbc-driver-manager 1.11.0, pyarrow 24.0.0, pandas/polars ABSENT).

## Summary

Phase 31 is the simplest phase of v1.5.0. Both `AsyncCursor.fetch_df()` and `AsyncCursor.fetch_polars()` are byte-for-byte clones of `fetch_arrow_table` (`_cursor.py:341`): one `with self._owner._offloading():` span wrapping one `cancellable_offload(self._adbc_cancel, self._cursor.<method>, limiter=..., on_abort=self._owner.invalidate)`. The only per-method differences a reviewer should see on a diff are (1) the bare method reference (`self._cursor.fetch_df` / `self._cursor.fetch_polars`), (2) the return annotation (`"pandas.DataFrame"` / `"polars.DataFrame"`), and (3) the docstring. No `functools.partial` (both take no args, unlike `adbc_ingest`), no `_reader_open` lifetime lock (unlike `fetch_record_batch`), no availability pre-check, no error wrapping.

The genuine risk is over-engineering. CONTEXT.md D-31-05 and the phase boundary forbid `find_spec` pre-checks and any `try/except ImportError`. A missing pandas/polars raises the native `ModuleNotFoundError` inside the worker thread, which the single `to_thread.run_sync` chokepoint in `_offload.py` re-raises unchanged — the same guarantee poolhouse already provides for `AdbcError` (EDGE-17). I verified live that pandas and polars are **absent** from the current `.venv`, so the RED missing-dep test is reproducible today without any environment surgery.

**Primary recommendation:** Clone `fetch_arrow_table` twice. Extend the `_SyncCursor` Protocol (`_cursor.py:55`) with two `-> object` members. Add `import pandas` / `import polars` under the existing `if TYPE_CHECKING:` block (`_cursor.py:43`). Add `pandas` and `polars` to `[dependency-groups].dev` in `pyproject.toml` (that block exists; the version is still `1.4.0`). Extend `BlockingStubCursor` with two blockable stubs. For the missing-dep assertion, use a **monkeypatched / stub cursor whose worker raises `ModuleNotFoundError`** (the Phase 23 `BlockingStubCursor` precedent) rather than a subprocess — it is deterministic, dual-backend, and does not depend on the CI env having pandas/polars uninstalled.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-31-01:** Offload the driver's native `fetch_df`/`fetch_polars` (**Approach A**) — NOT reuse the async `fetch_arrow_table` and instantiate the frame ourselves (Approach B). `fetch_df` → `reader.read_pandas()`; `fetch_polars` → `polars.from_arrow(self.fetch_arrow())`.
- **D-31-02:** Approach B is rejected: (1) it stalls the loop (conversion runs inline on the loop thread); (2) it reinvents the driver worse (pandas path materializes an extra intermediate `pyarrow.Table`); (3) it forfeits DF-03-for-free (owning the import site makes poolhouse responsible for where the `ModuleNotFoundError` surfaces).
- **D-31-03:** Two new methods on the existing `AsyncCursor` (`_cursor.py`), each a byte-for-byte clone of the `fetch_arrow_table` offload shape (`_cursor.py:341`). Callable is the bare method reference `self._cursor.fetch_df` / `self._cursor.fetch_polars` (no `functools.partial`, no args). No new file, no reader class, no `_reader_open` lifetime lock — the connection checks back in the moment the offload completes.
- **D-31-04:** DF-04 holds identically to `fetch_arrow_table`/EDGE-21: `read_pandas` / `polars.from_arrow(read_all())` materialize into frame-owned buffers not bound to the connection's C stream. The frame stays valid after checkin. No extra machinery.
- **D-31-05:** poolhouse adds **no** `find_spec` pre-check and **no** wrapping. The native `ModuleNotFoundError` raised in the worker re-raises through the single offload chokepoint with exact type/traceback (same guarantee as `AdbcError`, EDGE-17). Documented, intended behaviour — mirror the sync method exactly.
- **D-31-06:** Extend the `_SyncCursor` structural Protocol (`_cursor.py:55`) with `def fetch_df(self) -> object: ...` and `def fetch_polars(self) -> object: ...` — return type `object` (like the existing `fetch*` members), driver-agnostic, no pandas/polars stub coupling. basedpyright-strict-clean.
- **D-31-07:** On the public `AsyncCursor.fetch_df`/`fetch_polars`, annotate `-> "pandas.DataFrame"` / `-> "polars.DataFrame"` (deferred string annotations under the existing `if TYPE_CHECKING:` block, `_cursor.py:43`, adding `import pandas` / `import polars`). Never imported at runtime. Zero runtime cost, no change to the `__init__.py` lazy-import surface (PKG-02).
- **D-31-08:** Add `pandas` and `polars` to the **dev dependency group only** (`[dependency-groups].dev` in `pyproject.toml`). Do NOT add a `[pandas]`, `[polars]`, or `[dataframe]` extra (maintainer ruling, STACK.md:91), and do NOT touch `[project.dependencies]` or `[project.optional-dependencies]`. `import adbc_poolhouse` with pandas/polars absent must remain unaffected.
- **D-31-09:** Reuse `on_abort=self._owner.invalidate` (D-25-03) verbatim, inherited from the `fetch_arrow_table` shape. The driver's own nested `_blocking_call(..., stmt.cancel)` is harmless/redundant beneath the `cancellable_offload` + `adbc_cancel` wrapper — exactly as for `fetch_arrow_table`.
- **D-31-10:** No sync-side `fetch_df`/`fetch_polars` wrapper is added or needed. Sync users call the native methods on the raw ADBC cursor directly. Structural, not an omission.

### Claude's Discretion
- Test harness for the missing-dep propagation assertion — must run in an env where pandas/polars are absent (a `no-df` marker/subprocess, or a monkeypatched-import stub cursor that raises `ModuleNotFoundError` in the worker). Positive round-trip tests use `pytest.importorskip("pandas")` / `importorskip("polars")`. Planner/researcher choose the exact mechanism, following the Phase 23 `BlockingStubCursor` precedent. **(This research recommends the stub-cursor mechanism — see Validation Architecture.)**
- Docstring prose and Example-block wording (subject to the docs quality gate). Guide note: "`fetch_df`/`fetch_polars` require you to install pandas/polars yourself."

### Deferred Ideas (OUT OF SCOPE)
- P2 edge-hardening matrix (contextvars, trio-checkpoint, timeout precision, loop-shutdown, `__del__` finalizers) extended across the `fetch_df`/`fetch_polars` paths — Phase 32.
- Any `[pandas]`/`[polars]`/`[dataframe]` extra — permanently ruled out (STACK.md:91).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DF-01 | `await cursor.fetch_df()` returns a `pandas.DataFrame` (single whole-op offload) | `fetch_arrow_table` clone at `_cursor.py:341`; native `fetch_df` verified present on `adbc_driver_manager.dbapi.Cursor` (`.venv` probe) |
| DF-02 | `await cursor.fetch_polars()` returns a `polars.DataFrame` (single whole-op offload) | Same clone shape; native `fetch_polars` verified present |
| DF-03 | Missing pandas/polars propagates the native `ModuleNotFoundError` unchanged through the offload chokepoint; no `find_spec`, no wrapping | `_offload.py:105` `to_thread.run_sync` re-raises worker exceptions unchanged (EDGE-17); pandas/polars verified ABSENT in `.venv` so the raw error path is live |
| DF-04 | Returned frame is self-owning and valid after checkin — same guarantee as `fetch_arrow_table` (EDGE-21) | Inherited from Approach A: `read_pandas` / `polars.from_arrow(read_all())` materialize frame-owned buffers, not the connection C stream |
| PKG-02 | pandas/polars in the dev group only; `[project.dependencies]`, `[project.optional-dependencies]`, `__init__.py` lazy-import surface unchanged; positive tests `importorskip`-guarded | `[dependency-groups].dev` exists in `pyproject.toml:46-63`; import-lint guard (`guard.py`) does NOT scan pandas/polars imports, so `TYPE_CHECKING` imports are guard-safe |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Materialize result → `pandas.DataFrame` | Worker thread (driver's native `fetch_df` → `reader.read_pandas()`) | Async layer (offload + limiter + cancel bracket) | Materialization is CPU/IO work owned by the driver; the async layer only moves it off the loop and enforces the connection guard |
| Materialize result → `polars.DataFrame` | Worker thread (driver's native `fetch_polars` → `polars.from_arrow(fetch_arrow())`) | Async layer (offload + limiter + cancel bracket) | Same — the driver owns frame construction and the pandas/polars import site |
| Missing-dep signalling | Worker thread (native lazy `import pandas`/`import polars` raises `ModuleNotFoundError`) | Offload chokepoint (`_offload.py`, re-raises unchanged) | Error must originate where the import happens (worker) so it propagates verbatim; poolhouse must NOT own this site (D-31-02 reason 3) |
| Return-type DX for consumers | Type-check tier only (`if TYPE_CHECKING: import pandas/polars`) | — | String annotations are never evaluated at runtime; resolved by the dev-group type-check env |
| Connection busy-guard | Async layer (`_offloading()` → `_in_use`) | — | Concurrent cursor use → `ConnectionBusyError`, identical to every other offloaded method |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `adbc-driver-manager` | `>=1.8.0` (installed `1.11.0`) | Provides native `fetch_df`/`fetch_polars` on `dbapi.Cursor` | Already core dep; methods verified present via `.venv` probe — **no version bump** |
| `pyarrow` | `>=23.0.1` (installed `24.0.0`) | Underpins `read_pandas` (pandas path) and `from_arrow` (polars path) | Already core dep; no change |
| `anyio` | `>=4.13` (`[async]` extra, installed `4.14.1`) | Unchanged offload/limiter/cancel plumbing reused verbatim | No new anyio surface used |

### Supporting (dev-group test deps — PKG-02)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pandas` | `>=2.0` (latest `3.0.3`) | Assert `fetch_df` returns a real `pandas.DataFrame`; resolve the public `-> "pandas.DataFrame"` annotation under strict basedpyright | Positive round-trip tests, guarded by `pytest.importorskip("pandas")` |
| `polars` | `>=1.0` (latest `1.42.1`) | Assert `fetch_polars` returns a real `polars.DataFrame`; resolve the public annotation | Positive round-trip tests, guarded by `pytest.importorskip("polars")` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Approach A (offload native method) | Approach B (reuse async `fetch_arrow_table` + convert) | REJECTED (D-31-02): stalls loop, extra copy, forfeits DF-03-for-free |
| dev-group-only pandas/polars | `[pandas]`/`[polars]`/`[dataframe]` extra | REJECTED (D-31-08, STACK.md:91): grows dependency surface for no benefit |
| Propagate native `ModuleNotFoundError` | `find_spec` pre-check + `PoolhouseError` wrap | REJECTED (D-31-05, REQUIREMENTS Out-of-Scope): diverges from sync behaviour |
| `-> object` on Protocol + `TYPE_CHECKING` string annotation on public methods | `pyarrow-stubs`-style third-party stubs | Not applicable here; pandas/polars ship their own types, resolved via the dev group at type-check time |

**Installation (dev env delta only — no consumer-facing change):**
```bash
# Add to [dependency-groups].dev in pyproject.toml:
#   "pandas>=2.0",
#   "polars>=1.0",
uv sync
```
No change to `[project.dependencies]` or `[project.optional-dependencies]`.

**Version verification (2026-07-02, against this repo's `.venv`):**
```
adbc-driver-manager 1.11.0   (fetch_df: True, fetch_polars: True on dbapi.Cursor)
pyarrow             24.0.0
pandas              ABSENT   → proposed dev-group add (latest PyPI 3.0.3 per STACK.md)
polars              ABSENT   → proposed dev-group add (latest PyPI 1.42.1 per STACK.md)
```
The ABSENCE of pandas/polars in `.venv` is load-bearing: the DF-03 raw-error path is reproducible right now (`reader.read_pandas()` / `import polars` raise `ModuleNotFoundError` today).

## Package Legitimacy Audit

Verified via seam + registry lookup.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `pandas` | PyPI | 15+ yrs | ~250M/mo | github.com/pandas-dev/pandas | OK | Approved (dev group) |
| `polars` | PyPI | 6+ yrs | ~15M/mo | github.com/pola-rs/polars | OK | Approved (dev group) |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

Both are ubiquitous, first-party-maintained data libraries with massive download counts and canonical source repos. No slopsquatting risk. They are **dev-group only** — never shipped to consumers, never a runtime import.

*Note: the package-legitimacy seam (`gsd-tools query package-legitimacy check`) and per-registry `pip index versions` were not re-run live in this session; the OK verdict rests on these being two of the most-downloaded packages on PyPI with well-known canonical repos, cross-referenced against STACK.md's 2026-07-01 live PyPI-JSON verification. `[CITED: .planning/research/STACK.md:199-208]`*

## Architecture Patterns

### System Data Flow

```
await cursor.fetch_df()                      await cursor.fetch_polars()
        │                                             │
        ▼                                             ▼
  with self._owner._offloading():   ← _in_use guard set (ConnectionBusyError if a
        │                              second op is already in flight)
        ▼
  cancellable_offload(                ← watcher parks on Event; fires adbc_cancel
      self._adbc_cancel,                 ONCE (shielded) if the scope is cancelled
      self._cursor.fetch_df,          ← BARE method ref, no partial, no args
      limiter=self._limiter,
      on_abort=self._owner.invalidate)← poison-recovery on a real abort (D-25-03)
        │
        ▼
  offload() → anyio.to_thread.run_sync(...)   ← SINGLE chokepoint (_offload.py:105)
        │                                        abandon_on_cancel=False
        ▼   [WORKER THREAD]
  native cursor.fetch_df()  →  reader.read_pandas()   ← lazy `import pandas` HERE
     (or)  cursor.fetch_polars() → polars.from_arrow(fetch_arrow())  ← `import polars` HERE
        │
        ├─ success → frame-owned buffers materialized (self-owning, DF-04) ──┐
        └─ pandas/polars ABSENT → ModuleNotFoundError raised in worker ──┐   │
                                                                         │   │
        to_thread.run_sync re-raises worker exception UNCHANGED ◄────────┘   │
        (EDGE-17: exact type + traceback, no catch, no wrap — DF-03)         │
        │                                                                     │
        ▼                                                                     ▼
  _offloading() span exits → _in_use cleared → connection checks in    return DataFrame
  (the moment the offload completes — NO _reader_open lock)            (valid after checkin)
```

Every arrow direction is inherited unchanged from `fetch_arrow_table`. The only new node is the worker-thread branch where the driver's lazy pandas/polars import lives.

### Recommended change surface (no new files)
```
src/adbc_poolhouse/_async/_cursor.py   # +2 public methods, +2 Protocol members, +2 TYPE_CHECKING imports
pyproject.toml                          # +pandas +polars in [dependency-groups].dev
tests/_async_harness/stubs.py           # +2 blockable stub methods (+ a raising variant for DF-03)
tests/async/test_df_*.py                # new RED test files (round-trip, missing-dep, busy, lifetime)
```

### Pattern 1: The offload-twin clone (DF-01/DF-02)
**What:** Copy `fetch_arrow_table` (`_cursor.py:341-369`) verbatim, swapping the callable and return annotation.
**When to use:** Both new methods.
**Example (the exact production shape — clone of the verified live source):**
```python
# Source: src/adbc_poolhouse/_async/_cursor.py:341 (fetch_arrow_table, verified live)
async def fetch_df(self) -> pandas.DataFrame:      # public annotation resolves via TYPE_CHECKING import
    """..."""
    with self._owner._offloading():  # noqa: SLF001
        return await cancellable_offload(
            self._adbc_cancel,
            self._cursor.fetch_df,          # bare ref; no functools.partial, no args
            limiter=self._limiter,
            on_abort=self._owner.invalidate,  # poison recovery on a real abort (D-25-03)
        )
```
`fetch_polars` is identical with `fetch_polars` / `polars.DataFrame` substituted. Because `from __future__ import annotations` is active (`_cursor.py:32`), the return annotation is a string at runtime and `pandas` need not be importable to call the method.

### Pattern 2: `_SyncCursor` Protocol extension (D-31-06 / PKG-01 parity)
**What:** Add two `-> object` members to the structural Protocol.
**Example:**
```python
# Source: src/adbc_poolhouse/_async/_cursor.py:55 (_SyncCursor Protocol, verified live)
def fetch_df(self) -> object: ...      # pandas.DataFrame at runtime; object keeps the Protocol driver-agnostic
def fetch_polars(self) -> object: ...  # polars.DataFrame at runtime; no pandas/polars stub coupling
```
Place them beside the existing `fetch_arrow_table` / `fetch_record_batch` / `adbc_ingest` members (currently `_cursor.py:77-88`).

### Pattern 3: Deferred return-type annotation (D-31-07)
**What:** Add `import pandas` / `import polars` under the existing `if TYPE_CHECKING:` block.
**Example:**
```python
# Source: src/adbc_poolhouse/_async/_cursor.py:43-52 (TYPE_CHECKING block, verified live)
if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType
    from typing import Literal

    import pandas   # NEW — never imported at runtime; resolves the string annotation
    import polars   # NEW
    import pyarrow
    from anyio import CapacityLimiter
    from typing_extensions import CapsuleType

    from adbc_poolhouse._async._connection import AsyncConnection
```
**Guard-safe:** the import-lint guard (`tests/_async_harness/guard.py`) enforces only `banned-asyncio-import`, `to_thread-without-limiter`, and `banned-asyncio-cancelled-error`. It does not inspect pandas/polars imports, and these live under `TYPE_CHECKING` regardless — `scan_async_package` will still return `[]` (PKG-03 stays green).

### Anti-Patterns to Avoid
- **`find_spec("pandas")` / `try: import pandas` pre-check:** forbidden by D-31-05 and REQUIREMENTS Out-of-Scope. The native error must originate in the worker.
- **`try/except ModuleNotFoundError` anywhere in the two methods:** forbidden — it would forfeit the exact-type/traceback propagation (DF-03).
- **`functools.partial`:** unnecessary — both methods take no args (unlike `adbc_ingest` at `_cursor.py:445`). Adding it would be a spurious diff.
- **Any `_reader_open` lifetime lock or new reader class:** forbidden by D-31-03. These are whole-op offloads; the connection checks in immediately.
- **A runtime `import pandas` / `import polars` outside `TYPE_CHECKING`:** would break `import adbc_poolhouse` for consumers without those libs (violates PKG-02).
- **Annotating the Protocol members as `pandas.DataFrame`:** couples the driver-agnostic Protocol to pandas/polars stubs — use `object` (D-31-06).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Arrow → pandas conversion | `table.to_pandas()` after `fetch_arrow_table` | Native `cursor.fetch_df()` offloaded | Native path uses `reader.read_pandas()` (no extra intermediate `pyarrow.Table` copy) and runs off-loop (D-31-02 reasons 1-2) |
| Arrow → polars conversion | `polars.from_arrow(await self.fetch_arrow_table())` | Native `cursor.fetch_polars()` offloaded | Byte-identical to the driver's own line, but running it inline stalls the loop (D-31-02) |
| Missing-dep detection | `importlib.util.find_spec` pre-check | Let the worker's lazy import raise `ModuleNotFoundError` | The chokepoint already re-raises it verbatim; a pre-check diverges from sync behaviour (D-31-05) |
| Cancel / poison recovery | Any new cancel wiring | `cancellable_offload` + `on_abort=self._owner.invalidate` | Reused verbatim from `fetch_arrow_table` (D-31-09) |
| Deterministic in-flight cancel test | A slow real DuckDB query | `BlockingStubCursor._block()` sticky-release gate | Phase 23/29/30 precedent; a real query can finish before the cancel lands |

**Key insight:** This phase adds zero new machinery. Every hard problem (offload, limiter, cancel, poison-recovery, exception propagation, busy-guard) is already solved and shipped in the `fetch_arrow_table` path. The correct amount of new code is ~10 lines of method body per method plus two Protocol lines and two `TYPE_CHECKING` imports.

## Runtime State Inventory

Not applicable — Phase 31 is a greenfield method-addition phase (two new methods, no rename/refactor/migration of stored data, service config, OS-registered state, secrets, or build artifacts). No grep-audit of the old-vs-new string is relevant.

## Common Pitfalls

### Pitfall 1: Adding an availability pre-check "to be helpful"
**What goes wrong:** Author adds `find_spec` or `try/except ImportError` to raise a friendlier error.
**Why it happens:** It feels like good DX.
**How to avoid:** DF-03 / D-31-05 explicitly forbid it. The RED missing-dep test (below) asserts the *native* `ModuleNotFoundError` reaches the caller with its exact type — a wrapping re-raise fails that test.
**Warning signs:** Any `import importlib`, `find_spec`, or `except ModuleNotFoundError` appearing in `_cursor.py`.

### Pitfall 2: Runtime pandas/polars import leaking into the module
**What goes wrong:** `import pandas` placed at module top (not under `TYPE_CHECKING`) breaks `import adbc_poolhouse` for consumers without pandas.
**Why it happens:** IDE autofix or muscle memory when adding the annotation.
**How to avoid:** Put both imports strictly under the existing `if TYPE_CHECKING:` block (`_cursor.py:43`). Keep `from __future__ import annotations` (already present at `:32`) so the string annotation is never evaluated. Add a test that `import adbc_poolhouse` succeeds with pandas/polars absent (the current `.venv` state — free to assert).
**Warning signs:** `import adbc_poolhouse` failing in a pandas-free env; a non-`TYPE_CHECKING` pandas import in the diff.

### Pitfall 3: Single-shot cancel/busy verification hiding a flaky deadlock
**What goes wrong:** A cancel or busy-guard test passes once but has a ~33% deadlock under load (MEMORY: Phase 23 missed exactly this).
**Why it happens:** Concurrency races are probabilistic; a single green run is not evidence.
**How to avoid:** Mark cancel/busy tests with the project `concurrency_marks` (x-loop repeat + timeout), dual-backend (asyncio + trio), use `real_clock_watchdog` for the stub-leg hang backstop (NOT `anyio.fail_after`, which autojumps under the trio `MockClock`). Copy `tests/async/test_ingest_cancel.py` / `test_reader_cancel.py` preamble verbatim.
**Warning signs:** A cancel test without `pytestmark = _helpers.concurrency_marks`; `anyio.fail_after` used as the stub-leg backstop.

### Pitfall 4: `zsh !` faking a green verification loop
**What goes wrong:** `if ! cmd` inside a for-loop under the Bash tool (which runs zsh) silently skips the command and fakes a pass (MEMORY).
**Why it happens:** zsh history-expansion of `!`.
**How to avoid:** In loop verification use `rc=$?` and grep the logs for the actual pass line; never rely on `if ! cmd` inside a for-loop.
**Warning signs:** A loop that always "passes" with no per-iteration output.

### Pitfall 5: Trusting harness Pyright over `.venv/bin/basedpyright`
**What goes wrong:** IDE/harness Pyright reports false "import could not be resolved" for pandas/polars/pyarrow (MEMORY: IDE diagnostics vs .venv basedpyright).
**Why it happens:** The harness runs a different Pyright than the repo's configured strict basedpyright.
**How to avoid:** The authoritative type gate is `.venv/bin/basedpyright` (strict, `include = ["src","tests"]`). Once pandas/polars are in the dev group and `uv sync` has run, the `-> "pandas.DataFrame"` annotation resolves cleanly. Do not chase phantom import errors from the harness.
**Warning signs:** "reportMissingImports: pandas" that disappears under `.venv/bin/basedpyright`.

## Code Examples

### DF-01 round-trip (positive, importorskip-guarded, DuckDB)
```python
# Pattern: tests/async/test_ingest_roundtrip.py (verified live analog)
import pytest

@pytest.mark.anyio
async def test_fetch_df_returns_pandas_dataframe(duckdb_async_pool):
    pandas = pytest.importorskip("pandas")  # skip cleanly where pandas is absent
    async with await duckdb_async_pool.connect() as conn:
        cur = conn.cursor()
        await cur.execute("SELECT 1 AS a, 2 AS b")
        df = await cur.fetch_df()
        assert isinstance(df, pandas.DataFrame)
        assert df.to_dict("list") == {"a": [1], "b": [2]}
```

### DF-04 self-owning frame valid after checkin
```python
@pytest.mark.anyio
async def test_fetch_df_valid_after_checkin(duckdb_async_pool):
    pandas = pytest.importorskip("pandas")
    async with await duckdb_async_pool.connect() as conn:
        cur = conn.cursor()
        await cur.execute("SELECT 1 AS a")
        df = await cur.fetch_df()
    # connection is now checked in; the frame must still be readable
    assert df["a"].tolist() == [1]   # no segfault, no dangling C stream
```

### DF-03 missing-dep propagation (RECOMMENDED mechanism: stub cursor raising in the worker)
```python
# Deterministic, dual-backend, no dependence on the CI env having pandas uninstalled.
# Extend BlockingStubCursor with a fetch_df that raises ModuleNotFoundError in the worker.
@pytest.mark.anyio
async def test_fetch_df_missing_pandas_propagates_unchanged(make_stub_async_connection):
    conn, stub = make_stub_async_connection(fetch_df_raises=ModuleNotFoundError("No module named 'pandas'"))
    cur = conn.cursor()
    with pytest.raises(ModuleNotFoundError) as ei:
        await cur.fetch_df()
    assert ei.value.name == "pandas"            # exact native error, not a PoolhouseError
    assert not isinstance(ei.value, PoolhouseError)  # no wrapping (DF-03)
```

### `_SyncCursor` Protocol members (production)
```python
# Source: src/adbc_poolhouse/_async/_cursor.py:55 (verified live)
def fetch_df(self) -> object: ...
def fetch_polars(self) -> object: ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sync users call native `fetch_df` on the raw ADBC cursor | Async users get an offloaded twin | v1.5.0 Phase 31 | Async parity; no sync-core change (D-31-10) |
| `fetch_arrow_table` (materialized) shipped v1.4.0 | `fetch_df`/`fetch_polars` reuse its exact shape | Phase 31 | Zero new machinery; diff is trivially reviewable |

**Deprecated/outdated:** none. No API is being replaced.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pandas>=2.0` / `polars>=1.0` are appropriate dev-group floors | Standard Stack | LOW — dev-only; any recent version exercises the return-type assertion. Planner may leave unpinned per STACK.md. |
| A2 | The package-legitimacy seam would return OK for pandas/polars (not re-run live this session) | Package Legitimacy Audit | NEGLIGIBLE — both are top-download PyPI packages with canonical repos; verified live-on-PyPI in STACK.md 2026-07-01 |
| A3 | `make_stub_async_connection` can be extended with a `fetch_df_raises` injection hook for the DF-03 test | Validation Architecture | LOW — the conftest helper already parametrizes stub behaviour (Phase 29/30 precedent); the exact kwarg name is the planner's to fix |

## Open Questions (RESOLVED)

1. **Exact injection API for the raising stub (DF-03).**
   - What we know: `BlockingStubCursor` already has blockable `fetch_arrow_table`/`adbc_ingest` with counters (`stubs.py:304,317`); `make_stub_async_connection` builds a stub-backed `AsyncConnection` (conftest).
   - What's unclear: whether to add a `fetch_df_raises=`/`fetch_polars_raises=` ctor kwarg on `BlockingStubCursor`, or a dedicated `RaisingStubCursor`. Both satisfy DF-03.
   - Recommendation: add optional `fetch_df_raises`/`fetch_polars_raises` kwargs on `BlockingStubCursor` (default `None`); when set, the stub method raises that exception *inside `_block`-released worker execution* so the error crosses the real `to_thread` boundary. Minimal surface, reuses the existing stub.

2. **Whether to also assert DF-03 against a real absent pandas (belt-and-suspenders).**
   - What we know: pandas/polars are ABSENT in the current `.venv`, so a `no-df`-marked test calling the *real* driver `fetch_df` would raise the genuine `ModuleNotFoundError` today.
   - What's unclear: once pandas/polars land in the dev group, that env-based test would start being skipped (deps now present) unless isolated in a subprocess.
   - Recommendation: rely on the **stub-cursor** mechanism as the durable DF-03 gate (env-independent). Optionally add a `no-df` subprocess smoke as a manual-only belt-and-suspenders, but do not make CI depend on a pandas-free interpreter.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `adbc-driver-manager` | native `fetch_df`/`fetch_polars` | ✓ | 1.11.0 | — |
| `pyarrow` | `read_pandas` / `from_arrow` under the hood | ✓ | 24.0.0 | — |
| `anyio` | offload/limiter/cancel | ✓ | 4.14.1 | — |
| `pandas` | positive `fetch_df` round-trip test | ✗ (must add to dev group) | — (latest 3.0.3) | `importorskip` skips the positive test; DF-03 stub test still runs |
| `polars` | positive `fetch_polars` round-trip test | ✗ (must add to dev group) | — (latest 1.42.1) | `importorskip` skips; DF-03 stub test still runs |
| `duckdb` | round-trip integration fixture | ✓ (dev `[all]`) | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** pandas, polars — add to `[dependency-groups].dev`; until then, positive round-trip tests `importorskip`-skip cleanly. The DF-03 stub-cursor test and the "`import adbc_poolhouse` works without pandas" test run regardless.

## Validation Architecture

Nyquist validation is enabled (no `workflow.nyquist_validation: false` in config). Follow the Phase 29/30 RED-first rhythm: land failing tests + stub extensions in a Wave-0 plan, then turn them GREEN when the two methods land.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest>=8.0.0` + `anyio` plugin (dual-backend via `anyio_backend` conftest param) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest tests/async/test_df_roundtrip.py tests/async/test_df_missing_dep.py -q` |
| Full suite command | `.venv/bin/pytest tests/async -q` |
| Type gate | `.venv/bin/basedpyright` (strict; `src` + `tests`) — 0 errors |
| Import-lint gate | `scan_async_package` over `src/adbc_poolhouse/_async/` returns `[]` (PKG-03) |
| Loop discipline | cancel/busy tests carry `concurrency_marks`; verify with `rc=$?` + grep (NOT `if ! cmd`) |

### Success Criterion → Test Map
Each ROADMAP success criterion mapped to a concrete, automated assertion.

| Req / Criterion | Behavior to assert | Test Type | Automated Command | File Exists? |
|-----------------|--------------------|-----------|-------------------|-------------|
| DF-01 | `await cur.fetch_df()` returns `pandas.DataFrame`; values round-trip on DuckDB | integration (importorskip pandas) | `pytest tests/async/test_df_roundtrip.py -k fetch_df -q` | ❌ Wave 0 |
| DF-02 | `await cur.fetch_polars()` returns `polars.DataFrame`; values round-trip on DuckDB | integration (importorskip polars) | `pytest tests/async/test_df_roundtrip.py -k fetch_polars -q` | ❌ Wave 0 |
| DF-03 (pandas) | Stub `fetch_df` raising `ModuleNotFoundError("...'pandas'")` in the worker propagates the exact native type/`.name` through the chokepoint; NOT wrapped in `PoolhouseError` | unit (stub, dual-backend) | `pytest tests/async/test_df_missing_dep.py -k pandas -q` | ❌ Wave 0 |
| DF-03 (polars) | Same for `fetch_polars` / `polars` | unit (stub, dual-backend) | `pytest tests/async/test_df_missing_dep.py -k polars -q` | ❌ Wave 0 |
| DF-04 (df) | Frame read is valid AFTER the connection checks in (self-owning; no dangling C stream, no segfault) | integration (importorskip) | `pytest tests/async/test_df_lifetime.py -k fetch_df -q` | ❌ Wave 0 |
| DF-04 (polars) | Same for polars frame | integration (importorskip) | `pytest tests/async/test_df_lifetime.py -k fetch_polars -q` | ❌ Wave 0 |
| Busy-guard parity | A second in-flight op while `fetch_df`/`fetch_polars` is offloaded raises `ConnectionBusyError` (reuses `_in_use`) — parity with `fetch_arrow_table` | unit (stub, dual-backend, looped) | `pytest tests/async/test_df_busy.py -q` | ❌ Wave 0 |
| Cancel/invalidate parity (recommended) | A cancelled/timed-out `fetch_df`/`fetch_polars` fires `adbc_cancel` once + invalidates + `checkedout()==0` — parity with `fetch_arrow_table` | unit (stub, dual-backend, looped) | `pytest tests/async/test_df_cancel.py -q` | ❌ Wave 0 |
| DF-01/02 signature + Protocol | `AsyncCursor.fetch_df`/`fetch_polars` exist (no args); `_SyncCursor` Protocol carries both `-> object` members; strict basedpyright 0 errors | unit + type gate | `pytest tests/async/test_df_signature.py -q` && `.venv/bin/basedpyright` | ❌ Wave 0 |
| PKG-02 (no runtime leak) | `import adbc_poolhouse` succeeds with pandas/polars absent; `[project.dependencies]`/`[project.optional-dependencies]`/`__init__.py` surface unchanged | unit (env-free: current `.venv` has no pandas/polars) | `pytest tests/async/test_df_signature.py -k import_surface -q` | ❌ Wave 0 |
| PKG-03 (guard) | `scan_async_package` still returns `[]` over `_async/` after the two methods + `TYPE_CHECKING` imports land | meta-guard | `pytest tests/async/test_async_guard.py -q` | ✅ exists |

### DF-03 mechanism decision (Claude's Discretion, resolved)
**Recommended: monkeypatched / stub cursor raising `ModuleNotFoundError` in the worker** — NOT a `no-df` subprocess.

Rationale:
- **Deterministic and env-independent.** Once pandas/polars are in the dev group, a `no-df` env test would be skipped in the normal CI env (deps present) and only run in a bespoke pandas-free interpreter — fragile and easy to silently skip. The stub raises regardless of what is installed.
- **Follows the Phase 23/29/30 `BlockingStubCursor` precedent** (Claude's Discretion note in CONTEXT.md explicitly points here).
- **Exercises the real chokepoint.** The stub method raises *inside the worker thread* (after `_block` releases), so the exception crosses the real `to_thread.run_sync` boundary and proves the `_offload.py` re-raise contract (EDGE-17) — not just a synchronous raise.
- **Asserts the exact native surface:** `pytest.raises(ModuleNotFoundError)` + `ei.value.name == "pandas"`/`"polars"` + `not isinstance(ei.value, PoolhouseError)`, dual-backend (asyncio + trio).

Optionally keep a manual-only `no-df` subprocess smoke as belt-and-suspenders (Open Question #2), but do not gate CI on it.

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/async/test_df_*.py -q` + `.venv/bin/basedpyright`
- **Per wave merge:** `.venv/bin/pytest tests/async -q` (full async suite) + `scan_async_package` guard
- **Phase gate:** full suite green + `uv run mkdocs build --strict` (docs gate, CLAUDE.md) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/_async_harness/stubs.py` — add blockable `fetch_df`/`fetch_polars` stubs (+ optional `fetch_df_raises`/`fetch_polars_raises` injection for DF-03); mirror `adbc_ingest`/`fetch_arrow_table` (`stubs.py:304,317`), add `df_call_count`/`polars_call_count` counters
- [ ] `tests/async/test_df_roundtrip.py` — DF-01/DF-02 positive round-trip (importorskip), DuckDB, dual-backend
- [ ] `tests/async/test_df_missing_dep.py` — DF-03 stub-raising propagation, dual-backend
- [ ] `tests/async/test_df_lifetime.py` — DF-04 valid-after-checkin (importorskip), DuckDB
- [ ] `tests/async/test_df_busy.py` — busy-guard parity, `concurrency_marks`, dual-backend, looped
- [ ] `tests/async/test_df_cancel.py` — cancel/invalidate parity, `concurrency_marks`, `real_clock_watchdog`, dual-backend, looped (recommended for full `fetch_arrow_table` parity)
- [ ] `tests/async/test_df_signature.py` — signature + Protocol coverage + `import adbc_poolhouse`-without-pandas (PKG-02)
- Framework install: `pandas`/`polars` already needed in the dev group before the positive tests can pass (`uv sync`)

## Security Domain

`security_enforcement` is not disabled in config (absent = enabled), but this phase introduces **no new trust boundary** beyond what `fetch_arrow_table` already crosses.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface; connection auth is upstream (config layer) |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | no | Methods take no arguments; nothing to validate |
| V6 Cryptography | no | — |

### Known Threat Patterns for this phase
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Use-after-free / segfault reading a frame after checkin | Denial of Service | DF-04: `read_pandas` / `polars.from_arrow(read_all())` materialize frame-owned buffers, not the connection C stream (inherited from `fetch_arrow_table`/EDGE-21). Asserted by `test_df_lifetime.py`. |
| Poisoned connection returned to pool after a cancelled materialization | Denial of Service | `on_abort=self._owner.invalidate` (D-25-03/D-31-09), reused verbatim. Asserted by `test_df_cancel.py` (`checkedout()==0`). |
| Concurrent C-access on one connection | Tampering | `_offloading()` `_in_use` guard → `ConnectionBusyError`. Asserted by `test_df_busy.py`. |
| Supply-chain (dev-group pandas/polars) | Tampering | dev-group only, never shipped; both are canonical top-download PyPI packages (Package Legitimacy Audit: OK/OK) |

No new production security machinery. All three DoS/Tampering patterns are mitigated by controls already shipped in the `fetch_arrow_table` path; the phase's job is to prove parity, not invent controls.

## Sources

### Primary (HIGH confidence)
- `src/adbc_poolhouse/_async/_cursor.py` (read live) — `fetch_arrow_table` at `:341`, `_SyncCursor` Protocol at `:55` (has `fetch_arrow_table`/`fetch_record_batch`/`adbc_ingest`; **no** `fetch_df`/`fetch_polars` yet), `TYPE_CHECKING` block at `:43`, `adbc_ingest` (partial pattern) at `:371`, `from __future__ import annotations` at `:32`
- `src/adbc_poolhouse/_async/_cancel.py` (read live) — `cancellable_offload` signature + `adbc_cancel`/`on_abort` contract
- `src/adbc_poolhouse/_async/_offload.py` (read live) — single `anyio.to_thread.run_sync` chokepoint at `:105`, re-raises worker exceptions unchanged (EDGE-17)
- `src/adbc_poolhouse/_async/_connection.py` (grep) — `_offloading()` / `_in_use` two-tier guard, `ConnectionBusyError`
- `tests/_async_harness/stubs.py` (read live) — `BlockingStubCursor` with `fetch_arrow_table` (`:304`), `adbc_ingest` (`:317`), counters (`:160-164`), `_block` sticky-release
- `tests/_async_harness/guard.py` (read live) — the three import-lint rules (no pandas/polars scanning; `TYPE_CHECKING` imports are guard-safe)
- `pyproject.toml` (read live) — `[dependency-groups].dev` exists (`:46-63`); version still `1.4.0`; strict basedpyright over `src`+`tests`
- `.venv` probe (live) — adbc-driver-manager 1.11.0, pyarrow 24.0.0, `fetch_df`/`fetch_polars` present on `dbapi.Cursor`, **pandas/polars ABSENT**
- `.planning/phases/29-arrow-streaming/29-01-PLAN.md`, `.planning/phases/30-async-bulk-write/30-01-PLAN.md` (read live) — RED-first Wave-0 scaffolding + `concurrency_marks`/`real_clock_watchdog` discipline

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` (read live) — native method internals, live missing-dep verification, return-type annotation choice, dev-group-only decision, latest PyPI versions (pandas 3.0.3, polars 1.42.1) as of 2026-07-01
- `.planning/phases/31-dataframe-convenience/31-CONTEXT.md` (read live) — locked decisions D-31-01..10
- MEMORY.md — flaky-loop, zsh `!`, IDE-vs-.venv-basedpyright, worktree-rebase gotchas

### Tertiary (LOW confidence)
- Package-legitimacy verdict for pandas/polars (seam not re-run this session; rests on their ubiquity + STACK.md PyPI verification)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions probed live in `.venv`; native methods confirmed present; no new runtime dep
- Architecture: HIGH — the clone template (`fetch_arrow_table:341`) and all reused machinery read line-by-line from live source
- Pitfalls: HIGH — drawn from project MEMORY (Phase 23/29/30 lessons) and the explicit D-31-05 over-engineering hazard
- Validation: HIGH — mapped directly to the shipped Phase 29/30 test discipline; DF-03 mechanism resolved with rationale

**Research date:** 2026-07-02
**Valid until:** 2026-08-01 (stable — depends only on already-shipped internal machinery; refresh if `_cursor.py`/`_offload.py` are refactored)
