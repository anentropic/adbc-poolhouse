# ClickHouse guide

The ClickHouse ADBC driver is distributed via the ADBC Driver Foundry, not PyPI.
Follow the [Foundry installation guide](https://arrow.apache.org/adbc/current/driver/installation.html) to install it before using [`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig].

The driver is currently in alpha. Use the `--pre` flag when installing:

```bash
dbc install --pre clickhouse
```

`adbc-poolhouse` does not need a separate extra for ClickHouse:

```bash
pip install adbc-poolhouse
```

## Connection

[`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig] connects to a ClickHouse server. Specify the connection in one of two
ways: a full URI or individual fields (`host` and `username` together, with optional
`password`, `database`, and `port`).

Construction raises [`ConfigurationError`][adbc_poolhouse.ConfigurationError] if neither mode is fully specified.

### URI mode

```python
from pydantic import SecretStr

from adbc_poolhouse import ClickHouseConfig, create_pool

config = ClickHouseConfig(
    uri=SecretStr("http://default:password@localhost:8123/mydb"),  # pragma: allowlist secret
)
pool = create_pool(config)
```

### Individual fields

```python
from adbc_poolhouse import ClickHouseConfig, create_pool

config = ClickHouseConfig(
    host="localhost",
    username="default",
    password="password",  # pragma: allowlist secret
    database="mydb",
)
pool = create_pool(config)
```

`password` and `database` are optional. `port` defaults to `8123` (HTTP interface).

The field name is `username`, not `user`. The Columnar ClickHouse driver uses `username`
as the connection kwarg. Passing the wrong key causes a silent authentication failure.

## Loading from environment variables

[`ClickHouseConfig`][adbc_poolhouse.ClickHouseConfig] reads all fields from environment variables with the `CLICKHOUSE_` prefix:

```bash
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_USERNAME=default
export CLICKHOUSE_PASSWORD=password  # pragma: allowlist secret
export CLICKHOUSE_DATABASE=mydb
```

```python
config = ClickHouseConfig()  # reads from env
pool = create_pool(config)
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
