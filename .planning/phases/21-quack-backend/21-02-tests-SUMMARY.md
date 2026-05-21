---
phase: 21-quack-backend
plan: 02
subsystem: testing
tags: [pytest, pydantic, mock, quack, adbc, conditional-mock]

requires:
  - phase: 21-quack-backend (plan 01)
    provides: QuackConfig class, _quack_config module, package export, optional dep
provides:
  - TestQuackConfig (18 unit tests) covering construction, validation, kwargs shape, env loading, protocol satisfaction
  - TestQuackImports (1 semi-integration test) verifying create_pool wiring via conditional-mock pattern
  - 5 driver-path / dbapi-module tests (TestPyPIDriverPath, TestPyPIDbApiModule, module-level short-name test)
  - Regression-free full suite (265 tests passing — 241 prior + 24 new Quack tests)
affects: [21-03-docs (consumer-facing assertions locked), future-quack-tuning, regression-baseline]

tech-stack:
  added: []
  patterns:
    - "Conditional-mock test pattern (Snowflake-style) replicated for Quack"
    - "monkeypatch.setenv for env-prefix tests (no os.environ mutation)"

key-files:
  created: []
  modified:
    - tests/test_configs.py
    - tests/test_driver_imports.py
    - tests/test_drivers.py

key-decisions:
  - "Test class location: tests/test_configs.py::TestQuackConfig (per CONTEXT.md, superseding REQUIREMENTS.md QUACK-10 wording that named tests/test_quack_config.py)"
  - "Used QuackConfig(host='h', token=SecretStr('tk')) explicitly (not bare string) to match Databricks/ClickHouse precedent of constructing SecretStr at the call site in tests"
  - "Added extra explicit guard test_uri_is_plain_str_not_secretstr to lock the QUACK-locked decision that uri is plain str — not in REQUIREMENTS but specifically asserted in CONTEXT.md"
  - "Added test_to_adbc_kwargs_token_omitted_when_none as a symmetry partner to test_to_adbc_kwargs_tls_false_omitted — both omission behaviours now have explicit coverage"
  - "Added explicit token-not-embedded-in-URI assertion in test_to_adbc_kwargs_token_passthrough (locks the upstream README contract: token via kwarg, never URI)"

patterns-established:
  - "Conditional-mock for PyPI alpha drivers: if _driver_installed(pkg) -> patch pkg.dbapi.connect; else -> patch adbc_driver_manager.dbapi.connect"
  - "Pydantic env-prefix tests use monkeypatch.setenv exclusively — auto-reverts per test, no leakage risk"
  - "Test fixtures use obvious placeholder tokens (tk, envtok) with pragma allowlist secret where detect-secrets might flag"

requirements-completed: [QUACK-08, QUACK-10, QUACK-11, QUACK-12]

duration: ~8min
completed: 2026-05-19
---

# Phase 21 Plan 02: Quack Backend Tests Summary

**QuackConfig test coverage locked: 24 new tests across three files exercising URI/decomposed validation, kwargs shape (token passthrough, TLS omission, no `:None` for missing port), env-prefix loading, driver dispatch, and full-suite regression safety.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-19T21:49:00Z
- **Completed:** 2026-05-19T21:57:04Z
- **Tasks:** 4 (3 implementation + 1 verification gate)
- **Files modified:** 3

## Test Count

- **Before plan 02:** 241 tests (post plan 01 baseline)
- **After plan 02:** 265 tests passing
- **Net additions:** 24 tests (18 config + 1 semi-integration + 5 driver-path/dbapi)

## Accomplishments

- `TestQuackConfig` (18 tests) covering every locked decision from `21-CONTEXT.md`:
  - URI mode and decomposed mode construction (host-only, host+port)
  - Mutual exclusion: both modes set raises; neither set raises; port alone raises
  - Type guarantees: `uri` is plain `str` (not `SecretStr`); `token` is `SecretStr` with repr masking
  - `to_adbc_kwargs()` shape in both modes
  - Decomposed-without-port rebuilds URI as `quack://h` (no trailing `:None`)
  - Decomposed-with-port rebuilds as `quack://h:1234`
  - Token passthrough via `adbc.quack.token`; never embedded in URI
  - TLS True emits `adbc.quack.tls = "true"`; TLS False omits the key
  - Token=None omits the key (symmetry with TLS omission)
  - `QUACK_*` env-prefix loads (host, port, tls, token) via monkeypatch
  - `QUACK_POOL_SIZE` env-prefix inheritance
  - Structural Protocol satisfaction (`isinstance(c, WarehouseConfig)`)
- `TestQuackImports` semi-integration test mirroring `TestSnowflakeImports` line-for-line with conditional mock on driver presence.
- `TestPyPIDriverPath` and `TestPyPIDbApiModule` extended with four Quack tests covering both installed and missing driver paths.
- Module-level `test_quack_returns_short_name` per `21-VALIDATION.md` row 21-02-03.
- Full suite green: 265 tests pass, zero regressions from plan 01.

## Task Commits

Each task was committed atomically with `--no-verify` (parallel-executor protocol):

