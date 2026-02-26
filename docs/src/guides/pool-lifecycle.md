# Pool lifecycle

`create_pool` returns a SQLAlchemy `QueuePool`. Internally it holds one ADBC source connection plus a pool of cloned connections derived from it. The source connection is attached to the pool as `pool._adbc_source` so you can close it after draining the pool.

## Checking out and returning connections

Use `pool.connect()` as a context manager. The connection returns to the pool when the `with` block exits — whether it exits normally or raises.

```python
with pool.connect() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT now()")
    row = cursor.fetchone()
```

Do not hold a connection outside a `with` block. Connections held past the `with` block are never returned to the pool and the pool will run out of available connections once they are all checked out.

## Disposing the pool

To shut down cleanly, call `pool.dispose()` then `pool._adbc_source.close()`:

```python
pool.dispose()
pool._adbc_source.close()
```

`pool.dispose()` drains the pool and closes each pooled connection. The ADBC source connection that the pool was built from is a separate object — it stays open until you close it explicitly. Skipping `pool._adbc_source.close()` leaves a file handle or network socket open until the process exits.

## Pytest fixture pattern

For test suites, create the pool once per session and dispose it in the fixture teardown:

```python
import pytest
from adbc_poolhouse import DuckDBConfig, create_pool


@pytest.fixture(scope="session")
def pool():
    p = create_pool(DuckDBConfig(database="/tmp/test.db"))
    yield p
    p.dispose()
    p._adbc_source.close()
```

Using `scope="session"` creates one pool for the entire test session. If your tests need isolation between test functions, use `scope="function"` instead — each test gets its own pool.

## Common mistakes

**Not closing `_adbc_source` after `dispose()`**

`pool.dispose()` does not close the source connection. Always follow it with `pool._adbc_source.close()`.

**Using `database=":memory:"` with `pool_size > 1`**

Each DuckDB connection cloned from an in-memory source gets its own isolated empty database. `create_pool` raises `ValueError` if you pass `pool_size > 1` with an in-memory database to prevent this silent data-loss bug. Use a file-backed database when you need multiple connections.

**Holding connections outside the `with` block**

If you call `pool.connect()` without a context manager, the connection is checked out and never returned:

```python
# Wrong — connection is never returned to the pool
conn = pool.connect()
cursor = conn.cursor()
cursor.execute("SELECT 1")
```

The pool will exhaust its connections and subsequent `pool.connect()` calls will block until the timeout.

## See also

- [Consumer patterns](consumer-patterns.md) — FastAPI lifespan and dbt profiles examples
- [Configuration reference](configuration.md) — pool_size, max_overflow, timeout, recycle
