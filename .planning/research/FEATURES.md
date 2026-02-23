# Features Research: Python Connection Pool Libraries

**Date:** 2026-02-23
**Question:** What features do Python database connection pool libraries have? What's table stakes vs differentiating for an ADBC-specific connection pooling library targeting data warehouse workloads?
**Scope:** SQLAlchemy pool, psycopg3 ConnectionPool, asyncpg Pool, ADBC-specific examples

---

## Summary

Python connection pool libraries converge on a well-understood feature set. The table-stakes features are established and boring; every serious pool has them. The interesting question for adbc-poolhouse is not "how do we re-implement all of this" but "what is the minimal set needed given that SQLAlchemy QueuePool handles the hard parts, and what unique value comes from the ADBC + data warehouse context?"

The design already made the right call: delegate pool mechanics to SQLAlchemy QueuePool, own the config + translation + driver detection layers. This document maps the full feature space so requirements can make explicit keep/cut decisions.

---

## Library Survey

### SQLAlchemy Pool (`sqlalchemy.pool`)

SQLAlchemy ships multiple pool implementations behind a common interface:

**Pool types:**
- `QueuePool` — thread-safe FIFO pool with configurable size and overflow; the default for most dialects
- `NullPool` — no pooling; open/close on every checkout (useful for per-request or serverless)
- `StaticPool` — single reused connection (in-memory databases, testing)
- `AssertionPool` — raises if more than one connection checked out at a time (test enforcement)
- `AsyncAdaptedQueuePool` — async-compatible version of QueuePool

**Core configuration knobs:**
| Parameter | Purpose |
|-----------|---------|
| `pool_size` | Steady-state idle connections maintained |
| `max_overflow` | Burst capacity above `pool_size` (total max = `pool_size + max_overflow`) |
| `timeout` | Seconds to block when pool is exhausted before raising `TimeoutError` |
| `recycle` | Seconds before a connection is proactively replaced (avoids server-side idle timeouts and token expiry) |
| `pre_ping` | Issue a lightweight "is this connection still alive?" check on checkout |
| `use_lifo` | Last-in-first-out checkout (reduces idle connections under low load) |
| `reset_on_return` | `'rollback'`, `'commit'`, or `None` — what to do with the connection when returned |

**Event hooks (`sqlalchemy.event`):**
- `connect` — fired when a new DBAPI connection is created (set session defaults, SET ROLE, etc.)
- `checkout` — fired on every borrow from the pool (telemetry, circuit breakers)
| `checkin` — fired on every return
- `invalidate` — fired when a connection is removed as bad

**Health management:**
- Pre-ping on checkout (`pre_ping=True`) — cheapest form of health checking
- `Pool.dispose()` — close all connections and replace pool (for credential rotation, fork-safety)
- Connection invalidation on error — bad connections are discarded rather than returned

**Fork safety:**
- `NullPool` or `Pool.dispose()` after `os.fork()` — SQLAlchemy documents the fork-safety contract; consuming processes must reinitialize pools

**What SQLAlchemy does NOT do:**
- No async-native pool for blocking drivers (the async pool adapts sync connections; real async requires asyncio-native DBAPI)
- No built-in circuit breaker
- No metrics/instrumentation (consumers hook events manually)
- No per-connection credential refresh at checkout time (recycle is time-based only)

---

### psycopg3 `ConnectionPool` and `AsyncConnectionPool`

psycopg3 ships its own pool as a separate package (`psycopg-pool`). It is purpose-built for PostgreSQL with knowledge of the protocol.

**Key features beyond SQLAlchemy's pool:**

