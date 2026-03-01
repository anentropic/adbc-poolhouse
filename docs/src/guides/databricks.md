# Databricks guide

The Databricks ADBC driver is distributed via the ADBC Driver Foundry, not PyPI.
Follow the [Foundry installation guide](https://arrow.apache.org/adbc/current/driver/installation.html) to install it before using `DatabricksConfig`.

`adbc-poolhouse` does not need a separate extra for Databricks:

```bash
pip install adbc-poolhouse
```

## Connection

`DatabricksConfig` connects to a Databricks SQL warehouse or all-purpose cluster
using a personal access token (PAT). You must specify the connection in one of two
ways: a full URI or individual fields (`host`, `http_path`, and `token` together).

Construction raises `ConfigurationError` if neither mode is fully specified.

### URI mode

```python
from adbc_poolhouse import DatabricksConfig, create_pool

config = DatabricksConfig(
    uri="databricks://token:dapi...@adb-xxx.azuredatabricks.net:443/sql/1.0/warehouses/abc123",  # pragma: allowlist secret
)
pool = create_pool(config)
```

### Individual fields

Set `host`, `http_path`, and `token` together. The driver constructs the URI
internally, percent-encoding the token so that special characters (`+`, `=`, `/`)
do not corrupt the connection string.

```python
from pydantic import SecretStr
from adbc_poolhouse import DatabricksConfig, create_pool

config = DatabricksConfig(
    host="adb-xxx.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/abc123",
    token=SecretStr("dapi..."),  # pragma: allowlist secret
)
pool = create_pool(config)
```

## Loading from environment variables

`DatabricksConfig` reads all fields from environment variables with the `DATABRICKS_` prefix.
For individual field mode, all three variables must be set at the same time — setting only
`DATABRICKS_HOST` or `DATABRICKS_TOKEN` alone causes `ConfigurationError` at construction.

```bash
export DATABRICKS_HOST=adb-xxx.azuredatabricks.net
export DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/abc123
export DATABRICKS_TOKEN=dapi...  # pragma: allowlist secret
```

```python
config = DatabricksConfig()  # reads host, http_path, and token from env
pool = create_pool(config)
```

For URI mode, set `DATABRICKS_URI` instead of the three individual variables.

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
