---
phase: 35-async-prepared-statements
plan: 01
subsystem: testing
tags: [async, pyarrow, adbc, prepared-statements, pytest, anyio, red-scaffolding, tdd]

# Dependency graph
requires:
  - phase: 34-async-metadata
    provides: "cancellable/non-cancellable offload precedent + BlockingStubCursor harness + test_meta_cancel non-poisoning assertion pattern"
  - phase: 30-async-bulk-write
    provides: "adbc_ingest blocking-stub method template + Wave-0 RED pyright-pragma convention + test_ingest_cancel scaffold"
provides:
  - "BlockingStubCursor.adbc_prepare / adbc_execute_schema blocking methods + prepare_call_count / execute_schema_call_count counters + injectable _prepare_result / _execute_schema_result (never touch execute_call_count)"
  - "Five RED test files (tests/async/test_prep_{signature,roundtrip,no_execute,unsupported,cancel}.py) encoding PREP-01/02 before any production symbol exists"
  - "Fixed GREEN target for plan 35-02 (adbc_prepare + adbc_execute_schema on AsyncCursor)"
affects: [35-02 (implementation turns these RED tests GREEN), 35-03 (docs)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-axis cancel test (cancellable AND non-poisoning): hybrid of test_ingest_cancel (adbc_cancel==1) + test_meta_cancel (invalidate==0) for D-35-04"
    - "No-execute proof via decoupled stub counters: prepare/execute_schema counters bump independently of execute_call_count"
    - "Return-shape tolerance: adbc_prepare round-trip asserts isinstance(result, (pyarrow.Schema, type(None)))"

key-files:
  created:
    - tests/async/test_prep_signature.py
    - tests/async/test_prep_roundtrip.py
    - tests/async/test_prep_no_execute.py
    - tests/async/test_prep_unsupported.py
    - tests/async/test_prep_cancel.py
  modified:
    - tests/_async_harness/stubs.py

key-decisions:
  - "PREP-01/02 stay Pending in REQUIREMENTS.md — a RED scaffold does not satisfy the behavioral requirement; they are marked complete at 35-02 (mirrors META at 34-02)"
  - "Wave-0 pyright pragmas suppress not-yet-existing-method errors on the four method-referencing test files (whole-project basedpyright-strict hook would otherwise reject them) — Phase 30 precedent; green-wave TODO to delete once 35-02 lands the symbols"

patterns-established:
  - "Blocking stub methods for a new offloaded cursor method: del args → bump own counter under lock → _block() → return injectable result; never couple to execute_call_count"
  - "RED cancel test gates on the method's own in-flight counter (prepare_call_count >= 1) via await_inside before cancelling"

requirements-completed: []  # PREP-01/02 satisfied at 35-02 (implementation); this plan is RED-only scaffolding

# Metrics
duration: 8min
completed: 2026-07-04
---

# Phase 35 Plan 01: Async Prepared-Statement RED Scaffolding Summary

**Five RED tests/async/test_prep_*.py files (signature, DuckDB round-trip, stub no-execute, DuckDB NotSupportedError passthrough, two-axis non-poisoning cancel) plus a BlockingStubCursor extension, all failing RED with AttributeError before AsyncCursor.adbc_prepare / adbc_execute_schema exist.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-07-04T20:00:36Z
- **Completed:** 2026-07-04T20:08:13Z
- **Tasks:** 3
- **Files modified:** 6 (1 harness extended, 5 tests created)

## Accomplishments
- Extended `BlockingStubCursor` with blocking `adbc_prepare` / `adbc_execute_schema` (mirroring `adbc_ingest`), two new counters, and two injectable result knobs — all decoupled from `execute_call_count` so the PREP-02 no-execute proof reads it as `0`.
- Encoded the PREP-01 signature + DuckDB round-trip contracts (round-trip tolerates `pyarrow.Schema` OR `None` per D-35-02; `checkedout() == 0` after scope — no reader lifetime lock).
- Encoded the PREP-02 no-execute proof (injected sentinel `pyarrow.Schema` passes through unchanged AND `execute_call_count == 0`) and the native-error passthrough (`NotSupportedError` unwrapped on DuckDB, EDGE-17).
- Encoded the D-35-04 two-axis cancel: `adbc_cancel_call_count == 1` (cancellable) AND `invalidate_call_count == 0` (non-poisoning), across an explicit-cancel leg and a `fail_after` timeout twin, dual-backend under the `concurrency_marks` 20x loop, real-clock watchdog, 0 hangs.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend BlockingStubCursor + signature RED test** - `c7e517e` (test)
2. **Task 2: Round-trip + no-execute + unsupported RED tests** - `1279e2a` (test)
3. **Task 3: Deterministic non-poisoning cancel RED test** - `7114f62` (test)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified
- `tests/_async_harness/stubs.py` - Added blocking `adbc_prepare` / `adbc_execute_schema`, `prepare_call_count` / `execute_schema_call_count` counters, `_prepare_result` / `_execute_schema_result` injectables, and the `Attributes:` docstring entries. Neither method touches `execute_call_count`.
- `tests/async/test_prep_signature.py` - PREP-01 existence contract (sync introspection, no marker, no fixtures).
- `tests/async/test_prep_roundtrip.py` - PREP-01 `adbc_prepare` DuckDB round-trip; `isinstance(result, (pyarrow.Schema, type(None)))`; post-scope `checkedout() == 0`.
- `tests/async/test_prep_no_execute.py` - PREP-02 stub value pass-through + `execute_call_count == 0` (the no-execute proof); event-gated release under real-clock watchdog.
- `tests/async/test_prep_unsupported.py` - PREP-02 DuckDB native `NotSupportedError` passthrough (EDGE-17), `checkedout() == 0` after the failed call.
- `tests/async/test_prep_cancel.py` - PREP-01/02 non-poisoning cancel (D-35-04): explicit-cancel + timeout twin, `adbc_cancel_call_count == 1` and `invalidate_call_count == 0`.

## Decisions Made
- **PREP-01/02 remain Pending in REQUIREMENTS.md.** A Wave-1 RED scaffold pins the contract but does not deliver the behavior; the requirements are marked complete at 35-02, exactly as META-01/02 were marked at 34-02 (not the 34-01 RED scaffold). This keeps traceability honest.
- **`adbc_prepare`/`adbc_execute_schema` NOT implemented on `AsyncCursor` here** (per plan scope) — Wave 1 is RED-only; 35-02 clones `execute` (dropping `on_abort`) to turn these GREEN.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added Wave-0 pyright suppression pragmas to the four method-referencing test files**
- **Found during:** Task 2 (round-trip/no-execute/unsupported commit)
- **Issue:** The `basedpyright` pre-commit hook runs strict whole-project (`pass_filenames: false`, `include = ["src", "tests"]`). The RED tests reference `AsyncCursor.adbc_prepare` / `adbc_execute_schema`, which do not exist yet, producing 8 `reportAttributeAccessIssue` / `reportUnknownMemberType` / `reportUnknownVariableType` / `reportUnknownArgumentType` errors that blocked the commit. The plan's `<verify>` only ran `basedpyright` on `stubs.py`, so the whole-project hook interaction surfaced at commit time.
- **Fix:** Added a file-level `# pyright: report*=false` pragma block (with a "delete once the method lands" comment) to `test_prep_roundtrip.py`, `test_prep_no_execute.py`, `test_prep_unsupported.py`, and `test_prep_cancel.py` — the exact Phase 30 RED precedent (`git show fc9a734:tests/async/test_ingest_roundtrip.py`). `test_prep_signature.py` needed none (it uses `hasattr` string lookups, no static attribute access).
- **Files modified:** the four test files above.
- **Verification:** `.venv/bin/basedpyright <files>` → 0 errors; the `basedpyright` pre-commit hook passed on Tasks 2 and 3. Tests still fail RED at runtime (pragmas are static-only).
- **Committed in:** `1279e2a` (Task 2) and `7114f62` (Task 3).

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** Necessary to satisfy the strict-typing completion gate while keeping the RED scaffold; matches established repo precedent. No scope creep. Recorded as a green-wave TODO (delete pragmas in 35-02).

## Issues Encountered
- The `basedpyright` pre-commit hook panicked on the first commit attempt (a macOS SystemConfiguration `dynamic_store.rs` NULL-object panic) under the command sandbox. The direct `.venv/bin/basedpyright` run passed cleanly (0 errors), confirming a sandbox-blocked system call rather than a code defect. Resolved by running the `git commit` with the sandbox disabled for the hook's system access (MEMORY: prefer `.venv/bin/<tool>`; sandbox-workaround gotcha).
- Task 1's first commit also tripped a ruff `E501` on the `adbc_execute_schema` docstring summary line (104 > 100) — shortened before re-committing.

## Known Stubs
None that block the plan's goal. The two new `BlockingStubCursor` methods return injectable `None` by default — that is intentional test-harness behavior (the no-execute test injects a sentinel `pyarrow.Schema`; the cancel test never reads the return value), not a UI/data stub. The public `AsyncCursor` methods are deliberately absent (RED scaffolding); 35-02 implements them.

## Threat Flags
None. This plan adds only test scaffolding and two blocking stub methods — no new network endpoint, auth path, file access, or schema surface. The threat register's T-35-02 (connection-busy-after-cancel) mitigation is encoded by `test_prep_unsupported.py` (`checkedout() == 0` after a native error) and `test_prep_cancel.py` (`invalidate_call_count == 0`, no hang).

## Docs Quality Gate (CLAUDE.md, phases >= 7)
N/A for this test-only plan — no new public consumer-facing symbol, no guide/prose change. The two new stub methods carry Google-style Markdown docstrings (Args/Returns). PREP-03 (guide caveat removal + API reference + `mkdocs build --strict` + humanizer) is plan 35-03; the phase docs completion gate is evaluated at phase close.

## Next Phase Readiness
- Plan 35-02 has a fixed, un-fakeable GREEN target: five RED test files + the harness counters they read. Implementation clones `AsyncCursor.execute` twice (swap callable + return type, drop `on_abort`) and extends the `_SyncCursor` Protocol (D-35-01..05).
- Green-wave TODO carried into 35-02: delete the Wave-0 pyright pragma blocks from the four test files once `adbc_prepare` / `adbc_execute_schema` land, and mark PREP-01/02 complete in REQUIREMENTS.md.

## Self-Check: PASSED

All five test files + SUMMARY.md exist on disk; all four commits (`c7e517e`, `1279e2a`, `7114f62`, `a6e53e5`) present in git; `BlockingStubCursor.adbc_prepare` confirmed in `stubs.py`.

---
*Phase: 35-async-prepared-statements*
*Completed: 2026-07-04*
