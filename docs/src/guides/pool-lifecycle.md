# Pool lifecycle

`create_pool` returns a SQLAlchemy `QueuePool`. Internally it holds one ADBC source connection plus a pool of cloned connections derived from it.

## Create a pool

`create_pool` takes a config object and returns a ready-to-use `QueuePool`:

```python
from adbc_poolhouse import DuckDBConfig, create_pool

pool = create_pool(DuckDBConfig(database="/tmp/warehouse.db"))
```

adbc-poolhouse ships config classes for 12 backends:
[`BigQueryConfig`][adbc_poolhouse.BigQueryConfig],
[`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig],
[`DatabricksConfig`][adbc_poolhouse.DatabricksConfig],
[`DuckDBConfig`][adbc_poolhouse.DuckDBConfig],
[`FlightSQLConfig`][adbc_poolhouse.FlightSQLConfig],
[`MSSQLConfig`][adbc_poolhouse.MSSQLConfig],
[`MySQLConfig`][adbc_poolhouse.MySQLConfig],
[`PostgreSQLConfig`][adbc_poolhouse.PostgreSQLConfig],
[`RedshiftConfig`][adbc_poolhouse.RedshiftConfig],
[`SnowflakeConfig`][adbc_poolhouse.SnowflakeConfig],
[`SQLiteConfig`][adbc_poolhouse.SQLiteConfig],
and [`TrinoConfig`][adbc_poolhouse.TrinoConfig].
Each config class validates credentials, builds the ADBC connection kwargs, and resolves the driver automatically.

For custom ADBC drivers or cases where a built-in config class does not exist, `create_pool` also accepts raw driver arguments directly. See [Raw driver arguments](#raw-driver-arguments) below.

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

## Disposing the pool

To shut down cleanly, call `close_pool`:

```python
from adbc_poolhouse import close_pool

close_pool(pool)
```

`close_pool` drains the pool, closes each pooled connection, and releases the ADBC source connection in one call. Calling `pool.dispose()` alone leaves a file handle or network socket open until the process exits.

For scripts and short-lived processes, use `managed_pool` as a context manager instead:

```python
from adbc_poolhouse import DuckDBConfig, managed_pool

with managed_pool(DuckDBConfig(database="/tmp/test.db")) as pool:
    with pool.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
# pool is automatically closed when the with block exits
```

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
| `timeout` | `30` | Seconds to wait for a connection before raising `TimeoutError` |
| `recycle` | `3600` | Seconds before a connection is closed and replaced |
| `pre_ping` | `False` | Ping connections before checkout (disabled: does not function on standalone `QueuePool` without a SQLAlchemy dialect; use `recycle` instead) |

Pass any of these to `create_pool`:

```python
pool = create_pool(config, pool_size=10, recycle=7200)
```

## Raw driver arguments

For custom ADBC drivers or cases where a built-in config class does not exist, `create_pool` and `managed_pool` accept raw ADBC driver arguments directly.

Two raw paths are supported. Use one or the other, not both:

=== "Native ADBC driver"

    `driver_path` accepts two forms:

    - An absolute path to a shared library (`.so`, `.dylib`, `.dll`)
    - A short driver name like `"adbc_driver_duckdb"` that `adbc_driver_manager` resolves through its manifest-based lookup

    For a list of available drivers and installation instructions, see the
    [ADBC driver installation docs](https://arrow.apache.org/adbc/current/driver/installation.html).

    ```python
    from adbc_poolhouse import create_pool, close_pool

    pool = create_pool(
        driver_path="adbc_driver_duckdb",
        db_kwargs={"path": "/tmp/my.db"},
        # entrypoint is only needed when the driver uses a non-default
        # init symbol. DuckDB requires "duckdb_adbc_init".
        entrypoint="duckdb_adbc_init",
    )
    # ... use pool ...
    close_pool(pool)
    ```

    `entrypoint` is optional. Most drivers use a default init symbol and do not need it. DuckDB is the main driver that requires an explicit entrypoint (`"duckdb_adbc_init"`).

=== "Python dbapi module"

    `dbapi_module` is a dotted Python module path (e.g. `"adbc_driver_snowflake.dbapi"`). The module must expose a `connect()` function. adbc-poolhouse detects the function's signature and passes connection arguments accordingly.

    This path imports the Python package and calls its `connect()` directly. By contrast, `driver_path` loads a native shared library through `adbc_driver_manager`.

    ```python
    from adbc_poolhouse import managed_pool

    with managed_pool(
        dbapi_module="adbc_driver_snowflake.dbapi",
        db_kwargs={"adbc.snowflake.sql.account": "myorg-myaccount"},
    ) as pool:
        with pool.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
    ```

Pool tuning arguments (`pool_size`, `max_overflow`, `timeout`, `recycle`, `pre_ping`) work with both raw paths, same defaults as the config path.

## Common mistakes

**Calling `pool.dispose()` without `close_pool()`**

`pool.dispose()` drains the pool but does not close the ADBC source connection. Always use `close_pool(pool)` (or `managed_pool` as a context manager). Do not call `pool.dispose()` directly.

**Using `database=":memory:"` with `pool_size > 1`**

Each DuckDB connection cloned from an in-memory source gets its own isolated empty database. `create_pool` raises `ValueError` if you pass `pool_size > 1` with an in-memory database to prevent this silent data-loss bug. Use a file-backed database when you need multiple connections.

**Holding connections outside the `with` block**

If you call `pool.connect()` without a context manager, the connection is checked out and never returned:

```python
# Wrong -- connection is never returned to the pool
conn = pool.connect()
cursor = conn.cursor()
cursor.execute("SELECT 1")
```

The pool will exhaust its connections and subsequent `pool.connect()` calls will block until the timeout.

## See also

- [Consumer patterns](consumer-patterns.md) -- FastAPI lifespan and dbt profiles examples
- [Configuration reference](configuration.md) -- env var loading, pool tuning fields, and per-backend field details
