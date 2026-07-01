# Phase 30: Async Bulk Write - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver `await cursor.adbc_ingest(table_name, data, *, mode=..., catalog_name=None,
db_schema_name=None, temporary=False)` on `AsyncCursor` as a single
whole-operation offload that returns the affected row count as an `int`. `mode` is
a typed `Literal` forwarded verbatim to the driver; `data` is passed through with
zero conversion by poolhouse; a cancelled or timed-out ingest fires `adbc_cancel`
and invalidates the connection (a partial write poisons it) with asyncio/trio
parity.

Structurally this is the write-path twin of `fetch_arrow_table`: bracket with
`_offloading()`, dispatch through `cancellable_offload` with `adbc_cancel` +
`on_abort=self._owner.invalidate`, return the materialized result. No reader
lifetime lock (unlike Phase 29 — the operation completes and the connection checks
back in immediately). It reuses the Phase 29/25 cancel/offload machinery verbatim.
It exercises one new wrinkle in isolation: forwarding keyword-only arguments
through the positional-variadic offload chokepoint.

No new runtime deps, no new extras, **no sync-core change** — the sync half of
poolhouse is a pool factory only (`create_pool` → raw `QueuePool`), so a sync user
already calls the native `adbc_ingest` on the raw ADBC cursor. There is nothing to
wrap sync-side; the async layer wraps every cursor method precisely because the
raw call would block the event loop.

**Requirements:** INGEST-01, INGEST-02, INGEST-03, INGEST-04

</domain>

<decisions>
## Implementation Decisions

### Wrapper structure (INGEST-01)
- **D-30-01:** `AsyncCursor.adbc_ingest` is a new method on the existing
  `AsyncCursor` in `src/adbc_poolhouse/_async/_cursor.py` — a byte-for-byte clone
  of the `fetch_arrow_table` offload shape (`_cursor.py:327`): one
  `with self._owner._offloading():` span wrapping a single `cancellable_offload(...)`
  that returns the driver's `int` row count. **No** new file, **no** reader class,
  **no** `_reader_open` lifetime lock — the connection checks back in the moment the
  offload completes.
- **D-30-02:** Return type is `int` (rows inserted, or driver-reported `-1` when the
  driver cannot count). Poolhouse returns it unchanged.

### Keyword-argument forwarding (INGEST-01) — the phase's one real wrinkle
- **D-30-03:** The public API surfaces `mode`, `catalog_name`, `db_schema_name`,
  `temporary` as **keyword-only** (after `*`). The driver treats `mode` as
  positional-or-keyword and only the latter three as keyword-only; poolhouse
  tightens `mode` to keyword-only for a cleaner call site.
- **D-30-04:** `offload` / `cancellable_offload` forward arguments through a
  **positional variadic** (`Unpack[_Ts]`) and cannot forward keywords as written.
  Bind the arguments with **`functools.partial`** — wrap
  `self._cursor.adbc_ingest` into a zero-positional-arg partial closing over
  `table_name`, `data`, and the four keywords, then hand that partial to
  `cancellable_offload`. Do **not** widen the `offload`/`cancellable_offload`
  signature to accept `**kwargs`. (Researcher: confirm the partial-wrapped callable
  still cancels cleanly — `adbc_cancel` lives on the cursor object, unaffected by
  the partial — and does not trip the AST import-lint guard, PKG-03.)

### `mode` typing (INGEST-02)
- **D-30-05:** `mode: Literal["create", "append", "replace", "create_append"]`,
  default `"create"`, forwarded verbatim to the driver (no validation, no
  remapping). Docs MUST warn explicitly that `replace` **drops** the existing table.

### `data` typing (INGEST-03)
- **D-30-06:** Type `data` as the precise Arrow union
  `pyarrow.RecordBatch | pyarrow.Table | pyarrow.RecordBatchReader | CapsuleType`
  — **not** `object`. This union probed **0 real diagnostics** under strict
  basedpyright (STACK.md:147); pyarrow members degrade to `Any`, so it stays
  strict-clean while self-documenting the accepted inputs. Poolhouse performs
  **zero conversion** — the Arrow object is handed to the driver untouched.
- **D-30-07:** `CapsuleType` is imported from `typing_extensions` under
  `TYPE_CHECKING` (matching ADBC's own choice; `types.CapsuleType` is 3.13+ only and
  the floor is 3.11).

### `_SyncCursor` Protocol (PKG-01 parity)
- **D-30-08:** Extend the `_SyncCursor` structural Protocol (`_cursor.py:63`) with an
  `adbc_ingest(...) -> int` signature carrying the full argument union — exactly as
  `fetch_record_batch` was added in Phase 29. Keeps the async layer driver-agnostic
  and stub-testable; must stay basedpyright-strict-clean.

### Cancel / invalidate semantics (INGEST-04)
- **D-30-09:** Reuse `on_abort=self._owner.invalidate` (D-25-03) verbatim. A
  cancelled/timed-out ingest fires `adbc_cancel` once, invalidates the now-poisoned
  connection (shielded), and re-raises the cancellation, leaving
  `pool.checkedout() == 0` under asyncio and trio.
- **D-30-10:** `invalidate` recovers the **connection**; it does not and cannot roll
  back a **partially-applied write** in the database. That partial-table outcome is
  inherent to aborting mid-write and is **out of scope to fix** — document it, do not
  attempt compensation.

### Experimental keywords (INGEST-01)
- **D-30-11:** `catalog_name`, `db_schema_name`, `temporary` are marked EXPERIMENTAL
  in the ADBC docstring (STACK.md:44). Surface them as-is with no added stability
  guarantee; note the EXPERIMENTAL status in the docstring.

### No sync implementation
- **D-30-12:** No sync-side `adbc_ingest` wrapper is added or needed. The sync
  surface is `create_pool`/`close_pool`/`managed_pool` returning a raw
  `sqlalchemy.pool.QueuePool`; sync users call native `adbc_ingest` on the raw ADBC
  cursor directly. Confirmed structural, not an omission (PROJECT.md:11 "no
  sync-core changes").

### Claude's Discretion
- Exact test-harness mechanism for a deterministic in-flight cancel (a blocking
  fake `adbc_ingest` on the stub cursor vs. a genuinely slow/large DuckDB ingest) —
  planner/researcher choose, following the Phase 23 harness precedent.
- Docstring prose and Example-block wording (subject to the docs quality gate).

</decisions>

<specifics>
## Specific Ideas

- Mirror `fetch_arrow_table` so closely that a reviewer can diff the two methods and
  see only: the callable (`partial(adbc_ingest, ...)` vs `fetch_arrow_table`), the
  return annotation (`int` vs `pyarrow.Table`), and the docstring.
- Follow the Phase 29 TDD rhythm: RED tests (protocol signature + round-trip +
  cancel/parity) before the method lands.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — INGEST-01..04 definitions (note INGEST-02's explicit
  "`replace` **drops** the existing table" docs mandate; INGEST-04's
  `on_abort=invalidate` requirement)
- `.planning/ROADMAP.md` §"Phase 30: Async Bulk Write" — goal, four success
  criteria, dependency on Phase 29

### Verified research (answers the open typing/signature questions)
- `.planning/research/STACK.md` §"`adbc_ingest`" (lines 28–46) — the exact driver
  signature, the `data` Arrow union, the `-1` row-count case, EXPERIMENTAL keyword
  note, and the "natural fit for `cancellable_offload` + `on_abort=invalidate`"
  guidance
- `.planning/research/STACK.md` §"pyarrow-stub reality" (lines 149–165) — why the
  `data` union and `CapsuleType` are strict-clean without third-party stubs; the
  `TYPE_CHECKING` + `typing_extensions` import decision
- `.planning/research/SUMMARY.md` (lines 12–14) — "byte-for-byte copies of the
  `fetch_arrow_table` pattern"; build order places `adbc_ingest` after streaming

### Existing async layer (the patterns this phase copies)
- `src/adbc_poolhouse/_async/_cursor.py:327` — `fetch_arrow_table`, the exact
  offload shape to clone; `_SyncCursor` Protocol at `:63` to extend
- `src/adbc_poolhouse/_async/_cancel.py:41` — `cancellable_offload` signature; the
  positional-variadic (`Unpack[_Ts]`) that motivates the `functools.partial`
  decision, and the `adbc_cancel`/`on_abort` contract (reused verbatim)
- `src/adbc_poolhouse/_async/_offload.py:41` — the single `to_thread.run_sync`
  chokepoint the import-lint guard (PKG-03) audits
- `src/adbc_poolhouse/_async/_connection.py` — `_offloading`/`_in_use` guard and
  `invalidate` (dedicated teardown limiter) reused as-is

### Sync surface (confirms no sync work)
- `src/adbc_poolhouse/_pool_factory.py:162` — `create_pool` returns a raw
  `QueuePool`; there is no sync cursor wrapper, so `adbc_ingest` is native sync-side

### Test harness
- Phase 23 `BlockingStubCursor` harness (see archived `milestones/v1.4.0-phases/23-*`)
  — extend the stub cursor with an `adbc_ingest` that can block on demand for the
  deterministic in-flight cancel test
- `.planning/phases/29-arrow-streaming/29-01-PLAN.md` — the RED-first test scaffolding
  precedent to follow

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cancellable_offload` (`_cancel.py`): whole-op offload with `adbc_cancel` +
  `on_abort=invalidate` — used unchanged; the callable is a `functools.partial`
  binding the ingest arguments.
