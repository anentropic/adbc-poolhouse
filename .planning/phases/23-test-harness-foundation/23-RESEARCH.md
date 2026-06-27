# Phase 23: Test Harness Foundation - Research

**Researched:** 2026-06-27
**Domain:** Deterministic, backend-neutral async test infrastructure (anyio 4.x / trio / aiotools) + AST source-scan guard, Python 3.14 / pytest 9
**Confidence:** HIGH on the riskiest assumption (anyio trio backend forwards `clock=` — verified against anyio master source), HIGH on aiotools/trio APIs (official docs), HIGH on AST guard mechanics, HIGH on stack versions (PyPI verified 2026-06-27).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 — Virtual clock is a first-class Phase 23 deliverable**, built as a single backend-dispatching façade. Trio leg: `trio.testing.MockClock(autojump_threshold=0)` injected at the runner via the `anyio_backend` fixture options. Asyncio leg: `aiotools.VirtualClock().patch_loop()` used as an in-body context manager. The façade dispatches on `anyio_backend_name` (runner-level injection vs in-body patch are structurally different).
- **D-02 — Event-gating is the PRIMARY mechanism** for cancel-path determinism (forever-blocking stub released by the test or by `adbc_cancel`, plus a sibling task calling `scope.cancel()`). The virtual clock covers deadline/timeout paths (EDGE-06 P1, P2 timeout-precision cases).
- **D-03 — `BlockingStubCursor` / `BlockingStubConnection` are pure-`threading` fakes with ZERO async code.** They implement the dbapi surface (`execute`, `fetch_arrow_table`, `close`, `adbc_cancel`). `execute`/`fetch_arrow_table` block on a `threading.Event`; `adbc_cancel()` releases that event AND flips `observed_cancel`.
- **D-04 — Stub records exactly:** per-call **thread-id**, **call counts**, **`observed_cancel`**, an **`entered`** signal (set on worker entry), and **`max_concurrent_in_execute`** (counter incremented on entry / decremented on exit under a lock).
- **D-05 — The guard is an AST/source-scan callable returning a findings list.** Rules: ban `import asyncio`; ban bare `to_thread.run_sync(...)` WITHOUT a `limiter=` argument, scoped to the `_async/` package. Scans a configurable path, no-ops gracefully on absent/empty dir, tested against synthetic fixture source strings.
- **D-06 — Phase 23 stands up the `anyio_backend` parametrization** (`["asyncio", "trio"]`) in a test conftest, plus harness self-tests exercising both legs (block→release and block→`adbc_cancel`→unblock) with no real sleeps.
- **D-07 — Add `anyio`, `trio`, `aiotools` as dev/test-only deps.** The runtime `[async]` extra stays DEFERRED to Phase 26 — adding anyio to runtime now would contradict the zero-cost-sync-path goal.

### Claude's Discretion

- Exact harness module layout under `tests/` (e.g. `tests/_async_harness/`, `tests/async_/conftest.py`, or flat `tests/harness.py`) — planner's choice, consistent with the existing flat `tests/` layout.
- The precise bridge for the `entered` signal from worker thread → loop without a real sleep (anyio `Event` set via `from_thread`, or a poll on an anyio `Event`) — researcher to pin (PINNED below, see Pattern 3).

### Deferred Ideas (OUT OF SCOPE)

- Actual async wrappers (`AsyncPool`/`AsyncConnection`/`AsyncCursor`, offload helper, per-pool limiter) — Phase 24.
- Behavioral EDGE-NN tests that run the harness against real wrapper behaviour — Phases 24/25.
- Cancellation logic (`adbc_cancel` wiring, shielded checkin, invalidate-on-cancel) — Phase 25.
- Meta-guard that asserts every async test is dual-parametrized (EDGE-27/30 as suite-level assertions) — Phase 27. Phase 23 ships only the *callable guard infrastructure*.
- Real-backend / dual-backend matrix tests (DuckDB + Snowflake cassette) — Phase 27.
- The `[async]` runtime extra + PEP 562 lazy import — Phase 26.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-05 | A shared deterministic test harness exists — a `BlockingStubCursor` (blocks on a `threading.Event` released only by the test or by `adbc_cancel`; records thread-id, call counts, max-concurrent-in-execute) plus event-gating/virtual-clock helpers and a source-scan/import-lint guard — so edge-case tests need no real sleeps | Pattern 1 (stub), Pattern 2 (virtual-clock façade — trio `clock=` injection VERIFIED, aiotools asyncio leg CITED), Pattern 3 (`entered` bridge PINNED), Pattern 4 (AST guard, hand-rolled `ast.NodeVisitor` recommended over import-linter), Validation Architecture (harness self-tests) |
</phase_requirements>

## Summary

This phase builds three test-only deliverables. The research load was concentrated on one high-risk assumption flagged in CONTEXT and five open questions; all are now resolved with HIGH confidence.

**The riskiest assumption is CONFIRMED.** anyio's pytest plugin forwards the `anyio_backend_options` dict straight through to the trio runner: `extract_backend_and_options` splits the `("trio", {...})` tuple, then the trio backend's `TestRunner.__init__(**options)` stores it and `_call_in_runner_task` calls `trio.lowlevel.start_guest_run(..., **self._options)`. Because `start_guest_run` accepts the same `clock=` kwarg as `trio.run`, passing `anyio_backend = ("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})` injects the MockClock into the trio loop. This is VERIFIED against anyio master source (`_backends/_trio.py`, `pytest_plugin.py`), not taken on faith.

The asyncio leg is structurally different and must stay an in-body context manager: `aiotools.VirtualClock().patch_loop()` patches the *running* asyncio loop so `asyncio.sleep` returns instantly while virtual time advances — it has no runner-injection hook. This asymmetry is exactly why D-01 makes the façade dispatch on `anyio_backend_name`. The `BlockingStubCursor` (pure `threading`, zero async per D-03) and event-gating remain the primary determinism mechanism; the clock covers only timeout/deadline paths (EDGE-06, EDGE-31/32 in later phases). The AST guard is best hand-rolled as an `ast.NodeVisitor` returning a findings list — `import-linter` and ruff custom rules do not fit the "callable returning a list a test can assert empty" contract.

