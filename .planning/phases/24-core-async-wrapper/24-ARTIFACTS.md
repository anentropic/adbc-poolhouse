# Phase 24 — Artifacts This Phase Produces

Canonical manifest of every symbol/file/rule Phase 24 creates, across all five plans. The
executor and verifier check shipped work against this list.

## Public symbols (exported from `adbc_poolhouse`)

| Symbol | Kind | Module | Plan |
|--------|------|--------|------|
| `create_async_pool` | function (3 overloads) | `_async/_factory.py` | 02 |
| `managed_async_pool` | async context manager | `_async/_factory.py` | 02 |
| `close_async_pool` | async function | `_async/_factory.py` | 02 |
| `AsyncPool` | class | `_async/_pool.py` | 02 (contract) |
| `AsyncConnection` | class | `_async/_connection.py` | 02 (contract) / 03 (body) |
| `AsyncCursor` | class | `_async/_cursor.py` | 02 (contract) / 03 (body) |
| `ConnectionBusyError` | exception (`PoolhouseError` subclass) | `_exceptions.py` | 02 |

## Internal mechanism

| Item | Where | Plan |
|------|-------|------|
| `offload(fn, *args, limiter=)` — single `to_thread.run_sync` chokepoint (CORE-01) | `_async/_offload.py` | 02 |
| per-pool `_limiter: anyio.CapacityLimiter(pool_size + max_overflow)` (CORE-02) | `AsyncPool.__init__` | 02 |
| `_in_use: bool` flag + `_enter_offload`/`_exit_offload` (aliasing rejection, D-24-03) | `AsyncConnection` | 03 |
| PEP 562 lazy `__getattr__` async export guard | package `__init__.py` | 02 |

## New source files under `src/adbc_poolhouse/_async/`

`__init__.py`, `_offload.py`, `_factory.py`, `_pool.py` (Plan 02); `_connection.py`, `_cursor.py` (Plan 03).

## Modified shared source

`src/adbc_poolhouse/_exceptions.py` (+ `ConnectionBusyError`), `src/adbc_poolhouse/__init__.py`
(+ eager `ConnectionBusyError` export, + PEP 562 lazy async names) — Plan 02.

## New / modified test files

| Path | Plan |
|------|------|
| `tests/_async_harness/{stubs,gating,test_harness,test_stubs}.py` (MOD: re-armable gate + entered redesign) | 01 |
| `tests/async/conftest.py`, `tests/async/test_async_lifecycle.py` | 04 |
| `tests/async/test_edge_{limiter,aliasing,exceptions,resource,loophygiene}.py` | 04 |
| `tests/test_async_guard.py` (MOD: real-package scan + no-backend-names rule) | 04 |

## Lint / guard rules

- `scan_async_package` asserted against the REAL `src/adbc_poolhouse/_async/` (EDGE-25/CORE-03) — Plan 04.
- New `no-backend-specific-names` rule/check for `_async/` (D-24-04/CORE-04) — Plan 04.

## Docs artifacts

- `docs/src/guides/async.md` (usage guide + forbidden-aliasing antipattern) — Plan 05.
- `mkdocs.yml` nav + `docs/src/index.md` async entry points — Plan 05.
- Google-style docstrings + `Example:` blocks on all public async symbols — Plan 05.

## Explicitly NOT produced in Phase 24 (deferred — do not imply covered)

- Cancellation machinery (`adbc_cancel`/invalidate/full cancel scopes), EDGE-09 cancel-mid-block
  leg, EDGE-01..07/19/28/29 → **Phase 25** (D-24-02).
- Streaming `RecordBatchReader` results → v1.4.x.
- The `[async]` optional-dependency extra + PKG-04 anyio-absent CI job → **Phase 26**. The PEP
  562 lazy guard ships in Phase 24; the extra declaration ships in Phase 26.
- Live 13-backend smoke matrix → deferred future phase. D-24-04 proves genericity structurally
  (zero backend code in `_async/` + AST/name guard) + DuckDB real driver + Snowflake cassette.
- EDGE-16 (cancel-bypasses-lock) → DROPPED (no per-connection lock ships, D-24-03).
