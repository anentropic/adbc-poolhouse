# Databricks Python connector guide

[`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig] connects to Databricks
through the `databricks-sql-connector` package instead of the ADBC driver, using
the connector's Statement Execution ("kernel") path rather than Thrift.

Most workloads should use [`DatabricksConfig`][adbc_poolhouse.DatabricksConfig], which
runs on the ADBC driver and is the default choice for SQL warehouses. Reach for
`DatabricksPythonConfig` only when you need the non-Thrift path — in particular
**Lakehouse//RT**, which rejects Thrift and does not accept ADBC or ODBC
connections at all. If you are not targeting Lakehouse//RT, prefer
[`DatabricksConfig`][adbc_poolhouse.DatabricksConfig].

## Installation

This backend needs the `databricks-python` extra:

```bash
pip install "adbc-poolhouse[databricks-python]"
```

The extra pulls in `databricks-sql-connector` (with PyArrow) and `databricks-sdk`.
The SDK is only used to build OAuth machine-to-machine credentials.

## Connection

Set `host` and `http_path`, plus one auth method. Construction raises
[`ConfigurationError`][adbc_poolhouse.ConfigurationError] when the host, the HTTP path,
or a usable auth method is missing.

### Personal access token

```python
from pydantic import SecretStr
from adbc_poolhouse import DatabricksPythonConfig, create_pool

config = DatabricksPythonConfig(
    host="adb-xxx.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/abc123",
    token=SecretStr("dapi..."),  # pragma: allowlist secret
)
pool = create_pool(config)
```

### OAuth (user-to-machine)

The browser-based flow needs no secret. Set `auth_type="OAuthU2M"`:

```python
config = DatabricksPythonConfig(
    host="adb-xxx.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/abc123",
    auth_type="OAuthU2M",
)
```

### OAuth (machine-to-machine)

For a service principal, set `auth_type="OAuthM2M"` with `client_id` and
`client_secret`. The credentials provider is built lazily when the pool opens a
connection, so constructing the config does no network work:

```python
from pydantic import SecretStr

config = DatabricksPythonConfig(
    host="adb-xxx.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/abc123",
    auth_type="OAuthM2M",
    client_id="my-service-principal-id",
    client_secret=SecretStr("..."),  # pragma: allowlist secret
)
```

For cases the built-in modes do not cover, such as an Azure service principal or a
provider you construct yourself, pass a `credentials_provider` callable. It goes
to the connector unchanged:

```python
config = DatabricksPythonConfig(
    host="adb-xxx.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/abc123",
    credentials_provider=my_provider,
)
```

### Default catalog and schema

Set `catalog` and `schema` to pin a default namespace, so unqualified table names
resolve against it:

```python
config = DatabricksPythonConfig(
    host="adb-xxx.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/abc123",
    token=SecretStr("dapi..."),  # pragma: allowlist secret
    catalog="main",
    schema="sales",
)
```

## Cursor surface

Pooled connections present the ADBC DBAPI cursor, the same interface the ADBC
backends expose. The connector is Arrow-native, so the Arrow accessors return
real PyArrow objects:

```python
with pool.connect() as conn:
    cur = conn.cursor()
    cur.execute("SELECT 1 AS n")
    table = cur.fetch_arrow_table()          # pyarrow.Table
    # or stream: cur.fetch_record_batch()    # pyarrow.RecordBatchReader
```

`execute`, `executemany`, `fetchone`, `fetchmany`, `fetchall`,
`fetch_arrow_table`, `fetchallarrow`, `fetch_record_batch`, `fetch_df`,
`fetch_polars`, and `adbc_cancel` all work.

### Unsupported methods

The connector has no equivalent for a few ADBC-only cursor and connection methods.
Calling one raises `adbc_driver_manager.dbapi.NotSupportedError`:

- `fetch_arrow` — returns a raw Arrow C-stream handle; use `fetch_record_batch` instead.
- `adbc_ingest` — the connector has no Arrow bulk-ingest path; write with SQL `INSERT` or `COPY INTO`.
- `adbc_prepare`, `adbc_execute_schema`.
- `adbc_execute_partitions`, `adbc_read_partition`.
- Connection metadata methods: `adbc_get_info`, `adbc_get_objects`, `adbc_get_table_schema`, `adbc_get_table_types`.

## Loading from environment variables

[`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig] reads its fields from
environment variables with the `DATABRICKS_PYTHON_` prefix, a separate namespace
from the `DATABRICKS_` prefix that [`DatabricksConfig`][adbc_poolhouse.DatabricksConfig]
uses:

```bash
export DATABRICKS_PYTHON_HOST=adb-xxx.azuredatabricks.net
export DATABRICKS_PYTHON_HTTP_PATH=/sql/1.0/warehouses/abc123
export DATABRICKS_PYTHON_TOKEN=dapi...  # pragma: allowlist secret
```

```python
config = DatabricksPythonConfig()  # reads host, http_path, and token from env
pool = create_pool(config)
```

## See also

- [Databricks guide](databricks.md) — the ADBC driver backend, the default for SQL warehouses
- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
