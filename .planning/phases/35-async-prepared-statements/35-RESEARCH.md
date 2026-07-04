# Phase 35: Async Prepared Statements - Research

**Researched:** 2026-07-04
**Domain:** Async offload wrappers over the sync ADBC dbapi cursor (`adbc_prepare`, `adbc_execute_schema`)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-35-01:** Both methods are new methods on the existing `AsyncCursor`
  (`src/adbc_poolhouse/_async/_cursor.py`) — clones of the `execute` offload shape
  (`_cursor.py:200`): one `with self._owner._offloading():` span wrapping a single
  `cancellable_offload(...)`. No new file, no reader class, no `_reader_open`
  lifetime lock — the connection checks back in the moment the offload completes.
- **D-35-02:** `adbc_prepare(operation: bytes | str)` returns `pyarrow.Schema | None`
  (bind-parameter schema, or `None` when the driver cannot determine it). Returned
  unchanged. Forward `operation` **positionally** through `cancellable_offload` — no
  `functools.partial`.
- **D-35-03:** `adbc_execute_schema(operation: str, parameters: object = None)` returns
  `pyarrow.Schema` — the result-set schema **without executing** the query. Forward
  `operation` and `parameters` **positionally**. No `functools.partial`.
- **D-35-04 (LOCKED WITH USER):** Both methods use
  `cancellable_offload(self._adbc_cancel, ...)` with `on_abort` **omitted** (defaults
  to `None`). Cancellable but **non-poisoning**. Cancellable because the sync methods
  route through `_blocking_call(..., self._stmt.cancel)`; non-poisoning because neither
  executes/writes, so no `invalidate`. **Do not reopen this.**
- **D-35-05:** Extend the `_SyncCursor` Protocol (`_cursor.py:58`) with
  `adbc_prepare(self, operation: bytes | str, /) -> object` and
  `adbc_execute_schema(self, operation: str, parameters: object = ..., /) -> object`.
  Must stay basedpyright-strict-clean.
- **D-35-06:** No invented async error types, no `find_spec` pre-checks, no bespoke
  wrapping. Unsupported backend surfaces the driver's native error unchanged (EDGE-17).
  `adbc_execute_schema` must **not** execute the query (test asserts no side effects).
- **D-35-07:** No sync-side wrapper added or needed (sync surface is pool-only; native
  raw-cursor exposes both methods).
- **D-35-08:** Remove the async-guide caveat (prepared statements is the last bullet in
  the "not available yet" block → whole block goes; "What you get today" updated). Also
  fix `docs/src/index.md:71` — drop the stale "async ADBC metadata **and** prepared
  statements have not shipped yet" clause (metadata shipped in Phase 34). API reference
  renders both new symbols; `mkdocs build --strict` passes; humanizer pass on
  new/rewritten prose. Docs quality gate per CLAUDE.md (phases ≥ 7).

### Claude's Discretion
- Exact test-harness mechanism for a deterministic in-flight cancel (blocking fake vs.
  slow DuckDB) — follow the Phase 23/29 harness precedent. **This research recommends the
  blocking stub (see Validation Architecture).**
- Whether the async guide gets a short worked "prepare then execute" snippet vs.
  API-reference stubs only. **This research recommends a brief snippet.**
- Docstring prose and Example-block wording (subject to the docs quality gate).

### Deferred Ideas (OUT OF SCOPE)
- Partitioned result sets (`adbc_execute_partitions` / `adbc_read_partition`) —
  permanently deferred this milestone (niche Flight-SQL-oriented; most backends return
  unsupported).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PREP-01 | `adbc_prepare` + `adbc_execute_schema` awaitable on the async cursor, each a pure offload wrapper routed through the existing chokepoint + per-pool `CapacityLimiter` | `execute` at `_cursor.py:200` is the exact template; `cancellable_offload` at `_cancel.py:41` takes `on_abort=None`; sync signatures verified against `adbc_driver_manager` 1.11.0 |
