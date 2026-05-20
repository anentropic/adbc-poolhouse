# Roadmap: adbc-poolhouse

## Milestones

- 🚧 **v1.3.0 Quack Backend** — Phases 21–21.1 (awaiting release)
- ✅ **v1.2.0 Plugin/Extensibility API** — Phases 16-20 (shipped 2026-03-15)
- ✅ **v1.0.0 MVP + Backend Expansion** — Phases 1-15 (shipped 2026-03-07)

## Phases

### v1.3.0 Quack Backend

- [x] **Phase 21: Quack Backend** — Add `QuackConfig` (config + tests + docs) for `adbc-driver-quack` (completed 2026-05-19)
- [x] **Phase 21.1: ADBC dispatch URI-positional fix** — Fix `create_pool()` dispatch for Quack/Postgres/FlightSQL (completed 2026-05-20)

<details>
<summary>✅ v1.2.0 Plugin/Extensibility API (Phases 16-20) — SHIPPED 2026-03-15</summary>

- [x] Phase 16: Driver Import Semi-Integration Tests (2/2 plans) — completed 2026-03-12
- [x] Phase 17: Registry Infrastructure (2/2 plans) — completed 2026-03-12
- [x] Phase 17.5: Translator Consolidation (5/5 plans) — completed 2026-03-14
- [x] Phase 18: Registration Removal (3/3 plans) — completed 2026-03-15
- [x] Phase 19: Raw create_pool Overload (4/4 plans) — completed 2026-03-15
- [x] Phase 20: Protocol Documentation (1/1 plan) — completed 2026-03-15

</details>

<details>
<summary>✅ v1.0.0 MVP + Backend Expansion (Phases 1-15) — SHIPPED 2026-03-07</summary>

- [x] Phase 1: Pre-flight Fixes (1/1 plans) — completed 2026-02-23
- [x] Phase 2: Dependency Declarations (2/2 plans) — completed 2026-02-23
- [x] Phase 3: Config Layer (7/7 plans) — completed 2026-02-24
- [x] Phase 4: Translation and Driver Detection (5/5 plans) — completed 2026-02-24
- [x] Phase 5: Pool Factory and DuckDB Integration (2/2 plans) — completed 2026-02-24
- [x] Phase 6: Snowflake Integration (1/1 plan) — superseded by Phase 15
- [x] Phase 7: Documentation and PyPI Publication (5/5 plans) — completed 2026-02-27
- [x] Phase 8: Review and Improve Docs (6/6 plans) — completed 2026-02-28
- [x] Phase 9: Infrastructure and Databricks Fix (2/2 plans) — completed 2026-03-01
- [x] Phase 10: SQLite Backend (4/4 plans) — completed 2026-03-01
- [x] Phase 11: Foundry Tooling and MySQL Backend (4/4 plans) — completed 2026-03-01
- [x] Phase 12: ClickHouse Backend (4/4 plans) — completed 2026-03-02
- [x] Phase 13: Verification and Tracking Fix (2/2 plans) — completed 2026-03-02
- [x] Phase 14: Homepage Discovery Fix (1/1 plan) — completed 2026-03-02
- [x] Phase 15: Replace Syrupy with pytest-adbc-replay (5/5 plans) — completed 2026-03-07

</details>

## Phase Details

### Phase 21: Quack Backend
**Goal**: Users can configure and pool connections to a Quack server via `QuackConfig`, with documentation matching the established per-backend pattern.
**Depends on**: Phase 20 (self-describing config architecture and Protocol contract from v1.2.0)
**Milestone**: v1.3.0
**Requirements**: QUACK-01, QUACK-02, QUACK-03, QUACK-04, QUACK-05, QUACK-06, QUACK-07, QUACK-08, QUACK-09, QUACK-10, QUACK-11, QUACK-12, QUACK-13, QUACK-14, QUACK-15, QUACK-16, QUACK-17, QUACK-18
**Success Criteria** (what must be TRUE):
  1. User can `from adbc_poolhouse import QuackConfig` and construct it with either a `uri="quack://host:port"` OR decomposed `host`/`port` fields, plus optional `token` (SecretStr) and `tls` (bool)
  2. User who passes both `uri` and `host`, or neither, gets a Pydantic validation error at construction time (mutual exclusion enforced)
  3. `create_pool(QuackConfig(...))` returns a working `QueuePool` via the existing self-describing dispatch — no changes to `_pool_factory` required — using the `adbc_driver_quack` PyPI driver
  4. `pip install adbc-poolhouse[quack]` installs `adbc-driver-quack>=0.1.0a1` and the Quack backend is then usable
  5. User can read a per-warehouse guide at `docs/src/guides/quack.md` (linked in `mkdocs.yml` nav, listed on `index.md`, and shown in the `configuration.md` table) with alpha-status warning and external project link, and `uv run mkdocs build --strict` passes
  6. Unit tests cover URI/host/port/token/tls validation paths, the semi-integration test verifies pool creation against a conditional mock target, and all 241 existing tests continue to pass
