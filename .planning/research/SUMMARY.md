# Project Research Summary

**Project:** adbc-poolhouse v1.5.0 — Async Cursor Completion
**Domain:** Async Arrow streaming, bulk ingest, and DataFrame convenience over a thread-offload anyio pool wrapper
**Researched:** 2026-07-01
**Confidence:** HIGH — all four researchers grounded findings in installed-package introspection, live probes against the `.venv`, and direct source reads of `adbc_driver_manager 1.11.0` and the v1.4.0 async layer.

## Executive Summary

v1.5.0 completes the async cursor surface by wrapping four methods that already exist on the sync ADBC dbapi cursor: `fetch_record_batch`, `adbc_ingest`, `fetch_df`, and `fetch_polars`. All four researchers converge on the same headline conclusion: **zero new runtime dependencies, zero new extras**. pyarrow is already a core dep; anyio is already behind `[async]`; pandas and polars stay user-supplied at runtime (ADBC raises a clear `ModuleNotFoundError` if absent, exactly how the library treats missing drivers). The only packaging change is adding pandas and polars to the dev dependency group so the test suite can assert real return types.

Three of the four methods (`adbc_ingest`, `fetch_df`, `fetch_polars`) are genuinely trivial offload wrappers — byte-for-byte copies of the `fetch_arrow_table` pattern already shipped in v1.4.0: bracket with `_offloading()`, dispatch through `cancellable_offload` with `adbc_cancel` + `on_abort=self._owner.invalidate`, return the materialized result. The fourth method, `fetch_record_batch`, is the milestone's headline and its single genuine design risk: it returns a **live `pyarrow.RecordBatchReader` bound to the open ADBC statement**, not a self-owning buffer. Reading that reader after the connection checks in (the reset event closes cursors) is a use-after-free — confirmed by live DuckDB probe to raise `ArrowInvalid: stream already closed`, and liable to segfault on networked backends. The recommended design, on which all four researchers independently converge, is an `AsyncRecordBatchReader` wrapper whose `__anext__` issues a per-batch `cancellable_offload` and whose lifetime is hard-bound to the checked-out connection; read-after-checkin raises a clean, typed `PoolhouseError` subclass (proposed name `ReaderClosedError`), never a use-after-free.

