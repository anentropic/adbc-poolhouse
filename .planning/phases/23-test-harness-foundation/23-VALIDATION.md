---
phase: 23
slug: test-harness-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-27
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
>
> Note: this phase *is* test infrastructure. Its "validation surface" is the harness's
> own self-tests (block→release and block→`adbc_cancel`→unblock under both asyncio and
> trio, plus the AST-guard fixture tests). See `23-RESEARCH.md` → "## Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 8 (env has 9.0.3) + `anyio` pytest plugin (dev-group; installed in Wave 0) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest tests/ -k async_harness -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Estimated runtime** | ~15 seconds (harness self-tests are event-gated, no real sleeps) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 23-XX-XX | TBD | 0 | TEST-05 | — | N/A | install | `.venv/bin/pytest --version` | ❌ W0 | ⬜ pending |
| 23-XX-XX | TBD | 1 | TEST-05 | — | N/A | unit | `.venv/bin/pytest tests/ -k blocking_stub -q` | ❌ W0 | ⬜ pending |
| 23-XX-XX | TBD | 1 | TEST-05 | — | N/A | unit | `.venv/bin/pytest tests/ -k virtual_clock -q` | ❌ W0 | ⬜ pending |
| 23-XX-XX | TBD | 1 | TEST-05 | — | N/A | unit | `.venv/bin/pytest tests/ -k import_guard -q` | ❌ W0 | ⬜ pending |

*Task IDs finalized by the planner. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `anyio`, `trio`, `aiotools` added to the dev/test dependency group and installed (no framework gap otherwise — pytest is already present)
- [ ] `anyio` pytest plugin enabled; `anyio_backend` parametrization (`["asyncio", "trio"]`) wired in a conftest
- [ ] Test files for the stub fakes, the virtual-clock façade, and the AST guard (created by phase tasks, not pre-stubbed)

*The harness modules ARE the deliverable, so Wave 0 is dependency install + backend parametrization rather than test stubs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification — the harness self-tests run under both asyncio and trio.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
