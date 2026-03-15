---
status: diagnosed
trigger: "managed_pool(dbapi_module='adbc_driver_duckdb.dbapi', db_kwargs={'path': ':memory:'}) crashes with TypeError: Connection.__init__() got an unexpected keyword argument 'db_kwargs'"
created: 2026-03-15T00:00:00Z
updated: 2026-03-15T00:00:00Z
---

## Current Focus

hypothesis: dbapi_module path blindly passes db_kwargs= to mod.connect(), but PyPI drivers have non-uniform connect() signatures
test: inspect connect() signatures of all installed PyPI ADBC drivers
expecting: DuckDB connect() does NOT accept db_kwargs as a keyword argument
next_action: return diagnosis

## Symptoms

expected: managed_pool(dbapi_module="adbc_driver_duckdb.dbapi", db_kwargs={"path": ":memory:"}) creates a pool successfully
actual: TypeError: Connection.__init__() got an unexpected keyword argument 'db_kwargs'
errors: TypeError at _driver_api.py line 80: mod.connect(db_kwargs=kwargs)
reproduction: call managed_pool(dbapi_module="adbc_driver_duckdb.dbapi", db_kwargs={"path": ":memory:"})
started: present since dbapi_module path was implemented

## Eliminated

(none -- root cause found on first hypothesis)

## Evidence

- timestamp: 2026-03-15T00:00:00Z
  checked: adbc_driver_manager.dbapi.connect() signature
  found: "(driver, uri=None, *, entrypoint=None, db_kwargs=None, conn_kwargs=None, autocommit=False)" -- accepts db_kwargs as explicit keyword
  implication: the driver_path code path works because adbc_driver_manager.dbapi.connect() has a db_kwargs parameter

- timestamp: 2026-03-15T00:00:00Z
  checked: adbc_driver_duckdb.dbapi.connect() signature
  found: "(path: str | None = None, **kwargs) -> Connection" -- NO db_kwargs parameter. **kwargs flows to Connection.__init__(), which does not accept db_kwargs
  implication: mod.connect(db_kwargs=kwargs) passes db_kwargs into **kwargs, which forwards it to Connection.__init__() as a keyword argument, causing the TypeError

- timestamp: 2026-03-15T00:00:00Z
  checked: adbc_driver_snowflake.dbapi.connect() signature
  found: "(uri=None, db_kwargs=None, conn_kwargs=None, **kwargs)" -- DOES accept db_kwargs
  implication: Snowflake works with current code; the bug is DuckDB/SQLite-specific

- timestamp: 2026-03-15T00:00:00Z
  checked: adbc_driver_postgresql.dbapi.connect() signature
  found: "(uri, db_kwargs=None, conn_kwargs=None, *, autocommit=False, **kwargs)" -- DOES accept db_kwargs
  implication: PostgreSQL works with current code

- timestamp: 2026-03-15T00:00:00Z
  checked: adbc_driver_sqlite.dbapi.connect() signature
  found: "(uri: str | None = None, **kwargs) -> Connection" -- NO db_kwargs parameter, same pattern as DuckDB
  implication: SQLite would also crash with the same bug

- timestamp: 2026-03-15T00:00:00Z
  checked: DuckDB connect() source code
  found: "def connect(path=None, **kwargs): db = adbc_driver_duckdb.connect(path); conn = AdbcConnection(db); return Connection(db, conn, **kwargs)"
  implication: DuckDB's connect() takes path as first positional arg and passes everything else to Connection.__init__(). The db_kwargs dict needs to be unpacked into the path= argument, not passed as db_kwargs=.

## Resolution

root_cause: _driver_api.py line 80 calls mod.connect(db_kwargs=kwargs) assuming all PyPI driver dbapi modules accept a db_kwargs keyword argument. But DuckDB and SQLite have different connect() signatures -- DuckDB accepts (path, **kwargs) and SQLite accepts (uri, **kwargs). The db_kwargs keyword gets forwarded via **kwargs into Connection.__init__(), which does not recognize it, causing TypeError.

fix: (not applied -- diagnosis only)
verification: (not applied -- diagnosis only)
files_changed: []
