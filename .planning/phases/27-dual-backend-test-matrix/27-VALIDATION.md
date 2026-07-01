---
phase: 27
slug: dual-backend-test-matrix
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-28
---

# Phase 27 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **This is a test-layer phase — the new tests ARE the validation.** Each requirement maps to the test that proves it (see 27-RESEARCH.md → Validation Architecture).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0.0 + anyio pytest plugin (`@pytest.mark.anyio`) + pytest-adbc-replay 1.0.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (markers, `adbc_cassette_dir`, `adbc_auto_patch`) |
| **Quick run command** | `.venv/bin/pytest tests/async/<the new file> -x` |
| **Full suite command** | `.venv/bin/pytest` |
| **Estimated runtime** | ~60–120 seconds full suite; new files seconds each |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/async/<the new file> -x`
- **After every plan wave:** Run `.venv/bin/pytest tests/async tests/_async_harness`
- **Before `/gsd-verify-work`:** Full `.venv/bin/pytest` green + ×20 loop-stability gate (0 hangs) on every new/meta-flagged concurrency test + Linux CI green (the real cross-platform gate)
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {planner fills} | — | — | TEST-01 | — / — | N/A (test-layer) | meta + every test | `.venv/bin/pytest tests/async -k matrix` | ❌ W0 | ⬜ pending |
| {planner fills} | — | — | TEST-02 | — / — | N/A (test-layer) | parametrized read-path | `.venv/bin/pytest tests/async/test_matrix_*.py` | ❌ W0 | ⬜ pending |
| {planner fills} | — | — | TEST-03 | — / — | N/A (test-layer) | unit (real DuckDB) | `.venv/bin/pytest tests/async/test_stability_*.py` | ❌ W0 | ⬜ pending |
| {planner fills} | — | — | TEST-04 | — / — | N/A (test-layer) | stub-gated flood + smoke | `.venv/bin/pytest tests/async/test_limiter_stress_*.py` | ❌ W0 | ⬜ pending |
| {planner fills} | — | — | EDGE-27 | — / — | N/A (test-layer) | meta (AST scan) | `.venv/bin/pytest -k async_test_package_hygiene` | ❌ W0 | ⬜ pending |
| {planner fills} | — | — | EDGE-30 | — / — | N/A (test-layer) | meta (AST scan) | `.venv/bin/pytest -k no_positive_sleep` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/async/conftest.py` — add `snowflake_async_pool` cassette fixture (D-27-04)
- [ ] `tests/_async_harness/guard.py` — add `scan_async_test_hygiene` + `scan_for_positive_sleep` (EDGE-27/30), each with Google-style docstrings (CLAUDE.md docs gate — public harness callables)
- [ ] `tests/async/test_matrix_*.py` — TEST-01/02 read-path matrix
- [ ] `tests/async/test_stability_*.py` — TEST-03 allocator delta + reset-count
- [ ] `tests/async/test_limiter_stress_*.py` — TEST-04 flood + real-DuckDB smoke
- [ ] `tests/async/test_meta_guard_*.py` — EDGE-27/30 meta-tests asserting `== []`
- [ ] Framework install: none — all present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Linux/CI cross-platform stability | TEST-01..04, EDGE-27/30 | Lost-wakeup races can pass ×20 locally on macOS but hang on Linux CI (Phase 24–26 landmine) | Push branch; confirm the dual-backend `quality` job is green on Linux before phase sign-off |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
