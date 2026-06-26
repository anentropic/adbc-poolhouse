# Roadmap: adbc-poolhouse

## Milestones

- 🚧 **v1.4.0 Async API** — Phases 22–28 (in progress)
- ✅ **v1.3.0 Quack Backend** — Phases 21–21.1 (awaiting release)
- ✅ **v1.2.0 Plugin/Extensibility API** — Phases 16-20 (shipped 2026-03-15)
- ✅ **v1.0.0 MVP + Backend Expansion** — Phases 1-15 (shipped 2026-03-07)

## Phases

### v1.4.0 Async API

- [ ] **Phase 22: Feasibility Spike** — Benchmark GIL release for concurrent execute vs `fetch_arrow_table`; written go/no-go gating the milestone
- [ ] **Phase 23: Test Harness Foundation** — Build the `BlockingStubCursor` harness, event-gating/virtual-clock helpers, and the import-lint guard the EDGE suite rides on
- [ ] **Phase 24: Core Async Wrapper** — Offload helper, per-pool `CapacityLimiter`, `AsyncPool`/`AsyncConnection`/`AsyncCursor`, full DBAPI surface incl. `fetch_arrow_table`, plus structural EDGE coverage
- [ ] **Phase 25: Cancellation** — `adbc_cancel` wiring, shielded checkin, invalidate-on-cancel, no-leak under asyncio + trio, plus cancellation EDGE coverage
- [ ] **Phase 26: Packaging & Extra Scoping** — `[async]` extra, PEP 562 lazy import, zero-cost sync path, basedpyright-strict async typing
- [ ] **Phase 27: Dual-Backend Test Matrix** — anyio asyncio+trio parametrization across DuckDB + Snowflake cassette; Arrow-stability and limiter-stress proofs; meta-guards
- [ ] **Phase 28: Documentation** — Async usage guide (honest about I/O vs materialization), API reference, configuration/index updates, docs quality gate

<details>
<summary>✅ v1.3.0 Quack Backend (Phases 21-21.1) — awaiting release</summary>

- [x] **Phase 21: Quack Backend** — Add `QuackConfig` (config + tests + docs) for `adbc-driver-quack` (completed 2026-05-19)
- [x] **Phase 21.1: ADBC dispatch URI-positional fix** — Fix `create_pool()` dispatch for Quack/Postgres/FlightSQL (completed 2026-05-20)

</details>

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

### Phase 22: Feasibility Spike

**Goal**: Empirically validate that ADBC releases the GIL during both `execute` and `fetch_arrow_table` materialization, and record an honest go/no-go that fixes what concurrency the async layer may claim before any production code is written.
**Depends on**: Phase 21.1 (shipped sync core; the spike benchmarks the existing sync DuckDB path)
**Milestone**: v1.4.0
**Requirements**: SPIKE-01, SPIKE-02, SPIKE-03
**Success Criteria** (what must be TRUE):

  1. A reproducible DuckDB benchmark runs N concurrent slow (I/O-bound) `execute` calls from threads and reports wall-clock against ideal-parallel, demonstrating real GIL release during `execute` (SPIKE-01)
  2. A reproducible DuckDB benchmark runs N concurrent large `fetch_arrow_table` calls and reports wall-clock against ideal-parallel, quantifying whether pyarrow materialization parallelizes or serializes on the GIL (SPIKE-02)
  3. A written go/no-go document records which concurrency wins the async layer can honestly claim, what must be disclaimed, and any resulting offload-granularity guidance — and explicitly gates Phase 24 (SPIKE-03)**Plans**: 2 plans

**Wave 1**

  - [x] 22-01-PLAN.md — Kept benchmark harness + execute (SPIKE-01) and fetch_arrow_table (SPIKE-02) measurements via the real create_pool checkout path, plus a pure-function harness unit test

**Wave 2** *(blocked on Wave 1 completion)*

  - [x] 22-02-PLAN.md — SPIKE-03 go/no-go doc (8-point contract, gates Phase 24) + wheel-exclusion verification

**UI hint**: no

### Phase 23: Test Harness Foundation

**Goal**: A deterministic, backend-neutral test harness exists so every later async and EDGE test can arrange/trigger/assert without real sleeps — built before the wrappers it exercises so harness churn never blocks correctness work.
**Depends on**: Phase 22 (go/no-go confirms the async layer is worth building)
**Milestone**: v1.4.0
**Requirements**: TEST-05
**Success Criteria** (what must be TRUE):

  1. A `BlockingStubCursor` / `BlockingStubConnection` fake implements the dbapi surface (`execute`, `fetch_arrow_table`, `close`, `adbc_cancel`), blocks on a `threading.Event` released only by the test or by `adbc_cancel`, and records thread-id, call counts, `observed_cancel`, an `entered` event, and max-concurrent-in-execute (TEST-05)
  2. Event-gating and virtual-clock helpers usable under both asyncio and trio replace wall-clock sleeps in timeout/cancel tests (TEST-05)
  3. A source-scan / import-lint guard (asyncio-banned, bare-`to_thread`-without-limiter-banned in `_async/`) is exposed as a callable check the EDGE suite can assert against (TEST-05)

