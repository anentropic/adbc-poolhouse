---
phase: 11-foundry-tooling-and-mysql-backend
plan: 02
subsystem: database
tags: [mysql, adbc, foundry, pydantic, translator, go-dsn]

requires:
  - phase: 11-01
    provides: dbc CLI install recipes (prerequisite for testing MySQL driver)
provides:
  - MySQLConfig Pydantic BaseSettings class with URI and decomposed field modes
  - translate_mysql() pure function producing Go DSN format URIs
  - MYSQL_ env prefix for all config fields
affects:
  - 11-03-PLAN (wiring MySQLConfig into _drivers.py, _translators.py, __init__.py)

tech-stack:
  added: []
  patterns:
    - URI-first decomposed-field pattern (mirrors DatabricksConfig)
    - quote(safe='') for URL-encoding credentials — not quote_plus()
    - Go DSN format user:pass@tcp(host:port)/db (confirmed from adbc-quickstarts)

key-files:
  created:
    - src/adbc_poolhouse/_mysql_config.py
    - src/adbc_poolhouse/_mysql_translator.py
  modified: []

key-decisions:
  - "No _adbc_entrypoint() override — MySQL Foundry driver uses manifest resolution (base class returns None)"
  - "password is optional in decomposed mode — MySQL supports passwordless connections"
  - "quote(safe='') not quote_plus() — quote_plus encodes spaces as '+' which corrupts passwords"
  - "Omit :pass segment entirely when password is None — Go DSN format user@tcp(...) without colon"

requirements-completed:
  - MYSQL-01
  - MYSQL-02

duration: 1min
completed: 2026-03-01
---

# Phase 11 Plan 02: MySQLConfig and translate_mysql() Summary

**MySQLConfig Pydantic BaseSettings class and translate_mysql() pure function implementing URI and decomposed modes with Go DSN output format**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-01T17:19:46Z
- **Completed:** 2026-03-01T17:21:06Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `MySQLConfig` with URI mode (full connection string) and decomposed mode (host/user/database required, password optional, port defaults to 3306)
- `translate_mysql()` constructs Go DSN `user:pass@tcp(host:port)/db`; omits `:pass` when password is None
- Password URL-encoded with `urllib.parse.quote(safe='')` — correctly encodes `+`, `=`, `/`, `@`
- Both files pass `basedpyright` strict mode and `ruff check` with zero errors

## Task Commits

1. **Task 1: Create _mysql_config.py** - `fca867c` (feat)
2. **Task 2: Create _mysql_translator.py** - `48b434e` (feat)

## Files Created/Modified
- `src/adbc_poolhouse/_mysql_config.py` - MySQLConfig class with model_validator and MYSQL_ env prefix
- `src/adbc_poolhouse/_mysql_translator.py` - translate_mysql() pure function

## Decisions Made
- No `_adbc_entrypoint()` override — Foundry MySQL driver uses manifest resolution; base class returns None which is correct
- `password` optional in decomposed mode — MySQL supports passwordless logins
- `quote(safe='')` not `quote_plus()` — `quote_plus` encodes spaces as `+`, corrupting passwords with literal `+` characters
- `:pass` segment omitted entirely when password is None — Go DSN `user@tcp(...)` format without colon separator

## Deviations from Plan

None - plan executed exactly as written. ruff format reformatted the `check_connection_spec` multi-line conditional; pre-commit hook auto-fixed on re-stage.

## Issues Encountered

None.

## Next Phase Readiness
- `_mysql_config.py` and `_mysql_translator.py` ready to be wired into `_drivers.py`, `_translators.py`, and `__init__.py` in Plan 11-03
- All behavior verified inline; tests added in Plan 11-03

---
*Phase: 11-foundry-tooling-and-mysql-backend*
*Completed: 2026-03-01*
