# Pool lifecycle

[`create_pool`][adbc_poolhouse.create_pool] returns a SQLAlchemy `QueuePool`. Internally it holds one ADBC source connection plus a pool of cloned connections derived from it.

## Create a pool

`create_pool` takes a config object and returns a ready-to-use `QueuePool`:

```python
from adbc_poolhouse import DuckDBConfig, create_pool

pool = create_pool(DuckDBConfig(database="/tmp/warehouse.db"))
```

adbc-poolhouse ships config classes for 13 backends:
[`BigQueryConfig`][adbc_poolhouse.BigQueryConfig],
[`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig],
[`DatabricksConfig`][adbc_poolhouse.DatabricksConfig],
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
Each config class validates credentials, builds the ADBC connection kwargs, and resolves the driver automatically.

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

## Closing the pool

A pool holds a real ADBC source connection, a file handle or network socket, so it must be closed when you are done with it. There are two ways to close a pool, and which one fits depends on whether the pool's lifetime maps cleanly onto a single block of code.

### Explicit close, for lifetimes that span your app

When the pool outlives any single scope, such as a long-running server or backend that opens the pool at startup and serves requests for hours, close it explicitly with [`close_pool`][adbc_poolhouse.close_pool]:

```python
from adbc_poolhouse import close_pool

close_pool(pool)
```

`close_pool` drains the pool, closes each pooled connection, and releases the ADBC source connection in one call. Calling `pool.dispose()` alone leaves a file handle or network socket open until the process exits.

In practice you wire this into your framework's startup and shutdown hooks: create the pool when the app boots and call `close_pool` when it shuts down. See [Consumer patterns](consumer-patterns.md) for a FastAPI lifespan example that does exactly this.

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

Not every use case suits a context manager; a pool tied to your app's lifetime does not. But for the cases that do fit a scope, `managed_pool` is the preferred option: it guarantees `close_pool` runs on exit, including when the block raises, so you cannot leak the source connection by forgetting to close it or by hitting an early return.

## Pytest fixture pattern

For test suites, create the pool once per session and dispose it in the fixture teardown:

```python
import pytest
from adbc_poolhouse import DuckDBConfig, create_pool


@pytest.fixture(scope="session")
def pool():
    p = create_pool(DuckDBConfig(database="/tmp/test.db"))
    yield p
    from adbc_poolhouse import close_pool

    close_pool(p)
```

Using `scope="session"` creates one pool for the entire test session. If your tests need isolation between test functions, use `scope="function"` instead so each test gets its own pool.

## Tuning the pool

`create_pool` (and `managed_pool`) accept keyword arguments to tune pool behaviour. The defaults are conservative and appropriate for most use cases:

| Argument | Default | Description |
|---|---|---|
| `pool_size` | `5` | Connections kept in the pool at all times (DuckDB defaults to `1`) |
| `max_overflow` | `3` | Extra connections allowed above `pool_size` when demand is high |
| `timeout` | `30` | Seconds to wait for a connection before raising `sqlalchemy.exc.TimeoutError` |
| `recycle` | `3600` | Seconds before a connection is closed and replaced |
| `pre_ping` | `False` | Ping connections before checkout (disabled: does not function on standalone `QueuePool` without a SQLAlchemy dialect; use `recycle` instead) |

Pass any of these to `create_pool`:

```python
pool = create_pool(config, pool_size=10, recycle=7200)
```

## Common mistakes

**Calling `pool.dispose()` without `close_pool()`**

`pool.dispose()` drains the pool but does not close the ADBC source connection. Always use `close_pool(pool)` (or `managed_pool` as a context manager). Do not call `pool.dispose()` directly.

**Using `database=":memory:"` with `pool_size > 1`**

Each DuckDB connection cloned from an in-memory source gets its own isolated empty database. `DuckDBConfig` raises `ValidationError` at construction if you pass `pool_size > 1` with an in-memory database, which prevents this silent data-loss bug. Use a file-backed database when you need multiple connections.

**Holding connections outside the `with` block**

If you call `pool.connect()` without a context manager, the connection is checked out and never returned:

```python
# Wrong -- connection is never returned to the pool
conn = pool.connect()
cursor = conn.cursor()
cursor.execute("SELECT 1")
```

The pool will exhaust its connections and subsequent `pool.connect()` calls will block until the timeout.

## Catching errors

adbc-poolhouse's own exceptions both subclass [`PoolhouseError`][adbc_poolhouse.PoolhouseError]: [`ConfigurationError`][adbc_poolhouse.ConfigurationError] for invalid configuration and [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] for concurrent use of one async connection. Catch `PoolhouseError` to handle any library-specific error in one place. A saturated-pool checkout instead raises `sqlalchemy.exc.TimeoutError`, SQLAlchemy's own class, which does not subclass the builtin `TimeoutError`, so catch it separately from this hierarchy.

## See also

- [Consumer patterns](consumer-patterns.md) -- FastAPI lifespan and dbt profiles examples
- [Configuration reference](configuration.md) -- env var loading, pool tuning fields, and per-backend field details
