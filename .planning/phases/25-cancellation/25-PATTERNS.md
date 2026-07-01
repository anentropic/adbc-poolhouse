# Phase 25: Cancellation - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 11 (3 source, 8 test/docs)
**Analogs found:** 11 / 11 (every file has a concrete in-repo analog)

> All analogs are *in this repo* (Phase 23/24 deliverables). This phase is almost
> pure reuse: the planner should copy structure, not invent it. Where RESEARCH
> §"Recommended Project Structure" and the actual repo disagree, the **repo wins**
> and the discrepancy is flagged below (see the guard self-test note).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/adbc_poolhouse/_async/_cancel.py` | utility (offload helper) | event-driven (watcher/worker task group) | `src/adbc_poolhouse/_async/_offload.py` | role-match (same module family, wraps it) |
| `src/adbc_poolhouse/_async/_cursor.py` (MOD) | wrapper / request-response | request-response → offload | itself (existing `execute`/`fetch*` methods) | exact (in-place rewire) |
| `src/adbc_poolhouse/_async/_connection.py` (MOD: `invalidate()`) | wrapper | request-response → shielded offload | `AsyncConnection.close` (same file, lines 188-207 / 240-241) | exact (mirror of shielded `close`) |
| `tests/_async_harness/stubs.py` (MOD: `BlockingStubConnection.invalidate`) | test fake | event-driven counter | `BlockingStubConnection.close` (same file, lines 337-340) + `BlockingStubCursor.adbc_cancel` D-04 counter | exact (mirror an existing lock-guarded counter) |
| `tests/_async_harness/guard.py` (MOD: new AST rule) | test utility (AST lint) | transform (AST walk) | `_GuardVisitor.visit_Import` / `visit_ImportFrom` (same file, lines 53-79) | role-match (new visitor method, same Finding shape) |
| `tests/async/test_edge_cancel_depth.py` (NEW) | test | event-driven (gated cancel) | `tests/async/test_edge_aliasing.py` + `test_edge_limiter.py::TestEdge10` | exact (same gating choreography) |
| `tests/async/test_edge_exceptiongroup.py` (NEW) | test | request-response (real driver error) | `tests/async/test_edge_limiter.py::test_token_returns_after_error` | role-match (DuckDB `pytest.raises(AdbcError)`) |
| `tests/async/test_edge_backend_parity.py` (NEW) | test | event-driven (dual-backend aggregate) | `tests/async/test_edge_aliasing.py` (dual-backend stub) + EDGE-02 body | role-match (adds session-scoped dict) |
| `tests/async/test_edge_limiter.py` (MOD: EDGE-09 cancel leg) | test | event-driven token accounting | `TestEdge09TokenAccounting` (same file, lines 55-78) + `TestEdge10` cancel | exact (extend existing class) |
| `tests/test_async_guard.py` (MOD: new-rule self-test) | test | transform (synthetic AST) | `TestAsyncGuard.test_bans_asyncio_import` (same file, lines 88-94) | exact (synthetic-source assertion) |
| `docs/src/guides/async.md` (MOD: cancellation section) | docs | prose | "Cleanup is shielded" section (same file, lines 151-161) | exact (replace the "later release" placeholder) |

> **Repo-vs-RESEARCH discrepancy (planner: act on this).** RESEARCH §"Recommended
> Project Structure" lists `tests/async/test_async_guard.py`. The guard self-test
> actually lives at **`tests/test_async_guard.py`** (top-level, sync, NOT under
> `tests/async/`, no `@pytest.mark.anyio`). Add the EDGE-28 new-rule self-test
> there, alongside the existing `TestAsyncGuard` class. The real-package scan
> already runs in `TestRealAsyncPackage.test_scan_real_async_package_is_clean`
> (line 155) and will cover EDGE-28's "real `_async/` stays clean" for free.

---

## Pattern Assignments

### `src/adbc_poolhouse/_async/_cancel.py` (NEW — utility, event-driven)

**Analog:** `src/adbc_poolhouse/_async/_offload.py` (wrap it; do NOT replace it).

**Imports pattern** — copy `_offload.py` header conventions (lines 17-28): `from
__future__ import annotations`, `TYPE_CHECKING`/`TypeVar`, anyio import, and a
`if TYPE_CHECKING:` block for `Callable` + `CapacityLimiter`. The one addition is
`from adbc_poolhouse._async._offload import offload` and `from anyio import
get_cancelled_exc_class`. RESEARCH Pattern 1 (lines 215-268) gives the verbatim
recommended body.

**Critical reuse constraint — keep `to_thread.run_sync` literal in `_offload.py`.**
`_offload.py` documents (lines 12-14) why the attribute chain stays un-aliased:

```python
# _offload.py lines 67-71 — the chokepoint the AST guard matches:
return await anyio.to_thread.run_sync(
    lambda: fn(*args),
    limiter=limiter,
    abandon_on_cancel=False,
)
```

`cancellable_offload`'s `_worker` MUST call `offload(...)` (the helper), never
`anyio.to_thread.run_sync` directly — otherwise the guard's
`to_thread-without-limiter` rule and the `_async/` clean-scan would need a second
chokepoint to audit. The watcher/worker structure (RESEARCH Pattern 1) is the
exact code to author; the single subtle addition is the `except BaseExceptionGroup`
single-member unwrap (RESEARCH lines 259-266) to preserve EDGE-17.

**Docstring requirement (docs gate, phase ≥ 7):** Google-style Args/Returns/Raises,
Markdown not RST. The existing `offload` docstring (`_offload.py` lines 36-66) is
the style template — note its `Args:` block and the explicit "NON-cancellable"
note. The new docstring should explain the watcher/worker pair, the
`cancelled_by_us` flag, and the single-member EG unwrap.

---

### `src/adbc_poolhouse/_async/_cursor.py` (MOD — rewire 6 methods)

**Analog:** the file's own existing methods. The shape is uniform; here is the
exact current `execute` body to transform (lines 178-187):

```python
self._owner._enter_offload()  # noqa: SLF001 (intentional parent guard, see module docstring)
try:
    await offload(
        self._cursor.execute,
        operation,
        parameters,
        limiter=self._limiter,
    )
