---
phase: 03-config-layer
plan: 02
subsystem: config
tags: [pydantic-settings, pydantic, snowflake, config, jwt, oauth, secretstr]

# Dependency graph
requires:
  - phase: 03-01
    provides: BaseWarehouseConfig abstract base class and WarehouseConfig Protocol
provides:
  - SnowflakeConfig concrete config covering all Snowflake ADBC authentication methods
  - model_validator mutual exclusion pattern for private_key_path vs private_key_pem
affects:
  - 03-config-layer (plans 03-07 can reference SnowflakeConfig pattern)
  - 04-driver-detection (translates SnowflakeConfig fields to ADBC kwargs)
  - 05-pool-factory (accepts SnowflakeConfig via WarehouseConfig Protocol)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TC003 noqa suppression for Pydantic models using Path — Pydantic resolves annotations at runtime even with from __future__ import annotations"
    - "schema_ field with validation_alias='schema' and alias='schema' to avoid Pydantic internal method name collision"
    - "model_validator(mode='after') raises ValueError for cross-field mutual exclusion, wrapped into ValidationError by Pydantic"

key-files:
  created:
    - src/adbc_poolhouse/_snowflake_config.py
  modified:
    - src/adbc_poolhouse/_mssql_config.py

key-decisions:
  - "Path import kept at module level (not TYPE_CHECKING block) with # noqa: TC003 — Pydantic needs Path in the global namespace to resolve forward-reference annotations at model build time even when from __future__ import annotations is active"
  - "schema_ field alias approach: Field(validation_alias='schema', alias='schema') — maps SNOWFLAKE_SCHEMA env var to schema_ attribute without trailing underscore in env var name"

patterns-established:
  - "All Snowflake auth methods modelled as optional str/SecretStr fields (no enum) — allows new auth_type values without code changes"
  - "Boolean security/behaviour defaults follow Snowflake driver defaults: tls_skip_verify=False, ocsp_fail_open_mode=True, keep_session_alive=False"
  - "TC003 noqa pattern for stdlib types (Path) that Pydantic resolves at runtime: from pathlib import Path  # noqa: TC003"

requirements-completed: [CFG-03, CFG-04]

# Metrics
duration: 7min
completed: 2026-02-24
---

# Phase 3 Plan 02: SnowflakeConfig Summary

**SnowflakeConfig with full Snowflake ADBC field set (JWT, OAuth, MFA, Okta, PAT, WIF) and model_validator mutual exclusion on private key fields using pydantic-settings v2**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-02-24T07:18:00Z
- **Completed:** 2026-02-24T07:25:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- `SnowflakeConfig(BaseWarehouseConfig)` with `SNOWFLAKE_` env_prefix covering all Snowflake ADBC authentication methods
- Full field set: identity (account, user), password, auth_type selector (no enum — accepts any string), JWT private key fields (private_key_path as Path, private_key_pem as SecretStr, private_key_passphrase as SecretStr), OAuth token, Okta URL, WIF identity_provider, session scope (database, schema_, warehouse, role, region), connection (host, port, protocol), timeouts (login, request, client), security (tls_skip_verify, ocsp_fail_open_mode), session behaviour (keep_session_alive), telemetry (app_name, disable_telemetry, cache_mfa_token, store_temp_creds)
- `check_private_key_exclusion` model_validator raises ValidationError when both private_key_path and private_key_pem are provided simultaneously
- `schema_` field uses `Field(validation_alias='schema', alias='schema')` to map `SNOWFLAKE_SCHEMA` env var to `schema_` Python attribute, avoiding Pydantic's internal `schema` method name

## Task Commits

Each task was committed atomically:

1. **Task 1: Create _snowflake_config.py with full Snowflake ADBC parameter set** - `2799961` (feat)

## Files Created/Modified

- `src/adbc_poolhouse/_snowflake_config.py` - SnowflakeConfig with all fields, SecretStr protection, and mutual exclusion validator
- `src/adbc_poolhouse/_mssql_config.py` - Pre-existing staged file; fixed TC002 noqa for SecretStr and detect-secrets false positive on URI template docstring

## Decisions Made

