# Phase 24: Core Async Wrapper - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 14 (6 new `_async/` modules + 2 modified shared + 6 new test files; plus the in-place harness change)
**Analogs found:** 14 / 14 (every new file has a concrete in-repo analog)

This is almost entirely a **wrap-and-offload** phase: the async surface mirrors the existing sync
`_pool_factory.py` and offloads onto the **unchanged** sync `QueuePool` + ADBC dbapi cursor. The offload
shape is already prototyped in the Phase 23 harness (`tests/_async_harness/gating.py`). Prefer the real
in-repo analogs below over RESEARCH.md's illustrative snippets — they are the verified-green source of truth.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/adbc_poolhouse/_async/_offload.py` | utility | transform (off-loop dispatch) | `tests/_async_harness/gating.py` (`run_blocking`) | exact (mechanism identical) |
| `src/adbc_poolhouse/_async/_factory.py` | factory | request-response | `src/adbc_poolhouse/_pool_factory.py` (`create_pool`/`managed_pool` overloads) | exact |
| `src/adbc_poolhouse/_async/_pool.py` | provider/store | request-response | `src/adbc_poolhouse/_pool_factory.py` (`_create_pool_impl` body, `close_pool`) | role-match |
| `src/adbc_poolhouse/_async/_connection.py` | connection wrapper | request-response | sync checkout/checkin path in `tests/test_pool_factory.py:59-65` + `_release_arrow_allocators` reset event | role-match |
| `src/adbc_poolhouse/_async/_cursor.py` | cursor wrapper | CRUD + transform (Arrow) | dbapi `Cursor` surface (`.venv/.../adbc_driver_manager/dbapi.py`) wrapped via `gating.py` offload | role-match |
| `src/adbc_poolhouse/_async/__init__.py` | config/exports | n/a | `src/adbc_poolhouse/__init__.py` (`__all__` block) | exact |
| `src/adbc_poolhouse/_exceptions.py` (MOD) | model (exception) | n/a | `src/adbc_poolhouse/_exceptions.py` (`ConfigurationError(PoolhouseError, ...)`) | exact |
| `src/adbc_poolhouse/__init__.py` (MOD) | config/exports | n/a | itself (existing `__all__` + import block) | exact |
| `tests/_async_harness/stubs.py` (MOD, Wave 0) | test fixture | event-driven | itself (`BlockingStubCursor._block`/`entered`) | exact (in-place redesign) |
| `tests/async/conftest.py` | test config | n/a | `tests/_async_harness/conftest.py` (`anyio_backend` fixture) | exact |
| `tests/async/test_async_lifecycle.py` | test | request-response | `tests/test_pool_factory.py` (connect→cursor→execute→close) | role-match |
| `tests/async/test_edge_limiter.py` | test | event-driven | `tests/_async_harness/test_harness.py` (`_await_inside` + task-group gating) | exact |
| `tests/async/test_edge_aliasing.py` | test | event-driven | `tests/_async_harness/test_harness.py` (`test_max_concurrent`) | exact |
| `tests/async/test_edge_*.py` (exceptions/resource/loophygiene) | test | mixed | `test_harness.py` gating + `test_pool_factory.py` real-driver | role-match |
| `tests/test_async_guard.py` (MOD, EDGE-25) | test | static | itself (`scan_async_package` self-tests) | exact |

---

## Pattern Assignments

### `src/adbc_poolhouse/_async/_offload.py` (utility, off-loop dispatch)

**Analog:** `tests/_async_harness/gating.py` lines 31-100 (`run_blocking`). This is the *exact* offload
mechanism the wrappers must reuse — the harness was built to prototype it. The new `offload()` is `run_blocking`
minus the `entered` bridge.

**Imports + lazy anyio pattern** (gating.py lines 19-28):
```python
from __future__ import annotations
from typing import TYPE_CHECKING
import anyio.to_thread
if TYPE_CHECKING:
    from collections.abc import Callable
    from anyio import CapacityLimiter
```

