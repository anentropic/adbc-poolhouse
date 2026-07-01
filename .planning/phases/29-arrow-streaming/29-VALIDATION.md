---
phase: 29
slug: arrow-streaming
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-01
validated: 2026-07-01
---

# Phase 29 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source of the coverage map: `29-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + anyio (asyncio & trio parametrized via `anyio_backend`) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/async/ -x -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Type gate** | `.venv/bin/basedpyright` (strict, 0 errors — PKG-01) |
| **Import-lint gate** | `.venv/bin/pytest tests/test_pkg_import_guard.py -q` (no `import asyncio` / bare `to_thread` in `_async/` — PKG-03) |
| **Estimated runtime** | ~30–60 seconds (async subset); full suite ~2–3 min |

> Backend matrix: every reader test parametrizes `asyncio × trio` and, where a live
> C-stream is required, `DuckDB × Snowflake-cassette`. See `tests/async/conftest.py::anyio_backend`.

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/async/ -x -q`
- **After every plan wave:** Run `.venv/bin/pytest -q` + `.venv/bin/basedpyright`
- **Before `/gsd-verify-work`:** Full suite green, basedpyright 0 errors, import-lint pass
- **Max feedback latency:** 60 seconds (async subset)

---

## Per-Task Verification Map

> Populated during planning / by the Nyquist auditor once task IDs exist. Each row maps
> a task to the requirement it proves and the automated command that proves it. The
> requirement → observable mapping below is the authoritative source (from RESEARCH.md).

| Requirement | Secure/Correct Behavior (observable) | Test Type | Backend Matrix |
|-------------|--------------------------------------|-----------|----------------|
| STREAM-01 | `await cursor.fetch_record_batch()` returns `AsyncRecordBatchReader` | unit + integration | asyncio×trio, DuckDB |
| STREAM-02 | `async for batch` yields `pyarrow.RecordBatch`; each pull offloaded through the limiter | unit (stub counts limiter acquires) + integration | asyncio×trio, DuckDB |
| STREAM-03 | `schema` passthrough property; blocking members replaced by async twins; async CM closes offloaded-and-shielded | unit | asyncio×trio |
| STREAM-04 | drain-then-checkin yields correct rows; read-after-checkin → native `ArrowInvalid` (never segfault) | integration | asyncio×trio, DuckDB + Snowflake cassette |
| STREAM-05 | cancel/timeout on a pull fires `adbc_cancel` once, invalidates → `pool.checkedout() == 0` | integration + stub | asyncio×trio, DuckDB |
| STREAM-06 | foreign op while reader live raises `ConnectionBusyError`; reader's own pulls exempt (`_reader_open` reentrancy) | unit + integration | asyncio×trio |
| EDGE-33 | read-after-close / read-after-checkin surfaces driver's native closed-stream error | integration | asyncio×trio, DuckDB + Snowflake cassette |
| EDGE-20 | exception during shielded cleanup chains body error via `__context__` and still releases/invalidates | unit | asyncio×trio |
| EDGE-22 | unclosed reader `__del__` emits `ResourceWarning` | unit (`pytest.warns`) | asyncio |
| EDGE-23 | happy path (context-manager close) emits neither `ResourceWarning` nor "coroutine never awaited" `RuntimeWarning` | unit (`recwarn`) | asyncio×trio |
| PKG-01 | `_SyncCursor` Protocol gains `fetch_record_batch`; new `_SyncReader` Protocol; basedpyright strict 0 errors | type check | — |
| PKG-03 | import-lint guard passes over `_async/_reader.py` (no `import asyncio`, no bare `to_thread`) | lint test | — |

*Status per task: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — tracked in PLAN task `<acceptance_criteria>`.*

---

## Wave 0 Requirements

- [ ] Extend `tests/_async_harness/stubs.py` — add stub `fetch_record_batch` + stub reader satisfying `_SyncReader` (`schema`, `read_next_batch`, `close`), with configurable batch sequence, `StopIteration`-at-end, and blocking/cancel hooks
- [ ] `tests/async/test_stream_reader.py` (or equivalent) — failing stubs for STREAM-01..06, EDGE-20/22/23/33
- [ ] Wave-0 Snowflake cassette smoke (A1): confirm the checked-in Snowflake cassette can replay a streaming `fetch_record_batch`; if absent, scope the Snowflake leg to the `ArrowInvalid` read-after-checkin path only and record the decision

*Framework already installed — no install task needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Snowflake streaming `fetch_record_batch` recording | STREAM-04 / EDGE-33 (Snowflake leg) | Requires live Snowflake credentials to re-record the cassette; CI replays the checked-in cassette | Record with live creds per project cassette-recording flow, commit cassette; CI replay is automated thereafter |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (stub reader + Snowflake cassette smoke)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-01

---

## Validation Audit 2026-07-01

Post-execution Nyquist audit (State A). Every phase requirement has a green automated
test or a documented type/import gate; the only manual-only items are the Snowflake
cassette legs (A1: the checked-in cassette cannot replay a streaming `fetch_record_batch`,
so those legs are `@pytest.mark.snowflake` manual re-record; DuckDB carries the mandatory
STREAM-04/EDGE-33 coverage). No coverage gaps required auditor gap-filling.

| Requirement | Coverage | Test / Gate |
|-------------|----------|-------------|
| STREAM-01 | COVERED | `test_reader_stream.py` (real driver + stub) |
| STREAM-02 | COVERED | `test_reader_stream.py` — off-loop pull proof (made non-vacuous in `c45022a`) |
| STREAM-03 | COVERED | `test_reader_stream.py` / `test_reader_close.py` (async CM + `schema`) |
| STREAM-04 | COVERED | `test_reader_lifetime.py` (DuckDB); Snowflake leg manual-only |
| STREAM-05 | COVERED | `test_reader_cancel.py` (`adbc_cancel==1`, `checkedout()==0`) |
| STREAM-06 | COVERED | `test_reader_busy.py` + `test_reader_guard.py` (`ConnectionBusyError`) |
| EDGE-33 | COVERED | `test_reader_lifetime.py` + `test_reader_cassette_smoke.py` (DuckDB); Snowflake leg manual-only |
| EDGE-20 | COVERED | `test_reader_close.py` — shielded-close-raises path (made real in `c45022a`) |
| EDGE-22 | COVERED | `test_reader_resource.py` (`ResourceWarning` via `pytest.warns`) |
| EDGE-23 | COVERED | `test_reader_resource.py` (happy path: no warning) |
| PKG-01 | COVERED | `.venv/bin/basedpyright` strict — 0 errors |
| PKG-03 | COVERED | `test_pkg_import_guard.py` + `test_async_guard.py` (no `import asyncio` / bare `to_thread`) |

| Metric | Count |
|--------|-------|
| Requirements audited | 12 |
| COVERED (automated) | 12 |
| PARTIAL | 0 |
| MISSING | 0 |
| Manual-only (documented) | Snowflake legs of STREAM-04 / EDGE-33 |

Gates re-run at audit time: full suite 489 passed / 6 skipped; async suite looped 4× = 0 hangs;
basedpyright strict 0 errors; import-lint 3 passed.

**Non-blocking note (from code review WR-03):** cancel/lifetime tests leave readers unclosed,
so `__del__` emits `ResourceWarning`. Harmless today (no `filterwarnings = ["error::ResourceWarning"]`
in CI); would need `reader._detached = True` post-cancel (or `await reader.close()` after
`invalidate()`) if a strict warning gate is later added. Tracked, not a coverage gap.
