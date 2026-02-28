# PostgreSQL guide

Install the PostgreSQL extra:

```bash
pip install adbc-poolhouse[postgresql]
```

Or with uv:

```bash
uv add "adbc-poolhouse[postgresql]"
```

## Connection

`PostgreSQLConfig` takes a single `uri` field. All connection parameters — host, port, user, password, database, and SSL mode — are embedded in the URI.

```python
from adbc_poolhouse import PostgreSQLConfig, create_pool

config = PostgreSQLConfig(
    uri="postgresql://me:s3cret@db.example.com:5432/mydb?sslmode=require",  # pragma: allowlist secret
)
pool = create_pool(config)
```

## Loading from environment variables

`PostgreSQLConfig` reads fields from environment variables with the `POSTGRESQL_` prefix:

```bash
export POSTGRESQL_URI=postgresql://me:password@db.example.com:5432/mydb  # pragma: allowlist secret
```

```python
config = PostgreSQLConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
