---
phase: "01"
slug: driver-import-semi-integration-tests
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0.0 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/imports/test_driver_imports.py -v` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/imports/test_driver_imports.py -v`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | TEST-01, TEST-02, TEST-03 | semi-integration | `uv run pytest tests/imports/test_driver_imports.py -v` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | TEST-04 | semi-integration | `uv run pytest tests/imports/test_driver_imports.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/imports/__init__.py` — makes imports a package
- [ ] `tests/imports/test_driver_imports.py` — 12 test classes for all backends
- [ ] `justfile` — `install-all-drivers` recipe for PyPI + Foundry driver installation

*Existing infrastructure: `conftest.py` with `_clear_warehouse_env_vars` autouse fixture, pytest configured in pyproject.toml*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| None | - | All behaviors have automated verification | - |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
