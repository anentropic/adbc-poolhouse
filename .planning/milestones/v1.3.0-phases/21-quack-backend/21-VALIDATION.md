---
phase: 21
slug: quack-backend
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-19
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) + `tests/conftest.py` |
| **Quick run command** | `uv run pytest tests/test_configs.py::TestQuackConfig -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~30 seconds (full suite); ~2 seconds (quick) |

Docs validation:

| Property | Value |
|----------|-------|
| **Strict build** | `uv run mkdocs build --strict` |
| **Dev server (manual check)** | `uv run mkdocs serve` |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_configs.py::TestQuackConfig -x -q` (or the narrower file under change)
- **After every plan wave:** Run `uv run pytest -x -q` AND `uv run mkdocs build --strict`
- **Before `/gsd-verify-work`:** Full suite must be green; mkdocs strict build must pass
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | QUACK-01, QUACK-02, QUACK-03 | — | Config class + field validation | unit | `uv run pytest tests/test_configs.py::TestQuackConfig -x -q` | ❌ W0 (config class new) | ⬜ pending |
| 21-01-02 | 01 | 1 | QUACK-04, QUACK-05, QUACK-06 | — | ADBC kwargs serialization | unit | `uv run pytest tests/test_configs.py::TestQuackConfig::test_to_adbc_kwargs -x -q` | ❌ W0 | ⬜ pending |
| 21-01-03 | 01 | 1 | QUACK-07 | — | Public export from package | unit | `uv run python -c "from adbc_poolhouse import QuackConfig"` | ✅ (init exists) | ⬜ pending |
| 21-01-04 | 01 | 1 | QUACK-09 | — | Optional dep group declared | grep | `grep -q '^quack = \[' pyproject.toml` | ✅ (pyproject exists) | ⬜ pending |
| 21-02-01 | 02 | 2 | QUACK-10 | — | Unit tests for validation | unit | `uv run pytest tests/test_configs.py::TestQuackConfig -x -q` | ❌ W0 | ⬜ pending |
| 21-02-02 | 02 | 2 | QUACK-08, QUACK-11 | — | Semi-integration test for create_pool | unit (mock) | `uv run pytest tests/test_driver_imports.py::TestQuackImports -x -q` | ❌ W0 | ⬜ pending |
| 21-02-03 | 02 | 2 | — (driver short-name) | — | Driver path test | unit | `uv run pytest tests/test_drivers.py::test_quack_returns_short_name -x -q` | ✅ (file exists) | ⬜ pending |
| 21-02-04 | 02 | 2 | QUACK-12 | — | All 241 existing tests still pass | unit | `uv run pytest -x -q` | ✅ | ⬜ pending |
| 21-03-01 | 03 | 3 | QUACK-13, QUACK-14 | — | Per-warehouse guide present, alpha admonition + upstream link | grep | `grep -q "https://github.com/gizmodata/adbc-driver-quack" docs/src/guides/quack.md && grep -qE "alpha\|admonition\|!!! warning" docs/src/guides/quack.md` | ❌ W0 | ⬜ pending |
| 21-03-02 | 03 | 3 | QUACK-15 | — | Configuration table row | grep | `grep -qi "quack" docs/src/guides/configuration.md` | ✅ | ⬜ pending |
| 21-03-03 | 03 | 3 | QUACK-16 | — | index.md listing | grep | `grep -qi "quack" docs/src/index.md` | ✅ | ⬜ pending |
| 21-03-04 | 03 | 3 | QUACK-17 | — | mkdocs nav entry | grep | `grep -q "guides/quack.md" mkdocs.yml` | ✅ | ⬜ pending |
| 21-03-05 | 03 | 3 | QUACK-18 | — | Strict build passes | build | `uv run mkdocs build --strict` | ✅ | ⬜ pending |
| 21-03-06 | 03 | 3 | QUACK-18 | — | Humanizer pass applied to new prose | manual+grep | manual review using `humanizer` skill | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/adbc_poolhouse/_quack_config.py` — new module
- [ ] `tests/test_configs.py::TestQuackConfig` — new test class in existing file
- [ ] `tests/test_driver_imports.py::TestQuackImports` — new test class in existing file
- [ ] `tests/test_drivers.py::test_quack_returns_short_name` — new test in existing file
- [ ] `docs/src/guides/quack.md` — new guide page

Existing infrastructure (pytest, conftest, fixtures, mkdocs config) requires no setup.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Humanizer pass on docs prose | QUACK-18 | Stylistic judgment outside automated test scope | Run the `humanizer` skill against `docs/src/guides/quack.md` and any new prose in `configuration.md`/`index.md`; apply suggested edits |
| Live pool against real Quack server | (deferred) | No public test server; explicitly deferred in REQUIREMENTS.md | n/a — out of scope |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