| PREP-02 | Behavior mirrors sync — `adbc_execute_schema` returns the result schema without executing; no invented async error types | Sync `adbc_execute_schema` uses `_prepare_execute` + `execute_schema` (never `execute`); DuckDB/SQLite raise native `NotSupportedError` unchanged through the chokepoint (EDGE-17); no-execute proven via stub `execute_call_count == 0` |
| PREP-03 | Async guide + API reference document the methods; caveat line removed; `mkdocs build --strict` passes; humanizer pass | `docs/src/guides/async.md:23–32` + `docs/src/index.md:71` confirmed; API reference auto-renders `AsyncCursor` members via mkdocstrings `filters: ["!^__"]` — docstrings only, no nav edit |
</phase_requirements>

## Summary

This is the simplest phase in the v1.5.0 milestone — a near-exact structural twin of
`AsyncCursor.execute` (`_cursor.py:200`), differing only in the wrapped callable, the
return annotation, and the **absence** of `on_abort=self._owner.invalidate`. Two new
awaitable methods (`adbc_prepare`, `adbc_execute_schema`) offload their identically-named
sync `dbapi.Cursor` counterparts through the established `cancellable_offload` chokepoint.
Both sync methods route through `_blocking_call(..., self._stmt.cancel)` — verified in the
installed `adbc_driver_manager` 1.11.0 source — so they are genuinely driver-abortable
(hence `cancellable_offload` + `self._adbc_cancel`), but neither executes or writes, so a
cancelled call cannot poison the connection (hence no `on_abort`). This exactly implements
locked decision D-35-04.

The one non-obvious finding that shapes the test plan: **both DuckDB and SQLite raise
`NotSupportedError: NOT_IMPLEMENTED: AdbcStatementExecuteSchema not implemented` for
`adbc_execute_schema`** (verified by live probe). `adbc_prepare`, by contrast, works on
DuckDB and returns a real (possibly empty) `pyarrow.Schema`, not `None`. This splits the
validation cleanly: `adbc_prepare` gets a real-DuckDB positive round-trip; the positive
"returns result schema without executing" contract for `adbc_execute_schema` must be
proven against the **blocking stub cursor** (which also carries the deterministic in-flight
cancel test); and the DuckDB `NotSupportedError` becomes the ready-made EDGE-17 / PREP-02
"unsupported backend surfaces native error unchanged" leg.

**Primary recommendation:** Clone `execute` twice, drop `on_abort`, add two `_SyncCursor`
Protocol signatures, extend `BlockingStubCursor` with two blocking methods (with an
`execute_call_count`-untouched invariant for the no-execute proof), and follow the Phase
34 TDD rhythm. Prove `adbc_prepare` on DuckDB, `adbc_execute_schema` value + no-execute on
the stub, and unsupported-passthrough on DuckDB.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `adbc_prepare` await surface | `AsyncCursor` (`_async/_cursor.py`) | — | Cursor-level ADBC statement lifecycle; offloaded through the pool limiter |
| `adbc_execute_schema` await surface | `AsyncCursor` (`_async/_cursor.py`) | — | Same tier; result-set schema without execution |
| Blocking C call + abort | sync `dbapi.Cursor` (worker thread) | `cancellable_offload` (`_async/_cancel.py`) | The driver owns the C call and `_stmt.cancel`; the async layer only orchestrates offload + cancel |
| Structural typing of the sync surface | `_SyncCursor` Protocol (`_cursor.py:58`) | basedpyright-strict gate | Keeps the async layer driver-agnostic + stub-testable |
| Concurrency guard | `AsyncConnection._offloading()` / `_in_use` (`_connection.py`) | — | Reused unchanged; concurrent cursor use → `ConnectionBusyError` |
| Docs render | mkdocstrings over `AsyncCursor` | docs-author skill | Auto-renders new members; docstrings are the source of truth |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `adbc_driver_manager` | 1.11.0 (installed) | Provides sync `dbapi.Cursor.adbc_prepare` / `adbc_execute_schema` | Already the wrapped sync core; no change |
| `pyarrow` | ≥ 23.0.1 (installed, real `.pyi` stubs) | `pyarrow.Schema` return type | Already a core dep |
| `anyio` | installed (`[async]` extra) | `cancellable_offload` / `CapacityLimiter` chokepoint | Established async machinery |
| `adbc_driver_duckdb` | installed | Real-driver test leg for `adbc_prepare` + unsupported `adbc_execute_schema` | In-proc, deterministic |

