# Phase 23: Test Harness Foundation - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 8 (7 new, 1 modified)
**Analogs found:** 8 / 8 (all role/style analogs; the async *mechanisms* are net-new — see "No Behavioural Analog")

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/_async_harness/__init__.py` | package-init | — | `benchmarks/__init__.py` | exact |
| `tests/_async_harness/stubs.py` | utility (test fake) | event-driven (blocking) | `benchmarks/_harness.py` (`concurrent_wall`, pure-`threading`) | role + data-flow |
| `tests/_async_harness/clock.py` | utility (façade) | transform (dispatch) | `benchmarks/_harness.py` (pure-fn module style) | style-only (mechanism net-new) |
| `tests/_async_harness/gating.py` | utility (offload glue) | event-driven (worker↔loop) | `benchmarks/_harness.py` (`concurrent_wall` thread-gating) | partial (mechanism net-new) |
| `tests/_async_harness/guard.py` | utility (AST scanner) | batch / file-I/O | `benchmarks/_harness.py` (pure stdlib, ADBC-free module) | style-only (mechanism net-new) |
| `tests/_async_harness/conftest.py` | config (fixture) | request-response (pytest) | `tests/integration/conftest.py` (nested, function-scoped) + `tests/conftest.py` | role-match |
| `tests/test_async_harness.py` | test | event-driven / batch | `tests/test_benchmarks_harness.py` (self-test of a harness) | exact |
| `pyproject.toml` (modify) | config (deps) | — | `pyproject.toml` `[dependency-groups] dev` | exact (in-file) |

> Layout follows RESEARCH §"Recommended Project Structure" (Claude's-discretion D-05/D-06). `_async_harness/` underscore prefix keeps it out of default test collection; only `tests/test_async_harness.py` is collected.

## Pattern Assignments

### `tests/_async_harness/__init__.py` (package-init)

**Analog:** `benchmarks/__init__.py` (one-line module docstring, no exports).

**Pattern** (`benchmarks/__init__.py` line 1):
```python
"""GIL-release measurement spike (SPIKE-01/02): kept benchmarks outside the wheel."""
```
Copy the shape: a single-line docstring stating purpose + the "test-only, never shipped" framing (mirrors the harness's CONTEXT boundary: never in `src/`). `tests/__init__.py` is empty (0 bytes) — the existing precedent allows either; prefer a one-line docstring per the benchmarks analog.

---

### `tests/_async_harness/stubs.py` (utility, pure-threading fake)

**Analog:** `benchmarks/_harness.py` — the project's only pure-`threading`, ADBC-free, anyio-free harness module. The stub follows the SAME constraints (RESEARCH Pattern 1 / D-03).

**Module-docstring + import pattern** (`benchmarks/_harness.py` lines 1-30) — copy the "deliberately X-free" framing and the `from __future__ import annotations` + stdlib-only imports:
```python
"""
Pure timing/arithmetic core for the GIL-release spike (SPIKE-01, SPIKE-02).

This module is deliberately ADBC-free: it imports no `adbc_poolhouse` ...
... it never uses anyio or any async machinery.
"""

from __future__ import annotations

import statistics
import threading
import time
```
For `stubs.py`: same header style, but state "deliberately anyio-free / pure `threading`" (D-03 — sync-only is what makes it framework-neutral). Imports are `from __future__ import annotations` + `import threading` only. **NO `import anyio`** (anti-pattern, RESEARCH §Anti-Patterns).

**Lock-guarded counter pattern** — `benchmarks/_harness.py` uses `threading.Barrier`; the stub's `max_concurrent_in_execute` uses the `threading.Lock`-guarded increment/decrement from RESEARCH Pattern 1 lines 208-218:
```python
def _block(self) -> None:
    with self._lock:
        self._in_execute += 1
        self.max_concurrent_in_execute = max(self.max_concurrent_in_execute, self._in_execute)
    try:
        self.entered.set()
        self._event.wait()              # blocks FOREVER until released
    finally:
        with self._lock:
            self._in_execute -= 1