finally:
    self._owner._exit_offload()  # noqa: SLF001
```

**Rewire to** (RESEARCH Pattern 2, lines 277-294) — swap `offload` for
`cancellable_offload(self._cursor.adbc_cancel, ...)` and add the cancel-cleanup
branch:

```python
self._owner._enter_offload()  # noqa: SLF001
try:
    await cancellable_offload(
        self._cursor.adbc_cancel,
        self._cursor.execute,
        operation,
        parameters,
        limiter=self._limiter,
    )
except get_cancelled_exc_class():
    with anyio.CancelScope(shield=True):
        await self._owner.invalidate()   # poison recovery (D-25-03)
    raise                                # re-raise cancellation, never swallow (D-25-06)
finally:
    self._owner._exit_offload()  # noqa: SLF001
```

**Apply to all six (D-25-04):** `execute` (162-187), `executemany` (189-214),
`fetchone` (216-234), `fetchmany` (236-264), `fetchall` (266-284),
`fetch_arrow_table` (286-310). The `fetchmany` `size is None` branch (lines
253-262) needs the same two-call pattern routed through `cancellable_offload`.

**Do NOT touch `close` (lines 312-333).** It is already `CancelScope(shield=True)`
and deliberately NOT cancellable (D-25-04). Leave it exactly as is.

**Shield reference for the invalidate cleanup** — copy the existing shielded-offload
form already in this file (`close`, lines 327-331):

```python
with anyio.CancelScope(shield=True):
    await offload(self._cursor.close, limiter=self._limiter)
```

**Import addition:** `from adbc_poolhouse._async._cancel import cancellable_offload`
and `from anyio import get_cancelled_exc_class` (or `anyio.get_cancelled_exc_class()`).
`anyio` is already imported (line 35).

**Except ordering (RESEARCH Open Q2 / A2):** `except get_cancelled_exc_class()`
must come BEFORE any group catch. Because `cancellable_offload` unwraps the
single-member group internally, the cursor method only ever sees a bare
cancellation (invalidate path) or a bare `AdbcError` (propagates, NOT invalidated
— Pitfall 6, EDGE-18 contract).

**Docstring requirement:** update each rewired method's `Raises:`/behaviour text to
note the cancel-and-invalidate path (docs gate). Style template: the existing
`close` docstring (lines 313-324) already documents a shield.

---

### `src/adbc_poolhouse/_async/_connection.py` (MOD — add `invalidate()`)

**Analog:** `AsyncConnection.close` in the same file (lines 188-207) and the
shielded `__aexit__` (lines 240-241). `invalidate()` is a near-clone of `close`'s
shielded offload, but offloads `fairy.invalidate` and bypasses `_in_use`.

**Existing shielded-offload to mirror** (`__aexit__`, lines 240-241 — note it
bypasses `_enter_offload` for reclaim-safety, exactly what `invalidate` wants):

```python
with anyio.CancelScope(shield=True):
    await offload(self._fairy.close, limiter=self._limiter)
