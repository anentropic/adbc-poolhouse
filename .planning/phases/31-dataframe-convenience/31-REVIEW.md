---
phase: 31-dataframe-convenience
reviewed: 2026-07-02T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - src/adbc_poolhouse/_async/_cursor.py
  - tests/_async_harness/stubs.py
  - tests/async/test_df_roundtrip.py
  - tests/async/test_df_lifetime.py
  - tests/async/test_df_missing_dep.py
  - tests/async/test_df_busy.py
  - tests/async/test_df_cancel.py
  - tests/async/test_df_signature.py
  - docs/src/guides/async.md
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 31: Code Review Report

**Reviewed:** 2026-07-02
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 31 adds `AsyncCursor.fetch_df` and `AsyncCursor.fetch_polars` as deliberate
clones of `fetch_arrow_table`. I reviewed the two new production methods against
their template line-by-line, verified all locked design constraints (DF-03 no
pre-check / no wrapping, `TYPE_CHECKING`-only pandas/polars imports, bare method
reference with no `functools.partial`, no reader-lifetime lock, the documented
`typing.cast` deviation), and traced the cancel / busy-guard / exception paths
through `cancellable_offload`, `offload`, and the connection guard.

**The production method is correct.** `fetch_df`/`fetch_polars` are exact
structural twins of `fetch_arrow_table`:

- Same `with self._owner._offloading():` busy-guard bracket → `ConnectionBusyError`
  parity (T-31-03).
- Same `cancellable_offload(self._adbc_cancel, self._cursor.<method>, limiter=...,
  on_abort=self._owner.invalidate)` shape → cancel/invalidate parity (T-31-01).
- Bare method reference (`self._cursor.fetch_df`, no partial, no args) — matches
  DF-03/D-31-03 and the `test_method_takes_only_self` contract.
- pandas/polars appear only under `TYPE_CHECKING` (lines 49-50) and as deferred
  string return annotations; no `find_spec`, no `try/except ImportError`, no
  wrapping. A missing dep propagates the native `ModuleNotFoundError` unchanged
  (verified against the offload chokepoint's documented re-raise contract).
- The `typing.cast("pandas.DataFrame", ...)` at the return site is the
  intended, documented deviation reconciling the Protocol's `-> object` member
  with the public annotation; it has no runtime effect.

The `_SyncCursor` Protocol additions (`fetch_df`/`fetch_polars` typed `-> object`)
and the `BlockingStubCursor` fakes are consistent and thread-safe (counters bumped
under `self._lock`, injected exception raised AFTER `_block` so it crosses the real
`to_thread` boundary). The test suite is thorough and correctly RED-scaffolded.

The only substantive finding is a documentation self-contradiction. The rest are
minor.

## Warnings

### WR-01: Async guide contradicts itself — new methods listed as "not available yet"

**File:** `docs/src/guides/async.md:23-31` (contradicts `:280-306`)
**Issue:** The "Experimental" warning box still enumerates the two methods this
phase ships as unavailable:

```
It is also incomplete. The following are not available yet on the async side:

- **DataFrame convenience** — `fetch_df` and `fetch_polars`
```

Yet the same file now contains a full "## Fetching a DataFrame" section (lines
280-306) documenting `fetch_df`/`fetch_polars` as working, with a runnable example.
A reader of the warning box is told the feature does not exist; a reader 250 lines
later is shown how to use it. This is a shipped-doc correctness defect: the phase
added the feature and its guide section but did not remove the stale "not available"
bullet. CLAUDE.md makes documentation a completion requirement for phases >= 7, and
an internally contradictory guide fails that gate.

**Fix:** Remove the DataFrame bullet from the incomplete list, and (since
`fetch_df`/`fetch_polars` are now shipped) add them to the "What you get today"
sentence at line 30-31. E.g.:

```markdown
    It is also incomplete. The following are not available yet on the async side:

    - **Async ADBC metadata** — `adbc_get_table_schema`, `adbc_get_objects`, `adbc_get_info`
    - **Async prepared statements** — `adbc_prepare`, `adbc_execute_schema`

    What you get today is checkout, `execute` / `executemany`, the `fetch*` methods,
    `fetch_arrow_table`, `fetch_df` / `fetch_polars`, Arrow streaming through
    `fetch_record_batch`, bulk write through `adbc_ingest`, and cooperative
    cancellation. The rest is on the roadmap.
```

## Info

### IN-01: `functools` import may now be needed only by `adbc_ingest`

**File:** `src/adbc_poolhouse/_async/_cursor.py:35`
**Issue:** `import functools` is used only by `adbc_ingest` (line 553). The two new
methods correctly do NOT use `functools.partial` (per D-31-03), so this import's
scope is unchanged by the phase — but worth confirming it is still referenced.
It is (line 553), so this is not a dead import; noted only to document that the
"no partial" constraint was honored and `functools` remains legitimately used.
No change required.

### IN-02: Docstring example in `fetch_df`/`fetch_polars` omits the `async with cursor` form

**File:** `src/adbc_poolhouse/_async/_cursor.py:404-410`, `456-462`
**Issue:** The `Example:` blocks call `conn.cursor()` and never close the cursor,
while the guide (async.md) and the `fetch_arrow_table` narrative both promote the
`async with conn.cursor() as cur:` context-manager form. This mirrors the existing
`fetch_arrow_table` docstring example (line 121, also bare `conn.cursor()`), so it
is consistent with the template rather than a regression — a style nit, not a bug.
The frame-lifetime guarantee (readable after checkin) is real, so the example is
not misleading. Optional: align with the guide's `async with cursor` idiom for
consistency.

---

_Reviewed: 2026-07-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