```

**Core stub contract (HARD CONTRACT for Phases 24/25/27):** copy the full class skeleton from RESEARCH Pattern 1 (lines 191-247). Attribute names are locked by D-04: `entered`, `observed_cancel`, `execute_call_count`, `fetch_call_count`, `adbc_cancel_call_count`, `close_call_count`, `execute_thread_ids`, `max_concurrent_in_execute`. dbapi surface: `execute`, `fetch_arrow_table`, `close`, `adbc_cancel`, plus test-only `release()`. `adbc_cancel()` flips `observed_cancel` AND `self._event.set()`.

**Docstring style:** Google-style (Args/Returns/Raises), Markdown not RST, per `benchmarks/_harness.py` lines 33-46 (the `median` docstring is the canonical template). `Example:` (singular) blocks for the public entry point `BlockingStubCursor` (CLAUDE.md docs gate, phase ≥ 7).

`BlockingStubConnection` mirrors the same skeleton over the connection surface (D-03).

---

### `tests/_async_harness/clock.py` (utility, backend-dispatch façade)

**Analog (style):** `benchmarks/_harness.py` (pure-function stdlib module). **Mechanism is net-new** — copy structure/docstrings, NOT behaviour.

**Module/import pattern:** `from __future__ import annotations` header + module docstring (benchmarks analog). Imports per RESEARCH Pattern 2 lines 271-273:
```python
import contextlib
import aiotools
```

**Core façade** — copy verbatim from RESEARCH Pattern 2 (lines 274-282); dispatch on `anyio_backend_name` (D-01):
```python
@contextlib.contextmanager
def virtual_clock(anyio_backend_name: str):
    if anyio_backend_name == "trio":
        yield                                   # clock injected at the runner
    else:                                       # asyncio
        with aiotools.VirtualClock().patch_loop():
            yield
```
**Docs gate:** `virtual_clock` is a key entry point → needs an `Example:` block (RESEARCH §Project Constraints). Document the trio/asyncio asymmetry in the docstring (D-01).

---

### `tests/_async_harness/gating.py` (utility, worker↔loop offload glue)

**Analog (data-flow):** `benchmarks/_harness.py` `concurrent_wall` (lines 108-146) — the thread-gating precedent (`threading.Barrier` to release workers together). `gating.py` is the anyio analog of that gating, but on an anyio worker thread. **The `entered`-bridge mechanism is net-new** (RESEARCH Pattern 3, PINNED).

**Import pattern** (RESEARCH Pattern 3 lines 302-303):
```python
import anyio
from anyio import to_thread
```

**Core offload-glue pattern** — copy verbatim from RESEARCH Pattern 3 (lines 305-311). This is where anyio lives (NOT the stub):
```python
async def run_blocking(stub_call, *args, entered: anyio.Event, limiter):
    """Harness offload glue — models the future Phase 24 offload + bridges `entered`."""
    def _worker():
        anyio.from_thread.run_sync(entered.set)   # signal loop BEFORE blocking (no token needed)
        return stub_call(*args)
    return await to_thread.run_sync(_worker, limiter=limiter)
