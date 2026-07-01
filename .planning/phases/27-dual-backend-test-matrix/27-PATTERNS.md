# Phase 27: Dual-Backend Test Matrix - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 6 (2 MODIFY, 4 NEW)
**Analogs found:** 6 / 6 (every new/modified file has a strong in-repo analog)

> This phase is pure test-layer assembly. RESEARCH.md already mapped each file to
> its source pattern with inline examples; this PATTERNS.md is the *verified-against-
> live-code* distillation — every line number below was read this session, not
> carried over. Where RESEARCH and live code agree, the planner should treat the
> live excerpt here as authoritative. **No `src/` changes.** The only files written
> are the six listed; all other access was read-only.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/async/conftest.py` (MODIFY) | fixture (test) | request-response (replay) | `duckdb_async_pool` @ `conftest.py:75-94` + `TestSnowflakeCassetteLeg` @ `test_async_lifecycle.py:126-161` | exact |
| `tests/_async_harness/guard.py` (MODIFY) | utility (AST guard) | transform (source-scan) | `_GuardVisitor` + `scan_async_package` @ `guard.py:49-218` | exact |
| `tests/async/test_matrix_*.py` (NEW) | test | request-response (read-path) | `TestHappyPath` @ `test_async_lifecycle.py:40+` + cassette leg @ `:126-161` | exact |
| `tests/async/test_stability_*.py` (NEW) | test | batch (looped CRUD) | `TestEdge21ArrowLifetime` @ `test_edge_resource.py:27-72` | role+flow match |
| `tests/async/test_limiter_stress_*.py` (NEW) | test | event-driven (gated flood) | `TestEdge12ConcurrencyBound` @ `test_edge_limiter.py:269-318` | exact |
| `tests/async/test_meta_guard_*.py` (NEW) | test (meta) | transform (assert scan==[]) | `TestAsyncGuard` / `TestRealAsyncPackage` @ `test_async_guard.py:85-186` | exact |

## Pattern Assignments

---

### `tests/async/conftest.py` (MODIFY — add `snowflake_async_pool`, D-27-04)

**Analog A — the fixture shape to mirror:** `duckdb_async_pool` @ `tests/async/conftest.py:75-94`
```python
@pytest.fixture
async def duckdb_async_pool() -> AsyncIterator[AsyncPool]:
    tmpdir = tempfile.mkdtemp()
    pool = create_async_pool(DuckDBConfig(database=str(Path(tmpdir) / "async_edge.db")))
    try:
        yield pool
    finally:
        await pool.close()
```
Copy: async generator fixture, `try/yield/finally` teardown, `AsyncIterator[AsyncPool]`
return annotation, Google-style docstring with a `Yields:` section.

**Analog B — the cassette body to distill into the fixture:** `TestSnowflakeCassetteLeg` @ `tests/async/test_async_lifecycle.py:126-161`
```python
pytest.importorskip(
    "adbc_driver_snowflake.dbapi",
    reason="Snowflake driver not installed; cassette leg skipped",
)
if not (_CASSETTE_ROOT / "snowflake_arrow_round_trip").exists():
    pytest.skip("snowflake_arrow_round_trip cassette absent")
os.environ.setdefault("SNOWFLAKE_ACCOUNT", "replay-account")
pool = create_async_pool(SnowflakeConfig())  # type: ignore[call-arg]
try:
    ...
finally:
    await close_async_pool(pool)
```

**Cassette-root constant** to add (mirror `test_async_lifecycle.py:37`):
```python
_CASSETTE_ROOT = Path(__file__).parent.parent / "cassettes"
```

**New imports needed in conftest** (current imports are at `conftest.py:27-43`; add):
`import os`, `SnowflakeConfig`, `close_async_pool` from `adbc_poolhouse`.

**Landmine (D-27-06 / RESEARCH Pitfall 3):** the fixture ALONE does not mount the
cassette. The *consuming test* must carry `@pytest.mark.snowflake` AND
`@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")` — the `adbc_cassette`
marker (read from `adbc_cassette_dir` in `pyproject.toml`) is what mounts replay.
Without it the fixture attempts a real connection.

