---
status: testing
phase: 01-driver-import-semi-integration-tests
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md]
started: 2026-03-12T09:45:00Z
updated: 2026-03-12T09:45:00Z
---

## Current Test

number: 3
name: Install All Drivers Recipe Works
expected: |
  Running `just install-all-drivers` installs all 12 drivers (6 PyPI + 6 Foundry) without errors
awaiting: user response

## Tests

### 1. All 12 Backend Tests Pass
expected: Running `uv run pytest tests/test_driver_imports.py -v` shows all 12 tests pass (one per backend)
result: pass

### 2. Install All Drivers Recipe Exists
expected: Running `just --list` shows `install-all-drivers` as an available recipe
result: pass

### 3. Install All Drivers Recipe Works
expected: Running `just install-all-drivers` installs all 12 drivers (6 PyPI + 6 Foundry) without errors
result: pending

## Summary

total: 3
passed: 2
issues: 0
pending: 1
skipped: 0

## Gaps

[none yet]