**No new packages.** This phase installs nothing — every dependency is already present.
See Package Legitimacy Audit.

### Version verification
- `adbc_driver_manager.__version__ == "1.11.0"` — verified via `.venv/bin/python`.
- Sync method sources introspected via `inspect.getsource` (see Code Examples).

## Package Legitimacy Audit

> No external packages are installed by this phase. All dependencies (`adbc_driver_manager`,
> `pyarrow`, `anyio`, `adbc_driver_duckdb`) are pre-existing and already vetted in prior
> phases.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | No installs this phase |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
await cursor.adbc_prepare(operation)                await cursor.adbc_execute_schema(operation, parameters)
        │                                                   │
        ▼                                                   ▼
  with self._owner._offloading():   ── acquires _in_use guard (concurrent use → ConnectionBusyError)
        │
        ▼
  cancellable_offload(
      self._adbc_cancel,            ── driver-abortable (sync method wraps _blocking_call(..., _stmt.cancel))
      self._cursor.adbc_prepare,    ── or self._cursor.adbc_execute_schema
      operation[, parameters],      ── POSITIONAL forwarding (no functools.partial)
      limiter=self._limiter,        ── per-pool CapacityLimiter
      # on_abort OMITTED            ── NON-POISONING (D-35-04): no invalidate
  )
        │
        ├── success ──▶ worker returns pyarrow.Schema | None ──▶ connection checks in immediately
        │
        └── cancel/timeout ──▶ watcher fires adbc_cancel ONCE (shielded) ──▶ re-raise cancellation
                               ▶ NO invalidate ▶ clean connection returns to pool, checkedout()==0
```

### Recommended Project Structure
No new files. Edits confined to:
```
src/adbc_poolhouse/_async/_cursor.py   # +2 Protocol signatures (:58), +2 methods (after :564)
tests/_async_harness/stubs.py          # +2 blocking methods + 2 counters on BlockingStubCursor
tests/async/test_prep_*.py             # new RED→GREEN test files (signature/roundtrip/no-execute/cancel/unsupported)
docs/src/guides/async.md               # remove caveat block (:23–32), add prepare snippet
docs/src/index.md                      # drop stale clause (:71)
```

### Pattern 1: Non-poisoning cancellable offload (the phase's signature shape)
**What:** Clone `execute` but omit `on_abort`.
**When to use:** A cursor-level call that is driver-abortable but writes no state.
**Example:**
```python
# Source: adapted from src/adbc_poolhouse/_async/_cursor.py:200 (execute), D-35-04
async def adbc_prepare(self, operation: bytes | str) -> pyarrow.Schema | None:
    with self._owner._offloading():  # noqa: SLF001
        return cast(
            "pyarrow.Schema | None",
            await cancellable_offload(
                self._adbc_cancel,
                self._cursor.adbc_prepare,
                operation,                # positional — no functools.partial
                limiter=self._limiter,
                # on_abort OMITTED (D-35-04): cancellable but non-poisoning
            ),
        )
