---
phase: 24-core-async-wrapper
plan: 02
subsystem: async-core
tags: [async, anyio, pool, offload, exceptions, pep562]
requires:
  - adbc_poolhouse._pool_factory._create_pool_impl
  - adbc_poolhouse._pool_factory.close_pool
  - adbc_poolhouse._exceptions.PoolhouseError
  - anyio (dev extra; runtime [async] extra lands in Phase 26)
provides:
  - adbc_poolhouse.ConnectionBusyError
  - adbc_poolhouse._async._offload.offload
  - adbc_poolhouse._async._pool.AsyncPool
  - adbc_poolhouse._async._factory.create_async_pool
  - adbc_poolhouse._async._factory.managed_async_pool
  - adbc_poolhouse._async._factory.close_async_pool
  - adbc_poolhouse._async._connection.AsyncConnection (contract; body Plan 03)
  - adbc_poolhouse._async._connection.AsyncCursor (contract; body Plan 03)
affects:
  - adbc_poolhouse.__init__ (PEP 562 lazy async exports + ConnectionBusyError)
tech-stack:
  added: []
  patterns:
    - single offload chokepoint (anyio.to_thread.run_sync, limiter=, abandon_on_cancel=False)
    - per-pool dedicated CapacityLimiter(pool_size + max_overflow)
    - transient-token model (token borrowed per-offload, not held for connection lifetime)
    - shielded close (anyio.CancelScope(shield=True))
    - PEP 562 module __getattr__ for anyio-free import
    - interface-first contracts (typed AsyncConnection/AsyncCursor skeletons)
key-files:
  created:
    - src/adbc_poolhouse/_async/__init__.py
    - src/adbc_poolhouse/_async/_offload.py
    - src/adbc_poolhouse/_async/_pool.py
    - src/adbc_poolhouse/_async/_connection.py
    - src/adbc_poolhouse/_async/_factory.py
  modified:
    - src/adbc_poolhouse/_exceptions.py
    - src/adbc_poolhouse/__init__.py
decisions:
  - "PEP 695 generic syntax (def offload[T]) rejected for a TypeVar: project targets pythonVersion=3.11 (basedpyright), PEP 695 needs 3.12+"
  - "Backend config names (DuckDBConfig etc.) appear only in docstring Example: blocks (docs gate), never in executable code (D-24-04 verified by AST scan)"
  - "AsyncConnection/AsyncCursor shipped as typed contracts with raise NotImplementedError bodies so connect() is typeable and Plan 03 fills behavior against a fixed interface"
metrics:
  duration: 7min
  tasks: 2
  files: 7
  completed: 2026-06-27
---

# Phase 24 Plan 02: Async Foundation (offload, AsyncPool, factory) Summary

The load-bearing async foundation: a single `offload()` thread-dispatch chokepoint, the
`ConnectionBusyError` aliasing exception, `AsyncPool` owning a dedicated per-pool
`anyio.CapacityLimiter`, and the `create_async_pool` / `managed_async_pool` /
`close_async_pool` entry points — all reusing the unchanged sync core
(`_create_pool_impl`, `close_pool`) verbatim and exposed via a PEP 562 lazy `__getattr__`
so `import adbc_poolhouse` stays anyio-free.

## What Was Built

### Task 1 — offload chokepoint + ConnectionBusyError + lazy exports (`9bb696e`)

- **`ConnectionBusyError(PoolhouseError)`** in `_exceptions.py` — single inheritance (not
  `ValueError`, unlike `ConfigurationError`), carries the canonical D-24-03 message, with a
  `message=None` override hook. Eagerly exported (it is anyio-free).
- **`_async/_offload.py`** — the ONLY `anyio.to_thread.run_sync` call site in `_async/`.
  `async def offload(fn, *args, limiter)` runs `lambda: fn(*args)` with mandatory `limiter=`
  and `abandon_on_cancel=False`, no exception re-wrap (the worker's exact type + traceback
  propagate — EDGE-17). Literal un-aliased attribute chain so the source guard sees it.
