---
phase: 30
slug: async-bulk-write
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-01
---

# Phase 30 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Plan-time STRIDE register (register_authored_at_plan_time: true) — this audit
> VERIFIES each declared mitigation is present in shipped code; it does not scan
> for net-new threats. Phase 30 is a thin pass-through wrapper (`AsyncCursor.adbc_ingest`)
> that reuses the Phase 25/29 cancel/offload machinery verbatim — most controls
> resolve to "reused, verified wired into `adbc_ingest`" rather than net-new.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| caller → driver `adbc_ingest` (Arrow binding + SQL identifier) | `table_name`/`data`/`mode` cross into the driver untouched; the driver is the trust anchor. Poolhouse constructs no SQL and performs no validation (pass-through charter). | table name (SQL identifier), Arrow dataset (Table/RecordBatch/Reader/CapsuleType), write mode |
| loop task → offloaded C ingest / pool connection | A cancelled mid-write must not return a poisoned connection to the pool (pool starvation). | one pooled connection; per-call `_in_use` claim |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-30-01 | Denial of Service | poisoned connection returned to pool after a cancelled mid-write (pool starvation) | mitigate | `on_abort=self._owner.invalidate` wired into the `adbc_ingest` offload — `_cursor.py:455`. Recovery drops the poisoned connection shielded (`invalidate` clears `_reader_open`, checks the connection out of the pool — `_connection.py:303-340`). Proven by 20× looped `test_ingest_cancel.py` asserting `adbc_cancel_call_count == 1`, `invalidate_call_count == 1`, `checkedout()` 1→0 under asyncio + trio (`test_ingest_cancel.py:93-94,126-127,156-160`). | closed |
| T-30-02 | Tampering | AST import-lint guard (PKG-03) over `_async/` after adding `functools` | mitigate | `import functools` is a plain stdlib runtime import (`_cursor.py:34`); no `import asyncio` / bare `to_thread` / `asyncio.CancelledError` introduced. Guard re-run live this audit: `tests/test_pkg_import_guard.py` + `tests/async/test_async_guard.py` = 3 passed. | closed |
| T-30-03 | Tampering | `table_name` as an untrusted identifier (injection if a caller interpolates user input) | accept | Pass-through charter: poolhouse constructs no SQL and hands `table_name` straight to the driver's `adbc_ingest`, which owns identifier binding. Documented as a driver-level, non-sanitized identifier in the docstring — `_cursor.py:405-406` ("Passed straight to the driver as a SQL identifier; poolhouse does not quote or sanitize it") and `_cursor.py:392-394`. Logged in Accepted Risks below. | closed (accepted) |
| T-30-04 | Tampering | concurrent C access to one connection (memory corruption) | mitigate | `with self._owner._offloading()` per-call `_in_use` guard wraps the whole ingest — `_cursor.py:442`; a second in-flight op is rejected with `ConnectionBusyError` (`_connection.py:177-178,191-207`). NO `_reader_open` lifetime lock is taken (grep: `_reader_open` absent from the `adbc_ingest` body — whole-op offload, not a lifetime lock). | closed |
| T-30-05 | Tampering | abort-the-abort (double cancellation during recovery) | mitigate | `cancellable_offload` fires `adbc_cancel` exactly once inside `anyio.CancelScope(shield=True)` (D-25-07) — `_cancel.py:184-190`; reused verbatim from Phase 25, unchanged by this phase. `adbc_ingest` calls that same `cancellable_offload` (`_cursor.py:443`). | closed |
| T-30-SC | Tampering | supply chain (npm/pip/cargo installs) | mitigate | Zero new installs. The only new import is stdlib `functools` (`_cursor.py:34`); `Literal`/`CapsuleType` are annotation-only under `TYPE_CHECKING` from already-shipped `typing`/`typing_extensions`. `pyproject.toml` is untouched across the phase commits (`git diff d11467e~1 69aaf7c -- pyproject.toml` empty; last change predates Phase 30). | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-30-01 | T-30-03 | `table_name` is an untrusted SQL identifier handed unmodified to the driver. Consistent with the whole library's pass-through charter: poolhouse constructs no SQL and delegates identifier binding to the driver, so it adds no quoting/sanitization. Callers that interpolate untrusted input into `table_name` own the injection risk. Documented in the `adbc_ingest` docstring (`_cursor.py:392-394,405-406`). | plan-time STRIDE register (30-02-PLAN.md), confirmed by this audit | 2026-07-01 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-01 | 6 | 6 | 0 | gsd-security-auditor |

### Verification notes

- **No `## Threat Flags` section** appears in either `30-01-SUMMARY.md` or `30-02-SUMMARY.md`; no unregistered attack surface to log. The 30-02 SUMMARY "Threat Register Outcome" maps 1:1 to the plan-time register (T-30-01/02/03/04/05) — all informational, no orphans.
- Every `mitigate` threat was confirmed by locating the actual control in code (file:line above), not by documentation or intent. T-30-01/04/05 reuse the Phase 25/29 machinery — confirmed the reused machinery is genuinely wired into `adbc_ingest` (`_cursor.py:442-456`), not merely claimed.
- T-30-03 (`accept`) verified by the presence of the accepted-risk entry (AR-30-01) plus the required driver-level-identifier documentation in the shipped docstring.
- Guard (T-30-02) re-run live: `tests/test_pkg_import_guard.py tests/async/test_async_guard.py` → 3 passed.
- Supply chain (T-30-SC): `pyproject.toml` diff empty across the phase; only new import is stdlib `functools`.
- Implementation files were read-only throughout; only this SECURITY.md was written.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-01
