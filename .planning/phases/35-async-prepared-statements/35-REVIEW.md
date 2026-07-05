---
phase: 35-async-prepared-statements
reviewed: 2026-07-04T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/adbc_poolhouse/_async/_cursor.py
  - tests/_async_harness/stubs.py
  - tests/async/test_prep_signature.py
  - tests/async/test_prep_roundtrip.py
  - tests/async/test_prep_no_execute.py
  - tests/async/test_prep_unsupported.py
  - tests/async/test_prep_cancel.py
  - docs/src/guides/async.md
  - docs/src/index.md
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: resolved
resolved_in: 1980f95
---

# Phase 35: Code Review Report

**Depth:** standard | **Files Reviewed:** 9 | **Status:** resolved (all 4 findings fixed in `1980f95`)

> **Resolution (commit `1980f95`):** WR-01 — the prepared-statements guide example now
> creates table `t` and wraps `adbc_execute_schema` in DuckDB's real `NotSupportedError`
> path, so it runs end-to-end (verified). WR-02 — the non-poisoning claim is scoped in the
> guide and both docstrings to drivers that leave no session state after a cancelled prepare,
> with a PostgreSQL-style caveat. IN-01 — `adbc_execute_schema` `operation` widened to
> `bytes | str` (method + Protocol) for parity. IN-02 — the misleading "prepare once then
> run" comment reworded. `basedpyright` strict, `ruff`, the 12 prep tests, and
> `mkdocs build --strict` all remain green after the fixes.

## Summary

Phase 35 adds `AsyncCursor.adbc_prepare` and `adbc_execute_schema` as offloaded,
cancellable-but-non-poisoning wrappers, plus `_SyncCursor` Protocol entries,
`BlockingStubCursor` extensions, and five test modules. The core implementation is
correct against the stated template.

Verification performed:
- The two new methods clone the `execute` offload shape exactly, minus `on_abort`.
  `cancellable_offload`'s `on_abort` parameter defaults to `None` (`_cancel.py:46`),
  so omission is valid: `adbc_cancel` still fires on a real abort (`_cancel.py:183-185`)
  but `on_abort`/invalidate is skipped (`_cancel.py:191`). This matches D-35-04.
  **Confirmed intended, not a bug.**
- Both `cast` calls are inert and correctly typed off the `-> object` Protocol
  returns; `basedpyright` reports 0 errors.
- No concurrency/cancel divergence from the `execute` template: both use
  `self._owner._offloading()` + `self._adbc_cancel` identically.
- Real ADBC dbapi signatures match the positional forwarding: `adbc_prepare(operation)`,
  `adbc_execute_schema(operation, parameters=None)`.
- Harness stubs bump `prepare_call_count` / `execute_schema_call_count` and **never
  touch `execute_call_count`** (`stubs.py:487, 517`) — the PREP-02 no-execute proof holds.
- All 12 prep tests pass; `mkdocs build --strict` passes.

No BLOCKER-level defects found. The findings below are a documentation defect, a
scoped design-assumption risk, and two minor consistency notes.

## Warnings

### WR-01: Prepared-statements docs example is non-runnable on the DuckDB pool it configures

**File:** `docs/src/guides/async.md` (prepared-statements how-to example)
**Issue:** The example opens `managed_async_pool(DuckDBConfig(...))` and then calls both
new methods against that DuckDB pool, but neither line can run:
- `await cursor.adbc_prepare("SELECT * FROM t WHERE id = ?")` — table `t` is never
  created, so DuckDB raises `Catalog Error: Table with name t does not exist`. The
  `test_prep_roundtrip.py` test correctly does `CREATE TABLE t` first; the doc omits it.
- `await cursor.adbc_execute_schema("SELECT id, name FROM t")` — DuckDB raises
  `NotSupportedError` (also asserted by `test_prep_unsupported.py`). This contradicts the
  guide's own prose below ("DuckDB raises the driver's native `NotSupportedError`").

A reader copy-pasting the canonical example gets a crash on both statements. Given the
project's documentation quality gate, this is a real defect.
**Fix:** Add a `CREATE TABLE t (...)` before `adbc_prepare`, and mark the
`adbc_execute_schema` line as running on a backend that implements it (not DuckDB), or
show the `NotSupportedError` path explicitly. Use the schema results so the snippet reads
as runnable.

### WR-02: "Writes no state / returns clean" non-poisoning claim is asserted universally but is backend-specific

**File:** `src/adbc_poolhouse/_async/_cursor.py` (adbc_prepare / adbc_execute_schema
docstrings + inline comments); mirrored in `docs/src/guides/async.md`
**Issue:** The docstrings and inline comments justify omitting `on_abort` with a universal
claim: "a prepare writes no state, so an aborted call leaves the connection clean." This
holds for DuckDB (the tested backend). But on some backends a mid-statement cancel leaves
*session* state: PostgreSQL, for example, puts the session's transaction into an aborted
state after a cancel, and every subsequent command fails until a rollback. Returning such
a connection to the pool without `invalidate` would hand a poisoned connection to the next
checkout.

D-35-04 is a locked decision and the cancellable-but-non-poisoning shape is intended, so
this is not a code-change request. But the universality of the "clean" claim is unproven
for non-DuckDB drivers and the risk is undocumented.
**Fix:** Scope the claim: state that non-poisoning assumes the driver leaves no
session/transaction state after `adbc_cancel` on a prepare/schema call (true for DuckDB),
and note backends with cancel-aborts-transaction semantics may need invalidation. Track a
follow-up to validate against the ADBC PostgreSQL driver before the async surface leaves
"experimental."

## Info

### IN-01: `adbc_execute_schema` narrows `operation` to `str` while `execute`/`adbc_prepare` accept `bytes | str`

**File:** `src/adbc_poolhouse/_async/_cursor.py` (adbc_execute_schema + Protocol)
**Issue:** `execute` and `adbc_prepare` accept `bytes | str`; `adbc_execute_schema` accepts
only `str`. The underlying driver leaves `operation` unannotated (accepts either). Minor,
self-consistent inconsistency (the Protocol is narrowed to match), but a caller with a
`bytes` operation cannot use `adbc_execute_schema`.
**Fix:** Widen to `operation: bytes | str` for parity with the sibling methods, unless the
narrowing is deliberate.

### IN-02: Docs comment overstates the prepare→execute relationship

**File:** `docs/src/guides/async.md` (prepare→execute snippet comment)
**Issue:** The comment "Prepare once, then run the prepared operation with bound parameters"
implies the following `cursor.execute(...)` reuses the prepared plan. It does not — `execute`
sets and re-prepares its own statement; `adbc_prepare` here only yields the bind-parameter
schema and is discarded.
**Fix:** Reword to make clear `adbc_prepare` returns the bind schema and does not pre-stage
the subsequent `execute`.