- **`_async/__init__.py`** — package exporting the three factory entry points with a sorted
  `__all__`.
- **`__init__.py`** — added `ConnectionBusyError` to the eager import + `__all__`; added a
  PEP 562 `__getattr__` that lazily imports `create_async_pool` / `managed_async_pool` /
  `close_async_pool` from `_async` on first access, re-raising a clear
  `ImportError(... pip install adbc-poolhouse[async])` if anyio is absent; added `__dir__`
  returning `sorted(__all__)`. No eager `import adbc_poolhouse._async` at module top.

### Task 2 — AsyncPool + factory entry points (`5bd479f`)

- **`_async/_pool.py`** — `AsyncPool(sync_pool, *, pool_size, max_overflow)` builds ONE
  dedicated `anyio.CapacityLimiter(pool_size + max_overflow)` (CORE-02, never the global
  40-token default). `async connect()` offloads `self._pool.connect` under the limiter and
  returns `AsyncConnection(fairy, self._limiter)` (transient token released on return —
  D-24-01). `async close()` runs the offloaded `close_pool` inside
  `anyio.CancelScope(shield=True)`.
- **`_async/_factory.py`** — `create_async_pool` with the exact 3-overload shape and keyword
  defaults of `create_pool`, body calls `_create_pool_impl(...)` verbatim then wraps in
  `AsyncPool`. `close_async_pool` awaits `pool.close()`. `managed_async_pool` is a
  `@contextlib.asynccontextmanager` (3 overloads) with `try: yield / finally: await
  close_async_pool` (shield lives in `AsyncPool.close`). Zero per-backend code.
- **`_async/_connection.py`** — `AsyncConnection` / `AsyncCursor` typed contracts with the
  frozen constructor signatures `AsyncConnection(fairy, limiter)` and
  `AsyncCursor(sync_cursor, limiter, owner)` and `raise NotImplementedError` bodies for
  Plan 03 to fill. This keeps `connect()` typeable and basedpyright-strict-clean now.

## Verification Results

| Check | Result |
|-------|--------|
| `basedpyright src/adbc_poolhouse/_async/` | 0 errors |
| `basedpyright src/adbc_poolhouse/__init__.py` | 0 errors |
| `scan_async_package('src/adbc_poolhouse/_async')` | `[]` (guard-clean) |
| `ruff check src/adbc_poolhouse/` | clean |
| `mkdocs build --strict` | passes (ConnectionBusyError rendered in reference) |
| full sync suite `pytest -q` | 318 passed, 2 skipped |
| `import adbc_poolhouse` anyio-free | confirmed (`anyio` not in `sys.modules` post-import) |
| lazy resolve `create_async_pool` / `ConnectionBusyError` | OK via `__getattr__` |
| `CapacityLimiter(pool_size + max_overflow)` in code | exactly 1 (line 66 `_pool.py`) |
| `CancelScope(shield=True)` in code | exactly 1 (line 92 `_pool.py`) |
| backend identifiers in executable `_async/` code (AST scan) | NONE |
| `from adbc_poolhouse._pool_factory import _create_pool_impl` | present in `_factory.py` |
| `@overload` on `create_async_pool` / `managed_async_pool` | 3 each |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] PEP 695 generic syntax incompatible with the 3.11 type target**
- **Found during:** Task 1
- **Issue:** The plan's `async def offload[T](...)` (PEP 695) failed basedpyright with
  "Function type parameter syntax requires Python 3.12 or newer" — the project pins
  `pythonVersion = "3.11"` (and `requires-python = ">=3.11"`).
- **Fix:** Used the classic `_T = TypeVar("_T")` with `offload(fn: Callable[..., _T], ...) -> _T`.
  Semantically identical, basedpyright-strict-clean against the 3.11 target.
- **Files modified:** `src/adbc_poolhouse/_async/_offload.py`
- **Commit:** `9bb696e`

