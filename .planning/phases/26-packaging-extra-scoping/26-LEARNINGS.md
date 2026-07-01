---
phase: 26
phase_name: "Packaging & Extra Scoping"
project: "adbc-poolhouse"
generated: "2026-06-28"
counts:
  decisions: 2
  lessons: 3
  patterns: 2
  surprises: 2
missing_artifacts: []
---

# Phase 26 Learnings: Packaging & Extra Scoping

> Phase 26's own scope (the `[async]` extra, PEP 562 guard tests, the no-anyio CI
> job, TypeVarTuple/Unpack typing) landed cleanly. The substantive learning came
> *after* the phase, when the first CI run on the milestone branch (PR #32) went
> red — and the failure turned out to be a pre-existing Phase-25 test-harness bug
> that only surfaces on Linux. This file captures that diagnosis end-to-end so the
> elimination trail is not lost.

## Decisions

### PKG-05 mechanism is TypeVarTuple/Unpack, not ParamSpec
The requirement text suggested `ParamSpec`/`Concatenate`, but `ParamSpec` cannot
compile for `offload`/`cancellable_offload`: the typing spec forbids a keyword-only
parameter (`limiter`) after `*args: P.args`. The variadic forwarder is typed with
PEP 646 `TypeVarTuple` + `Unpack` instead — exactly how anyio types
`to_thread.run_sync`. Verified: keeps `_async/` at basedpyright-strict 0 errors and
now type-checks forwarded positional args.

**Rationale:** ParamSpec is the wrong tool for a dispatch chokepoint that has its
own keyword-only params; TypeVarTuple models "forward these positionals, keep my
own keywords."
**Source:** 26-RESEARCH.md, 26-02-SUMMARY.md

### The PKG-05 expect-error fixture needs a file-scoped pyright pragma to bite
`tests/test_offload_typing.py` pins the tightening with `# pyright:
ignore[reportArgumentType]` comments that must become *unnecessary* if the
signature regresses. That only triggers a failure when
`reportUnnecessaryTypeIgnoreComment` is enabled — which strict mode does NOT enable.
Enabling it project-wide surfaced 14 pre-existing unnecessary ignores, so it is
scoped to the fixture via a file-level `# pyright:
reportUnnecessaryTypeIgnoreComment=error` pragma. Proven: regressing the offload
signature now produces 2 errors; restoring returns to 0.

**Rationale:** an expect-error test that cannot fail is worse than no test — it
reads as coverage while guaranteeing nothing.
**Source:** 26-REVIEW.md (CR-01), 26-VERIFICATION.md

## Lessons

### A green local concurrency loop does not prove a cross-platform race is absent
The 4 failing tests (`test_cancel_in_dispatch_window_still_aborts`,
`test_fail_after_and_scope_cancel_parity`, both backends) passed **20/20 in a local
loop on macOS** yet failed **deterministically on Ubuntu CI**. Looping locally
(the standing guidance for these async tests) is necessary but not sufficient: a
race whose outcome depends on OS thread-scheduling order will not reproduce on the
platform that happens to win the race. Linux CI — plus, when needed, a throwaway
diagnostic job — is the real gate for cancel/thread-handoff timing.

**Context:** macOS scheduled the worker thread into `_block` before the cancel
fired (set survived); Linux's slower thread startup let the cancel fire first
(set was cleared on re-arm).
**Source:** PR #32 CI runs; 8eae4e1

### When you can't reproduce a CI-only failure, push a minimal diagnostic, don't guess
The first hypothesis was "the virtual clock (`MockClock`/`aiotools.VirtualClock`)
freezes past a blocked `to_thread` worker on Linux." Rather than ship a fix on that
hunch, a self-contained diagnostic was run as a temporary non-blocking CI job. It
printed `autojump_works=True` for all four cases on Linux — **disproving the
hypothesis** and redirecting the search to the stub. A fix based on the wrong
hypothesis (e.g. bumping the watchdog budget) would have masked nothing and shipped
a real bug.

**Context:** the diagnostic isolated "does the deadline fire past a blocked thread"
(`abandon_on_cancel=True`) from "does the cancel→adbc_cancel→release path work"
(`abandon_on_cancel=False`). Only the latter was broken.
**Source:** 57ec5e8 (temporary diag, since removed); PR #32 diag-clock job logs

### Type-annotation-only changes are runtime-inert — rule them out first
Phase 26's only edit to `_offload.py`/`_cancel.py` was the TypeVarTuple/Unpack
annotations. Confirming via `git diff` that the diff was annotations + imports only
(no body change, chokepoint literal frozen) cheaply excluded Phase 26 as the cause
and pointed at the newly-CI-exercised Phase-25 tests.

**Context:** the milestone branch accumulates phases 22–26 unpushed, so PR #32 was
the first CI execution of the Phase-25 EDGE cancel suite.
**Source:** git diff ae6287e^..HEAD; 8eae4e1

## Patterns

### Model an external cancel as sticky (latched) state, symmetric with close
`BlockingStubCursor.close()` was already correct: `_block()` checks `self._closed`
at entry (under the lock) before re-arming, so a close that arrives before the
worker reaches `_block` is honoured. `adbc_cancel()` was NOT symmetric — it only
did a transient `self._event.set()`, which the re-arm `self._event.clear()` wiped.
The fix latches `self._cancelled = True` under the lock in `adbc_cancel`, and
`_block` checks `if self._closed or self._cancelled:` at entry. This makes the stub
a faithful model of a real driver, whose `adbc_cancel` latches cancellation so a
cancel issued before the call enters is still observed.

**When to use:** any test double (or real component) where a "release/abort" signal
can race ahead of the consumer reaching its wait point — latch the signal under the
same lock the wait re-arms under, and check it before re-arming. A bare
`Event.set()` paired with an entry-time `Event.clear()` is a lost-wakeup waiting to
happen.
**Source:** tests/_async_harness/stubs.py; 8eae4e1

### Deterministically reproduce a scheduling race by forcing the losing order
The Linux-only hang was reproduced on macOS by calling `adbc_cancel()` *before*
starting the worker thread that calls `execute()` → `_block()`. This forces the
exact order (cancel-then-block) that Linux hit by chance, so the fix could be
proven locally without a Linux box: pre-fix it hangs, post-fix it returns at once.

**When to use:** to verify a fix for a platform-timing race you can't reproduce on
your own platform, construct the adversarial ordering explicitly rather than
relying on the scheduler.
**Source:** 8eae4e1 (deterministic repro in the fix verification)

## Surprises

### The virtual clock was fine on Linux — the prime suspect was innocent
The natural suspect for a deadline-driven test hanging only on CI was the virtual
clock not autojumping past a blocked worker thread. The diagnostic showed it
autojumps perfectly on Linux (`real≈0.001s`, `timed_out=True`). The actual culprit
was one layer down, in the stub's event re-arm.

**Impact:** avoided a wrong fix; the real bug was a one-flag asymmetry between
`close()` and `adbc_cancel()` that had been latent since Phase 23.
**Source:** PR #32 diag-clock job logs

### The CI failure was in Phase 25's tests, surfaced by Phase 26's first CI run
The phase under execution (26) was not the cause. The milestone branch had carried
the Phase-25 EDGE cancel suite unpushed; Phase 26's push was simply the first time
those tests ran on Linux. A red CI on "your" PR can belong to an earlier phase.

**Impact:** scope the investigation by *what CI newly exercised*, not by *what the
current phase changed*.
**Source:** git log; PR #32
