---
phase: 32-p2-edge-hardening
reviewed: 2026-07-02T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - tests/async/test_edge_checkpoint.py
  - tests/async/test_edge_contextvars.py
  - tests/async/test_edge_shutdown.py
  - tests/async/test_edge_timeout_precision.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: clean
---

# Phase 32: Code Review Report

**Reviewed:** 2026-07-02
**Depth:** standard
**Files Reviewed:** 4
**Status:** clean

## Summary

Four deterministic async edge-case test modules (EDGE-08 checkpoint-before-offload,
EDGE-13/14 contextvar copy-in/no-leak-back, EDGE-24 shutdown cleanliness, EDGE-31/32
timeout precision), each dual-backend (asyncio + trio) and guarded by the x-loop
`concurrency_marks` gate.

I reviewed these as TEST code against the stance that the arrange/trigger/assert
logic is buggy, the assertions are vacuous, or there is a hidden flake/hang. I traced
every load-bearing assertion through the production offload path (`_cursor.py`,
`_reader.py`), the `make_stub_async_connection` fixture, and the pure-threading stubs
(`stubs.py`), and confirmed:

- **Assertions are non-vacuous.** `adbc_cancel_call_count`, `invalidate_call_count`,
  `ingest_call_count`, `df_call_count`, `read_call_count`, `observed_cancel` and
  `scope.cancelled_caught` are all wired to real state that only the exercised path
  mutates. `_adbc_cancel` reaches the stub cursor's `adbc_cancel`; `on_abort` reaches
  the stub connection's `invalidate`. The `seen == ["outer"]` / `_cv.get() == "outer"`
  contextvar pins are backed by anyio's real `copy_context` across the thread boundary.
- **No hang/flake vectors.** No positive-duration real sleeps; every gated leg uses
  `real_clock_watchdog` (wall-clock side thread), never `anyio.fail_after` under the
  autojumping trio `MockClock`; happy-path releases run on real side threads
  (`_release_when_entered` / `_release_reader_when_entered` / `_release_when_entered`
  in contextvars); wedged-worker teardown is handled by releasing every stub worker in
  the teardown window rather than racing a non-cancellable join. The streaming legs arm
  `record_batch_batches = [object()]` before `fetch_record_batch()` so the first pull
  genuinely blocks (Pitfall 5).
- **Single-cursor invariant holds.** Each test calls `async_conn.cursor()` exactly
  once, so `cursors[0]` and `cursors[-1]` reference the same `BlockingStubCursor`; the
  mixed indexing across files is harmless.
- **Watchdog ordering is safe.** In EDGE-32 the post-body `releaser.join(timeout=5)`
  sits outside the watchdog span, but any never-entered reader/ingest blocks the awaited
  pull INSIDE the watchdog, which force-closes the cursors and trips `tripped[0]`,
  failing the assertion rather than hanging.
- **Tooling clean.** `ruff check` passes on all four files; the phase reports green
  basedpyright strict and x20 asyncio+trio CI.

The known-good patterns called out in the prompt (`real_clock_watchdog` over
`fail_after`, real-thread releasers, `record_batch_batches` arming, the `on_enter`
worker-thread hook vs `register_on_enter`) are correct and were NOT flagged.

No Critical or Warning findings. Two Info-level observations below are optional
robustness notes, not defects — the tests are correct as written.

## Info

### IN-01: `no_leak` contextvar assertion relies on `_cv` being set earlier in the same test

**File:** `tests/async/test_edge_contextvars.py:162`
**Issue:** `assert _cv.get() == "outer"` calls `ContextVar.get()` with no default. This is
correct only because line 148 (`_cv.set("outer")`) always runs first on the same task,
so `get()` cannot raise `LookupError`. The invariant is real but implicit — a future
refactor that moved or guarded the `set` would turn a logic regression into a raw
`LookupError` at the assert line rather than a clean assertion failure. Same shape
applies to the `copied_in` twin, though there the worker-side probe reads with an
explicit `"MISSING"` default (`_cv.get("MISSING")`), which is the more defensive form.
**Fix:** Optional. If defensiveness is wanted, mirror the probe's explicit-default style
on the caller-side read so a missing set surfaces as a value mismatch, not an exception:
```python
assert _cv.get("MISSING") == "outer"  # no leak back; explicit default documents the set-first invariant
```
No behavioural change on the passing path; keeps a hypothetical regression as a readable
assertion diff. Leaving it as-is is also acceptable — the set-first ordering is local and
obvious.

### IN-02: `_pull_started` swallows an unexpected reader shape via `getattr` defaults

**File:** `tests/async/test_edge_shutdown.py:85-89`
**Issue:** `_pull_started` reads the blocking stub via
`getattr(reader, "_reader", None)` then `getattr(stub, "read_call_count", 0)`. Both
defaults mask a structural mismatch: if `AsyncRecordBatchReader` ever renamed `_reader`
or the stub renamed `read_call_count` (both are D-04 "hard contract" names, so this is
unlikely), `_pull_started` would silently return `False` forever, and the gate
`await await_inside(lambda: _pull_started(reader))` would spin to its 100k-iteration
bound and then fall through — the pull would be released before it ever blocked, quietly
weakening the "pending offload at teardown" property under test rather than failing loudly.
The `real_clock_watchdog` still prevents a true hang, so this is a resilience/legibility
note, not a correctness bug on the current contract.
**Fix:** Optional. Since these attribute names are a locked contract, direct access would
fail fast on an accidental rename instead of degrading to a vacuous gate:
```python
def _pull_started(reader: AsyncRecordBatchReader) -> bool:
    """Whether the reader's blocking stub has recorded at least one blocked pull."""
    return reader._reader.read_call_count >= 1  # noqa: SLF001  (locked D-04 name)
```
Note this deliberately differs from the sibling `EDGE-32` streaming leg, which already
uses direct `reader._reader` access (`test_edge_timeout_precision.py:226`) — tightening
here would make the two consistent. Keeping the `getattr` form is defensible if the intent
was to tolerate a non-stub reader; on the stub-only path it is dead defensiveness.

---

_Reviewed: 2026-07-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
