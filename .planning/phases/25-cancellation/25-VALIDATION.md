---
phase: 25
slug: cancellation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-28
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. This is the milestone's highest-risk correctness item; the sampling strategy below is deliberately strict (×20 loop, wall-clock watchdog, dual-backend asyncio↔trio).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` + anyio pytest plugin; dual-backend via the `anyio_backend` fixture (asyncio + trio MockClock), already in `tests/async/conftest.py` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (no separate pytest.ini) |
| **Quick run command** | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -x -q` |
| **Full suite command** | `.venv/bin/pytest -q` (sync + harness + async, both backends) |
| **Estimated runtime** | ~30–60 seconds (full suite); ×20 cancel loop ~ a few minutes |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/async -x -q` + `.venv/bin/ruff check` + `.venv/bin/basedpyright`
- **After every plan wave:** Run `.venv/bin/pytest -q` (both backends) — for the cancel waves, run it in a **×20 loop**, 0 hangs/failures required (MEMORY: single-shot missed a ~33% deadlock in Phase 23; verify with `rc=$?` + grep the pass line, **never** `if ! pytest` — zsh `!` gotcha)
- **Before `/gsd-verify-work`:** Full suite green + ×20 loop clean + `.venv/bin/basedpyright` 0 errors + `.venv/bin/ruff check`/`format --check` clean + `.venv/bin/mkdocs build --strict` passes (docs gate, phase ≥7) + `scan_async_package("src/adbc_poolhouse/_async/") == []` incl. the new `banned-asyncio-cancelled-error` rule
- **Max feedback latency:** ~60 seconds for the quick path; the ×20 cancel loop runs at wave merge

---

## Observable Signals the cancel tests MUST assert

| Signal | Source | Asserted value (canonical cancel) |
|--------|--------|-----------------------------------|
| `adbc_cancel_call_count` | `BlockingStubCursor` (lock-guarded) | `== 1` on EDGE-02/06; `== 0` on EDGE-01/07; `== 1` (not 2) on EDGE-04 double-cancel |
| `observed_cancel` | `BlockingStubCursor` | `True` after a cancelled block; `False` on EDGE-07 (op finished first) |
| `invalidate_call_count` | `BlockingStubConnection` (**NEW — Wave 0**) | `== 1` after a cancelled scope (EDGE-02/04/05); `== 0` on EDGE-01/07 and on a genuine `AdbcError` |
| `pool.checkedout()` | real-driver DuckDB pool | `== 0` after a cancelled scope (CANCEL-02, EDGE-02/05) |
| `pool._limiter.borrowed_tokens` | `AsyncPool._limiter` | `== 0` after a cancelled `cancellable_offload` (EDGE-09 cancel-mid-block leg, ×50) |
| Surfaced exception identity | caller `pytest.raises(...)` | `TimeoutError` for `fail_after`; nothing for `scope.cancel()`; the bare `get_cancelled_exc_class()` instance escapes (EDGE-03); a bare `AdbcError` (not `ExceptionGroup`) on the non-cancel path (EDGE-19) |
| `(adbc_cancel_count, invalidate_count, checkedout_after)` tuple | aggregate per backend | EQUAL under asyncio and trio (EDGE-29) |
| `real_clock_watchdog` `tripped[0]` | wall-clock side thread | `False` (no worker stranded) in every cancel test |
| `scan_async_package(_async/)` | AST guard | `== []` incl. the new `banned-asyncio-cancelled-error` rule (EDGE-28) |

---

## Per-Task Verification Map

> Task IDs are assigned by the planner; this maps each phase requirement to its automated proof. The planner's PLAN.md tasks must carry these as `<automated>` verify commands.