```

### Pattern 2: `cast` from the driver-agnostic Protocol return
**What:** `_SyncCursor.adbc_prepare` is typed `-> object` (D-35-05), so the public method
`cast`s back to `pyarrow.Schema | None`, exactly as `fetch_df` casts to `pandas.DataFrame`
(`_cursor.py:417`). No runtime effect.

### Anti-Patterns to Avoid
- **Adding `on_abort=self._owner.invalidate`** — this is the `execute`/`fetchall` poison
  path. These methods do not execute; invalidating a never-poisoned connection is the exact
  CR-34-01 hazard (dropping a clean connection). D-35-04 forbids it.
- **`functools.partial`** — only needed for keyword-only args (Phase 30 `adbc_ingest`).
  Both new methods forward positionals; a partial adds noise and diverges from `execute`.
- **`find_spec` / backend capability pre-check** — D-35-06 forbids it. Let DuckDB's
  `NotSupportedError` surface unchanged.
- **Assuming `adbc_prepare` returns a non-null Schema** — it returns `Optional`; the
  round-trip test must accept both `Schema` and `None`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Off-loop cancel of a blocking C call | A custom watcher/thread | `cancellable_offload` (`_cancel.py:41`) | Already handles the worker-started gate, shielded single-fire `adbc_cancel`, ExceptionGroup unwrap (EDGE-17/19) |
| Concurrent-use rejection | A new lock | `self._owner._offloading()` | Reused as-is; raises `ConnectionBusyError` |
| Driver cancel resolution | Re-derive the cancel hook | `self._adbc_cancel` (`_cursor.py:151`) | Already tolerant of a missing hook |
| Deterministic in-flight cancel test | A real slow query | `BlockingStubCursor._block()` gate | DuckDB `adbc_cancel` intermittently wedges (~10–40% cold, MEMORY loop-flaky lesson) |

**Key insight:** Every mechanism this phase needs already exists and is proven. The phase
is 100% reuse — the only genuinely new code is two ~10-line methods and two Protocol lines.

## Common Pitfalls

### Pitfall 1: Testing `adbc_execute_schema` value against DuckDB
**What goes wrong:** A "returns the result schema" round-trip test written against DuckDB
(or SQLite) fails with `NotSupportedError: NOT_IMPLEMENTED: AdbcStatementExecuteSchema not
implemented`.
**Why it happens:** The embedded backends do not implement `AdbcStatementExecuteSchema`
(verified live for both DuckDB and SQLite).
**How to avoid:** Prove the positive value + no-execute contract against the **blocking
stub cursor** (inject a sentinel `pyarrow.Schema`, assert `execute_call_count == 0`). Use
the DuckDB `NotSupportedError` as the *unsupported-passthrough* leg instead.
**Warning signs:** A green `adbc_prepare` test but a red `adbc_execute_schema` test with
`NOT_IMPLEMENTED` — that is the backend, not your code.

### Pitfall 2: Expecting `adbc_prepare` to return `None`
**What goes wrong:** A test asserting `result is None` fails on DuckDB.
**Why it happens:** DuckDB returns a real `pyarrow.Schema` — empty (`0` fields) for a
no-parameter query, one `0: null` field for a single `?`. `None` only appears when the
driver's `get_parameter_schema` raises `NotSupportedError` internally.
**How to avoid:** Assert `isinstance(result, (pyarrow.Schema, type(None)))`; the round-trip
must tolerate both (D-35-02, specifics note).

### Pitfall 3: Snowflake cassette leg for the new methods
**What goes wrong:** Attempting a `@pytest.mark.snowflake` replay leg hangs or errors.
**Why it happens:** Per the resolved A1 blocker (Phase 29), `pytest-adbc-replay`'s
`ReplayCursor` implements only `fetch_arrow_table` + row fetches — it has no
`adbc_prepare` / `adbc_execute_schema`, and stores one materialized Arrow result.
**How to avoid:** DuckDB (`adbc_prepare` + unsupported `execute_schema`) and the stub
(`execute_schema` value/cancel) carry the coverage. Mark any Snowflake leg manual-only /
skip, consistent with the Phase 29 A1 precedent.

### Pitfall 4: `coroutine was never awaited` on a mistyped Protocol signature
**What goes wrong:** basedpyright-strict flags the new methods or the Protocol.
**Why it happens:** The `_SyncCursor` return must be `-> object` (driver-agnostic); the
public method must `cast`. Forgetting the cast, or annotating the Protocol with
`pyarrow.Schema`, breaks strict typing.
**How to avoid:** Mirror `fetch_df` exactly (`_cursor.py:82` Protocol line, `:417` cast).

## Runtime State Inventory

> Not applicable — this is an additive greenfield phase (two new methods), not a
> rename/refactor/migration. No stored data, live-service config, OS-registered state,
> secrets, or build artifacts embed any renamed string. None — verified: the phase adds
> symbols, renames nothing.

## Code Examples

### Verified sync signatures (adbc_driver_manager 1.11.0)
```python
# Source: inspect.getsource(adbc_driver_manager.dbapi.Cursor.adbc_prepare)
def adbc_prepare(self, operation: Union[bytes, str]) -> Optional["pyarrow.Schema"]:
    # ... returns schema of the BIND PARAMETERS, or None if undeterminable
    self._clear()
    self._prepare_execute(operation)
    try:
        handle = _blocking_call(self._stmt.get_parameter_schema, (), {}, self._stmt.cancel)
    except NotSupportedError:
        return None                      # <-- the None branch
    return self._conn._backend.import_schema(handle)

