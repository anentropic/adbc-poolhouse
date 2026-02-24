---
phase: 03-config-layer
plan: 04
subsystem: config
tags: [pydantic-settings, pydantic, databricks, redshift, trino, foundry, config]

# Dependency graph
requires:
  - phase: 03-config-layer/03-01
    provides: BaseWarehouseConfig abstract base class and WarehouseConfig Protocol
provides:
  - DatabricksConfig for Columnar ADBC Databricks driver (PAT and OAuth U2M/M2M)
  - RedshiftConfig for Columnar ADBC Redshift driver (provisioned and serverless)
  - TrinoConfig for Columnar ADBC Trino driver (URI-based and decomposed fields)
affects:
  - 03-config-layer (plans 05-07 for remaining backends)
  - 04-driver-detection (translates Foundry config fields to ADBC kwargs)
  - 05-pool-factory (accepts WarehouseConfig Protocol including Foundry backends)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - SecretStr field alone from pydantic requires # noqa: TC002 (pydantic needs runtime type, TYPE_CHECKING breaks model definition)
    - schema_ field uses Field(validation_alias="schema", alias="schema") to map WAREHOUSE_SCHEMA env var without trailing underscore
    - Multi-line class docstrings start on second line after opening triple-quote (D213 enforcement by ruff)

key-files:
  created:
    - src/adbc_poolhouse/_databricks_config.py
    - src/adbc_poolhouse/_redshift_config.py
    - src/adbc_poolhouse/_trino_config.py
  modified: []

key-decisions:
  - "SecretStr sole pydantic import uses # noqa: TC002 — TYPE_CHECKING breaks pydantic model build (PydanticUserError: class-not-fully-defined); validated on Python 3.14 / pydantic v2"
  - "DatabricksConfig.uri is SecretStr (URI may embed token in path); RedshiftConfig.uri is plain str (credentials are separate IAM fields)"
  - "TrinoConfig.ssl defaults to True — production-safe default matching Columnar driver; ssl_verify also defaults True"

patterns-established:
  - "Foundry-distributed driver configs are fully constructible with zero driver import — only pydantic-settings required"
  - "When SecretStr is the sole pydantic import in a file: add # noqa: TC002 to suppress ruff TC002 (moving to TYPE_CHECKING breaks pydantic v2 field resolution)"

requirements-completed: [CFG-06]

# Metrics
duration: 10min
completed: 2026-02-24
---

# Phase 3 Plan 04: Foundry Backend Configs (Databricks, Redshift, Trino) Summary

**Databricks, Redshift, and Trino pydantic-settings configs with SecretStr credential fields, URI-primary and decomposed field designs, all constructible with no driver installed**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-02-24T06:23:03Z
- **Completed:** 2026-02-24T06:33:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `DatabricksConfig` with DATABRICKS_ env_prefix, PAT (`token: SecretStr`) and OAuth M2M (`client_secret: SecretStr`) field decomposition, URI-as-SecretStr (may embed token in path), and `schema_` alias pattern
- `RedshiftConfig` with REDSHIFT_ env_prefix, provisioned cluster and serverless fields, IAM auth (`aws_secret_access_key: SecretStr`), plain `uri: str` (no credential embedding — IAM fields are separate)
- `TrinoConfig` with TRINO_ env_prefix, URI-based and decomposed field connection, `password: SecretStr`, `ssl=True`/`ssl_verify=True` safe defaults, and `schema_` alias pattern
- All three configs are instances of `WarehouseConfig` Protocol with `pool_size=5` inherited default

## Task Commits

Each task was committed atomically:

1. **Task 1: Create _databricks_config.py and _redshift_config.py** - `bcb792c` (feat)
2. **Task 2: Create _trino_config.py** - `b0151a7` (feat)

## Files Created/Modified

- `src/adbc_poolhouse/_databricks_config.py` - DatabricksConfig with PAT/OAuth auth fields, uri/token/client_secret as SecretStr, schema_ alias
- `src/adbc_poolhouse/_redshift_config.py` - RedshiftConfig with provisioned/serverless cluster support, aws_secret_access_key as SecretStr
- `src/adbc_poolhouse/_trino_config.py` - TrinoConfig with uri+decomposed fields, password as SecretStr, ssl=True default, schema_ alias

