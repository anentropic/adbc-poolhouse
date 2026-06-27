---
phase: 24
slug: core-async-wrapper
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-27
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0.0 + anyio pytest plugin (dual-backend via `anyio_backend` fixture: asyncio + trio) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest tests/async -x -q` |
| **Full suite command** | `.venv/bin/pytest -q` (sync + harness + async) |
| **Loop-run (REQUIRED for concurrency)** | `for i in $(seq 1 20); do .venv/bin/pytest tests/async -q \|\| break; done` — 0 hangs across 20 runs |
| **Estimated runtime** | ~60-90s full suite; ~10-20s `tests/async` quick run |

> Sandbox note (MEMORY): prefer `.venv/bin/<tool>` over `uv run <tool>` for mkdocs/pytest/basedpyright.

---

## Sampling Rate

- **After every task commit:** `.venv/bin/pytest tests/async -x -q` + `.venv/bin/ruff check` + `.venv/bin/basedpyright src/adbc_poolhouse/_async/`.
- **After every plan wave:** full suite `.venv/bin/pytest -q` (both backends). For the concurrency-touching waves (Plan 01 harness, Plan 04 EDGE) run the x20 loop — **0 hangs required** (single-shot masked a ~33% deadlock in Phase 23 — see [[feedback_loop_test_flaky_concurrency]]).
- **Before `/gsd-verify-work`:** full suite green + `.venv/bin/basedpyright` 0 errors + `.venv/bin/ruff check`/`format --check` clean + `.venv/bin/mkdocs build --strict` passes (docs gate, phase >= 7).
- **Concurrency/EDGE tests:** loop-run x20 with `anyio.fail_after` watchdog on every concurrency body.
- **Max feedback latency:** < 90s (full suite).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-T1 | 01 | 1 | TEST-05 | T-24-01-TR | re-armable gate + entered-after-block; flags lock-guarded | unit (harness self-test) | `.venv/bin/pytest tests/_async_harness/test_stubs.py -x -q` | ✅ MOD | ⬜ pending |
| 01-T2 | 01 | 1 | TEST-05 | T-24-01-DOS | execute-then-fetch re-arm; x20 loop 0 hangs | unit (harness self-test) | `for i in $(seq 1 20); do .venv/bin/pytest tests/_async_harness/test_harness.py -q \|\| break; done` | ✅ MOD | ⬜ pending |
| 02-T1 | 02 | 1 | CORE-01, EDGE-17 | T-24-02-INFO | single offload chokepoint; no re-wrap; ConnectionBusyError exported; PEP 562 lazy | unit + import | `.venv/bin/pytest tests/ -k "exceptions or init" -q && .venv/bin/python -c "import adbc_poolhouse; adbc_poolhouse.ConnectionBusyError"` | ❌ W0 | ⬜ pending |
| 02-T2 | 02 | 1 | CORE-02, CORE-04, APOOL-01/02/03, ACONN-01 | T-24-02-DOS | dedicated limiter; reuse _create_pool_impl; shielded close | static (type+guard) | `.venv/bin/basedpyright src/adbc_poolhouse/_async/ && python -c "from tests._async_harness.guard import scan_async_package as s; assert s('src/adbc_poolhouse/_async')==[]"` | ❌ W0 | ⬜ pending |
| 03-T1 | 03 | 2 | ACONN-02/03/04/05/06, EDGE-15, EDGE-18 | T-24-03-EOP | _in_use no-await check-and-set; shielded checkin via reset event; reclaim on failure | static (type+guard) | `.venv/bin/basedpyright src/adbc_poolhouse/_async/ && python -c "from tests._async_harness.guard import scan_async_package as s; assert s('src/adbc_poolhouse/_async')==[]"` | ❌ W0 | ⬜ pending |
| 03-T2 | 03 | 2 | ACUR-01..07, ACUR-06, EDGE-17, EDGE-21 | T-24-03-LIFE | offloaded DBAPI surface; materialized pyarrow.Table; sync props | static (type+guard) | `.venv/bin/basedpyright src/adbc_poolhouse/_async/ && python -c "from tests._async_harness.guard import scan_async_package as s; assert s('src/adbc_poolhouse/_async')==[]"` | ❌ W0 | ⬜ pending |
| 04-T1 | 04 | 3 | APOOL-01, ACONN-01/02/03/04/05, ACUR-01/04/07, CORE-04 | T-24-04-COLL | happy path (real DuckDB) + sync surface + lifecycle, both backends; Snowflake cassette | integration | `.venv/bin/pytest tests/async/test_async_lifecycle.py -q` | ❌ W0 | ⬜ pending |
| 04-T2 | 04 | 3 | EDGE-09, EDGE-10, EDGE-11, EDGE-12, EDGE-15 | T-24-04-DOS | token accounting, queued-cancel recovery, no deadlock, bound, aliasing reject; loop-stable | unit/integration (stub+real) | `for i in $(seq 1 20); do .venv/bin/pytest tests/async/test_edge_limiter.py tests/async/test_edge_aliasing.py -q \|\| break; done` | ❌ W0 | ⬜ pending |
| 04-T3 | 04 | 3 | EDGE-17, EDGE-18, EDGE-21, EDGE-25, EDGE-26, CORE-03, CORE-04 | T-24-04-TAMPER | error fidelity, no leak, Arrow-after-checkin, off-loop, no-starve, guard (no asyncio/bare-to_thread/backend-names) | unit + static (AST) | `.venv/bin/pytest tests/async/test_edge_exceptions.py tests/async/test_edge_resource.py tests/async/test_edge_loophygiene.py tests/test_async_guard.py -q` | ❌ W0 | ⬜ pending |
| 05-T1 | 05 | 4 | APOOL-01, ACONN-03, ACUR-04 | T-24-05-INFO | complete docstrings + Example blocks; no RST | static (lint+docs) | `.venv/bin/ruff check src/adbc_poolhouse/_async/ && .venv/bin/mkdocs build --strict` | ❌ W0 | ⬜ pending |
| 05-T2 | 05 | 4 | EDGE-15, CORE-04 | T-24-05-EOP | async guide + forbidden-aliasing antipattern + honest concurrency framing | static (docs) | `.venv/bin/mkdocs build --strict` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> "Wave 0" here = the harness prerequisite (Plan 01) that MUST land and merge before the
> execute-then-fetch / gated-concurrency EDGE tests (Plan 04) can run without deadlock, plus
> the test scaffolds those EDGE tests need. Plan 01 is wave 1 in the dependency graph but is
> the Nyquist Wave-0 gate for the concurrency suite.

- [x] **Harness redesign (Plan 01):** re-armable cursor gate + `entered`-after-block (D-CF-01 / WR-01) in `tests/_async_harness/stubs.py` + `gating.py`; WR-03 (flags under lock) + IN-03 (public `closed`). Prerequisite for execute-then-fetch EDGE tests.
- [x] **anyio_backend fixture + pool fixtures (Plan 04 T1):** `tests/async/conftest.py` mirroring the harness conftest (asyncio+trio) + real DuckDB `AsyncPool` fixture + stub-backed `AsyncConnection`/`AsyncPool` fixtures. MUST NOT live in the root conftest (Pitfall 6).
- [x] **Happy-path lifecycle test (Plan 04 T1):** `tests/async/test_async_lifecycle.py` — covers the bulk of CORE/APOOL/ACONN/ACUR.
- [x] **Five EDGE test files (Plan 04 T2/T3):** `tests/async/test_edge_{limiter,aliasing,exceptions,resource,loophygiene}.py`.
- [x] **Guard extension (Plan 04 T3):** point `scan_async_package` at the real `src/adbc_poolhouse/_async/`; add the `no-backend-specific-names` rule (D-24-04, Open Q2).

All "MISSING" references in the RESEARCH Test Map are created by Plan 01 (harness) and Plan 04
(tests). No production code in any plan depends on a test that does not yet exist within its
own or an earlier wave.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none) | — | All phase behaviors have automated verification | — |

> Humanizer pass on docs prose (Plan 05) is a human-judgment review, but its mechanical gate
> (no banned terms, em-dash limit) is grep-checkable; treat it as automated-assisted.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (harness + test scaffolds in Plan 01 / Plan 04)
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned — pending execution