# Source: inspect.getsource(adbc_driver_manager.dbapi.Cursor.adbc_execute_schema)
def adbc_execute_schema(self, operation, parameters=None) -> "pyarrow.Schema":
    # ... returns schema of the RESULT SET, WITHOUT executing
    self._clear()
    self._prepare_execute(operation, parameters)   # prepares only; never .execute()
    schema = _blocking_call(self._stmt.execute_schema, (), {}, self._stmt.cancel)
    return self._conn._backend.import_schema(schema)
```
Both wrap `_blocking_call(..., self._stmt.cancel)` — confirming D-35-04's *cancellable*
axis. Neither calls `self._stmt.execute()` — confirming *non-poisoning* and the
no-execute contract (PREP-02).

### Live DuckDB behavior (verified probe)
```python
# adbc_prepare on DuckDB → real pyarrow.Schema (NOT None)
cur.adbc_prepare("SELECT * FROM t WHERE id = ?")   # -> Schema: "0: null"  (one bind param)
cur.adbc_prepare("SELECT * FROM t")                # -> Schema: ""          (empty, 0 fields)

# adbc_execute_schema on DuckDB AND SQLite → raises:
#   adbc_driver_manager.NotSupportedError:
#   NOT_IMPLEMENTED: [Driver Manager] AdbcStatementExecuteSchema not implemented
```

### Protocol extension (D-35-05)
```python
# Source: add to _SyncCursor in src/adbc_poolhouse/_async/_cursor.py:58
def adbc_prepare(self, operation: bytes | str, /) -> object: ...
def adbc_execute_schema(self, operation: str, parameters: object = ..., /) -> object: ...
```

### Harness extension (BlockingStubCursor, tests/_async_harness/stubs.py)
```python
# Mirror `adbc_ingest` (stubs.py:397): record + _block() + return an injectable value.
# CRITICAL: do NOT touch execute_call_count — the no-execute proof reads it == 0.
def adbc_prepare(self, operation: object = None) -> object:
    del operation
    with self._lock:
        self.prepare_call_count += 1
    self._block()
    return self._prepare_result           # injectable: a sentinel pyarrow.Schema OR None

def adbc_execute_schema(self, operation: object = None, parameters: object = None) -> object:
    del operation, parameters
    with self._lock:
        self.execute_schema_call_count += 1
    self._block()
    return self._execute_schema_result    # injectable sentinel pyarrow.Schema
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 30 keyword-only args via `functools.partial` | Positional forwarding, no partial | Phase 35 (D-35-02/03) | Simpler; diffs cleanly against `execute` |
| Phase 34 metadata: plain non-cancellable `offload` (no cancel hook) | `cancellable_offload` + `self._adbc_cancel`, no `on_abort` | Phase 35 (D-35-04) | New two-axis point: cancellable AND non-poisoning |
| `execute`/`fetchall`: `on_abort=invalidate` | `on_abort` omitted | Phase 35 (D-35-04) | Cancelled prepare/execute_schema keeps the connection clean |

