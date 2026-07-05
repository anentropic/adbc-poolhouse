---
phase: 31
slug: dataframe-convenience
status: secured
threats_open: 0
asvs_level: 1
created: 2026-07-02
---

# Phase 31 — DataFrame Convenience: Security Audit

**Phase:** 31 — dataframe-convenience
**Audited:** 2026-07-02
**ASVS Level:** 1
**Block-on:** high
**Result:** SECURED — 5/5 threats closed
**Threats open:** 0

This audit verifies each threat in the Phase 31 register by its declared
disposition. Every `mitigate` threat was confirmed by locating the actual
control in the implementation (not documentation) and by running its proving
test. Every `accept` threat was confirmed factually correct against the code and
`pyproject.toml`.

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-31-01 | Denial of Service (poisoned connection after cancelled materialization) | mitigate | CLOSED | `on_abort=self._owner.invalidate` wired into both `fetch_df` (`_cursor.py:423`) and `fetch_polars` (`_cursor.py:475`) `cancellable_offload` calls. Abort chain confirmed in `_cancel.py:184-193`: on cancel, `adbc_cancel()` fires once (shielded) then `await on_abort()` runs the connection's poison-recovery; `_connection.py:303-340` `invalidate` drops the connection and clears `_reader_open`. Proven by `test_df_cancel.py` asserting `adbc_cancel_call_count == 1` + `invalidate_call_count == 1` (stub + timeout legs) and `checkedout()` 1→0 (DuckDB drain leg), under asyncio + trio, `concurrency_marks`-looped. |
| T-31-02 | Denial of Service (use-after-free / segfault reading a frame after checkin) | mitigate | CLOSED | Approach A: both methods offload the driver's bare native `self._cursor.fetch_df` (`_cursor.py:421`) / `self._cursor.fetch_polars` (`_cursor.py:473`), which materialize frame-owned buffers not bound to the connection C stream. No `RecordBatchReader` wrap, no `_reader_open` lifetime lock in either method. Proven by `test_df_lifetime.py` reading `df["a"].tolist()` / `.to_list()` AFTER the `async with ... as conn:` block exits (connection checked in). |
| T-31-03 | Tampering (concurrent C-access on one connection) | mitigate | CLOSED | `with self._owner._offloading():` brackets both method bodies (`_cursor.py:412`, `:464`). `_connection.py:177-184` `_enter_offload` raises `ConnectionBusyError` when `_in_use` is already set (single synchronous check-and-set span, Pitfall 3). Proven by `test_df_busy.py`: a second in-flight op on the same connection raises `ConnectionBusyError` while a worker is gated inside `fetch_df`/`fetch_polars`; `concurrency_marks`-looped, dual-backend. |
| T-31-04 | Information Disclosure / Tampering (poolhouse owning the pandas/polars import site) | accept (by design) | CLOSED | Acceptance is factually correct. Grep over `_cursor.py` finds NO `find_spec`, NO `import importlib`, NO `except ModuleNotFoundError`/`except ImportError`, and NO top-level (runtime) `import pandas`/`import polars` — the imports live only under `if TYPE_CHECKING:` (`_cursor.py:49-50`). The driver imports pandas/polars in the worker; the native `ModuleNotFoundError` crosses the single `to_thread.run_sync` chokepoint (`_offload.py:105`) unwrapped (EDGE-17, `_offload.py` re-raises with exact type). Proven by `test_df_missing_dep.py` asserting `ei.value.name == "pandas"/"polars"` AND `not isinstance(ei.value, PoolhouseError)`. Documented as an accepted-by-design risk below. |
| T-31-SC | Tampering (dev-group pandas/polars supply-chain) | accept (verified) | CLOSED | Acceptance is factually correct. `pandas>=2.0`, `pandas-stubs>=2.0`, `polars>=1.0` appear ONLY under `[dependency-groups].dev` (`pyproject.toml:47-56`). `[project.dependencies]` (`:10-14`) contains only `pydantic-settings`, `sqlalchemy`, `adbc-driver-manager` — no pandas/polars. `[project.optional-dependencies]` (`:16`) is empty of them; zero `[pandas]`/`[polars]`/`[dataframe]` extras exist. Never a runtime import (see T-31-04). Not shipped to consumers. Canonical top-download PyPI packages (pandas-dev/pandas, pola-rs/polars). Documented as an accepted-verified risk below. |

**Live verification:** `test_df_cancel.py`, `test_df_busy.py`, `test_df_lifetime.py`,
`test_df_missing_dep.py` → **22 passed** (0.24s).

---

## Accepted Risks Log

### T-31-04 — poolhouse does not own the pandas/polars import site (accept, by design)

Poolhouse deliberately performs no pre-flight `find_spec` and no
`try/except ImportError` around `fetch_df`/`fetch_polars`. A missing pandas or
polars install surfaces the driver's native `ModuleNotFoundError` unchanged
(exact `.name`, not a `PoolhouseError`), propagated through the single
`to_thread.run_sync` offload chokepoint. This is the intended contract:
pandas/polars are user-supplied runtime dependencies, and the failure mode is
identical to calling the underlying sync ADBC method directly. Any `find_spec`
or wrapping would be a defect; `test_df_missing_dep.py` enforces its absence.

**Accepted by:** phase threat model (D-31-02 / D-31-05). **Residual risk:** none
beyond the standard "optional dependency not installed" surface, which is
correctly and predictably reported.

### T-31-SC — dev-group pandas/polars supply-chain (accept, verified)

pandas and polars (plus the `pandas-stubs` typing-only stub package) are
declared exclusively in `[dependency-groups].dev`. They are never a runtime
import (guarded to `TYPE_CHECKING` in `_cursor.py`), never a `[project]`
dependency, never an extra, and are therefore never installed for or shipped to
consumers of the library. Both are canonical, top-download PyPI packages
(github.com/pandas-dev/pandas, github.com/pola-rs/polars). No `[SLOP]`/`[SUS]`
packages were introduced; no legitimacy checkpoint is required.

**Accepted by:** phase threat model (D-31-08 / PKG-02). **Residual risk:** limited
to the local dev/test toolchain; no consumer-facing supply-chain exposure.

---

## Unregistered Flags

None. The Plan 31-02 `SUMMARY.md ## Threat Flags` section reports "None" and
explicitly maps all controls to the existing register IDs (T-31-01..04),
reusing the shipped `_offloading()`/`_in_use` guard, the
`on_abort=invalidate` recovery, and the single `to_thread.run_sync` chokepoint —
no new network endpoint, auth path, file access, or trust boundary beyond what
`fetch_arrow_table` already crosses. Plan 31-01 declared no threat flags. No new
attack surface appeared during implementation.

---

## Audit Notes

- Implementation files were treated as READ-ONLY; only this SECURITY.md was written.
- Every `mitigate` threat was verified by locating the control in the named source
  file at a specific line AND running its proving test — not by accepting the
  verification report or summary prose.
- Both `accept` dispositions were re-verified factually against the code and
  `pyproject.toml`, not taken on the register's word.
