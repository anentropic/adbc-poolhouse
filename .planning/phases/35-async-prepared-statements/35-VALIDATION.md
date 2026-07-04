---
phase: 35
slug: async-prepared-statements
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-04
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (asyncio + trio via anyio) |
| **Config file** | `pyproject.toml` / `tests/conftest.py` |
| **Quick run command** | `.venv/bin/pytest tests/_async/ -k prepare or execute_schema -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Estimated runtime** | ~30–90 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

*Populated by the planner from the RESEARCH.md Validation Architecture section.
Each success criterion (PREP-01/02/03) maps to at least one automated test leg:
signature/awaitable, value round-trip (`adbc_prepare` → Schema|None,
`adbc_execute_schema` → Schema), no-execute proof (stub `execute_call_count == 0`),
in-flight cancel (BlockingStubCursor, asyncio + trio), and DuckDB
`NotSupportedError` unsupported-passthrough (EDGE-17).*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 35-01-01 | 01 | 1 | PREP-01/02 | — | N/A | unit | `.venv/bin/pytest tests/_async/ -k prepare` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] RED test module(s) under `tests/_async/` — stubs for PREP-01/02
- [ ] `BlockingStubCursor` extension — blocking `adbc_prepare` / `adbc_execute_schema`
      + call counters (must NOT touch `execute_call_count` — the no-execute proof)

*Existing async test infrastructure (Phase 23/27/32 harness) covers the rest.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `mkdocs build --strict` + humanizer pass | PREP-03 | Prose/build gate | `.venv/bin/mkdocs build --strict` |

*All runtime behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
