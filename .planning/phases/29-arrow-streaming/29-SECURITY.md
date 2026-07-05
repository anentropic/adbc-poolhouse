---
phase: 29
slug: arrow-streaming
status: secured
threats_open: 0
threats_closed: 8
asvs_level: 1
created: 2026-07-01
---

# SECURITY.md — Phase 29: Arrow Streaming

**Audit disposition:** SECURED — all 8 threats verified closed.
**ASVS Level:** 1
**block_on:** high
**Threats closed:** 8/8
**Register source:** authored at plan-time (`register_authored_at_plan_time: true`), `.planning/phases/29-arrow-streaming/29-0[1-4]-PLAN.md`
**Implementation files:** untouched (read-only audit).

Every declared mitigation was verified by locating the mitigation code AND its
proving test in the shipped implementation. Documentation and intent were not
accepted as evidence; each row cites file:line for the code and for the test.

## Threat verification

| Threat ID | Category | Disposition | Status | Code evidence | Test evidence |
|-----------|----------|-------------|--------|---------------|---------------|
| T-29-01 | Denial (use-after-free / segfault) | mitigate | CLOSED | `_pool_factory.py:407-428` `_release_arrow_allocators` reset backstop closes the dbapi cursor on checkin (fires on all return paths, guards `None` dbapi_conn, iterates `_cursors` closing unclosed ones); `_reader.py:281-283` `_detached` idempotency latch; worker exceptions never re-wrapped (`_reader.py:118-121`, `_pull` catches only `StopIteration`, everything else propagates native) | `test_reader_lifetime.py:83-127` — read-after-close AND read-after-checkin both raise native `pyarrow.ArrowInvalid` ("stream that has already been closed"), never a poolhouse error, never a segfault; looped `_LIFETIME_LOOPS=5` to surface allocator reuse |
| T-29-02 | Denial (pool leak on cancel) | mitigate | CLOSED | `_reader.py:250-257` per-pull `cancellable_offload(self._adbc_cancel, _pull, ..., on_abort=self._owner.invalidate)`; `_adbc_cancel` is the owning CURSOR's cancel threaded in at `_cursor.py:410-417`; `_connection.py:303-342` `invalidate` offloads `fairy.invalidate` shielded through dedicated teardown limiter, clears `_reader_open` first | `test_reader_cancel.py:57-127` — cancel and timeout legs both assert `adbc_cancel_call_count == 1` and `invalidate_call_count == 1`; `test_reader_cancel.py:134-159` real DuckDB leg asserts `pool.checkedout() == 0` after `invalidate` |
| T-29-03 | Tampering (concurrent C-access corruption) | mitigate | CLOSED | `_connection.py:149-184` `_enter_offload` two-tier guard: unconditional `_in_use` tier first, then `_reader_open` tier rejected for foreign callers `if self._reader_open and not from_reader`; reader pulls exempt only via `from_reader=True` (`_reader.py:250`, the sole `from_reader=True` caller); foreign cursor/conn ops call `_offloading()` with default `from_reader=False` | `test_reader_busy.py:49-97` — foreign `execute`, second `fetch_record_batch`, and `commit` while reader live all raise `ConnectionBusyError`; `test_reader_busy.py:104-145` own pulls exempt + lock persists past drain; `test_reader_guard.py:61-146` unit-level: foreign rejected, reentrancy exemption skips only reader tier, `_in_use` tier unconditional even `from_reader=True` |
| T-29-04 | Denial (resource leak) | mitigate | CLOSED | `_reader.py:317-333` warn-only `__del__` emits single `ResourceWarning`, NEVER calls `self.close()` (no un-awaited coroutine); `_pool_factory.py:407-428` reset-event checkin backstop releases buffers | `test_reader_resource.py:35-113` — unclosed `__del__` emits `ResourceWarning` and NO "never awaited" `RuntimeWarning`; closed-via-`async with` happy path emits neither warning |
| T-29-05 | Denial (permanent busy lock) | accept/mitigate | CLOSED | `_connection.py:186-188` `_exit_offload` clears `_in_use` only (never `_reader_open`); `_reader.py:284-290` `close` clears `_reader_open` in a `finally` even if close raised; `_connection.py:340` `invalidate` also clears it; fresh `AsyncConnection` per `connect()` is the documented backstop (D-29-13, `_connection.py:93-97` docstring). Accepted-risk rationale HOLDS: a stale `_reader_open == True` is harmless because checkin discards the wrapper | `test_reader_close.py:79-134` (EDGE-20) — raising shielded close still clears `_reader_open` (no `ConnectionBusyError` afterward); `test_reader_guard.py:149-172` `_exit_offload` never writes `_reader_open` |
| T-29-06 | Tampering (StopIteration→RuntimeError leak) | mitigate | CLOSED | `_reader.py:96-121` module-level `_pull` worker-side `except StopIteration: return _EXHAUSTED` (`_EXHAUSTED` singleton `_reader.py:89-93`); `_reader.py:258-259` `__anext__` raises `StopAsyncIteration` on the sentinel | `test_reader_stream.py:64-151` — `async for` yields `pyarrow.RecordBatch` and drains cleanly to `StopAsyncIteration` (no `RuntimeError`), stub leg proves off-loop worker execution |
| T-29-07 | Information disclosure (misleading docs) | mitigate | CLOSED | `docs/src/guides/async.md` — reader-lifetime contract ("locks its connection for its whole lifetime", `ConnectionBusyError` framing ~L176-182), canonical `async with await cursor.fetch_record_batch()` usage (~L146-165), "Always close the reader" section (~L167), read-after-close native `pyarrow.lib.ArrowInvalid` (~L185-201), honest per-batch-offload / GIL framing (~L211-229, "not free of the GIL", "not a parallel pipeline") | Human-verify checkpoint gated accuracy (29-VERIFICATION passed 12/12); `mkdocs build --strict` is the phase completion gate (CLAUDE.md) |
| T-29-SC | Tampering (supply chain) | accept | CLOSED | `pyproject.toml` — no new runtime deps or extras added this phase: `async` extra is `anyio>=4.13` (pre-existing since Phase 24), runtime deps unchanged (`sqlalchemy`, `adbc-driver-manager`), `pyarrow` is a pre-existing test-group dep. RESEARCH Package Legitimacy Audit found no packages installed. Accepted-risk rationale HOLDS | N/A (accept) — verified by inspection: `dependencies` and `optional-dependencies` unchanged |

