---
status: passed
phase: 26-packaging-extra-scoping
source: [26-VERIFICATION.md]
started: 2026-06-28T11:05:00Z
updated: 2026-06-28T12:30:00Z
---

## Current Test

number: 1
name: sync-no-anyio CI job is green on a real GitHub Actions run
expected: |
  On a pushed commit (or PR), the `Sync suite without anyio` job in
  .github/workflows/ci.yml is green: the `Assert anyio is genuinely absent` step
  exits 0 (find_spec('anyio') is None) and the pytest step passes with tests/async
  and tests/_async_harness deselected. The existing `quality` matrix job also stays
  green under the relocked uv.lock.
awaiting: none — passed on PR #32 (run 28319876419)

## Tests

### 1. sync-no-anyio CI job is green on a real GitHub Actions run
expected: The `Sync suite without anyio` job passes on GitHub Actions — anyio-absent assertion exits 0, sync pytest passes, and `quality` stays green under the relocked uv.lock.
result: passed — PR #32 run 28319876419: Quality gates (3.11 + 3.14), Sync suite without anyio, and coverage all green. (First push exposed a pre-existing Phase-25 harness lost-wakeup in tests/async/test_edge_cancel_depth.py — fixed in commit 8eae4e1 by latching sticky cancel state in BlockingStubCursor; unrelated to Phase 26's annotation-only offload change.)

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