**2. [Rule 3 - Blocking] `managed_async_pool` calling the overloaded public factory lost type info**
- **Found during:** Task 2
- **Issue:** Calling `create_async_pool(config, ...)` from inside `managed_async_pool` with
  all keywords (including `config=None` positional) matched no overload, forcing a
  `# type: ignore` that made the yielded `pool` type unknown (2 basedpyright errors).
- **Fix:** Inlined `_create_pool_impl(...) + AsyncPool(...)` directly (mirroring how the sync
  `managed_pool` calls `_create_pool_impl` rather than `create_pool`). 0 errors.
- **Files modified:** `src/adbc_poolhouse/_async/_factory.py`
- **Commit:** `5bd479f`

### Interpretation note (not a code change)

The plan's acceptance criterion "grep for any of DuckDBConfig/SnowflakeConfig/etc. returns 0"
is satisfied for **executable code** (verified by an AST identifier scan — NONE found). The
docs-author gate (CLAUDE.md, phase >= 7) requires `Example:` blocks on the entry points, and
those examples naturally reference `DuckDBConfig` — exactly as the sync `create_pool`/
`managed_pool` docstrings do. D-24-04's genericity intent (no per-backend code/branching/
imports in `_async/`) is met; the only backend-name occurrences are illustrative docstrings.

## Environment Note

The pre-commit `basedpyright` hook is wired as `uv run basedpyright`. Under the command
sandbox, `uv run` panics at macOS `system-configuration` (NULL SCDynamicStore) — the
documented `uv-sandbox-workaround`. Direct `.venv/bin/basedpyright` is clean; the two task
commits were made with the sandbox disabled so the `uv run` hook could access system config.
All hooks (ruff, ruff-format, basedpyright, blacken-docs, detect-secrets) passed on both
commits.

## Threat Model Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-24-02-DOS (mis-sized limiter) | mitigate | DONE — dedicated `CapacityLimiter(pool_size + max_overflow)`, never the default (strict-bound proof is EDGE-12, Plan 04) |
| T-24-02-INFO (swallowed traceback) | mitigate | DONE — `offload` does not catch/re-wrap; `run_sync` re-raises exact type+traceback (proof in Plan 04) |
| T-24-02-DOS2 (close abandoned mid-cancel) | mitigate | DONE — `AsyncPool.close` offloads inside `CancelScope(shield=True)` |
| T-24-02-TAMPER (per-backend fork) | mitigate | DONE — reuses `_create_pool_impl` verbatim; AST scan confirms no backend names in executable code |
| T-24-02-SC (installs) | N/A | no new packages added |

## Authentication Gates

None.

## Known Stubs

`AsyncConnection` / `AsyncCursor` method bodies raise `NotImplementedError` — this is the
**intentional interface-first contract** the plan specifies (objective: "define the contracts
here so Plan 03 fills in behavior against a fixed interface"). The constructor signatures are
frozen; **Plan 03 (24-03)** supplies the `_in_use` aliasing guard, shielded check-in,
synchronous `cursor()`, and offloaded `execute` / `executemany` / `fetch_arrow_table` /
`commit` / `rollback` / `close` bodies. These are not data-stub placeholders flowing to a UI;
they are typed skeletons on a fixed interface, resolved by the next plan in the same phase.

## Next Steps

- **Plan 03 (24-03):** Implement `AsyncConnection` / `AsyncCursor` bodies (`_in_use` guard,
  shielded check-in, sync `cursor()`, offloaded methods, async context-manager protocol).
- **Plan 04 (24-04):** Structural EDGE coverage (EDGE-09 success/error legs, EDGE-10,
  EDGE-12 strict bound, EDGE-17 traceback fidelity, EDGE-25 guard meta-test) + the extended
  source guard asserting no backend names.

## Self-Check: PASSED

All 5 created source files + SUMMARY.md present on disk; both task commits
(`9bb696e`, `5bd479f`) found in git history.