**Core offload pattern** (gating.py lines 93-100 — copy this call shape verbatim):
```python
return await anyio.to_thread.run_sync(
    _worker, limiter=limiter, abandon_on_cancel=abandon_on_cancel
)
```
For `_offload.py`, drop the `_worker` `entered` bridge and forward args via a closure:
```python
async def offload[T](fn: Callable[..., T], *args: object, limiter: CapacityLimiter) -> T:
    return await anyio.to_thread.run_sync(
        lambda: fn(*args), limiter=limiter, abandon_on_cancel=False
    )
```

**Critical constraints (from guard.py `_is_to_thread_run_sync`, lines 96-112):**
- Keep the literal `anyio.to_thread.run_sync(...)` attribute chain — the AST guard matches that exact chain.
  Do NOT alias the import (`from anyio.to_thread import run_sync as rs` slips the guard AND ships a bare offload).
- `limiter=` MUST be a keyword arg — guard `visit_Call` (lines 81-94) flags any `to_thread.run_sync` without it.
- `abandon_on_cancel=False` is the production default (D-24-02); never `True` (leaks the busy worker, EDGE anti-pattern).
- Do NOT wrap/re-raise the worker's exception — `to_thread.run_sync` re-raises with type + traceback intact (EDGE-17/ACUR-06).

---

### `src/adbc_poolhouse/_async/_factory.py` (factory, request-response)

**Analog:** `src/adbc_poolhouse/_pool_factory.py` — `create_pool` overloads (lines 111-241) and
`managed_pool` (lines 267-404). Mirror the 3-overload shape exactly; the async factory is sync-bodied
(pool construction does no per-call I/O — RESEARCH A2) and just hands `_create_pool_impl`'s result to `AsyncPool`.

**3-overload signature shape** (pool_factory.py lines 111-147 — replicate for `create_async_pool`):
```python
@overload
def create_pool(config: WarehouseConfig, *, pool_size: int = 5, max_overflow: int = 3,
                timeout: int = 30, recycle: int = 3600, pre_ping: bool = False) -> sqlalchemy.pool.QueuePool: ...
@overload
def create_pool(*, driver_path: str, db_kwargs: dict[str, str], entrypoint: str | None = None,
                pool_size: int = 5, ...) -> sqlalchemy.pool.QueuePool: ...
@overload
def create_pool(*, dbapi_module: str, db_kwargs: dict[str, str], pool_size: int = 5, ...) -> ...: ...
```

**Reuse-not-fork (CORE-04 / D-24-04):** import and call `_create_pool_impl` verbatim — do NOT re-derive
driver paths. (pool_factory.py lines 230-241 show the impl-delegation pattern.)
```python
from adbc_poolhouse._pool_factory import _create_pool_impl  # REUSE — no per-backend branch
sync_pool = _create_pool_impl(config, driver_path, db_kwargs, entrypoint, dbapi_module,
                              pool_size, max_overflow, timeout, recycle, pre_ping)
return AsyncPool(sync_pool, pool_size=pool_size, max_overflow=max_overflow)
```

**`managed_async_pool` pattern:** mirror `managed_pool` (lines 306-404) — same 3 overloads, but use
`@contextlib.asynccontextmanager`, `async with`, and a **shielded** close in the `finally` (APOOL-03,
Pattern 4 below). The try/yield/finally-close skeleton (lines 401-404) carries over directly.

---

### `src/adbc_poolhouse/_async/_pool.py` (provider/store, request-response)

**Analog:** `_pool_factory.py` `_create_pool_impl` (lines 95-108: builds the `QueuePool`, wires the reset
event) + `close_pool` (lines 244-264). `AsyncPool` *owns* the sync `QueuePool` (built by the factory) plus
the per-pool limiter, and offloads `connect`/`close`.

