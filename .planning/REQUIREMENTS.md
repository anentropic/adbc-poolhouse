# Requirements: adbc-poolhouse v1.3.0

**Milestone:** v1.3.0 — Quack Backend
**Defined:** 2026-05-19
**Core Value:** One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool in a single call.

## v1.3 Requirements

Add `QuackConfig` warehouse backend for `adbc-driver-quack` (DuckDB Quack remote protocol). Follows established Protocol-based, self-describing config pattern from v1.2.0.

### Config Class

- [ ] **QUACK-01**: `QuackConfig` class exists in `src/adbc_poolhouse/_quack_config.py`, inheriting `BaseWarehouseConfig`
- [ ] **QUACK-02**: `QuackConfig` exposes `uri: str | None`, `host: str | None`, `port: int | None`, `token: SecretStr | None`, `tls: bool = False` (URI-first with decomposed host/port fallback, matching Databricks/MySQL pattern)
- [ ] **QUACK-03**: `QuackConfig` validates that either `uri` is set OR (`host` is set, port optional) — never both, never neither (model_validator)
- [ ] **QUACK-04**: `QuackConfig.to_adbc_kwargs()` returns `{"uri": "quack://...", "adbc.quack.token": ..., "adbc.quack.tls": ...}` with `token`/`tls` keys omitted when not set
- [ ] **QUACK-05**: `QuackConfig._driver_path()` returns `"adbc_driver_quack"` (PyPI module name for `find_spec` detection)
- [ ] **QUACK-06**: `QuackConfig._dbapi_module()` returns `adbc_driver_quack.dbapi` module

### Public API

- [ ] **QUACK-07**: `QuackConfig` exported from `adbc_poolhouse.__init__`
- [ ] **QUACK-08**: `create_pool(QuackConfig(...))` returns a working `QueuePool` via the existing self-describing dispatch (no changes to `_pool_factory` required)

### Packaging

- [ ] **QUACK-09**: `pyproject.toml` adds `quack` optional dependency group: `adbc-driver-quack>=0.1.0a1` (alpha lower bound, no upper cap — matches house style)

### Tests

- [ ] **QUACK-10**: Unit tests for `QuackConfig` validation (URI-only, host-only, host+port, mutual exclusion, token/tls passthrough) in `tests/test_quack_config.py`
- [ ] **QUACK-11**: Semi-integration test verifies `create_pool(QuackConfig(...))` returns a pool with conditional mock target (matches pattern for other Foundry/PyPI backends)
- [ ] **QUACK-12**: All existing 241 tests continue to pass

### Documentation

- [ ] **QUACK-13**: `docs/src/guides/quack.md` per-warehouse guide page — covers config fields, URI scheme, token + tls usage, install instructions
- [ ] **QUACK-14**: `docs/src/guides/quack.md` includes alpha-status warning admonition and external link to https://github.com/gizmodata/adbc-driver-quack
- [ ] **QUACK-15**: `docs/src/guides/configuration.md` table updated with Quack row
- [ ] **QUACK-16**: `docs/src/index.md` backend listing updated to include Quack (listing only, no example)
- [ ] **QUACK-17**: `mkdocs.yml` nav adds `guides/quack.md` entry
- [ ] **QUACK-18**: `uv run mkdocs build --strict` passes; humanizer pass applied to new prose

## Future Requirements

None deferred for this milestone — Quack surface is small and fully addressed.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live integration test against real Quack server | No public test server; cassette replay not warranted for a single-protocol driver |
| Decomposed authentication fields (username/password) | Quack uses single token, not split credentials |
| Quack-specific connection pooling tuning | Standard `QueuePool` parameters suffice; no Quack-unique knobs identified |
| Quickstart example for Quack | User confirmed not needed on index.md |

## Traceability

To be populated by roadmapper.

| Requirement | Phase | Status |
|-------------|-------|--------|
| QUACK-01 | Phase ? | Pending |
| QUACK-02 | Phase ? | Pending |
| QUACK-03 | Phase ? | Pending |
| QUACK-04 | Phase ? | Pending |
| QUACK-05 | Phase ? | Pending |
| QUACK-06 | Phase ? | Pending |
| QUACK-07 | Phase ? | Pending |
| QUACK-08 | Phase ? | Pending |
| QUACK-09 | Phase ? | Pending |
| QUACK-10 | Phase ? | Pending |
| QUACK-11 | Phase ? | Pending |
| QUACK-12 | Phase ? | Pending |
| QUACK-13 | Phase ? | Pending |
| QUACK-14 | Phase ? | Pending |
| QUACK-15 | Phase ? | Pending |
| QUACK-16 | Phase ? | Pending |
| QUACK-17 | Phase ? | Pending |
| QUACK-18 | Phase ? | Pending |

**Coverage:**
- v1.3 requirements: 18 total
- Mapped to phases: 0
- Unmapped: 18 ⚠️ (will be mapped by roadmapper)

---
*Requirements defined: 2026-05-19*
