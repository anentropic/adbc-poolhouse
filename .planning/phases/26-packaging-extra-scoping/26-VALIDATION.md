---
phase: 26
slug: packaging-extra-scoping
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-28
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest -q` |
| **Full suite command** | `.venv/bin/pytest` |
| **Type gate** | `.venv/bin/basedpyright src/adbc_poolhouse/_async` (must stay `0 errors`) |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest -q` (+ `basedpyright` for typing tasks)
- **After every plan wave:** Run `.venv/bin/pytest` full suite
- **Before `/gsd-verify-work`:** Full suite green AND `basedpyright` 0 errors AND `mkdocs build --strict` passes
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 26-01-xx | 01 | 1 | PKG-01 | — | N/A | unit/build | `uv lock --locked` + `.venv/bin/pytest tests/test_pkg_extra.py` (metadata `Provides-Extra: async`) | ❌ W0 | ⬜ pending |
| 26-02-xx | 02 | 1 | PKG-05 | — | N/A | type | `.venv/bin/basedpyright src/adbc_poolhouse/_async` → 0 errors; `tests/test_offload_typing.py` expect-error probe flags mistyped arg | ✅ | ⬜ pending |
| 26-03-xx | 03 | 1 | PKG-02, PKG-03 | — | guard raises ImportError naming `[async]` when anyio absent | unit (subprocess) | `.venv/bin/pytest tests/test_pkg_import_guard.py` | ❌ W0 | ⬜ pending |
| 26-04-xx | 04 | 2 | PKG-04 | — | sync suite green with anyio uninstalled | ci | `.github/workflows/ci.yml` `sync-no-anyio` job: `uv sync --no-default-groups --extra duckdb` + sync-suite green + `python -c "import anyio"` fails | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pkg_import_guard.py` — subprocess-isolated regression tests for PKG-02/03 (import succeeds anyio-absent; async-symbol access raises ImportError naming `[async]`)
- [ ] `tests/test_pkg_extra.py` — metadata assertion that the `async` extra is declared (PKG-01)
- [ ] `tests/test_offload_typing.py` — expect-error probe proving the tightened offload signature flags a mistyped arg (PKG-05)
- [ ] `pyproject.toml` `[async]` extra + `uv.lock` refresh (PKG-01) — build-time prerequisite for the no-anyio CI job
- [ ] `.github/workflows/ci.yml` `sync-no-anyio` job (PKG-04)

*Existing pytest + basedpyright infrastructure covers the typing and runtime assertions; no framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI `sync-no-anyio` job actually runs green on GitHub | PKG-04 | Real CI environment differs from local; only observable on a pushed run | Push branch; confirm the `sync-no-anyio` job passes in the Actions run |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-28 (plans satisfy the Wave-0 contract; `wave_0_complete` flips to true once execution writes the test artifacts)
