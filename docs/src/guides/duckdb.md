# DuckDB guide

## Installation

Install the DuckDB extra:

```bash
pip install adbc-poolhouse[duckdb]
```

Or with uv:

```bash
uv add "adbc-poolhouse[duckdb]"
```

## Connection

[`DuckDBConfig`][adbc_poolhouse.DuckDBConfig] supports file-backed and in-memory databases.

Both default to a pool of 5 connections. The pool clones every connection from one source connection, so they all open the same database. With `:memory:` that means one in-memory database shared by the whole pool: a table one connection creates and commits is visible to the others, including connections the pool opens later to replace recycled ones. The database lasts until you close the pool.

### File-backed

```python
from adbc_poolhouse import DuckDBConfig, create_pool

config = DuckDBConfig(database="/tmp/warehouse.db")
pool = create_pool(config)
```

### In-memory

Set up tables and data once, on any connection, and commit. ADBC connections start with autocommit off, so other connections see nothing until you commit.

```python
config = DuckDBConfig(database=":memory:")
pool = create_pool(config)

with pool.connect() as conn:
    cur = conn.cursor()
    cur.execute("CREATE TABLE events AS SELECT 1 AS id")
    cur.close()
    conn.commit()
```

Temporary tables and connection-level settings such as `SET search_path` still belong to one connection, as they do with a file-backed database.

### Read-only

```python
config = DuckDBConfig(database="/data/warehouse.db", read_only=True)
pool = create_pool(config)
```

## Loading from environment variables

[`DuckDBConfig`][adbc_poolhouse.DuckDBConfig] reads all fields from environment variables with the `DUCKDB_` prefix:

```bash
export DUCKDB_DATABASE=/data/warehouse.db
export DUCKDB_READ_ONLY=false
```

```python
config = DuckDBConfig()  # reads from env
```

## See also

- [Configuration](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