**Deprecated/outdated:** none relevant to this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Snowflake cassette (`ReplayCursor`) does not implement `adbc_prepare`/`adbc_execute_schema`, so both new methods have no cassette leg | Pitfall 3 | LOW — mirrors the resolved Phase 29 A1; worst case an extra skip. Planner should confirm `ReplayCursor` surface before writing any snowflake leg |

**All other claims verified via live probe or source introspection this session.**

## Open Questions

1. **Positive `adbc_execute_schema` on a real backend**
   - What we know: DuckDB + SQLite both return `NotSupportedError`.
   - What's unclear: whether any installed backend implements it (PostgreSQL/Flight SQL
     might, but are not part of the deterministic in-proc test matrix).
   - Recommendation: Do **not** chase a real-backend positive leg — prove value +
     no-execute on the stub; DuckDB carries the unsupported-passthrough leg. This is
     sufficient for PREP-01/02.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `adbc_driver_manager` | Sync methods being wrapped | ✓ | 1.11.0 | — |
| `pyarrow` | `Schema` return type | ✓ | ≥ 23.0.1 (real `.pyi` stubs) | — |
| `anyio` | offload chokepoint | ✓ | `[async]` extra | — |
| `adbc_driver_duckdb` | `adbc_prepare` + unsupported-`execute_schema` legs | ✓ | installed | — |
| `.venv/bin/basedpyright` | strict typing gate | ✓ | authoritative (not harness Pyright) | — |
| `.venv/bin/mkdocs` | `--strict` docs gate | ✓ | Material + mkdocstrings | `uv run mkdocs` (sandbox-prompt) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none blocking.

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — this section is required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + `pytest-anyio` (`@pytest.mark.anyio`, asyncio + trio) |
| Config file | `pyproject.toml` (existing `[tool.pytest.ini_options]`) |
| Quick run command | `.venv/bin/python -m pytest tests/async/test_prep_*.py -q` |
| Full suite command | `ADBC_ASYNC_REPEAT=20 .venv/bin/python -m pytest tests/async -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PREP-01 | Both methods exist + are awaitable on `AsyncCursor`; Protocol carries both signatures | signature (runtime introspection + basedpyright-strict) | `pytest tests/async/test_prep_signature.py -x` + `.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py` | ❌ Wave 0 |
| PREP-01 | `adbc_prepare` round-trips the driver's value (Schema or None) on real DuckDB; connection checks in (`checkedout()==0`) | integration (DuckDB, dual-backend) | `pytest tests/async/test_prep_roundtrip.py -x` | ❌ Wave 0 |
| PREP-02 | `adbc_execute_schema` returns the injected result Schema **without executing** (`execute_call_count == 0`) | unit (blocking stub) | `pytest tests/async/test_prep_no_execute.py -x` | ❌ Wave 0 |
| PREP-02 | Unsupported backend surfaces the driver's native `NotSupportedError` unchanged (EDGE-17) | integration (DuckDB) | `pytest tests/async/test_prep_unsupported.py -x` | ❌ Wave 0 |
| PREP-01/02 | Deterministic in-flight cancel: `adbc_cancel` fires **once**, `invalidate` **not** called, `checkedout()==0`, no hang; dual-backend, looped | concurrency (blocking stub + real-clock watchdog) | `ADBC_ASYNC_REPEAT=20 pytest tests/async/test_prep_cancel.py -x` | ❌ Wave 0 |
| PREP-03 | Guide + reference document both methods; caveat removed; strict build passes | docs gate | `DISABLE_MKDOCS_2_WARNING=true .venv/bin/mkdocs build --strict` (exit 0) | ❌ Wave 0 |

### Test design notes (deterministic)
- **`adbc_prepare` positive → real DuckDB.** Prepare `"SELECT * FROM t WHERE id = ?"`;
  assert `isinstance(result, (pyarrow.Schema, type(None)))` (Pitfall 2 — do NOT assert
  non-null). Assert `pool.checkedout() == 0` after the scope (no reader lifetime lock).
- **`adbc_execute_schema` value + no-execute → blocking stub.** Inject a sentinel
  `pyarrow.Schema` as `_execute_schema_result`; assert the awaited value is that object
  **and** `stub_cursor.execute_call_count == 0` (the no-execute proof, PREP-02). DuckDB
  cannot host this leg (`NotSupportedError`).
- **Unsupported passthrough → real DuckDB.** `await cursor.adbc_execute_schema("SELECT 1")`
  must raise `adbc_driver_manager.NotSupportedError` with the native `NOT_IMPLEMENTED`
  message, unwrapped (EDGE-17 chokepoint contract). This doubles as the PREP-02
  "no invented error type" assertion.
- **Cancel → blocking stub, NOT DuckDB.** Gate on `prepare_call_count >= 1` (or
  `execute_schema_call_count >= 1`), cancel the scope from a REAL thread (real-clock
  watchdog, MEMORY carried-forward gotcha — never `anyio.fail_after` which autojumps under
  the trio MockClock). Assert: `adbc_cancel_call_count == 1` (cancellable) **and**
  `invalidate_call_count == 0` (non-poisoning, D-35-04) **and** the watchdog did not trip.
  This is the hybrid of `test_ingest_cancel.py` (cursor `adbc_cancel`) and
  `test_meta_cancel.py` (invalidate-not-called). Run under `ADBC_ASYNC_REPEAT=20`, both
  backends — the "0-hang loop" gate (MEMORY loop-flaky lesson; single-shot missed a ~33%
  deadlock in Phase 23).
- **Harness prerequisite (Wave 0).** `BlockingStubCursor` (`tests/_async_harness/stubs.py`)
  must gain `adbc_prepare` + `adbc_execute_schema` (blocking, injectable result) plus
  `prepare_call_count` / `execute_schema_call_count` counters, mirroring `adbc_ingest`
  (`stubs.py:397`). The stub must **not** bump `execute_call_count` from these methods.

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/async/test_prep_*.py -q`
- **Per wave merge:** `ADBC_ASYNC_REPEAT=20 .venv/bin/python -m pytest tests/async -q`
  (0 hangs) + `.venv/bin/basedpyright src/adbc_poolhouse/_async/` (0 errors) + import-lint
  guard (PKG-03) + `.venv/bin/mkdocs build --strict` (exit 0)
