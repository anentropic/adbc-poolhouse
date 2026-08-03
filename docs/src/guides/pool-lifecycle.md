# Pool lifecycle

[`create_pool`][adbc_poolhouse.create_pool] returns a SQLAlchemy `QueuePool`. On the ADBC path it holds one ADBC source connection plus a pool of cloned connections derived from it. [`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig] is the exception: it opens an independent Databricks Python connector session per pooled connection, with no shared source behind them.

## Create a pool

`create_pool` takes a config object and returns a ready-to-use `QueuePool`:

```python
from adbc_poolhouse import DuckDBConfig, create_pool

pool = create_pool(DuckDBConfig(database="/tmp/warehouse.db"))
```

adbc-poolhouse ships config classes for 14 backends, 13 ADBC drivers plus the
non-ADBC Databricks Python connector:
[`BigQueryConfig`][adbc_poolhouse.BigQueryConfig],
[`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig],
[`DatabricksConfig`][adbc_poolhouse.DatabricksConfig],
[`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig],
[`DuckDBConfig`][adbc_poolhouse.DuckDBConfig],
[`FlightSQLConfig`][adbc_poolhouse.FlightSQLConfig],
[`MSSQLConfig`][adbc_poolhouse.MSSQLConfig],
[`MySQLConfig`][adbc_poolhouse.MySQLConfig],
[`PostgreSQLConfig`][adbc_poolhouse.PostgreSQLConfig],
[`QuackConfig`][adbc_poolhouse.QuackConfig],
[`RedshiftConfig`][adbc_poolhouse.RedshiftConfig],
[`SnowflakeConfig`][adbc_poolhouse.SnowflakeConfig],
[`SQLiteConfig`][adbc_poolhouse.SQLiteConfig],
and [`TrinoConfig`][adbc_poolhouse.TrinoConfig].
Each config class validates credentials and prepares its connection automatically: the ADBC backends build the connection kwargs and resolve the driver, while [`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig] drives the Databricks Python connector instead (see the [Databricks Python connector guide](databricks-python.md)).

