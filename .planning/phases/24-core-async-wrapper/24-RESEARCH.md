# Phase 24: Core Async Wrapper - Research

**Researched:** 2026-06-27
**Domain:** anyio thread-offload async wrapper over a sync SQLAlchemy `QueuePool` + ADBC dbapi
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-24-01 — Limiter token model: TRANSIENT, borrowed per-offload (NOT held for connection lifetime).**
Every offloaded call (`connect`, `execute`, `executemany`, `fetch*`, `fetch_arrow_table`, `commit`,
`rollback`, `close`) passes `limiter=pool._limiter` to `anyio.to_thread.run_sync` and borrows a token
**only for the duration of that one call**. An `AsyncConnection` holds **no** limiter token between calls.
One dedicated `anyio.CapacityLimiter(pool_size + max_overflow)` per pool. Safety is by construction: one
`AsyncConnection` is used serially (≤1 offload in flight per connection), and checked-out connections are
capped at `pool_size + max_overflow` by the sync `QueuePool`, so concurrent in-connection offloads ≤ bound
= total tokens. **Option B (hold a token from checkout to checkin) is REJECTED — it deadlocks (EDGE-11).**
Planner note: ARCHITECTURE.md's phrase *"a connection you hold already owns a token"* must be read as
"owns a **checkout slot**," NOT a retained limiter token.

**D-24-02 — EDGE-09 is SPLIT across Phase 24 / Phase 25.**
- Phase 24 owns, fully green: EDGE-09 **success** + **error** legs (`borrowed_tokens == 0` after a normal
  return AND after an `AdbcError`), and **EDGE-10** in full (cancel while *queued waiting to acquire* a
  token on a saturated limiter — pure async-layer behaviour, no driver touched).
- Phase 25 owns: EDGE-09's **cancel-mid-block** leg (rides on `adbc_cancel` wiring).

**D-24-03 — Connection aliasing: REJECT with a typed `ConnectionBusyError(PoolhouseError)` (NO per-connection lock).**
Each `AsyncConnection` carries a cheap `_in_use` flag set around each offload; a second concurrent entry
raises `ConnectionBusyError` immediately. The exception MUST inherit `PoolhouseError` and be exported.
**EDGE-16 is DROPPED** (was conditional on a lock shipping). EDGE-15 is satisfied by its reject form:
assert the second concurrent caller raises `ConnectionBusyError`, no concurrency-violation flag is set,
and `checkedout()` stays correct.

**D-24-04 — "13 backends" verified by STRUCTURAL genericity, not 13 live runs.**
- Genericity (binding): zero backend-specific code in `_async/` — wrappers touch only the `WarehouseConfig`
  Protocol and the sync `QueuePool`. Proved by construction + a static check (the Phase 23 `scan_async_package`
  AST guard, extended to also assert no backend names / per-backend branching in `_async/`).
