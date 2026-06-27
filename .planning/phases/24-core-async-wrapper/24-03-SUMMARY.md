---
phase: 24-core-async-wrapper
plan: 03
subsystem: async-core
tags: [async, anyio, offload, cursor, connection, in-use, shield, arrow]
requires:
  - adbc_poolhouse._async._offload.offload
  - adbc_poolhouse._async._pool.AsyncPool
  - adbc_poolhouse._exceptions.ConnectionBusyError
  - adbc_poolhouse._pool_factory._release_arrow_allocators (reset event)
provides:
  - adbc_poolhouse._async._connection.AsyncConnection (full body)
  - adbc_poolhouse._async._cursor.AsyncCursor (full body)
  - adbc_poolhouse._async._cursor._SyncCursor (structural dbapi-cursor Protocol)
affects:
  - adbc_poolhouse._async._pool (AsyncPool.connect now returns a working AsyncConnection)
tech-stack:
  added: []
  patterns:
    - "_in_use bool check-and-set (no await between read and write) for aliasing rejection"
    - "cursor guards the PARENT connection's _in_use flag (concurrent cursor use = concurrent connection use)"
    - "shielded checkin via anyio.CancelScope(shield=True) routing through fairy.close() reset event"
    - "sync cursor() + sync description/rowcount/arraysize @property passthroughs (no offload)"
    - "materialized pyarrow.Table return from fetch_arrow_table (no streaming reader)"
    - "driver-agnostic structural Protocol (_SyncCursor) + cast at the SQLAlchemy boundary"
key-files:
  created:
    - src/adbc_poolhouse/_async/_cursor.py
  modified:
    - src/adbc_poolhouse/_async/_connection.py
decisions:
  - "Open Q1/A3 settled: the SQLAlchemy fairy proxies commit/rollback/cursor/close directly to the dbapi connection (probed against DuckDB) — no driver_connection unwrap needed"
  - "AsyncCursor split into its own module src/adbc_poolhouse/_async/_cursor.py (Plan 02 had both classes co-located in _connection.py); plan files_modified lists both files, the split matches it"
  - "_SyncCursor structural Protocol added to type the driver-agnostic dbapi cursor surface; AsyncConnection.cursor() casts SQLAlchemy's generic DBAPICursor to it at the boundary (SQLAlchemy types the cursor narrower than the ADBC runtime reality)"
  - "Constructor signatures honored exactly as frozen by Plan 02: AsyncConnection(fairy, limiter), AsyncCursor(sync_cursor, limiter, owner) — the plan body's AsyncCursor(.., self) / AsyncConnection(self, ..) prose was the contradicting form; the frozen contract wins"
metrics:
  duration: 6min
  tasks: 2
  files: 2
  completed: 2026-06-28
---

# Phase 24 Plan 03: AsyncConnection / AsyncCursor bodies Summary

The behavioral heart of the async surface: the `_in_use` aliasing-rejection flag, a
synchronous `cursor()`, the full offloaded DBAPI surface, a materialized
`fetch_arrow_table`, and a shielded check-in that fires the existing pool reset event.
`AsyncPool.connect → cursor → execute → fetch_arrow_table → checkin` now works end to
end with every structural pitfall except cancellation (Phase 25) closed.

## What Was Built

### Task 1 — AsyncConnection (`d876c16`, docstring fixup `2cfeac5`)

- **`_enter_offload`/`_exit_offload`** — the `_in_use` guard. `_enter_offload` reads
  `_in_use` and sets it `True` in one synchronous span with NO `await` between the read
  and the write, so two tasks can never both observe `False` and both proceed on the
  single-threaded loop (Pitfall 3). A second concurrent caller raises
  `ConnectionBusyError` (D-24-03). `_in_use` is a plain bool — never a serializing lock.
- **`cursor()`** — a plain `def` (NOT `async`, ACONN-03): the dbapi `cursor()` does no
  I/O, so it is not offloaded. Returns `AsyncCursor(<fairy cursor>, self._limiter, self)`,
  passing the connection as `owner` so the cursor guards this connection's `_in_use`.
- **`commit`/`rollback`/`close`** (ACONN-04/05) — each brackets one `offload(...)` with
  `_enter_offload()` / `finally: _exit_offload()`. `close` (and `__aexit__`) wrap the
  offloaded `fairy.close()` in `anyio.CancelScope(shield=True)` (ACONN-02), which fires
  the pool `reset` listener (`_release_arrow_allocators`) unchanged (ACONN-06) — no new
  cleanup path.
- **`__aenter__`/`__aexit__`** — `__aenter__` returns self. `__aexit__` always runs the
  shielded `fairy.close()` (reclaim-on-failure), so `checkedout()` returns to 0 even if
  the body or setup raised (EDGE-18).

