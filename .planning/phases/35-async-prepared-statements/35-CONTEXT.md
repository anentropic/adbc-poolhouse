# Phase 35: Async Prepared Statements - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning
**Source:** /gsd-discuss-phase 35 --assumptions (assumptions validated; one decision locked with user)

<domain>
## Phase Boundary

Deliver two new awaitable methods on `AsyncCursor`
(`src/adbc_poolhouse/_async/_cursor.py`):

- `await cursor.adbc_prepare(operation)` → `pyarrow.Schema | None` — prepares a
  query without executing it, returning the schema of the **bind parameters** (or
  `None` when the driver cannot determine it).
- `await cursor.adbc_execute_schema(operation, parameters=None)` → `pyarrow.Schema`
  — returns the schema of the **result set** *without executing the query*.

Both are pure offload wrappers over the already-wrapped sync `dbapi.Cursor`
methods of the same name, routed through the existing `cancellable_offload`
chokepoint and the per-pool `CapacityLimiter`. Behavior mirrors the sync
statement lifecycle exactly: no invented async-specific error types, no
`find_spec` pre-checks, no bespoke wrapping. Native driver errors surface
unchanged through the single offload chokepoint (EDGE-17).

Structurally these are the cursor-level twins of the `execute` offload shape
(`_cursor.py:200`): one `with self._owner._offloading():` span wrapping a single
`cancellable_offload(...)`. This is the simplest phase in the milestone — both
methods return a plain `pyarrow.Schema` (or `None`); there is **no** streaming
reader, **no** `AsyncRecordBatchReader`, **no** reader-lifetime lock. It closes
the **last** async/sync parity gap named in the v1.5.0 docs caveat — after this
the "not available yet" block disappears entirely.

**Requirements:** PREP-01, PREP-02, PREP-03

</domain>

<decisions>
## Implementation Decisions

### Wrapper structure (PREP-01)
- **D-35-01:** Both methods are new methods on the existing `AsyncCursor` in
  `src/adbc_poolhouse/_async/_cursor.py` — clones of the `execute` offload shape
  (`_cursor.py:200`): one `with self._owner._offloading():` span wrapping a single
  `cancellable_offload(...)`. **No** new file, **no** reader class, **no**
  `_reader_open` lifetime lock — the connection checks back in the moment the
  offload completes.
- **D-35-02:** `adbc_prepare(operation: bytes | str)` returns `pyarrow.Schema | None`
  (the bind-parameter schema, or `None` when the driver cannot determine it —
  the sync method returns `Optional[pyarrow.Schema]`). Poolhouse returns it
  unchanged. Forward `operation` **positionally** through the `cancellable_offload`
  variadic — **no** `functools.partial` needed (unlike Phase 30; `operation` is a
  plain positional arg, not keyword-only).
- **D-35-03:** `adbc_execute_schema(operation: str, parameters: object = None)`
  returns `pyarrow.Schema` — the schema of the result set **without executing** the
  query. Forward `operation` and `parameters` **positionally** through the variadic,
  exactly as `execute` forwards its `(operation, parameters)`. No `functools.partial`.

### Cancel / abort semantics (PREP-01/02) — the phase's one real decision
- **D-35-04:** Both methods use `cancellable_offload(self._adbc_cancel, ...)` with
  `on_abort` **omitted** (defaults to `None`). This makes them **cancellable but
  non-poisoning**. LOCKED WITH USER (assumptions discussion 2026-07-04).

  Rationale — two-axis decision, distinct from both prior patterns:
  - **Cancellable (unlike Phase 34 metadata).** The sync `adbc_prepare` /
    `adbc_execute_schema` both route through `_blocking_call(..., self._stmt.cancel)`
    — the driver itself makes them abortable. So they get the `cancellable_offload`
    + `self._adbc_cancel` treatment like `execute`/`fetchall`, **not** the plain
    non-cancellable `offload` that Phase 34's `adbc_get_info` used (metadata reads
    were treated "like `commit`" — no cancel hook).
  - **Non-poisoning (unlike `execute`/`fetchall`).** Neither method executes the
    query or writes data, so an aborted prepare/execute_schema cannot leave a
    half-applied state that poisons the connection. Therefore `on_abort` is omitted
    (no `self._owner.invalidate`) — a cancelled call fires `adbc_cancel` once and
    the clean connection returns to the pool. This mirrors the Phase 34 reader
    rationale ("NOT invalidated — it was never poisoned"), applied to a cancellable
    call.

  Net: `cancellable_offload` fires `adbc_cancel` to abort the in-flight C call on
  cancel/timeout, then re-raises the cancellation — with `pool.checkedout() == 0`
  and no `invalidate`.

