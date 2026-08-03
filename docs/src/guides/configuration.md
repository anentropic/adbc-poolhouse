# Configuration

All config classes in adbc-poolhouse are Pydantic `BaseSettings` models. Fields can be set by passing keyword arguments or by reading from environment variables using a warehouse-specific prefix.

## Environment variable prefixes

Each config class reads its fields from environment variables with a prefix matching the warehouse name:

| Config class | env_prefix |
|---|---|
| [`DuckDBConfig`][adbc_poolhouse.DuckDBConfig] | `DUCKDB_` |
| [`SQLiteConfig`][adbc_poolhouse.SQLiteConfig] | `SQLITE_` |
| [`SnowflakeConfig`][adbc_poolhouse.SnowflakeConfig] | `SNOWFLAKE_` |
| [`BigQueryConfig`][adbc_poolhouse.BigQueryConfig] | `BIGQUERY_` |
| [`PostgreSQLConfig`][adbc_poolhouse.PostgreSQLConfig] | `POSTGRESQL_` |
| [`FlightSQLConfig`][adbc_poolhouse.FlightSQLConfig] | `FLIGHTSQL_` |
| [`DatabricksConfig`][adbc_poolhouse.DatabricksConfig] | `DATABRICKS_` |
| [`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig] | `DATABRICKS_PYTHON_` |
| [`RedshiftConfig`][adbc_poolhouse.RedshiftConfig] | `REDSHIFT_` |
| [`TrinoConfig`][adbc_poolhouse.TrinoConfig] | `TRINO_` |
| [`MSSQLConfig`][adbc_poolhouse.MSSQLConfig] | `MSSQL_` |
| [`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig] | `CLICKHOUSE_` |
| [`MySQLConfig`][adbc_poolhouse.MySQLConfig] | `MYSQL_` |
| [`QuackConfig`][adbc_poolhouse.QuackConfig] | `QUACK_` |