**Plans**: TBD
**UI hint**: no

### Phase 24: Core Async Wrapper

**Goal**: A user can run a full async query end-to-end (`create_async_pool` → `connect` → `execute` → `fetch_arrow_table` → checkin) on any of the 13 backends, with every structural pitfall except cancellation already closed: dedicated per-pool limiter, offload-everything rule, symmetric Arrow cleanup, and strict typing.
**Depends on**: Phase 23 (harness) and Phase 22 (validated GIL premise / disclaimed limits)
**Milestone**: v1.4.0
**Requirements**: CORE-01, CORE-02, CORE-03, CORE-04, APOOL-01, APOOL-02, APOOL-03, ACONN-01, ACONN-02, ACONN-03, ACONN-04, ACONN-05, ACONN-06, ACUR-01, ACUR-02, ACUR-03, ACUR-04, ACUR-05, ACUR-06, ACUR-07, EDGE-09, EDGE-10, EDGE-11, EDGE-12, EDGE-15, EDGE-17, EDGE-18, EDGE-21, EDGE-25, EDGE-26
**Success Criteria** (what must be TRUE):

  1. User can `create_async_pool(config, ...)` / `await close_async_pool(pool)` / `async with managed_async_pool(config, ...) as pool:` with the sync signature and overloads mirrored, and `await pool.connect()` yields an `AsyncConnection` whose `cursor()` returns an `AsyncCursor` synchronously (APOOL-01/02/03, ACONN-01/03)
  2. User can `await` the full DBAPI surface — `execute`, `executemany`, `fetchone`/`fetchmany`/`fetchall`, `fetch_arrow_table` (returning a `pyarrow.Table`), `commit`/`rollback`, `close` — while sync no-I/O properties (`description`/`rowcount`/`arraysize`) pass through without `await` (ACUR-01..07, ACONN-04/05)
  3. Every blocking call routes through one offload helper using each pool's dedicated `CapacityLimiter(pool_size + max_overflow)` — never the global 40-token default — with observed in-flight concurrency strictly bounded to that size under a 4× flood, tokens borrowed-then-released exactly once across success/error/cancel paths, and worker thread-ids proven off-loop (CORE-01/02, EDGE-09/10/11/12/25/26)
  4. Async checkin routes through the existing reset path so `_release_arrow_allocators` fires symmetrically; a materialized `fetch_arrow_table` result is valid after checkin; an error in `__aenter__`/post-checkout and two tasks aliasing one connection both leave `checkedout() == 0` / serialize cleanly; ADBC errors cross the thread boundary with exact type and traceback (ACONN-06, EDGE-21/18/15/17)
  5. The async layer is generic over all 13 backends via the existing `WarehouseConfig` Protocol with no per-backend async code, `import asyncio` is banned and lint-enforced in `_async/`, and basedpyright strict passes on the module (CORE-03/04)

**Plans**: TBD
**UI hint**: no

### Phase 25: Cancellation

**Goal**: A cancelled or timed-out async operation never poisons the pool — the in-flight C call is aborted via `adbc_cancel`, the worker is joined, the connection is invalidated, and cleanup completes under a shield, identically under asyncio and trio. This is the milestone's highest-risk correctness item, isolated for focused design and explicit assertions.
**Depends on**: Phase 24 (stable execute/fetch wrappers to cancel) and Phase 23 (deterministic blocking harness)
**Milestone**: v1.4.0
**Requirements**: CANCEL-01, CANCEL-02, CANCEL-03, CANCEL-04, EDGE-01, EDGE-02, EDGE-03, EDGE-04, EDGE-05, EDGE-06, EDGE-07, EDGE-19, EDGE-28, EDGE-29
**Success Criteria** (what must be TRUE):

  1. When an awaited `execute`/`fetch_arrow_table` is cancelled or times out mid-flight, `cursor.adbc_cancel()` is invoked exactly once from the loop thread, the worker is joined, the connection is invalidated, and `pool.checkedout() == 0` afterwards (CANCEL-01/02, EDGE-02)
  2. `__aexit__`/checkin is wrapped in `CancelScope(shield=True)` so the connection always returns or invalidates even when cancelled mid-cleanup, and a double-cancel during that shielded cleanup is idempotent — one `adbc_cancel`, one invalidate, one cancel exception (CANCEL-03, EDGE-04/05)
  3. A cancel delivered *before* the offload starts never touches the driver (no `execute`, no `adbc_cancel`, connection stays clean); a `move_on_after` on an already-finished op does nothing; `fail_after` timeout and explicit `scope.cancel()` are handled identically apart from the surfaced exception type (EDGE-01/06/07)
  4. The framework cancel class (`get_cancelled_exc_class()`) is never swallowed and never a raw `asyncio.CancelledError`; a trio cancel of a blocked execute *does* run `adbc_cancel` + invalidate; the `(adbc_cancel_count, invalidate_count, checkedout_after)` tuple is equal under asyncio and trio (CANCEL-04, EDGE-03/28/29)
  5. An `ExceptionGroup`/`except*` from a task group preserves the original ADBC errors, keeps cancellation distinguishable, and leaves `checkedout() == 0` (EDGE-19)