**Limiter construction (CORE-02)** — one dedicated limiter per pool, sized to `pool_size + max_overflow`,
never the shared 40-token default. Build it in `AsyncPool.__init__` (verified live API):
```python
self._limiter = anyio.CapacityLimiter(pool_size + max_overflow)
```

**`connect()` offload (ACONN-01)** — offload `sync_pool.connect()` through the limiter, wrap the returned
fairy in `AsyncConnection`. The sync call being offloaded is `pool.connect()` (see `test_pool_factory.py:59`).

**`close()` offload (APOOL-02)** — offload the existing `close_pool(sync_pool)` helper (pool_factory.py
lines 244-264: `pool.dispose()` + `pool._adbc_source.close()`). Do NOT reimplement dispose; reuse `close_pool`.

**`borrowed_tokens` / `available_tokens` / `total_tokens`** are read directly off `self._limiter` by the
EDGE-09/12 tests (`reportPrivateUsage = false` lets tests read `pool._limiter`).

---

### `src/adbc_poolhouse/_async/_connection.py` (connection wrapper, request-response)

**Analog (checkout/checkin path):** `tests/test_pool_factory.py` lines 59-65 — the exact sync path the
async layer wraps:
```python
conn = pool.connect()      # ← offloaded by AsyncPool.connect → fairy
cur = conn.cursor()        # ← SYNC passthrough (ACONN-03, no await)
cur.execute("SELECT 42 AS answer")
cur.close()
conn.close()               # ← offloaded + shielded; fires the reset event
```

**Analog (Arrow cleanup on checkin — ACONN-06):** `_pool_factory.py` lines 106 + 407-429
(`_release_arrow_allocators` registered on the pool `"reset"` event). This fires **for free** on
`fairy.close()` — the async checkin offloads `fairy.close()` and the reset listener runs unchanged. Do NOT
build a new async cleanup path. Key fact (line 423-428): the reset event closes open cursors to release
Arrow readers; `reset` is used over `checkin` because checkin gets `None` on invalidation.

**`cursor()` is SYNC (ACONN-03, Pattern 5):** return `AsyncCursor(self._fairy.cursor(), self)` with no
`await` — dbapi `cursor()` constructs an `AdbcStatement`, does no I/O.

**`commit`/`rollback`/`close` offloads (ACONN-04/05):** offload the fairy/dbapi methods. dbapi `Connection`
exposes `commit` (dbapi.py:408), `rollback` (dbapi.py:430), `cursor` (dbapi.py:413). RESEARCH Open-Q1 /
A3: confirm in Wave 0 whether the SQLAlchemy `_ConnectionFairy` passes these through or needs
`.driver_connection` unwrapping — the sync suite calls `fairy.cursor()`/`fairy.close()` directly so those
pass through; `commit`/`rollback` may need the unwrap.

**`_in_use` flag (D-24-03, Pattern 3, EDGE-15) — NEW mechanism, no sync analog (no analog: see below):**
check-and-set the flag in one synchronous span on the loop thread, with **no `await` between check and set**,
then offload, then clear in `finally`:
```python
def _enter_offload(self) -> None:
    if self._in_use:
        raise ConnectionBusyError(...)   # see _exceptions.py analog
    self._in_use = True
def _exit_offload(self) -> None:
    self._in_use = False
```
A cursor's `execute`/`fetch` must guard the **parent connection's** flag (concurrent cursor use = concurrent
connection use).

**`__aexit__` reclaim-on-failure (EDGE-18):** if `__aenter__`/post-checkout raises, reclaim the fairy so
`checkedout()` stays 0. Model the cleanup discipline on the sync test's `cur.close(); conn.close()`
(test_pool_factory.py:64-65) but in a failure path.

---

### `src/adbc_poolhouse/_async/_cursor.py` (cursor wrapper, CRUD + Arrow transform)