- Real-driver smoke: DuckDB (real in-proc driver — needed for EDGE-21's real `pyarrow.Table`) + the
  Snowflake `pytest-adbc-replay` cassette. The remaining 11 backends inherit coverage transitively via the
  Protocol + existing sync suite. A live multi-backend matrix is explicitly OUT (deferred, do not imply covered).

### Claude's Discretion

Everything except the four load-bearing decisions: method-by-method offload structure, the `_in_use` flag
mechanics, exact exception name/message, overload shapes, file-internal helpers — within ARCHITECTURE.md's
wrap-and-offload pattern and the Phase 23 harness contract.

### Deferred Ideas (OUT OF SCOPE)

- **Cancellation machinery** (`adbc_cancel`/invalidate/`CancelScope(shield=True)`, EDGE-01..07/19/28/29) → Phase 25.
- **Streaming `RecordBatchReader`** results → v1.4.x. `fetch_arrow_table` returns a fully-materialized
  `pyarrow.Table` only.
- **EDGE-09 cancel-mid-block leg** → Phase 25.
- **EDGE-16** (cancel-bypasses-lock) → DROPPED (no lock ships).
- **Live 13-backend smoke matrix** → separate future phase needing CI infra.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | Single internal offload helper routes every blocking call through `to_thread.run_sync` with explicit `limiter=`; no bare `to_thread` | Pattern: `_async/_offload.py` single `offload(fn, *args, limiter=)` helper. AST guard already enforces (test_async_guard) |
| CORE-02 | Each pool owns a dedicated `CapacityLimiter(pool_size + max_overflow)`; never the shared 40-token default | `AsyncPool.__init__` builds the limiter; verified API `anyio.CapacityLimiter(n)` |
| CORE-03 | Async package uses anyio only — `import asyncio` banned, lint-enforced | `scan_async_package` rule `banned-asyncio-import` already implemented (guard.py) |
| CORE-04 | Generic over all 13 backends via `WarehouseConfig` Protocol — no per-backend async code | Reuse `_create_pool_impl` verbatim; D-24-04 static check |
| APOOL-01 | `create_async_pool(config, ...)` mirrors `create_pool` signature + overloads | Mirror the 3-overload shape of `create_pool` (verified in _pool_factory.py) |
| APOOL-02 | `await close_async_pool(pool)` offloaded | Offload `close_pool(pool)` (sync helper exists) |
| APOOL-03 | `async with managed_async_pool(config, ...)` create-and-auto-close, close path shielded | `@asynccontextmanager` + shielded close offload |
| ACONN-01 | `await pool.connect()` → `AsyncConnection`, checkout offloaded through limiter | Offload `sync_pool.connect()` |
| ACONN-02 | `AsyncConnection` async ctx mgr; checkin shielded | `__aexit__` offloads `fairy.close()` inside `CancelScope(shield=True)` |
| ACONN-03 | `conn.cursor()` returns `AsyncCursor` synchronously (no `await`) | dbapi `connection.cursor()` is cheap/sync; mirror psycopg3 convention |
| ACONN-04 | `await conn.commit()` / `await conn.rollback()` offloaded | Offload fairy/dbapi `commit`/`rollback` |
| ACONN-05 | `await conn.close()` offloaded + shielded | Offload `fairy.close()` |
| ACONN-06 | Async checkin routes through existing reset path so `_release_arrow_allocators` fires | `fairy.close()` → pool `reset` event fires unchanged (verified) |
| ACUR-01 | `await cursor.execute(operation, parameters=None)` | Offload dbapi `cursor.execute` |
| ACUR-02 | `await cursor.executemany(operation, seq_of_parameters)` | Offload dbapi `cursor.executemany` |
| ACUR-03 | `await cursor.fetchone()/fetchmany(size=None)/fetchall()` | Offload dbapi fetch methods |
| ACUR-04 | `await cursor.fetch_arrow_table()` → `pyarrow.Table` | Offload dbapi `fetch_arrow_table` (returns materialized `pyarrow.Table` — verified) |
| ACUR-05 | `AsyncCursor` async ctx mgr; `close()` offloaded + shielded | `__aexit__` offloads `cursor.close()` shielded |
| ACUR-06 | ADBC `Error` subclasses propagate unchanged across thread boundary | `to_thread.run_sync` re-raises worker exception; do NOT wrap (EDGE-17) |
| ACUR-07 | Sync no-I/O properties (`description`, `rowcount`, `arraysize`) pass through without `await` | Plain `@property` passthrough to dbapi cursor (verified these are pure sync) |
| EDGE-09 | Token borrowed-then-released once across success + error (×50 loop, `borrowed_tokens==0`) | `pool._limiter.borrowed_tokens` observable; cancel-leg → Phase 25 (D-24-02) |
| EDGE-10 | Token not leaked when acquire cancelled while queued on saturated limiter | Pure async-layer test; saturate limiter, cancel a queued offload |
| EDGE-11 | Holding a connection + awaiting a second offload does not self-deadlock | Safe-by-construction under D-24-01 (transient token); watchdog test |
| EDGE-12 | In-flight concurrency strictly bounded == pool_size+max_overflow under 4× flood | Stub counter + `max_concurrent_in_execute` (already in BlockingStubCursor) |
| EDGE-15 | Two tasks sharing one conn/cursor raise `ConnectionBusyError`; checkedout() correct | `_in_use` flag (D-24-03) |
| EDGE-17 | ADBC error propagates with exact type + traceback intact | No re-wrap in offload helper |
| EDGE-18 | Exception in `__aenter__`/post-checkout leaks no connection (checkedout()==0 over N) | Reclaim fairy on failure in `__aenter__` |
| EDGE-21 | Materialized `fetch_arrow_table` valid after checkin; result is `pyarrow.Table` not live reader | DuckDB real driver; assert post-checkin read |
| EDGE-25 | Every blocking call off the loop thread + lint (no asyncio, no bare to_thread) | thread-id capture via stub `execute_thread_ids` + `scan_async_package` |
| EDGE-26 | Long blocked offload does not starve loop — concurrent coroutine advances | stub block + concurrent `sleep(0)` counter |
</phase_requirements>

## Summary

Phase 24 builds the `_async/` package: an `AsyncPool` / `AsyncConnection` / `AsyncCursor` surface plus a
single `offload()` helper and a per-pool `anyio.CapacityLimiter`, wrapping the **already-shipped, unchanged**
sync `QueuePool` (`_create_pool_impl`) and ADBC dbapi cursor. The hard architectural work is already
settled in `.planning/research/ARCHITECTURE.md` and the four locked CONTEXT decisions; this phase is almost
entirely **wrap-and-offload glue** plus a focused set of deterministic EDGE tests built on the Phase 23
harness. There is no novel concurrency primitive to invent — anyio's `to_thread.run_sync(fn, limiter=...)`
plus the sync pool's existing checkout/reset machinery do all the heavy lifting.

The two genuinely new pieces of *mechanism* are (1) the transient-token offload discipline (D-24-01: every
offload borrows a token for exactly one call, never holds one across calls — this is what makes EDGE-11
deadlock-free by construction) and (2) the `_in_use` flag on `AsyncConnection` that turns concurrent aliasing
into an immediate `ConnectionBusyError` instead of a per-connection lock (D-24-03). Everything else —
checkout, checkin, the Arrow reset event, the 13-backend config dispatch — is reused verbatim from the sync
layer through the `WarehouseConfig` Protocol, which is exactly what D-24-04's structural-genericity claim rests on.

The largest *risk* in this phase is not the wrappers — it is the **test harness reuse**. The Phase 23 review
left WR-01 (re-armable cursor gate) reverted because the `entered`-before-block timing made a naive re-arm
deadlock. Phase 24 needs execute-then-fetch on ONE cursor, which requires a re-armable gate, so this phase
MUST land the `entered`-timing redesign (D-CF-01) together with the re-arm. The `_await_inside` bounded-poll
pattern (commit `943c074`) is the proven safe interim; the cleaner fix is to fire `entered` *after* the worker
is inside the blocked section. MEMORY also warns: run async/concurrency tests in a loop (×N), never single-shot
— a ~33% deadlock slipped past a single "passed" run in Phase 23.

**Primary recommendation:** Build the `_async/` package in the ARCHITECTURE.md build order (offload helper +
factory + `AsyncPool`/limiter → connection/cursor wrappers → EDGE tests → docs), implement the transient-token
discipline and `_in_use` flag exactly as the locked decisions specify, land the harness `entered`-redesign +
re-armable gate as a Wave-0 prerequisite before any execute-then-fetch EDGE test, and gate every concurrency
test with a `fail_after` watchdog run in a ×N loop.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Pool construction / config dispatch | Sync core (`_create_pool_impl`) | — | Reused verbatim; async never re-derives driver paths (D-24-04, CORE-04) |
| Checkout queueing / timeout / recycle | Sync `QueuePool` | Async offload | Battle-tested; async only offloads the blocking `connect()` (ARCHITECTURE Q2) |
| Arrow cleanup on checkin | Sync `reset` event (`_release_arrow_allocators`) | — | Pool-level event fires identically for async-checked-out conns (ACONN-06) |
| Thread budget / backpressure | Async `CapacityLimiter` | — | Per-pool, sized to `pool_size+max_overflow`; not the pool's checkout queue (CORE-02) |
| Off-loop dispatch of blocking calls | Async `offload()` helper | — | Single chokepoint for the `limiter=` rule (CORE-01, EDGE-25) |
| Concurrent-aliasing rejection | Async `AsyncConnection._in_use` flag | — | Loud `ConnectionBusyError`, no lock (D-24-03, EDGE-15) |
| Result materialization | ADBC dbapi (`fetch_arrow_table`) | Async offload | dbapi returns a self-owning `pyarrow.Table`, safe after checkin (EDGE-21) |
| Cancellation (`adbc_cancel`/invalidate) | **Phase 25** | — | OUT of Phase 24 scope (D-24-02) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anyio` | `>=4.13` (installed: 4.x) | `to_thread.run_sync`, `CapacityLimiter`, cancel scopes; asyncio+trio neutral | Project-mandated neutrality constraint; already a dev dep `[CITED: pyproject.toml]` |
| `sqlalchemy` | `>=2.0.0` (installed 2.0.x) | sync `QueuePool` being wrapped (unchanged) | Already the sync pool backend `[CITED: pyproject.toml]` |
| `adbc-driver-manager` | `>=1.8.0` | dbapi `Cursor`/`Connection` surface being offloaded | Already core dep; surface verified directly `[VERIFIED: dbapi.py source]` |
| `pyarrow` | `>=23.0.1` (dev) | `fetch_arrow_table` return type (`pyarrow.Table`) | dbapi `fetch_arrow_table` returns `pyarrow.Table` `[VERIFIED: dbapi.py:1340]` |

### Supporting (test/dev only)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `trio` | `>=0.31` | second anyio backend for dual-backend tests | every async test parametrized over both |
| `aiotools` | `>=2.2` | asyncio-leg virtual clock (`VirtualClock().patch_loop()`) | timeout/deadline tests (mostly Phase 25; harness already wires it) |
| `pytest-adbc-replay` | `>=1.0.0a3` | Snowflake cassette replay (driver-agnostic leg of D-24-04) | backend-generic smoke without live creds |
| `duckdb` / `adbc-driver-duckdb` | (via `[duckdb]` extra) | real in-proc driver for EDGE-21 Arrow path | the one real-driver leg of D-24-04 |
| `basedpyright` | `>=1.38.0` | strict type check of new wrappers | CI gate; strict mode `[CITED: pyproject.toml]` |
| `ruff` | `>=0.15.1` | lint/format (D-docstrings rules on) | CI gate |

### Packaging
- The `[async]` extra adds **`anyio>=4.0` only** (ARCHITECTURE.md). `anyio` is currently a *dev* dep — Phase 24
  must add the `[async]` optional-extra group to `pyproject.toml` so consumers install it explicitly, and keep
  the sync path importable with anyio absent (PEP 562 lazy `__getattr__` on package `__init__`).

**Installation (already satisfied in the dev env):**
```bash
# Dev env already has anyio, trio, aiotools, pyarrow, duckdb via dependency-groups.
# Production-facing change: declare the [async] extra in pyproject.toml.
uv sync   # picks up the dev group
```

**Version verification:** `anyio.CapacityLimiter` API confirmed live in the venv (see Package Legitimacy
Audit). `pyarrow.Table` return type confirmed from `adbc_driver_manager/dbapi.py` source.

## Package Legitimacy Audit

> No NEW external packages are introduced by Phase 24. The `[async]` extra declares `anyio`, which is already
> a vetted dependency. The audit below records the verification of the load-bearing libraries.

| Package | Registry | Source Repo | Verdict | Disposition |
|---------|----------|-------------|---------|-------------|
| `anyio` | PyPI | github.com/agronholm/anyio | OK | Approved — already dev dep; `CapacityLimiter`/`to_thread.run_sync` API verified live in venv `[VERIFIED]` |
| `sqlalchemy` | PyPI | github.com/sqlalchemy/sqlalchemy | OK | Approved — existing core dep |
| `adbc-driver-manager` | PyPI | github.com/apache/arrow-adbc | OK | Approved — existing core dep |
| `pyarrow` | PyPI | github.com/apache/arrow | OK | Approved — existing dev dep |
| `trio` / `aiotools` / `pytest-adbc-replay` | PyPI | (existing dev deps) | OK | Approved — existing dev deps |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

*Note: the package-legitimacy seam was not re-run because Phase 24 adds no new third-party package; all
libraries are pre-existing, vetted dependencies whose live API surface was verified directly in this session.*

## Architecture Patterns

### System Architecture Diagram

```
  create_async_pool(cfg)  managed_async_pool(cfg)  close_async_pool(pool)
        │                        │                         │
        └──────────┬─────────────┴─────────────────────────┘
                   ▼
            AsyncPool
            ├─ _pool: sync QueuePool   ◀── _create_pool_impl(cfg, ...)  [UNCHANGED sync core]
            └─ _limiter: CapacityLimiter(pool_size + max_overflow)
                   │
   await pool.connect() ── offload(_pool.connect, limiter) ─┐
                   ▼                                          │ (borrows 1 token for the
            AsyncConnection                                   │  duration of connect() only,
            ├─ _fairy: checked-out sync ConnectionFairy       │  then RELEASES — D-24-01)
            ├─ _limiter (shared, by ref)                      │
            └─ _in_use: bool   ◀── set around each offload (D-24-03)
                   │
       conn.cursor()  ──(SYNC, no await — ACONN-03)──▶ AsyncCursor
                   ▼
            AsyncCursor
            ├─ _cur: dbapi Cursor
            ├─ _conn: parent AsyncConnection (for _in_use + invalidate)
            └─ description/rowcount/arraysize  ──(SYNC @property passthrough — ACUR-07)
                   │
   await cur.execute(sql)  ── offload(_cur.execute, sql, params, limiter) ──▶ worker thread
   await cur.fetch_arrow_table() ── offload(_cur.fetch_arrow_table, limiter) ─▶ worker thread
                   │                                          (each offload: borrow→run→release 1 token)
                   ▼
            pyarrow.Table  (materialized, self-owning, safe after checkin — EDGE-21)
                   │
   async ctx exit ── offload(_fairy.close, limiter) inside CancelScope(shield=True) ──▶ checkin
                   │
                   ▼
            sync pool "reset" event ──▶ _release_arrow_allocators  [UNCHANGED — ACONN-06]
```

Data flow for the canonical use case (Goal): `create_async_pool` → `await pool.connect()` →
`conn.cursor()` (sync) → `await cur.execute(...)` → `await cur.fetch_arrow_table()` → checkin via
`__aexit__`. Each blocking step is one offload borrowing one transient token; cleanup is shielded.

### Recommended Project Structure
```
src/adbc_poolhouse/
├── __init__.py              # MODIFIED: PEP 562 lazy __getattr__ guards anyio import; export async names + ConnectionBusyError
├── _exceptions.py           # MODIFIED: add ConnectionBusyError(PoolhouseError)
├── _async/                  # NEW package (the entire async surface)
│   ├── __init__.py          # public: create_async_pool, managed_async_pool, close_async_pool
│   ├── _offload.py          # offload(fn, *args, limiter) — the SINGLE to_thread chokepoint (CORE-01)
│   ├── _factory.py          # async factory; calls _create_pool_impl, builds AsyncPool + limiter (CORE-04)
│   ├── _pool.py             # AsyncPool (connect/close offload; owns CapacityLimiter — CORE-02)
│   ├── _connection.py       # AsyncConnection (cursor() sync; commit/rollback/close offload; _in_use flag)
│   └── _cursor.py           # AsyncCursor (execute/executemany/fetch*/fetch_arrow_table offload; sync props)
tests/
├── _async_harness/          # REUSED from Phase 23 (stubs, gating, clock, guard) — extend in place
│   └── stubs.py             # WR-01 re-armable gate + D-CF-01 entered redesign land HERE
└── async/                   # NEW: Phase 24 EDGE tests + happy-path lifecycle (anyio, both backends)
    ├── conftest.py          # anyio_backend fixture (mirror tests/_async_harness/conftest.py) + DuckDB pool fixtures
    ├── test_async_lifecycle.py   # happy path: create→connect→execute→fetch_arrow_table→checkin (DuckDB)
    ├── test_edge_limiter.py      # EDGE-09/10/11/12
    ├── test_edge_aliasing.py     # EDGE-15
    ├── test_edge_exceptions.py   # EDGE-17/18
    ├── test_edge_resource.py     # EDGE-21
    └── test_edge_loophygiene.py  # EDGE-25/26 (EDGE-25 also extends the guard meta-test)
```

> **conftest placement is load-bearing** `[VERIFIED: tests/_async_harness/conftest.py docstring]`: the
> `anyio_backend` fixture must live in the directory that holds the async tests (or an ancestor of them
> but NOT an ancestor of the sync suite). Putting it in the root `tests/conftest.py` would drag the entire
> sync suite under the anyio plugin and break collection (and future PKG-04 "sync works with anyio absent").
> So `tests/async/` needs its OWN `conftest.py` defining `anyio_backend`, or the new tests go under
> `tests/_async_harness/`. **Recommendation:** give `tests/async/` its own conftest mirroring the harness one.

### Pattern 1: The single offload chokepoint (CORE-01 / EDGE-25)
**What:** One module-level helper that every wrapper method routes through. This is the only place
`to_thread.run_sync` is called, so the `limiter=` rule and `abandon_on_cancel=False` default are enforced once.
**When to use:** Every blocking boundary — checkout, execute, fetch*, commit/rollback, close.
```python
# src/adbc_poolhouse/_async/_offload.py
# Source: ARCHITECTURE.md Pattern 1 + Phase 23 gating.py (the limiter= shape the AST guard enforces)
from __future__ import annotations
from typing import TYPE_CHECKING
import anyio.to_thread

if TYPE_CHECKING:
    from collections.abc import Callable
    from anyio import CapacityLimiter

async def offload[T](fn: Callable[..., T], *args: object, limiter: CapacityLimiter) -> T:
    """Run one blocking sync call on a worker thread, borrowing one limiter token."""
    # abandon_on_cancel=False (default): Phase 24 does NOT abandon workers. The cancel
    # path (adbc_cancel + invalidate) is wired in Phase 25; here we keep the production
    # default so EDGE-09's success/error legs reflect the real offload (D-24-02).
    return await anyio.to_thread.run_sync(
        lambda: fn(*args), limiter=limiter, abandon_on_cancel=False
    )
```
> **Note for the planner:** `to_thread.run_sync` passes `*args` positionally to the target; a `lambda`
> closure (as above) or `functools.partial` is the idiomatic way to forward keyword-ish args. The AST guard
> only matches the literal `to_thread.run_sync(...)` attribute chain, so keep the call in this canonical
> form (not aliased) so the EDGE-25 lint actually sees it. `[VERIFIED: guard.py _is_to_thread_run_sync]`

### Pattern 2: Transient-token discipline (D-24-01, EDGE-09/11/12)
**What:** A token is borrowed by `to_thread.run_sync(limiter=...)` for the *duration of one call* and
released when that call returns. `AsyncConnection` holds **no** token between calls.
**Why it is correct:** `CapacityLimiter` borrows on entry to `run_sync` and releases on exit
`[VERIFIED: anyio CapacityLimiter live API]`. Because one `AsyncConnection` is used serially (≤1 in-flight
offload) and checkouts are capped at `pool_size+max_overflow`, simultaneous in-connection offloads ≤ bound =
total tokens. No hold-and-wait → no EDGE-11 deadlock.
**Anti-pattern (REJECTED, do NOT build):** acquiring a token at checkout and holding it to checkin (Option B).
N held tokens + N execute-needing-a-token = classic hold-and-wait deadlock.

### Pattern 3: `_in_use` flag for aliasing rejection (D-24-03, EDGE-15)
**What:** `AsyncConnection` carries `_in_use: bool`. Each offloading method checks-and-sets it before the
offload and clears it after (try/finally). A second concurrent entry sees `_in_use == True` and raises
`ConnectionBusyError`.
**When to use:** Around every offload on the connection AND its cursors (a cursor's `execute`/`fetch` must
also guard the parent connection's flag — concurrent cursor use is concurrent connection use).
```python
# src/adbc_poolhouse/_async/_connection.py (sketch — exact mechanics are Claude's discretion)
# Source: D-24-03; CONTEXT.md
class AsyncConnection:
    def _enter_offload(self) -> None:
        # Check-and-set must be atomic on the EVENT LOOP THREAD. Because the flag
        # is only ever read/written on the loop (never in the worker), no lock is
        # needed: the check and set happen in one synchronous, non-awaiting span.
        if self._in_use:
            raise ConnectionBusyError(
                "This connection is already executing in another task; an ADBC "
                "connection allows serialized but not concurrent access. Check out "
                "a separate connection per task."
            )
        self._in_use = True

    def _exit_offload(self) -> None:
        self._in_use = False
```
> **Critical correctness note for the planner:** the check-and-set is race-free *only* because it runs
> entirely on the loop thread with **no `await` between the check and the set**. Do NOT `await` (no
> `anyio.sleep(0)`, no offload) between reading and writing `_in_use`. Set the flag synchronously, THEN
> `await offload(...)`, THEN clear it in a `finally`. This is the whole reason a lock is unnecessary.

### Pattern 4: Shielded checkin (ACONN-02 / ACONN-05 / ACUR-05 / APOOL-03)
**What:** The checkin/close offload runs inside `anyio.CancelScope(shield=True)` so a cancellation landing
during `__aexit__` cannot abandon the connection (which would leak it from the pool forever).
```python
# Source: ARCHITECTURE.md + anyio cancellation docs (finalization needs a shielded scope)
async def __aexit__(self, *exc: object) -> None:
    with anyio.CancelScope(shield=True):
        await offload(self._fairy.close, limiter=self._limiter)
```
> The *full* cancel/invalidate machinery is Phase 25, but the **shield on checkin** is in scope for Phase 24
> (the requirements explicitly say "shielded"). EDGE-05 (cancel-during-checkin) is a Phase 25 test, but the
> shield itself ships now so the happy-path and EDGE-18 close paths are robust.

### Pattern 5: Sync cursor + sync properties (ACONN-03 / ACUR-07)
**What:** `conn.cursor()` returns an `AsyncCursor` **synchronously** (no `await`) — it only wraps the cheap
dbapi `connection.cursor()`. `description`, `rowcount`, `arraysize` are plain `@property` passthroughs.
**Why:** dbapi `cursor()` does no I/O (it constructs an `AdbcStatement`), and `description`/`rowcount`/
`arraysize` are pure attribute reads `[VERIFIED: dbapi.py:801-830]`. Offloading them would be wasteful and
would surprise users who expect the psycopg3 convention.
> **Subtle:** `description`/`rowcount` read state populated by the *last* `execute`. Since `execute` is
> offloaded and the connection is used serially, by the time the user reads the property the offload has
> returned and the state is consistent. No offload needed.

### Pattern 6: PEP 562 lazy import guard (packaging)
**What:** Package `__init__.py` exposes async names via `__getattr__` that imports `_async` on first access
and raises a clear `ImportError("install adbc-poolhouse[async]")` if `anyio` is missing.
**Why:** `import adbc_poolhouse` must stay zero-cost and anyio-free for sync users. `[CITED: ARCHITECTURE.md]`

### Anti-Patterns to Avoid
- **Bare `to_thread.run_sync(...)` without `limiter=`** — banned, AST-guarded (EDGE-25).
- **`import asyncio` anywhere in `_async/`** — banned, AST-guarded (CORE-03). Use `anyio` primitives only.
- **Holding a limiter token across calls (Option B)** — deadlocks (EDGE-11). Transient only.
- **Per-connection `anyio.Lock`** — explicitly rejected (D-24-03). Use the `_in_use` flag + loud error.
- **Re-wrapping ADBC errors** in the offload helper — breaks EDGE-17 type/traceback fidelity. Let them propagate.
- **`await` between the `_in_use` check and set** — reintroduces the race a lock would have guarded.
- **Forking `_create_pool_impl` / per-backend branches in `_async/`** — breaks CORE-04 / D-24-04 genericity.
- **`abandon_on_cancel=True` as a cancel mechanism** — leaks the busy worker. (Cancel is Phase 25 anyway.)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Checkout queueing / timeout / recycle | An anyio-native connection queue | The sync `QueuePool` offloaded via `to_thread` | Re-implements fairness/recycle/invalidation; ARCHITECTURE Q2 rejects it |
| Thread budget | Manual `acquire()`/`release()` around offloads | `to_thread.run_sync(limiter=...)` (borrow is automatic) | Manual acquire risks the cancel-while-waiting token-leak (EDGE-10); `run_sync` handles it |
| Config dispatch for 13 backends | Per-backend async branches | Reuse `_create_pool_impl()` through the Protocol | Duplicates the Family A/A'/B dispatch; breaks D-24-04 |
| Arrow cleanup on checkin | A new async cleanup path | The existing `reset` event (`_release_arrow_allocators`) | Fires for free on `fairy.close()` (ACONN-06) |
| Concurrent-aliasing serialization | A per-connection lock | The `_in_use` flag + `ConnectionBusyError` | A lock gives false comfort (interleaves statements in one txn); D-24-03 |
| Worker→loop signalling in tests | Hand-rolled thread events | The Phase 23 `run_blocking(..., entered=)` + `_await_inside` poll | Already verified-green; bridges `from_thread.run_sync(entered.set)` |
| Virtual clock for timeout tests | `time.sleep`/wall-clock | `virtual_clock()` facade (trio MockClock / aiotools patch_loop) | Already wired in the harness (clock.py); deterministic, no flake |
| Dual-backend parametrization | asyncio-only fixtures | The `anyio_backend` fixture (asyncio + trio) | Project neutrality constraint; harness conftest already provides it |

**Key insight:** This phase's correctness comes almost entirely from *reuse* — the sync pool, the reset
event, the anyio limiter's automatic borrow/release, and the Phase 23 harness. The only genuinely new
logic is the thin offload glue, the transient-token discipline, and the `_in_use` flag. Resist the urge to
build any concurrency primitive; anyio already has the right ones.

## Runtime State Inventory

> Phase 24 is **greenfield code addition** (a new `_async/` package + new tests + new exception + a
> `pyproject.toml` extra). It is NOT a rename/refactor/migration of existing runtime state. The five
> categories are answered explicitly below for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore keys/collections/IDs are renamed or migrated. The new async layer wraps the existing pool; no persisted state changes. | None |
| Live service config | None — no external service config (n8n, Datadog, Tailscale, etc.) references this code. | None |
| OS-registered state | None — no Task Scheduler / launchd / pm2 / systemd registrations involved. | None |
| Secrets/env vars | None — no secret keys or env var names added or renamed. (DB creds flow through existing `WarehouseConfig`.) | None |
| Build artifacts / installed packages | The `[async]` extra is added to `pyproject.toml`; after the edit run `uv sync` so `anyio` is declared as an extra (it is already present via the dev group, so no functional change in the dev env). `mkdocs` site rebuild needed for new docstrings (docs gate). | `uv sync`; `mkdocs build --strict` |

**Nothing found in the rename-sensitive categories** — verified by: this phase adds files, it does not move
or rename any existing symbol, datastore key, or registration.

## Common Pitfalls

### Pitfall 1: Re-arming the cursor gate naively deadlocks (the WR-01 trap)
**What goes wrong:** Phase 24 runs `execute` THEN `fetch_arrow_table` on ONE cursor, so the harness stub's
blocking gate must re-arm per call. The Phase 23 auto-fix replaced the sticky `threading.Event` with a
per-call latch and **deadlocked** (`test_max_concurrent` hung under full-suite scheduling).
**Why it happens:** `run_blocking` signals the loop-facing `entered` event *before* the worker enters the
blocked section (D-CF-01). A worker can register its fresh latch AFTER the test's `release()`, then wait on
a never-set latch forever. The old sticky event tolerated this (a late worker saw the already-set event); a
per-call latch does not. `[VERIFIED: 23-REVIEW-FIX.md WR-01]`
**How to avoid:** Land the re-arm **together with** the `entered`-after-block redesign — fire `entered`
*inside* the blocked section (via an `on_enter` callback the stub invokes inside `_block`, bridged to the
anyio event) so `await entered` becomes a true "inside execute" signal. Alternatively keep the
`_await_inside` bounded-`sleep(0)` poll after `await entered` and **always `release()` in a `finally`**.
**Warning signs:** A concurrency test passes in isolation but hangs under the full suite; a `fail_after`
watchdog tripping in CI.

### Pitfall 2: Single-shot test "passes" but hides a ~33% deadlock
**What goes wrong:** A concurrency test passes once in the closeout run, then deadlocks ~1-in-3 in CI.
**Why it happens:** Non-cancellable offloads (`abandon_on_cancel=False`) turn a missed/raced assertion into
a hung task group, and scheduling is nondeterministic. Phase 23's "307 passed" closeout got lucky.
`[VERIFIED: 23-REVIEW-FIX.md "Bonus"; MEMORY feedback_loop_test_flaky_concurrency]`
**How to avoid:** Run every async/concurrency test in a loop (e.g. `pytest ... --count` or a shell loop ×20)
during verification; require **0 hangs across N runs**, not a single green. Wrap concurrency-sensitive
bodies in `fail_after(watchdog)`.
**Warning signs:** Intermittent CI timeouts; "Task was destroyed but it is pending"; a test that only ever
fails under `-p xdist` or full-suite ordering.

### Pitfall 3: The `_in_use` check raced by an `await`
**What goes wrong:** Two tasks both pass the `_in_use == False` check before either sets it, so both proceed
— the aliasing rejection silently fails and two workers touch one connection.
**Why it happens:** Inserting any `await` (even `sleep(0)`, or doing the offload) between the check and the
set yields control to the other task at that checkpoint.
**How to avoid:** Make check-and-set a single synchronous span on the loop thread; only `await` the offload
*after* the flag is set; clear it in `finally`. No lock needed precisely because there is no checkpoint
between check and set. `[ASSUMED — standard event-loop single-threaded reasoning; validate with EDGE-15 test]`
**Warning signs:** EDGE-15 intermittently sees `max_concurrent_in_execute == 2` instead of a raised
`ConnectionBusyError`.

### Pitfall 4: Offloading the sync cursor properties
**What goes wrong:** Making `description`/`rowcount`/`arraysize`/`cursor()` async (returning coroutines)
breaks ACONN-03/ACUR-07 and surprises users (`await conn.cursor()` is wrong per the convention).
**Why it happens:** Over-applying "everything blocking gets offloaded" to calls that do no I/O.
**How to avoid:** `cursor()` and the three properties are pure sync passthroughs `[VERIFIED: dbapi.py]`.
Only calls that touch the driver/network get offloaded.
**Warning signs:** A "coroutine was never awaited" RuntimeWarning from a property access (EDGE-23 territory).

### Pitfall 5: The AST guard misses an aliased `to_thread` import
**What goes wrong:** `from anyio.to_thread import run_sync as rs; rs(fn)` slips past `scan_async_package`,
so a bare (limiter-less) offload could ship undetected.
**Why it happens:** The guard matches the `to_thread.run_sync` attribute chain, not a fully-aliased re-import
`[VERIFIED: guard.py docstring + test_alias_limitation_documented]`.
**How to avoid:** In `_async/`, **only** call offloads via the single `offload()` helper using the canonical
`anyio.to_thread.run_sync(...)` form (Pattern 1). Do not alias the import. The EDGE-25 meta-test asserts
`scan_async_package("src/adbc_poolhouse/_async/") == []`.
**Warning signs:** A code review finds an aliased import; the guard stays green but a bare offload exists.

### Pitfall 6: Hoisting `anyio_backend` into the root conftest
**What goes wrong:** Every sync test gets dragged under the anyio plugin → collection breaks; the future
"sync works with anyio absent" guarantee (PKG-04) is violated.
**Why it happens:** Putting the fixture in `tests/conftest.py` (an ancestor of the sync suite).
`[VERIFIED: tests/_async_harness/conftest.py docstring]`
**How to avoid:** Give `tests/async/` its own `conftest.py` defining `anyio_backend` (mirror the harness one),
so the fixture only reaches the async tests.
**Warning signs:** `fixture 'anyio_backend' not found` on async tests, or sync tests failing collection.

### Pitfall 7: `pyarrow.Table` lifetime vs a streaming reader
**What goes wrong:** Returning anything other than a fully-materialized `pyarrow.Table` from
`fetch_arrow_table` (e.g. a `RecordBatchReader`) would be read-after-checkin = use-after-free.
**Why it happens:** The reset event closes cursors on checkin; a live reader bound to the cursor dies.
**How to avoid:** `fetch_arrow_table` returns a materialized `pyarrow.Table` `[VERIFIED: dbapi.py:1340]`,
which is self-owning and safe after checkin. Streaming readers are explicitly deferred to v1.4.x. EDGE-21
asserts a post-checkin read succeeds AND the result is a `pyarrow.Table`, not a reader.
**Warning signs:** A segfault or "closed cursor" error when reading the table after `__aexit__`.

## Code Examples

### Async pool factory mirroring the sync overloads (APOOL-01)
```python
# src/adbc_poolhouse/_async/_factory.py
# Source: _pool_factory.py create_pool overload shape (verified) + ARCHITECTURE.md
from __future__ import annotations
from typing import overload, TYPE_CHECKING
from adbc_poolhouse._pool_factory import _create_pool_impl  # REUSE — no fork (CORE-04)
from adbc_poolhouse._async._pool import AsyncPool

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig

@overload
def create_async_pool(config: WarehouseConfig, *, pool_size: int = 5, max_overflow: int = 3,
                      timeout: int = 30, recycle: int = 3600, pre_ping: bool = False) -> AsyncPool: ...
@overload
def create_async_pool(*, driver_path: str, db_kwargs: dict[str, str], entrypoint: str | None = None,
                      pool_size: int = 5, max_overflow: int = 3, timeout: int = 30,
                      recycle: int = 3600, pre_ping: bool = False) -> AsyncPool: ...
@overload
def create_async_pool(*, dbapi_module: str, db_kwargs: dict[str, str], pool_size: int = 5,
                      max_overflow: int = 3, timeout: int = 30, recycle: int = 3600,
                      pre_ping: bool = False) -> AsyncPool: ...

def create_async_pool(config=None, *, driver_path=None, db_kwargs=None, entrypoint=None,
                      dbapi_module=None, pool_size=5, max_overflow=3, timeout=30,
                      recycle=3600, pre_ping=False) -> AsyncPool:
    """Create an async pool; signature mirrors `create_pool` exactly (APOOL-01)."""
    sync_pool = _create_pool_impl(config, driver_path, db_kwargs, entrypoint, dbapi_module,
                                  pool_size, max_overflow, timeout, recycle, pre_ping)
    return AsyncPool(sync_pool, pool_size=pool_size, max_overflow=max_overflow)
```
> Note: pool construction stays **synchronous** — `_create_pool_impl` runs once at creation and does no
> per-call network I/O, so `create_async_pool` itself need not be a coroutine. Only `connect`/`execute`/
> `fetch`/`close` are offloaded. (Confirm against ARCHITECTURE build order step 1.)

### EDGE-09 success+error token accounting (the Phase-24-owned legs)
```python
# tests/async/test_edge_limiter.py
# Source: ASYNC-EDGE-CASES.md §2 + D-24-02 (cancel leg deferred to Phase 25)
import pytest, anyio

@pytest.mark.anyio
async def test_token_released_on_success_and_error(anyio_backend_name, async_duckdb_pool):
    pool = async_duckdb_pool
    for _ in range(50):  # ×50 loop — catches a slow leak
        async with await pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute("SELECT 1")
            await cur.fetch_arrow_table()
        assert pool._limiter.borrowed_tokens == 0
    # error leg: an AdbcError mid-execute must also return the token
    for _ in range(50):
        with pytest.raises(Exception):  # a deliberately bad query → AdbcError
            async with await pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT * FROM does_not_exist")
        assert pool._limiter.borrowed_tokens == 0
        assert pool._limiter.available_tokens == pool._limiter.total_tokens
```

### EDGE-15 aliasing rejection with the stub harness
```python
# tests/async/test_edge_aliasing.py
# Source: D-24-03 + Phase 23 stubs (BlockingStubCursor records max_concurrent_in_execute)
import pytest, anyio
from adbc_poolhouse import ConnectionBusyError  # exported (new)

@pytest.mark.anyio
async def test_concurrent_alias_raises(anyio_backend_name, async_stub_connection):
    conn = async_stub_connection            # wraps a BlockingStubConnection
    cur = conn.cursor()
    errors: list[BaseException] = []
    async with anyio.create_task_group() as tg:
        async def run():
            try:
                await cur.execute("SELECT 1")  # one task blocks inside execute
            except BaseException as e:           # noqa: BLE001 — collect for assertion
                errors.append(e)
        tg.start_soon(run)
        await _await_inside(lambda: conn._stub.execute_call_count == 1)  # first is inside
        tg.start_soon(run)                       # second concurrent entry → reject
        # release the blocked first call so the group can finish
        ...
    assert any(isinstance(e, ConnectionBusyError) for e in errors)
    assert conn._stub.max_concurrent_in_execute == 1   # never two-in-execute
```
> The exact stub wiring depends on the re-armable-gate redesign (Pitfall 1). The planner should land that
> harness change as a Wave-0 task before the aliasing/limiter EDGE tests that need execute-then-fetch.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `to_thread.run_sync(cancellable=...)` | `abandon_on_cancel=...` | anyio 4.x | `cancellable` is a deprecated alias; use `abandon_on_cancel=` and never leak the old name `[VERIFIED: ASYNC-EDGE-CASES.md fact 2]` |
| `SQLAlchemy AsyncAdaptedQueuePool` (greenlet) | plain `QueuePool` + `to_thread` offload | n/a (project choice) | greenlet path is asyncio-bound → breaks trio neutrality; rejected (ARCHITECTURE Q2) |
| `asyncio.to_thread` / `run_in_executor` | `anyio.to_thread.run_sync` | n/a (project choice) | anyio copies contextvars to the worker and is backend-neutral; asyncio variants break trio + lose context `[CITED: ASYNC-EDGE-CASES.md fact 4]` |
| `except asyncio.CancelledError` | `anyio.get_cancelled_exc_class()` | n/a | asyncio-only catch is a no-op under trio (Phase 25 concern, but keep `_async/` asyncio-free now) |

**Deprecated/outdated:**
- `cancellable=` kwarg on `to_thread.run_sync` — use `abandon_on_cancel=`.
- Any direct `asyncio.*` reference inside `_async/` — banned and AST-guarded.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `_in_use` check-and-set is race-free purely because there is no `await` between check and set on the single-threaded loop | Pattern 3 / Pitfall 3 | If wrong, aliasing rejection (EDGE-15) silently fails — but this is standard event-loop reasoning and EDGE-15 directly tests it, so risk is low |
| A2 | `create_async_pool` can be a plain (non-async) function because pool construction does no per-call I/O | Code Examples | If pool construction turns out to block meaningfully, may need to offload it; low risk — sync `create_pool` is already non-blocking at construction |
| A3 | `conn.commit()`/`rollback()` exist on the checked-out fairy/dbapi connection and are offloadable (ACONN-04) | Phase Requirements | dbapi `Connection` has `commit`/`rollback` (standard DBAPI 2.0); verify the SQLAlchemy fairy exposes them or unwrap to `.driver_connection`. Medium — confirm the fairy→dbapi unwrap path when planning |
| A4 | The SQLAlchemy `_ConnectionFairy` from `pool.connect()` exposes `.cursor()` directly (sync tests use `conn.cursor()`) | Project structure / patterns | Verified the sync suite calls `pool.connect().cursor()` `[VERIFIED: tests/test_pool_factory.py:59]`; the async wrapper unwraps the same way. Low |
| A5 | `_release_arrow_allocators` fires on async checkin because `fairy.close()` triggers the pool `reset` event identically | ACONN-06 | Verified the reset listener is pool-level and fires on all return paths `[VERIFIED: _pool_factory.py:106]`. Low |

## Open Questions

1. **Does `pool.connect()` return a `_ConnectionFairy` whose `.cursor()`/`.commit()`/`.rollback()`/`.close()`
   pass straight through to the dbapi connection, or must the wrapper unwrap to `.driver_connection`?**
   - What we know: the sync suite calls `pool.connect().cursor().execute(...)` and `conn.close()` directly,
     and the reset event fires on `close()` `[VERIFIED: test_pool_factory.py, _pool_factory.py]`.
   - What's unclear: whether `commit`/`rollback`/`adbc_cancel` (Phase 25) need `.driver_connection` unwrapping.
   - Recommendation: in Wave 0, read the SQLAlchemy `_ConnectionFairy` surface (or just unwrap to
     `fairy.driver_connection` / `fairy.dbapi_connection` for the dbapi-specific calls). Low risk; settle in planning.

2. **Should the EDGE-25 guard be extended to also assert "no backend names in `_async/`" (D-24-04 structural check)?**
   - What we know: `scan_async_package` currently enforces `banned-asyncio-import` + `to_thread-without-limiter`.
     D-24-04 wants a static check that no backend-specific names appear in `_async/`.
   - What's unclear: whether to add a third rule to the guard or use a simpler grep test.
   - Recommendation: add a `no-backend-specific-names` rule (a small allowlist/denylist of the 13 backend
     class names) to `guard.py`, surfaced as a Phase-24 meta-test. Cheap and keeps D-24-04 enforceable.

3. **Re-armable gate: redesign `entered` to fire after the block, or keep the `_await_inside` poll?**
   - What we know: the poll pattern is verified-green (commit `943c074`); the after-block redesign is cleaner
     but was never landed (WR-01 reverted).
   - What's unclear: how much the execute-then-fetch EDGE tests need a true "inside execute" signal vs the poll.
   - Recommendation: land the after-block `entered` redesign (an `on_enter` callback bridged via
     `from_thread.run_sync`) as the durable fix, since Phase 24 reuses cursors and Phase 25 needs honest
     cancel timing too. Keep `_await_inside` as the belt-and-suspenders fallback.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `anyio` | the whole `_async/` layer + tests | ✓ | 4.x (`CapacityLimiter` API verified live) | — |
| `trio` | dual-backend test leg | ✓ | >=0.31 | — |
| `aiotools` | asyncio virtual clock (harness) | ✓ | >=2.2 | event-gating (no virtual clock) |
| `pyarrow` | `fetch_arrow_table` / EDGE-21 | ✓ | >=23.0.1 | — |
| `duckdb` (`[duckdb]` extra) | real-driver smoke (EDGE-21, D-24-04) | ✓ (dev `[all]`) | via extra | SQLite in-proc as alt real driver |
| `pytest-adbc-replay` | Snowflake cassette leg (D-24-04) | ✓ | >=1.0.0a3 | — |
| `mkdocs` + strict | docs gate (phase ≥7) | ✓ | docs group | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none material — all required deps are present in the dev env.

> Sandbox note (MEMORY): prefer `.venv/bin/<tool>` over `uv run <tool>` for mkdocs/hooks to avoid sandbox
> prompts — e.g. `.venv/bin/mkdocs build --strict`.

## Validation Architecture

> `workflow.nyquist_validation` is not disabled, so this section applies.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest >=8.0.0` + `anyio` pytest plugin (dual-backend via `anyio_backend` fixture) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (no separate pytest.ini) |
| Quick run command | `.venv/bin/pytest tests/async -x -q` (or `tests/async/test_async_lifecycle.py` for the happy path) |
| Full suite command | `.venv/bin/pytest -q` (sync + harness + async; must stay green with both backends) |
| Loop-run (REQUIRED for concurrency) | `for i in $(seq 1 20); do .venv/bin/pytest tests/async -q || break; done` — 0 hangs across 20 runs |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APOOL-01/ACONN-01/ACUR-01/ACUR-04 | happy path create→connect→execute→fetch_arrow_table→checkin (DuckDB) | integration (real driver) | `.venv/bin/pytest tests/async/test_async_lifecycle.py -q` | ❌ Wave 0 |
| ACONN-03/ACUR-07 | `cursor()` sync; `description`/`rowcount`/`arraysize` no-await | unit | `.venv/bin/pytest tests/async/test_async_lifecycle.py -k sync_surface -q` | ❌ Wave 0 |
| ACONN-04/05, APOOL-02/03 | commit/rollback/close offloaded; managed_async_pool auto-close | integration | `.venv/bin/pytest tests/async/test_async_lifecycle.py -k lifecycle -q` | ❌ Wave 0 |
| EDGE-09 (success+error) | token `borrowed_tokens==0` after success and AdbcError, ×50 | unit/integration | `.venv/bin/pytest tests/async/test_edge_limiter.py -k token -q` | ❌ Wave 0 |
| EDGE-10 | token not leaked when acquire cancelled while queued | unit (stub) | `.venv/bin/pytest tests/async/test_edge_limiter.py -k queued_cancel -q` | ❌ Wave 0 |
| EDGE-11 | hold connection + second offload, no deadlock (watchdog) | unit (stub) | `.venv/bin/pytest tests/async/test_edge_limiter.py -k no_deadlock -q` | ❌ Wave 0 |
| EDGE-12 | in-flight running-max == pool_size+max_overflow under 4× flood | unit (stub) | `.venv/bin/pytest tests/async/test_edge_limiter.py -k bounded -q` | ❌ Wave 0 |
| EDGE-15 | concurrent alias → `ConnectionBusyError`; max_concurrent==1 | unit (stub) | `.venv/bin/pytest tests/async/test_edge_aliasing.py -q` | ❌ Wave 0 |
| EDGE-17 | ADBC error exact type + traceback across boundary | unit (stub) | `.venv/bin/pytest tests/async/test_edge_exceptions.py -k propagates -q` | ❌ Wave 0 |
| EDGE-18 | exception in `__aenter__` leaks no connection (checkedout()==0 over N) | unit/integration | `.venv/bin/pytest tests/async/test_edge_exceptions.py -k aenter_leak -q` | ❌ Wave 0 |
| EDGE-21 | materialized `pyarrow.Table` valid after checkin (DuckDB) | integration (real driver) | `.venv/bin/pytest tests/async/test_edge_resource.py -q` | ❌ Wave 0 |
| EDGE-25 | every blocking call off loop thread + guard meta-test empty | unit (stub + AST) | `.venv/bin/pytest tests/async/test_edge_loophygiene.py -k off_loop -q` + extend `test_async_guard.py` | ⚠️ guard exists; off-loop test ❌ Wave 0 |
| EDGE-26 | long offload does not starve loop (concurrent coroutine advances) | unit (stub) | `.venv/bin/pytest tests/async/test_edge_loophygiene.py -k starve -q` | ❌ Wave 0 |
| CORE-03/EDGE-25 lint | no `asyncio` import, no bare `to_thread` in `_async/` | static (AST) | `.venv/bin/pytest tests/test_async_guard.py -q` (extend to scan real `_async/`) | ✅ guard impl; needs a test pointing at `src/adbc_poolhouse/_async/` |
| CORE-04/D-24-04 genericity | no backend-specific names in `_async/` | static (AST/grep) | new guard rule or grep test | ❌ Wave 0 (Open Q2) |
| D-24-04 backend-generic | Snowflake cassette replay through async layer | integration (replay) | `.venv/bin/pytest tests/async -k snowflake -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/async -x -q` (fast) + `.venv/bin/ruff check` + `.venv/bin/basedpyright`.
- **Per wave merge:** full suite `.venv/bin/pytest -q` (both backends) **run in a ×20 loop** for the
  concurrency-touching waves (EDGE-09..15) — 0 hangs required (MEMORY: single-shot missed a 33% deadlock).
- **Phase gate:** full suite green + `.venv/bin/basedpyright` 0 errors + `.venv/bin/ruff check`/`format --check`
  clean + `.venv/bin/mkdocs build --strict` passes (docs gate, phase ≥7).

### Wave 0 Gaps
- [ ] **Harness:** land the `entered`-after-block redesign + re-armable cursor gate in
  `tests/_async_harness/stubs.py` + `gating.py` (WR-01 + D-CF-01) — **prerequisite** for execute-then-fetch
  EDGE tests. Re-apply WR-03 (set flags under the lock) and IN-03 (public `closed`) if needed.
- [ ] `tests/async/conftest.py` — `anyio_backend` fixture (mirror harness conftest) + DuckDB real-pool
  fixture + stub-backed `AsyncConnection`/`AsyncPool` fixtures.
- [ ] `tests/async/test_async_lifecycle.py` — happy path + sync-surface tests (covers the bulk of CORE/APOOL/ACONN/ACUR).
- [ ] `tests/async/test_edge_*.py` — the five EDGE files mapped above.
- [ ] Extend `tests/test_async_guard.py` to scan the real `src/adbc_poolhouse/_async/` package (currently
  the guard is only self-tested on synthetic source).
- [ ] Decide + add the `no-backend-specific-names` guard rule (Open Q2) for D-24-04.

## Project Constraints (from CLAUDE.md + MEMORY)

- **Docs gate (phase ≥7):** every new public symbol needs Google-style docstrings (Args/Returns/Raises);
  key entry points (`create_async_pool`, `managed_async_pool`, `AsyncPool`, `AsyncConnection`, `AsyncCursor`)
  need an `Example:` block; consumer-facing behaviour (the forbidden-aliasing antipattern from CONTEXT) goes
  in the async guide; `mkdocs build --strict` must pass; humanizer pass on new prose. Include
  `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in the plan's `<execution_context>`.
- **Docstring style (MEMORY):** Google-style, **Markdown** in docstrings (not RST) — `` `create_pool` ``
  not `:func:`create_pool``. `Example:` (singular) = admonition with ```` ```python ```` fences;
  `Examples:` (plural) = `>>>` doctest section.
- **Forbidden-aliasing docs (D-24-03):** the async guide MUST document the "do not share one async connection
  across concurrent tasks" antipattern using the canonical ❌/✅ example in CONTEXT.md.
- **Sandbox (MEMORY):** prefer `.venv/bin/<tool>` over `uv run <tool>` for mkdocs/hooks.
- **STATE.md is stale-prone (MEMORY):** trust git tags + pyproject + ROADMAP over STATE.md frontmatter.
- **Worktree base quirk (MEMORY):** Claude Code worktrees branch off project-default, not orchestrator HEAD;
  a wave-N executor depending on a wave-(N-1) merge needs an explicit rebase step — relevant because the
  harness redesign (Wave 0) must be merged before the EDGE-test waves.
- **Loop concurrency tests (MEMORY):** run harness/async tests in a loop (target 0 hangs), not once.
- **basedpyright strict** + ruff (`E,F,W,I,UP,B,SIM,TCH,D`, line-length 100): new wrappers must be fully
  typed and docstring-clean. `reportPrivateUsage = false` lets tests read `pool._limiter` / `conn._in_use`.

## Sources

### Primary (HIGH confidence)
- `.planning/research/ARCHITECTURE.md` — settled offload model, limiter sizing, build order, anti-patterns (the binding design).
- `.planning/research/ASYNC-EDGE-CASES.md` — EDGE-09..26 deterministic test designs + the 5 verified anyio/trio facts.
- `.planning/phases/24-core-async-wrapper/24-CONTEXT.md` — the four locked decisions (D-24-01..04) + Phase 23 carry-forward (D-CF-01, WR-01..04, IN-03/04).
- `.planning/phases/23-test-harness-foundation/23-REVIEW-FIX.md` — WR-01 deadlock postmortem; what's deferred to Phase 24.
- `src/adbc_poolhouse/_pool_factory.py` — `_create_pool_impl` (reuse), `close_pool`, `_release_arrow_allocators` reset event `[VERIFIED]`.
- `src/adbc_poolhouse/_exceptions.py` — `PoolhouseError` base for `ConnectionBusyError` `[VERIFIED]`.
- `tests/_async_harness/{stubs,gating,guard,conftest,clock}.py` + `test_harness.py` — the reusable harness surface + `_await_inside` pattern `[VERIFIED]`.
- `.venv/.../adbc_driver_manager/dbapi.py` — Cursor surface: `execute`/`executemany`/`fetch*`/`fetch_arrow_table`→`pyarrow.Table`; sync `description`/`rowcount`/`arraysize` props; `cursor()` `[VERIFIED: source read]`.
- Live venv probe — `anyio.CapacityLimiter`: `total_tokens`/`borrowed_tokens`/`available_tokens`/`statistics`/`acquire`/`release` `[VERIFIED]`.
- `pyproject.toml` — dep versions, basedpyright strict, ruff config, pytest ini `[VERIFIED]`.
- `CLAUDE.md` + user MEMORY — docs gate, docstring style, sandbox + loop-test gotchas `[VERIFIED]`.

### Secondary (MEDIUM confidence)
- anyio docs (via ASYNC-EDGE-CASES.md citations) — `to_thread.run_sync` shielded-by-default, `abandon_on_cancel` vs deprecated `cancellable`, contextvar copy semantics.

### Tertiary (LOW confidence)
- A1/A3 assumptions (event-loop check-and-set race-freedom; fairy→dbapi `commit`/`rollback` unwrap) — flagged in Assumptions Log; resolved by Wave-0 verification + EDGE-15 test.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libs are existing, vetted deps; key APIs verified live this session.
- Architecture: HIGH — fully settled in ARCHITECTURE.md + four locked CONTEXT decisions; nothing to re-litigate.
- Pitfalls: HIGH — drawn from the actual Phase 23 review/postmortem and verified harness code, not speculation.
- Test design: HIGH — EDGE designs are pre-written in ASYNC-EDGE-CASES.md; harness reuse path is concrete.
- Two LOW items (A1, A3) are isolated and directly testable.

**Research date:** 2026-06-27
**Valid until:** ~2026-07-27 (stable internal design; anyio 4.x API is the only external moving part and it is pinned).