```

**New method** (RESEARCH Pattern 3, lines 303-306):

```python
async def invalidate(self) -> None:
    with anyio.CancelScope(shield=True):
        await offload(self._fairy.invalidate, limiter=self._limiter)
```

**Why bypass `_in_use`:** the cursor method that calls `invalidate()` still holds
`_in_use` (it is inside its own `try`/`finally`); the docstring on `__aexit__`
(lines 232-234) explains the same reclaim-safety rationale to copy.

**Import:** `offload` (line 42) and `anyio` (line 39) are already imported. No new
import needed.

**Docstring requirement (docs gate — `invalidate` is a NEW public symbol):**
Google-style, Markdown. Use the `close` docstring (lines 189-200) as the template;
explain "drops a poisoned connection from the pool, offloaded + shielded, drives
`pool.checkedout()` → 0" (D-25-03).

---

### `tests/_async_harness/stubs.py` (MOD — `BlockingStubConnection.invalidate`)

**Analog:** two existing patterns in the SAME file:
1. `BlockingStubConnection.close` (lines 337-340) — the lock-guarded counter shape.
2. `BlockingStubCursor.adbc_cancel` (lines 245-258) — the D-04 LOCKED counter+flag
   contract the EDGE assertions read by name.

**Existing `close` to mirror** (lines 337-340):

```python
def close(self) -> None:
    """Increment `close_call_count`."""
    with self._lock:
        self.close_call_count += 1
```

**Add** `invalidate_call_count: int = 0` to `__init__` (alongside lines 320-322)
and an `invalidate()` method that increments it under `self._lock`:

```python
def invalidate(self) -> None:
    """Increment `invalidate_call_count` (mirrors the fairy's poison-recovery)."""
    with self._lock:
        self.invalidate_call_count += 1
```

**D-04 contract discipline (LOCKED attribute names):** the class docstring (lines
296-302) lists the public `Attributes:` contract — add `invalidate_call_count` to
it. `AsyncConnection.invalidate()` calls `self._fairy.invalidate()`, so this method
name is the seam the stub-backed EDGE-02/04/05/29 tests drive (RESEARCH Open Q1 /
A4 — the single harness gap this phase needs). Counter is the asserted signal
(RESEARCH Observable Signals table: `invalidate_call_count == 1` after a cancelled
scope, `== 0` on EDGE-01/07 and on a genuine `AdbcError`).

---

### `tests/_async_harness/guard.py` (MOD — `banned-asyncio-cancelled-error` rule)

**Analog:** the existing `_GuardVisitor` rules `visit_Import` (lines 53-65) and
`visit_ImportFrom` (lines 67-79) — both append a `Finding` with a rule id and
message. Add a NEW `visit_Attribute` method in the same shape.

**Existing rule to mirror** (`visit_Import`, lines 53-65):

```python
def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
    """Flag `import asyncio` and `import asyncio.<sub>`."""
    for alias in node.names:
        if alias.name == "asyncio" or alias.name.startswith("asyncio."):
            self.findings.append(
                Finding(
                    self.path,
                    node.lineno,
                    "banned-asyncio-import",
                    f"`import {alias.name}` is banned in _async/",
                )
            )
    self.generic_visit(node)
```

**Add** (RESEARCH Pattern 4, lines 314-320):

```python
def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
    """Flag `asyncio.CancelledError` attribute access (EDGE-28, D-25-06)."""
    if (
        node.attr == "CancelledError"
        and isinstance(node.value, ast.Name)
        and node.value.id == "asyncio"
    ):
        self.findings.append(
            Finding(
                self.path,
                node.lineno,
                "banned-asyncio-cancelled-error",
                "`asyncio.CancelledError` is banned in _async/; use anyio.get_cancelled_exc_class()",
            )
        )
    self.generic_visit(node)
