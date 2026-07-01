---
phase: 23-test-harness-foundation
fixed_at: 2026-06-27
review_path: .planning/phases/23-test-harness-foundation/23-REVIEW.md
iteration: 1
fix_scope: all
findings_in_scope: 8
fixed: 3
reverted: 5
skipped: 0
status: partial
---

# Phase 23: Code Review Fix Report

> `/gsd-code-review 23 --fix --all` was attempted. An auto-applied fix (WR-01)
> introduced a hard deadlock, so it and the stub-contract findings entangled with
> it were rolled back. Three safe findings were kept. A separate, **pre-existing**
> flaky deadlock in the harness self-tests was found during verification and fixed.
> Net result: a **deterministic, green** harness (316 passed, 2 skipped; full
> suite 8/8 and harness tests 20/20 with zero hangs).

## Fixed (kept)

### WR-04 — `run_blocking` cancellation semantics documented + opt-in param
`gating.py`: documented that `run_blocking` is NON-cancellable by design (the
consumer must release/cancel the stub to unblock the worker) and added an
additive, default-`False` `abandon_on_cancel` keyword forwarded to
`to_thread.run_sync`, so the Phase 24/25 timeout EDGE cases can opt into the
cancellable variant. Default-false → existing callers unaffected. (commit `4241411`)

### IN-01 — guard false-positive surface documented
`guard.py`: added a note that `scan_async_package`'s `to_thread.run_sync` matcher
is name-based and would also flag an unrelated `*.to_thread.run_sync` attribute
chain. (commit `0f76d3b`)

### IN-02 — `scan_async_package` tolerates unparseable files
`guard.py`: `ast.parse` of a malformed / non-UTF-8 file now emits a `Finding`
instead of aborting the whole scan with a traceback. (commit `0f76d3b`)

## Reverted (deferred to Phase 24)

These were rolled back (commit `696e54e`) and are **not** applied. They are
stub-contract hardening items the phase verifier already flagged for Phase 24 to
own, where the real async wrappers exist and the harness's `entered`-timing can be
designed correctly.

### WR-01 — re-armable cursor gate — REVERTED (introduced a deadlock)
The fix replaced the stub's sticky blocking event with a per-call latch so a
cursor could gate on `execute` then `fetch_arrow_table` (Phase 24 reuse). But
`run_blocking` signals the loop-facing `entered` event BEFORE the worker enters
the blocked section, so a worker can register its latch AFTER the test's
`release()` and then wait on a never-set latch forever. `test_max_concurrent`
deadlocked the task group under full-suite scheduling (passed in isolation). The
old sticky event tolerated this (a late worker saw the already-set event). A
correct re-armable gate needs the `entered`-after-block redesign that belongs with
Phase 24's wrapper work. **Deferred.**

### WR-02 / WR-03 / IN-03 / IN-04 — REVERTED (entangled with WR-01)
`WR-02` (connection→cursor `close`/`adbc_cancel` propagation), `WR-03`
(`observed_cancel` / `closed` set under the counter's lock), `IN-03` (promote
`_closed` to a public `closed` attribute), and `IN-04` (deterministic
max-concurrent rewrite in `test_stubs.py`) all lived in `stubs.py` /
`test_stubs.py` alongside the broken WR-01 re-arm. They were rolled back together
with WR-01 to restore a known-good gate rather than surgically disentangle a file
mid-deadlock. WR-03 and IN-03 are low-risk and could be re-applied to the sticky
stub in a focused follow-up; WR-02 is a feature Phase 24/25 can add when an EDGE
case needs connection-close-cancels-cursors semantics. **Deferred.**

## Bonus: pre-existing flaky deadlock fixed (not a review finding)

Verification surfaced a deadlock that was **already in Phase 23** (the single-shot
"307 passed" closeout got lucky): `test_max_concurrent`,
`test_offloaded_thread_id`, and `test_block_then_release` asserted a stub
invariant the instant `entered` fired — before the worker had recorded it — and
the non-cancellable offload turned a missed assert into a hung task group (~33% of
full-suite runs). Fixed at the test level (no contract change): poll the
lock-guarded invariant via a bounded `anyio.sleep(0)` helper after `await
entered`, and ALWAYS `release()` in a `finally`. (commit `943c074`)

## Verification

- Harness self-tests: **20/20** runs pass, **0 hangs** (was ~33% deadlock).
- Full suite: **8/8** runs pass, **0 hangs**; `316 passed, 2 skipped` (~0.7s).
- `ruff check` + `ruff format --check`: clean. `basedpyright` strict: 0 errors.
- `mkdocs build --strict`: unaffected (no doc-surface change in the kept fixes).

## Contract note for Phase 24

The stub/gating HARD CONTRACT (D-04/D-05) is unchanged from the verified Phase 23
baseline except for the additive `run_blocking(abandon_on_cancel=False)` (WR-04).
Phase 24 should: (a) decide the `entered`-after-block redesign so cursors can be
reused (WR-01) and timeout EDGE cases gate correctly; (b) re-apply WR-02/WR-03/
IN-03 if the EDGE cases need them; and (c) reuse the `_await_inside` poll pattern
(or the redesigned `entered`) instead of asserting on the bare `entered` event.

_Iteration: 1 · Scope: all · Fixed: 3 · Reverted/deferred: 5 · Skipped: 0_
