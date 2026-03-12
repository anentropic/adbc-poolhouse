# Phase 2: Registry Infrastructure

**Status:** Complete  
**Milestone:** v1.2.0 Plugin/Extensibility API

## Goal

Add a backend registry and manual registration API.

## Requirements

- REG-01: Backend Registry
- REG-02: Manual Registration API
- REG-03: Registry Integration
- TEST-INFRA-01: Dummy Backend Plugin

**Deferred:**
- REG-04: List Backends Utility — deferred to future (no clear use case, can add later if needed)

## Success Criteria

1. `register_backend(name, config_class, translator, driver_package, ...)` registers a new backend at runtime
2. Registered backends work identically to built-in backends
3. Duplicate registration raises `BackendAlreadyRegisteredError`
4. Dummy backend fixture created for integration testing

## Quality Gates

- [x] Unit tests for all new public APIs
- [x] Integration test with manually registered backend
- [x] `uv run basedpyright` passes
- [x] `uv run ruff check` passes
- [x] `uv run ruff format --check` passes

## Plans

- [x] Plan 1: Backend Registry Core — exceptions, registration API, dummy backend fixture
- [x] Plan 2: Registry Integration — dispatch replacement, lazy registration, public API exports
