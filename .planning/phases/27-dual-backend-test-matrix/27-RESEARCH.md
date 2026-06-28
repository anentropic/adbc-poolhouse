# Phase 27: Dual-Backend Test Matrix - Research

**Researched:** 2026-06-28
**Domain:** Test-layer engineering — anyio dual-backend (asyncio/trio) parametrization, pytest-adbc-replay cassette fixtures, AST source-scan meta-guards, pyarrow allocator accounting, deterministic limiter-stress flooding
**Confidence:** HIGH (entirely grounded in directly-read in-repo source; every reusable asset, API, and landmine was read this session, not assumed)

## Summary

Phase 27 is a pure `tests/` phase that adds the last six requirements of the v1.4.0 async milestone (TEST-01..04, EDGE-27, EDGE-30). The async layer it exercises is already frozen (`src/adbc_poolhouse/_async/` — Phases 24–26); **no production code may change**. Almost everything this phase needs already exists in the repo and was read directly this session: the dual-backend `anyio_backend` fixture, the real-DuckDB `duckdb_async_pool`, the `BlockingStubConnection`/`BlockingStubCursor` gating fakes (with the load-bearing sticky-cancel latch), the `real_clock_watchdog` + `await_inside` helpers, the EDGE-12 running-max flood pattern, the EDGE-21 Arrow-lifetime pattern, the `scan_async_package` AST guard, and a *working* inline Snowflake cassette async leg (`test_async_lifecycle.py::TestSnowflakeCassetteLeg`). The work is therefore mostly **assembly and extension of proven primitives**, not new infrastructure.

The five concrete deliverables: (1) promote the existing inline Snowflake-cassette async pattern into a reusable `snowflake_async_pool` conftest fixture and parametrize the read-path surface ×{DuckDB, Snowflake}×{asyncio, trio}; (2) extend `tests/_async_harness/guard.py` with two new pure-AST scanner callables — one asserting test-package hygiene (no `import asyncio`, no `@pytest.mark.asyncio`, every async test anyio-parametrized) and one banning positive-duration `sleep(...)` literals while allowing `sleep(0)`; (3) an Arrow-stability test using `pyarrow.total_allocated_bytes()` deltas over N≥100 cycles plus a reset-event counter; (4) a stub-gated limiter flood reusing EDGE-12 with a `time.monotonic()` watchdog; (5) wire all of it into the existing dual-backend CI job while keeping it out of the `sync-no-anyio` job.

**Primary recommendation:** Build by extension, not invention. Reuse `real_clock_watchdog` (never `anyio.fail_after` for off-loop gating — the MockClock-autojump landmine), reuse the EDGE-12 `close()`-to-drain flood shape, promote the already-green Snowflake cassette leg verbatim into a fixture, and add the two meta-guards as new pure-stdlib functions alongside `scan_async_package`. The single biggest risk is the EDGE-30 scanner scope and `sleep(0)` allow-listing — get the AST literal check exactly right (allow `sleep(0)`, allow non-literal args, ban positive literals) or it will either false-positive on the existing `await_inside` checkpoints or false-negative real wall-clock sleeps.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Dual-backend (asyncio/trio) parametrization | Test fixtures (`tests/async/conftest.py`) | — | `anyio_backend` fixture already owns this; tests opt in via `@pytest.mark.anyio` |
| Backend matrix (DuckDB × Snowflake) | Test fixtures (cassette + real pool) | pytest-adbc-replay plugin | Read-path surface parametrized over two pool fixtures |
| Source-hygiene meta-guards (EDGE-27/30) | Harness AST guard (`tests/_async_harness/guard.py`) | meta-test asserting `== []` | Pure-stdlib AST scan, no anyio import, mirrors `scan_async_package` |
| Arrow memory accounting (TEST-03) | Test (`pyarrow.total_allocated_bytes`) | pool `reset` event listener | Process-level allocator counter is deterministic; reset-event count proves symmetric cleanup |
| Limiter-stress flood (TEST-04) | Test + stub fakes (`BlockingStub*`) | `real_clock_watchdog` thread | Stub-gated determinism + real-clock deadlock detection |
| Deadlock detection | Real-clock watchdog thread (`time.monotonic`) | — | Virtual `fail_after` autojumps under MockClock — banned for off-loop gating |
| CI matrix wiring | `.github/workflows/ci.yml` | — | New tests join `quality` job; excluded from `sync-no-anyio` job |

## Standard Stack

### Core (all already installed and locked — versions verified this session)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anyio` | 4.14.1 | asyncio/trio neutrality, `CapacityLimiter`, cancel scopes | The project's foundational async abstraction (PKG-01) `[VERIFIED: importlib.metadata]` |
| `trio` | 0.33.0 | trio backend + `trio.testing.MockClock` | Second backend leg + virtual clock injection `[VERIFIED: importlib.metadata]` |
| `pyarrow` | 24.0.0 | `total_allocated_bytes()` for TEST-03 | The Arrow allocator counter; delta behaviour verified below `[VERIFIED: importlib.metadata]` |
| `pytest-adbc-replay` | 1.0.0 | Snowflake cassette replay (TEST-02) | Already wired (`adbc_auto_patch`, `adbc_cassette_dir`); proven green on the async layer `[VERIFIED: importlib.metadata]` |
| `pytest` | >=8.0.0 | Test runner | Project standard `[VERIFIED: pyproject.toml]` |
| `aiotools` | >=2.2 | `VirtualClock().patch_loop()` for the asyncio virtual-clock leg | Used by `tests/_async_harness/clock.py` for deadline tests `[VERIFIED: pyproject.toml]` |