**Docs gate:** this is a public harness fixture → Google-style docstring with a
`Yields:` section, mirroring `duckdb_async_pool`'s.

---

### `tests/async/test_matrix_*.py` (NEW — TEST-01/02 read-path matrix)

**Analog:** `TestHappyPath.test_execute_fetch_arrow_table` @ `test_async_lifecycle.py:40+`
(the DuckDB round trip) crossed with the cassette leg @ `:126-161`.

**Core read-path body** (the surface to parametrize — connect → execute → fetch → checkin):
```python
async with await pool.connect() as conn:
    cur = conn.cursor()
    await cur.execute("SELECT 1 AS n, 'hello' AS s")
    table = await cur.fetch_arrow_table()
    assert table.num_rows == 1
assert pool._pool.checkedout() == 0   # checkin assertion (see test_edge_resource.py:48)
```

**Backend-axis parametrization** (RESEARCH Pattern 2 — parametrize over the *pool
fixture name*, request lazily so the Snowflake leg skips independently):
```python
@pytest.mark.anyio
@pytest.mark.parametrize("pool_fixture", [
    "duckdb_async_pool",
    pytest.param("snowflake_async_pool",
                 marks=[pytest.mark.snowflake,
                        pytest.mark.adbc_cassette("snowflake_arrow_round_trip")]),
])
async def test_readpath_backend_generic(pool_fixture, request):
    pool = request.getfixturevalue(pool_fixture)  # lazy: snowflake leg skips cleanly
    ...
```

**Free axis:** `{asyncio, trio}` comes from `@pytest.mark.anyio` + the
`anyio_backend` fixture (`conftest.py:46-72`). Do NOT hand-roll a backend loop.

**Landmines:**
- Cassette `ReplayCursor` is **read-path only** — no `adbc_cancel`, cannot block-gate.
  Keep this file to happy-path SELECT + `fetch_arrow_table` only (D-27-05/06).
- Carry BOTH snowflake markers on the cassette param (RESEARCH Pitfall 3).

---

### `tests/async/test_stability_*.py` (NEW — TEST-03 Arrow allocator + reset count)

**Analog:** `TestEdge21ArrowLifetime` @ `tests/async/test_edge_resource.py:27-72`
— same real DuckDB pool, same `execute → fetch_arrow_table → checkin → del tbl`
loop, same `checkedout() == 0` assertion. Extend the loop count from
`_LIFETIME_LOOPS = 5` (`:24`) to `_N = 100` (D-27-07) and add the two new metrics.

**Loop body to copy** (`test_edge_resource.py:41-52`):
```python
for i in range(_N):
    async with await duckdb_async_pool.connect() as conn:
        cur = conn.cursor()
        await cur.execute(f"SELECT {i} AS n")
        tbl = await cur.fetch_arrow_table()
        del tbl
    # checkin fired the reset event here
```

**New metric 1 — allocator delta (D-27-07):** verified deterministic this session
(`0 → 8000 → 0`). `import pyarrow; import gc`:
```python
gc.collect()
baseline = pyarrow.total_allocated_bytes()
... loop ...
gc.collect()
assert pyarrow.total_allocated_bytes() - baseline == 0
```
Fallback if exact-zero flakes on a build: `delta < single_table_bytes` (RESEARCH Pitfall 5).

**New metric 2 — reset-event count (D-27-08, ACONN-06):** count the pool `reset`
event WITHOUT touching frozen `src/` (RESEARCH "Don't Hand-Roll"):
```python
import sqlalchemy
reset_count = 0
def _on_reset(dbapi_conn, conn_record, reset_state):
    nonlocal reset_count
    reset_count += 1
sqlalchemy.event.listen(duckdb_async_pool._pool, "reset", _on_reset)
...
assert reset_count == _N   # the _release_arrow_allocators path (_pool_factory.py:106,407) fired once per checkin
```

