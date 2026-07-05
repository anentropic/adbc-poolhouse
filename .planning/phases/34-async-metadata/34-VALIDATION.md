---
phase: 34
slug: async-metadata
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-04
validated: 2026-07-04
---

# Phase 34 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` + `anyio` plugin (asyncio×trio axis via `anyio_backend` fixture) |
| **Config file** | `pyproject.toml` (ruff, basedpyright, pytest markers: `anyio`, `snowflake`, `adbc_cassette`) |
| **Quick run command** | `.venv/bin/pytest tests/async/test_meta_*.py -x` |
| **Full suite command** | `.venv/bin/pytest tests/async -q` (loop gate: `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async -q` if any cancel/streaming leg is added) |
| **Type gate** | `.venv/bin/basedpyright src/adbc_poolhouse/_async/_connection.py` (0 errors) |
| **Docs gate** | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` (exit 0) |
| **Estimated runtime** | ~20 seconds (async suite) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/async/test_meta_*.py -x` + `.venv/bin/basedpyright src/adbc_poolhouse/_async/_connection.py`
- **After every plan wave:** Run `.venv/bin/pytest tests/async -q` (+ `ADBC_ASYNC_REPEAT=20` if a streaming/cancel leg was added)
- **Before `/gsd-verify-work`:** Full async suite green + basedpyright 0 errors + `mkdocs build --strict` exit 0
- **Max feedback latency:** ~20 seconds

---

## Per-Task Verification Map

Plan/wave/task IDs are assigned by the planner; requirement→test mapping is fixed by the research.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T1 | 34-01/02 | 0 | META-01 | — | N/A (no new attack surface) | unit (signature) | `.venv/bin/pytest tests/async/test_meta_signature.py -x` | ✅ | ✅ green |
| T2 | 34-02 | 1 | META-01/02 | — | N/A | integration (DuckDB) | `.venv/bin/pytest tests/async/test_meta_roundtrip.py -x` | ✅ | ✅ green |
| T3 | 34-02 | 1 | META-02 | — | N/A | integration (DuckDB) | `.venv/bin/pytest tests/async/test_meta_stream.py -x` | ✅ | ✅ green |
| T4 | 34-02 | 1 | META-03 | — | native error surfaced unchanged | integration (DuckDB) | `.venv/bin/pytest tests/async/test_meta_unsupported.py -x` | ✅ | ✅ green |
| T5 | 34-03 | 1 | META-04 | — | N/A | docs gate | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` | n/a (build) | ✅ green |
| T6 | 34-02 | 1 | (cross) | — | guard-clean, strict types | meta-guard + basedpyright | `.venv/bin/pytest tests/async/test_meta_guard.py -x && .venv/bin/basedpyright src/adbc_poolhouse/_async/_connection.py` | ✅ | ✅ green |
| T7 | 34-02 | 1 | META-02 (CR-34-01) | — | cancelled metadata pull does NOT invalidate (`invalidate_call_count == 0`); non-poisoning reader | integration (dual-backend, looped) | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_meta_cancel.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/async/test_meta_signature.py` — META-01 signature/existence (RED first): `hasattr(AsyncConnection, name)` for all six; `inspect.signature` asserts kw-only params and positional `table_name` (mirror `test_ingest_signature.py`)
- [x] `tests/async/test_meta_roundtrip.py` — META-01/02 value methods: `adbc_get_info()`→`dict`, `adbc_get_table_types()`→`list`, `adbc_get_table_schema("t")`→`pyarrow.Schema`; assert `pool.checkedout() == 0` after checkin
- [x] `tests/async/test_meta_stream.py` — META-02 streaming reader: `async with await conn.adbc_get_objects(depth="tables") as reader` yields `pyarrow.RecordBatch`; drains and `pool.checkedout() == 0`; optional busy-guard leg (foreign `commit` while reader live raises `ConnectionBusyError`)
- [x] `tests/async/test_meta_unsupported.py` — META-03 native error: `pytest.raises(adbc_driver_manager.NotSupportedError)` for `adbc_get_statistics()` and `adbc_get_statistic_names()` [VERIFIED both raise on DuckDB]
- [x] `tests/async/test_meta_cancel.py` — CR-34-01 regression guard (added on GREEN): cancelled metadata pull asserts `invalidate_call_count == 0` (non-poisoning), looped x20
- [x] No new fixtures needed — `duckdb_async_pool` + `anyio_backend` already exist in `tests/async/conftest.py`
- [x] No framework install needed

*New test files must observe `tests/async/` discipline (`@pytest.mark.anyio` on every async test, no `import asyncio`, no positive-duration `sleep`) or `test_meta_guard.py` fails.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Streaming metadata against a non-DuckDB backend that returns statistics | META-02 | Snowflake cassette cannot replay metadata (Phase 29 A1 pattern); no live warehouse in CI | Optional: run `adbc_get_statistics` against a live warehouse that implements it, confirm `AsyncRecordBatchReader` streams batches |

*DuckDB carries all automated coverage; the row above is optional cross-backend confidence only.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-07-04

---

## Validation Audit 2026-07-04

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

State-A reconciliation of the pre-execution draft strategy against the completed phase.
All META requirements (01/02/03/04) plus the CR-34-01 non-poisoning-cancel regression
guard are COVERED by existing, substantive tests — no gaps, no auditor spawn needed.
Re-ran locally at audit time:

- `pytest tests/async/test_meta_*.py` → **24 passed**
- `ADBC_ASYNC_REPEAT=20 pytest tests/async/test_meta_cancel.py test_meta_stream.py` → **48 passed, 0 hangs**
- `basedpyright src/adbc_poolhouse/_async/_connection.py` → **0 errors**
- Docs + full-suite gates confirmed green in 34-VERIFICATION.md (`mkdocs build --strict` exit 0)

Frontmatter reconciled: `status: draft → validated`, `nyquist_compliant: false → true`,
`wave_0_complete: false → true`. The prior `nyquist_compliant: false` reflected the
pre-execution draft state, not a coverage gap — the phase shipped with full automated
coverage (22 tests green in VERIFICATION; 24 at audit time).
