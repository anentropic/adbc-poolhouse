# adbc-poolhouse

One config in, one pool out — `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy QueuePool.

## Installation

```bash
pip install adbc-poolhouse
```

Driver extras are available for each supported warehouse (DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL). See the [documentation](https://anentropic.github.io/adbc-poolhouse/) for the full list.

## Quick example

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

## Supported warehouses

DuckDB, Snowflake, BigQuery, PostgreSQL, FlightSQL, Databricks, Redshift, Trino, MSSQL / Azure SQL / Fabric.

## Links

- [Documentation](https://anentropic.github.io/adbc-poolhouse/)
- [Changelog](https://anentropic.github.io/adbc-poolhouse/changelog/)
- [Source](https://github.com/anentropic/adbc-poolhouse)
- [PyPI](https://pypi.org/project/adbc-poolhouse/)

## License

MIT
