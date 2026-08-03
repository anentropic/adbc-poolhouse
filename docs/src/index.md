# adbc-poolhouse

adbc-poolhouse creates a SQLAlchemy `QueuePool` from a typed warehouse config. One config in, one pool out, with no boilerplate around driver detection or connection string assembly.

## Installation

```bash
pip install adbc-poolhouse
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add adbc-poolhouse
```

## ADBC drivers

adbc-poolhouse manages the pool, not the driver. You also need a driver for your target warehouse. Thirteen of the fourteen backends below run on an ADBC driver; the Databricks Python connector is the exception, and its guide covers what that changes. Install the matching extra with adbc-poolhouse:

| Warehouse | Install command |
|---|---|
| **PyPI drivers** | |
| [Apache Arrow Flight SQL](guides/flightsql.md) | `pip install adbc-poolhouse[flightsql]` |
| [BigQuery](guides/bigquery.md) | `pip install adbc-poolhouse[bigquery]` |
| [Databricks (Python connector, for Lakehouse//RT)](guides/databricks-python.md) | `pip install adbc-poolhouse[databricks-python]` |
| [DuckDB](guides/duckdb.md) | `pip install adbc-poolhouse[duckdb]` |
| [PostgreSQL](guides/postgresql.md) | `pip install adbc-poolhouse[postgresql]` |
| [Quack](guides/quack.md) | `pip install --pre adbc-poolhouse[quack]` |
| [Snowflake](guides/snowflake.md) | `pip install adbc-poolhouse[snowflake]` |
| [SQLite](guides/sqlite.md) | `pip install adbc-poolhouse[sqlite]` |
| **ADBC Driver Foundry drivers** | |
| ClickHouse | See [Foundry installation](guides/clickhouse.md) |
| Databricks | See [Foundry installation](guides/databricks.md) |
| MSSQL / Azure SQL / Fabric | See [Foundry installation](guides/mssql.md) |
| MySQL | See [Foundry installation](guides/mysql.md) |
| Redshift | See [Foundry installation](guides/redshift.md) |
| Trino | See [Foundry installation](guides/trino.md) |

## First pool in five minutes

All supported warehouses have a typed config class.

PyPI-installed: [`BigQueryConfig`][adbc_poolhouse.BigQueryConfig], [`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig], [`DuckDBConfig`][adbc_poolhouse.DuckDBConfig], [`FlightSQLConfig`][adbc_poolhouse.FlightSQLConfig], [`PostgreSQLConfig`][adbc_poolhouse.PostgreSQLConfig], [`QuackConfig`][adbc_poolhouse.QuackConfig], [`SnowflakeConfig`][adbc_poolhouse.SnowflakeConfig], [`SQLiteConfig`][adbc_poolhouse.SQLiteConfig].

Foundry-distributed: [`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig], [`DatabricksConfig`][adbc_poolhouse.DatabricksConfig], [`MSSQLConfig`][adbc_poolhouse.MSSQLConfig], [`MySQLConfig`][adbc_poolhouse.MySQLConfig], [`RedshiftConfig`][adbc_poolhouse.RedshiftConfig], [`TrinoConfig`][adbc_poolhouse.TrinoConfig].

The example below uses DuckDB, which needs no credentials or running server.

```python
from adbc_poolhouse import DuckDBConfig, create_pool, close_pool

# File-backed database (connections share the same file)
config = DuckDBConfig(database="/tmp/warehouse.db")
pool = create_pool(config)

with pool.connect() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT 42 AS answer")
    row = cursor.fetchone()
    print(row)  # (42,)

close_pool(pool)
```

`pool.connect()` checks out a connection from the pool and returns it when the `with` block exits. [`close_pool(pool)`][adbc_poolhouse.close_pool] drains the pool and closes the underlying ADBC source connection.

## Async

For asyncio or trio code, [`create_async_pool`][adbc_poolhouse.create_async_pool], [`managed_async_pool`][adbc_poolhouse.managed_async_pool], and [`close_async_pool`][adbc_poolhouse.close_async_pool] mirror the sync entry points and run each blocking ADBC call on a worker thread. Install the `[async]` extra with `pip install adbc-poolhouse[async]`.

!!! warning "Experimental"
    The async API is experimental. Its surface may change between minor releases, so pin the version you build against. The [async pool guide](guides/async.md) has the full caveat and the rest of the async surface.

```python
import anyio
from adbc_poolhouse import DuckDBConfig, create_async_pool, close_async_pool


async def main():
    pool = create_async_pool(DuckDBConfig(database="/tmp/warehouse.db"))
    try:
        async with await pool.connect() as conn:
            async with conn.cursor() as cur:  # cursor() is synchronous, no await
                await cur.execute("SELECT 42 AS answer")
                table = await cur.fetch_arrow_table()
                print(table.column("answer")[0].as_py())  # 42
    finally:
        await close_async_pool(pool)


anyio.run(main)
```

## What's next

- [Pool lifecycle](guides/pool-lifecycle.md) — how to dispose correctly, pytest fixture patterns, and common mistakes
- [Async pool](guides/async.md) — the asyncio/trio wrapper, its concurrency limits, and the one connection per task rule
- [Consumer patterns](guides/consumer-patterns.md) — wiring a pool into FastAPI and reading credentials from a dbt profiles file
- [Configuration](guides/configuration.md) — environment variable prefixes, pool tuning, and secret handling
- [Snowflake guide](guides/snowflake.md) — supported auth methods and private key variants
- [Warehouse guides](guides/duckdb.md) — per-warehouse install commands, auth examples, and env var prefixes
- [Custom backends](guides/custom-backends.md) — raw driver arguments and writing a reusable config class for an unsupported warehouse

## See also

- [API Reference](reference/adbc_poolhouse.md) — auto-generated from source
- [Changelog](changelog.md)
