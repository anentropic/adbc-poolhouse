# SQLite guide

Install the SQLite extra:

```bash
pip install adbc-poolhouse[sqlite]
```

Or with uv:

```bash
uv add "adbc-poolhouse[sqlite]"
```

## Connection

`SQLiteConfig` supports file-backed and in-memory databases.

For a pool with more than one connection, use a file path. In-memory SQLite is shared across all connections in the pool — unlike DuckDB, where each connection gets its own isolated database.

### File-backed

```python
from adbc_poolhouse import SQLiteConfig, create_pool

config = SQLiteConfig(database="/tmp/warehouse.db")
pool = create_pool(config)
```

### In-memory

`pool_size` must be `1` for in-memory databases. All connections in the pool share the same in-memory database — unlike DuckDB, where each connection gets its own isolated database. A pool with `pool_size > 1` and `:memory:` raises `ValidationError`.

```python
config = SQLiteConfig(database=":memory:")
pool = create_pool(config)
```

## Loading from environment variables

`SQLiteConfig` reads all fields from environment variables with the `SQLITE_` prefix:

```bash
export SQLITE_DATABASE=/data/warehouse.db
export SQLITE_POOL_SIZE=3
```

```python
config = SQLiteConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