```

**Module docstring update (docs/intent):** the guard module docstring (lines
13-16) enumerates the enforced rules ("Two rules are enforced") — extend it to
list the new `banned-asyncio-cancelled-error` rule. Update the `Finding.rule`
docstring (lines 33-37) to include the new rule id.

---

### `tests/test_async_guard.py` (MOD — new-rule self-test)

**Analog:** `TestAsyncGuard.test_bans_asyncio_import` (lines 88-94) — write a
synthetic source string into `tmp_path`, scan, assert the rule fires.

**Existing self-test to mirror** (lines 88-94):

```python
def test_bans_asyncio_import(self, tmp_path: Path) -> None:
    """`import asyncio` and `from asyncio import ...` each raise a finding."""
    (tmp_path / "a.py").write_text("import asyncio\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from asyncio import sleep\n", encoding="utf-8")
    findings = scan_async_package(tmp_path)
    rules = [f.rule for f in findings]
    assert rules.count("banned-asyncio-import") == 2
```

**Add** a `test_bans_asyncio_cancelled_error` that writes e.g.
`"try:\n    pass\nexcept asyncio.CancelledError:\n    pass\n"` and asserts a
`banned-asyncio-cancelled-error` finding. The real-package clean-scan is ALREADY
covered by `TestRealAsyncPackage.test_scan_real_async_package_is_clean` (line 155)
— no new real-scan test needed for EDGE-28.

> This is the **`tests/test_async_guard.py`** file (top-level, sync, no anyio mark),
> NOT `tests/async/test_async_guard.py` as RESEARCH §Structure states.

---

### `tests/async/test_edge_cancel_depth.py` (NEW — EDGE-01/02/03/04/05/06/07)

**Analog:** `tests/async/test_edge_aliasing.py` (gating choreography) and
`tests/async/test_edge_limiter.py::TestEdge10CancelWhileQueued` (cancel-scope +
`await_inside` + `real_clock_watchdog` + release-in-`finally`).

**Module header + helper import to copy verbatim** (from `test_edge_aliasing.py`
lines 18-34 — note the `importlib` dance for the `async`-reserved-keyword dir):

```python
from __future__ import annotations
import functools
import importlib
import anyio
import pytest
from adbc_poolhouse import ConnectionBusyError  # (cancel tests import what they need)
from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
```

**Gating choreography to copy** (from `test_edge_aliasing.py` lines 59-74): wrap
the body in `with real_clock_watchdog(stub_conn.cursors) as watchdog:`, start the
gated worker via `tg.start_soon(functools.partial(first_cur.execute, "SELECT 1"))`,
`await await_inside(lambda: blocking_stub.execute_call_count == 1)` to confirm the
worker is inside, then drive the cancel, then `assert watchdog[0] is False`.

**Cancel-scope trigger to copy** (from `TestEdge10` lines 116-121 and RESEARCH
EDGE-02 example lines 409-423): use `anyio.move_on_after(0)` or a nested task group's
`cancel_scope.cancel()` to cancel the gated `execute`. Fixtures available:
`make_stub_async_connection` (conftest line 97), `anyio_backend_name`.

**Asserted signals (RESEARCH Observable Signals table):** `adbc_cancel_call_count
== 1` (EDGE-02/06), `== 0` (EDGE-01/07), `== 1` not 2 (EDGE-04 double-cancel);
`invalidate_call_count == 1` (EDGE-02/04/05); `tripped[0] is False` always; a
DuckDB real-driver leg additionally asserts `pool.checkedout() == 0`.

**Loop discipline (MEMORY + CONTEXT specifics):** every cancel test runs in a ×20
loop, 0 hangs, under BOTH backends, watchdog-wrapped. EDGE-06 uses
`virtual_clock(anyio_backend_name)` + `anyio.fail_after`/`move_on_after` ONLY as
the cancellation trigger under test — NEVER as the watchdog (use
`real_clock_watchdog`; `fail_after` autojumps under trio MockClock).

---

### `tests/async/test_edge_exceptiongroup.py` (NEW — EDGE-19)

**Analog:** `tests/async/test_edge_limiter.py::test_token_returns_after_error`
(lines 69-78) — real DuckDB pool, `pytest.raises(AdbcError)`, assert pool state.

**Existing real-driver-error assertion to mirror** (lines 69-77):

```python
@pytest.mark.anyio
async def test_token_returns_after_error(self, duckdb_async_pool: AsyncPool) -> None:
    for _ in range(_ACCOUNTING_LOOPS):
        with pytest.raises(AdbcError):
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT * FROM does_not_exist")
        limiter = duckdb_async_pool._limiter
        assert limiter.borrowed_tokens == 0
