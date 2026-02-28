# DuckDB guide

Install the DuckDB extra:

```bash
pip install adbc-poolhouse[duckdb]
```

Or with uv:

```bash
uv add "adbc-poolhouse[duckdb]"
```

## Connection

`DuckDBConfig` supports file-backed and in-memory databases.

For a pool with more than one connection, use a file path. Each in-memory connection gets its own isolated database — sharing state across connections is not possible with `:memory:`.

### File-backed

```python
from adbc_poolhouse import DuckDBConfig, create_pool

config = DuckDBConfig(database="/tmp/warehouse.db")
pool = create_pool(config)
```

### In-memory (single connection)

`pool_size` is forced to `1` for in-memory databases. Requesting a larger pool would give each connection its own empty database, which is almost always unintended.

```python
config = DuckDBConfig(database=":memory:")
pool = create_pool(config)
```

### Read-only

```python
config = DuckDBConfig(database="/data/warehouse.db", read_only=True)
pool = create_pool(config)
```

## Loading from environment variables

`DuckDBConfig` reads all fields from environment variables with the `DUCKDB_` prefix:

```bash
export DUCKDB_DATABASE=/data/warehouse.db
export DUCKDB_READ_ONLY=false
```

```python
config = DuckDBConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
