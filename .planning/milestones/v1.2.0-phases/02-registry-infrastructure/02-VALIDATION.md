---
phase: 02
slug: registry-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | pyproject.toml [tool.pytest] |
| **Quick run command** | `uv run pytest tests/test_registry.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_registry.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | REG-01 | unit | `uv run pytest tests/test_registry.py::TestBackendRegistry -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | REG-02 | unit | `uv run pytest tests/test_registry.py::TestRegisterBackend -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | TEST-INFRA-01 | fixture | `uv run pytest tests/test_registry.py::TestDummyBackend -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | REG-03 | unit | `uv run pytest tests/test_registry.py::TestRegistryIntegration -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | REG-03 | unit | `uv run pytest tests/test_registry.py::TestBuiltInBackends -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_registry.py` — stubs for REG-01, REG-02, REG-03, TEST-INFRA-01
- [ ] `tests/conftest.py` — dummy backend fixture (minimal config class + no-op translator)
- [ ] Exception hierarchy tests (add to existing `tests/test_exceptions.py` or create new)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| None | - | All behaviors have automated tests | - |

*All phase behaviors have automated verification.*

---

## Test Scenarios (from CONTEXT.md)

| # | Scenario | Test Class | Key Assertions |
|---|----------|------------|----------------|
| 1 | Manual registration works | `TestRegisterBackend::test_valid_registration` | No exception raised, registry contains entry |
| 2 | Duplicate detection | `TestRegisterBackend::test_duplicate_raises` | `BackendAlreadyRegisteredError` raised |
| 3 | Invalid params | `TestRegisterBackend::test_invalid_params` | `TypeError` with clear message |
| 4 | Unregistered backend | `TestRegistryIntegration::test_unregistered_config` | `BackendNotRegisteredError` from `create_pool()` |
| 5 | Built-ins work without registration | `TestBuiltInBackends::test_duckdb_without_manual_registration` | `create_pool(DuckDBConfig())` succeeds |

---

## Key Integration Points to Test

1. **`create_pool()` → `ensure_registered()`**: Verify lazy registration triggered
2. **`translate_config()` → `get_translator()`**: Verify correct translator returned
3. **`resolve_driver()` → `get_driver_path()`**: Verify correct driver_path returned
4. **Exception messages**: Verify `BackendNotRegisteredError` includes hint to call `register_backend()`

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
