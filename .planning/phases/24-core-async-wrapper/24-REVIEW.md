---
phase: 24-core-async-wrapper
reviewed: 2026-06-28T00:00:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - src/adbc_poolhouse/__init__.py
  - src/adbc_poolhouse/_async/__init__.py
  - src/adbc_poolhouse/_async/_connection.py
  - src/adbc_poolhouse/_async/_cursor.py
  - src/adbc_poolhouse/_async/_factory.py
  - src/adbc_poolhouse/_async/_offload.py
  - src/adbc_poolhouse/_async/_pool.py
  - src/adbc_poolhouse/_exceptions.py
  - docs/src/guides/async.md
  - docs/src/index.md
  - mkdocs.yml
  - tests/_async_harness/gating.py
  - tests/_async_harness/stubs.py
  - tests/_async_harness/test_harness.py
  - tests/async/_edge_helpers.py
  - tests/async/conftest.py
  - tests/async/test_async_lifecycle.py
  - tests/async/test_edge_aliasing.py
  - tests/async/test_edge_exceptions.py
  - tests/async/test_edge_limiter.py
  - tests/async/test_edge_loophygiene.py
  - tests/async/test_edge_resource.py
  - tests/test_async_guard.py
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 24: Code Review Report

**Reviewed:** 2026-06-28
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

Reviewed the new async wrapper layer (`AsyncPool` / `AsyncConnection` /
`AsyncCursor`), the single `offload` chokepoint, the lazy PEP 562 surface on the
top-level package, the `ConnectionBusyError` exception, the docs, and the full
async test suite.

The core concurrency machinery is sound. I independently verified the things the
prompt asked me to scrutinise:

- **The `_in_use` check-and-set is race-free.** `_enter_offload` reads then writes
  `_in_use` with no `await`, no `try`, and no other suspension point between the
  read and the write, so on the single-threaded loop two tasks can never both
  observe `False`. `_in_use` is only ever touched on the loop thread (never inside
  a worker), so the no-lock model is correct.
- **Token accounting balances on both legs.** Every offloading method brackets the
  `await offload(...)` in `try/finally` with `_exit_offload`, and the transient
  token is owned entirely by `to_thread.run_sync`, which returns it on success and
  on exception. I ran the real-driver token-accounting and no-leak suites; both are
  green and `borrowed_tokens` returns to 0 after success and after `AdbcError`.
- **Worker exceptions propagate unwrapped.** `offload` does not catch, and no
  caller catches; the EDGE-17 test confirms the exact `adbc_driver_manager` type
  and the `_offload` worker frame survive.
- **Shielded check-in works.** `close` / `__aexit__` / `AsyncPool.close` wrap the
  offload in `CancelScope(shield=True)`.

`mkdocs build --strict` passes. The async suite passed 3/3 loop runs with no
flakiness (71 passed, 2 skipped).

The findings below are robustness and consistency gaps, not correctness failures
on the documented happy path. The highest-value ones (WR-01, WR-02) concern the
two places where the connection is touched WITHOUT the `_in_use` guard, which
weakens the very aliasing invariant the module is built around.

## Warnings

### WR-01: `__aexit__` bypasses the `_in_use` guard, so check-in can run a second blocking call on the connection concurrently with an in-flight sibling call