1. **Task 1: Add TestQuackConfig to tests/test_configs.py** — `9208e4d` (test)
2. **Task 2: Add TestQuackImports semi-integration test** — `b05b1aa` (test)
3. **Task 3: Add driver-path and dbapi-module tests** — `bead389` (test)
4. **Task 4: Full-suite regression gate** — verification-only, no commit (no code changes)

## Files Created/Modified

- `tests/test_configs.py` — added `QuackConfig` import; appended `TestQuackConfig` class (18 tests) after `TestClickHouseConfig`
- `tests/test_driver_imports.py` — added `QuackConfig` import; inserted `TestQuackImports` class (1 test) between `TestSnowflakeImports` and `TestBigQueryImports`
- `tests/test_drivers.py` — added `QuackConfig` import; appended two Quack tests to `TestPyPIDriverPath`, two to `TestPyPIDbApiModule`, and a module-level `test_quack_returns_short_name`

## Decisions Made

- **QUACK-10 file-location discrepancy resolved in favour of CONTEXT.md:** REQUIREMENTS.md QUACK-10 named `tests/test_quack_config.py`; CONTEXT.md and RESEARCH.md both supersede with `tests/test_configs.py::TestQuackConfig`. All other 12 backend configs already live in `tests/test_configs.py`, so the CONTEXT.md path preserves project consistency. Followed CONTEXT.md.
- **Extra symmetry coverage added beyond CONTEXT.md list:** `test_to_adbc_kwargs_token_omitted_when_none` was added as a symmetry partner to `test_to_adbc_kwargs_tls_false_omitted`. CONTEXT.md only explicitly listed the TLS omission case, but both fields have identical omit-when-default semantics — symmetric coverage makes the invariant harder to silently break in a future refactor.
- **Token-not-in-URI assertion added:** `test_to_adbc_kwargs_token_passthrough` additionally asserts `assert "tk" not in k["uri"]` to lock the upstream driver README contract that the token never appears in the URI. This is the security-relevant invariant from the locked decisions in CONTEXT.md.
- **Used `SecretStr("tk")` at the test call site** (not bare `"tk"`) in token-related tests to mirror the `TestDatabricksConfig` / `TestClickHouseConfig` precedent of explicit SecretStr construction.

## Deviations from Plan

None of significance — the plan was executed as written. Three additive enhancements documented above (extra symmetry test, token-not-in-URI assertion, explicit SecretStr construction in test calls) are within plan acceptance criteria and Claude's discretion under the "test case naming and assertion granularity" rule in `21-RESEARCH.md`.

**Total deviations:** 0 auto-fixes; 3 minor coverage additions within discretion bounds.
**Impact on plan:** None — all acceptance criteria met; all CONTEXT.md locked decisions covered; full suite green.

## Issues Encountered

- **Sandbox blocked `uv run pytest`:** the configured sandbox could not access `/Users/paul/.cache/uv/sdists-v9/.git`. Worked around by invoking the project venv interpreter directly: `/Users/paul/Documents/Dev/Personal/adbc-poolhouse/.venv/bin/python -m pytest …`. This is environmental, not a project issue, and does not affect committed artefacts.

## Verification Results

- `pytest tests/test_configs.py::TestQuackConfig -x -q` → **18 passed in 0.37s**
- `pytest tests/test_driver_imports.py::TestQuackImports -x -q` → **1 passed in 0.17s**
- `pytest tests/test_drivers.py -k quack -x -q` → **5 passed, 30 deselected in 0.17s**
- `pytest -x -q` (full suite) → **265 passed in 0.97s** (zero regressions; QUACK-12 confirmed)
- `grep -E 'os\.environ\[["\'']QUACK_' tests/test_configs.py` → no matches (env-leakage anti-pattern absent; T-21-06 mitigation in place)

## Threat Mitigations Confirmed

- **T-21-05 (Info Disclosure — placeholder tokens):** All test tokens use obvious placeholders (`"tk"`, `"envtok"`) with `# pragma: allowlist secret` annotations.
- **T-21-06 (Env-var leakage between tests):** Verified via grep — no `os.environ[...]` mutation in `tests/test_configs.py`; all env tests use `monkeypatch.setenv`.
- **T-21-07 (Mock bypasses real driver):** Accepted per project policy. Conditional-mock pattern mirrors `TestSnowflakeImports` precedent.

## User Setup Required

None — all changes are test-only additions.

## Next Phase Readiness

- Plan 03 (docs) can now reference `[QuackConfig][adbc_poolhouse.QuackConfig]` knowing every consumer-facing behaviour is locked by a passing test.
- No blockers for the parallel docs work in plan 03.

## Self-Check: PASSED

Verified artefacts:

- `FOUND: tests/test_configs.py` (TestQuackConfig present, 18 methods)
- `FOUND: tests/test_driver_imports.py` (TestQuackImports present)
- `FOUND: tests/test_drivers.py` (5 Quack-related tests present)
- `FOUND: 9208e4d` (Task 1 commit)
- `FOUND: b05b1aa` (Task 2 commit)
- `FOUND: bead389` (Task 3 commit)
- Full suite green: 265 tests pass

---
*Phase: 21-quack-backend*
*Plan: 02-tests*
*Completed: 2026-05-19*