For custom ADBC drivers or cases where a built-in config class does not exist, `create_pool` also accepts [raw driver arguments](configuration.md#raw-driver-arguments) directly.

For env var loading and field details, see the [configuration guide](configuration.md).

## Checking out and returning connections

Use `pool.connect()` as a context manager. The connection returns to the pool when the `with` block exits, whether it exits normally or raises.

```python
with pool.connect() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT now()")
    row = cursor.fetchone()
```

Do not hold a connection outside a `with` block. Connections held past the `with` block are never returned to the pool and the pool will run out of available connections once they are all checked out.

`QueuePool` is thread-safe, so one pool can serve many concurrent workers: call `pool.connect()` from each request handler or worker thread and every checkout returns a distinct connection. Keep to one connection per thread. A checked-out connection should be used by a single thread at a time, never shared across concurrent tasks. The pool hands out at most `pool_size + max_overflow` connections at once; when they are all checked out, the next `pool.connect()` waits up to `timeout` seconds and then raises `sqlalchemy.exc.TimeoutError`. Size the pool against the connections you expect to be in use at the same time (see [Sizing under load](configuration.md#sizing-under-load)).

!!! warning "This pool is synchronous"

    `pool.connect()` and every driver call made through it block the calling thread. In an `async def` handler that stalls the event loop for the length of the query, and with it every other request the process is serving. Either declare the handler as a plain `def` so your framework runs it in a threadpool, or use the async pool. [Consumer patterns](consumer-patterns.md#do-not-call-the-sync-pool-from-an-async-def-handler) shows both.

## Committing writes

ADBC DBAPI connections are not in autocommit mode. Anything you write, whether that is a `CREATE TABLE`, an `INSERT`, or an `adbc_ingest`, sits in an open transaction until you commit it. Returning the connection to the pool does not commit that transaction: check-in calls `rollback()` on the connection, so uncommitted work is discarded. No exception is raised, and the row count the driver reported for the write is still whatever it was. The data is simply gone the next time you look.

Call `conn.commit()` before the `with` block exits:

```python
from adbc_poolhouse import DuckDBConfig, managed_pool

with managed_pool(DuckDBConfig(database="/tmp/warehouse.db")) as pool:
    with pool.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER)")
        cursor.execute("INSERT INTO events VALUES (1)")
        conn.commit()  # without this, both statements are rolled back at check-in
```

The async surface behaves identically, with `await` in front:

```python
from adbc_poolhouse import DuckDBConfig, managed_async_pool

async with managed_async_pool(DuckDBConfig(database="/tmp/warehouse.db")) as pool:
    async with await pool.connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO events VALUES (2)")
        await conn.commit()
```

Two consequences are worth planning for. Until you commit, the write is invisible to every other connection in the pool, including connections your own process checked out for a different request. And a connection the pool invalidates part-way through, which is what happens when an in-flight async write is cancelled, takes its open transaction down with it, so on a transactional driver the write never lands. `conn.rollback()` is available when you want to abandon the work deliberately rather than leave it to check-in.

Reads need no commit. If a handler only runs `SELECT` statements, checking the connection back in is enough.

## Closing the pool

A pool holds real driver resources, a file handle or a network socket, so it must be closed when you are done with it. There are two ways to close a pool, and which one fits depends on whether the pool's lifetime maps cleanly onto a single block of code.

### Explicit close, for lifetimes that span your app

When the pool outlives any single scope, such as a long-running server or backend that opens the pool at startup and serves requests for hours, close it explicitly with [`close_pool`][adbc_poolhouse.close_pool]:

```python
from adbc_poolhouse import close_pool

close_pool(pool)
```

`close_pool` drains the pool and closes each pooled connection, and on the ADBC path it also releases the shared source connection, all in one call. Calling `pool.dispose()` alone leaves a file handle or network socket open until the process exits.

What it does not do is wait. Connections that are still checked out when you call it are neither closed nor waited for, and the source connection closes immediately regardless. Call it once the work using the pool has finished, not alongside it.

In practice you wire this into your framework's startup and shutdown hooks: create the pool when the app boots and call `close_pool` when it shuts down. [Consumer patterns](consumer-patterns.md#the-sync-pool-in-a-fastapi-lifespan) has a FastAPI lifespan that does exactly this.

### Context manager, for lifetimes that fit a scope

When the pool's lifetime fits neatly inside an enclosing block, such as a script, a short-lived process, or a test, use [`managed_pool`][adbc_poolhouse.managed_pool] as a context manager:

```python
from adbc_poolhouse import DuckDBConfig, managed_pool

with managed_pool(DuckDBConfig(database="/tmp/test.db")) as pool:
    with pool.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
# pool is automatically closed when the with block exits
```

More lifetimes fit inside a scope than you might expect. A framework's lifespan hook is itself a block, so a pool that lives as long as the whole application can still be wrapped: [Consumer patterns](consumer-patterns.md#fastapi-lifespan-with-the-async-pool) does exactly that with [`managed_async_pool`][adbc_poolhouse.managed_async_pool]. Wherever a scope does fit, it is the preferred option: `managed_pool` guarantees `close_pool` runs on exit, including when the block raises, so you cannot leak the source connection by forgetting to close it or by hitting an early return.

## Pytest fixture pattern

For test suites, create the pool once per session and dispose it in the fixture teardown:

```python
import pytest
from adbc_poolhouse import DuckDBConfig, close_pool, create_pool


@pytest.fixture(scope="session")
def pool():
    p = create_pool(DuckDBConfig(database="/tmp/test.db"))
    yield p
    close_pool(p)
```

Using `scope="session"` creates one pool for the entire test session. If your tests need isolation between test functions, use `scope="function"` instead so each test gets its own pool.

## Tuning the pool

`create_pool` (and `managed_pool`) accept five keyword arguments that tune pool behaviour: `pool_size`, `max_overflow`, `timeout`, `recycle`, and `pre_ping`. The defaults are conservative and appropriate for most use cases. [Pool tuning](configuration.md#pool-tuning) in the configuration guide is the single description of what each one does, its default, and how it loads from an environment variable.

A keyword passed here overrides whatever the config carries:

```python
pool = create_pool(config, pool_size=10, recycle=7200)
```

Two of the five shape how the pool behaves in a long-running process. `pool_size` plus `max_overflow` is the checkout ceiling described above, so it decides when callers start waiting on `timeout`. And `recycle` is what stops a long-lived connection going stale, because `pre_ping` cannot run on the standalone `QueuePool` this library builds: setting `pre_ping=True` raises `NotImplementedError` on the first re-checkout of a pooled connection. [Keeping connections healthy with recycle](configuration.md#keeping-connections-healthy-with-recycle) covers how to pick a `recycle` value.

## Common mistakes

**Calling `pool.dispose()` without `close_pool()`**

`pool.dispose()` drains the pool but does not close the ADBC source connection. Always use `close_pool(pool)` (or `managed_pool` as a context manager). Do not call `pool.dispose()` directly.

**Using `database=":memory:"` with `pool_size > 1`**

Each DuckDB connection cloned from an in-memory source gets its own isolated empty database. [`DuckDBConfig`][adbc_poolhouse.DuckDBConfig] raises [`ConfigurationError`][adbc_poolhouse.ConfigurationError] at construction (wrapped by Pydantic as a `ValidationError`) if you pass `pool_size > 1` with an in-memory database, which prevents this silent data-loss bug. Use a file-backed database when you need multiple connections.

**Holding connections outside the `with` block**

If you call `pool.connect()` without a context manager, the connection is checked out and never returned:

```python
# Wrong -- connection is never returned to the pool
conn = pool.connect()
cursor = conn.cursor()
cursor.execute("SELECT 1")
```

The pool will exhaust its connections and subsequent `pool.connect()` calls will block until the timeout and then raise `sqlalchemy.exc.TimeoutError`.

**Writing without committing**

A write that is never committed is rolled back when the connection checks in, and nothing tells you so. See [Committing writes](#committing-writes).

## Catching errors

adbc-poolhouse's own exceptions both subclass [`PoolhouseError`][adbc_poolhouse.PoolhouseError]: [`ConfigurationError`][adbc_poolhouse.ConfigurationError] for invalid configuration and [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] for concurrent use of one async connection. `except PoolhouseError` catches `ConnectionBusyError` at runtime.

It does not catch a configuration failure. Config validation runs inside Pydantic validators, so building a config surfaces `pydantic.ValidationError`, which sits outside this hierarchy however the validator failed. Guard config construction with `except pydantic.ValidationError` and the runtime paths with `except PoolhouseError`.

A saturated-pool checkout raises something else again: `sqlalchemy.exc.TimeoutError`, SQLAlchemy's own class, which does not subclass the builtin `TimeoutError`. Catch it by its full name, separately from both of the above.

## See also

- [Consumer patterns](consumer-patterns.md) — FastAPI lifespan and dbt profiles examples
- [Pool tuning](configuration.md#pool-tuning) — the five tuning fields, their defaults, and recycle guidance
- [Configuration](configuration.md) — env var loading and per-backend field details
