---
phase: 19
slug: raw-create-pool
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-15
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_pool_factory.py tests/test_drivers.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_pool_factory.py tests/test_drivers.py -x && uv run basedpyright`
- **After every plan wave:** Run `uv run pytest tests/ -x && uv run basedpyright`
- **Before `/gsd:verify-work`:** Full suite must be green + `uv run mkdocs build --strict`
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | RAW-01 | unit (mock) | `uv run pytest tests/test_pool_factory.py -k "raw_driver_path" -x` | ❌ W0 | ⬜ pending |
| 19-01-02 | 01 | 1 | RAW-02 | unit (mock) | `uv run pytest tests/test_pool_factory.py -k "raw_dbapi_module" -x` | ❌ W0 | ⬜ pending |
| 19-01-03 | 01 | 1 | RAW-03 | unit (mock) | `uv run pytest tests/test_pool_factory.py -k "managed_raw" -x` | ❌ W0 | ⬜ pending |
| 19-01-04 | 01 | 1 | RAW-04 | unit | `uv run pytest tests/test_pool_factory.py -k "missing_args" -x` | ❌ W0 | ⬜ pending |
| 19-01-05 | 01 | 1 | RAW-05 | unit | `uv run pytest tests/test_pool_factory.py -k "mutual_exclusive" -x` | ❌ W0 | ⬜ pending |
| 19-01-06 | 01 | 1 | RAW-06 | regression | `uv run pytest tests/ -x` | ✅ | ⬜ pending |
| 19-01-07 | 01 | 1 | RAW-07 | unit | `uv run pytest tests/test_drivers.py -k "not_found" -x` | ✅ (needs update) | ⬜ pending |
| 19-01-08 | 01 | 1 | RAW-08 | type-check | `uv run basedpyright` | N/A | ⬜ pending |
| 19-02-01 | 02 | 1 | RAW-09 | integration | `uv run pytest tests/test_pool_factory.py -k "raw_duckdb_integration" -x` | ❌ W0 | ⬜ pending |
| 19-02-02 | 02 | 1 | RAW-10 | docs | `uv run mkdocs build --strict` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pool_factory.py` — new test cases for raw driver_path, raw dbapi_module, managed_pool raw variants, TypeError cases
- [ ] `tests/test_drivers.py` — update `test_foundry_not_found_message_contains_install_command` to match new error format
- [ ] `tests/test_pool_factory.py` — integration test for raw DuckDB driver_path

*Existing test infrastructure covers framework and fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docstrings cover all three call patterns | RAW-10 | Prose quality requires human review | Read `create_pool()` and `managed_pool()` docstrings |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