Thirteen of those backends run on an ADBC driver. [`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig] is the exception: it drives the Databricks Python connector instead, which is not ADBC (see the [Databricks Python connector guide](databricks-python.md)).

For example, setting `SNOWFLAKE_ACCOUNT=myorg-myaccount` in the environment is equivalent to passing `account="myorg-myaccount"` to `SnowflakeConfig(...)`.

To create a pool from environment variables only, call the config class with no arguments:

```python
import os
from adbc_poolhouse import SnowflakeConfig, create_pool

os.environ["SNOWFLAKE_ACCOUNT"] = "myorg-myaccount"
os.environ["SNOWFLAKE_USER"] = "me"
os.environ["SNOWFLAKE_PASSWORD"] = "..."

config = SnowflakeConfig()  # reads all fields from env
pool = create_pool(config)
```

## Pool tuning

All config classes inherit pool tuning fields from [`BaseWarehouseConfig`][adbc_poolhouse.BaseWarehouseConfig]. These also load from environment variables using the same warehouse prefix:

| Field | Default | Description |
|---|---|---|
| `pool_size` | `5` | Number of connections to keep open (DuckDB and SQLite default to `1` for in-memory databases, `5` for file-backed) |
| `max_overflow` | `3` | Extra connections allowed when pool is full |
| `timeout` | `30` | Seconds to wait for a connection before raising `sqlalchemy.exc.TimeoutError` |
| `recycle` | `3600` | Seconds before a connection is closed and replaced |
| `pre_ping` | `False` | Ping connections before checkout. Setting `pre_ping=True` raises `NotImplementedError` on the first re-checkout of a pooled connection; leave it `False` and use `recycle` for connection health. |

This table is the reference copy. The [pool lifecycle](pool-lifecycle.md#tuning-the-pool) and [custom backends](custom-backends.md#pool-tuning) guides point back here rather than repeating it.

[`create_pool`][adbc_poolhouse.create_pool] reads these fields off the config, so setting them on the config (or via its environment prefix) tunes the pool. A tuning keyword passed directly to `create_pool` overrides the config's field. To override pool size via environment variable:

```bash
export SNOWFLAKE_POOL_SIZE=10
export SNOWFLAKE_MAX_OVERFLOW=5
```

Two base types sit behind those fields, and they are not interchangeable. [`BaseWarehouseConfig`][adbc_poolhouse.BaseWarehouseConfig] is the Pydantic `BaseSettings` class every built-in config inherits from, and it is where all five fields above are defined. [`WarehouseConfig`][adbc_poolhouse.WarehouseConfig] is a separate structural `Protocol` describing what `create_pool` actually requires of a config object: four of those fields (`pool_size`, `max_overflow`, `timeout`, `recycle`) plus the driver-resolution methods. `pre_ping` is deliberately outside the Protocol, so a config that does not declare it is read as `False`. The distinction only matters when you write a config class of your own; the [custom backends guide](custom-backends.md) covers both routes.

### Keeping connections healthy with recycle

`recycle` caps how long a pooled connection may live before the pool discards it and opens a replacement. `pre_ping` cannot run on the standalone `QueuePool` that adbc-poolhouse builds: SQLAlchemy's ping path needs a dialect the pool does not have, so setting `pre_ping=True` raises `NotImplementedError` on the first re-checkout of a pooled connection. The first checkout of a fresh connection succeeds, which is why the failure tends to arrive on the second request rather than at startup. Leave `pre_ping` at its `False` default. That makes `recycle` the pool's connection-health mechanism, which is why it ships enabled at 3600 seconds rather than off.

The age check runs at checkout, not on a background timer. Each time the pool hands out a connection it compares that connection's age against `recycle`; if the connection is older, the pool closes it and creates a fresh one before returning. Two consequences follow. An idle pool never recycles anything on its own, so a process that goes quiet overnight does its recycling on the first checkout of the morning. And the replacement is invisible to your code, which receives a usable connection either way.

Choose a value below whatever idle timeout your warehouse, proxy, or load balancer applies to a session, with margin for a connection that passes the age check and then sits for the length of a slow query. If your warehouse drops idle sessions after 30 minutes, something like `recycle=1200` gives that margin. The one-hour default is a generic starting point, not a value tuned to any particular backend, so check what your warehouse actually enforces.

Set `recycle` too high and the pool will eventually hand you a connection the server has already closed. Nothing detects this at checkout: the pool considers the connection valid, and the failure surfaces on the first statement you run as the driver's own exception. adbc-poolhouse does not wrap it, so it is not a [`PoolhouseError`][adbc_poolhouse.PoolhouseError] and catching one will not catch it. Retrying is your responsibility; lowering `recycle` is the fix.

One limit worth knowing: on the ADBC path the pooled connections are clones of a single source connection that [`create_pool`][adbc_poolhouse.create_pool] opens and [`close_pool`][adbc_poolhouse.close_pool] closes. Recycling refreshes the clones, never the source they are cloned from.

### Sizing under load

A pool built by [`create_pool`][adbc_poolhouse.create_pool] (or [`managed_pool`][adbc_poolhouse.managed_pool]) hands out at most `pool_size + max_overflow` connections at once. That sum is the checkout ceiling. Once every connection is in use, the next `pool.connect()` waits up to `timeout` seconds for one to return, then raises `sqlalchemy.exc.TimeoutError`. That is SQLAlchemy's own class, not the builtin `TimeoutError`, so catch it by its full name (see [Catching errors](pool-lifecycle.md#catching-errors)).

Size `pool_size` against the number of connections you expect to be checked out at the same time, and keep the ceiling at or below whatever the warehouse allows per client. A pool that is too small serializes callers behind the timeout; one that is too large can exhaust the warehouse's own connection limit. The pool is thread-safe, so these connections can be checked out concurrently from many threads or request handlers (see [Checking out and returning connections](pool-lifecycle.md#checking-out-and-returning-connections)).

An async pool applies the same ceiling and raises the same exception, with one extra limit in front of it. See [When the pool is saturated](async.md#when-the-pool-is-saturated) for how the two interact and what to catch in a request handler.

## Async pools

!!! warning "Experimental"
    The async API is experimental. Its surface may change between minor releases. See the [async pool guide](async.md) for the full caveat.

The async entry points live behind an optional extra. Install it with:

```bash
pip install adbc-poolhouse[async]
```

The three async entry points ([`create_async_pool`][adbc_poolhouse.create_async_pool], [`managed_async_pool`][adbc_poolhouse.managed_async_pool], and [`close_async_pool`][adbc_poolhouse.close_async_pool]) mirror the signatures of their sync counterparts (`create_pool`, `managed_pool`, [`close_pool`][adbc_poolhouse.close_pool]). The same `pool_size`, `max_overflow`, `timeout`, `recycle`, and `pre_ping` fields documented in [Pool tuning](#pool-tuning) apply, with the same defaults.

Each async pool sizes its own `anyio.CapacityLimiter` to `pool_size + max_overflow`. That limiter caps how many blocking ADBC calls run on worker threads at once, so the same tuning fields that size the underlying `QueuePool` also govern async concurrency. There is no separate knob.

For the first-query walkthrough, concurrency limits, and the one-connection-per-task rule, see the [async pool guide](async.md).

## Secret fields

Fields like `password`, `private_key_pem`, and `oauth_token` are `SecretStr` values. They are masked in `repr()` output to avoid leaking credentials in logs:

```python
from adbc_poolhouse import SnowflakeConfig

config = SnowflakeConfig(account="myorg", user="me", password="s3cret")
print(config.password)  # **********
print(config.password.get_secret_value())  # s3cret
```

Call `.get_secret_value()` when you need the raw string, for example when passing credentials to a driver.

## Error handling

Invalid configuration is rejected at construction time: mutually exclusive credentials, a `pool_size` a backend cannot support, and similar validation failures. Every one of those checks runs inside a Pydantic validator, so what reaches your call site is Pydantic's `ValidationError`, carrying the message inside it. Catch `pydantic.ValidationError` around config construction. Neither `except ConfigurationError` nor `except PoolhouseError` fires there.

[`ConfigurationError`][adbc_poolhouse.ConfigurationError] is the type most of those checks raise, and it subclasses [`PoolhouseError`][adbc_poolhouse.PoolhouseError], the base class for every exception adbc-poolhouse defines. Reading it out of a `ValidationError` is rarely worth the trouble; the message is already in the report Pydantic prints. Driver errors and `sqlalchemy.exc.TimeoutError` sit outside the hierarchy entirely and pass through unwrapped. [Catching errors](pool-lifecycle.md#catching-errors) in the pool lifecycle guide has the full picture.

One failure mode raises nothing at all. Pooled ADBC connections are not in autocommit mode, so a write you do not commit is discarded when the connection checks in, silently. [Committing writes](pool-lifecycle.md#committing-writes) covers what to call and when.

## Foundry-distributed backends

[`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig], [`DatabricksConfig`][adbc_poolhouse.DatabricksConfig], [`MySQLConfig`][adbc_poolhouse.MySQLConfig], [`RedshiftConfig`][adbc_poolhouse.RedshiftConfig], [`TrinoConfig`][adbc_poolhouse.TrinoConfig], and [`MSSQLConfig`][adbc_poolhouse.MSSQLConfig] are present in the package but their ADBC drivers are not available on PyPI. They are distributed through the ADBC Driver Foundry. To use one of these backends, follow the Foundry installation guide for your platform to install the matching driver package.