```
**Critical:** `from_thread.run_sync` from an anyio worker thread needs NO token (RESEARCH Pattern 3 / Anti-Patterns). Use `limiter=` explicitly on `to_thread.run_sync` — this is also exactly what the guard (`guard.py`) enforces, so the harness must model the compliant call shape.

---

### `tests/_async_harness/guard.py` (utility, AST source-scan, batch/file-I/O)

**Analog (style):** `benchmarks/_harness.py` (pure stdlib, ADBC-free, no third-party deps). **Mechanism net-new** — RESEARCH Pattern 4 is the authoritative source.

**Import pattern** (RESEARCH Pattern 4 lines 329-332):
```python
from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path
```

**Findings dataclass + visitor + entry point** — copy verbatim from RESEARCH Pattern 4 (lines 334-389). The `Finding` frozen dataclass, `_GuardVisitor(ast.NodeVisitor)` with `visit_Import`/`visit_ImportFrom`/`visit_Call`, and the public `scan_async_package(root) -> list[Finding]`.

**Graceful no-op pattern** (RESEARCH Pattern 4 lines 378-389, D-05) — the path-absent guard clause is load-bearing (`_async/` does not exist until Phase 24):
```python
def scan_async_package(root: str | Path) -> list[Finding]:
    root = Path(root)
    if not root.exists():
        return []                               # D-05: graceful no-op
    findings: list[Finding] = []
    for py in sorted(root.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        v = _GuardVisitor(str(py))
        v.visit(tree)
        findings.extend(v.findings)
    return findings
```
**Path-handling analog:** `tests/integration/conftest.py` lines 19-24 show the project's `Path(__file__).parent... / ".env"` + `.exists()`-guard idiom — mirror that `exists()`-then-act style.
**Docs gate:** `scan_async_package` is a key entry point → `Example:` block. Document the accepted alias-limitation (RESEARCH Pattern 4 line 391 / Pitfall 3) in the docstring.

---

### `tests/_async_harness/conftest.py` (config, pytest fixture)

**Analog:** `tests/integration/conftest.py` — the project's precedent for a **nested, function-scoped** conftest that scopes fixtures to a subtree (here: cloud tests; there: the async harness). Combined with `tests/conftest.py` for the fixture-docstring style.

**Why nested, not top-level:** RESEARCH Pitfall 4 — defining `anyio_backend` in the top-level `tests/conftest.py` would force the existing sync suite (`test_configs.py`, etc.) under the anyio plugin. Scope it here. This mirrors how `tests/integration/conftest.py` keeps cloud-pool fixtures out of the root suite.

**Fixture pattern** (function-scoped, RESEARCH Pattern 2 lines 258-267; scoping rationale = Open Question 2 / Pattern 2 caveat lines 293-294 — fresh `MockClock` per test):
```python
import pytest
import trio.testing

@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: pytest.FixtureRequest) -> object:
    if request.param == "trio":
        return ("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})
    return "asyncio"
```
**Fixture-docstring style:** copy `tests/conftest.py` lines 36-46 (the `_clear_warehouse_env_vars` autouse fixture) — module docstring explaining WHY, plus per-fixture Google-style docstring. Note `tests/conftest.py` uses `# pyright: ignore[reportUnusedFunction]` on the autouse fixture — the `anyio_backend` fixture is referenced by name (not unused), so that suppression is not needed here.

---

### `tests/test_async_harness.py` (test, self-test of the harness)

**Analog:** `tests/test_benchmarks_harness.py` — the project's EXACT precedent for unit-testing a test-harness's internals on synthetic inputs (no DB, no driver, no wall-clock). This is the closest analog in the whole repo.

**Module-docstring pattern** (`tests/test_benchmarks_harness.py` lines 1-7) — copy the "exercises only X on synthetic inputs, no real Y" framing:
```python
"""
Unit tests for the GIL-release benchmark harness arithmetic (SPIKE-01, SPIKE-02).

Exercises only the pure ... functions ... on synthetic timings -- no threads,
no connection pool, no ADBC driver, and no wall-clock assertion ...
"""
```
For the async harness: state "no real sleeps, no DB, dual-backend via `anyio_backend`" (D-06).

**Class/method + Google-docstring style** (`tests/test_benchmarks_harness.py` lines 16-33, mirrored in `tests/test_translators.py` lines 28-55): one-line docstring per test method describing the asserted behaviour, grouped under a `Test...` class. The project favours `class TestX:` grouping with descriptive one-line method docstrings.

**Async self-test skeleton** — copy verbatim from RESEARCH §"Harness self-test skeleton (D-06)" (lines 449-481): `@pytest.mark.anyio`, `anyio_backend_name` param injection, `anyio.CapacityLimiter(1)`, `anyio.Event()`, `await entered.wait()` before triggering (Pitfall 2), then `stub.release()` or `stub.adbc_cancel()`. Imports:
```python
import anyio
import pytest
from tests._async_harness.stubs import BlockingStubCursor
from tests._async_harness.gating import run_blocking
```
**Full test list** is enumerated in RESEARCH §"Phase Requirements → Test Map" (lines 545-556): block→release, block→adbc_cancel, offloaded-thread-id (EDGE-25 mechanism), max_concurrent, trio virtual-clock (inside a real-time watchdog), asyncio virtual-clock (resolves A1), guard-bans-asyncio, guard-to_thread-limiter, guard-noop-absent-dir, and a `--collect-only` dual-id parametrization check.

---

### `pyproject.toml` (modify — dev dependency-group)

**Analog:** the existing `[dependency-groups] dev` block (`pyproject.toml` lines 44-56).

**Pattern:** append `anyio`, `trio`, `aiotools` to the `dev` list (D-07 — dev/test-only; must NOT touch `[project.dependencies]` or `[project.optional-dependencies]`, which would leak into the wheel). Floors from RESEARCH §Standard Stack:
```toml
dev = [
    "adbc-poolhouse[all]",
    "basedpyright>=1.38.0",
    # ... existing ...
    "anyio>=4.13",
    "trio>=0.31",
    "aiotools>=2.2",
]
```
Install via `uv add --dev anyio trio aiotools` (RESEARCH line 90). **Do not** add `anyio_mode = "auto"` to `[tool.pytest.ini_options]` (Pitfall 4) — keep the plugin opt-in via `@pytest.mark.anyio`. The existing `[tool.basedpyright] include = ["src", "tests"]` (line 80) means new harness code must be strict-clean and fully typed.

---

## Shared Patterns

### Module header / "deliberately X-free" framing
**Source:** `benchmarks/_harness.py` lines 1-24
**Apply to:** all `tests/_async_harness/*.py`
Every harness module opens with `from __future__ import annotations` and a docstring stating its dependency boundary (stubs = "pure threading, no anyio"; guard = "pure stdlib ast, no third-party"). This is the established project voice for test/bench infrastructure.

### Google-style docstrings (Markdown, not RST)
**Source:** `benchmarks/_harness.py` lines 33-65 (the `median`/`speedup` docstrings)
**Apply to:** all public harness symbols (`BlockingStubCursor`, `virtual_clock`, `run_blocking`, `scan_async_package`, `Finding`)
Args/Returns/Raises sections; backticks for code refs (`` `to_thread.run_sync` ``), NOT RST `:func:` roles (MEMORY). Key entry points get `Example:` (singular = admonition with ` ```python ` fences). Required by CLAUDE.md docs gate (phase ≥ 7); `.venv/bin/mkdocs build --strict` must pass.

### Function-scoped, nested-conftest fixture scoping
**Source:** `tests/integration/conftest.py` (whole file — function-scoped pool fixtures in a subtree conftest)
**Apply to:** `tests/_async_harness/conftest.py`
Keep backend-parametrization fixtures out of the root `tests/conftest.py` so the sync suite stays plugin-free (Pitfall 4; protects future PKG-04).

### Harness self-test on synthetic inputs
**Source:** `tests/test_benchmarks_harness.py` (whole file)
**Apply to:** `tests/test_async_harness.py`
`class TestX:` grouping, one-line behaviour docstring per method, synthetic inputs only (no DB/driver/wall-clock). For the async legs: dual-backend via `anyio_backend`, no real sleeps (event-gating + virtual clock).

### Path-exists guard idiom
**Source:** `tests/integration/conftest.py` lines 19-24 (`Path(...) ... if _dotenv_path.exists() else {}`)
**Apply to:** `guard.py` `scan_async_package` no-op-on-absent-dir (D-05)

## No Behavioural Analog (mechanism is net-new — use RESEARCH patterns)

The repo has **zero** existing anyio/trio/async-test code (`grep` for `anyio`/`CapacityLimiter` across `src` + `tests` → none). The following have a **style** analog (`benchmarks/_harness.py`) but their async/AST *mechanics* must come from RESEARCH, not the codebase:

| File | Role | Data Flow | Net-new mechanism | Authoritative source |
|------|------|-----------|-------------------|----------------------|
| `tests/_async_harness/clock.py` | utility | transform | backend-dispatch virtual-clock façade (trio runner-injection vs aiotools in-body) | RESEARCH Pattern 2 (lines 250-294) |
| `tests/_async_harness/gating.py` | utility | event-driven | `entered` worker→loop bridge via `from_thread.run_sync` | RESEARCH Pattern 3 (lines 296-321) |
| `tests/_async_harness/guard.py` | utility | batch/file-I/O | `ast.NodeVisitor` source-scan returning findings list | RESEARCH Pattern 4 (lines 323-391) |
| `tests/_async_harness/conftest.py` | config | request-response | `anyio_backend` param with trio `clock=` injection | RESEARCH Pattern 2 (lines 258-267) |

> The `_async/` SOURCE package (`src/adbc_poolhouse/_async/`) does NOT exist yet (Phase 24 creates it). The guard scans it but must no-op on its absence (D-05). Self-tests run against synthetic source strings via `tmp_path`, never the real (empty) package.

## Metadata

**Analog search scope:** `tests/`, `tests/integration/`, `benchmarks/`, `src/adbc_poolhouse/`, `pyproject.toml`
**Files scanned:** `tests/conftest.py`, `tests/test_benchmarks_harness.py`, `tests/test_translators.py`, `tests/integration/conftest.py`, `benchmarks/_harness.py`, `benchmarks/__init__.py`, `pyproject.toml`; grep-confirmed absence of any anyio/CapacityLimiter usage
**Pattern extraction date:** 2026-06-27