**Analog (offloaded methods):** ADBC dbapi `Cursor` surface (`.venv/.../adbc_driver_manager/dbapi.py`):
- `execute(operation, parameters=None)` — dbapi.py:894 (ACUR-01)
- `executemany(operation, seq_of_parameters)` — dbapi.py:930 (ACUR-02)
- `fetchone()` :1001, `fetchmany(size=None)` :1010, `fetchall()` :1021 (ACUR-03)
- `fetch_arrow_table()` :1340 — **returns a fully-materialized `pyarrow.Table`** (verified: `return
  self._results.fetch_arrow_table()`), self-owning and safe after checkin (ACUR-04 / EDGE-21). Do NOT return
  a streaming reader.
- `close()` :843 (ACUR-05, offloaded + shielded)

Each blocking method routes through the single `offload()` helper, guarding the parent connection's `_in_use`.

**Analog (sync passthrough props — ACUR-07, Pattern 5):** dbapi `description` (:819), `rowcount` (:826),
`arraysize` (:801) are pure attribute reads. Mirror as plain `@property` passthroughs — NO `await`, NO offload
(Pitfall 4: a coroutine property triggers "coroutine never awaited"). Model the read-after-execute consistency
note: state is populated by the last (offloaded, serially-completed) `execute`, so a plain read is consistent.

---

### `src/adbc_poolhouse/_async/__init__.py` + `src/adbc_poolhouse/__init__.py` (MOD) (exports)

**Analog:** existing `src/adbc_poolhouse/__init__.py` lines 8-44 — the import block + sorted `__all__`.

**For `_async/__init__.py`:** export `create_async_pool`, `managed_async_pool`, `close_async_pool` with a
sorted `__all__` exactly like the existing pattern (lines 23-44).

**For the package `__init__.py` (MOD):** add `ConnectionBusyError` to the `_exceptions` import (currently
lines 8-11) and to `__all__` (lines 23-44). The async names are exposed via a **PEP 562 lazy `__getattr__`**
(Pattern 6) — NOT a top-level `import` — so `import adbc_poolhouse` stays anyio-free for sync users. There is
no existing `__getattr__` analog in this file; the existing eager import block is the analog for the
*non-lazy* exception export only.

---

### `src/adbc_poolhouse/_exceptions.py` (MOD) — `ConnectionBusyError`

**Analog:** `_exceptions.py` lines 4-27 — `PoolhouseError` base + `ConfigurationError(PoolhouseError, ...)`.
Copy the docstring shape (Google-style, Markdown per MEMORY) and the inheritance pattern.

**Exact requirement (D-24-03):** `ConnectionBusyError` MUST inherit `PoolhouseError` and be exported
alongside it. Suggested body:
```python
class ConnectionBusyError(PoolhouseError):
    """
    Raised when a second task uses an `AsyncConnection` already in use.

    An ADBC connection allows serialized but not concurrent access; check out a
    separate connection per task. ...
    """
```
Message (from CONTEXT D-24-03): *"This connection is already executing in another task; an ADBC connection
allows serialized but not concurrent access. Check out a separate connection per task."*

---

### `tests/_async_harness/stubs.py` (MOD, Wave 0) — re-armable gate + `entered`-after-block

**Analog:** the file itself — `BlockingStubCursor._block` (lines 105-123), `entered` (lines 84-94, 47-55),
`release`/`adbc_cancel`/`close` (lines 151-183).

**Required change (D-CF-01 + WR-01, Pitfall 1):** the gate must **re-arm per blocking call** (Phase 24 does
`execute` THEN `fetch_arrow_table` on one cursor) AND `entered` must fire **after** the worker is inside the
blocked section (currently `entered.set()` at line 118 fires *before* `self._event.wait()` but the loop-facing
`entered` is bridged in `gating.py:95` *before* the stub call even runs). Land both together — a naive re-arm
without the timing fix deadlocked in Phase 23 (commit reverted; see `23-REVIEW-FIX.md` WR-01). Preferred
durable fix: an `on_enter` callback the stub invokes inside `_block`, bridged to the anyio event via
`from_thread.run_sync`. Re-apply WR-03 (set `observed_cancel`/`closed` under `self._lock`) and IN-03 (public
`closed` attr) while in here.