### Supporting (in-repo harness — read directly this session)
| Asset | Location | Purpose | When to Use |
|-------|----------|---------|-------------|
| `anyio_backend` fixture | `tests/async/conftest.py:46` | asyncio + trio param, trio leg gets `MockClock(autojump_threshold=0)` | Every async test gets the backend axis free `[VERIFIED: read]` |
| `duckdb_async_pool` fixture | `tests/async/conftest.py:75` | Real file-backed DuckDB `AsyncPool`, closed on teardown | Template for `snowflake_async_pool`; backs TEST-03 `[VERIFIED: read]` |
| `make_stub_async_connection` | `tests/async/conftest.py:97` | Real `AsyncConnection` over a `BlockingStubConnection` | Stub-gated mechanics `[VERIFIED: read]` |
| `_stub_conn_on(limiter)` | `tests/async/test_edge_limiter.py:52` | Build `AsyncConnection` over fresh stub sharing one limiter | TEST-04 flood reuses this exact helper `[VERIFIED: read]` |
| `real_clock_watchdog` | `tests/async/_edge_helpers.py:38` | Wall-clock side-thread that `close()`s stubs on overrun | TEST-04 deadlock detection (D-27-11) `[VERIFIED: read]` |
| `await_inside` | `tests/async/_edge_helpers.py:81` | Bounded `anyio.sleep(0)` poll until a stub predicate holds | Wait-for-saturation in the flood `[VERIFIED: read]` |
| `scan_async_package` | `tests/_async_harness/guard.py:136` | Pure-AST source scanner returning `list[Finding]` | The EDGE-27/30 guards extend this module `[VERIFIED: read]` |
| `BlockingStubCursor`/`Connection` | `tests/_async_harness/stubs.py` | Sticky-latch gating fakes (locked D-04 attr names) | Flood + any gating test `[VERIFIED: read]` |
| `run_blocking` | `tests/_async_harness/gating.py:31` | Offload + `entered` bridge (compliant `limiter=` shape) | Reference offload shape `[VERIFIED: read]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff | Verdict |
|------------|-----------|----------|---------|
| `total_allocated_bytes()` delta | process RSS (`psutil`) | RSS is non-deterministic → flaky tolerance | **Rejected by D-27-07** — use the allocator counter |
| `real_clock_watchdog` thread | `anyio.fail_after` | Autojumps to its own deadline under trio MockClock → trips every run | **Rejected by D-27-11** and the harness lesson — never for off-loop gating |
| Rewrite all EDGE tests to one shape | Blanket parametrization sweep | Risks reintroducing lost-wakeup/MockClock landmines | **Rejected by D-27-02** — fix only meta-flagged violators |
| Force every EDGE test through cassette | DuckDB+Snowflake on all gating tests | `ReplayCursor` can't block-gate and lacks `adbc_cancel` | **Rejected by D-27-06** — cassette = read-path surface only |

**Installation:** None. Every dependency is already in `[dependency-groups].dev` and locked in `uv.lock`. `[VERIFIED: pyproject.toml]`

**Version verification (run this session):**
```
anyio 4.14.1 · trio 0.33.0 · pyarrow 24.0.0 · pytest-adbc-replay 1.0.0
```
`total_allocated_bytes()` delta behaviour confirmed deterministic:
```
baseline: 0  →  after pa.table({'a': range(1000)}): 8000  →  after del+gc.collect(): 0
```
This is exactly the no-monotonic-growth signal D-27-07 specifies. `[VERIFIED: .venv/bin/python]`

## Package Legitimacy Audit

> No new external packages are installed by this phase — all dependencies already ship in the locked `dev` group. The gate is therefore satisfied by confirming the existing versions resolve on the correct ecosystem registry.

| Package | Registry | Source Repo | Verdict | Disposition |
|---------|----------|-------------|---------|-------------|
| anyio 4.14.1 | PyPI | github.com/agronholm/anyio | OK | Already installed |
| trio 0.33.0 | PyPI | github.com/python-trio/trio | OK | Already installed |
| pyarrow 24.0.0 | PyPI | github.com/apache/arrow | OK | Already installed |
| pytest-adbc-replay 1.0.0 | PyPI | (ADBC ecosystem) | OK | Already installed |
| aiotools >=2.2 | PyPI | github.com/achimnol/aiotools | OK | Already installed |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
**No new installs** — `package-legitimacy check` not required (no new package surface introduced).

## Architecture Patterns

### System Architecture Diagram

```
                        Phase 27 test additions (all in tests/)
                        ════════════════════════════════════════

  ┌─────────────────────────── tests/async/conftest.py ───────────────────────────┐
  │  anyio_backend  ──(asyncio | trio + MockClock)──┐                              │
  │  duckdb_async_pool ─────────────────────────────┤  fixtures consumed below    │
  │  snowflake_async_pool  (NEW — D-27-04) ─────────┤                              │
  │  make_stub_async_connection / _stub_conn_on ────┘                              │
  └────────────────────────────────────────────────────────────────────────────────┘
            │                    │                       │                  │
            ▼                    ▼                       ▼                  ▼
   ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐
   │ test_matrix_*   │  │ test_stability_* │  │ test_limiter_    │  │ test_meta_   │
   │ (TEST-01/02)    │  │ (TEST-03)        │  │  stress_*        │  │  guard_*     │
   │                 │  │                  │  │ (TEST-04)        │  │ (EDGE-27/30) │
   │ read-path ×     │  │ N≥100 cycles:    │  │ 4×(ps+mo) flood  │  │ asserts the  │
   │ {ddb,snow} ×    │  │ open→exec→fetch→ │  │ stub-gated;      │  │ NEW guard    │
   │ {asyncio,trio}  │  │ checkin; assert  │  │ running-max==    │  │ callables    │
   │                 │  │ total_allocated  │  │ bound; +DuckDB   │  │ return []    │
   │ DuckDB: real    │  │ _bytes() delta   │  │ smoke flood;     │  │              │
   │ Snow:  cassette │  │ →baseline;       │  │ time.monotonic() │  └──────┬───────┘
   │  (ReplayCursor) │  │ reset-event      │  │ watchdog (NOT    │         │
   └─────────────────┘  │ count==N         │  │ fail_after)      │         │
                        └──────────────────┘  └────────┬─────────┘         │
                                                       │                   ▼
                                       ┌───────────────┘    ┌──────────────────────────────┐
                                       ▼                    │ tests/_async_harness/guard.py │
                            ┌────────────────────┐          │  scan_async_package (exists)  │
                            │ BlockingStub*       │          │  + scan_async_test_hygiene NEW│
                            │ real_clock_watchdog │          │  + scan_for_positive_sleep NEW│
                            │ await_inside        │          │  (pure stdlib AST, no anyio)  │
                            └────────────────────┘          └──────────────────────────────┘

  CI (.github/workflows/ci.yml):
     quality job (uv sync --dev --extra duckdb)  ← runs pytest → INCLUDES all new tests
     sync-no-anyio job (--no-default-groups)     ← --ignore=tests/async → EXCLUDES them