| Feature | Description |
|---------|-------------|
| `min_size` / `max_size` | Maintain a range of connections (not pool_size + overflow) |
| Background connection opener | Proactively fills pool to `min_size` in a background thread/task |
| `reconnect_attempts` | Retry failed connections N times with backoff before giving up |
| `reconnect_timeout` | Total time budget for reconnection attempts |
| `open(wait=True/False)` | Block until pool is ready, or return immediately (background fill) |
| `check()` | Verify all idle connections are alive (triggered by `check_connection` callback) |
| `getconn()` / `putconn()` / context manager | Two checkout styles |
| `connection()` context manager | High-level: borrow, use, return in one `with` block |
| `stats()` | Returns dict of pool metrics: pool_min, pool_max, pool_size, pool_available, requests_waiting, etc. |
| Per-pool `configure` callback | Called after connection creation; used to set `search_path`, timezone, etc. |
| Per-pool `check` callback | Called at checkout to validate; replaces pre_ping |
| `closed` property | Detect if pool was disposed |
| `AsyncConnectionPool` | True async pool (not adapted sync); native asyncio |

**What makes psycopg3's pool noteworthy for this research:**
- The `stats()` method is a notable differentiator: built-in visibility into pool state without hooking events
- Explicit `open()` / `close()` lifecycle with `wait` parameter — important for startup sequencing
- Background prefill means first request does not pay the connection cost
- `check_connection` callback decouples health check logic from pool internals

---

### asyncpg `Pool`

asyncpg's pool is async-native, designed specifically for PostgreSQL with the asyncpg driver.

**Key features:**

| Feature | Description |
|---------|-------------|
| `min_size` / `max_size` | Maintain between min and max live connections |
| `max_inactive_connection_lifetime` | Prune connections idle longer than N seconds (separate from recycle) |
| `setup` coroutine | Called after each new connection: SET statements, prepare statements, etc. |
| `init` coroutine | Called once on pool creation |
| `connection_class` | Override the connection class returned by `acquire()` |
| `acquire()` / `release()` | Explicit borrow/return; also works as async context manager |
| `acquire(timeout=N)` | Per-acquire timeout overriding pool default |
| `terminate()` / `close()` | Graceful vs. immediate shutdown |
| `get_size()` / `get_min_size()` / `get_max_size()` | Runtime introspection |
| `get_idle_size()` | Count idle connections at any moment |
| Connection pruning | Background task prunes idle connections down toward min_size |

**asyncpg-specific:**
- `execute()` / `fetch()` / `fetchrow()` / `fetchval()` directly on the pool (borrow-execute-return in one call) — this is a "pool as executor" pattern that adbc-poolhouse explicitly does NOT adopt
- Statement caching per-connection (Postgres-specific)

---

### ADBC-Specific Pooling Examples

There is no widely-adopted standalone ADBC connection pool library as of early 2026. The pattern in the wild is:

1. **Direct dbapi usage** — open a single connection per process, no pooling (common for DuckDB in scripts)
2. **SQLAlchemy dialects** — `adbc-driver-postgresql`, `adbc-driver-snowflake` each ship SQLAlchemy dialect adapters; consumers use SQLAlchemy `create_engine()` which wraps QueuePool automatically. This is the closest to "existing ADBC pooling," but it goes through the full ORM engine machinery.
3. **Flight SQL + gRPC connection pooling** — some data warehouse clients pool gRPC channels rather than ADBC connections; this is a different layer
4. **Custom pools in BI tools** — tools like Apache Superset manage their own per-warehouse connection pools; ADBC drivers are treated as just another DBAPI

**ADBC-specific challenges that generic pools don't handle:**
- Token/credential expiry: warehouse auth tokens (Snowflake JWT, OAuth tokens) expire independently of connection idle time; `recycle` by wall-clock time is the blunt fix but not perfectly aligned
- Driver detection: ADBC has two driver distribution channels (PyPI packages and Foundry shared libraries); pools that wrap DBAPI assume `import driver_module` works, but Foundry drivers require `adbc_driver_manager` loading
- Connection kwargs structure: ADBC driver kwargs are warehouse-specific string keys (e.g. `adbc.snowflake.sql.account`); generic pools have no translation layer
- `adbc_driver_manager.dbapi.connect()` vs per-driver `.connect()`: the manager's DBAPI connect is the uniform entry point; pools need to know to use this

