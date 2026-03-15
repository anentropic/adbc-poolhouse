---
phase: 18
slug: registration-removal
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-15
audited: 2026-03-15
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
| **Estimated runtime** | ~0.5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -x -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 1 second

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 1 | SELF-DESC-01 | unit | `uv run pytest tests/test_drivers.py -x -k duckdb` | ✅ | ✅ green |
| 18-01-02 | 01 | 1 | SELF-DESC-02 | unit | `uv run pytest tests/test_drivers.py -x -k PyPI` | ✅ | ✅ green |
| 18-01-03 | 01 | 1 | SELF-DESC-03 | unit | `uv run pytest tests/test_drivers.py -x -k Foundry` | ✅ | ✅ green |
| 18-01-04 | 01 | 1 | SELF-DESC-04 | unit | `uv run pytest tests/test_drivers.py -x -k DbApiModule` | ✅ | ✅ green |
| 18-01-05 | 01 | 1 | SELF-DESC-05 | unit | `uv run pytest tests/test_drivers.py -x -k sqlite_dbapi` | ✅ | ✅ green |
| 18-02-01 | 02 | 2 | REG-DELETE-01 | smoke | `uv run pytest --co -q` | ✅ | ✅ green |
| 18-02-02 | 02 | 2 | REG-DELETE-02 | smoke | `uv run pytest --co -q` | ✅ | ✅ green |
| 18-02-03 | 02 | 2 | REG-DELETE-03 | smoke | `uv run pytest --co -q` | ✅ | ✅ green |
| 18-02-04 | 02 | 2 | POOL-INLINE-01 | unit | `uv run pytest tests/test_pool_factory.py -x` | ✅ | ✅ green |
| 18-02-05 | 02 | 2 | POOL-INLINE-02 | unit | `uv run pytest tests/test_driver_imports.py -x` | ✅ | ✅ green |
| 18-02-06 | 02 | 2 | 3P-CONTRACT-01 | unit | `uv run pytest tests/test_drivers.py -x -k custom` | ✅ | ✅ green |
| 18-XX-XX | XX | XX | FULL-SUITE | full | `uv run pytest` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] Rewrite `tests/test_drivers.py` — test config._driver_path() and _dbapi_module() instead of resolve_driver()
- [x] Delete `tests/test_registry.py` — all tests are for deleted code
- [x] Update `tests/conftest.py` — remove clean_registry fixture and related helpers

*Wave 0 completed during plan execution (Plans 02 and 03).*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 1s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-15

---

## Validation Audit 2026-03-15

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
