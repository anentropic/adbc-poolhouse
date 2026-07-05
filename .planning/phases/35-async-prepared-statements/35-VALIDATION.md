---
phase: 35
slug: async-prepared-statements
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-04
validated: 2026-07-05
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (asyncio + trio via anyio) |
| **Config file** | `pyproject.toml` / `tests/conftest.py` |
| **Quick run command** | `.venv/bin/pytest tests/async/ -k "prep" -q` |
| **Full suite command** | `.venv/bin/pytest -q` |
| **Estimated runtime** | ~30–90 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

*Populated by the planner from the RESEARCH.md Validation Architecture section.
Each success criterion (PREP-01/02/03) maps to at least one automated test leg:
signature/awaitable, value round-trip (`adbc_prepare` → Schema|None,
`adbc_execute_schema` → Schema), no-execute proof (stub `execute_call_count == 0`),
in-flight cancel (BlockingStubCursor, asyncio + trio), and DuckDB
`NotSupportedError` unsupported-passthrough (EDGE-17).*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 35-01-01 | 01 | 1 | PREP-01 | — | N/A | harness+signature | `.venv/bin/pytest tests/async/test_prep_signature.py -q` + `.venv/bin/basedpyright tests/_async_harness/stubs.py` | ✅ | ✅ COVERED |
| 35-01-02 | 01 | 1 | PREP-01/02 | T-35-02 | clean checkin on native error | integration (DuckDB) + unit (stub) | `.venv/bin/pytest tests/async/test_prep_roundtrip.py tests/async/test_prep_no_execute.py tests/async/test_prep_unsupported.py -q` | ✅ | ✅ COVERED |
| 35-01-03 | 01 | 1 | PREP-01/02 | T-35-02 | non-poisoning cancel (D-35-04) | concurrency (stub, looped) | `ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_prep_cancel.py -q` | ✅ | ✅ COVERED |
| 35-02-01 | 02 | 2 | PREP-01 | T-35-01 | SQL forwarded verbatim to driver | tdd (signature+roundtrip GREEN) | `.venv/bin/pytest tests/async/test_prep_signature.py tests/async/test_prep_roundtrip.py -x -q && .venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py` | ✅ | ✅ COVERED |
| 35-02-02 | 02 | 2 | PREP-02 | T-35-02 | no-execute + native-error passthrough + non-poisoning cancel | tdd (no-execute/unsupported/cancel GREEN) | `.venv/bin/pytest tests/async/test_prep_no_execute.py tests/async/test_prep_unsupported.py -x -q && ADBC_ASYNC_REPEAT=20 .venv/bin/pytest tests/async/test_prep_cancel.py -q` | ✅ | ✅ COVERED |
| 35-03-01 | 03 | 3 | PREP-03 | T-35-05 | caveat matches shipped surface | docs (grep gate) | `grep -q "Prepared statements" docs/src/guides/async.md && ! grep -q "not available yet" docs/src/guides/async.md && ! grep -q "have not shipped yet" docs/src/index.md` | ✅ | ✅ COVERED |
| 35-03-02 | 03 | 3 | PREP-03 | — | N/A | docs gate | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` (exit 0) | ✅ | ✅ COVERED |

---

## Wave 0 Requirements

- [x] RED test module(s) under `tests/async/` — stubs for PREP-01/02 *(all five `test_prep_*.py` created in 35-01, turned GREEN in 35-02)*
- [x] `BlockingStubCursor` extension — blocking `adbc_prepare` / `adbc_execute_schema`
      + call counters (must NOT touch `execute_call_count` — the no-execute proof) *(landed in 35-01, `tests/_async_harness/stubs.py`)*

*Existing async test infrastructure (Phase 23/27/32 harness) covers the rest.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `mkdocs build --strict` + humanizer pass | PREP-03 | Prose/build gate | `.venv/bin/mkdocs build --strict` |

*All runtime behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-07-05 — all 7 legs green, 0 gaps

---

## Validation Audit 2026-07-05

Retroactive audit of the executed phase (State A). The plan-time VALIDATION.md
carried every task as `⬜ pending` / `❌ W0`; all three plans have since executed
and every automated leg was re-run green during this audit:

- `test_prep_signature/roundtrip/no_execute/unsupported` → 8 passed (asyncio + trio)
- `ADBC_ASYNC_REPEAT=20 test_prep_cancel` → 80 passed, 0 hangs
- docs grep gate → heading present, no stale caveat in `async.md`/`index.md`
- `mkdocs build --strict` → exit 0

| Metric | Count |
|--------|-------|
| Requirements | 3 (PREP-01/02/03) |
| Task legs | 7 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| COVERED | 7 |

**Result:** Phase 35 is Nyquist-compliant. No tests generated (none missing).