### Task 2 — AsyncCursor (`47a9400`)

- **Offloaded DBAPI surface** — `execute` (ACUR-01), `executemany` (ACUR-02),
  `fetchone`/`fetchmany`/`fetchall` (ACUR-03), `fetch_arrow_table` (ACUR-04), `close`
  (ACUR-05). Each runs exactly one `offload(...)` through the parent's limiter, bracketed
  by the **parent connection's** `_enter_offload`/`_exit_offload` — so concurrent cursor
  use raises `ConnectionBusyError` via the connection's single-task flag (EDGE-15;
  concurrent cursor use IS concurrent connection use).
- **`fetch_arrow_table`** returns the dbapi result unchanged: a fully-materialized
  `pyarrow.Table` that owns its own buffers, readable after check-in (ACUR-04/EDGE-21) —
  no wrapper, no `RecordBatchReader` (Pitfall 7).
- **`description`/`rowcount`/`arraysize`** — plain sync `@property` passthroughs (ACUR-07),
  never offloaded and never `async` (Pitfall 4).
- **No re-wrap** (ACUR-06/EDGE-17) — nothing catches the worker error; the `offload`
  chokepoint re-raises the exact type + traceback.
- **`_SyncCursor` Protocol** — a structural type for the dbapi cursor surface, declared
  driver-agnostically (the dbapi module is resolved dynamically by the sync core).
  `close()` is offloaded inside `anyio.CancelScope(shield=True)`; `__aexit__` calls it.

## Verification Results

| Check | Result |
|-------|--------|
| `.venv/bin/basedpyright src/adbc_poolhouse/_async/` | 0 errors |
| `.venv/bin/basedpyright src/adbc_poolhouse/__init__.py` | 0 errors |
| `scan_async_package('src/adbc_poolhouse/_async')` | `[]` (guard-clean) |
| `.venv/bin/ruff check src/adbc_poolhouse/_async/` | clean |
| `.venv/bin/mkdocs build --strict` | passes |
| full sync suite `.venv/bin/pytest -q` | 318 passed, 2 skipped |
| `def cursor` is a plain `def` (no `async`) | confirmed (line 133) |
| `CancelScope(shield=True)` in `_connection.py` executable | 2 (`close`, `__aexit__`) |
| `anyio.Lock` token in `_connection.py` | 0 |
| `description`/`rowcount`/`arraysize` are non-`async` `@property` | confirmed |
| `offload(` + `_enter_offload`/`_exit_offload` in `_cursor.py` | both present |
| behavioral smoke (happy path, materialized table, aliasing reject, checkedout()->0) | all OK |

The behavioral smoke run (DuckDB, not part of the committed suite) confirmed:
`connect → cursor → execute → fetch_arrow_table` returns a `pyarrow.Table` whose contents
are readable after check-in; a re-entrant `_enter_offload` raises `ConnectionBusyError`;
and `checkedout()` is 0 after `close()`. The formal EDGE proofs land in Plan 04.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan body constructor calls contradicted the frozen Plan 02 contract**
- **Found during:** Tasks 1 & 2
- **Issue:** The plan prose said `AsyncCursor(self._fairy.cursor(), self)` and
  `AsyncConnection(self, fairy, limiter)`, but Plan 02 froze and shipped
  `AsyncConnection(fairy, limiter)` and `AsyncCursor(sync_cursor, limiter, owner)` (its
  SUMMARY explicitly calls these "frozen"). Following the prose would have broken
  `AsyncPool.connect`, which already calls `AsyncConnection(fairy, self._limiter)`.
