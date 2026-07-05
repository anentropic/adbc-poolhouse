# Phase 31: DataFrame Convenience - Context

**Gathered:** 2026-07-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver `await cursor.fetch_df()` returning a `pandas.DataFrame` and
`await cursor.fetch_polars()` returning a `polars.DataFrame` on `AsyncCursor`, each
as a single whole-operation offload. Both are wafer-thin twins of
`fetch_arrow_table` (`_cursor.py:341`): bracket with `_offloading()`, dispatch the
**native** driver method through `cancellable_offload` with `adbc_cancel` +
`on_abort=self._owner.invalidate`, return the materialized frame. No arguments, no
`functools.partial` (unlike `adbc_ingest`), no reader lifetime lock (unlike
`fetch_record_batch`) — the connection checks back in the moment the offload
completes.

pandas and polars stay **user-supplied runtime deps**. poolhouse never imports them
in production code and never touches the DataFrame instantiation itself — the driver
does. A missing dep raises the native `ModuleNotFoundError` inside the worker thread,
which propagates unchanged through the single offload chokepoint (DF-03), exactly as
poolhouse already surfaces a missing ADBC driver. pandas/polars are added to the
**dev dependency group only** so the test suite can assert real return types;
`[project.dependencies]`, `[project.optional-dependencies]`, and the `__init__.py`
lazy-import surface are untouched (PKG-02).

No sync-core change — the sync half of poolhouse is a pool factory (`create_pool` →
raw `QueuePool`), so a sync user already calls native `fetch_df`/`fetch_polars` on
the raw ADBC cursor. There is nothing to wrap sync-side; the async layer wraps every
cursor method precisely because the raw call would block the event loop.

**Requirements:** DF-01, DF-02, DF-03, DF-04, PKG-02

</domain>

<decisions>
## Implementation Decisions

### Delegation strategy — the phase's one genuine design question (DF-01/DF-02/DF-04)
- **D-31-01:** **Offload the driver's native `fetch_df`/`fetch_polars` (Approach A)** —
  NOT reuse our async `fetch_arrow_table` and instantiate the frame ourselves
  (Approach B). Both native methods already do exactly the right thing under a
  `_blocking_call`:
  - `fetch_df` → `reader.read_pandas()` (reads Arrow batches straight into pandas
    blocks; imports pandas lazily)
  - `fetch_polars` → `polars.from_arrow(self.fetch_arrow())` (imports polars at call
    time)
- **D-31-02:** Approach B is **rejected** for three concrete reasons, decided during
  discussion:
  1. **It stalls the event loop.** `table = await self.fetch_arrow_table()` returns to
     the loop, then `.to_pandas()` / `polars.from_arrow(table)` runs *inline* on the
     loop thread — and Arrow→pandas conversion is CPU-heavy. Fixing it means offloading
     the conversion too, i.e. rebuilding the native method.
  2. **It reinvents the driver worse.** The pandas path via `read_all().to_pandas()`
     materializes a full intermediate `pyarrow.Table` and *then* converts — an extra
     full copy vs. the native `reader.read_pandas()`. The polars path is byte-identical
     to what the driver already does, so reimplementing just relocates one line.
  3. **It forfeits DF-03-for-free.** With the native call the pandas/polars `import`
     happens *inside the worker*; the `ModuleNotFoundError` propagates through the
     chokepoint with zero poolhouse code. Owning the import site (Approach B) would make
     us responsible for where/how that error surfaces.
  - Portability (Approach B builds on `fetch_arrow_table`, which every driver has) is
    **not** a real differentiator: the async layer already depends on
    adbc_driver_manager extensions (`fetch_arrow_table`, `fetch_record_batch`,
    `adbc_ingest`, `adbc_cancel` — none are DBAPI-standard). `fetch_df`/`fetch_polars`
    are the same class of extension.

### Wrapper structure (DF-01/DF-02)
- **D-31-03:** Two new methods on the existing `AsyncCursor`
  (`src/adbc_poolhouse/_async/_cursor.py`) — each a byte-for-byte clone of the
  `fetch_arrow_table` offload shape (`_cursor.py:341`): one
  `with self._owner._offloading():` span wrapping a single `cancellable_offload(...)`.
  The callable is the **bare method reference** `self._cursor.fetch_df` /
  `self._cursor.fetch_polars` (both take no args — **no** `functools.partial`, unlike
  `adbc_ingest`). **No** new file, **no** reader class, **no** `_reader_open` lifetime
  lock — the connection checks back in the moment the offload completes.