## Raw driver arguments

For custom ADBC drivers or cases where a built-in config class does not exist, `create_pool` and `managed_pool` accept raw ADBC driver arguments directly.

Two raw paths are supported. Use one or the other, not both:

=== "Native ADBC driver"

    `driver_path` accepts two forms:

    - An absolute path to a shared library (`.so`, `.dylib`, `.dll`)
    - A short driver name that `adbc_driver_manager` resolves through its manifest-based lookup

    Manifest lookup only finds drivers that install a manifest, which is what the ADBC Driver Foundry's `dbc install` command does. A driver package installed from PyPI ships no manifest, so a short name will not resolve to it. Those packages expose their own path helper instead, and that is what you pass as `driver_path`. For DuckDB the helper is `adbc_driver_duckdb.driver_path()`.

    For a list of available drivers and installation instructions, see the
    [ADBC driver installation docs](https://arrow.apache.org/adbc/current/driver/installation.html).

    See the [ADBC driver manifests docs](https://arrow.apache.org/adbc/current/format/driver_manifests.html)
    for details about driver path resolution.


    ```python
    import adbc_driver_duckdb

    from adbc_poolhouse import create_pool, close_pool

    pool = create_pool(
        driver_path=adbc_driver_duckdb.driver_path(),
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

For writing a reusable config class instead, see the [custom backends guide](custom-backends.md).

## See also

- [Pool lifecycle](pool-lifecycle.md) — checkout, committing writes, closing the pool, and pytest fixtures
- [Async pool](async.md) — the asyncio/trio wrapper, the `[async]` extra, and concurrency limits
- [Snowflake guide](snowflake.md) — JWT, OAuth, and private key configuration
- [Custom backends](custom-backends.md) — writing a config class for unsupported drivers
- [API Reference](../reference/adbc_poolhouse.md) — full field listing per config class
