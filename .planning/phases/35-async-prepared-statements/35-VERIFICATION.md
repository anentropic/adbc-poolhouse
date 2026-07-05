---
phase: 35-async-prepared-statements
verified: 2026-07-04T21:30:00Z
status: passed
score: 3/3 must-haves verified
overrides_applied: 0
re_verification: null
---

# Phase 35: Async Prepared Statements Verification Report

**Phase Goal:** `adbc_prepare` and `adbc_execute_schema` are available on the async cursor as pure offload wrappers over the wrapped sync `dbapi.Cursor`, routed through the existing `offload`/`cancellable_offload` chokepoint and per-pool `CapacityLimiter`. Behavior mirrors the sync statement lifecycle — `adbc_execute_schema` returns the result Arrow schema without executing the query — with no invented async-specific error types. Closes the second async/sync parity gap named in the v1.5.0 docs caveat.
**Verified:** 2026-07-04T21:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Merged from ROADMAP Success Criteria (SC1-3 = PREP-01/02/03) and PLAN frontmatter truths.

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1 (PREP-01) | `adbc_prepare` and `adbc_execute_schema` are awaitable on `AsyncCursor`, each an offload wrapper over the sync counterpart through `cancellable_offload` + per-pool `CapacityLimiter` | ✓ VERIFIED | `_cursor.py:570` `async def adbc_prepare` and `:631` `async def adbc_execute_schema`; both wrap `with self._owner._offloading():` around a single `await cancellable_offload(self._adbc_cancel, self._cursor.adbc_prepare/adbc_execute_schema, ..., limiter=self._limiter)` — structurally identical to `execute` (`:225-233`). `test_prep_signature.py` + `test_prep_roundtrip.py` pass. |
| 2 (PREP-02) | Behavior mirrors sync — `adbc_execute_schema` returns the result Arrow schema WITHOUT executing; no invented async error types; native driver errors surface unchanged | ✓ VERIFIED | No-execute proof: `test_prep_no_execute.py:95-96` asserts `result is sentinel` AND `stub_cursor.execute_call_count == 0`; stub `adbc_execute_schema` (`stubs.py:491-519`) bumps only `execute_schema_call_count`, never `execute_call_count`. Native error passthrough: `test_prep_unsupported.py` asserts DuckDB `NotSupportedError` unwrapped. No try/except, no `find_spec`, no wrapping in either method body. |
| 3 (PREP-03) | Async guide + API reference document the methods, caveat line removed; `mkdocs build --strict` passes; humanizer pass applied | ✓ VERIFIED | `async.md:352` `## Prepared statements` section with plain fenced python block; `:25-26` "What you get today" lists both methods; "not available yet" block absent; `index.md:71` stale "have not shipped yet" clause dropped. `mkdocs build --strict` exit 0. API reference renders both methods (32 hits in `site/reference/adbc_poolhouse/index.html`). |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `src/adbc_poolhouse/_async/_cursor.py` | Both AsyncCursor methods + `_SyncCursor` Protocol signatures | ✓ VERIFIED | `adbc_prepare` (`:570`), `adbc_execute_schema` (`:631`), Protocol lines `:94-97`. Full Google-style docstrings with `Example:`. basedpyright strict: 0 errors. |
| `tests/_async_harness/stubs.py` | Blocking prepare/execute_schema + counters decoupled from `execute_call_count` | ✓ VERIFIED | `prepare_call_count`/`execute_schema_call_count` (`:186-187`), injectables (`:201-202`), blocking methods (`:460`,`:491`); neither touches `execute_call_count`. |
| `tests/async/test_prep_*.py` (5 files) | PREP-01/02 contracts | ✓ VERIFIED | All 5 present; 12 prep tests pass (asyncio+trio); cancel test 80/80 under 20x loop. |
| `docs/src/guides/async.md` | caveat removed + section + snippet | ✓ VERIFIED | See truth 3. |
| `docs/src/index.md` | stale clause dropped | ✓ VERIFIED | `:71` now only the experimental note. |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `AsyncCursor.adbc_prepare/adbc_execute_schema` | `self._cursor.adbc_*` (cast `_SyncCursor`) | `cancellable_offload(self._adbc_cancel, ..., limiter=self._limiter)`, `on_abort` OMITTED | ✓ WIRED | `_cursor.py:618-629`, `:684-696` — `on_abort` deliberately absent (D-35-04 non-poisoning); `cast("pyarrow.Schema | None"/"pyarrow.Schema", ...)`. |
| async methods | return type | `cast` off `-> object` Protocol | ✓ WIRED | Casts present at `:618` and `:684`. |
| test files | `BlockingStubCursor` counters | `make_stub_async_connection → cursors[-1]` | ✓ WIRED | `test_prep_cancel.py:85` gates on `prepare_call_count >= 1`; `test_prep_no_execute.py:85` sets `_execute_schema_result`. |

