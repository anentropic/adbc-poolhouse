---
phase: 18
slug: registration-removal
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-15
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -x -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 1 | SELF-DESC-01 | unit | `uv run pytest tests/test_drivers.py -x -k duckdb` | Rewrite needed | ⬜ pending |
| 18-01-02 | 01 | 1 | SELF-DESC-02 | unit | `uv run pytest tests/test_drivers.py -x -k pypi` | Rewrite needed | ⬜ pending |
| 18-01-03 | 01 | 1 | SELF-DESC-03 | unit | `uv run pytest tests/test_drivers.py -x -k foundry` | Rewrite needed | ⬜ pending |
| 18-01-04 | 01 | 1 | SELF-DESC-04 | unit | `uv run pytest tests/test_drivers.py -x -k dbapi_module` | New | ⬜ pending |
| 18-01-05 | 01 | 1 | SELF-DESC-05 | unit | `uv run pytest tests/test_drivers.py -x -k sqlite_dbapi` | New | ⬜ pending |
| 18-02-01 | 02 | 2 | REG-DELETE-01 | smoke | `uv run pytest --co -q` | N/A | ⬜ pending |
| 18-02-02 | 02 | 2 | REG-DELETE-02 | smoke | `uv run pytest --co -q` | N/A | ⬜ pending |
| 18-02-03 | 02 | 2 | REG-DELETE-03 | unit | `uv run pytest tests/test_pool_factory.py -x -k exception` | Existing | ⬜ pending |
| 18-02-04 | 02 | 2 | POOL-INLINE-01 | unit | `uv run pytest tests/test_pool_factory.py -x` | Existing (update) | ⬜ pending |
| 18-02-05 | 02 | 2 | POOL-INLINE-02 | unit | `uv run pytest tests/test_driver_imports.py -x` | Existing (update) | ⬜ pending |
| 18-02-06 | 02 | 2 | 3P-CONTRACT-01 | unit | `uv run pytest tests/test_drivers.py -x -k custom` | Rewrite needed | ⬜ pending |
| 18-XX-XX | XX | XX | FULL-SUITE | full | `uv run pytest` | Existing + new | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Rewrite `tests/test_drivers.py` — test config._driver_path() and _dbapi_module() instead of resolve_driver()
- [ ] Delete `tests/test_registry.py` — all tests are for deleted code
- [ ] Update `tests/conftest.py` — remove clean_registry fixture and related helpers

*Wave 0 is embedded within plan execution (not a separate wave).*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