### Self-owning frame (DF-04)
- **D-31-04:** DF-04 holds identically to `fetch_arrow_table`/EDGE-21: `read_pandas`
  and `polars.from_arrow(read_all())` materialize into frame-owned / refcounted-heap
  buffers not bound to the connection's C stream. The frame stays valid after checkin.
  No extra machinery needed — it is inherited from Approach A.

### Missing-dependency propagation (DF-03)
- **D-31-05:** poolhouse adds **no** `find_spec` pre-check and **no** wrapping. The
  native `ModuleNotFoundError` raised in the worker re-raises through the single
  offload chokepoint with exact type/traceback (same guarantee as `AdbcError`,
  EDGE-17). This is the *documented, intended* behaviour — mirror the sync method
  exactly. Verified live in STACK.md with pandas/polars uninstalled.

### `_SyncCursor` Protocol (parity with prior phases)
- **D-31-06:** Extend the `_SyncCursor` structural Protocol (`_cursor.py:55`) with
  `def fetch_df(self) -> object: ...` and `def fetch_polars(self) -> object: ...` —
  return type `object` (like the existing `fetch*` members), keeping the Protocol
  driver-agnostic and free of any pandas/polars stub coupling. Must stay
  basedpyright-strict-clean.

### Public return-type annotations (DX)
- **D-31-07:** On the **public** `AsyncCursor.fetch_df`/`fetch_polars` methods,
  annotate `-> "pandas.DataFrame"` / `-> "polars.DataFrame"` (deferred string
  annotations under the existing `if TYPE_CHECKING:` block, `_cursor.py:43`, adding
  `import pandas` / `import polars`). Never imported at runtime — the annotation string
  is never evaluated by a consumer lacking the libs; the repo's own type-check resolves
  them via the dev group. Gives consumers accurate IDE return types with zero runtime
  cost and no change to the `__init__.py` lazy-import surface (PKG-02).

### Packaging (PKG-02)
- **D-31-08:** Add `pandas` and `polars` to the **dev dependency group only**
  (`[dependency-groups].dev` in `pyproject.toml`). Do **NOT** add a `[pandas]`,
  `[polars]`, or `[dataframe]` extra (maintainer ruling, STACK.md:91), and do **NOT**
  touch `[project.dependencies]` or `[project.optional-dependencies]`. `import
  adbc_poolhouse` with pandas/polars absent must remain unaffected.

