---
title: Phase 34 Async Metadata — Code Review
phase: 34-async-metadata
depth: standard
files_reviewed: 6
status: issues_found
findings:
  blocker: 1
  warning: 2
  info: 2
  total: 5
---

# Phase 34: Code Review Report

**Depth:** standard
**Files reviewed:** `src/adbc_poolhouse/_async/_connection.py`, `tests/async/test_meta_signature.py`, `tests/async/test_meta_roundtrip.py`, `tests/async/test_meta_stream.py`, `tests/async/test_meta_unsupported.py`, `docs/src/guides/async.md`
**Status:** issues_found

## Summary

The six metadata methods are wired correctly for the happy path: `functools.partial` kwarg forwarding is right, the `_offloading()` bracketing matches `commit`/`rollback`, and the `_reader_open = True` timing (after the guard span, success-path only, no intervening `await`) is a faithful copy of `fetch_record_batch`. The `NotSupportedError` pass-through and the busy-guard tests are meaningful and honor the `tests/async/` dual-backend + `checkedout()==0` discipline.

The real problem is in the **cancellation path of the three streaming methods**. They reuse the cursor's `AsyncRecordBatchReader` but hand it `_noop_cancel` while leaving `on_abort=self._owner.invalidate` intact inside `__anext__`. That combination is unsafe in a way the cursor reader never was, because the cursor always passes a *real* `adbc_cancel`.

## Blocker

### CR-01: Cancelled metadata-reader pull invalidates the connection concurrently with a still-blocked worker thread

**File:** `src/adbc_poolhouse/_async/_connection.py` (the three `AsyncRecordBatchReader(..., _noop_cancel)` constructions) in combination with `src/adbc_poolhouse/_async/_reader.py:250-257` and `src/adbc_poolhouse/_async/_cancel.py:178-200`.

**Issue:** The three streaming methods build the shared reader with `_noop_cancel` as the cancel hook, but every per-batch pull still runs through `cancellable_offload(self._adbc_cancel, _pull, ..., on_abort=self._owner.invalidate)`. Trace a pull cancelled by an outer `fail_after`/`move_on_after` while a batch is in flight (realistic: wrapping `async for batch in reader` in a deadline):

1. `_watcher` receives the cancellation, `worker_started` is `True`.
2. It fires `adbc_cancel()` — here `_noop_cancel()`, a no-op. **The worker thread is NOT unblocked and stays inside the driver's `read_next_batch()` on the connection** (`offload` runs with `abandon_on_cancel=False`, so the task group joins the worker).
3. It sets `aborted_by_us = True` unconditionally and then `await on_abort()` → `self._owner.invalidate()`.
4. `invalidate()` dispatches a *second* worker thread (via the separate `_teardown_limiter`, so it is not throttled behind the pool token the first worker holds) running `self._fairy.invalidate()` on the **same ADBC connection the first worker is still reading from**.

This is exactly the concurrent, cross-thread access to one ADBC connection the library forbids ("serialized access but not concurrent access" — module docstrings and `docs/src/guides/async.md`). For the cursor reader the hazard does not exist: its real `adbc_cancel` genuinely aborts the in-flight C call before/around `invalidate`. With `_noop_cancel` the worker is *guaranteed* to still be blocked when `invalidate` runs.

Secondary defect on the same path: because `aborted_by_us` is set even though nothing was actually aborted, a cancelled metadata pull **permanently drops an otherwise-healthy connection from the pool** — poison-recovery runs on a connection that was never poisoned.

The locked decision to use `_noop_cancel` is accepted; the defect is that it is combined with `on_abort=invalidate` in the reader, so the cancel branch fires connection teardown while the driver call is still executing on another thread.

**Fix (reviewer-recommended):** Give the connection-level reader an `on_abort=None` path (or an `AsyncRecordBatchReader` variant / constructor flag that skips poison-recovery when the cancel hook is a no-op), so a cancelled metadata pull re-raises the cancellation and lets the worker finish its read normally without a second thread touching the connection. The reader still can't be aborted mid-read (accepted, non-cancellable per the locked decision), but no cross-thread invalidate races the live read, and a non-poisoned connection is not dropped. Add a real-DuckDB loop test (`ADBC_ASYNC_REPEAT=20`, both backends) that cancels an in-flight `adbc_get_objects` pull with `fail_after` and asserts no crash/hang and correct pool accounting (see WR-02).

## Warnings

### WR-01: `_noop_cancel` docstring rationale is copy-pasted from `_pull` and is inaccurate

**File:** `src/adbc_poolhouse/_async/_connection.py` (the `_noop_cancel` definition)

- "`AsyncRecordBatchReader` still requires a 4-argument cancel hook" — the hook takes **zero** arguments (`def _noop_cancel() -> None`); it is the reader's 4th *constructor parameter*.
- "It is a module-level function (not a lambda) so it preserves the offload `TypeVarTuple` arity" — lifted from `_pull`'s docstring, where it is correct because `_pull` is the offloaded `fn`. `_noop_cancel` is passed as the `adbc_cancel` callback (`Callable[[], None]`), never part of the `TypeVarTuple` spread. A lambda would behave identically; the arity justification does not apply.

**Fix:** Reword: the reader takes a zero-argument cancel callback as its fourth constructor argument; a module-level function keeps the `scan_async_package` source-guard matcher clean (drop the TypeVarTuple claim).

### WR-02: Streaming metadata methods have no cancellation test; `functools.partial` filter forwarding is untested

**File:** `tests/async/test_meta_stream.py`; `tests/async/test_meta_roundtrip.py`

Given CR-01, the absence of any cancellation test over the streaming trio is a material gap — the one path with a genuine concurrency hazard is unexercised. Separately, no test passes a non-default filter: `adbc_get_table_schema("t")` is called with no `catalog_filter`/`db_schema_filter`, and `adbc_get_objects` only sets `depth="tables"`. A partial that dropped or mis-forwarded a keyword filter would pass every current test.

**Fix:** Add (a) a real-driver loop test cancelling an in-flight `adbc_get_objects` pull (assert no crash, `checkedout()==0` — the CR-01 gate), and (b) at least one call with an explicit non-default filter so the kwarg forwarding is observed.

## Info

### IN-01: Async guide's "what you get today" list names only 3 of the 6 metadata methods

**File:** `docs/src/guides/async.md`

The capability blurb names `adbc_get_info` / `adbc_get_objects` / `adbc_get_table_schema`, omitting `adbc_get_table_types`, `adbc_get_statistics`, `adbc_get_statistic_names` (all shipped, all documented in the "Connection metadata" section below).

**Fix:** Enumerate all six or reword to "the six `adbc_get_*` connection-metadata methods (see [Connection metadata](#connection-metadata))".

### IN-02: Round-trip test leaks its setup cursor inside the connection scope

**File:** `tests/async/test_meta_roundtrip.py`

`cursor = conn.cursor()` is opened for `CREATE TABLE` and never closed; check-in reclaims it so `checkedout()==0` still holds, but it diverges from the `async with conn.cursor()` discipline the guides teach.

**Fix:** Wrap the setup cursor in `async with conn.cursor() as cursor:`.