**Run ×{asyncio, trio}** via `@pytest.mark.anyio` (D-27-09). `del anyio_backend_name`
if requested-but-unused, per the existing convention (`test_edge_resource.py:57`).

---

### `tests/async/test_limiter_stress_*.py` (NEW — TEST-04 flood + smoke)

**Analog:** `TestEdge12ConcurrencyBound.test_running_max_equals_bound_under_flood`
@ `tests/async/test_edge_limiter.py:269-318` — this is the **verbatim** pattern.

**Helper to copy** (`test_edge_limiter.py:52-56`):
```python
def _stub_conn_on(limiter: anyio.CapacityLimiter) -> tuple[AsyncConnection, BlockingStubConnection]:
    stub_conn = BlockingStubConnection()
    async_conn = AsyncConnection(stub_conn, limiter)  # type: ignore[arg-type]
    return async_conn, stub_conn
```

**Cross-package helper import** (`async` is a reserved word → importlib, `test_edge_limiter.py:42-46`):
```python
_helpers = importlib.import_module("tests.async._edge_helpers")
await_inside = _helpers.await_inside
real_clock_watchdog = _helpers.real_clock_watchdog
```

**Flood body** (`test_edge_limiter.py:284-317`):
```python
bound = pool_size + max_overflow   # use real default 8 (5+3) per Open Question 1
flood = bound * 4
limiter = anyio.CapacityLimiter(bound)
pairs = [_stub_conn_on(limiter) for _ in range(flood)]
cursors = [conn.cursor() for conn, _ in pairs]
stub_cursors = [stub.cursors[0] for _, stub in pairs]
with real_clock_watchdog(stub_cursors) as watchdog:
    async with anyio.create_task_group() as tg:
        for i, cur in enumerate(cursors):
            tg.start_soon(functools.partial(cur.execute, f"SELECT {i}"))
        try:
            await await_inside(lambda: limiter.borrowed_tokens == bound)
            assert limiter.borrowed_tokens == bound        # never exceeds (running-max == bound)
        finally:
            for cur in stub_cursors:
                cur.close()                                 # terminal drain — NOT release()
            await await_inside(lambda: limiter.borrowed_tokens == 0)  # no starvation
assert watchdog[0] is False, "watchdog tripped: a worker hung"
assert limiter.borrowed_tokens == 0
```

**Two load-bearing landmines (both verified against `test_edge_limiter.py:295-316`
+ `stubs.py:302-324`):**
1. **Drain with `close()`, never `release()`.** `close()` latches the sticky
   `_closed` flag so `_block` short-circuits even for a worker that has not yet
   entered (`stubs.py:302-315`); a plain `release()` only sets the transient event
   and strands a late worker (the Phase 26 lost-wakeup). `release()` is test-only
   happy-path (`stubs.py:317-324`).
2. **Watchdog = `real_clock_watchdog`, never `anyio.fail_after`.** The watchdog is
   a wall-clock side thread (`_edge_helpers.py:38-78`). `anyio.fail_after`
   autojumps to its own deadline under the trio `MockClock(autojump_threshold=0)`
   the instant workers block off-loop (D-27-11).

**Real-DuckDB smoke flood (D-27-10):** a separate, smaller test — flood `4×bound`
real `await pool.connect() → execute → fetch` tasks against `duckdb_async_pool`,
assert all complete and `checkedout() == 0`. Pattern source: combine the
`TestEdge09TokenAccounting` real-pool body (`test_edge_limiter.py:63-70`) with a
`create_task_group` flood; wrap in `real_clock_watchdog([])` (empty list — no stubs
to break open, see `test_edge_limiter.py:257`).

**×20 loop-stability gate** (project rule, RESEARCH Validation §): run this file in
a 20× loop, 0 hangs, using `rc=$?` + grep "passed" (zsh `!` landmine, MEMORY) —
NOT `if ! pytest`.

