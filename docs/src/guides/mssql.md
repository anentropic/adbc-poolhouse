# MSSQL guide

The MSSQL ADBC driver is distributed via the ADBC Driver Foundry, not PyPI.
Follow your Foundry installation guide to install it before using `MSSQLConfig`.

`adbc-poolhouse` does not need a separate extra for MSSQL:

```bash
pip install adbc-poolhouse
```

`MSSQLConfig` covers Microsoft SQL Server, Azure SQL Database, Azure SQL Managed
Instance, Azure Synapse Analytics, and Azure Fabric SQL endpoint.

## Loading from environment variables

`MSSQLConfig` reads all fields from environment variables with the `MSSQL_` prefix:

```bash
export MSSQL_HOST=myserver.database.windows.net
export MSSQL_USER=me
export MSSQL_PASSWORD=s3cret  # pragma: allowlist secret
export MSSQL_DATABASE=mydb
```

```python
from adbc_poolhouse import MSSQLConfig

config = MSSQLConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning, Foundry backends
- [API Reference](../reference/) — full MSSQLConfig field listing