```

### Recommended Project Structure
```
tests/
├── async/
│   ├── conftest.py              # ADD snowflake_async_pool fixture (D-27-04)
│   ├── test_matrix_readpath.py  # NEW — TEST-01/02 read-path × backend × loop
│   ├── test_stability_arrow.py  # NEW — TEST-03 allocator delta + reset count
│   ├── test_limiter_stress.py   # NEW — TEST-04 flood + smoke flood
│   └── test_meta_guard.py       # NEW — EDGE-27/30 assert guard callables == []
│                                #   (names at planner discretion per D-27 discretion)
└── _async_harness/
    └── guard.py                 # EXTEND — two new pure-AST scanner callables
```

### Pattern 1: Promote the inline Snowflake cassette leg into a fixture (D-27-04)
**What:** A `snowflake_async_pool` fixture mirroring `duckdb_async_pool`, backed by the existing `snowflake_arrow_round_trip` cassette — no live Snowflake.
**When to use:** Backing the read-path matrix's Snowflake leg.
**Source:** The pattern is already proven green in `tests/async/test_async_lifecycle.py:132` (`TestSnowflakeCassetteLeg`). Promote it verbatim into a fixture:
```python
# tests/async/conftest.py — NEW fixture (mirror of duckdb_async_pool)
# Source: distilled from test_async_lifecycle.py::TestSnowflakeCassetteLeg (proven green)
import os
from pathlib import Path
import pytest
from adbc_poolhouse import SnowflakeConfig, close_async_pool, create_async_pool

_CASSETTE_ROOT = Path(__file__).parent.parent / "cassettes"

@pytest.fixture
async def snowflake_async_pool():
    """Cassette-backed Snowflake AsyncPool; skipped cleanly if driver/cassette absent."""
    pytest.importorskip(
        "adbc_driver_snowflake.dbapi",
        reason="Snowflake driver not installed; cassette leg skipped",
    )
    if not (_CASSETTE_ROOT / "snowflake_arrow_round_trip").exists():
        pytest.skip("snowflake_arrow_round_trip cassette absent")
    # Replay mode: dummy account satisfies the validator; cassette intercepts.
    os.environ.setdefault("SNOWFLAKE_ACCOUNT", "replay-account")
    pool = create_async_pool(SnowflakeConfig())  # type: ignore[call-arg]
    try:
        yield pool
    finally:
        await close_async_pool(pool)
```
**Critical:** The consuming test methods must still carry `@pytest.mark.snowflake` and `@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")` — the marker is what tells pytest-adbc-replay which cassette to mount. The fixture alone does NOT mount the cassette; the `adbc_cassette` marker (read from `adbc_cassette_dir = "tests/cassettes"` in pyproject) does. `[VERIFIED: read — test_async_lifecycle.py + pyproject.toml lines 71-80]`

### Pattern 2: Read-path matrix (D-27-05) — parametrize over the pool fixture, not the backend
**What:** The DuckDB × Snowflake cross-product applies only to the read-path surface: connect → execute → `fetch_arrow_table` → checkin, and the `AsyncCursor` fetch surface. The {asyncio, trio} axis is already free via `anyio_backend`.
**When to use:** TEST-01/02.
**Example (use an indirect fixture-name parametrization so each pool fixture is requested lazily and skips independently):**
```python
# Source: pattern grounded in conftest fixtures + pytest indirect parametrization
import pytest

@pytest.mark.anyio
@pytest.mark.parametrize("pool_fixture", [
    "duckdb_async_pool",
    pytest.param("snowflake_async_pool",
                 marks=[pytest.mark.snowflake,
                        pytest.mark.adbc_cassette("snowflake_arrow_round_trip")]),
])
async def test_readpath_backend_generic(pool_fixture, request):
    pool = request.getfixturevalue(pool_fixture)  # lazy: snowflake leg skips cleanly
    async with await pool.connect() as conn:
        cur = conn.cursor()
        await cur.execute("SELECT 1 AS n, 'hello' AS s")
        table = await cur.fetch_arrow_table()
        assert table.num_rows == 1
    assert pool._pool.checkedout() == 0
```
**Why `request.getfixturevalue`:** it defers fixture construction until the param is actually selected, so the Snowflake `importorskip`/`skip` only fires on that leg and never breaks the DuckDB leg. `[CITED: docs.pytest.org getfixturevalue]` `[VERIFIED: fixture skip pattern read from test_async_lifecycle.py]`

> **Landmine (D-27-06):** Do NOT route gating/limiter/cancel tests through the cassette. The `ReplayCursor` is replay-only — it cannot block a worker (no `threading.Event` gate) and lacks `adbc_cancel` (Phase 25). It can only back the happy-path read surface. Stub-gated mechanics stay DuckDB+stub.