**File:** `src/adbc_poolhouse/_async/_connection.py:218-241`
**Issue:** `__aexit__` deliberately does NOT acquire `_in_use` ("Bypasses the
`_in_use` guard so a connection left marked busy by a failed in-flight call is
still reclaimed"). The reclaim-safety motivation is legitimate, but the
consequence is that if the connection has been aliased across tasks (the exact
misuse the whole module exists to reject), an `__aexit__` firing in task A will
run `fairy.close()` on a worker thread at the same time another task B is mid-flight
in `execute` on the SAME ADBC connection — two worker threads touching one
connection simultaneously, which is the precise corruption `ConnectionBusyError`
is meant to make impossible. Every other entry point (`commit`, `rollback`,
explicit `close`, all cursor methods) is guarded; `__aexit__` is the one hole.
Note this is gated behind aliasing misuse, so it is not a happy-path bug — hence
WARNING, not BLOCKER — but it means the "race-free" guarantee in the module
docstring is not actually total.
**Fix:** The reclaim and the guard are not mutually exclusive. Set the flag
unconditionally on entry without rejecting, so a real in-flight sibling is at
least not silently double-driven; or document explicitly that `__aexit__` is the
one intentionally-unguarded path and that aliasing + context-exit is undefined.
At minimum, make the asymmetry between guarded `close()` and unguarded
`__aexit__` explicit in the class docstring rather than only in the `__aexit__`
docstring.

### WR-02: `cursor()` is unguarded and calls into the driver on the loop thread while a sibling call may be in flight

**File:** `src/adbc_poolhouse/_async/_connection.py:134-151`
**Issue:** `cursor()` does not consult `_in_use`, and it calls
`self._fairy.cursor()` synchronously on the event-loop thread. For the real ADBC
driver, `Connection.cursor()` constructs an `AdbcStatement(conn._conn)` — an FFI
call into the driver that allocates a statement against the connection (verified
against `adbc_driver_manager.dbapi.Cursor.__init__`). Two problems compound: (1)
it is characterised throughout the code and docs as "does no I/O," but it does
make a C call into the driver that briefly holds the GIL and, on some drivers,
could block; (2) because it is unguarded, an aliased sibling task can be mid-flight
in `execute` on the same connection while `cursor()` allocates a new statement on
that connection from the loop thread — again an unsynchronised concurrent touch of
the connection the aliasing guard is supposed to prevent.
**Fix:** Either offload `cursor()` like every other connection call (the cleanest,
consistent with "every blocking ADBC call goes through `offload`"), or, if keeping
it synchronous for the ACONN-03 contract, soften the "does no I/O" wording to "does
a cheap local statement allocation, not a network round-trip" and acknowledge it
runs on the loop thread. A guard here is harder because `cursor()` returns
synchronously, but the I/O claim should at least be accurate.

### WR-03: Explicit `close()` followed by context exit double-closes the fairy

**File:** `src/adbc_poolhouse/_async/_connection.py:188-207, 218-241`
**Issue:** The documented usage is `async with await pool.connect() as conn:`.
A user who also calls `await conn.close()` inside that block (a reasonable thing to
do, and `close()` is a public method) causes `fairy.close()` to run twice: once
from the explicit `close()` and again from `__aexit__`. I verified empirically
that this is currently benign for DuckDB (`checkedout()` stays 0, no token leak),
because SQLAlchemy's fairy `close()` is idempotent. But the second `close()` is an
extra full offload — it borrows a limiter token and dispatches a worker thread to
re-run check-in on an already-returned connection, and its idempotency depends on
SQLAlchemy internals rather than anything the wrapper enforces.
**Fix:** Track a `_closed` flag on `AsyncConnection` and make `close()` /
`__aexit__` no-op (return early) if already closed, so check-in runs exactly once
and does not depend on fairy idempotency.

### WR-04: `close_async_pool` is not idempotent and re-runs blocking teardown on every call

**File:** `src/adbc_poolhouse/_async/_pool.py:104-114`; `_factory.py:159-179`
**Issue:** `AsyncPool.close` always offloads `close_pool(self._pool)`, which calls
`pool.dispose()` then `pool._adbc_source.close()` (see
`_pool_factory.close_pool`). There is no guard against calling `close()` twice. The
`managed_async_pool` context manager calls `close_async_pool` in its `finally`; a
user who also calls `close_async_pool(pool)` explicitly inside the block (or
re-uses a closed pool) will dispatch a second teardown that re-closes an
already-closed ADBC source. Whether `adbc_source.close()` is safe to call twice is
driver-dependent and not guaranteed.
**Fix:** Add an idempotency flag to `AsyncPool` (set on first `close`) and return
early on subsequent calls, mirroring the `_closed` suggestion in WR-03.

### WR-05: `AsyncCursor.close()` holds the `_in_use` guard inside the shield, so a cursor cannot be closed while its own connection call is genuinely in flight — but `__aexit__` close ordering is undefined relative to connection check-in

**File:** `src/adbc_poolhouse/_async/_cursor.py:312-358`
**Issue:** `AsyncCursor.__aexit__` → `close()` acquires the parent's
`_enter_offload`. In the common nested form
`async with await pool.connect() as conn:` with a bare `cur = conn.cursor()`
(never used as a context manager), the cursor is never explicitly closed and
instead is reaped by the pool `reset` event's `_release_arrow_allocators` on
check-in — fine. But if a user writes `async with conn.cursor() as cur:` nested
inside the connection's `async with`, cursor `__aexit__` runs first and acquires
`_in_use`, then connection `__aexit__` runs `fairy.close()` (unguarded, WR-01).
The two close paths (cursor close, then connection close which also closes all
cursors via the reset event) overlap in responsibility, and the cursor `close`
offload borrows a token that the connection close path does not coordinate with.
This is correct on the happy path but the layered close semantics are implicit.
**Fix:** Document the intended close ordering (cursor context exit before
connection context exit) and confirm the reset-event cursor reaping is idempotent
with an explicit `cur.close()` having already run. Consider the same `_closed`
guard on `AsyncCursor` so a cursor closed explicitly is not re-closed by its own
`__aexit__`.

## Info

### IN-01: `close_async_pool` docstring example is not runnable as written

**File:** `src/adbc_poolhouse/_async/_factory.py:171-177`
**Issue:** The Example block shows `await close_async_pool(pool)` at module top
level with no surrounding `async def` / `anyio.run`, unlike the `create_async_pool`
example which correctly wraps the call. Copy-pasting it raises `SyntaxError`
(`await` outside a coroutine). The `index.md` and `async.md` examples are correct;
only this docstring is misleading.
**Fix:** Wrap the snippet in an `async def main(): ... ; anyio.run(main)` shell as
the sibling `create_async_pool` example does.

### IN-02: Module docstring references a Plan-numbered phase ("Plan 03") that leaks planning artifacts into shipped code

**File:** `src/adbc_poolhouse/_async/_factory.py:13`; also `_offload.py:8` ("the
`scan_async_package` source guard"), `gating.py:14` ("the Plan 03 source-scan
guard")
**Issue:** Several shipped-source docstrings reference internal planning vocabulary
("the per-call cursor methods in Plan 03", "the Plan 03 source-scan guard"). These
are meaningless to an external reader of the published API docs and tie the
shipped docstrings to phase-internal plan numbers.
**Fix:** Replace plan-relative phrasing with stable descriptions ("the cursor
methods", "the source-scan guard in the test harness").

### IN-03: `_SyncCursor.description` is typed `object`, weakening downstream type safety

**File:** `src/adbc_poolhouse/_async/_cursor.py:60-61, 128-138`
**Issue:** Both the Protocol member and `AsyncCursor.description` return `object`,
so callers get no static information about the DBAPI description tuple shape. This
is defensible given the structural Protocol, but `object` is the loosest possible
type and silently accepts any misuse.
**Fix:** Consider a narrower alias (e.g. `Sequence[tuple[object, ...]] | None`) to
match the documented "sequence of column-metadata tuples, or `None`" contract.

### IN-04: `AsyncCursor.fetchmany` / `fetchall` / `fetchone` are annotated `-> object` while the Protocol gives precise types

**File:** `src/adbc_poolhouse/_async/_cursor.py:216-310`
**Issue:** The wrapper methods return `object` even though the underlying
`_SyncCursor` Protocol declares `fetchmany -> Sequence[object]`, `fetchall ->
Sequence[object]`. The wrapper discards that information at the async boundary, so
a consumer of `await cur.fetchall()` gets `object` and must cast. Not a bug, but a
needless loss of the type fidelity the Protocol already provides.
**Fix:** Propagate the Protocol return types through the async wrappers
(`-> Sequence[object]` for fetchmany/fetchall, `-> object | None` for fetchone).

---

_Reviewed: 2026-06-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