- `_offloading()` / `_in_use` (`_connection.py`): per-call C-access guard reused
  as-is (concurrent cursor use → `ConnectionBusyError`).
- `fetch_arrow_table` (`_cursor.py:327`): the exact template — copy its structure,
  swap the callable and return type.

### Established Patterns
- `_SyncCursor` structural Protocol → add `adbc_ingest`; keeps the layer
  driver-agnostic and stub-testable.
- No worker-exception re-wrapping (EDGE-17): the single offload chokepoint re-raises
  native errors (incl. driver `ProgrammingError` before `execute`, `AdbcError` on a
  bad ingest) with exact type/traceback — do not catch or wrap.
- pyarrow type annotations degrade to `Any` under the placeholder stub → real
  `pyarrow.*` names stay strict-clean and forward-compatible.

### Integration Points
- `AsyncCursor.adbc_ingest()` is the sole new entry point (extend `_cursor.py`).
- `_SyncCursor` Protocol gains the `adbc_ingest` signature (same file).
- No new files; no `_connection.py`/`_offload.py`/`_cancel.py` signature changes.

</code_context>

<deferred>
## Deferred Ideas

- `fetch_df` / `fetch_polars` DataFrame convenience — Phase 31 (independent read
  path; reuses this phase's whole-op offload shape, not its write semantics).
- P2 edge-hardening matrix (contextvars, trio-checkpoint, timeout precision,
  loop-shutdown, finalizers) extended across the ingest path — Phase 32.
- Any `[pandas]`/`[polars]`/`[dataframe]` extra — permanently ruled out (STACK.md:91);
  not this phase's concern anyway.

</deferred>

---

*Phase: 30-async-bulk-write*
*Context gathered: 2026-07-01*
