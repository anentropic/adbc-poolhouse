# adbc-poolhouse

adbc-poolhouse creates a SQLAlchemy `QueuePool` from a typed warehouse config. One config in, one pool out — no boilerplate around driver detection or connection string assembly.

## Installation

```bash
pip install adbc-poolhouse
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add adbc-poolhouse
```

## ADBC drivers

adbc-poolhouse manages the pool, not the driver. You also need an ADBC driver for your target warehouse. Install the matching extra with adbc-poolhouse:

| Warehouse | Install command |
|---|---|
| **PyPI drivers** | |
| Apache Arrow Flight SQL | `pip install adbc-poolhouse[flightsql]` |
| BigQuery | `pip install adbc-poolhouse[bigquery]` |
| DuckDB | `pip install adbc-poolhouse[duckdb]` |
| PostgreSQL | `pip install adbc-poolhouse[postgresql]` |
| Quack | `pip install --pre adbc-poolhouse[quack]` |
| Snowflake | `pip install adbc-poolhouse[snowflake]` |
| SQLite | `pip install adbc-poolhouse[sqlite]` |
| **Foundry-distributed drivers** | |
| ClickHouse | Foundry-distributed — see [Foundry installation](guides/clickhouse.md) |
| Databricks | Foundry-distributed — see [Foundry installation](guides/databricks.md) |
| MSSQL / Azure SQL / Fabric | Foundry-distributed — see [Foundry installation](guides/mssql.md) |
| MySQL | Foundry-distributed — see [Foundry installation](guides/mysql.md) |
| Redshift | Foundry-distributed — see [Foundry installation](guides/redshift.md) |
| Trino | Foundry-distributed — see [Foundry installation](guides/trino.md) |

## First pool in five minutes

All supported warehouses have a typed config class.

PyPI-installed: `BigQueryConfig`, `DuckDBConfig`, `FlightSQLConfig`, `PostgreSQLConfig`, `QuackConfig`, `SnowflakeConfig`, `SQLiteConfig`.

Foundry-distributed: `ClickHouseConfig`, `DatabricksConfig`, `MSSQLConfig`, `MySQLConfig`, `RedshiftConfig`, `TrinoConfig`.

The example below uses DuckDB — no credentials or running server required.

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

`pool.connect()` checks out a connection from the pool and returns it when the `with` block exits. `close_pool(pool)` drains the pool and closes the underlying ADBC source connection.

## Async

For asyncio or trio code, `create_async_pool`, `managed_async_pool`, and `close_async_pool` mirror the sync entry points and run each blocking ADBC call on a worker thread. Install the `[async]` extra (`pip install adbc-poolhouse[async]`) and see the [async pool guide](guides/async.md).

```python
import anyio
from adbc_poolhouse import DuckDBConfig, create_async_pool, close_async_pool


async def main():
    pool = create_async_pool(DuckDBConfig(database="/tmp/warehouse.db"))
    try:
        async with await pool.connect() as conn:
            cur = conn.cursor()  # synchronous, no await
            await cur.execute("SELECT 42 AS answer")
            table = await cur.fetch_arrow_table()
            print(table.column("answer")[0].as_py())  # 42
    finally:
        await close_async_pool(pool)


anyio.run(main)
```

## What's next

- [Pool lifecycle](guides/pool-lifecycle.md) — how to dispose correctly, pytest fixture patterns, and common mistakes
- [Async pool](guides/async.md) — the asyncio/trio wrapper, honest concurrency limits, and the one connection per task rule
- [Consumer patterns](guides/consumer-patterns.md) — wiring a pool into FastAPI and reading credentials from a dbt profiles file
- [Configuration reference](guides/configuration.md) — environment variable prefixes, pool tuning, and secret handling
- [Snowflake guide](guides/snowflake.md) — supported auth methods and private key variants
- [Warehouse guides](guides/duckdb.md) — per-warehouse install commands, auth examples, and env var prefixes

## See also

- [API Reference](reference/) — auto-generated from source
- [Changelog](changelog.md)