### Data-Flow Trace (Level 4)

N/A — methods forward a driver-produced `pyarrow.Schema` (or `None`) straight from the offloaded sync ADBC call; no rendered dynamic data source to trace. The no-execute proof (`execute_call_count == 0` while returning the injected sentinel) is the equivalent flow check and passes.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Prep suite green (asyncio+trio) | `pytest tests/async/ -k prep -q` | 12 passed, 239 deselected | ✓ PASS |
| Non-poisoning cancel, no hang | `ADBC_ASYNC_REPEAT=20 pytest tests/async/test_prep_cancel.py -q` | 80 passed, 0 hangs | ✓ PASS |
| Strict types over source | `basedpyright src/adbc_poolhouse/_async/_cursor.py` | 0 errors, 0 warnings, 0 notes | ✓ PASS |
| Strict docs build | `DISABLE_MKDOCS_2_WARNING=true mkdocs build --strict` | exit 0 | ✓ PASS |
| API reference render | `grep -c adbc_* site/reference/.../index.html` | 32 hits | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| PREP-01 | 35-01, 35-02 | Both methods awaitable, offload wrappers via chokepoint + limiter | ✓ SATISFIED | Truth 1; REQUIREMENTS.md `Complete (35-02)` |
| PREP-02 | 35-01, 35-02 | Mirrors sync; execute_schema returns schema without executing; no invented errors | ✓ SATISFIED | Truth 2; REQUIREMENTS.md `Complete (35-02)` |
| PREP-03 | 35-03 | Guide + API reference document methods, caveat removed, strict build, humanizer | ✓ SATISFIED | Truth 3; REQUIREMENTS.md `Complete (35-03)` |

All 3 phase requirement IDs accounted for. No orphaned requirements (REQUIREMENTS.md maps exactly PREP-01..03 to Phase 35).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | none | — | No `TBD/FIXME/XXX`, no leftover `# pyright: report*=false` Wave-0 pragmas (removed in commit `d3dd2b7`), no stub returns in production code. |

### Human Verification Required

None. All truths are verifiable programmatically (test suite, type checker, docs build, and rendered HTML inspection all executed in-process and passed).

### Gaps Summary

No gaps. All three success criteria (PREP-01/02/03) are observably true in the codebase:
- Both async methods exist, are offload wrappers over the sync `dbapi.Cursor` methods through the `cancellable_offload` chokepoint and per-pool `CapacityLimiter`, and OMIT `on_abort` (cancellable but non-poisoning, D-35-04) as the deliberate difference from `execute`.
- `adbc_execute_schema` returns the result schema without executing (proven by `execute_call_count == 0` on the stub); native `NotSupportedError` surfaces unchanged; no invented async error types.
- Docs caveat retired, both methods documented in the async guide and auto-rendered API reference, `mkdocs build --strict` green.

The prior code review (`35-REVIEW.md`, status: resolved, 0 critical) fixes are present in commit `1980f95`. No unreferenced debt markers.

---

_Verified: 2026-07-04T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
