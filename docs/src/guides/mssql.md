# MSSQL guide

The MSSQL ADBC driver is distributed via the ADBC Driver Foundry, not PyPI.
Follow the [Foundry installation guide](https://arrow.apache.org/adbc/current/driver/installation.html) to install it before using [`MSSQLConfig`][adbc_poolhouse.MSSQLConfig].

`adbc-poolhouse` does not need a separate extra for MSSQL:

```bash
pip install adbc-poolhouse
```

[`MSSQLConfig`][adbc_poolhouse.MSSQLConfig] covers Microsoft SQL Server, Azure SQL Database, Azure SQL Managed
Instance, Azure Synapse Analytics, and Azure Fabric SQL endpoint.

## Connection

### URI mode

```python
from adbc_poolhouse import MSSQLConfig, create_pool

config = MSSQLConfig(
    uri="sqlserver://me:s3cret@myserver.database.windows.net:1433?database=mydb",  # pragma: allowlist secret
)
pool = create_pool(config)
```

### Individual fields

```python
from adbc_poolhouse import MSSQLConfig, create_pool

config = MSSQLConfig(
    host="myserver.database.windows.net",
    user="me",
    password="s3cret",  # pragma: allowlist secret
    database="mydb",
)
pool = create_pool(config)
```

## Loading from environment variables

[`MSSQLConfig`][adbc_poolhouse.MSSQLConfig] reads all fields from environment variables with the `MSSQL_` prefix:

```bash
export MSSQL_HOST=myserver.database.windows.net
export MSSQL_USER=me
export MSSQL_PASSWORD=s3cret  # pragma: allowlist secret
export MSSQL_DATABASE=mydb
```

```python
from adbc_poolhouse import MSSQLConfig, create_pool

config = MSSQLConfig()  # reads from env
pool = create_pool(config)
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning, Foundry backends
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