- **Phase gate:** full async suite green + Linux CI leg for the cancel test (carried-forward
  platform-dependent lost-wakeup gotcha — passes 20/20 on macOS can still hang on Linux CI)
  before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/async/test_prep_signature.py` — PREP-01 existence + Protocol shape (RED)
- [ ] `tests/async/test_prep_roundtrip.py` — PREP-01 DuckDB `adbc_prepare` value + checkin
- [ ] `tests/async/test_prep_no_execute.py` — PREP-02 stub value + `execute_call_count == 0`
- [ ] `tests/async/test_prep_unsupported.py` — PREP-02 DuckDB `NotSupportedError` passthrough
- [ ] `tests/async/test_prep_cancel.py` — PREP-01/02 deterministic cancel, no-invalidate, looped
- [ ] `tests/_async_harness/stubs.py` — add two blocking methods + two counters (shared fixture)

## Security Domain

> `security_enforcement` not set to `false` (absent = enabled), but this phase is a
> library-internal async wrapper with no auth, session, network, or crypto surface.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | partial | `operation`/`parameters` are forwarded verbatim to the driver, which owns SQL binding — poolhouse does not construct or sanitize SQL (same contract as `execute`) |
| V6 Cryptography | no | — |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `operation` | Tampering | Not poolhouse's boundary — the caller passes SQL to the driver exactly as with sync `adbc_prepare`; parameterized queries are the user's responsibility (mirrors `execute`, D-35-06) |

No new attack surface: the methods add no parsing, no I/O beyond the driver call, and no
new error handling.

## Project Constraints (from CLAUDE.md)
- Docs are a completion requirement for phases ≥ 7: all new public symbols need Google-style
  docstrings (Args/Returns/Raises); key entry points get an `Example:` block; new
  consumer-facing behavior reflected in the async guide; `mkdocs build --strict` passes;
  humanizer pass on new/rewritten prose. Include
  `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in the plan `<execution_context>`.