---

### `tests/async/test_meta_guard_*.py` (NEW) + `tests/_async_harness/guard.py` (MODIFY)

**Analog for the guard callables:** `_GuardVisitor` + `scan_async_package`
@ `tests/_async_harness/guard.py:49-218` (pure-stdlib AST visitor, `Finding`
dataclass `:28-47`, tolerant `rglob` + absent-root no-op `:193-218`).

**Analog for the meta-test:** `TestAsyncGuard` / `TestRealAsyncPackage`
@ `tests/test_async_guard.py:85-186` — plain SYNC tests (no `@pytest.mark.anyio`;
the guard needs no event loop, `:11-13`), assert `scan_* == []` / count rules.

**Two NEW callables to add alongside `scan_async_package`:**

**Guard A — `scan_async_test_hygiene(root)` (EDGE-27, D-27-01).** Reuse the existing
`visit_Import`/`visit_ImportFrom` asyncio logic (`guard.py:56-82`) and add, per
`async def test_*`:
- flag any `import asyncio` / `from asyncio import ...` (reuse verbatim);
- flag any `@pytest.mark.asyncio` decorator (`ast.Attribute` chain on a `FunctionDef`);
- flag any `async def test_*` lacking `@pytest.mark.anyio`.
**Critical (RESEARCH Pitfall 2):** the "anyio-parametrized" signal is the PRESENCE
of `@pytest.mark.anyio`, NOT a literal `anyio_backend` argument. Most existing
tests (e.g. `test_async_lifecycle.py`) get the axis via the marker + a plain async
fixture, so requiring the literal arg would false-positive on hardened tests.

**Guard B — `scan_for_positive_sleep(root)` (EDGE-30, discretion).** New
`ast.NodeVisitor` matching `<mod>.sleep(...)` / bare `sleep(...)` whose first
positional arg is a numeric `ast.Constant > 0`. **ALLOW** `sleep(0)`, `sleep(0.0)`,
and any non-literal arg (`sleep(deadline)`). RESEARCH Pattern 5 gives the exact
visitor:
```python
def _is_sleep_call(func):
    if isinstance(func, ast.Attribute) and func.attr == "sleep":
        return True
    return isinstance(func, ast.Name) and func.id == "sleep"
# in visit_Call: if _is_sleep_call(node.func) and node.args:
#     arg = node.args[0]
#     if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)) and arg.value > 0: -> Finding
```

**Meta-test body** (mirror `test_async_guard.py` sync style):
```python
from tests._async_harness.guard import scan_async_test_hygiene, scan_for_positive_sleep

def test_async_test_package_hygiene():
    assert scan_async_test_hygiene("tests/async") == []

def test_no_positive_sleep_in_async_tests():
    assert scan_for_positive_sleep("tests/async") == []
```

**Landmines:**
- **EDGE-30 scope = `tests/async/` ONLY** (RESEARCH Anti-Pattern + Pitfall 1).
  The harness has DELIBERATE positive sleeps under virtual clocks
  (`tests/_async_harness/conftest.py:71` `anyio.sleep(1)`, `clock.py:68`
  `anyio.sleep(3600)`). Scanning the harness root would false-positive.
- **Allow `sleep(0)`** — `await_inside` (`_edge_helpers.py:101`) and several EDGE
  tests use `anyio.sleep(0)` checkpoints (EDGE-26). Banning bare `sleep(` breaks them.
- **D-27-02:** do NOT rewrite the ~10 existing EDGE files. Fix ONLY a file the
  meta-scan actually flags. A blanket sweep risks reintroducing the lost-wakeup /
  MockClock landmines those tests were hardened against.
- **Docs gate:** both new callables are public harness symbols → Google-style
  docstrings (Args/Returns + an `Example:` block), mirroring `scan_async_package`'s
  thorough docstring (`guard.py:136-192`). Add `Finding.rule` ids for the two new
  rules to the `Finding` docstring (`guard.py:28-47`).