## Decisions Made

- **SecretStr import requires `# noqa: TC002`:** When `SecretStr` is the only import from pydantic (as in `_redshift_config.py`), ruff's TC002 rule flags it for moving to `TYPE_CHECKING`. Attempting this breaks pydantic v2 with `PydanticUserError: class-not-fully-defined`. Resolution: keep the runtime import and add `# noqa: TC002`. Files that import multiple pydantic symbols (Field + SecretStr) are not flagged because `Field` is unconditionally needed at runtime.

- **DatabricksConfig.uri as SecretStr vs RedshiftConfig.uri as str:** Databricks URIs embed the PAT token in the path (`databricks://token:<TOKEN>@<host>:443/<http-path>`), so `uri` is `SecretStr` to prevent token leakage in logs and repr. Redshift URIs may contain a password but the standard IAM auth approach uses separate `aws_access_key_id` / `aws_secret_access_key` fields — `uri` is plain `str` per the RESEARCH.md design.

- **schema_ alias resolution:** `Field(default=None, validation_alias="schema", alias="schema")` — consistent with SnowflakeConfig pattern (03-02). The Python attribute is `schema_` to avoid Pydantic's own `schema` class method name collision.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added `# noqa: TC002` to `_redshift_config.py` SecretStr import**
- **Found during:** Task 1 (prek pre-commit hook run)
- **Issue:** ruff TC002 flagged `from pydantic import SecretStr` as moveable to `TYPE_CHECKING`. Attempted fix (moved to TYPE_CHECKING) caused `PydanticUserError: RedshiftConfig is not fully defined; you should define SecretStr, then call RedshiftConfig.model_rebuild()`.
- **Fix:** Reverted TYPE_CHECKING approach; added `# noqa: TC002` inline to suppress ruff while keeping the runtime import pydantic requires.
- **Files modified:** `src/adbc_poolhouse/_redshift_config.py`
- **Verification:** `RedshiftConfig()` constructs successfully; `aws_secret_access_key` is SecretStr with env var
- **Committed in:** `bcb792c` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed D213 docstring formatting in all three files**
- **Found during:** Task 1 and Task 2 (prek ruff-format hook)
- **Issue:** Class docstrings used `"""Summary on first line` style but project enforces D213 (summary on second line).
- **Fix:** Changed to `"""\n    Summary` pattern — consistent with `_duckdb_config.py`. ruff-format auto-applied the quote style normalization (single to double quotes).
- **Files modified:** all three config files
- **Verification:** `uv run ruff check` passes on all three files
- **Committed in:** `bcb792c` (Task 1 commit), `b0151a7` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (Rule 1 — linting/formatting enforcement)
**Impact on plan:** Both auto-fixes required for pre-commit compliance. No scope creep. Core design intent fully preserved.

## Issues Encountered

- First prek run on `_trino_config.py` failed due to stash conflict: ruff-format modified the file while detect-secrets was running with a stash active, causing a patch restore conflict. Resolved by restaging the ruff-format-normalized file and running prek again — second run passed cleanly.

## User Setup Required

None - no external service configuration required. All Foundry backends are constructible with no driver installed.

## Next Phase Readiness

- `DatabricksConfig`, `RedshiftConfig`, and `TrinoConfig` available for plans 05-07 (remaining warehouse configs: MSSQL, Teradata, BigQuery etc.)
- All three implement `WarehouseConfig` Protocol and `_adbc_driver_key()` — ready for Phase 4 (driver detection)
- `# noqa: TC002` pattern established for single-SecretStr pydantic files — apply to any future config with this pattern

---
## Self-Check: PASSED

- FOUND: src/adbc_poolhouse/_databricks_config.py
- FOUND: src/adbc_poolhouse/_redshift_config.py
- FOUND: src/adbc_poolhouse/_trino_config.py
- FOUND: commit bcb792c (Task 1)
- FOUND: commit b0151a7 (Task 2)

---
*Phase: 03-config-layer*
*Completed: 2026-02-24*
