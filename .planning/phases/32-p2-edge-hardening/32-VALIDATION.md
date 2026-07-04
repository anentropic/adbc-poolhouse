---
phase: 32
slug: p2-edge-hardening
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-02
validated: 2026-07-04
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + anyio plugin (`@pytest.mark.anyio`) + pytest-repeat + pytest-timeout |
| **Config file** | `pyproject.toml` (dev-group deps); async fixtures in `tests/async/conftest.py` |
| **Quick run command** | `.venv/bin/pytest tests/async/test_edge_*.py -x -q` |
| **Full suite command** | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/ -q` |
| **Estimated runtime** | ~30s quick / ~3–5 min full x20 loop |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/async/test_edge_*.py -x -q`
- **After every plan wave:** Run `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/ -q` (the 0-hang loop gate)
- **Before `/gsd-verify-work`:** Full async suite green under the x20 loop on **Linux CI** — the real gate for EDGE-24/31/32 (cancel/lost-wakeup races can pass 20/20 on macOS but hang on Linux)
- **Max feedback latency:** ~30 seconds (quick) / ~5 min (full loop)

---

## Per-Task Verification Map

> Task IDs are assigned by the planner; rows are keyed by requirement + target test file. Every EDGE item runs under both asyncio and trio via the `anyio_backend` fixture.

| Requirement | Wave | Target Test File | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|------|------------------|-----------------|-----------|-------------------|-------------|--------|
| EDGE-08 | 1 | `tests/async/test_edge_checkpoint.py` | Cancel set before a new-method offload is delivered at the boundary; `fn` never runs (trio = discriminator) | unit (dual-backend) | `.venv/bin/pytest tests/async/test_edge_checkpoint.py -x` | ✅ | ✅ green |
| EDGE-13 | 1 | `tests/async/test_edge_contextvars.py` | contextvar set before a new-method offload is visible in the worker (copied in) | unit (dual-backend) | `.venv/bin/pytest tests/async/test_edge_contextvars.py -k copied_in -x` | ✅ | ✅ green |
| EDGE-14 | 1 | `tests/async/test_edge_contextvars.py` | worker contextvar mutation does not leak back to the caller after the offload | unit (dual-backend) | `.venv/bin/pytest tests/async/test_edge_contextvars.py -k no_leak -x` | ✅ | ✅ green |
| EDGE-31 | 1 | `tests/async/test_edge_timeout_precision.py` | `move_on_after(0)` still cancels a blocked streaming pull / ingest (`adbc_cancel` once, invalidate) | integration (dual-backend, looped) | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_edge_timeout_precision.py -k move_on_after_zero` | ✅ | ✅ green |
| EDGE-32 | 1 | `tests/async/test_edge_timeout_precision.py` | op completing at deadline−ε is NOT over-cancelled (no `adbc_cancel`, no invalidate, clean return) — streaming pull + ingest | integration (dual-backend, looped) | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_edge_timeout_precision.py -k deadline_epsilon` | ✅ | ✅ green |
| EDGE-24 | 1 | `tests/async/test_edge_shutdown.py` | open pool / pending offload at loop shutdown (mid-stream + mid-ingest) raises no library-attributable exception; trio nursery canary | integration (dual-backend, looped) | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_edge_shutdown.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/async/test_edge_checkpoint.py` — EDGE-08 (both backends; trio discriminator marked)
- [x] `tests/async/test_edge_contextvars.py` — EDGE-13 + EDGE-14 (no gating needed; simplest legs)
- [x] `tests/async/test_edge_timeout_precision.py` — EDGE-31 + EDGE-32 on streaming pull + ingest (`virtual_clock` triggers, `real_clock_watchdog` guard, `concurrency_marks`)
- [x] `tests/async/test_edge_shutdown.py` — EDGE-24 mid-stream + mid-ingest, warnings-capture, trio canary, `concurrency_marks`
- [x] Framework install: none — pytest-repeat / pytest-timeout / anyio / trio / aiotools all present
- [x] Optional one-line stub contextvar-read probe for EDGE-13 (Claude's discretion; otherwise none)

*No new fixtures required: `make_stub_async_connection`, `duckdb_async_pool`, `anyio_backend`, `await_inside`, `real_clock_watchdog`, `virtual_clock`, `concurrency_marks` all exist and are reused.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Linux-CI x20 loop confirmation | EDGE-24, EDGE-31, EDGE-32 | Cancel/lost-wakeup races are platform-dependent — a macOS-green run is not authoritative | Push branch; confirm the async job's `ADBC_ASYNC_REPEAT=20` loop is green on Linux CI (0 hangs) before verify. **✅ Satisfied** — Linux-CI run 28622475955 (Python 3.11 + 3.14, `ADBC_ASYNC_REPEAT=20`, 0 hangs) confirmed green and user-approved at the Plan 03 blocking checkpoint (see 32-VERIFICATION.md `human_verification_resolved`) |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (quick) / documented for the looped legs
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-07-04

---

## Validation Audit 2026-07-04

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

State-A reconciliation of the pre-execution draft strategy against the completed phase.
All six EDGE requirements (08/13/14/24/31/32) are COVERED by existing, substantive,
dual-backend tests — no gaps, no auditor spawn needed. Re-ran locally at audit time:

- `pytest tests/async/test_edge_{checkpoint,contextvars,timeout_precision,shutdown}.py` → **20 passed** (both backends)
- `ADBC_ASYNC_REPEAT=20 pytest tests/async/test_edge_timeout_precision.py test_edge_shutdown.py` → **280 passed, 0 hangs**
- Linux-CI x20 gate for EDGE-24/31/32 → confirmed green (run 28622475955, per 32-VERIFICATION.md)

Frontmatter reconciled: `status: draft → validated`, `wave_0_complete: false → true`.