### `_SyncCursor` Protocol (PREP-01 parity)
- **D-35-05:** Extend the `_SyncCursor` structural Protocol (`_cursor.py:58`) with
  two signatures — `adbc_prepare(self, operation: bytes | str, /) -> object` and
  `adbc_execute_schema(self, operation: str, parameters: object = ..., /) -> object`
  — exactly as `fetch_record_batch`/`adbc_ingest` were added in Phases 29/30. Keeps
  the async layer driver-agnostic and stub-testable; must stay
  basedpyright-strict-clean.

### Behavior mirroring (PREP-02)
- **D-35-06:** No invented async-specific error types, no `find_spec` pre-checks, no
  bespoke wrapping. A backend that does not implement a method surfaces the driver's
  native error unchanged (single offload chokepoint re-raises with exact
  type/traceback — EDGE-17). `adbc_execute_schema` must **not** execute the query
  (test must assert no side effects / rowcount unaffected).

### No sync implementation
- **D-35-07:** No sync-side wrapper is added or needed. The sync surface is
  `create_pool`/`close_pool`/`managed_pool` returning a raw
  `sqlalchemy.pool.QueuePool`; sync users call native `adbc_prepare` /
  `adbc_execute_schema` on the raw ADBC cursor directly. Structural, not an omission
  (PROJECT.md "no sync-core changes").

### Docs (PREP-03)
- **D-35-08:** Remove the async-guide caveat. Prepared statements is the **last
  remaining bullet** in the `docs/src/guides/async.md` "not available yet" block
  (lines 23–25 after Phase 34), so the whole block goes and the "What you get today"
  paragraph is updated to include the prepared-statement methods. **Also** fix
  `docs/src/index.md:71`, which still reads "async ADBC metadata **and** prepared
  statements have not shipped yet" — metadata shipped in Phase 34, so that whole
  clause is a stale leftover to drop, not just the prepared-statements half. Add API
  reference render for both new symbols; `mkdocs build --strict` passes; humanizer
  pass on new/rewritten prose. Docs quality gate per CLAUDE.md (phases ≥ 7) applies.

### Claude's Discretion
- Exact test-harness mechanism for a deterministic in-flight cancel (a blocking
  fake `adbc_prepare`/`adbc_execute_schema` on the stub cursor vs. a genuinely slow
  DuckDB call) — planner/researcher choose, following the Phase 23/29 harness
  precedent.
- Whether the async guide gets a short worked "prepare then execute" snippet vs.
  API-reference stubs only (lean: a brief snippet, since prepare's value — reuse
  across `execute`/`executemany` — is not obvious from the signature).
- Docstring prose and Example-block wording (subject to the docs quality gate).

</decisions>

<specifics>
## Specific Ideas

- Mirror `execute` (`_cursor.py:200`) so closely that a reviewer can diff the two and
  see only: the callable (`adbc_prepare` / `adbc_execute_schema` vs `execute`), the
  return annotation (`pyarrow.Schema | None` / `pyarrow.Schema` vs `None`), the
  **absence** of `on_abort=self._owner.invalidate` (D-35-04), and the docstring.
- Follow the Phase 29/30 TDD rhythm: RED tests (Protocol signature + value
  round-trip + no-execute assertion + cancel/parity + unsupported passthrough)
  before the methods land.
- Return-type note: `adbc_prepare` tolerates **both** `Schema` and `None` — the
  round-trip test must not assume a non-null schema.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — PREP-01..03 definitions