### Pattern 3: Arrow memory-stability (TEST-03 / D-27-07/08)
**What:** Loop N≥100 real DuckDB cursor cycles; assert `total_allocated_bytes()` returns to (or stays bounded near) baseline after drop + `gc.collect()`; second assertion counts the `reset` event firing once per checkin (ACONN-06).
**Source:** EDGE-21 (`test_edge_resource.py`) is the closest analog (real DuckDB, `fetch_arrow_table`, checkin, looped). Extend its loop to N≥100 and add the allocator delta.
```python
# Source: extends test_edge_resource.py pattern + pyarrow allocator counter (verified)
import gc
import pyarrow
import pytest
import sqlalchemy

_N = 100  # D-27-07: N >= 100 cycles

@pytest.mark.anyio
async def test_arrow_allocator_no_growth(duckdb_async_pool, anyio_backend_name):
    del anyio_backend_name
    # D-27-08: count the reset event (the _release_arrow_allocators path) per checkin.
    reset_count = 0
    def _on_reset(dbapi_conn, conn_record, reset_state):  # SQLAlchemy reset listener
        nonlocal reset_count
        reset_count += 1
    sqlalchemy.event.listen(duckdb_async_pool._pool, "reset", _on_reset)

    gc.collect()
    baseline = pyarrow.total_allocated_bytes()
    for i in range(_N):
        async with await duckdb_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute(f"SELECT {i} AS n")
            tbl = await cur.fetch_arrow_table()
            del tbl  # drop the only ref inside the loop
        # checkin fired the reset event here
    gc.collect()
    delta = pyarrow.total_allocated_bytes() - baseline
    assert delta == 0, f"Arrow allocator grew by {delta} bytes over {_N} cycles"
    assert reset_count == _N, f"reset fired {reset_count}x, expected {_N} (ACONN-06)"
```
**Why this works:** verified this session that `total_allocated_bytes()` returns exactly to 0 after `del table; gc.collect()`. The existing `_release_arrow_allocators` (`_pool_factory.py:407`) is registered on the pool `reset` event (`_pool_factory.py:106`), which fires on every return path — so a parallel `event.listen(pool._pool, "reset", counter)` counts firings **without touching production code** (D-27-08, no source change). `[VERIFIED: read _pool_factory.py:106,407 + total_allocated_bytes probe]`

> **Determinism note:** `total_allocated_bytes()` is the *process-global* Arrow allocator total, not RSS — so the delta is exact and reproducible (D-27-07 chose it precisely to avoid a flaky RSS tolerance). If `delta == 0` proves too strict on some pyarrow build, fall back to a bounded `delta < single_table_bytes` assertion (still "no monotonic growth"), but try the exact-zero form first — it held in the probe.

### Pattern 4: Limiter-sizing stress flood (TEST-04 / D-27-10/11)
**What:** Reuse the EDGE-12 shape exactly: `bound = pool_size + max_overflow` stub-backed connections share ONE limiter; launch `4 × bound` gated executes; assert observed running-max (`limiter.borrowed_tokens` at saturation) `== bound`; drain via `close()`; assert every worker eventually runs (no starvation). Wrap in `real_clock_watchdog` (NOT `anyio.fail_after`).
**Source:** `test_edge_limiter.py:269` (`TestEdge12ConcurrencyBound`) is the verbatim pattern. Add a small real-DuckDB smoke flood for realism (D-27-10).
```python
# Source: test_edge_limiter.py::TestEdge12ConcurrencyBound (verbatim reuse)
import functools, importlib
import anyio, pytest
from adbc_poolhouse._async._connection import AsyncConnection
from tests._async_harness.stubs import BlockingStubConnection

_h = importlib.import_module("tests.async._edge_helpers")
await_inside, real_clock_watchdog = _h.await_inside, _h.real_clock_watchdog

def _stub_conn_on(limiter):
    sc = BlockingStubConnection()
    return AsyncConnection(sc, limiter), sc  # type: ignore[arg-type]

@pytest.mark.anyio
async def test_running_max_equals_bound(anyio_backend_name):
    del anyio_backend_name
    bound = 8  # stand-in for pool_size + max_overflow (5 + 3)
    flood = bound * 4
    limiter = anyio.CapacityLimiter(bound)
    pairs = [_stub_conn_on(limiter) for _ in range(flood)]
    cursors = [c.cursor() for c, _ in pairs]
    stub_cursors = [s.cursors[0] for _, s in pairs]
    with real_clock_watchdog(stub_cursors) as watchdog:
        async with anyio.create_task_group() as tg:
            for i, cur in enumerate(cursors):
                tg.start_soon(functools.partial(cur.execute, f"SELECT {i}"))
            try:
                await await_inside(lambda: limiter.borrowed_tokens == bound)
                assert limiter.borrowed_tokens == bound  # never exceeds
            finally:
                for cur in stub_cursors:
                    cur.close()  # terminal drain — no re-arm trap (see EDGE-12 note)
                await await_inside(lambda: limiter.borrowed_tokens == 0)  # no starvation
    assert watchdog[0] is False, "watchdog tripped: a worker hung"
    assert limiter.borrowed_tokens == 0
```
**The two load-bearing details from the EDGE-12 source:**
1. **Drain via `close()`, not `release()`** — a closed stub short-circuits in `_block` and returns immediately even for a worker that has not yet entered; a plain `release()` clears on the next `_block` and strands a worker that enters after it (the lost-wakeup the Phase 26 LEARNINGS diagnosed).
2. **`real_clock_watchdog` measures wall-clock on a side thread** — `anyio.fail_after` would autojump to its own deadline under the trio `MockClock(autojump_threshold=0)` the instant the workers block off-loop, tripping every run.
`[VERIFIED: read test_edge_limiter.py:269-318 + 26-LEARNINGS.md]`