---

## Feature Taxonomy

### Table Stakes
*The library is not usable without these. Any serious pool has them.*

| Feature | Complexity | Notes |
|---------|-----------|-------|
| Configurable pool size | Low | `pool_size`, `max_overflow` — SQLAlchemy QueuePool provides |
| Checkout timeout | Low | Block and raise when pool exhausted — QueuePool provides |
| Connection health check (pre-ping) | Low | SQLAlchemy `pre_ping=True` — one flag |
| Connection recycling by age | Low | `recycle=N` — critical for warehouse token expiry |
| Thread-safe checkout/return | Medium | QueuePool is thread-safe; single-threaded use does not need this but multi-threaded consumers require it |
| Pool disposal / shutdown | Low | `Pool.dispose()` — required for clean teardown |
| Typed warehouse configuration | Medium | Pydantic BaseSettings per warehouse type; validation at construction time |
| ADBC driver kwargs translation | Medium | Config fields → driver-specific string kwargs; one translator per warehouse |
| ADBC driver detection | Medium | Try PyPI import, fall back to adbc_driver_manager; helpful error on missing driver |
| Sensible defaults | Low | `pool_size=5`, `max_overflow=3`, `timeout=30`, `pre_ping=True`, `recycle=3600` out of the box |
| Overridable pool kwargs | Low | Pass-through to QueuePool constructor; consumers who know what they want can set it |

**Dependency chain:** Driver detection depends on Config layer. Translation depends on Config layer. Pool factory depends on all three.

---

### Differentiators
*Competitive advantage for the ADBC + data warehouse use case. Not universal in generic pools.*

| Feature | Complexity | Notes |
|---------|-----------|-------|
| Warehouse-typed config models | Medium | `SnowflakeConfig`, `DuckDBConfig` — not "dsn string", but fields that match warehouse concepts (`account`, `warehouse`, `role`); Pydantic BaseSettings means env vars work for free |
| Environment variable support out of the box | Low | Comes for free from Pydantic BaseSettings — no extra work; competitors require manual os.environ |
| Dual driver channel support (PyPI + Foundry) | Medium | Transparent to consumer; handles the ADBC Foundry (dbc CLI) driver distribution model that generic pools know nothing about |
| Helpful installation errors | Low | "Driver not found. Run: pip install adbc-driver-snowflake" instead of ImportError traceback — DX differentiator |
| Config-to-pool in one call | Low | `create_pool(SnowflakeConfig(...))` — no DSN string wrangling, no manual kwarg construction |
| Recycle default tuned for token expiry | Low | Default `recycle=3600` is deliberately set for warehouse auth token lifetimes, not just "avoid server timeout" |
| No global state | Low | Library owns no singletons; consumers own pools — safe for multi-tenant applications and testing |

**Dependency chain:** All differentiators build on the Config layer. Dual driver support is internal to the driver detection layer.

---

### Anti-Features
*Things to deliberately NOT build. Each one kept out reduces scope and maintenance burden.*