| Plan | Wave | Requirement | Behavior | Test Type | Automated Command | File Exists |
|------|------|-------------|----------|-----------|-------------------|-------------|
| harness | 0 | (prereq) | stub `invalidate()` + `invalidate_call_count` | unit | `.venv/bin/pytest tests/_async_harness -q` | ❌ W0 |
| guard | 0 | EDGE-28 | `banned-asyncio-cancelled-error` AST rule | static | `.venv/bin/pytest tests/async/test_async_guard.py -q` | ⚠️ guard exists; rule ❌ W0 |
| cancel | 1 | EDGE-01 | cancel before offload — no `execute`, no `adbc_cancel`, clean | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k before -q` | ❌ W0 |
| cancel | 1 | EDGE-02 / CANCEL-01/02 | cancel during block — `adbc_cancel`×1, invalidate, `checkedout()==0` | unit + integration | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k during -q` | ❌ W0 |
| cancel | 1 | EDGE-03 | framework cancel class escapes; no trio hang | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k escapes -q` | ❌ W0 |
| cancel | 1 | EDGE-04 / CANCEL-03 | double-cancel idempotent — one `adbc_cancel`, one invalidate, one cancel exc | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k double -q` | ❌ W0 |
| cancel | 1 | EDGE-05 | cancel during `__aexit__`/checkin — `checkedout()==0` conn+cursor | unit + integration | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k checkin -q` | ❌ W0 |
| cancel | 1 | EDGE-06 | `fail_after` vs `scope.cancel()` parity (type differs only) | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k parity -q` | ❌ W0 |
| cancel | 1 | EDGE-07 | `move_on_after` on finished op — `cancelled_caught` False, no `adbc_cancel` | unit (stub) | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k finished -q` | ❌ W0 |
| eg | 1 | EDGE-19 | genuine `AdbcError` unwrapped from EG; `checkedout()==0` | integration (DuckDB) | `.venv/bin/pytest tests/async/test_edge_exceptiongroup.py -q` | ❌ W0 |
| limiter | 1 | EDGE-09 (cancel leg) | `borrowed_tokens==0` after cancelled offload (×50) | unit (stub) | `.venv/bin/pytest tests/async/test_edge_limiter.py -k cancel_token -q` | ⚠️ file exists; leg ❌ |
| parity | 1 | EDGE-29 / CANCEL-04 | `(adbc_cancel, invalidate, checkedout)` tuple equal asyncio↔trio | unit (stub) | `.venv/bin/pytest tests/async/test_edge_backend_parity.py -q` | ❌ W0 |
| real | 1 | CANCEL-01/02 (real driver) | end-to-end cancel→`adbc_cancel`→invalidate→`checkedout()==0` on DuckDB | integration | `.venv/bin/pytest tests/async/test_edge_cancel_depth.py -k duckdb -q` | ❌ W0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] **Harness:** add `invalidate()` + `invalidate_call_count` (lock-guarded, D-04 style) to `BlockingStubConnection` in `tests/_async_harness/stubs.py` — **prerequisite** for stub-backed EDGE-02/04/05/29
- [ ] **Guard:** add the `banned-asyncio-cancelled-error` rule to `tests/_async_harness/guard.py` + a self-test for it
- [ ] `tests/async/test_edge_cancel_depth.py` — EDGE-01/02/03/04/05/06/07 (stub + a DuckDB real-driver leg)
- [ ] `tests/async/test_edge_exceptiongroup.py` — EDGE-19 (DuckDB bare-`AdbcError` unwrap)
- [ ] `tests/async/test_edge_backend_parity.py` — EDGE-29 tuple equality (session-scoped dict + cross-leg assert)
- [ ] Extend `tests/async/test_edge_limiter.py` with the EDGE-09 cancel-mid-block ×50 leg
- [ ] Extend `tests/async/test_async_guard.py` to assert the new rule fires on synthetic `asyncio.CancelledError` and that real `_async/` stays clean

*Existing `duckdb_async_pool`, `make_stub_async_connection`, `await_inside`, `real_clock_watchdog`, and `virtual_clock` cover everything else — no new fixtures/helpers beyond the stub `invalidate()` and the guard rule.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | All phase behaviors have automated verification. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (stub `invalidate()`, guard rule, new test files)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s (quick path); ×20 cancel loop at wave merge
- [ ] `nyquist_compliant: true` set in frontmatter once Wave 0 lands

**Approval:** pending
