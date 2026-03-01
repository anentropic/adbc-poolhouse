# MySQL guide

The MySQL ADBC driver is distributed via the ADBC Driver Foundry, not PyPI.
Follow the [Foundry installation guide](https://arrow.apache.org/adbc/current/driver/installation.html) to install it before using [`MySQLConfig`][adbc_poolhouse.MySQLConfig].

`adbc-poolhouse` does not need a separate extra for MySQL:

```bash
pip install adbc-poolhouse
```

## Connection

[`MySQLConfig`][adbc_poolhouse.MySQLConfig] connects to a MySQL server. You must specify the connection in one of two
ways: a full URI or individual fields (`host` and `user` together, with optional
`password`, `database`, and `port`).

Construction raises [`ConfigurationError`][adbc_poolhouse.ConfigurationError] if neither mode is fully specified.

### URI mode

```python
from adbc_poolhouse import MySQLConfig, create_pool

config = MySQLConfig(
    uri="root:password@tcp(localhost:3306)/mydb",  # pragma: allowlist secret
)
pool = create_pool(config)
```

### Individual fields

```python
from adbc_poolhouse import MySQLConfig, create_pool

config = MySQLConfig(
    host="localhost",
    user="root",
    password="password",  # pragma: allowlist secret
    database="mydb",
)
pool = create_pool(config)
```

`password` is optional — MySQL supports passwordless connections. `port` defaults to `3306`.

## Loading from environment variables

[`MySQLConfig`][adbc_poolhouse.MySQLConfig] reads all fields from environment variables with the `MYSQL_` prefix:

```bash
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=password  # pragma: allowlist secret
export MYSQL_DATABASE=mydb
```

```python
config = MySQLConfig()  # reads from env
pool = create_pool(config)
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