| Anti-Feature | Why Not | Risk if Added |
|-------------|---------|---------------|
| Multi-pool registry / warehouse router | Consumer business logic; library is one pool per call | Adds global state, lifecycle management, thread contention over registry |
| Query execution on the pool | asyncpg does `pool.fetch()` etc; adbc-poolhouse explicitly does not | Couples execution semantics to pool; consumers have incompatible needs |
| Async pool | ADBC DBAPI is synchronous; SQLAlchemy async pool adapts sync connections (not native); genuine async ADBC is a future protocol concern | Incorrect semantics; blocking I/O in async context without proper thread pool is worse than no async |
| Connection string / DSN parsing | Each warehouse has different DSN formats; Pydantic fields are the right abstraction | DSN parsing is a rabbit hole; breaks type safety |
| OAuth / SSO auth logic | Delegated entirely to ADBC drivers and config field values | Auth is warehouse-specific and security-critical; wrong place to own it |
| Connection health callback customization | SQLAlchemy events cover this if consumers need it; default pre_ping is sufficient | Adds surface area; most consumers never need it |
| Built-in metrics / stats | psycopg3 has `stats()`; this library does not need it for v1 | Can be added later; SQLAlchemy events let consumers instrument themselves |
| Background connection prefill | psycopg3 and asyncpg pre-open connections; QueuePool is lazy | Complexity without clear benefit for batch/data warehouse workloads |
| Per-connection credential refresh | Some pools refresh tokens at checkout time | Warehouse token expiry is handled by `recycle`; proper per-checkout refresh requires driver cooperation |
| BigQuery, PostgreSQL, Databricks, Redshift, Trino, MSSQL | Explicitly Future | Adding before DuckDB + Snowflake are solid increases test burden |
| dbt profiles.yml reading | Consumer (dbt-open-sl) provides its own translation shim | This library must not know about dbt |
| Flight SQL / REST / gRPC serving | Different layer entirely | Out of scope by definition |

---

## Alignment with Existing Design

The design documented in `_notes/design-discussion.md` aligns well with standard practice:

**Aligns with standard practice:**
- SQLAlchemy QueuePool as the pool implementation — the most widely used, battle-tested choice; psycopg3 and asyncpg built their own pools only because they needed async or PostgreSQL-specific features that SQLAlchemy's pool did not provide
- `pool_size`, `max_overflow`, `timeout`, `pre_ping`, `recycle` defaults — these map exactly to the knobs every serious pool exposes
- No global state — consistent with modern library design; SQLAlchemy itself moved away from global metadata in recent versions
- Config + pool only, no execution — the right separation of concerns

**Diverges from standard practice (intentionally):**
- Typed config models instead of DSN strings — generic pools universally accept connection strings or callables; adbc-poolhouse's Pydantic BaseSettings is more opinionated and DX-focused; this is a deliberate differentiator, not a gap
- No async pool — asyncpg and psycopg3 both have async-first pools for async workloads; this library explicitly declines for v1 because ADBC DBAPI is synchronous
- Dual driver channel (PyPI + Foundry) — no generic pool knows about the ADBC driver distribution problem; this is unique to this library

**Design decisions that are table stakes but appear unique:**
- `recycle=3600` default — generic pools often default to no recycling or very long intervals; the 1-hour default is tuned for warehouse auth token lifetimes, making it a better default for the target use case

---

## Feature Dependencies

```
Config Layer (Pydantic BaseSettings per warehouse)
    └── Parameter Translation Layer (config fields → ADBC kwargs)
            └── Driver Detection Layer (PyPI import → Foundry fallback → helpful error)
                    └── Pool Factory: create_pool(config, **pool_kwargs) → QueuePool
                                └── Consumer: borrows connections, executes queries
```

Table stakes features cluster in the Pool Factory and are mostly delegated to SQLAlchemy QueuePool.
Differentiators cluster in the Config and Translation layers — this is where adbc-poolhouse does original work.
Anti-features are mostly things that belong either above the factory (consumer) or below it (driver internals).

---

## Sources

This research draws on:
- SQLAlchemy pool documentation and source (`sqlalchemy.pool.QueuePool`, `sqlalchemy.pool.events`)
- psycopg3 / psycopg-pool documentation (`ConnectionPool`, `AsyncConnectionPool`)
- asyncpg documentation (`asyncpg.create_pool`, `asyncpg.Pool`)
- Apache Arrow ADBC documentation and driver packages (`adbc-driver-snowflake`, `adbc-driver-manager`)
- ADBC Driver Foundry documentation (launched Oct 2025)
- Project design documents: `_notes/design-discussion.md`, `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md`