- `.planning/ROADMAP.md` §"Phase 35: Async Prepared Statements" — goal, three
  success criteria, dependency on Phase 34

### Existing async layer (the patterns this phase copies)
- `src/adbc_poolhouse/_async/_cursor.py:200` — `execute`, the exact offload shape to
  clone (positional forwarding of `operation`/`parameters`); `_SyncCursor` Protocol
  at `:58` to extend; `_adbc_cancel` resolver at `:151`
- `src/adbc_poolhouse/_async/_cancel.py:41` — `cancellable_offload` signature;
  `on_abort: Callable[[], Awaitable[None]] | None = None` (optional, defaults None →
  the non-poisoning path for D-35-04); the `adbc_cancel`/`on_abort` contract
- `src/adbc_poolhouse/_async/_offload.py` — the single `to_thread.run_sync`
  chokepoint the import-lint guard (PKG-03) audits
- `src/adbc_poolhouse/_async/_connection.py` — `_offloading`/`_in_use` guard reused
  as-is; note `adbc_get_info` (`:347`) as the **contrast** case (plain
  non-cancellable `offload`, deliberately NOT what this phase does)

### Prior-phase precedent (the direct template)
- `.planning/phases/34-async-metadata/34-02-PLAN.md` — the Protocol-extension +
  offload-wrapper + docstring implementation pattern (one level up, on the
  connection); and `34-03-PLAN.md` for the caveat-shrink docs pattern
- `.planning/phases/30-async-bulk-write/30-CONTEXT.md` — the offload-wrapper CONTEXT
  precedent; note Phase 30 needed `functools.partial` for keyword-only args, which
  this phase does **not** (D-35-02/03)

### Sync surface (confirms no sync work)
- `src/adbc_poolhouse/_pool_factory.py` — `create_pool` returns a raw `QueuePool`;
  there is no sync cursor wrapper, so `adbc_prepare`/`adbc_execute_schema` are native
  sync-side

### Docs to edit (PREP-03)
- `docs/src/guides/async.md:18–32` — the "Experimental" warning block; remove the
  last caveat bullet + the enclosing "not available yet" block, update "What you get
  today"
- `docs/src/index.md:71` — drop the stale "metadata and prepared statements have not
  shipped yet" clause (metadata shipped Phase 34)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cancellable_offload` (`_cancel.py:41`): whole-op offload with `adbc_cancel`; call
  it **without** `on_abort` for the non-poisoning path (D-35-04).
- `_adbc_cancel` (`_cursor.py:151`): the driver cancel resolver, reused unchanged.
- `_offloading()` / `_in_use` (`_connection.py`): per-call C-access guard reused
  as-is (concurrent cursor use → `ConnectionBusyError`).
- `execute` (`_cursor.py:200`): the exact template — copy its structure, swap the
  callable and return type, drop `on_abort`.

### Established Patterns
- `_SyncCursor` structural Protocol → add both signatures; keeps the layer
  driver-agnostic and stub-testable.
- No worker-exception re-wrapping (EDGE-17): the single offload chokepoint re-raises
  native errors with exact type/traceback — do not catch or wrap.
- pyarrow type annotations degrade to `Any` under the placeholder stub → real
  `pyarrow.Schema` names stay strict-clean and forward-compatible.

### Integration Points
- `AsyncCursor.adbc_prepare()` / `AsyncCursor.adbc_execute_schema()` are the sole new
  entry points (extend `_cursor.py`).
- `_SyncCursor` Protocol gains both signatures (same file).
- No new files; no `_connection.py`/`_offload.py`/`_cancel.py` signature changes.

</code_context>

<deferred>
## Deferred Ideas

- Partitioned result sets (`adbc_execute_partitions` / `adbc_read_partition`) —
  permanently deferred this milestone: a niche Flight-SQL-oriented feature most
  supported backends return unsupported for (ROADMAP milestone goal).

</deferred>

---

*Phase: 35-async-prepared-statements*
*Context gathered: 2026-07-04 via /gsd-discuss-phase --assumptions*