**Primary recommendation:** Build a flat `tests/_async_harness/` package (`stubs.py`, `clock.py`, `guard.py`) plus an `anyio`-parametrized `conftest.py`, with self-tests that drive both legs through event-gating (no real sleeps). Pin `anyio>=4.13`, `trio>=0.31`, `aiotools>=2.2` in the `dev` dependency-group only. The `entered` worker→loop bridge must live in the harness offload glue (NOT the pure-threading stub): the worker, being an anyio worker thread spawned by `to_thread.run_sync`, calls `anyio.from_thread.run_sync(entered_event.set)` with no token needed.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `BlockingStubCursor` / `BlockingStubConnection` blocking + recording | Test harness (pure `threading`, sync) | — | D-03: sync-only is what makes them framework-neutral; they impersonate the dbapi surface the *future* offload calls into |
| `entered` signal worker→loop bridge | Test harness offload glue (anyio worker thread → loop) | — | Pure-threading stub cannot call anyio; bridge belongs in the harness's offload wrapper, which runs on an anyio worker thread |
| Virtual-clock façade (dispatch) | Test harness (`anyio_backend_name`) | trio runner (injection) / asyncio loop (in-body patch) | D-01: two structurally different injection points unified behind one façade |
| `anyio_backend` parametrization | Test conftest fixture | anyio pytest plugin | D-06: suite-level neutrality guarantee |
| AST source-scan guard | Test harness (stdlib `ast`) | — | D-05: callable returning findings list; scans `_async/` which does not exist yet |
| Dependency wiring (`anyio`/`trio`/`aiotools`) | `pyproject.toml` `[dependency-groups] dev` | — | D-07: dev/test-only; must NOT leak into the built wheel or runtime deps |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anyio` | `>=4.13` (latest 4.14.1, 2026-06-24) | Backend-neutral async API + pytest plugin (`anyio_backend` fixture, `pytest.mark.anyio`) | The whole milestone's neutrality foundation; the plugin ships *with* anyio (no separate install) `[VERIFIED: PyPI anyio 4.14.1; anyio testing docs]` |
| `trio` | `>=0.31` (latest 0.33.0, 2026-02-14) | The trio backend + `trio.testing.MockClock` for the trio virtual-clock leg | Required for the `["asyncio","trio"]` parametrization and the runner-injected mock clock `[VERIFIED: PyPI trio 0.33.0; trio testing docs]` |
| `aiotools` | `>=2.2` (latest 2.2.3, min Python 3.11) | `VirtualClock().patch_loop()` for the asyncio virtual-clock leg | The canonical asyncio loop-patching virtual clock; in-body context manager `[CITED: aiotools.readthedocs.io/en/latest/aiotools.timer.html]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | `9.0.3` (already installed) | Test runner | Already present; note INSTALLED is 9.0.3, NOT the `>=8.0.0` floor in pyproject — anyio 4.14.1 supports pytest 8/9 |
| stdlib `ast` | (3.14 stdlib) | Source-scan guard (`ast.parse` + `ast.NodeVisitor`) | D-05 guard — no third-party dependency `[VERIFIED: stdlib]` |
| stdlib `threading` | (3.14 stdlib) | Stub blocking primitive (`threading.Event`, `threading.Lock`) | D-03/D-04 stub internals — no async `[VERIFIED: stdlib]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled `ast.NodeVisitor` guard | `import-linter` (contract-based) | import-linter checks *module dependency* contracts, not call-arg shapes; it cannot express "ban `to_thread.run_sync` without `limiter=`" and does not return a Python findings list a test asserts empty. REJECTED for D-05. |
| Hand-rolled `ast.NodeVisitor` guard | ruff custom rule / flake8 plugin | Requires a plugin entry point and runs as a linter process, not an importable callable; wrong contract shape. REJECTED. |
| `aiotools.VirtualClock` (asyncio) | anyio-native fake clock | anyio has no public uniform fake-clock across both backends; this is *why* D-01 splits the façade. The asyncio loop-patch is the pragmatic path. |
| `trio.testing.MockClock` runner injection | in-body `autojump_clock` fixture | trio's clock must be set at `trio.run`/guest-run start; it cannot be swapped mid-run. Runner injection via `anyio_backend` options is the only correct trio path (VERIFIED). |

**Installation (dev group only — D-07):**
```bash
uv add --dev anyio trio aiotools
```

**Version verification (performed 2026-06-27 against PyPI JSON API):**
- `anyio` latest **4.14.1** (2026-06-24); supports Python 3.14; ships pytest plugin. Recent: 4.14.0 (2026-06-15), 4.13.0 (2026-03-24).
- `trio` latest **0.33.0** (2026-02-14); supports Python 3.14. Recent: 0.32.0 (2025-10-31), 0.31.0 (2025-09-09).
- `aiotools` latest **2.2.3** (min Python 3.11, Python 3.14 classifier present); MIT; repo `github.com/achimnol/aiotools`.

> NOTE: None of the three are currently installed in `.venv` (verified `import` failures 2026-06-27). The plan's first task must install them into the dev group.

## Package Legitimacy Audit

> `gsd-tools query package-legitimacy check` was unavailable on this host (not on PATH). Verdicts below are from direct PyPI JSON verification + repo confirmation on 2026-06-27.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `anyio` | PyPI | mature (4.x series, years) | very high (transitive dep of httpx/starlette/etc.) | github.com/agronholm/anyio (MIT, ~2.5k stars, canonical) | OK | Approved |
| `trio` | PyPI | mature (0.33.0; long-established) | high | github.com/python-trio/trio (canonical) | OK | Approved |
| `aiotools` | PyPI | mature (2.2.3; v1.0 shipped VirtualClock years ago) | PyPI stats disabled on package, but established (achimnol/aiotools, MIT) | github.com/achimnol/aiotools (MIT) | OK | Approved |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*All three are well-established, repo-backed PyPI packages confirmed against official docs/PyPI on 2026-06-27. `aiotools` is the least famous of the three but is the documented home of `VirtualClock` and is repo-backed; no checkpoint needed, but the planner may add a one-line confidence note since download stats are disabled on its PyPI page.*

## Architecture Patterns

### System Architecture Diagram

```
                          ┌──────────────────────────────────────────────┐
   pytest collection ───► │  conftest.py: anyio_backend fixture           │
   (@pytest.mark.anyio)   │  params = ["asyncio", ("trio", {clock: MC})]  │
                          └───────────────┬──────────────────────────────┘
                                          │ anyio_backend_name dispatch
                  ┌───────────────────────┴────────────────────────┐
                  ▼                                                 ▼
        asyncio leg                                         trio leg
   ┌────────────────────────┐                      ┌──────────────────────────┐
   │ virtual_clock() façade │                      │ virtual_clock() façade   │
   │  → aiotools.VirtualClk │                      │  → no-op CM (clock is     │
   │    .patch_loop()  (CM) │                      │    already injected at    │
   │  in-body, patches loop │                      │    the runner)            │
   └───────────┬────────────┘                      └────────────┬─────────────┘
               │                                                 │
               └──────────────────┬──────────────────────────────┘
                                  ▼
              ┌──────────────────────────────────────────────┐
   test body  │ await offload_glue(stub.execute, sql,         │
              │                    limiter=L)                  │   ← future Phase 24
              │   ── anyio.to_thread.run_sync ──┐              │     surface (harness
              └─────────────────────────────────┼──────────────┘     models the call)
                                                ▼  (worker thread)
                          ┌──────────────────────────────────────┐
                          │ BlockingStubCursor.execute(sql)        │
                          │  • record thread-id, call count        │
                          │  • max_concurrent_in_execute++ (lock)  │
                          │  • from_thread.run_sync(entered.set) ◄─┼── bridge lives in
                          │  • event.wait()  ◄── blocks forever    │   offload glue,
                          │  • max_concurrent_in_execute-- (lock)  │   NOT the stub
                          └───────────┬───────────────────────────┘
                                      ▲
        test sets event ─────────────┤  OR  adbc_cancel(): event.set() + observed_cancel=True
                                      │                            ▲
                          sibling task scope.cancel() ────────────┘ (triggers the
                                                                     Phase 24/25 cancel
                                                                     path that calls adbc_cancel)

   ┌────────────────────────────────────────────────────────────────────────┐
   │ guard.scan_async_package(path) → list[Finding]   (stdlib ast, sync)      │
   │   • ban `import asyncio` / `from asyncio import …`                        │
   │   • ban `to_thread.run_sync(...)` lacking a `limiter=` keyword            │
   │   • no-op on absent/empty dir; tested vs synthetic source strings         │
   └────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (Claude's-discretion layout — consistent with flat `tests/`)
```
tests/
├── _async_harness/          # underscore = not collected as a test module by default discovery
│   ├── __init__.py
│   ├── stubs.py             # BlockingStubCursor / BlockingStubConnection (pure threading, D-03/D-04)
│   ├── clock.py             # virtual_clock() façade (dispatch on anyio_backend_name, D-01)
│   ├── gating.py            # entered-signal bridge + offload glue helpers (Pattern 3)
│   └── guard.py             # scan_async_package() AST callable (D-05)
├── conftest.py              # existing — add nothing async here (keep autouse env fixture isolated)
└── test_async_harness.py    # harness self-tests (D-06): both legs, block→release, block→cancel→unblock
```
> A `tests/async_conftest.py` or a `conftest.py` inside `_async_harness/` can define the `anyio_backend` fixture so it scopes only to async tests, keeping the existing sync suite untouched (relevant to future PKG-04 "sync suite passes without anyio").

### Pattern 1: Pure-threading BlockingStubCursor (D-03 / D-04)
**What:** A sync fake of the dbapi cursor surface that blocks forever on a `threading.Event` until the test or `adbc_cancel` releases it, recording everything the EDGE table needs.
**When to use:** Backs EDGE-01..12, 15, 17, 25, 26, 28, 29, 31, 32 across Phases 24/25/27. The attribute names below become a HARD CONTRACT.
**Example:**
```python
# Pattern (synthesized from D-03/D-04 + ASYNC-EDGE-CASES.md §"Shared test infrastructure")
# NO anyio import here — pure threading keeps the stub framework-neutral.
from __future__ import annotations
import threading


class BlockingStubCursor:
    """Sync dbapi-shaped fake whose execute/fetch block until released."""

    def __init__(self, *, entered: threading.Event | None = None) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self.entered = entered or threading.Event()  # set on worker entry
        self.observed_cancel = False
        self.execute_call_count = 0
        self.fetch_call_count = 0
        self.adbc_cancel_call_count = 0
        self.close_call_count = 0
        self.execute_thread_ids: list[int] = []
        self._in_execute = 0
        self.max_concurrent_in_execute = 0
        self._closed = False

    def _block(self) -> None:
        # caller records entry/concurrency around this; the bridge sets `entered`
        with self._lock:
            self._in_execute += 1
            self.max_concurrent_in_execute = max(self.max_concurrent_in_execute, self._in_execute)
        try:
            self.entered.set()              # signal "worker is inside execute" (see Pattern 3)
            self._event.wait()              # blocks FOREVER until released
        finally:
            with self._lock:
                self._in_execute -= 1

    def execute(self, operation: str, parameters: object = None) -> None:
        with self._lock:
            self.execute_call_count += 1
            self.execute_thread_ids.append(threading.get_ident())
        self._block()

    def fetch_arrow_table(self) -> object:
        with self._lock:
            self.fetch_call_count += 1
        self._block()
        return None  # later phases inject a real pyarrow.Table when needed

    def adbc_cancel(self) -> None:
        with self._lock:
            self.adbc_cancel_call_count += 1
        self.observed_cancel = True
        self._event.set()                   # releases the blocked execute/fetch

    def close(self) -> None:
        with self._lock:
            self.close_call_count += 1
        self._closed = True
        self._event.set()                   # never leave a blocked worker

    def release(self) -> None:
        """Test-only: unblock without cancel (the happy-path release)."""
        self._event.set()
```
> The stub records `execute_thread_ids` (per-call thread-id, D-04) so EDGE-25 can assert worker-id ≠ loop-id. `max_concurrent_in_execute` (counter under a lock) backs EDGE-12/EDGE-15. `adbc_cancel` flips `observed_cancel` AND releases — exactly D-03.

### Pattern 2: Virtual-clock façade dispatching on `anyio_backend_name` (D-01) — riskiest assumption VERIFIED
**What:** One callable the test enters; it picks the right mechanism per backend.
**When to use:** Timeout/deadline tests (EDGE-06 P1; EDGE-31/32 P2). Event-gating (Pattern 3) remains primary for cancel paths (D-02).

**Trio leg — runner injection via `anyio_backend` options (VERIFIED against anyio master + trio docs):**
```python
# conftest.py
import pytest
import trio.testing

@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: pytest.FixtureRequest) -> object:
    if request.param == "trio":
        # VERIFIED: anyio TrioBackend.TestRunner.__init__(**options) stores this dict and
        # _call_in_runner_task calls trio.lowlevel.start_guest_run(..., **options).
        # start_guest_run accepts clock= just like trio.run, so the MockClock reaches the loop.
        return ("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})
    return "asyncio"
```
```python
# clock.py — the façade
import contextlib
import aiotools

@contextlib.contextmanager
def virtual_clock(anyio_backend_name: str):
    if anyio_backend_name == "trio":
        # Clock already injected at the runner; nothing to do in-body.
        yield
    else:  # asyncio
        with aiotools.VirtualClock().patch_loop():
            yield
```
```python
# usage in a (future) timeout test
@pytest.mark.anyio
async def test_timeout(anyio_backend_name):
    with virtual_clock(anyio_backend_name):
        with anyio.fail_after(5):       # advances on virtual time on BOTH legs
            ...
```
- **Trio:** `trio.testing.MockClock(rate=0.0, autojump_threshold=inf)`; `autojump_threshold=0` makes the clock jump to the next scheduled timeout the moment all tasks are blocked → `fail_after`/`move_on_after` fire instantly, no wall-clock. `[VERIFIED: anyio master `_backends/_trio.py` TestRunner + `pytest_plugin.py` extract_backend_and_options; trio docs trio.run/MockClock]`
- **Asyncio:** `aiotools.VirtualClock().patch_loop()` is a *sync* context manager that patches the running loop so `loop.time()`/sleep advance virtually; `await asyncio.sleep(3600)` returns instantly while virtual time reads 3600. anyio's asyncio backend uses the standard running loop, so anyio timeouts (which key off `loop.time()` deadlines) ride the patched clock. `[CITED: aiotools.readthedocs.io aiotools.timer; aiotools docs example]`

> **Plan caveat (carry into the plan as a verify step):** the trio `anyio_backend` fixture is *param-driven*, so the MockClock instance is constructed once per param resolution. If a session/module-scoped fixture is used, the SAME MockClock is shared across tests in that scope — construct it fresh per test (function-scoped `anyio_backend` fixture, as above) to avoid clock state bleed. A self-test should assert a `fail_after` fires under the trio leg without consuming wall-clock (e.g. wrap the whole test in an outer real-time `fail_after(5)` watchdog and assert the inner virtual `fail_after(3600)` still fires).

### Pattern 3: The `entered` worker→loop bridge without a real sleep (Claude's-discretion item — PINNED)
**What:** The test (on the loop) must wait until the worker thread has actually entered the blocked `execute`, deterministically, before triggering cancel/timeout — otherwise the trigger races the worker.
**The key constraint:** the stub is pure-threading (D-03) and CANNOT import anyio. So the bridge lives in the **harness offload glue**, which runs on an **anyio worker thread** (spawned by `to_thread.run_sync`). From an anyio worker thread, `anyio.from_thread.run_sync(fn)` runs `fn` on the loop **without needing a token**.
**Recommended (PINNED): anyio `Event` set from the worker via `from_thread.run_sync`.**
```python
# gating.py
import anyio
from anyio import to_thread

async def run_blocking(stub_call, *args, entered: anyio.Event, limiter):
    """Harness offload glue — models the future Phase 24 offload + bridges `entered`."""
    def _worker():
        # We are on an anyio worker thread → from_thread.run_sync needs no token.
        anyio.from_thread.run_sync(entered.set)   # signal the loop BEFORE blocking
        return stub_call(*args)                   # this blocks on the stub's threading.Event
    return await to_thread.run_sync(_worker, limiter=limiter)
```
```python
# in a test
entered = anyio.Event()
async with anyio.create_task_group() as tg:
    tg.start_soon(run_blocking, stub.execute, "SELECT 1", entered=entered, limiter=limiter)
    await entered.wait()        # deterministic: returns the instant the worker is in execute
    # now trigger: stub.release()  OR  scope.cancel()  OR  let virtual clock fire fail_after
```
> Two viable variants existed (CONTEXT left this to the researcher): (a) **anyio `Event` set via `from_thread.run_sync`** — chosen; fully deterministic, no poll, no sleep, works identically on both backends; (b) poll an anyio `Event` in a loop — rejected, needs a `sleep(0)`/checkpoint loop and is less crisp. The stub *also* exposes its own `threading.Event entered` (Pattern 1) for purely-sync self-tests, but the loop-facing signal MUST be the anyio `Event` set through `from_thread`. `[VERIFIED: anyio threads docs — from_thread.run_sync from an anyio worker thread needs no token]`

### Pattern 4: AST source-scan guard returning a findings list (D-05)
**What:** A pure-stdlib `ast.NodeVisitor` that walks every `.py` file under a configurable path and returns a `list[Finding]` for the two banned patterns.
**When to use:** Backs EDGE-25/27/28 in later phases (the meta-guards). Phase 23 ships ONLY the callable + its self-tests against synthetic sources.
**Example:**
```python
# guard.py
from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Finding:
    path: str
    lineno: int
    rule: str          # "banned-asyncio-import" | "to_thread-without-limiter"
    message: str

class _GuardVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "asyncio" or alias.name.startswith("asyncio."):
                self.findings.append(Finding(self.path, node.lineno,
                    "banned-asyncio-import", f"`import {alias.name}` is banned in _async/"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "asyncio" or (node.module or "").startswith("asyncio."):
            self.findings.append(Finding(self.path, node.lineno,
                "banned-asyncio-import", "`from asyncio import …` is banned in _async/"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_to_thread_run_sync(node.func):
            has_limiter = any(kw.arg == "limiter" for kw in node.keywords)
            if not has_limiter:
                self.findings.append(Finding(self.path, node.lineno,
                    "to_thread-without-limiter",
                    "`to_thread.run_sync(...)` must pass an explicit `limiter=`"))
        self.generic_visit(node)

    @staticmethod
    def _is_to_thread_run_sync(func: ast.expr) -> bool:
        # Matches `to_thread.run_sync(...)` and `anyio.to_thread.run_sync(...)`
        # regardless of how `to_thread` was imported, by checking the attribute chain tail.
        if isinstance(func, ast.Attribute) and func.attr == "run_sync":
            value = func.value
            return isinstance(value, ast.Attribute) and value.attr == "to_thread" \
                or isinstance(value, ast.Name) and value.id == "to_thread"
        return False

def scan_async_package(root: str | Path) -> list[Finding]:
    """Scan every .py under `root`; return findings. No-op if `root` is absent/empty."""
    root = Path(root)
    if not root.exists():
        return []                                   # D-05: graceful no-op (path doesn't exist yet)
    findings: list[Finding] = []
    for py in sorted(root.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        v = _GuardVisitor(str(py))
        v.visit(tree)
        findings.extend(v.findings)
    return findings
```
> **Robustness notes:** matching on the **attribute-chain tail** (`.run_sync` whose value's `.attr`/`.id` is `to_thread`) catches both `anyio.to_thread.run_sync(...)` and `from anyio import to_thread; to_thread.run_sync(...)`. It will NOT catch a fully-aliased `from anyio.to_thread import run_sync as rs; rs(...)` — flag this as an accepted limitation (a self-test should document it). The `import asyncio` ban does not need alias tracking because the requirement is a literal `import asyncio` ban (CORE-03). For self-tests, feed **synthetic source strings** via a `tmp_path` fixture writing `.py` files, plus a direct `ast.parse` path — do NOT scan the real (empty) `_async/`.

### Anti-Patterns to Avoid
- **Putting anyio inside the stub.** Violates D-03 and couples the framework-neutral fake to one backend. The bridge belongs in the offload glue (Pattern 3).
- **Real sleeps to wait for "worker started."** Flakes under CI (Pitfall 12 in ASYNC-EDGE-CASES). Use the `entered` anyio `Event` (Pattern 3).
- **`from_thread.run_sync` with an explicit `token` when on an anyio worker thread.** Unnecessary and error-prone; only needed for non-anyio threads.
- **Trying to swap the trio clock in-body.** Trio's clock is fixed at run start; injection MUST be at the runner via `anyio_backend` options.
- **`import-linter` / ruff for D-05.** Wrong contract shape (see Alternatives). Hand-roll the `ast` visitor.
- **Defining `anyio_backend` in the top-level `tests/conftest.py`.** Would attempt to parametrize/await the existing sync suite. Scope it to the async harness (a nested conftest or the async test module).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| asyncio/trio backend parametrization | A custom event-loop runner or `asyncio.run` wrapper | anyio's bundled pytest plugin (`@pytest.mark.anyio` + `anyio_backend` fixture) | Ships with anyio; handles fixtures, both backends, cancellation semantics |
| asyncio virtual time | A monkeypatch of `time.monotonic`/`loop.time` | `aiotools.VirtualClock().patch_loop()` | Correctly patches the running loop's timer + sleep; battle-tested |
| trio virtual time | A custom `trio.abc.Clock` | `trio.testing.MockClock(autojump_threshold=0)` | Canonical; autojump handles "all tasks blocked → advance" precisely |
| worker→loop signalling | A `threading.Event` polled from the loop with `sleep(0)` | `anyio.from_thread.run_sync(event.set)` + `await anyio.Event().wait()` | Deterministic, no poll, no sleep, backend-neutral |

**Key insight:** Every timing/scheduling primitive this harness needs already exists in anyio/trio/aiotools. The ONLY thing to hand-roll is the `BlockingStubCursor` (a domain-specific fake) and the `ast` guard (a domain-specific rule) — both are thin and have no off-the-shelf equivalent that fits the contract.

## Common Pitfalls

### Pitfall 1: Assuming anyio's trio backend silently drops the `clock` option
**What goes wrong:** Planner assumes `("trio", {"clock": ...})` is ignored (because anyio docs only *document* `restrict_keyboard_interrupt_to_checkpoints` for trio) and falls back to an inferior mechanism.
**Why it happens:** The anyio testing docs list only two backend options and do not mention `clock`.
**How to avoid:** The plugin forwards the WHOLE options dict via `**options` to `start_guest_run`, which accepts `clock=`. VERIFIED in source. The plan should include one self-test that proves a trio `fail_after` fires on virtual time (inside a real-time watchdog) so the assumption is locked by a test, not by docs.
**Warning signs:** A trio timeout test hangs or consumes real wall-clock → the clock did not reach the loop.

### Pitfall 2: The `entered` race (triggering cancel before the worker blocks)
**What goes wrong:** Test calls `scope.cancel()` or sets the virtual clock before the worker thread is actually inside `execute`; cancel lands at the offload boundary (EDGE-01 territory) instead of during the block (EDGE-02), or the test is non-deterministic.
**Why it happens:** `tg.start_soon(...)` schedules the worker but does not wait for it to enter the C call.
**How to avoid:** Always `await entered.wait()` (Pattern 3) before triggering. The bridge sets the anyio `Event` from the worker *before* `event.wait()`.
**Warning signs:** Intermittent `execute_call_count == 0` when you expected `== 1`.

### Pitfall 3: AST guard misses aliased imports / `to_thread` re-exports
**What goes wrong:** `from anyio.to_thread import run_sync as rs; rs(...)` slips past the visitor.
**Why it happens:** The visitor matches the `to_thread.run_sync` attribute chain, not a fully-aliased bare name.
**How to avoid:** Document the limitation in a self-test; the real `_async/` code (Phase 24) will use the canonical `anyio.to_thread.run_sync(...)` form, which IS caught. CORE-01 in Phase 24 constrains the call style, so the guard's coverage matches actual usage.
**Warning signs:** A guard self-test for the aliased form fails — expected; assert it as a known gap, not a bug.

### Pitfall 4: `anyio_backend` fixture leaking into the sync suite
**What goes wrong:** A top-level `anyio_backend` fixture or `anyio_mode = "auto"` in pytest config makes the existing sync tests try to run under the plugin.
**Why it happens:** Over-broad placement of the fixture / config.
**How to avoid:** Keep the `anyio_backend` fixture inside the async harness scope (nested conftest or the async test module); do NOT set `anyio_mode = "auto"` globally. This also protects future PKG-04 (sync suite must pass with anyio uninstalled).
**Warning signs:** Existing `tests/test_configs.py` etc. start erroring about missing `anyio_backend` or async collection.

### Pitfall 5: pytest 9 already installed (floor is `>=8.0.0`)
**What goes wrong:** Plan assumes pytest 8 behaviour; the installed runner is 9.0.3.
**Why it happens:** pyproject floor is `>=8.0.0` but the resolved env has 9.0.3.
**How to avoid:** anyio 4.14.1 supports pytest 8 and 9; no action needed, but verify the anyio plugin loads under pytest 9 (it does — anyio 4.14.x targets current pytest). Note in the plan that the dev env is pytest 9 / Python 3.14.
**Warning signs:** Plugin-registration or deprecation warnings at collection under pytest 9.

## Code Examples

(See Patterns 1–4 above — each is a complete, paste-adaptable example sourced from the cited docs/source.)

### Harness self-test skeleton (D-06) — both legs, no real sleeps
```python
# test_async_harness.py
import anyio
import pytest
from tests._async_harness.stubs import BlockingStubCursor
from tests._async_harness.gating import run_blocking

@pytest.mark.anyio
async def test_block_then_release(anyio_backend_name):
    stub = BlockingStubCursor()
    limiter = anyio.CapacityLimiter(1)
    entered = anyio.Event()
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_blocking, stub.execute, "SELECT 1",
                      entered=entered, limiter=limiter)
        await entered.wait()                 # deterministic
        assert stub.execute_call_count == 1
        stub.release()                       # unblock the worker — no sleep
    assert stub.observed_cancel is False

@pytest.mark.anyio
async def test_block_then_adbc_cancel(anyio_backend_name):
    stub = BlockingStubCursor()
    limiter = anyio.CapacityLimiter(1)
    entered = anyio.Event()
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_blocking, stub.execute, "SELECT 1",
                      entered=entered, limiter=limiter)
        await entered.wait()
        stub.adbc_cancel()                   # releases + flips observed_cancel
    assert stub.observed_cancel is True
    assert stub.adbc_cancel_call_count == 1
```
> Both run under asyncio AND trio via the `anyio_backend` fixture (D-06). Worker thread-id capture (`stub.execute_thread_ids`) lets a self-test assert it ran off-loop, pre-proving EDGE-25's mechanism.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `cancellable=` kwarg on `to_thread.run_sync` | `abandon_on_cancel=` (cancellable is a deprecated alias) | anyio 4.1+ | The guard/style in `_async/` must use `abandon_on_cancel=`; Phase 24 concern, but harness self-tests should model the current name |
| asyncio-only fake clocks (`asynctest`, manual loop patching) | `aiotools.VirtualClock` (asyncio) + `trio.testing.MockClock` (trio) | aiotools v1.0 (virtual clock) | Two-leg façade is the modern path; no single cross-backend fake clock exists |
| `@pytest.mark.asyncio` (asyncio-only) | `@pytest.mark.anyio` + `anyio_backend` param | anyio pytest plugin | Backend neutrality is a hard requirement (EDGE-27); asyncio-only markers are banned in the async suite |

**Deprecated/outdated:**
- `@pytest.mark.asyncio` in the async test package — banned by EDGE-27 (Phase 27 meta-guard). Phase 23 must not use it.
- `import asyncio` anywhere the guard scans — banned by CORE-03/EDGE-25.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | aiotools `VirtualClock().patch_loop()` correctly drives anyio's `fail_after`/`move_on_after` deadlines on the asyncio leg (anyio asyncio timeouts key off the patched `loop.time()`) | Pattern 2 | If anyio's asyncio backend reads a clock source aiotools does not patch, the asyncio timeout leg would not fast-forward. MITIGATION: a self-test must assert an asyncio `fail_after(3600)` fires instantly under `patch_loop()`. CITED (not source-verified for the anyio-deadline interaction specifically). |
| A2 | `aiotools>=2.2` is the right floor and `VirtualClock` API (`patch_loop()`, `virtual_time()`) is stable at that floor | Standard Stack | Low risk; API documented since v1.0. Verify the installed version exposes `patch_loop()` in the install task. |

> **A1 is the only residual risk** and is explicitly converted into a Phase 23 self-test (see Validation Architecture / Pitfall 1). Everything else (trio clock injection, the `entered` bridge, the AST guard, dep legitimacy) is VERIFIED or stdlib.

## Open Questions

1. **Does anyio's asyncio backend's `fail_after` deadline honour `aiotools.VirtualClock().patch_loop()`?**
   - What we know: aiotools patches the running loop so `loop.time()` and sleeps advance virtually; anyio's asyncio backend uses the standard running loop and computes deadlines from `loop.time()`.
   - What's unclear: whether anyio caches or reads time through a path aiotools does not patch.
   - Recommendation: make this a **Phase 23 self-test** (assert an asyncio-leg `fail_after(3600)` fires instantly inside a real-time watchdog). If it fails, fall back to event-gating for the asyncio timeout cases (event-gating is already primary per D-02, so this is a contained risk, not a blocker).

2. **Should `anyio_backend` be function-scoped or session-scoped given the shared MockClock?**
   - What we know: a param-driven function-scoped fixture constructs a fresh MockClock per test (recommended).
   - Recommendation: function-scoped (the Pattern 2 example). Document why (clock-state isolation).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `anyio` | parametrization, offload glue, virtual-clock trio injection | ✗ (not in venv) | — (target `>=4.13`) | none — install in dev group (plan task 1) |
| `trio` | trio backend + MockClock | ✗ (not in venv) | — (target `>=0.31`) | none — install in dev group |
| `aiotools` | asyncio virtual clock | ✗ (not in venv) | — (target `>=2.2`) | event-gating only (degrades EDGE-31/32 precision; D-02 keeps gating primary) |
| `pytest` | runner | ✓ | 9.0.3 | — |
| Python | runtime | ✓ | 3.14.2 | — |
| stdlib `ast`, `threading` | guard, stubs | ✓ | 3.14 stdlib | — |

**Missing dependencies with no fallback:** `anyio`, `trio` — must be installed in the dev group as the plan's first task (D-07).
**Missing dependencies with fallback:** `aiotools` — if its asyncio virtual-clock interaction with anyio fails (A1), event-gating covers the cancel paths; only EDGE-31/32 timeout-precision (P2, later phases) would be affected.

## Validation Architecture

> nyquist_validation is enabled (`.planning/config.json` workflow.nyquist_validation = true). The harness's OWN self-tests are the validation surface for this phase.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 + anyio pytest plugin (`@pytest.mark.anyio`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (existing) |
| Quick run command | `.venv/bin/pytest tests/_async_harness/ tests/test_async_guard.py -q` |
| Full suite command | `.venv/bin/pytest -q` |

> Use `.venv/bin/pytest` (not `uv run pytest`) under the sandbox per project MEMORY (uv-sandbox-workarounds).
>
> **Final layout note (supersedes the single-file paths in the rows below):** the plan-checker moved the
> anyio dual-backend self-tests into `tests/_async_harness/test_harness.py` (so they sit at/below the
> `tests/_async_harness/conftest.py` that defines `anyio_backend`), and the sync guard self-tests live in
> `tests/test_async_guard.py`. The `tests/test_async_harness.py` path used in the table rows and Wave-0
> list below is the early single-file sketch — the `23-*-PLAN.md` files carry the authoritative paths.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-05 (stub) | block→release: `execute_call_count==1`, `observed_cancel False` under both backends | unit (async, dual-backend) | `.venv/bin/pytest tests/test_async_harness.py::test_block_then_release -x` | ❌ Wave 0 |
| TEST-05 (stub) | block→`adbc_cancel`→unblock: `observed_cancel True`, `adbc_cancel_call_count==1` | unit (async, dual-backend) | `.venv/bin/pytest tests/test_async_harness.py::test_block_then_adbc_cancel -x` | ❌ Wave 0 |
| TEST-05 (stub) | worker ran off-loop: `execute_thread_ids[0] != loop_thread_id` | unit (async, dual-backend) | `.venv/bin/pytest tests/test_async_harness.py::test_offloaded_thread_id -x` | ❌ Wave 0 |
| TEST-05 (stub) | `max_concurrent_in_execute` tracks concurrent entries under a flood | unit (async, dual-backend) | `.venv/bin/pytest tests/test_async_harness.py::test_max_concurrent -x` | ❌ Wave 0 |
| TEST-05 (clock) | trio leg `fail_after` fires on virtual time (inside real-time watchdog) | unit (async, trio) | `.venv/bin/pytest tests/test_async_harness.py::test_trio_virtual_clock -x` | ❌ Wave 0 |
| TEST-05 (clock) | asyncio leg `fail_after` fires under `patch_loop()` (resolves A1) | unit (async, asyncio) | `.venv/bin/pytest tests/test_async_harness.py::test_asyncio_virtual_clock -x` | ❌ Wave 0 |
| TEST-05 (guard) | `import asyncio` flagged in synthetic source | unit (sync) | `.venv/bin/pytest tests/test_async_harness.py::test_guard_bans_asyncio -x` | ❌ Wave 0 |
| TEST-05 (guard) | bare `to_thread.run_sync` without `limiter=` flagged; with `limiter=` clean | unit (sync) | `.venv/bin/pytest tests/test_async_harness.py::test_guard_to_thread_limiter -x` | ❌ Wave 0 |
| TEST-05 (guard) | absent dir → empty findings (no-op) | unit (sync) | `.venv/bin/pytest tests/test_async_harness.py::test_guard_noop_absent_dir -x` | ❌ Wave 0 |
| TEST-05 (parametrization) | every async self-test runs under asyncio AND trio | unit (collection) | `.venv/bin/pytest tests/test_async_harness.py --collect-only -q` (assert both ids) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/test_async_harness.py -q`
- **Per wave merge:** `.venv/bin/pytest -q` (full suite — must stay green; the existing sync suite must not regress)
- **Phase gate:** Full suite green + `.venv/bin/mkdocs build --strict` (CLAUDE.md docs gate, phase ≥ 7) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/_async_harness/__init__.py` + `stubs.py`, `clock.py`, `gating.py`, `guard.py` — the harness modules
- [ ] `tests/_async_harness/conftest.py` (or async test module) — the `anyio_backend` fixture (function-scoped, params `["asyncio", ("trio", {clock: MockClock(autojump_threshold=0)})]`)
- [ ] `tests/test_async_harness.py` — all self-tests above
- [ ] Dev-group install: `uv add --dev anyio trio aiotools`
- [ ] basedpyright-strict clean for the new harness (config includes `tests`); note `reportPrivateUsage = false` already set

## Project Constraints (from CLAUDE.md)

- **Docs gate applies (phase ≥ 7):** include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in the plan's `<execution_context>`. Phase 23 is a test-harness phase, but the docs gate still applies: new public-ish harness symbols need Google-style docstrings (Args/Returns/Raises), key entry points (`scan_async_package`, `virtual_clock`, `BlockingStubCursor`) get an `Example:` block, and `.venv/bin/mkdocs build --strict` must pass.
  - Note: harness lives under `tests/`, not `src/`, so it is NOT in the mkdocstrings API reference (`gen_ref_pages.py` scans `src/`). The `--strict` build must still pass (it will, since nothing references the harness from docs). The docstring requirement is about code quality, not published API.
- **Docstrings:** Google-style (Args/Returns/Raises); **Markdown** in docstrings, NOT RST (no `:func:` roles — use backticks). `Example:` (singular) = admonition with fenced ` ```python ` blocks; `Examples:` (plural) = `>>>` doctests.
- **Humanizer pass** on all new/substantially-rewritten prose (any docstring prose, any guide text).
- **basedpyright strict** over `src` AND `tests` (`reportPrivateUsage = false`). All new harness code must be strict-clean and fully typed.
- **ruff** select includes `D` (pydocstyle) — but `D1` ignored (docstrings not required everywhere); line-length 100.
- **Sandbox tooling:** prefer `.venv/bin/<tool>` over `uv run <tool>` for pytest/mkdocs/basedpyright to avoid sandbox permission prompts (MEMORY: uv-sandbox-workarounds).
- **STATE.md can be stale** — trust git tags + pyproject + ROADMAP over STATE.md frontmatter (MEMORY).

## Project Skills

- **`adbc-poolhouse-docs-author`** (`.claude/skills/adbc-poolhouse-docs-author/SKILL.md`): audience = async Python devs; voice = HTTPX/SQLAlchemy-like; Google-style docstrings; humanizer pass after any prose. Include in plan `<execution_context>` per CLAUDE.md (phase ≥ 7). Do NOT hand-write `docs/src/reference/` (auto-generated from `src/`).

## Sources

### Primary (HIGH confidence)
- anyio master source `src/anyio/_backends/_trio.py` — `TrioBackend.run` (`trio.run(func, *args, **options)`) and the trio `TestRunner.__init__(**options)` + `_call_in_runner_task` (`trio.lowlevel.start_guest_run(..., **self._options)`) — **confirms `clock` option forwards to the trio loop**. https://raw.githubusercontent.com/agronholm/anyio/master/src/anyio/_backends/_trio.py
- anyio master source `src/anyio/pytest_plugin.py` — `extract_backend_and_options`, `anyio_backend_name`/`anyio_backend_options` fixtures, `create_test_runner(backend_options)`. https://raw.githubusercontent.com/agronholm/anyio/master/src/anyio/pytest_plugin.py
- trio testing docs — `trio.testing.MockClock(rate=0.0, autojump_threshold=inf)`, `jump()`; `trio.run(..., clock=...)` accepts a MockClock. https://trio.readthedocs.io/en/stable/reference-testing.html , https://trio.readthedocs.io/en/stable/reference-core.html
- anyio threads docs — `to_thread.run_sync(func, *args, abandon_on_cancel=False, limiter=None)`; `from_thread.run_sync(event.set)` needs no token from an anyio worker thread. https://anyio.readthedocs.io/en/stable/threads.html
- anyio testing docs — `anyio_backend` fixture, `("backend", {options})` tuple form, plugin enabling. https://anyio.readthedocs.io/en/stable/testing.html
- PyPI JSON (2026-06-27): anyio 4.14.1, trio 0.33.0, aiotools 2.2.3 (versions, dates, Python 3.14 classifiers).
- Project source read directly: `_pool_factory.py` (`_release_arrow_allocators` reset listener, `pool_size=5/max_overflow=3`, `checkedout()` semantics), `tests/conftest.py`, `tests/test_benchmarks_harness.py` (self-test precedent), `pyproject.toml` (deps, pytest config, basedpyright strict, ruff).

### Secondary (MEDIUM confidence)
- aiotools docs — `VirtualClock().patch_loop()` (sync CM) + `virtual_time()`; asyncio loop-patching example. https://aiotools.readthedocs.io/en/latest/aiotools.timer.html (the anyio-deadline interaction A1 is inferred, not directly documented).

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — three deps verified on PyPI with dates/versions/Python 3.14 classifiers 2026-06-27.
- Architecture (trio clock injection): HIGH — verified in anyio master source, not docs alone.
- Architecture (asyncio clock A1): MEDIUM — aiotools mechanism documented; anyio-deadline interaction converted to a Phase 23 self-test.
- `entered` bridge: HIGH — anyio `from_thread.run_sync` from an anyio worker thread is documented to need no token.
- AST guard: HIGH — stdlib `ast` mechanics; one documented alias-limitation accepted.
- Pitfalls: HIGH — grounded in ASYNC-EDGE-CASES.md + verified semantics.

**Research date:** 2026-06-27
**Valid until:** 2026-07-27 (30 days — stable libraries; re-check anyio/trio if a major version ships, as the trio-clock forwarding is an internal detail that could theoretically change).