- Docstring style: **Google-style**, **Markdown not RST** (`` `create_pool` `` not
  `:func:`create_pool``); singular `Example:` (admonition) with fenced ```python blocks.
- Use `.venv/bin/<tool>` (basedpyright, mkdocs) over `uv run <tool>` under the sandbox;
  `.venv/bin/basedpyright` is authoritative (harness Pyright gives false import errors).
- API reference auto-renders `AsyncCursor` members via mkdocstrings (`filters: ["!^__"]`,
  `docs/scripts/gen_ref_pages.py:43`) — the two new methods render from their docstrings
  with **no nav or `:::` edit** needed.
- Edit STATE/ROADMAP/REQUIREMENTS by hand (gsd-tools lacks mutation handlers); commit via
  `query commit --files`.

## Sources

### Primary (HIGH confidence)
- `adbc_driver_manager.dbapi.Cursor.adbc_prepare` / `.adbc_execute_schema` — source via
  `inspect.getsource`, version 1.11.0 (installed `.venv`)
- Live DuckDB + SQLite probe — `adbc_prepare` returns real `Schema`; both raise
  `NotSupportedError` on `adbc_execute_schema`
- `src/adbc_poolhouse/_async/_cursor.py` (`execute` :200, `_SyncCursor` :58, `_adbc_cancel`
  :151, `fetch_df` cast :417) — the exact template
- `src/adbc_poolhouse/_async/_cancel.py` (`cancellable_offload` :41, `on_abort=None` default)
- `tests/_async_harness/stubs.py` (`BlockingStubCursor` :67, `_block` :263, `adbc_ingest`
  :397, `adbc_cancel` :443, counters)
- `tests/async/test_meta_cancel.py` (invalidate-not-called cancel template),
  `tests/async/test_meta_signature.py` (introspection RED template)
- `docs/src/guides/async.md:23–32`, `docs/src/index.md:71`, `docs/scripts/gen_ref_pages.py:43`
- `.planning/phases/35-async-prepared-statements/35-CONTEXT.md`, `.planning/REQUIREMENTS.md`,
  `.planning/STATE.md`

### Secondary (MEDIUM confidence)
- Phase 29 A1 resolution (STATE.md) — `ReplayCursor` streaming/method limitation informs
  the Snowflake-leg assumption

### Tertiary (LOW confidence)
- none

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — sync signatures + versions verified via introspection
- Architecture: HIGH — direct clone of the proven `execute` shape; D-35-04 locked
- Pitfalls: HIGH — DuckDB/SQLite `NotSupportedError` and `adbc_prepare` return shape
  verified by live probe
- Validation: HIGH — test legs mapped to verified backend behavior; harness extension
  mirrors existing `adbc_ingest`

**Research date:** 2026-07-04
**Valid until:** 2026-08-03 (stable; pinned to `adbc_driver_manager` 1.11.0 — re-verify
`adbc_execute_schema` support if the driver is upgraded, as a future DuckDB release could
implement `AdbcStatementExecuteSchema` and change the unsupported-passthrough leg)
