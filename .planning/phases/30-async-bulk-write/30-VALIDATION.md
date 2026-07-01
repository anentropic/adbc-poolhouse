---
phase: 30
slug: async-bulk-write
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-01
---

# Phase 30 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from `30-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + anyio plugin (asyncio + trio backends via `anyio_backend_name`) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `.venv/bin/pytest tests/async/test_ingest_*.py -x -q && .venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py` |
| **Full suite command** | `.venv/bin/pytest tests/async -q && .venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py && .venv/bin/pytest tests/test_pkg_import_guard.py tests/async/test_async_guard.py -q` |
| **Estimated runtime** | ~30 seconds (async suite + typecheck + guard) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/async/test_ingest_*.py -x -q && .venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py`
- **After every plan wave:** Run `.venv/bin/pytest tests/async -q` (full async suite — confirm no existing call site regressed)
- **Before `/gsd-verify-work`:** Full suite green + `basedpyright` 0 errors + guard `[]` + `.venv/bin/mkdocs build --strict` (docs gate, CLAUDE.md phase ≥ 7)
- **Max feedback latency:** ~30 seconds
- **Concurrency-test hygiene (MEMORY):** run `test_ingest_cancel.py` in a **loop** (e.g. `--count=20` via `pytest-repeat`), not once — single-shot verification missed a ~33% deadlock in Phase 23. Use `rc=$?` + grep for the pass line, never `if ! cmd` in a zsh for-loop (zsh `!` quirk).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 30-01-01 | 01 | 0 | INGEST-01 | — | Round-trip ingest→query returns rows; returns driver `int` count; connection checks in immediately | integration (DuckDB) | `.venv/bin/pytest tests/async/test_ingest_roundtrip.py -x` | ❌ W0 | ⬜ pending |
| 30-01-02 | 01 | 0 | INGEST-01 | — | `_SyncCursor` Protocol carries `adbc_ingest`; public method keyword-only; strict-clean | unit + typecheck | `.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py` | ❌ W0 | ⬜ pending |
| 30-01-03 | 01 | 0 | INGEST-02 | — | All four `Literal` modes forwarded verbatim to driver (`replace`=drop, `create_append`) | integration (DuckDB) | `.venv/bin/pytest tests/async/test_ingest_modes.py -x` | ❌ W0 | ⬜ pending |
| 30-01-04 | 01 | 0 | INGEST-03 | — | `data` pass-through: `pyarrow.Table`/`RecordBatch` ingests + round-trips unchanged; zero conversion | integration (DuckDB) | `.venv/bin/pytest tests/async/test_ingest_roundtrip.py::test_data_passthrough -x` | ❌ W0 | ⬜ pending |
| 30-01-05 | 01 | 0 | INGEST-04 | T-30-01 | In-flight cancel → `adbc_cancel` fires once + `invalidate` + `checkedout()==0`; asyncio AND trio | unit (BlockingStubCursor, looped) | `.venv/bin/pytest tests/async/test_ingest_cancel.py -x` | ❌ W0 | ⬜ pending |
| 30-01-06 | 01 | — | PKG-03 (re-verify) | T-30-02 | Import-lint guard passes over `_async/` with `functools.partial` present | guard | `.venv/bin/pytest tests/test_pkg_import_guard.py tests/async/test_async_guard.py -q` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · Wave/Task IDs are indicative — planner assigns final IDs.*

---

## Wave 0 Requirements

- [ ] `tests/async/test_ingest_roundtrip.py` — covers INGEST-01, INGEST-03 (DuckDB create/append round-trip + data pass-through)
- [ ] `tests/async/test_ingest_modes.py` — covers INGEST-02 (all four modes; `replace`=drop, `create_append` semantics)
- [ ] `tests/async/test_ingest_cancel.py` — covers INGEST-04 (cancel → `adbc_cancel` once + `invalidate` + `checkedout()==0`, asyncio+trio, looped)
- [ ] `tests/_async_harness/stubs.py` — add `BlockingStubCursor.adbc_ingest` (sticky-release blocking gate + `ingest_call_count`)
- [ ] `tests/async/test_ingest_signature.py` (or fold into existing signature test) — asserts `_SyncCursor` Protocol + public keyword-only signature under basedpyright strict

*(No conftest/fixture gaps: existing `tests/async/conftest.py` already exposes `BlockingStubCursor`, the anyio backend param, and DuckDB pool fixtures used by the Phase 29 read-path round-trip tests.)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Per-backend partial-write table state after a cancelled ingest | INGEST-04 (scoped OUT per D-30-10) | DB-level non-atomicity is inherent to aborting mid-write; poisoned-connection recovery is the only guarantee | Document the non-atomicity in the docstring; assert only connection recovery (`checkedout()==0`), NOT rollback of partial rows |

*All in-scope phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
