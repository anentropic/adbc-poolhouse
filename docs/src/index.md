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

## First pool in five minutes

The example below uses DuckDB — no credentials or running server required.

```python
from adbc_poolhouse import DuckDBConfig, create_pool

# File-backed database (connections share the same file)
config = DuckDBConfig(database="/tmp/warehouse.db")
pool = create_pool(config)

with pool.connect() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT 42 AS answer")
    row = cursor.fetchone()
    print(row)  # (42,)

pool.dispose()
pool._adbc_source.close()
```

`pool.connect()` checks out a connection from the pool and returns it when the `with` block exits. `pool.dispose()` drains the pool; `pool._adbc_source.close()` releases the underlying ADBC source connection that the pool holds internally.

## What's next

- [Pool lifecycle](guides/pool-lifecycle.md) — how to dispose correctly, pytest fixture patterns, and common mistakes
- [Consumer patterns](guides/consumer-patterns.md) — wiring a pool into FastAPI and reading credentials from a dbt profiles file
- [Configuration reference](guides/configuration.md) — environment variable prefixes, pool tuning, and secret handling
- [Snowflake guide](guides/snowflake.md) — supported auth methods and private key variants

## See also

- [API Reference](reference/) — auto-generated from source
- [Changelog](changelog.md)