> **Real-DuckDB smoke flood (D-27-10):** a separate, smaller test that floods `4×bound` real `await pool.connect()→execute→fetch` tasks against `duckdb_async_pool` and asserts they all complete and `checkedout() == 0` after — realism, no gating, watchdog-wrapped. Keep it small (the real driver returns promptly; the gating proof is the stub test).

### Pattern 5: Meta-guard extension (EDGE-27 / D-27-01, EDGE-30 / discretion)
**What:** Two NEW pure-stdlib AST callables in `tests/_async_harness/guard.py`, asserted `== []` from a meta-test — mirroring the existing `scan_async_package` + `test_async_guard.py` pattern.

**Guard A — `scan_async_test_hygiene(root)` (EDGE-27):** scans `tests/async/` and returns `Finding`s for:
- any `import asyncio` / `from asyncio import ...` (reuse the existing `visit_Import`/`visit_ImportFrom` logic);
- any `@pytest.mark.asyncio` decorator (an `ast.Attribute` chain `pytest.mark.asyncio` on an async `FunctionDef`);
- any `async def test_*` that is NOT anyio-parametrized — i.e. lacks `@pytest.mark.anyio` AND does not request `anyio_backend`/`anyio_backend_name` (directly or via a fixture). **See the indirection caveat below.**

**Guard B — `scan_for_positive_sleep(root)` (EDGE-30):** returns `Finding`s for any `sleep(...)` call (`anyio.sleep`, `trio.sleep`, `asyncio.sleep`, `time.sleep`) whose first positional arg is a numeric `ast.Constant` `> 0`. `sleep(0)`, `sleep(0.0)`, and any non-literal arg (e.g. `sleep(deadline)`) are ALLOWED.

```python
# Source: extends tests/_async_harness/guard.py (same pure-stdlib AST visitor pattern)
import ast

def _is_sleep_call(func: ast.expr) -> bool:
    # matches `<mod>.sleep(...)` and bare `sleep(...)`
    if isinstance(func, ast.Attribute) and func.attr == "sleep":
        return True
    return isinstance(func, ast.Name) and func.id == "sleep"

class _SleepVisitor(ast.NodeVisitor):
    def __init__(self, path): self.path, self.findings = path, []
    def visit_Call(self, node):  # noqa: N802
        if _is_sleep_call(node.func) and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)) and arg.value > 0:
                self.findings.append(Finding(self.path, node.lineno,
                    "positive-sleep-literal",
                    f"sleep({arg.value!r}) banned in timeout/cancel tests; use sleep(0) or event gating"))
        self.generic_visit(node)
```
**Meta-test:**
```python
# Source: mirrors tests/test_async_guard.py::TestRealAsyncPackage
from tests._async_harness.guard import scan_async_test_hygiene, scan_for_positive_sleep

def test_async_test_package_hygiene():
    assert scan_async_test_hygiene("tests/async") == []

def test_no_positive_sleep_in_async_tests():
    assert scan_for_positive_sleep("tests/async") == []
```
`[VERIFIED: pattern read from guard.py + test_async_guard.py]`

### Anti-Patterns to Avoid
- **Using `anyio.fail_after` as a watchdog for off-loop gating** — autojumps under the trio MockClock, trips every run. Use `real_clock_watchdog` (D-27-11). `[VERIFIED: _edge_helpers.py + 26-LEARNINGS.md]`
- **Draining a flood with `release()`** — strands late workers via the re-arm `clear()`. Use `close()` (terminal). `[VERIFIED: test_edge_limiter.py:307-313]`
- **Routing gating/cancel/limiter tests through the Snowflake cassette** — `ReplayCursor` can't block-gate and has no `adbc_cancel` (D-27-06). `[VERIFIED: 25-CONTEXT + canonical refs]`
- **Process RSS for stability** — non-deterministic; D-27-07 mandates `total_allocated_bytes()`. `[VERIFIED: probe + D-27-07]`
- **Blanket-rewriting the ~10 existing EDGE files** — risks reintroducing landmines; fix only meta-flagged violators (D-27-02). `[VERIFIED: D-27-02]`
- **Hoisting `anyio_backend` to the root conftest** — breaks PKG-04 (sync suite must collect without anyio). Keep fixtures at/below `tests/async/`. `[VERIFIED: conftest docstrings]`
- **EDGE-30 scanner scope creep** — `tests/_async_harness/conftest.py:71` (`anyio.sleep(1)`) and `clock.py:68` (`anyio.sleep(3600)`) are positive sleeps that exist in the **harness** (under MockClock/VirtualClock, deliberate). Scope the EDGE-30 scan to `tests/async/` only (the requirement says "in timeout tests" / "async test package"), NOT the whole harness, or it will false-positive. `[VERIFIED: grep this session]`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dual-backend param | A custom asyncio/trio runner | `anyio_backend` fixture (`conftest.py:46`) | Already gives the axis + MockClock for free |
| Block a worker deterministically | A `time.sleep`-based fake | `BlockingStubCursor` (sticky-latch) | Sticky-cancel latch already survives the Linux lost-wakeup |
| Deadlock detection | `anyio.fail_after` | `real_clock_watchdog` | Virtual clock autojumps; real-clock thread is the proven substitute |
| Wait for saturation | A polling loop with sleeps | `await_inside` | Pure `sleep(0)` checkpoints, settles under both legs |
| Snowflake replay | Live Snowflake / a new mock | `pytest-adbc-replay` + existing cassette | Already wired and green for the async layer |
| Arrow memory metric | RSS sampling / `tracemalloc` | `pyarrow.total_allocated_bytes()` | Deterministic, process-global, delta verified |
| Source-scan guard | A regex grep | `scan_async_package`-style AST visitor | Pure-stdlib AST already in the harness; extend it |
| Reset-event counting | Patch `_release_arrow_allocators` | `sqlalchemy.event.listen(pool._pool, "reset", counter)` | Counts firings WITHOUT touching frozen source |