```

**For EDGE-19** (RESEARCH lines 444-454): assert `pytest.raises(AdbcError)` — NOT
`ExceptionGroup` — escapes a `SELECT * FROM does_not_exist` after the
`cancellable_offload` rewire, proving the single-member EG unwrap preserves the
bare type, AND `duckdb_async_pool._pool.checkedout() == 0` (connection returned via
the reset path, NOT invalidated — the non-cancel branch). Import
`from adbc_driver_manager import Error as AdbcError` (as `test_edge_limiter.py`
line 30 does). Uses the `duckdb_async_pool` fixture (conftest line 75).

---

### `tests/async/test_edge_backend_parity.py` (NEW — EDGE-29)

**Analog:** `test_edge_aliasing.py` dual-backend stub body + the EDGE-02 cancel
body from `test_edge_cancel_depth.py`. The new mechanic is a session-scoped dict
fixture both backend legs write into, plus one cross-leg equality assertion.

**Pattern (RESEARCH lines 456-467):** run the canonical EDGE-02 cancel on each
backend leg, write `(adbc_cancel_count, invalidate_count, checkedout_after)` into a
session-scoped dict keyed by `anyio_backend_name`, then a finalizer or
non-parametrized test asserts the asyncio and trio tuples are EQUAL. Keep both
legs' setup byte-identical so the only variable is the backend. Signals come from
the same `BlockingStubCursor.adbc_cancel_call_count` /
`BlockingStubConnection.invalidate_call_count` the depth tests read.

---

### `tests/async/test_edge_limiter.py` (MOD — EDGE-09 cancel-mid-block leg)

**Analog:** `TestEdge09TokenAccounting` in the SAME file (lines 55-78) — extend
this class with the cancel leg D-24-02 deferred to Phase 25 (the module docstring
lines 12-14 explicitly note its absence).

**Existing accounting loop to mirror** (lines 59-66):

```python
@pytest.mark.anyio
async def test_token_returns_after_success(self, duckdb_async_pool: AsyncPool) -> None:
    """After a normal round trip, `borrowed_tokens` is 0 --- across a x50 loop."""
    for _ in range(_ACCOUNTING_LOOPS):
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1 AS n")
            await cur.fetch_arrow_table()
        assert duckdb_async_pool._limiter.borrowed_tokens == 0
```

**Add** `test_token_returns_after_cancel` (×50 loop): gate a stub-backed worker
inside `execute`, cancel it (via `move_on_after(0)` / `cancel_scope.cancel()`),
then assert `limiter.borrowed_tokens == 0` after the cancelled `cancellable_offload`
(transient-token model — `adbc_cancel` unblocks the worker, the offload returns,
the token releases exactly once). Use the stub path (`_stub_conn_on`, line 48,
+ `await_inside` + `real_clock_watchdog`) since the cancel must honestly join a
non-cancellable worker. Update the module docstring (lines 12-14) to remove the
"deliberately NO cancel-mid-block test" note.

---

### `docs/src/guides/async.md` (MOD — cancellation/timeout section)

**Analog:** the existing "Cleanup is shielded" section (lines 151-161) — same
file, same register. It currently contains the placeholder to REPLACE:

```markdown
Full cancellation handling for in-flight queries (cooperative `adbc_cancel` and
the cancel-mid-query path) lands in a later release. The shield that protects
check-in and pool close ships now.
```

**Replace** with a cancellation/timeout section documenting: `fail_after` /
`move_on_after` around `execute` / `fetch_arrow_table`, the cooperative
`adbc_cancel` abort, invalidate-on-cancel (`pool.checkedout()` stays correct),
identical behaviour under asyncio and trio. Cross-link `AsyncConnection.invalidate`
in the API reference (the "See also" block, lines 163-169, shows the link style).
Markdown not RST; humanizer pass (CLAUDE.md docs gate). Build check:
`.venv/bin/mkdocs build --strict` (MEMORY: prefer `.venv/bin/` over `uv run` under
sandbox).

---

## Shared Patterns

### Shielded offload (cleanup that must complete)
**Source:** `_connection.py` lines 240-241 (`__aexit__`), `_cursor.py` lines 327-331
(`close`).
**Apply to:** `AsyncConnection.invalidate` (new), the cursor methods'
`except get_cancelled_exc_class()` cleanup branch, the `cancellable_offload`
watcher's `adbc_cancel` call.
```python
with anyio.CancelScope(shield=True):
    await offload(self._fairy.close, limiter=self._limiter)  # or .invalidate / adbc_cancel