---

## Shared Patterns

### Dual-backend axis (asyncio/trio) — TEST-01, every async test
**Source:** `anyio_backend` fixture @ `tests/async/conftest.py:46-72`
**Apply to:** every new async test file (matrix, stability, limiter-stress).
```python
@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request):
    if request.param == "trio":
        return ("trio", {"clock": trio.testing.MockClock(autojump_threshold=0)})
    return "asyncio"
```
Tests opt in with `@pytest.mark.anyio`; request `anyio_backend_name` only when the
backend string is needed, then `del anyio_backend_name` (convention seen across
the EDGE suite). Do NOT hoist this fixture above `tests/async/` (breaks PKG-04).

### Real-clock watchdog — every off-loop gating test (TEST-04)
**Source:** `real_clock_watchdog` @ `tests/async/_edge_helpers.py:38-78`
**Apply to:** any test that gates a worker inside a stub. Wall-clock side thread
that `close()`s stubs on overrun; yields a `[bool]` you assert is `False`. NEVER
substitute `anyio.fail_after` for off-loop gating.

### Saturation poll — gated floods (TEST-04)
**Source:** `await_inside` @ `tests/async/_edge_helpers.py:81-102`
**Apply to:** waiting for `limiter.borrowed_tokens == bound` / `== 0`. Pure
`anyio.sleep(0)` checkpoints — settles under both legs, no wall-clock.

### Blocking stub fakes — gated mechanics (TEST-04)
**Source:** `BlockingStubConnection` / `BlockingStubCursor` @ `tests/_async_harness/stubs.py:61,327`
**Apply to:** the limiter flood (DuckDB+stub only, D-27-06). Sticky `_closed` /
`_cancelled` latches (`stubs.py:159-167`) survive the Linux lost-wakeup. Reach the
cursor via `stub_conn.cursors[0]`. Counters: `execute_call_count`,
`adbc_cancel_call_count`, `close_call_count`.

### Pure-stdlib AST guard — EDGE-27/30
**Source:** `_GuardVisitor` + `scan_async_package` @ `tests/_async_harness/guard.py:49-218`
**Apply to:** both new guard callables. No `anyio`/`trio`/`adbc_poolhouse` import,
read-only `ast.parse` walk, absent-root → `[]`, return `list[Finding]`.

### Checkin assertion — read-path + stability tests
**Source:** `assert pool._pool.checkedout() == 0` @ `test_edge_resource.py:48`
**Apply to:** matrix read-path and the smoke flood, to prove the connection
returned to the pool.

### CI wiring (Claude's discretion)
**Source:** `.github/workflows/ci.yml` — `quality` job (`:13`, runs full `pytest`,
auto-includes new `tests/async/` files) and `sync-no-anyio` job (`:49`, runs
`pytest tests/ --ignore=tests/async --ignore=tests/_async_harness`, `:87`).
**Apply to:** new tests need NO workflow edit — they join `quality` automatically
and are already excluded from `sync-no-anyio` by the directory ignore. Verify only;
do not add them to the no-anyio job (they import anyio at collection).

## No Analog Found

None. Every file maps to a verified in-repo analog. The only genuinely *new* code
is the two AST guard callables, and even those extend the existing `_GuardVisitor`
pattern one-for-one.

## Metadata

**Analog search scope:** `tests/async/`, `tests/_async_harness/`, `tests/test_async_guard.py`, `.github/workflows/ci.yml`
**Files read this session:** `tests/async/conftest.py`, `tests/_async_harness/guard.py`, `tests/async/test_edge_limiter.py`, `tests/async/_edge_helpers.py`, `tests/async/test_edge_resource.py`, `tests/test_async_guard.py`, `tests/async/test_async_lifecycle.py` (targeted), `tests/_async_harness/stubs.py` (targeted), `.github/workflows/ci.yml` (grep)
**Pattern extraction date:** 2026-06-28