**Key insight:** Phase 27's hardest problems (deterministic gating, cross-platform lost-wakeup, virtual-clock autojump, Arrow lifetime) were already solved and hardened in Phases 23–26. The phase's job is to *assemble* these primitives into the matrix shape, not re-solve them. Every "don't hand-roll" row points at an in-repo asset read this session.

## Runtime State Inventory

> Phase 27 is a pure additive test phase (new test files + two new guard functions). It is NOT a rename/refactor/migration. No production code, stored data, services, OS registrations, secrets, or build artifacts are touched.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — verified: no DB key/collection/user_id renames; cassettes are read-only replay assets, not mutated | None |
| Live service config | None — verified: Snowflake leg uses checked-in cassettes (no live warehouse); no CI service config changes beyond test selection | None |
| OS-registered state | None — no task scheduler / launchd / systemd / pm2 involvement | None |
| Secrets/env vars | `SNOWFLAKE_ACCOUNT=replay-account` is set in-test for replay mode only (existing pattern, no real secret) | None |
| Build artifacts | None — no `pyproject.toml` package metadata, egg-info, or compiled artifacts change | None |

**Net:** the only on-disk additions are new `tests/async/test_*.py` files, edits to `tests/async/conftest.py` and `tests/_async_harness/guard.py`, and (if a cassette is genuinely missing) a re-recorded cassette under `tests/cassettes/`. The existing `snowflake_arrow_round_trip` cassette already exists and is used green, so a re-record is likely unnecessary (verified the cassette files are present).

## Common Pitfalls

### Pitfall 1: EDGE-30 `sleep(0)` allow-list and scanner scope
**What goes wrong:** A naive "ban `sleep(`" scanner flags the ~10 legitimate `anyio.sleep(0)` checkpoints in `await_inside`, `test_edge_loophygiene.py`, `test_edge_cancel_depth.py`, and `test_edge_limiter.py` — and/or flags the deliberate positive sleeps in `tests/_async_harness/conftest.py:71` / `clock.py:68` that run under virtual clocks.
**Why it happens:** The ban is on *positive-duration literals in `tests/async/` timeout/cancel tests*, not all sleeps everywhere.
**How to avoid:** AST-match `sleep(<positive numeric Constant>)` only; allow `sleep(0)`, `sleep(0.0)`, and non-literal args. Scope the scan root to `tests/async/`, not `tests/_async_harness/`.
**Warning signs:** the meta-test fails on existing, hardened tests.
`[VERIFIED: grep of sleep usage this session]`

### Pitfall 2: The "every test is anyio-parametrized" check and indirect fixture requesting
**What goes wrong:** A test like `test_execute_fetch_arrow_table(self, duckdb_async_pool)` carries `@pytest.mark.anyio` but does NOT name `anyio_backend`/`anyio_backend_name` in its signature — it gets the backend axis transitively because the anyio plugin parametrizes any `@pytest.mark.anyio` test, and `duckdb_async_pool` is an async fixture. A scanner that requires the literal `anyio_backend` argument would false-positive on most existing tests.
**Why it happens:** anyio's plugin keys off the `@pytest.mark.anyio` marker, not the fixture name; many tests get `anyio_backend_name` only when they need the string.
**How to avoid:** The EDGE-27 hygiene rule should assert **`@pytest.mark.anyio` is present on every `async def test_*`** (that is what guarantees the asyncio/trio param), plus the negative rules (no `import asyncio`, no `@pytest.mark.asyncio`). Do NOT require the literal `anyio_backend` argument. This matches D-27-01's "requests `anyio_backend`/`anyio_backend_name` directly OR via a fixture" — and `@pytest.mark.anyio` is the via-fixture signal.
**Warning signs:** the hygiene meta-test flags `test_async_lifecycle.py` tests that are demonstrably dual-backend.
`[VERIFIED: read test_async_lifecycle.py — tests use @pytest.mark.anyio + plain fixtures]`

### Pitfall 3: Forgetting the `adbc_cassette` marker on the Snowflake matrix leg
**What goes wrong:** The `snowflake_async_pool` fixture builds a pool, but without `@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")` on the test, pytest-adbc-replay never mounts the cassette → the test tries a real connection and fails (or skips for the wrong reason).
**Why it happens:** The cassette is mounted by the marker, not the fixture.
**How to avoid:** Carry both `@pytest.mark.snowflake` and `@pytest.mark.adbc_cassette(...)` on the Snowflake parametrization (via `pytest.param(..., marks=[...])`).
**Warning signs:** a replay-mode connection error instead of a clean replay.
`[VERIFIED: pyproject.toml adbc_cassette_dir + test_snowflake.py marker usage]`

