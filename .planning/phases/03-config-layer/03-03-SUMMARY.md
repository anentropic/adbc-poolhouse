---
phase: 03-config-layer
plan: 03
subsystem: config
tags: [pydantic-settings, pydantic, bigquery, postgresql, flightsql, config, grpc, tls]

# Dependency graph
requires:
  - phase: 03-01
    provides: BaseWarehouseConfig abstract base class and WarehouseConfig Protocol
provides:
  - BigQueryConfig with GCP auth fields (ADC, JSON credential file, user auth flow)
  - PostgreSQLConfig with URI-primary design (libpq connection string)
  - FlightSQLConfig with gRPC, auth, TLS, and timeout fields
affects:
  - 03-06 (__init__.py exports)
  - 04-driver-detection (translates config fields to ADBC kwargs)
  - 05-pool-factory (accepts configs via WarehouseConfig Protocol)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TC002 noqa suppression for SecretStr — Pydantic resolves BaseSettings field annotations at class-creation time, making runtime import necessary"
    - "pragma: allowlist secret for URI docstring examples containing user:password patterns"
    - "D213 docstring style: multi-line docstring summary starts on second line (auto-fixed by ruff)"

key-files:
  created:
    - src/adbc_poolhouse/_bigquery_config.py
    - src/adbc_poolhouse/_postgresql_config.py
    - src/adbc_poolhouse/_flightsql_config.py

key-decisions:
  - "PostgreSQLConfig uses URI-primary design — all libpq params (host, port, user, password, dbname, sslmode) go in URI string; no individual host/port fields"
  - "FlightSQLConfig has no required fields — uri can be None and supplied via FLIGHTSQL_URI env var"
  - "mtls_private_key and authorization_header are SecretStr — these can contain raw key material and bearer tokens"
  - "pragma: allowlist secret added to PostgreSQL docstring example (false positive on user:password pattern)"

patterns-established:
  - "URI-primary design pattern: single uri field as str | None = None, populated via env var — used by PostgreSQL and FlightSQL"
  - "No cross-field validators needed for these three configs — simpler than Snowflake"

requirements-completed: [CFG-05]

# Metrics
duration: ~15min (including orchestrator recovery after Bash permission issue)
completed: 2026-02-24
---

# Phase 3 Plan 03: BigQuery, PostgreSQL, FlightSQL Config Summary

**Three Apache ADBC backend configs completing the PyPI-available backend set: BigQueryConfig (GCP auth), PostgreSQLConfig (URI-primary), FlightSQLConfig (gRPC with TLS and timeout fields)**

## Performance

- **Duration:** ~15 min (including orchestrator recovery)
- **Completed:** 2026-02-24
- **Tasks:** 2
- **Files created:** 3

## Accomplishments

- `BigQueryConfig(BaseWarehouseConfig)` with `BIGQUERY_` env_prefix: auth_type selector (no enum), auth_credentials/client_id/client_secret/refresh_token for all GCP auth flows (ADC, JSON file, JSON string, user auth), project_id, dataset_id
- `PostgreSQLConfig(BaseWarehouseConfig)` with `POSTGRESQL_` env_prefix: URI-primary design, use_copy=True default for COPY protocol acceleration
- `FlightSQLConfig(BaseWarehouseConfig)` with `FLIGHTSQL_` env_prefix: uri, username/password/authorization_header (auth), mtls_cert_chain/mtls_private_key (mTLS), tls_root_certs/tls_skip_verify/tls_override_hostname (TLS), connect/query/fetch/update timeouts, authority/max_msg_size/with_cookie_middleware (gRPC options)

## Task Commits

1. **Task 1: Create _bigquery_config.py and _postgresql_config.py** — `f638bfe`
2. **Task 2: Create _flightsql_config.py** — `ebf97e2`

## Files Created/Modified

- `src/adbc_poolhouse/_bigquery_config.py` — BigQueryConfig with GCP auth fields; auth_credentials/client_secret/refresh_token as SecretStr
- `src/adbc_poolhouse/_postgresql_config.py` — PostgreSQLConfig with URI-primary design; pragma: allowlist secret on docstring URI example
- `src/adbc_poolhouse/_flightsql_config.py` — FlightSQLConfig with 15 fields across auth/mTLS/TLS/timeout/gRPC categories; password/authorization_header/mtls_private_key as SecretStr

## Decisions Made

- **URI-primary design for PostgreSQL:** libpq accepts all connection parameters via a single URI string. No individual host/port/user/password fields — this would duplicate libpq's own parameter system and create sync issues.
- **FlightSQLConfig no required fields:** `uri` defaults to None so the config can be constructed and then populated from FLIGHTSQL_URI env var. Same pattern as PostgreSQLConfig.uri.
- **SecretStr for mTLS private key and auth header:** mtls_private_key may contain PEM-encoded private key material; authorization_header may contain raw bearer tokens. Both must be masked in repr and logs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Auto] TC002 ruff violation: SecretStr import in BigQueryConfig**
- **Issue:** Ruff flagged `from pydantic import SecretStr` as a type-annotation-only import
- **Fix:** Added `# noqa: TC002` — Pydantic BaseSettings resolves field annotations at class-creation time; runtime import is necessary
- **Consistent with:** Pattern established in 03-05 for MSSQLConfig and TeradataConfig

**2. [Rule 3 - Blocking] detect-secrets false positive on PostgreSQL docstring**
- **Issue:** `postgresql://user:password@host:5432/dbname` in docstring triggered Basic Auth Credentials detector
- **Fix:** Added `# pragma: allowlist secret` to the docstring line
- **Consistent with:** Pattern established in 03-05 for MSSQLConfig URI docstring

**3. [Infrastructure] Agent 03-03 lost Bash access mid-execution**
- **Issue:** Subagent wrote BigQueryConfig and PostgreSQLConfig but could not commit; FlightSQLConfig not yet written
- **Recovery:** Orchestrator created FlightSQLConfig, ran ruff fixes, applied noqa/pragma annotations, committed all three files

## Issues Encountered

- Agent Bash permission issue required orchestrator recovery (not a code issue)
- D213 docstring style (ruff auto-fixed): multi-line docstring summaries should start on second line

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All three configs satisfy WarehouseConfig Protocol instanceof checks
- URI-primary pattern documented for PostgreSQL and FlightSQL
- Phase 3 Plan 06 (__init__.py) can now export BigQueryConfig, PostgreSQLConfig, FlightSQLConfig

---

## Self-Check: PASSED

- FOUND: src/adbc_poolhouse/_bigquery_config.py
- FOUND: src/adbc_poolhouse/_postgresql_config.py
- FOUND: src/adbc_poolhouse/_flightsql_config.py
- FOUND: commit f638bfe (Task 1 — BigQuery + PostgreSQL)
- FOUND: commit ebf97e2 (Task 2 — FlightSQL)

---
*Phase: 03-config-layer*
*Completed: 2026-02-24*