**Plans**: TBD
**UI hint**: no

### Phase 26: Packaging & Extra Scoping

**Goal**: The async surface ships behind an `[async]` extra with zero cost to sync users — `import adbc_poolhouse` succeeds and the sync suite passes with anyio uninstalled — and all async public API is fully typed under basedpyright strict. Isolated because mis-scoping the extra or the import guard is cheap to fix here and expensive to discover in the field.
**Depends on**: Phase 25 (module structure frozen once cancellation lands, so import guards are stable)
**Milestone**: v1.4.0
**Requirements**: PKG-01, PKG-02, PKG-03, PKG-04, PKG-05
**Success Criteria** (what must be TRUE):

  1. An `[async]` optional-dependency extra adds `anyio>=4.0.0` and nothing else, and `[all]` includes it (PKG-01)
  2. `import adbc_poolhouse` succeeds with anyio not installed via a PEP 562 `__getattr__` lazy import, and accessing an async symbol without anyio raises a clear `ImportError` naming the `[async]` extra (PKG-02/03)
  3. A CI job runs the existing sync test suite with anyio uninstalled and passes, proving there is no hard async dependency (PKG-04)
  4. All async public API is fully typed under basedpyright strict, using `ParamSpec`/`Concatenate` to mirror the sync overloads (PKG-05)

**Plans**: TBD
**UI hint**: no

### Phase 27: Dual-Backend Test Matrix

**Goal**: The whole async layer is proven backend-generic and backend-neutral — every async test runs under asyncio and trio across DuckDB (in-proc) and the Snowflake cassette, with Arrow-memory stability and limiter-sizing stress proven and the no-asyncio meta-guards enforced. Last in the build sequence because it depends on the full surface being stable.
**Depends on**: Phase 26 (packaging) and Phases 24–25 (full async surface + cancellation)
**Milestone**: v1.4.0
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, EDGE-27, EDGE-30
**Success Criteria** (what must be TRUE):

  1. The async suite runs parametrized over asyncio and trio via `@pytest.mark.anyio`, exercised against DuckDB (in-proc) and Snowflake (pytest-adbc-replay cassette), proving one async layer covers backends generically (TEST-01/02)
  2. An Arrow memory-stability test confirms no allocator growth across many async cursor lifecycles (TEST-03)
  3. A limiter-sizing stress test confirms no deadlock or starvation when concurrency exceeds `pool_size` (TEST-04)
  4. A meta-test asserts every async test is parametrized over both backends with no `@pytest.mark.asyncio` and no `asyncio` import in the async test package, and timeout/cancel tests use a virtual clock or event gating with no positive-duration `sleep` (source-scan enforced) (EDGE-27/30)

**Plans**: TBD
**UI hint**: no

### Phase 28: Documentation

**Goal**: Async usage is fully documented and the docs quality gate passes — an honest usage guide (distinguishing I/O-bound wins from materialization-bound limits per the Phase 22 findings), complete API reference, and configuration/index updates. This is the consolidation point for docs, though per-phase docstrings are expected throughout the milestone.
**Depends on**: Phase 27 (full, confirmed behaviour + Phase 22 benchmark results to write honestly)
**Milestone**: v1.4.0
**Requirements**: DOCS-01, DOCS-02, DOCS-03, DOCS-04
**Success Criteria** (what must be TRUE):

  1. An async usage guide shows `create_async_pool` → `connect` → `execute` → `fetch_arrow_table` → checkin, honest about I/O-bound vs materialization-bound concurrency per the SPIKE findings (DOCS-01)
  2. The API reference documents `AsyncPool`, `AsyncConnection`, `AsyncCursor`, and the three entry-point functions with Google-style docstrings (Args/Returns/Raises + Example) (DOCS-02)
  3. The configuration and index pages list the `[async]` extra and the async entry points (DOCS-03)
  4. `uv run mkdocs build --strict` passes and a humanizer pass is applied to all new or substantially rewritten prose (DOCS-04)

**Plans**: TBD
**UI hint**: no

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

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 22. Feasibility Spike | v1.4.0 | 2/2 | Complete   | 2026-06-26 |
| 23. Test Harness Foundation | v1.4.0 | 0/0 | Not started | - |
| 24. Core Async Wrapper | v1.4.0 | 0/0 | Not started | - |
| 25. Cancellation | v1.4.0 | 0/0 | Not started | - |
| 26. Packaging & Extra Scoping | v1.4.0 | 0/0 | Not started | - |
| 27. Dual-Backend Test Matrix | v1.4.0 | 0/0 | Not started | - |
| 28. Documentation | v1.4.0 | 0/0 | Not started | - |
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
</content>
</invoke>