## Accepted risks log

- **T-29-05 (permanent busy lock) — accepted residual, mitigated in depth.** A
  `_reader_open` flag left True on a wrapper cannot strand a real pooled
  connection: `_exit_offload` never sets it, `close`/`__aexit__`/`invalidate`
  all clear it, and a fresh `AsyncConnection` wraps each `connect()` so checkin
  is the ultimate eraser (D-29-13). Residual risk is confined to a defunct
  in-process wrapper handle and is harmless. Proven by `test_reader_close.py`
  (EDGE-20) and `test_reader_guard.py`.
- **T-29-SC (supply chain) — accepted, zero new attack surface.** No npm / pip /
  cargo packages were installed for this phase. `pyproject.toml` runtime
  dependencies and optional extras are unchanged; the async surface reuses the
  pre-existing `anyio` dependency. No transitive dependency drift introduced.

## Unregistered flags

None. No `## Threat Flags` section is present in any Phase 29 SUMMARY
(`29-0[1-4]-SUMMARY.md`); no new attack surface appeared during implementation
without a mapped threat ID. The 8 register threats cover the phase's entire new
surface (the `AsyncRecordBatchReader`, its two-tier connection guard, and the
checkin backstop).

## Auditor notes

- Independent code review (`29-REVIEW.md`) found NO production defects and traced
  every mitigation sound; this audit independently re-verified each mitigation
  against shipped code + test, not against the review.
- T-29-02 correctly threads the CURSOR's `adbc_cancel` into the reader
  (`_cursor.py:410-417` → `_reader.py:193`), since a `pyarrow` reader has no
  cancel hook of its own (Pitfall 4). Verified the reader does not resolve a
  bogus `self._reader.adbc_cancel`.
- T-29-01's read-after-checkin safety depends on the reset event (not checkin)
  because checkin passes `None` dbapi_conn on invalidation; `_release_arrow_allocators`
  guards this at `_pool_factory.py:423-424`. Verified.