**Plans**: TBD
**UI hint**: no

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 21.1. ADBC dispatch URI-positional fix | v1.3.0 | 3/3 | Complete | 2026-05-20 |
| 21. Quack Backend | v1.3.0 | 3/3 | Complete    | 2026-05-19 |
| 16. Driver Import Semi-Integration Tests | v1.2.0 | 2/2 | Complete | 2026-03-12 |
| 17. Registry Infrastructure | v1.2.0 | 2/2 | Complete | 2026-03-12 |
| 17.5. Translator Consolidation | v1.2.0 | 5/5 | Complete | 2026-03-14 |
| 18. Registration Removal | v1.2.0 | 3/3 | Complete | 2026-03-15 |
| 19. Raw create_pool Overload | v1.2.0 | 4/4 | Complete | 2026-03-15 |
| 20. Protocol Documentation | v1.2.0 | 1/1 | Complete | 2026-03-15 |
| 1. Pre-flight Fixes | v1.0.0 | 1/1 | Complete | 2026-02-23 |
| 2. Dependency Declarations | v1.0.0 | 2/2 | Complete | 2026-02-23 |
| 3. Config Layer | v1.0.0 | 7/7 | Complete | 2026-02-24 |
| 4. Translation and Driver Detection | v1.0.0 | 5/5 | Complete | 2026-02-24 |
| 5. Pool Factory and DuckDB Integration | v1.0.0 | 2/2 | Complete | 2026-02-24 |
| 6. Snowflake Integration | v1.0.0 | 1/1 | Complete | 2026-02-24 |
| 7. Documentation and PyPI Publication | v1.0.0 | 5/5 | Complete | 2026-02-27 |
| 8. Review and Improve Docs | v1.0.0 | 6/6 | Complete | 2026-02-28 |
| 9. Infrastructure and Databricks Fix | v1.0.0 | 2/2 | Complete | 2026-03-01 |
| 10. SQLite Backend | v1.0.0 | 4/4 | Complete | 2026-03-01 |
| 11. Foundry Tooling and MySQL Backend | v1.0.0 | 4/4 | Complete | 2026-03-01 |
| 12. ClickHouse Backend | v1.0.0 | 4/4 | Complete | 2026-03-02 |
| 13. Verification and Tracking Fix | v1.0.0 | 2/2 | Complete | 2026-03-02 |
| 14. Homepage Discovery Fix | v1.0.0 | 1/1 | Complete | 2026-03-02 |
| 15. Replace Syrupy with pytest-adbc-replay | v1.0.0 | 5/5 | Complete | 2026-03-07 |

### Phase 21.1: ADBC dispatch URI-positional fix (INSERTED)

**Goal**: `create_pool()` returns a working `QueuePool` for every PyPI-driver backend (Quack, Postgres, FlightSQL) when the matching driver is installed — fixing the `TypeError: connect() missing 1 required positional argument: 'uri'` that breaks the documented quickstart.
**Depends on**: Phase 21 (Quack backend ships the surface that surfaced the bug)
**Milestone**: v1.3.0 (gap closure)
**Requirements**: DISP-01, DISP-02, DISP-03, DISP-04, DISP-05, DISP-06, DISP-07, DISP-08, DISP-09, DISP-10, DISP-11
**Success Criteria** (what must be TRUE):
  1. `_driver_api.create_adbc_connection` correctly dispatches to PyPI driver `connect()` functions whose signature has a required-positional `uri` AND `db_kwargs` in parameters — by popping `"uri"` from kwargs and passing it positionally
  2. `create_pool(QuackConfig(uri="quack://..."))` returns a working `QueuePool` when `adbc-driver-quack` is installed (closes Phase 21 QUACK-08 gap)
  3. `create_pool(PostgreSQLConfig(uri="postgresql://..."))` returns a working `QueuePool` when `adbc-driver-postgresql` is installed (latent v1.0.0 bug)
  4. `create_pool(FlightSQLConfig(uri="grpc://..."))` returns a working `QueuePool` when `adbc-driver-flightsql` is installed (latent v1.0.0 bug)
  5. Test mocks for Quack, Postgres, and FlightSQL imports use a signature-preserving stub so this regression class is caught by CI in future
  6. A dedicated `tests/test_driver_api.py` unit test exercises the new uri-positional dispatch branch against a fake module
  7. Duplicate `test_quack_returns_short_name` removed (ultrareview bug_005)
  8. All existing tests continue to pass; `uv run mkdocs build --strict` passes; humanizer pass applied to new prose
**Plans**: TBD
**UI hint**: no