### Pitfall 4: A green local ×20 loop does not prove cross-platform stability
**What goes wrong:** The flood/stability tests pass 20/20 on macOS but a thread-scheduling race hangs on Linux CI (exactly the Phase 25 bug surfaced by Phase 26's first CI run).
**Why it happens:** Race outcomes depend on OS thread-startup order.
**How to avoid:** Run the ×20 loop locally (the project rule) AND treat Linux CI as the real gate. Use `close()`-drain + `real_clock_watchdog` (both already cross-platform-hardened). If a new test gates a worker, model any release that can outrun the consumer as sticky state (the stubs already do).
**Warning signs:** a single-shot green that hangs intermittently on CI.
`[VERIFIED: 26-LEARNINGS.md "green local loop does not prove cross-platform race absent"]`

### Pitfall 5: `total_allocated_bytes()` exact-zero may not hold on every Arrow build
**What goes wrong:** The exact `delta == 0` assertion could be brittle if a future pyarrow build retains a small pool arena.
**Why it happens:** Allocator implementation detail.
**How to avoid:** Try `delta == 0` first (it held in this session's probe on pyarrow 24.0.0). If it flakes, relax to `delta < one_table_size` — still proves "no monotonic growth across N cycles," which is what D-27-07 requires.
**Warning signs:** a small non-zero delta that does not grow with N.
`[VERIFIED: probe held delta==0 on 24.0.0; relaxation is the documented fallback]`

## Code Examples

All load-bearing examples are inline in the Architecture Patterns section above (Patterns 1–5), each tagged with its in-repo source. No additional external examples are needed — the phase is built entirely from in-repo primitives.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `anyio.fail_after` watchdog | `real_clock_watchdog` side thread | Phase 24/25 | Off-loop gating tests need real-clock detection (MockClock autojumps) |
| Transient `Event.set()` release in stubs | Sticky `_cancelled`/`_closed` latch under lock | Phase 26 (PR #32) | Fixes Linux-only lost-wakeup; flood drains must use `close()` |
| `cancellable=` kwarg on `to_thread.run_sync` | `abandon_on_cancel=` | anyio 4.x | `cancellable=` is a deprecated alias; not relevant to this test phase but noted |
| Inline Snowflake cassette leg in a test method | Promote to `snowflake_async_pool` fixture | Phase 27 (this phase) | Reusable across the read-path matrix |

**Deprecated/outdated:** None affecting this phase. The frozen `_async/` surface uses `abandon_on_cancel=` correctly already (Phase 24/26).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `total_allocated_bytes() delta == 0` holds in CI (Linux, pyarrow 24.0.0) as it did in the local macOS probe | Pattern 3 / Pitfall 5 | LOW — documented fallback to bounded delta; same "no growth" guarantee |
| A2 | The existing `snowflake_arrow_round_trip` cassette covers the read-path the matrix needs (SELECT + fetch_arrow_table) | Pattern 1/2 | LOW — verified the cassette files exist and the inline async leg already replays them green; if a new query shape is needed, re-record once per D-27-04 |
| A3 | `@pytest.mark.anyio` presence is a sufficient EDGE-27 hygiene signal for "anyio-parametrized" | Pitfall 2 | LOW — matches D-27-01's "directly OR via a fixture"; confirm with the planner that the marker (not the literal arg) is the assertion |

**If this table is empty:** it is not — three LOW-risk assumptions, each with a documented mitigation. None contradict a locked decision.

## Open Questions

1. **Exact `pool_size + max_overflow` value for the flood bound**
   - What we know: defaults are `pool_size=5`, `max_overflow=3` → bound 8 (`_pool_factory.py` / EDGE-12 used a stand-in `bound=3`).
   - What's unclear: whether the flood should use the real default-8 or a smaller stand-in for speed.
   - Recommendation: use the real default (8) so the test proves the *shipped* bound; flood of 32 gated stubs is cheap (no real I/O).

2. **Whether a cassette re-record is needed at all**
   - What we know: `snowflake_arrow_round_trip` exists and replays green through the async layer.
   - What's unclear: if the planner wants a distinct read-path query not covered by the existing cassette.
   - Recommendation: reuse the existing cassette; only re-record (`pytest --adbc-record=once -m snowflake`, needs live creds) if a genuinely new query shape is required (D-27-04 explicitly permits this).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| anyio | all async tests | ✓ | 4.14.1 | — |
| trio | trio leg | ✓ | 0.33.0 | — |
| pyarrow | TEST-03 | ✓ | 24.0.0 | bounded delta if exact-zero flakes |
| pytest-adbc-replay | TEST-02 Snowflake leg | ✓ | 1.0.0 | leg skips via `importorskip` if driver absent |
| adbc-driver-snowflake | Snowflake cassette replay | ✓ (dev `[all]`) | — | `pytest.importorskip` → clean skip |
| DuckDB driver | DuckDB legs | ✓ (`[duckdb]` extra) | — | — |
| Snowflake cassette assets | Snowflake leg | ✓ | `tests/cassettes/snowflake_arrow_round_trip/` present | clean `pytest.skip` if absent |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none currently missing; the Snowflake leg degrades to a clean skip if the driver or cassette is absent (existing pattern).

## Validation Architecture

> `nyquist_validation: true` in config.json — section included. **This is a test phase, so the new tests ARE the validation.** Each requirement maps to the test that proves it.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0.0 + anyio pytest plugin (`@pytest.mark.anyio`) + pytest-adbc-replay 1.0.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (markers, `adbc_cassette_dir`, `adbc_auto_patch`) |
| Quick run command | `.venv/bin/pytest tests/async/test_<new>.py -x` |
| Full suite command | `.venv/bin/pytest` (or `uv run pytest`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | Async suite param over asyncio+trio | meta + every test | `.venv/bin/pytest tests/async -k matrix` | ❌ Wave 0 (new) |
| TEST-02 | Exercised vs DuckDB + Snowflake cassette | parametrized read-path | `.venv/bin/pytest tests/async/test_matrix_*.py` | ❌ Wave 0 (new) |
| TEST-03 | No Arrow allocator growth over N≥100 | unit (real DuckDB) | `.venv/bin/pytest tests/async/test_stability_*.py` | ❌ Wave 0 (new) |
| TEST-04 | No deadlock/starvation when concurrency > pool_size | stub-gated flood + smoke | `.venv/bin/pytest tests/async/test_limiter_stress_*.py` | ❌ Wave 0 (new) |
| EDGE-27 | No asyncio import / mark; all anyio-param | meta (AST scan) | `.venv/bin/pytest -k async_test_package_hygiene` | ❌ Wave 0 (new guard fn + meta-test) |
| EDGE-30 | No positive `sleep` literal in timeout tests | meta (AST scan) | `.venv/bin/pytest -k no_positive_sleep` | ❌ Wave 0 (new guard fn + meta-test) |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/async/<the new file> -x`
- **Per wave merge:** `.venv/bin/pytest tests/async tests/_async_harness`
- **Phase gate:** full `.venv/bin/pytest` green + the ×20 loop-stability gate (0 hangs) on every new/meta-flagged concurrency test + Linux CI green (the real cross-platform gate per Pitfall 4).

### ×20 Loop-Stability Gate (project flaky-concurrency rule)
Run each new concurrency test (flood, stability, any gated test) in a loop and require 0 hangs. **Caveat (from MEMORY):** the Bash tool runs zsh; `if ! cmd` inside a `for`-loop silently skips the command and fakes a green loop. Use `rc=$?` and grep the log for the pass line:
```bash
for i in $(seq 1 20); do
  .venv/bin/pytest tests/async/test_limiter_stress_xxx.py -x -q >/tmp/loop.$i.log 2>&1
  rc=$?
  grep -q "passed" /tmp/loop.$i.log || { echo "FAIL iter $i (rc=$rc)"; break; }
done
```
`[VERIFIED: MEMORY zsh-bang + loop-flaky-concurrency feedback notes]`

### Wave 0 Gaps
- [ ] `tests/async/conftest.py` — add `snowflake_async_pool` fixture (D-27-04)
- [ ] `tests/_async_harness/guard.py` — add `scan_async_test_hygiene` + `scan_for_positive_sleep` (EDGE-27/30), each with Google-style docstrings (CLAUDE.md docs gate — these are public harness callables)
- [ ] `tests/async/test_matrix_*.py` — TEST-01/02 read-path matrix
- [ ] `tests/async/test_stability_*.py` — TEST-03 allocator + reset-count
- [ ] `tests/async/test_limiter_stress_*.py` — TEST-04 flood + smoke
- [ ] `tests/async/test_meta_guard_*.py` — EDGE-27/30 meta-tests asserting `== []`
- [ ] Framework install: none — all present.

## Project Constraints (from CLAUDE.md)

- **Docs quality gate (phases ≥ 7):** Plans must include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>`. For this test phase, the "public symbols" requiring Google-style docstrings (Args/Returns/Raises) are the **new harness guard callables** (`scan_async_test_hygiene`, `scan_for_positive_sleep`) and the new `snowflake_async_pool` fixture — mirror the existing thorough docstrings in `guard.py`/`conftest.py`.
- **`uv run mkdocs build --strict` must pass** as a completion requirement. Test files are not in the API reference, but if any new public harness symbol is referenced by docs autogen it must build clean. Use `.venv/bin/mkdocs build --strict` under the sandbox (MEMORY uv-sandbox-workaround).
- **Docstring style (MEMORY):** Google-style, Markdown (not RST) — `` `create_pool` `` not `` :func:`create_pool` ``. `Example:` (singular) for an admonition box with fenced code.
- **Humanizer pass** on any new or substantially rewritten prose.

## Project Skills (discovered)

- `.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — project voice (direct, second-person, HTTPX/SQLAlchemy-like), Google-style docstrings, humanizer pass. Applies to the docstrings on the new harness callables and fixture.

## Sources

### Primary (HIGH confidence — read directly this session)
- `tests/async/conftest.py` — `anyio_backend`, `duckdb_async_pool`, `make_stub_async_connection`
- `tests/async/test_edge_limiter.py` — EDGE-12 flood (`TestEdge12ConcurrencyBound`), token accounting, `_stub_conn_on`
- `tests/async/test_edge_resource.py` — EDGE-21 Arrow-lifetime pattern (TEST-03 analog)
- `tests/async/test_async_lifecycle.py` — working inline Snowflake cassette async leg (`TestSnowflakeCassetteLeg`)
- `tests/async/_edge_helpers.py` — `real_clock_watchdog`, `await_inside`
- `tests/_async_harness/guard.py` + `tests/test_async_guard.py` — `scan_async_package` AST guard + self-tests
- `tests/_async_harness/stubs.py` — `BlockingStub*`, sticky-cancel latch
- `tests/_async_harness/gating.py` / `clock.py` / `conftest.py` — offload bridge, virtual clock, nested backend fixture
- `tests/integration/test_snowflake.py` + `tests/integration/conftest.py` — `snowflake_pool` fixture + cassette marker usage
- `src/adbc_poolhouse/_pool_factory.py:106,407` — `_release_arrow_allocators` reset listener (TEST-03 reset count)
- `src/adbc_poolhouse/_async/_connection.py:199-280` — checkin/close/invalidate firing the reset event
- `pyproject.toml` — `adbc_cassette_dir`, `adbc_auto_patch`, markers, dev deps
- `.github/workflows/ci.yml` — `quality` job (runs all tests) + `sync-no-anyio` job (`--ignore=tests/async`)
- `.planning/phases/26-packaging-extra-scoping/26-LEARNINGS.md` — lost-wakeup, MockClock autojump, sticky latch
- Version + allocator probe via `.venv/bin/python` (anyio 4.14.1, trio 0.33.0, pyarrow 24.0.0, pytest-adbc-replay 1.0.0; `total_allocated_bytes` 0→8000→0)

### Secondary (MEDIUM confidence)
- `.planning/research/ASYNC-EDGE-CASES.md` — EDGE-12/21/27/30 designs (verified against anyio 4.x docs at authoring)

### Tertiary (LOW confidence)
- None — every claim is grounded in directly-read in-repo source or a tool probe.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every asset read this session; versions probed
- Architecture/patterns: HIGH — built from in-repo, already-green primitives
- Pitfalls: HIGH — drawn from Phase 26 LEARNINGS + grep of actual sleep/asyncio usage
- TEST-03 metric: HIGH — `total_allocated_bytes` delta behaviour verified by probe
- Cassette fixture: HIGH — working inline pattern already replays green

**Research date:** 2026-06-28
**Valid until:** 2026-07-28 (stable — in-repo assets and locked dependency versions; no fast-moving external surface)
