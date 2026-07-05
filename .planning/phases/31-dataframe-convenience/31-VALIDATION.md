---
phase: 31
slug: dataframe-convenience
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-02
audited: 2026-07-02
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `31-RESEARCH.md` §"Validation Architecture". Follow the Phase 29/30
> RED-first rhythm: land failing tests + stub extensions in Wave 0, turn them GREEN
> when the two `AsyncCursor` methods land.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest>=8.0.0` + `anyio` plugin (dual-backend: asyncio + trio via `anyio_backend`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest tests/async/test_df_roundtrip.py tests/async/test_df_missing_dep.py -q` |
| **Full suite command** | `.venv/bin/pytest tests/async -q` |
| **Type gate** | `.venv/bin/basedpyright` (strict; `src` + `tests`) — 0 errors |
| **Import-lint gate** | `scan_async_package` over `src/adbc_poolhouse/_async/` returns `[]` (PKG-03) |
| **Docs gate** | `uv run mkdocs build --strict` (or `.venv/bin/mkdocs build --strict`) |
| **Estimated runtime** | ~15 seconds (async suite) |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/async/test_df_*.py -q` + `.venv/bin/basedpyright`
- **After every plan wave:** Run `.venv/bin/pytest tests/async -q` (full async suite) + `scan_async_package` guard
- **Before `/gsd-verify-work`:** Full suite green + `uv run mkdocs build --strict` (docs gate, CLAUDE.md)
- **Max feedback latency:** ~15 seconds
- **Loop discipline:** cancel/busy tests carry `concurrency_marks`; verify with `rc=$?` + grep for the pass line (NEVER `if ! cmd` — zsh silently fakes a green loop)

---

## Per-Task Verification Map

| Req / Criterion | Wave | Behavior to assert | Test Type | Automated Command | File Exists | Status |
|-----------------|------|--------------------|-----------|-------------------|-------------|--------|
| DF-01 | 1 | `await cur.fetch_df()` returns `pandas.DataFrame`; values round-trip on DuckDB | integration (importorskip pandas) | `pytest tests/async/test_df_roundtrip.py -k fetch_df -q` | ✅ | ✅ green |
| DF-02 | 1 | `await cur.fetch_polars()` returns `polars.DataFrame`; values round-trip on DuckDB | integration (importorskip polars) | `pytest tests/async/test_df_roundtrip.py -k fetch_polars -q` | ✅ | ✅ green |
| DF-03 (pandas) | 1 | Stub `fetch_df` raising `ModuleNotFoundError` in the worker propagates exact native type/`.name`; NOT wrapped in `PoolhouseError` | unit (stub, dual-backend) | `pytest tests/async/test_df_missing_dep.py -k pandas -q` | ✅ | ✅ green |
| DF-03 (polars) | 1 | Same for `fetch_polars` / `polars` | unit (stub, dual-backend) | `pytest tests/async/test_df_missing_dep.py -k polars -q` | ✅ | ✅ green |
| DF-04 (df) | 1 | Frame read valid AFTER connection checks in (self-owning; no dangling C stream) | integration (importorskip) | `pytest tests/async/test_df_lifetime.py -k fetch_df -q` | ✅ | ✅ green |
| DF-04 (polars) | 1 | Same for polars frame | integration (importorskip) | `pytest tests/async/test_df_lifetime.py -k fetch_polars -q` | ✅ | ✅ green |
| Busy-guard parity | 1 | Second in-flight op raises `ConnectionBusyError` (`_in_use`) — parity with `fetch_arrow_table` | unit (stub, dual-backend, looped) | `pytest tests/async/test_df_busy.py -q` | ✅ | ✅ green |
| Cancel/invalidate parity | 1 | Cancelled/timed-out call fires `adbc_cancel` once + invalidates + `checkedout()==0` | unit (stub, dual-backend, looped) | `pytest tests/async/test_df_cancel.py -q` | ✅ | ✅ green |
| DF-01/02 signature + Protocol | 1 | Methods exist (no args); `_SyncCursor` Protocol carries both `-> object` members; strict 0 errors | unit + type gate | `pytest tests/async/test_df_signature.py -q` && `.venv/bin/basedpyright` | ✅ | ✅ green |
| PKG-02 (no runtime leak) | 1 | `import adbc_poolhouse` succeeds with pandas/polars absent; surface unchanged | unit (env-free) | `pytest tests/async/test_df_signature.py -k import_surface -q` | ✅ | ✅ green |
| PKG-03 (guard) | 1 | `scan_async_package` still `[]` over `_async/` after the two methods + `TYPE_CHECKING` imports land | meta-guard | `pytest tests/async/test_async_guard.py -q` | ✅ exists | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/_async_harness/stubs.py` — add blockable `fetch_df`/`fetch_polars` stubs (+ optional `fetch_df_raises`/`fetch_polars_raises` injection for DF-03); mirror `adbc_ingest`/`fetch_arrow_table`, add `df_call_count`/`polars_call_count` counters
- [x] `tests/async/test_df_roundtrip.py` — DF-01/DF-02 positive round-trip (importorskip), DuckDB, dual-backend
- [x] `tests/async/test_df_missing_dep.py` — DF-03 stub-raising propagation, dual-backend
- [x] `tests/async/test_df_lifetime.py` — DF-04 valid-after-checkin (importorskip), DuckDB
- [x] `tests/async/test_df_busy.py` — busy-guard parity, `concurrency_marks`, dual-backend, looped
- [x] `tests/async/test_df_cancel.py` — cancel/invalidate parity, `concurrency_marks`, `real_clock_watchdog`, dual-backend, looped
- [x] `tests/async/test_df_signature.py` — signature + Protocol coverage + `import adbc_poolhouse`-without-pandas (PKG-02)
- [x] Framework install: `pandas` + `polars` added to `[dependency-groups].dev`, then `uv sync` before positive tests can pass

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `no-df` subprocess smoke (belt-and-suspenders) | DF-03 | Once pandas/polars land in the dev group, a real pandas-free interpreter can't be reproduced in normal CI | Optional: run `fetch_df` in a venv without pandas installed; assert raw `ModuleNotFoundError`. Do NOT gate CI on it (the stub test is the CI gate). |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-02

---

## Validation Audit 2026-07-02

| Metric | Count |
|--------|-------|
| Requirements audited | 11 |
| Covered | 11 |
| Partial | 0 |
| Missing | 0 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

State A audit (VALIDATION.md pre-existed from planning). Every Per-Task Map row
cross-referenced against its landed test file and re-run green: DF test suite +
guard **32 passed**; concurrency (`test_df_busy.py`, `test_df_cancel.py`)
**loop-verified 10/10, 0 hangs** (`rc=$?` + pass-line grep, not `if ! cmd`).
No gaps — no `gsd-nyquist-auditor` spawn required. `nyquist_compliant: true`.
The single Manual-Only item (`no-df` subprocess smoke) is belt-and-suspenders and
intentionally not a CI gate; the stub-raising `test_df_missing_dep.py` is the DF-03
CI gate.