- **Fix:** Implemented against the frozen contract. The cursor receives `(sync_cursor,
  limiter, owner)`; `owner` is the parent `AsyncConnection`, used exactly as the plan
  intends (guarding the parent's `_in_use`). Semantically identical to the plan's intent.
- **Files modified:** `_connection.py`, `_cursor.py`
- **Commits:** `d876c16`, `47a9400`

**2. [Rule 3 - Blocking] `sync_cursor: object` produced 22 "unknown type" basedpyright errors**
- **Found during:** Task 2
- **Issue:** The Plan 02 contract annotated the cursor param as `object`, so every
  `self._cursor.<method>` access was `reportUnknownMemberType`/`reportUnknownArgumentType`
  under basedpyright-strict (22 errors). The acceptance gate requires 0 errors.
- **Fix:** Added a structural `_SyncCursor` Protocol describing the dbapi cursor surface
  and typed the param with it (constructor name/order unchanged — still
  `(sync_cursor, limiter, owner)`). This removed all 22 errors and made the
  `# pyright: ignore` hacks unnecessary (none remain).
- **Files modified:** `_cursor.py`
- **Commit:** `47a9400`

**3. [Rule 3 - Blocking] SQLAlchemy types the fairy's cursor narrower than the ADBC runtime**
- **Found during:** Task 1
- **Issue:** `self._fairy.cursor()` is statically `DBAPICursor` (generic PEP 249), which
  lacks `fetch_arrow_table` — so passing it to `AsyncCursor(_SyncCursor)` failed
  `reportArgumentType`. At runtime the fairy's cursor IS the ADBC cursor.
- **Fix:** `cast("_SyncCursor", self._fairy.cursor())` at the connection boundary, with a
  comment explaining the SQLAlchemy-narrow vs ADBC-runtime mismatch. Single localized cast.
- **Files modified:** `_connection.py`
- **Commit:** `d876c16`

**4. [Rule 1 - Acceptance grep] literal `anyio.Lock` token appeared in a docstring negation**
- **Found during:** post-Task-1 acceptance check
- **Issue:** The Task 1 criterion requires `grep -c "anyio.Lock" == 0`, but the `_in_use`
  attribute docstring contained the literal phrase "never an `anyio.Lock`" — count was 1.
- **Fix:** Reworded the prose to "plain bool, never a serializing lock" (same meaning,
  no literal token). Doc-only, no behavior change.
- **Files modified:** `_connection.py`
- **Commit:** `2cfeac5`

### Interpretation notes (not code changes)

- The plan's `<verify>` and acceptance criteria are intentionally **structural** for this
  plan (basedpyright + guard + source greps + mkdocs), with the behavioral EDGE proofs
  (EDGE-15/17/18/21, ACUR/ACONN happy path) explicitly deferred to Plan 04. This plan
  honors that: the structural gates pass, and a non-committed DuckDB smoke run was used as
  a sanity check only.
- Open Q1/A3 (whether the fairy needs a `driver_connection` unwrap for commit/rollback)
  was settled empirically: the SQLAlchemy `_ConnectionFairy` proxies `commit`, `rollback`,
  `cursor`, and `close` straight through to the dbapi connection (probed against the DuckDB
  driver), so the bodies call `self._fairy.<method>` directly — matching how the sync suite
  calls `fairy.cursor()` / `fairy.close()`.

## Threat Model Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-24-03-EOP (concurrent aliasing) | mitigate | DONE — `_in_use` check-and-set (no intervening await) raises `ConnectionBusyError` on the 2nd entry; EDGE-15 proof is Plan 04 |
| T-24-03-DOS (leak on cancel / setup failure) | mitigate | DONE — shielded checkin + `__aexit__` reclaim-on-failure; smoke confirms `checkedout()`->0 |
| T-24-03-INFO (altered traceback) | mitigate | DONE — no re-wrap anywhere; `offload` re-raises verbatim |
| T-24-03-LIFE (use-after-checkin reader) | mitigate | DONE — `fetch_arrow_table` returns a self-owning materialized `pyarrow.Table`, not a reader; smoke reads it after checkin |
| T-24-03-RACE (await injected into check-and-set) | mitigate | DONE — single synchronous check-and-set span; reviewed in source, EDGE-15 is the behavioral proof |
| T-24-03-SC (installs) | N/A | no new packages |

No new security surface introduced beyond the plan's threat model.

## Authentication Gates

None.

## Environment Note

The pre-commit `basedpyright` hook is wired as `uv run basedpyright`. Under the command
sandbox, `uv run` panics at macOS `system-configuration` (NULL SCDynamicStore) — the
documented `uv-sandbox-workaround`. Direct `.venv/bin/basedpyright` is clean; the three
commits were made with the sandbox disabled so the `uv run` hook could reach system
config. All hooks (ruff, ruff-format, basedpyright, blacken-docs, detect-secrets) passed.

## Known Stubs

None. The Plan 02 `NotImplementedError` skeletons are fully replaced with working bodies.

## Next Steps

- **Plan 04 (24-04):** Behavioral EDGE coverage — EDGE-15 (max_concurrent==1 via the
  `_in_use` flag), EDGE-17 (traceback fidelity), EDGE-18 (no leak over N iterations),
  EDGE-21 (`pyarrow.Table` lifetime after checkin), plus the ACONN/ACUR happy path.
- **Phase 25:** Cancellation (`adbc_cancel`/invalidate). The shield ships now; the
  cooperative cancel join is deferred there per the roadmap.

## Self-Check: PASSED

`src/adbc_poolhouse/_async/_connection.py` and `_cursor.py` present on disk; all three
commits (`d876c16`, `47a9400`, `2cfeac5`) found in git history.