```

### Re-raise the framework cancellation, never swallow (D-25-06)
**Source:** RESEARCH Pattern 1 watcher (`raise` after the shielded `adbc_cancel`)
and Pattern 2 cursor cleanup (`raise` after `invalidate`).
**Apply to:** `_cancel.py` watcher, every rewired `_cursor.py` cancel branch.
The cleanup is shielded; the `raise` is mandatory (Pitfall 5 — swallowing hangs
`fail_after` / breaks trio structured cancellation).

### Lock-guarded counter on the stub (D-04 LOCKED contract)
**Source:** `stubs.py` — `BlockingStubCursor.adbc_cancel` (lines 245-258, counter
+ flag under one lock), `BlockingStubConnection.close` (lines 337-340).
**Apply to:** the new `BlockingStubConnection.invalidate` + `invalidate_call_count`.
Write the counter under `self._lock` so a loop-thread reader never sees a torn
state (WR-03).

### `Finding`-shaped AST rule (one method per rule)
**Source:** `guard.py` `_GuardVisitor.visit_Import` / `visit_ImportFrom` (lines
53-79) — each appends `Finding(self.path, node.lineno, "<rule-id>", "<message>")`
then calls `self.generic_visit(node)`.
**Apply to:** the new `visit_Attribute` (`banned-asyncio-cancelled-error` rule).

### Gated stub-cancel test choreography (no sleeps, watchdog-wrapped)
**Source:** `test_edge_aliasing.py` lines 59-74, `test_edge_limiter.py::TestEdge10`
lines 103-141.
**Apply to:** all of `test_edge_cancel_depth.py`, `test_edge_backend_parity.py`,
the `test_edge_limiter.py` cancel leg.
```python
with real_clock_watchdog(stub_conn.cursors) as watchdog:
    async with anyio.create_task_group() as tg:
        tg.start_soon(functools.partial(first_cur.execute, "SELECT 1"))
        try:
            await await_inside(lambda: stub_conn.cursors[0].execute_call_count == 1)
            # ... drive the cancel scope here ...
        finally:
            for cur in stub_conn.cursors:
                cur.release()
assert watchdog[0] is False
```

### Dual-backend parametrization
**Source:** `conftest.py` `anyio_backend` fixture (lines 46-72) — already supplies
asyncio + trio MockClock; tests request `anyio_backend_name`.
**Apply to:** every new/modified async test (each runs once per backend; EDGE-29
asserts the per-backend tuples are equal).

### Docs gate (phase ≥ 7, CLAUDE.md)
**Apply to:** `_cancel.py` (`cancellable_offload` docstring),
`_connection.py` (`invalidate` docstring — new public symbol),
`_cursor.py` (rewired-method behaviour text), `docs/src/guides/async.md`.
Google-style Args/Returns/Raises, Markdown not RST, `Example:` singular for
admonition blocks (MEMORY). Build: `.venv/bin/mkdocs build --strict`.

---

## No Analog Found

None. Every file in this phase has a concrete in-repo analog (Phase 23/24 built
the harness, the offload chokepoint, the shielded check-in, the AST guard, and the
EDGE test template specifically to be extended here). The only genuinely new
*structure* is `cancellable_offload`'s watcher/worker task group, and even that is
spelled out verbatim in RESEARCH Pattern 1 (lines 215-268) and built only from
existing anyio primitives (`create_task_group`, `Event`, `CancelScope(shield=True)`,
`get_cancelled_exc_class`).

## Metadata

**Analog search scope:** `src/adbc_poolhouse/_async/`, `tests/_async_harness/`,
`tests/async/`, `tests/test_async_guard.py`, `docs/src/guides/async.md`.
**Files scanned (read in full):** `_offload.py`, `_cursor.py`, `_connection.py`,
`stubs.py`, `guard.py`, `_edge_helpers.py`, `test_edge_limiter.py`,
`test_edge_aliasing.py`, `conftest.py`, `test_async_guard.py`, `async.md` (relevant
section). Plus both CONTEXT.md and RESEARCH.md (full).
**Pattern extraction date:** 2026-06-28
