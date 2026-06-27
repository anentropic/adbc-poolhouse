---
phase: 24
slug: core-async-wrapper
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-27
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | pyproject.toml |
| **Quick run command** | `.venv/bin/pytest tests/_async -x -q` |
| **Full suite command** | `.venv/bin/pytest` |
| **Estimated runtime** | ~TBD seconds (planner to refine) |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Concurrency/EDGE tests:** loop-run ×N with `fail_after` watchdog (single-shot "passed" masked a ~33% deadlock in Phase 23 — see [[feedback_loop_test_flaky_concurrency]])
- **Max feedback latency:** TBD seconds

---

## Per-Task Verification Map

> Populated by the planner during plan generation. One row per task with an automated verify command.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | TBD | — | TBD | unit | TBD | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Re-armable cursor gate + `entered`-after-block harness redesign (D-CF-01 / WR-01) — prerequisite for execute-then-fetch EDGE tests
- [ ] `tests/_async/` test module scaffold + shared fixtures

*Planner to refine against the RESEARCH.md Validation Architecture section.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| TBD | TBD | TBD | TBD |

*Planner to populate; aim for "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < TBDs
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