- **Path stays at module level with noqa:** TC003 rule (move to TYPE_CHECKING block) conflicts with Pydantic's runtime annotation resolution. Even with `from __future__ import annotations`, Pydantic evaluates forward references when building model fields. Moving `Path` to `TYPE_CHECKING` causes `PydanticUndefinedAnnotation` at class construction. Solution: `from pathlib import Path  # noqa: TC003` — keeps the import visible at runtime while suppressing the linting rule.
- **schema_ field alias:** Used `Field(default=None, validation_alias='schema', alias='schema')` — `validation_alias` controls what pydantic-settings looks for in env (SNOWFLAKE_SCHEMA), `alias` controls serialization. The Python attribute name `schema_` avoids colliding with `BaseModel.schema()` method. Verified: `os.environ['SNOWFLAKE_SCHEMA'] = 'PUBLIC'` correctly populates `config.schema_ == 'PUBLIC'`.
- **No enum for auth_type:** Plan specified accepting auth_type as plain string without enum restriction. This allows forward compatibility if Snowflake adds new auth methods without requiring a library update.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TC003 ruff violation: Path import must stay at module level**
- **Found during:** Task 1 (post-creation prek run)
- **Issue:** Ruff TC003 flagged `from pathlib import Path` as a type-annotation-only import that should move to TYPE_CHECKING block. Attempting to move it caused `PydanticUserError: SnowflakeConfig is not fully defined` and then `PydanticUndefinedAnnotation: name 'Path' is not defined` even with `model_rebuild()`.
- **Fix:** Kept `Path` as module-level import with `# noqa: TC003` suppression. This is the correct pattern for Pydantic field types — the type must be resolvable at model construction time.
- **Files modified:** `src/adbc_poolhouse/_snowflake_config.py`
- **Verification:** All five assertions pass including `SnowflakeConfig(account='myaccount', private_key_path=Path('/tmp/key.p8'))` constructing successfully
- **Committed in:** `2799961` (Task 1 commit)

**2. [Rule 3 - Blocking] Fixed pre-existing staged _mssql_config.py blocking pre-commit**
- **Found during:** Task 1 (prek run after staging snowflake file)
- **Issue:** `_mssql_config.py` was already staged from a prior work session and failing prek: (a) TC002 on `SecretStr` import, (b) detect-secrets false positive on URI template docstring `mssql://user:pass@host[...]`
- **Fix:** Added `# noqa: TC002` to SecretStr import; added `# pragma: allowlist secret` to URI docstring to mark as intentional example template, not an actual credential
- **Files modified:** `src/adbc_poolhouse/_mssql_config.py`
- **Verification:** prek passes with both files staged
- **Committed in:** `2799961` (included in task commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 1 — ruff/Pydantic incompatibility, 1 Rule 3 — blocking pre-existing staged file)
**Impact on plan:** Both fixes necessary for correctness (Pydantic annotation resolution) and unblocking the commit (pre-existing staged file). No scope creep.

## Issues Encountered

- Ruff TCH rules conflict with Pydantic v2's runtime annotation resolution: `TC003` (stdlib) and `TC002` (third-party) assume pure type-checking use, but Pydantic evaluates all field type annotations when building the model schema. This is a known tension. The `# noqa: TCH` pattern is the correct project-level fix for Pydantic field type imports.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `SnowflakeConfig` validates the model_validator cross-field constraint pattern for all remaining warehouse configs
- `schema_` field alias approach documented for reuse in any other config needing Python-reserved attribute names
- Phase 3 Plans 03-07 (remaining warehouse configs) can follow the SnowflakeConfig pattern for their own validators
- Phase 4 (driver detection) can use `_adbc_driver_key() == 'snowflake'` to route to Snowflake ADBC driver

---

## Self-Check: PASSED

- FOUND: src/adbc_poolhouse/_snowflake_config.py
- FOUND: .planning/phases/03-config-layer/03-02-SUMMARY.md
- FOUND: commit 2799961 (Task 1 — SnowflakeConfig + MSSQLConfig pre-existing fix)

---
*Phase: 03-config-layer*
*Completed: 2026-02-24*
