---
phase: 22
slug: feasibility-spike
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-26
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/ -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -q` |
| **Estimated runtime** | ~tens of seconds |

> Note: this is a measurement spike. CI must NOT assert on wall-clock speedup ratios
> (flaky across machines/load). Unit tests cover the harness arithmetic (speedup-ratio
> math, baseline computation, median/aggregation) and that the benchmark drives the real
> `create_pool(DuckDBConfig(...))` checkout path leaving `checkedout() == 0`. The
> measured parallel/serial verdict is recorded once in the go/no-go doc, not re-asserted
> in CI. See the Validation Architecture section of `22-RESEARCH.md`.

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/ -q`
- **After every plan wave:** Run `.venv/bin/pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | SPIKE-01 | — | N/A | unit | `.venv/bin/pytest tests/ -q -k benchmark` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | SPIKE-02 | — | N/A | unit | `.venv/bin/pytest tests/ -q -k benchmark` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | SPIKE-03 | — | N/A | manual | go/no-go doc review | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*The planner finalizes task IDs and the harness-arithmetic test mapping.*

---

## Wave 0 Requirements

- [ ] Benchmark harness module under `benchmarks/` (kept, reusable)
- [ ] Unit test for harness arithmetic (speedup-ratio / baseline / median)

*The kept harness is itself the test target; no new framework install needed (pytest present).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Go/no-go verdict honesty (parallelism vs inferred I/O concurrency; named materialization caveat) | SPIKE-03 | Prose judgment, not machine-checkable | Review `22-feasibility-spike/` go/no-go doc against CONTEXT.md terminology constraints |
| Measured speedup ratios | SPIKE-01, SPIKE-02 | Wall-clock is machine/load dependent; asserting it in CI is flaky | Run benchmark locally; record medians in the go/no-go doc |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
