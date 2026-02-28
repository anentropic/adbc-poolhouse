# Configuration reference

All config classes in adbc-poolhouse are Pydantic `BaseSettings` models. Fields can be set by passing keyword arguments or by reading from environment variables using a warehouse-specific prefix.

## Environment variable prefixes

Each config class reads its fields from environment variables with a prefix matching the warehouse name:

| Config class | env_prefix |
|---|---|
| `DuckDBConfig` | `DUCKDB_` |
| `SnowflakeConfig` | `SNOWFLAKE_` |
| `BigQueryConfig` | `BIGQUERY_` |
| `PostgreSQLConfig` | `POSTGRESQL_` |
| `FlightSQLConfig` | `FLIGHTSQL_` |
| `DatabricksConfig` | `DATABRICKS_` |
| `RedshiftConfig` | `REDSHIFT_` |
| `TrinoConfig` | `TRINO_` |
| `MSSQLConfig` | `MSSQL_` |

For example, setting `SNOWFLAKE_ACCOUNT=myorg-myaccount` in the environment is equivalent to passing `account="myorg-myaccount"` to `SnowflakeConfig(...)`.

To create a pool from environment variables only, call the config class with no arguments:

```python
import os
from adbc_poolhouse import SnowflakeConfig, create_pool

os.environ["SNOWFLAKE_ACCOUNT"] = "myorg-myaccount"
os.environ["SNOWFLAKE_USER"] = "me"
os.environ["SNOWFLAKE_PASSWORD"] = "..."

config = SnowflakeConfig()  # reads all fields from env
pool = create_pool(config)
```

## Pool tuning

All config classes inherit pool tuning fields from `BaseWarehouseConfig`. These also load from environment variables using the same warehouse prefix:

| Field | Default | Description |
|---|---|---|
| `pool_size` | `5` | Number of connections to keep open (DuckDB defaults to `1`) |
| `max_overflow` | `3` | Extra connections allowed when pool is full |
| `timeout` | `30` | Seconds to wait for a connection before raising |
| `recycle` | `3600` | Seconds before a connection is closed and replaced |
| `pre_ping` | `False` | Ping connections before checkout. Disabled by default — does not function on standalone `QueuePool` without a SQLAlchemy dialect; use `recycle` for connection health. |

To override pool size via environment variable:

```bash
export SNOWFLAKE_POOL_SIZE=10
export SNOWFLAKE_MAX_OVERFLOW=5
```

## Secret fields

Fields like `password`, `private_key_pem`, and `token` are `SecretStr` values. They are masked in `repr()` output to avoid leaking credentials in logs:

```python
config = SnowflakeConfig(account="myorg", user="me", password="s3cret")
print(config.password)  # **********
print(config.password.get_secret_value())  # s3cret
```

Call `.get_secret_value()` when you need the raw string — for example, passing credentials to a driver.

## Foundry-distributed backends

`DatabricksConfig`, `RedshiftConfig`, `TrinoConfig`, and `MSSQLConfig` are present in the package but their ADBC drivers are not available on PyPI. They are distributed through the ADBC Driver Foundry. If you use one of these backends, follow the installation guide for your Foundry setup to get the correct driver package installed.

## See also

- [Snowflake guide](snowflake.md) — JWT, OAuth, and private key configuration
- [API Reference](../reference/) — full field listing per config class
