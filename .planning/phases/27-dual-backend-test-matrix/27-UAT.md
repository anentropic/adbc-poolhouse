---
status: passed
phase: 27-dual-backend-test-matrix
source: [27-VERIFICATION.md]
started: 2026-06-28T14:22:02Z
updated: 2026-07-01T00:00:00Z
---

## Current Test

number: 1
name: Linux CI cross-platform gate — dual-backend `quality` job green
expected: |
  After pushing branch `gsd/v1.4.0-async-api`, the dual-backend `quality` CI job
  (full suite including `tests/async/`, run under asyncio and trio across DuckDB +
  Snowflake cassette) passes GREEN on Linux. A green local ×20 loop on macOS does
  NOT prove this — the Phase 24–26 landmine is that async cancel races can pass
  20/20 on macOS but hang on Linux CI. The new `tests/async/test_meta_guard.py` is
  collected by `quality` and correctly excluded from the `sync-no-anyio` job.
awaiting: none — resolved 2026-07-01 (CI run 28481988002 green on Linux)

## Tests

### 1. Linux CI cross-platform gate — dual-backend `quality` job green
expected: |
  `git push origin gsd/v1.4.0-async-api`, then the dual-backend `quality` CI job is
  GREEN on Linux (full suite incl. tests/async/ under asyncio+trio × DuckDB+Snowflake
  cassette). The `sync-no-anyio` job also stays green (it ignores tests/async and
  tests/_async_harness — the phase 27 tests require anyio at collection).
result: [passed] — GitHub Actions run 28481988002 (push, branch gsd/v1.4.0-async-api): 'Quality gates' 3.11 + 3.14 green on Linux (full suite incl. tests/async under asyncio+trio × DuckDB+Snowflake cassette); 'Sync suite without anyio' green.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
