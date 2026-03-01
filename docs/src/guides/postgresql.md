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

### URI mode

```python
from adbc_poolhouse import PostgreSQLConfig, create_pool

config = PostgreSQLConfig(
    uri="postgresql://me:s3cret@db.example.com:5432/mydb?sslmode=require",  # pragma: allowlist secret
)
pool = create_pool(config)
```

### Individual fields

```python
from adbc_poolhouse import PostgreSQLConfig, create_pool

config = PostgreSQLConfig(
    host="db.example.com",
    user="me",
    password="s3cret",  # pragma: allowlist secret
    database="mydb",
    sslmode="require",
)
pool = create_pool(config)
```

`port` defaults to 5432 when omitted. `password` and `sslmode` are optional.

## Loading from environment variables

`PostgreSQLConfig` reads fields from environment variables with the `POSTGRESQL_` prefix:

```bash
export POSTGRESQL_HOST=db.example.com
export POSTGRESQL_USER=me
export POSTGRESQL_PASSWORD=s3cret  # pragma: allowlist secret
export POSTGRESQL_DATABASE=mydb
```

```python
config = PostgreSQLConfig()  # reads from env
pool = create_pool(config)
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
