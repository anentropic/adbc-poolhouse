# MySQL guide

MySQL uses the Columnar ADBC MySQL driver, distributed via the ADBC Driver Foundry.

## Install

Install the `dbc` CLI and the MySQL driver:

```bash
just install-dbc
just install-foundry-drivers
```

See the Foundry Driver Management section in [DEVELOP.md](https://github.com/anentropic/adbc-poolhouse/blob/main/DEVELOP.md) for setup details.

## Connection

`MySQLConfig` supports two connection modes.

### URI mode

```python
from pydantic import SecretStr
from adbc_poolhouse import MySQLConfig, create_pool

config = MySQLConfig(uri=SecretStr("root:password@tcp(localhost:3306)/mydb"))
pool = create_pool(config)
```

### Decomposed fields

```python
from pydantic import SecretStr
from adbc_poolhouse import MySQLConfig, create_pool

config = MySQLConfig(
    host="localhost",
    user="root",
    password=SecretStr("password"),
    database="mydb",
)
pool = create_pool(config)
```

`password` is optional — MySQL supports passwordless connections. `port` defaults to `3306`.

## Loading from environment variables

`MySQLConfig` reads all fields from environment variables with the `MYSQL_` prefix:

```bash
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=password
export MYSQL_DATABASE=mydb
```

```python
config = MySQLConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