### Cancel / invalidate semantics
- **D-31-09:** Reuse `on_abort=self._owner.invalidate` (D-25-03) verbatim, inherited
  from the `fetch_arrow_table` shape. The driver's own nested `_blocking_call(...,
  stmt.cancel)` is harmless/redundant beneath our `cancellable_offload` +
  `adbc_cancel` wrapper — exactly as it already is for `fetch_arrow_table` (also a
  `_blocking_call` under the hood).

### No sync implementation
- **D-31-10:** No sync-side `fetch_df`/`fetch_polars` wrapper is added or needed. Sync
  users call the native methods on the raw ADBC cursor directly. Structural, not an
  omission (PROJECT.md "no sync-core changes").

### Claude's Discretion
- Test harness for the missing-dep propagation assertion — must run in an env where
  pandas/polars are *absent* (a `no-df` marker/subprocess, or a monkeypatched-import
  stub cursor that raises `ModuleNotFoundError` in the worker). Positive round-trip
  tests use `pytest.importorskip("pandas")` / `importorskip("polars")`. Planner/
  researcher choose the exact mechanism, following the Phase 23 `BlockingStubCursor`
  precedent.
- Docstring prose and Example-block wording (subject to the docs quality gate). Guide
  note: "`fetch_df`/`fetch_polars` require you to install pandas/polars yourself."

</decisions>

<specifics>
## Specific Ideas

- Mirror `fetch_arrow_table` so closely a reviewer can diff and see only: the callable
  (`self._cursor.fetch_df` / `fetch_polars` vs `fetch_arrow_table`), the return
  annotation (`pandas.DataFrame` / `polars.DataFrame` vs `pyarrow.Table`), and the
  docstring. Simplest of the v1.5.0 phases — the risk is over-engineering (adding
  availability checks or error wrapping that DF-03 forbids). Keep it dumb.
- Follow the Phase 29/30 TDD rhythm: RED tests (protocol signatures + round-trip
  return-type + missing-dep propagation + busy-guard parity) before the methods land.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — DF-01..04 (note DF-03's explicit "no `find_spec`
  pre-check / no wrapping" and DF-04's EDGE-21 self-owning guarantee) and PKG-02
  (dev-group-only, `importorskip`-guarded, `__init__` surface unchanged)
- `.planning/ROADMAP.md` §"Phase 31: DataFrame Convenience" — goal, four success
  criteria, dependency on Phase 30

### Verified research (answers the delegation + typing + packaging questions)
- `.planning/research/STACK.md` §"`fetch_df`" / "`fetch_polars`" (lines 48–63) — the
  native driver internals (`read_pandas`, `polars.from_arrow(fetch_arrow())`) that
  justify Approach A
- `.planning/research/STACK.md` §"How ADBC Signals Missing pandas / polars" (lines
  66–77) — live-verified `ModuleNotFoundError` propagation backing DF-03 ("do not
  catch, do not wrap")
- `.planning/research/STACK.md` §"`fetch_df`/`fetch_polars` return-type annotation
  choice" (lines 166–170) — `-> object` on the Protocol, `TYPE_CHECKING` string
  annotation on the public methods (D-31-06/07)
- `.planning/research/STACK.md` (lines 91, 97–105) — dev-group-only decision, no
  extras, `importorskip` guards (D-31-08)

### Existing async layer (the patterns this phase copies)
- `src/adbc_poolhouse/_async/_cursor.py:341` — `fetch_arrow_table`, the exact
  no-arg offload shape to clone; `_SyncCursor` Protocol at `:55` to extend; the
  `TYPE_CHECKING` import block at `:43`
- `src/adbc_poolhouse/_async/_cancel.py` — `cancellable_offload` signature and the
  `adbc_cancel`/`on_abort=invalidate` contract, reused verbatim
- `src/adbc_poolhouse/_async/_offload.py` — the single `to_thread.run_sync`
  chokepoint that re-raises worker exceptions unchanged (backs DF-03) and that the
  import-lint guard (PKG-03) audits

### Prior-phase precedent
- `.planning/phases/30-async-bulk-write/30-CONTEXT.md` — the sibling read/write-path
  decision set; this phase reuses its whole-op offload shape (not its keyword-forward
  or partial-binding wrinkles)
- `.planning/phases/29-arrow-streaming/29-01-PLAN.md` — the RED-first test scaffolding
  precedent to follow
- Phase 23 `BlockingStubCursor` harness (archived `milestones/v1.4.0-phases/23-*`) —
  extend the stub with `fetch_df`/`fetch_polars` for the deterministic tests

### Sync surface (confirms no sync work)
- `src/adbc_poolhouse/_pool_factory.py` — `create_pool` returns a raw `QueuePool`;
  no sync cursor wrapper, so `fetch_df`/`fetch_polars` are native sync-side

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `cancellable_offload` (`_cancel.py`): whole-op offload with `adbc_cancel` +
  `on_abort=invalidate` — used unchanged; the callable is the bare
  `self._cursor.fetch_df` / `self._cursor.fetch_polars` method reference (no
  `functools.partial`, no args).
- `_offloading()` / `_in_use` (`_connection.py`): per-call C-access guard reused
  as-is (concurrent cursor use → `ConnectionBusyError`).
- `fetch_arrow_table` (`_cursor.py:341`): the exact template — copy its structure,
  swap the callable and return annotation. Two clones, one per DataFrame flavour.

### Established Patterns
- `_SyncCursor` structural Protocol → add `fetch_df`/`fetch_polars` at `-> object`;
  keeps the layer driver-agnostic and stub-testable.
- No worker-exception re-wrapping (EDGE-17): the single offload chokepoint re-raises
  native errors (incl. `ModuleNotFoundError` for a missing pandas/polars, and driver
  `ProgrammingError` before `execute`) with exact type/traceback — do not catch.
- pandas/polars typed only as deferred `TYPE_CHECKING` string annotations on the
  public methods → accurate consumer DX, zero runtime import.

### Integration Points
- `AsyncCursor.fetch_df()` and `AsyncCursor.fetch_polars()` are the sole new entry
  points (extend `_cursor.py`).
- `_SyncCursor` Protocol gains two `-> object` signatures (same file).
- `pyproject.toml` `[dependency-groups].dev` gains `pandas` + `polars`.
- No new files; no `_connection.py`/`_offload.py`/`_cancel.py` signature changes.

</code_context>

<deferred>
## Deferred Ideas

- P2 edge-hardening matrix (contextvars, trio-checkpoint, timeout precision,
  loop-shutdown, `__del__` finalizers) extended across the `fetch_df`/`fetch_polars`
  paths — Phase 32.
- Any `[pandas]`/`[polars]`/`[dataframe]` extra — permanently ruled out (STACK.md:91).

</deferred>

---

*Phase: 31-dataframe-convenience*
*Context gathered: 2026-07-02*