Alongside the four methods, the milestone lands the deferred P2 async edge-case suite: EDGE-08, 13/14, 20, 22/23, 24, and 31/32. These are test-only additions that pin existing behaviour of the v1.4.0 layer (plus the new methods' cancel/cleanup paths) under both asyncio and trio. EDGE-16 is permanently dropped (D-24-03: connection aliasing rejected via `ConnectionBusyError`). The recommended build order is dependency-ordered: streaming first (highest risk, gates the reader-lifetime design that informs everything else) then `adbc_ingest` then `fetch_df`/`fetch_polars` then consolidated P2 edge hardening + `__del__` finalizers then docs.

## Key Findings

### Recommended Stack

v1.5.0 adds nothing to the runtime or extras. The installed stack (`adbc-driver-manager 1.11.0`, `pyarrow 24.0.0`, `anyio 4.14.1`) already provides everything needed. The four target methods are present on `adbc_driver_manager.dbapi.Cursor` and their exact signatures were verified by introspection. pyarrow 24.0.0 ships a `py.typed` marker but its `__init__.pyi` is an official placeholder (all members resolve to `Any` under basedpyright strict), so `-> pyarrow.RecordBatchReader` and the `adbc_ingest` data-union annotations are already strict-clean without third-party stubs. `CapsuleType` should be imported from `typing_extensions` under `TYPE_CHECKING` (matching ADBC's own choice; `types.CapsuleType` is 3.13+ only; the floor is 3.11). For the `_SyncCursor` Protocol, return types for `fetch_df`/`fetch_polars` should be `-> object`; on the public `AsyncCursor` methods, use `-> "pandas.DataFrame"` / `-> "polars.DataFrame"` under `TYPE_CHECKING` for good IDE DX without a runtime import.

**Core technologies (v1.5.0 delta — all unchanged from v1.4.0):**
- `adbc-driver-manager >= 1.8.0` (installed 1.11.0): provides all four target methods natively; no version bump needed
- `pyarrow >= 23.0.1` (installed 24.0.0, core dep): `RecordBatchReader` return type; Arrow inputs for `adbc_ingest`; underpins `read_pandas` and `from_arrow` — already present
- `anyio >= 4.13` (`[async]` extra, installed 4.14.1): unchanged offload/limiter/cancel plumbing; all new methods reuse `offload`/`cancellable_offload` verbatim

**Dev group additions (test-only, never shipped):**
- `pandas >= 2.0`: so the suite can assert `fetch_df` returns a real `pandas.DataFrame`; use `pytest.importorskip` guards so contributors without it see a green-skipped suite
- `polars >= 1.0`: same, for `fetch_polars`

### Expected Features

**Must have (table stakes) — v1.5.0:**
- `await cursor.fetch_record_batch()` returning an `AsyncRecordBatchReader` with `async for batch in reader:` — the milestone's headline; true lazy Arrow streaming, each `read_next_batch()` offloaded per-batch through the pool limiter with cancel wiring
- `await cursor.adbc_ingest(table_name, data, mode='create', *, catalog_name, db_schema_name, temporary)` — single whole-operation offload; `on_abort=invalidate`; returns `int` row count; `mode` typed as `Literal['append','create','replace','create_append']` forwarded verbatim
- `await cursor.fetch_df()` — single offload; self-owning `pandas.DataFrame` safe after checkin; pandas user-supplied
- `await cursor.fetch_polars()` — single offload; self-owning `polars.DataFrame` safe after checkin; polars user-supplied
- Materialized-result safety after checkin (`fetch_df`/`fetch_polars`) — same EDGE-21 guarantee as `fetch_arrow_table`
- P2 edge-case suite: EDGE-08, 13, 14, 20, 22, 23, 24, 31, 32 — deterministic, both asyncio and trio backends, reusing the shipped `BlockingStubCursor` harness
- Docs: guide + API-reference entries for all four methods including pandas/polars user-supplied note and streaming reader-lifetime caveat (docs-author skill, phase >= 7 gate per CLAUDE.md)

**Should have (differentiators):**
- True lazy, per-batch Arrow streaming — no surveyed async DB library offers Arrow streaming; backend-neutral (asyncio and trio); memory-bounded (one batch resident at a time)
- `AsyncRecordBatchReader` as a distinct async-iterable type — mirrors psycopg3/SQLAlchemy exposing a named streaming type, not a raw server cursor
- Explicit typed error (`ReaderClosedError` or similar) on read-after-checkin — fails loudly rather than silently truncating or segfaulting

**Defer (v2+):**
- Async ADBC metadata methods (`adbc_get_table_schema`, `adbc_get_objects`, `adbc_get_info`)
- Async prepared statements (`adbc_prepare`, `adbc_execute_schema`)
- anyio-native checkout limiter (only if offloaded checkout is a measured bottleneck)
- `[pandas]` / `[polars]` / `[dataframe]` poolhouse extras — ruled out; pandas/polars are permanently user-supplied

**Anti-features (confirmed out of scope):**
- Bundling pandas/polars as poolhouse extras — breaks the user-supplied runtime dep charter
- Eagerly draining the reader inside `fetch_record_batch()` — defeats streaming; is just `fetch_arrow_table` under another name
- `mode='upsert'` on `adbc_ingest` — ADBC exposes exactly four modes; invent nothing
- Runtime type-checking of `data` in `adbc_ingest` — pure pass-through; ADBC's binding raises clearly on bad input

### Architecture Approach

All four new methods are pure offload wrappers over sync ADBC cursor methods, routed exclusively through the existing `offload`/`cancellable_offload` chokepoint in `_offload.py`/`_cancel.py`. The only genuinely new architectural element is `AsyncRecordBatchReader` (`_async/_reader.py`): an async iterator whose `__anext__` issues one `cancellable_offload(self._cursor._adbc_cancel, reader.read_next_batch, ..., on_abort=self._owner.invalidate)` per batch, and whose `_detached` flag is set by `AsyncCursor.close()` so any subsequent pull raises a typed error rather than touching freed C state. The `_SyncCursor` Protocol gains four new method stubs. `AsyncCursor.__init__`/`close` gain tracking of any outstanding `AsyncRecordBatchReader` (so close drains/closes the reader before the connection checks in). `__del__` finalizers are added to `AsyncCursor`, `AsyncConnection`, and `AsyncRecordBatchReader` to emit `ResourceWarning` if unclosed, but never to `await` or schedule. Nothing else changes.

**Major components (new and modified):**
1. `AsyncRecordBatchReader` (new, `_async/_reader.py`) — async iterator; per-batch `cancellable_offload`; `_detached` guard; reader lifetime bound to checked-out connection; drain-on-cursor-close; `ResourceWarning` in `__del__`
2. `AsyncCursor` additions — `fetch_record_batch()`, `adbc_ingest()`, `fetch_df()`, `fetch_polars()` methods; reader-tracking in `close()`; `__del__` finalizer
3. `_SyncCursor` Protocol extension — four new method stubs typed under `TYPE_CHECKING`
4. P2 edge-case test suite — extends existing `BlockingStubCursor` harness; no production changes beyond what the four methods introduce

**Untouched:** `_offload.offload`, `_cancel.cancellable_offload`, `AsyncPool`, `AsyncConnection` core, the sync core, the entire cancellation machinery, `scan_async_package` guard, `__init__.py` lazy-import table.

**Offload granularity (all researchers agree):**

| Method | Offload unit | Cancellable per unit |
|--------|-------------|----------------------|
| `fetch_record_batch()` acquisition | 1 trivial offload | via plain `offload` |
| `AsyncRecordBatchReader.__anext__` | 1 `cancellable_offload` per batch | yes — `read_next_batch` is `_blocking_call(..., stmt.cancel)` |
| `adbc_ingest(...)` | 1 whole-operation `cancellable_offload` | yes — maps onto `execute` cancel path |
| `fetch_df()` / `fetch_polars()` | 1 whole-operation `cancellable_offload` each | yes — `_blocking_call(reader.read_pandas/from_arrow, ..., stmt.cancel)` |

### Critical Pitfalls

1. **`fetch_record_batch` returns a live reader — use-after-checkin is a confirmed segfault/ArrowInvalid.** Prevention: never hand back the raw `pyarrow.RecordBatchReader`; wrap in `AsyncRecordBatchReader` with `_detached` guard; set `_detached` on cursor close so any later `__anext__` raises a typed `PoolhouseError` (proposed `ReaderClosedError`) before touching freed C state. Front-load in Phase 1.

2. **`adbc_ingest` mode default is `create` and `replace` drops the table.** Prevention: type `mode` as `Literal['append','create','replace','create_append']`; default to `'create'` (matching ADBC exactly); document the mode table verbatim with a prominent note that `replace` drops-then-recreates. A cancelled ingest must use `on_abort=invalidate`. Document that cancellation does NOT guarantee rollback of already-written rows.

3. **`fetch_df`/`fetch_polars` missing-dep handling — open design decision (present both options, do not decide unilaterally).** STACK researcher: propagate ADBC's raw `ModuleNotFoundError` unchanged (consistent with driver treatment). PITFALLS researcher: `find_spec` pre-check on the loop thread raising a poolhouse-attributable `ImportError` naming the package (friendlier, consistent with PKG-03). Resolve in requirements before Phase 3.

4. **Arrow allocator leak from a partially-consumed streaming reader.** Prevention: `AsyncRecordBatchReader.__aexit__` must close the underlying reader (offloaded, shielded) whether or not iteration completed. The pool reset is the safety net, not the primary path. Add `ResourceWarning` in `__del__`. Verify with a streaming memory-stability loop.

5. **pandas/polars must never enter the runtime import graph.** Prevention: import both only under `TYPE_CHECKING`; extend PKG-04 to include no-pandas/no-polars import test. Never add a `[pandas]`, `[polars]`, or `[dataframe]` extra.

## Implications for Roadmap

All four researchers independently converge on the same five-phase build order, driven by risk (highest first) and dependency:

### Phase 1: Arrow Streaming — `fetch_record_batch` + `AsyncRecordBatchReader`

**Rationale:** The headline feature and the only genuine design risk. The reader-lifetime decision introduces patterns (`__aexit__`, `__del__`, per-batch `cancellable_offload`, `_detached` flag) that Phases 2 and 3 copy. EDGE-20 (cleanup error chaining for the reader `__aexit__`) and EDGE-22/23 (`__del__` on `AsyncRecordBatchReader`) belong here.

**Delivers:** `await cursor.fetch_record_batch()` returning `AsyncRecordBatchReader`; `async for batch in reader:` with per-batch `cancellable_offload`; `_detached` guard; shielded reader-close in `__aexit__`; `ResourceWarning` in `__del__`; `_SyncCursor.fetch_record_batch` Protocol stub; EDGE-20/22/23 tests scoped to the reader surface; extended-EDGE-21 test asserting read-after-checkin raises a typed error.

**Addresses:** Differentiator streaming feature; Pitfalls 1, 2, 3, 4 (use-after-free, allocator leak, stream-holds-connection cost documentation, per-batch cancel wiring).

**Research flag:** Standard patterns for the offload wiring (copies `fetch_arrow_table`); reader-lifetime design is fully specified in ARCHITECTURE.md — no additional research phase needed.

### Phase 2: Bulk Write — `adbc_ingest`

**Rationale:** Single whole-operation offload; exercises the write path and the keyword-only-arg-arity concern in isolation. `on_abort=invalidate` is identical to `execute`; no new cancel machinery.

**Delivers:** `await cursor.adbc_ingest(table_name, data, mode, *, catalog_name, db_schema_name, temporary)` returning `int`; `Literal` mode typing; `on_abort=invalidate`; per-mode semantics tests (especially `replace`=drop, `create_append`=create-if-absent); cancel-mid-ingest test; documented non-atomicity caveat.

**Addresses:** Pitfall 6 (mode misuse and partial-apply); Pitfall 5 (GIL/cancel framing — honest docs, not parallelism claims).

**Open question for requirements:** How to handle keyword-only args across the `TypeVarTuple` offload boundary — the `fetchmany` two-arm pattern or a `functools.partial`/lambda. Resolve with a small spike in Phase 2 planning.

**Research flag:** Well-documented write path; no research phase needed.

### Phase 3: DataFrame Convenience — `fetch_df` + `fetch_polars`

**Rationale:** Two genuinely trivial single-offload wrappers. Both fully materialize inside the worker (self-owning, safe after checkin — same EDGE-21 category). No reader-lifetime concern. The only design decision is the missing-dep handling.

**Delivers:** `await cursor.fetch_df()` and `await cursor.fetch_polars()`; `TYPE_CHECKING`-only imports; missing-dep handling per the resolved decision; `pytest.importorskip` guards; no-pandas/no-polars import test extending PKG-04; Protocol stubs.

**Addresses:** Pitfalls 7, 8, 9, 12 (missing-dep handling, GIL framing, pandas/polars out of runtime graph, zero-cost lazy-import path).

**Research flag:** No research phase needed; pure pattern copy. Resolve missing-dep decision before planning.

### Phase 4: P2 Edge Hardening + `__del__` Finalizers

**Rationale:** All four methods must exist before the full P2 suite can cover streaming, ingest, and DataFrame cancel/cleanup paths. `__del__` finalizers on `AsyncCursor`/`AsyncConnection` land here unless EDGE-22 is blocking (move to Phase 1 if so). No new production code beyond what Phases 1–3 introduced.

**Delivers:** EDGE-08 (trio checkpoint delivery); EDGE-13/14 (contextvars copy-in / no-leak-back); EDGE-20 (cleanup error chaining extended to `AsyncCursor`/`AsyncConnection` `__aexit__`); EDGE-22/23 (`__del__` finalizers on `AsyncCursor`/`AsyncConnection`; happy-path `RuntimeWarning` sweep); EDGE-24 (loop-shutdown extended to mid-stream and mid-ingest scenarios); EDGE-31/32 (timeout precision extended to streaming/ingest); `scan_async_package` gate extended to all new files.

**EDGE-16 is DROPPED** (D-24-03): connection aliasing rejected in Phase 24 via `ConnectionBusyError`; do not resurrect.

**Research flag:** No research phase needed; all edge designs fully specified in `ASYNC-EDGE-CASES.md`.

### Phase 5: Docs

**Rationale:** Per CLAUDE.md, documentation is a completion requirement for every phase >= 7. A consolidated docs pass covers all four methods' guide sections, API-reference docstrings (Google-style, `Example:` singular admonition per MEMORY.md), streaming reader-lifetime caveat, pandas/polars user-supplied note, and honest-concurrency framing for `fetch_df`/`fetch_polars`. `.venv/bin/mkdocs build --strict` is the gate; humanizer pass required.

**Delivers:** Streaming guide (reader as context manager, lifetime contract, pool-sizing note); ingest guide (mode table verbatim, `replace`=drop warning, non-atomicity caveat); DataFrame guide (install-yourself note, GIL caveat); API-reference entries for `AsyncRecordBatchReader` and all four `AsyncCursor` methods; `mkdocs build --strict` passing.

**Addresses:** Pitfall 14 (mkdocs strict autoref failures); DOCS-01 honest-concurrency posture extended to new methods.

**Research flag:** No research phase needed; docs-author skill required (`@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>`).

### Phase Ordering Rationale

- **Risk-first:** `fetch_record_batch` is the only design novelty; its reader-lifetime decisions ripple into ingest invalidation semantics and DataFrame `__aexit__` patterns. Phase 1 means Phases 2 and 3 copy proven patterns.
- **Dependency-ordered:** P2 edge tests need all four methods present to exercise streaming, ingest, and DataFrame paths. Phase 4 placement avoids retroactive test extension.
- **Trivial-last among new methods:** `fetch_df`/`fetch_polars` carry the one open design question; Phase 3 placement lets requirements resolve it with full context from Phases 1 and 2.
- **Docs as a named phase:** `mkdocs build --strict` is a hard gate; the final guide + API-reference pass needs its own phase.

### Research Flags

All phases use standard, well-documented patterns fully specified by the research files. No phase needs a `/gsd-plan-phase --research-phase` invocation. Open design decisions are resolved during requirements definition, not by additional research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All findings verified by direct `.venv` introspection, live missing-dep probes, and PyPI JSON |
| Features | HIGH | Four target methods verified against `adbc_driver_manager 1.11.0` source and ADBC reference docs; P2 edge designs from `ASYNC-EDGE-CASES.md` |
| Architecture | HIGH | `fetch_record_batch` use-after-free confirmed by live DuckDB probe; offload patterns verified against v1.4.0 `_async/` source; `AsyncRecordBatchReader` design consensus across all four researchers |
| Pitfalls | HIGH | Root causes traced to upstream source; mode semantics verified; one MEDIUM area: per-backend `adbc_ingest` transactional recovery (driver-dependent, not spec-guaranteed) |

**Overall confidence:** HIGH

### Gaps to Address

The following open questions must be resolved before or during requirements definition. None blocks starting Phase 1.

- **`ReaderClosedError` class name / error hierarchy.** All researchers agree a typed `PoolhouseError` subclass must be raised on read-after-checkin; none pins the class name or whether it shares a base with `ConnectionBusyError`. Resolve in requirements.

- **`fetch_df`/`fetch_polars` missing-dep handling — the one divergent finding across researchers.** STACK: propagate ADBC's raw `ModuleNotFoundError` unchanged (consistent with driver treatment; chokepoint already does this). PITFALLS: `find_spec` pre-check raising a poolhouse-attributable `ImportError` with an install hint (friendlier, consistent with PKG-03). Requirements must pick one. Suggested criterion: if PKG-03 sets a precedent for poolhouse-attributable errors on optional deps, match it; otherwise let the raw error propagate.

- **`adbc_ingest` keyword-only args through the `TypeVarTuple` offload boundary.** Two resolution patterns: the `fetchmany` two-arm pattern or a `functools.partial`/lambda wrapper. Resolve with a short implementation spike in Phase 2 planning.

- **`_in_use` / reader aliasing semantics.** Does `AsyncRecordBatchReader` hold the parent connection's `_in_use` guard for its entire lifetime (blocking concurrent `execute` while un-drained) or only during each individual `__anext__` offload (freeing it between batch pulls)? Per-pull is consistent with the transient-token model but allows concurrent `execute` to interleave between batches on the same connection. Resolve in Phase 1 requirements.

- **Write-side GIL micro-benchmark for `adbc_ingest`.** SPIKE-02 measured read-side GIL behaviour; the write side was not spiked. Whether to add a write-side benchmark is a Phase 2 scope decision. If not spiked, document the concurrency claim conservatively (loop-liveness only, no throughput parallelism claim).

## Sources

### Primary (HIGH confidence)

- Installed-package introspection: `.venv/bin/python -c "import inspect, adbc_driver_manager.dbapi as d; ..."` — verbatim signatures for all four methods, `_blocking_call` wiring, `_RowIterator` / `ArrowArrayStreamHandle` structure, `Cursor._clear` close path
- Live DuckDB probe: `fetch_record_batch` read after `cursor.close()` raises `ArrowInvalid: Attempt to read from a stream that has already been closed`; drain-then-close yields correct data after `conn.close()` — HIGH (empirical)
- Live missing-dep probe: `reader.read_pandas()` and `import polars` with pandas/polars absent raises `ModuleNotFoundError` — HIGH (empirical)
- `.venv/bin/basedpyright` strict-mode probe on extended `_SyncCursor` Protocol scaffold — 0 real diagnostics — HIGH (empirical)
- pyarrow 24.0.0 `__init__.pyi` — confirmed official placeholder stub — HIGH
- PyPI JSON for adbc-driver-manager (1.11.0), pyarrow (24.0.0), anyio (4.14.1), pandas (3.0.3), polars (1.42.1) — HIGH
- ADBC dbapi reference: https://arrow.apache.org/adbc/current/python/api/adbc_driver_manager.html — mode semantics, return types — HIGH
- Upstream `apache/arrow-adbc` `dbapi.py` read directly — `fetch_record_batch` returns `self._results.reader._reader`; internal structure of all four methods — HIGH
- anyio threads docs: https://anyio.readthedocs.io/en/stable/threads.html — `to_thread.run_sync` context copy / no-leak-back; `abandon_on_cancel` default shielded — HIGH

### Secondary (project docs, HIGH confidence in context)

- `.planning/research/ASYNC-EDGE-CASES.md` — full P2 edge designs (EDGE-08, 13/14, 20, 22/23, 24, 31/32); verified anyio/trio semantics
- `.planning/milestones/v1.4.0-REQUIREMENTS.md` — shipped invariants, P2 deferral list, EDGE-16 DROPPED (D-24-03), EDGE-21 materialized-safety contract
- `.planning/milestones/v1.4.0-research/SUMMARY.md` — SPIKE-02 GIL/materialization finding; anyio one-runtime-dep posture
- `src/adbc_poolhouse/_async/_cursor.py` — `_SyncCursor` Protocol, `_offloading()` guard, `fetch_arrow_table` reference pattern
- `src/adbc_poolhouse/_async/_offload.py`, `_cancel.py`, `_connection.py` — transient-token model, `cancellable_offload`, `_in_use` guard, `invalidate` dedicated teardown limiter
- `src/adbc_poolhouse/_pool_factory.py` — `_release_arrow_allocators` reset listener
- `tests/_async_harness/guard.py` — `scan_async_package` rules
- `CLAUDE.md` / `MEMORY.md` — docs-author skill gate, `.venv/bin/basedpyright`, `mkdocs build --strict`, Google-style Markdown docstrings, `Example:` singular admonition

---
*Research completed: 2026-07-01*
*Ready for roadmap: yes*
