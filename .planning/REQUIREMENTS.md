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

## v1.3.1 Requirements (Phase 21.1 — ADBC dispatch URI-positional fix)

Surfaced by `/ultrareview` of Phase 21: `create_pool()` raises `TypeError: connect() missing 1 required positional argument: 'uri'` for any PyPI driver whose `connect()` declares `uri` as a required positional AND has `db_kwargs` in its signature. Affects Quack (Phase 21), Postgres (latent since v1.0.0), and FlightSQL (latent since v1.0.0). Closes the Phase 21 QUACK-08 verification gap.

### Dispatch fix

- [ ] **DISP-01**: `_driver_api.create_adbc_connection` detects when the target `connect()` signature has a required-positional `uri` parameter (no default) AND `db_kwargs` in parameters, and in that case pops `"uri"` from kwargs to pass positionally: `mod.connect(uri_val, db_kwargs=kwargs)`
- [ ] **DISP-02**: All other signature shapes continue to work unchanged (Snowflake optional-uri, BigQuery no-uri, SQLite no-db_kwargs)

### Verified happy paths

- [ ] **DISP-03**: `create_pool(QuackConfig(uri="quack://h:p"))` returns a working `QueuePool` when `adbc-driver-quack` is installed
- [ ] **DISP-04**: `create_pool(PostgreSQLConfig(uri="postgresql://..."))` returns a working `QueuePool` when `adbc-driver-postgresql` is installed
- [ ] **DISP-05**: `create_pool(FlightSQLConfig(uri="grpc://..."))` returns a working `QueuePool` when `adbc-driver-flightsql` is installed

### Test hardening

- [ ] **DISP-06**: `TestQuackImports`, `TestPostgreSQLImports`, and `TestFlightSQLImports` patch `dbapi.connect` with a signature-preserving stub (not bare `MagicMock`) so future regressions of this class are caught
- [ ] **DISP-07**: Add a dispatch-level unit test in `tests/test_driver_api.py` exercising the new uri-positional branch against a faked module with the affected signature shape
- [ ] **DISP-08**: Delete the duplicate `test_quack_returns_short_name` at `tests/test_drivers.py` (identical to the in-class `TestPyPIDriverPath::test_quack_missing_returns_package_name`) — `/ultrareview` bug_005
- [ ] **DISP-09**: All existing tests continue to pass (current count: 265, post-21)

### Documentation

- [ ] **DISP-10**: `docs/src/guides/custom-backends.md` updated with a brief note explaining the `_dbapi_module()` dispatch contract — when to return a module path vs `None` — so third-party backend authors don't hit the same trap
- [ ] **DISP-11**: `uv run mkdocs build --strict` passes; humanizer pass on any new prose

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

v1.3 requirements consolidated into Phase 21 (Quack Backend) per v1.0.0 retrospective lesson — single backend addition with config + tests + docs in one phase. DISP-* requirements added in Phase 21.1 to close the QUACK-08 verification gap (signature-shape regression).

| Requirement | Phase | Status |
|-------------|-------|--------|
| QUACK-01 | Phase 21 | Pending |
| QUACK-02 | Phase 21 | Pending |
| QUACK-03 | Phase 21 | Pending |
| QUACK-04 | Phase 21 | Pending |
| QUACK-05 | Phase 21 | Pending |
| QUACK-06 | Phase 21 | Pending |
| QUACK-07 | Phase 21 | Pending |
| QUACK-08 | Phase 21 | Pending |
| QUACK-09 | Phase 21 | Pending |
| QUACK-10 | Phase 21 | Pending |
| QUACK-11 | Phase 21 | Pending |
| QUACK-12 | Phase 21 | Pending |
| QUACK-13 | Phase 21 | Pending |
| QUACK-14 | Phase 21 | Pending |
| QUACK-15 | Phase 21 | Pending |
| QUACK-16 | Phase 21 | Pending |
| QUACK-17 | Phase 21 | Pending |
| QUACK-18 | Phase 21 | Pending |
| DISP-01 | Phase 21.1 | Pending |
| DISP-02 | Phase 21.1 | Pending |
| DISP-03 | Phase 21.1 | Pending |
| DISP-04 | Phase 21.1 | Pending |
| DISP-05 | Phase 21.1 | Pending |
| DISP-06 | Phase 21.1 | Pending |
| DISP-07 | Phase 21.1 | Pending |
| DISP-08 | Phase 21.1 | Pending |
| DISP-09 | Phase 21.1 | Pending |
| DISP-10 | Phase 21.1 | Pending |
| DISP-11 | Phase 21.1 | Pending |

**Coverage:**
- v1.3 requirements: 29 total (18 QUACK + 11 DISP)
- Mapped to phases: 29 ✓
- Unmapped: 0

---
*Requirements defined: 2026-05-19*
*Traceability populated: 2026-05-19*