**Belt-and-suspenders fallback:** keep the `_await_inside` bounded-`sleep(0)` poll
(`test_harness.py:60-76`) after `await entered`, and **always `release()` in a `finally`**.

---

### `tests/async/conftest.py` — anyio backend + fixtures

**Analog:** `tests/_async_harness/conftest.py` lines 31-76 — the `anyio_backend` fixture (asyncio + trio
MockClock). **Copy this fixture verbatim** into `tests/async/conftest.py`. Placement is load-bearing
(Pitfall 6): the fixture MUST live in `tests/async/` (ancestor of the async tests only) — NEVER the root
conftest, or the sync suite gets dragged under the anyio plugin and collection breaks.

Add: a real-driver DuckDB `AsyncPool` fixture (EDGE-21) and a stub-backed `AsyncConnection`/`AsyncPool`
fixture wrapping `BlockingStubConnection`.

---

### `tests/async/test_async_lifecycle.py` — happy path

**Analog:** `tests/test_pool_factory.py` lines 56-69 — the canonical create→connect→cursor→execute→close
flow with a real driver, plus the `pool._adbc_source.close()` teardown discipline (lines 30/69). The async
version: `create_async_pool` → `await pool.connect()` → `conn.cursor()` (sync) → `await cur.execute(...)` →
`await cur.fetch_arrow_table()` → `__aexit__` checkin. Mark `@pytest.mark.anyio`, take `anyio_backend_name`.

---

### `tests/async/test_edge_limiter.py` / `test_edge_aliasing.py` — concurrency EDGE tests

**Analog:** `tests/_async_harness/test_harness.py`:
- `_await_inside` poll (lines 60-76) — copy/import; the deterministic "worker is inside" gate.
- `test_max_concurrent` (lines 143-175) — the canonical two-gated-workers + per-event + poll-high-water-mark
  pattern; **direct template for EDGE-12 (bounded concurrency) and EDGE-15 (aliasing → max_concurrent==1)**.
- `test_block_then_release` (lines 82-102) — the `try/await entered.wait()/finally: release()` skeleton;
  ALWAYS release in `finally` (non-cancellable worker would otherwise deadlock the group).
- `test_block_then_adbc_cancel` (lines 105-117) — the gated-cancel shape for EDGE-10 (cancel-while-queued).

**EDGE-09 token accounting:** assert `pool._limiter.borrowed_tokens == 0` after success AND after an
`AdbcError`, in a ×50 loop (RESEARCH Code Examples). The limiter attrs are verified live.

**MEMORY (load-bearing):** run these in a ×N loop (target 0 hangs across 20), never single-shot — a ~33%
deadlock slipped past a single green in Phase 23. Wrap concurrency bodies in `fail_after(watchdog)`.

---

### `tests/test_async_guard.py` (MOD, EDGE-25 / CORE-03) + D-24-04 genericity check

**Analog:** the file itself (lines 20-84) — `scan_async_package` self-tests against synthetic source.

**Required additions:**
- A test pointing `scan_async_package` at the **real** `src/adbc_poolhouse/_async/` and asserting `== []`
  (EDGE-25 / CORE-03). The guard already tolerates an absent root (guard.py:170-172), so this is green-by-default
  until the package lands.
- A `no-backend-specific-names` rule/grep (D-24-04, Open-Q2) asserting no backend class names appear in
  `_async/`. Model a new rule on the existing `_GuardVisitor` rules (guard.py:53-94) or a simple grep test.

---

## Shared Patterns

### The single offload chokepoint (CORE-01 / EDGE-25)
**Source:** `tests/_async_harness/gating.py` lines 93-100 (the `anyio.to_thread.run_sync(..., limiter=..,
abandon_on_cancel=False)` call shape).
**Apply to:** EVERY blocking method across `_pool.py`, `_connection.py`, `_cursor.py` — all route through
the one `offload()` in `_offload.py`. Never call `to_thread.run_sync` directly anywhere else; never alias it.
```python
return await anyio.to_thread.run_sync(lambda: fn(*args), limiter=limiter, abandon_on_cancel=False)
```

