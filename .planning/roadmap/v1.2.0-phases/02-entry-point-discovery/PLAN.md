# Phase 2: Entry Point Discovery

**Status:** Not Started  
**Milestone:** v1.2.0 Plugin/Extensibility API  
**Depends on:** Phase 1

## Goal

Auto-discover 3rd party backends via Python entry points.

## Requirements

- EP-01: Entry Point Group Definition
- EP-02: Lazy Discovery
- EP-03: Error Handling
- TEST-INFRA-02: CI Integration
- TEST-INFRA-03: Malformed Plugin Fixtures

## Success Criteria

1. 3rd party packages can declare backends via `[project.entry-points."adbc_poolhouse.backends"]`
2. Entry points are discovered lazily on first `create_pool()` call
3. Entry point load failures produce clear error messages
4. CI installs dummy backend and runs integration tests
5. Malformed plugin fixtures verify graceful error handling

## Quality Gates

- [ ] Unit tests for entry point discovery logic
- [ ] Integration test with installed dummy backend
- [ ] Integration tests with malformed plugin fixtures
- [ ] `uv run basedpyright` passes
- [ ] `uv run ruff check` passes
- [ ] `uv run ruff format --check` passes

## Plans

- [ ] Plan 1: TBD
- [ ] Plan 2: TBD
