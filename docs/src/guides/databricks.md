# Databricks guide

The Databricks ADBC driver is distributed via the ADBC Driver Foundry, not PyPI.
Follow the [Foundry installation guide](https://arrow.apache.org/adbc/current/driver/installation.html) to install it before using `DatabricksConfig`.

`adbc-poolhouse` does not need a separate extra for Databricks:

```bash
pip install adbc-poolhouse
```

## Connection

`DatabricksConfig` connects to a Databricks SQL warehouse or all-purpose cluster
using a personal access token (PAT). Specify the connection as a URI or via
decomposed fields.

### URI

```python
from adbc_poolhouse import DatabricksConfig, create_pool

config = DatabricksConfig(
    uri="databricks://token:dapi...@adb-xxx.azuredatabricks.net:443/sql/1.0/warehouses/abc123",  # pragma: allowlist secret
)
pool = create_pool(config)
```

### Decomposed fields

```python
config = DatabricksConfig(
    host="adb-xxx.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/abc123",
    token="dapi...",  # pragma: allowlist secret
)
pool = create_pool(config)
```

## Loading from environment variables

`DatabricksConfig` reads all fields from environment variables with the `DATABRICKS_` prefix:

```bash
export DATABRICKS_HOST=adb-xxx.azuredatabricks.net
export DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/abc123
export DATABRICKS_TOKEN=dapi...
```

```python
config = DatabricksConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