### Transient-token discipline (D-24-01, EDGE-09/11/12)
**Source:** by construction from the offload helper — `CapacityLimiter` borrows on entry to `run_sync` and
releases on exit. **Apply to:** every offload. Hold NO token between calls. Do NOT build Option B
(token held checkout→checkin) — it deadlocks (EDGE-11).

### `_in_use` aliasing rejection (D-24-03, EDGE-15)
**Source:** Pattern 3 (no in-repo analog — new). **Apply to:** every offloading method on `AsyncConnection`
AND `AsyncCursor` (cursor guards the parent connection's flag). Check-and-set synchronously on the loop with
NO `await` between check and set; clear in `finally`. Raise `ConnectionBusyError` on the second concurrent entry.

### Shielded checkin/close (ACONN-02/05 / ACUR-05 / APOOL-03, Pattern 4)
**Source:** anyio cancellation finalization idiom (no sync analog — sync has no cancel surface).
**Apply to:** `AsyncConnection.__aexit__`/`close`, `AsyncCursor.__aexit__`/`close`, `managed_async_pool`
close. Wrap the close offload in `anyio.CancelScope(shield=True)` so cancel during teardown cannot leak the
connection:
```python
async def __aexit__(self, *exc: object) -> None:
    with anyio.CancelScope(shield=True):
        await offload(self._fairy.close, limiter=self._limiter)
```

### Arrow cleanup via the existing reset event (ACONN-06)
**Source:** `src/adbc_poolhouse/_pool_factory.py` lines 106 + 407-429 (`_release_arrow_allocators` on the
pool `"reset"` event). **Apply to:** nothing new — it fires automatically on the offloaded `fairy.close()`.
Reuse, do not reimplement.

### Google-style / Markdown docstrings (docs gate, phase ≥7)
**Source:** `_pool_factory.py` docstrings (e.g. `create_pool` lines 163-229: Args/Returns/Raises/Example) and
`_exceptions.py` lines 5-27. **Apply to:** every new public symbol. `Example:` (singular) = admonition with
` ```python ` fences (MEMORY). Markdown, never RST. `create_async_pool`/`managed_async_pool`/`AsyncPool`/
`AsyncConnection`/`AsyncCursor` need an `Example:` block. `mkdocs build --strict` must pass.

---

## No Analog Found

Files/mechanisms with no close in-repo match — the planner should use RESEARCH.md (Patterns 3, 4, 6) instead:

| Item | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `_in_use` check-and-set flag (`_connection.py`) | mechanism | event-driven | First aliasing-rejection primitive in the repo; the sync `QueuePool` has NO per-connection lock (D-24-03 §3). Follow RESEARCH Pattern 3 + Pitfall 3. |
| `CancelScope(shield=True)` checkin (`_connection.py`/`_cursor.py`) | mechanism | request-response | Sync code has no cancellation surface to shield. Follow RESEARCH Pattern 4. |
| PEP 562 lazy `__getattr__` async export (`__init__.py`) | config | n/a | Existing `__init__.py` uses eager imports only; no lazy-import precedent. Follow RESEARCH Pattern 6. |
| `[async]` optional-extra in `pyproject.toml` | config | n/a | No existing optional-extra declaring a runtime dep this way (anyio is currently dev-only). |

## Metadata

**Analog search scope:** `src/adbc_poolhouse/` (factory, exceptions, exports), `tests/` (sync pool tests,
async harness: stubs/gating/guard/conftest/test_harness), `.venv/.../adbc_driver_manager/dbapi.py` (Cursor
surface).
**Files scanned:** ~12 read in full or targeted; dbapi cursor surface grepped + spot-read.
**Pattern extraction date:** 2026-06-27
