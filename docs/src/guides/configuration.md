# Configuration reference

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
| [`RedshiftConfig`][adbc_poolhouse.RedshiftConfig] | `REDSHIFT_` |
| [`TrinoConfig`][adbc_poolhouse.TrinoConfig] | `TRINO_` |
| [`MSSQLConfig`][adbc_poolhouse.MSSQLConfig] | `MSSQL_` |
| [`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig] | `CLICKHOUSE_` |
| [`MySQLConfig`][adbc_poolhouse.MySQLConfig] | `MYSQL_` |
| [`QuackConfig`][adbc_poolhouse.QuackConfig] | `QUACK_` |

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
| `pool_size` | `5` | Number of connections to keep open (DuckDB defaults to `1`) |
| `max_overflow` | `3` | Extra connections allowed when pool is full |
| `timeout` | `30` | Seconds to wait for a connection before raising `sqlalchemy.exc.TimeoutError` |
| `recycle` | `3600` | Seconds before a connection is closed and replaced |
| `pre_ping` | `False` | Ping connections before checkout. Disabled by default. It does not function on standalone `QueuePool` without a SQLAlchemy dialect; use `recycle` for connection health. |

To override pool size via environment variable:

```bash
export SNOWFLAKE_POOL_SIZE=10
export SNOWFLAKE_MAX_OVERFLOW=5
```

### Sizing under load

A pool built by [`create_pool`][adbc_poolhouse.create_pool] (or [`managed_pool`][adbc_poolhouse.managed_pool]) hands out at most `pool_size + max_overflow` connections at once. That sum is the checkout ceiling. Once every connection is in use, the next `pool.connect()` waits up to `timeout` seconds for one to return, then raises `sqlalchemy.exc.TimeoutError`.

Size `pool_size` against the number of connections you expect to be checked out at the same time, and keep the ceiling at or below whatever the warehouse allows per client. A pool that is too small serializes callers behind the timeout; one that is too large can exhaust the warehouse's own connection limit. The pool is thread-safe, so these connections can be checked out concurrently from many threads or request handlers (see [Checking out and returning connections](pool-lifecycle.md#checking-out-and-returning-connections)).

## Async pools

!!! warning "Experimental"
    The async API is experimental and incomplete. See the [async pool guide](async.md) for the full caveat.

The async entry points live behind an optional extra. Install it with:

```bash
pip install adbc-poolhouse[async]
```

The three async entry points ([`create_async_pool`][adbc_poolhouse.create_async_pool], [`managed_async_pool`][adbc_poolhouse.managed_async_pool], and [`close_async_pool`][adbc_poolhouse.close_async_pool]) mirror the signatures of their sync counterparts (`create_pool`, `managed_pool`, [`close_pool`][adbc_poolhouse.close_pool]). The same `pool_size`, `max_overflow`, `timeout`, `recycle`, and `pre_ping` fields documented in [Pool tuning](#pool-tuning) apply, with the same defaults.

Each async pool sizes its own `anyio.CapacityLimiter` to `pool_size + max_overflow`. That limiter caps how many blocking ADBC calls run on worker threads at once, so the same tuning fields that size the underlying `QueuePool` also govern async concurrency. There is no separate knob.

For the first-query walkthrough, concurrency limits, and the one-connection-per-task rule, see the [async pool guide](async.md).

## Secret fields

Fields like `password`, `private_key_pem`, and `token` are `SecretStr` values. They are masked in `repr()` output to avoid leaking credentials in logs:

```python
config = SnowflakeConfig(account="myorg", user="me", password="s3cret")
print(config.password)  # **********
print(config.password.get_secret_value())  # s3cret
```

Call `.get_secret_value()` when you need the raw string, for example when passing credentials to a driver.

## Foundry-distributed backends

[`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig], [`DatabricksConfig`][adbc_poolhouse.DatabricksConfig], [`MySQLConfig`][adbc_poolhouse.MySQLConfig], [`RedshiftConfig`][adbc_poolhouse.RedshiftConfig], [`TrinoConfig`][adbc_poolhouse.TrinoConfig], and [`MSSQLConfig`][adbc_poolhouse.MSSQLConfig] are present in the package but their ADBC drivers are not available on PyPI. They are distributed through the ADBC Driver Foundry. If you use one of these backends, follow the installation guide for your Foundry setup to get the correct driver package installed.

## Raw driver arguments

For custom ADBC drivers or cases where a built-in config class does not exist, `create_pool` and `managed_pool` accept raw ADBC driver arguments directly.

Two raw paths are supported. Use one or the other, not both:

=== "Native ADBC driver"

    `driver_path` accepts two forms:

    - An absolute path to a shared library (`.so`, `.dylib`, `.dll`)
    - A short driver name like `"adbc_driver_duckdb"` that `adbc_driver_manager` resolves through its manifest-based lookup

    For a list of available drivers and installation instructions, see the
    [ADBC driver installation docs](https://arrow.apache.org/adbc/current/driver/installation.html).

    See the [ADBC driver manifests docs](https://arrow.apache.org/adbc/current/format/driver_manifests.html)
    for details about driver path resolution.


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

For writing a reusable config class instead, see the [custom backends guide](custom-backends.md).

## See also

- [Async pool](async.md) — the asyncio/trio wrapper, the `[async]` extra, and concurrency limits
- [Snowflake guide](snowflake.md) — JWT, OAuth, and private key configuration
- [Custom backends](custom-backends.md) — writing a config class for unsupported drivers
- [API Reference](../reference/) — full field listing per config class
