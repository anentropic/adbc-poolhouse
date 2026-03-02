---
phase: 12-clickhouse-backend
plan: "01"
subsystem: database
tags: [clickhouse, pydantic, pydantic-settings, adbc, columnar, foundry]

# Dependency graph
requires:
  - phase: 11-foundry-tooling-and-mysql-backend
    provides: MySQLConfig and translate_mysql() patterns used as reference
  - phase: 09-infrastructure-and-databricks-fix
    provides: URI-first decomposed-field pattern and ConfigurationError dual-inherit
  - phase: 03-config-layer
    provides: BaseWarehouseConfig base class
provides:
  - ClickHouseConfig Pydantic BaseSettings model (src/adbc_poolhouse/_clickhouse_config.py)
  - translate_clickhouse() pure translator function (src/adbc_poolhouse/_clickhouse_translator.py)
  - TestClickHouseConfig (13 tests) in tests/test_configs.py
  - TestClickHouseTranslator (10 tests) in tests/test_translators.py
affects: [12-02, 12-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ClickHouse decomposed mode uses direct kwargs (username/host/port/password/database), not a URI string — distinct from MySQL Go DSN approach"
    - "username field (not user) — Columnar ClickHouse driver kwarg; wrong key causes silent auth failure"
    - "Port 8123 default — HTTP interface, not 9000 native protocol"
    - "Optional database in decomposed mode — ClickHouse only requires host+username, unlike MySQL requiring host+user+database"

key-files:
  created:
    - src/adbc_poolhouse/_clickhouse_config.py
    - src/adbc_poolhouse/_clickhouse_translator.py
  modified:
    - tests/test_configs.py
    - tests/test_translators.py

key-decisions:
  - "ClickHouseConfig decomposed mode requires only host+username (not database) — ClickHouse default database is 'default'; database is truly optional"
  - "translate_clickhouse() returns individual kwargs dict in decomposed mode, not a URI string — Columnar ClickHouse driver accepts kwargs directly unlike MySQL which uses Go DSN"
  - "Field name is 'username' not 'user' — confirmed from columnar-tech/adbc-quickstarts; using 'user' causes silent auth failure"

patterns-established:
  - "ClickHouseConfig: model exactly on MySQLConfig except username vs user, port 8123, and database optional in decomposed guard"
  - "translate_clickhouse: URI-first, then direct kwargs (not URI string) in decomposed mode"

requirements-completed: [CH-01, CH-02]

# Metrics
duration: 3min
completed: 2026-03-02
---

# Phase 12 Plan 01: ClickHouseConfig and translate_clickhouse() Summary

**ClickHouseConfig Pydantic BaseSettings with CLICKHOUSE_* env prefix and translate_clickhouse() returning direct kwargs dict (not URI) in decomposed mode**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-02T09:49:07Z
- **Completed:** 2026-03-02T09:52:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- ClickHouseConfig with uri/host/username/password/database/port fields, model_validator guard, and CLICKHOUSE_* env prefix
- translate_clickhouse() supporting URI passthrough and direct-kwargs decomposed mode (no URI construction)
- 23 new tests (13 config + 10 translator), all passing alongside 184 total passing tests
- Field name 'username' (not 'user') enforced — critical for Columnar driver compatibility

## Task Commits

Each task was committed atomically:

1. **Task 1: ClickHouseConfig class** - `b531a66` (feat)
2. **Task 2: translate_clickhouse() function** - `0c80606` (feat)

_Note: TDD RED+GREEN combined in one commit per task — basedpyright strict mode (includes tests/) fails on unknown imports; RED-only commit blocked by pre-commit hooks (established pattern from Phase 05)_

## Files Created/Modified

- `src/adbc_poolhouse/_clickhouse_config.py` - ClickHouseConfig BaseSettings subclass with validation guard
- `src/adbc_poolhouse/_clickhouse_translator.py` - translate_clickhouse() pure translator function
- `tests/test_configs.py` - Added TestClickHouseConfig (13 tests)
- `tests/test_translators.py` - Added TestClickHouseTranslator (10 tests)

## Decisions Made

- ClickHouseConfig decomposed guard requires only `host` AND `username` — database is optional (ClickHouse's "default" database is used implicitly)
- translate_clickhouse() returns `{"username": ..., "host": ..., "port": str, ...}` in decomposed mode — Columnar ClickHouse driver takes these as direct kwargs, unlike MySQL which needs a Go DSN URI string
- Field named `username` not `user` — confirmed from columnar-tech/adbc-quickstarts; passing `user` causes silent auth failure with no error raised

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

- ruff E501 (line too long) on the test_uri_mode_constructs line in test_configs.py — ruff-format auto-reformatted on first prek run; re-staged and second prek run was clean.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- ClickHouseConfig and translate_clickhouse() are self-contained, importable without any ADBC driver
- Ready for Plan 02: wiring into __init__.py, _translators.py dispatcher, and _drivers.py detection
- Ready for Plan 03: config and translator tests plus integration tests

---
*Phase: 12-clickhouse-backend*
*Completed: 2026-03-02*
