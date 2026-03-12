# Phase 1: Registry Infrastructure

**Status:** Not Started  
**Milestone:** v1.2.0 Plugin/Extensibility API

## Goal

Add a backend registry and manual registration API.

## Requirements

- REG-01: Backend Registry
- REG-02: Manual Registration API
- REG-03: Registry Integration
- REG-04: List Backends Utility
- TEST-INFRA-01: Dummy Backend Plugin

## Success Criteria

1. `register_backend(name, config_class, translator, driver_package, ...)` registers a new backend at runtime
2. Registered backends work identically to built-in backends
3. `list_backends()` returns all registered backends
4. Duplicate registration raises `BackendAlreadyRegisteredError`
5. Dummy backend fixture created for integration testing

## Quality Gates

- [ ] Unit tests for all new public APIs
- [ ] Integration test with manually registered backend
- [ ] `uv run basedpyright` passes
- [ ] `uv run ruff check` passes
- [ ] `uv run ruff format --check` passes

## Plans

- [ ] Plan 1: TBD
- [ ] Plan 2: TBD
