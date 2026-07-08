# Databricks Python connector guide

[`DatabricksPythonConfig`][adbc_poolhouse.DatabricksPythonConfig] connects to Databricks
through the `databricks-sql-connector` package instead of the ADBC driver, using
the connector's Statement Execution ("kernel") path rather than Thrift.

Most workloads should use [`DatabricksConfig`][adbc_poolhouse.DatabricksConfig], which
runs on the ADBC driver and is the default choice for SQL warehouses. Reach for
`DatabricksPythonConfig` only when you need the non-Thrift path, in particular
**Lakehouse//RT**, which [rejects the Thrift protocol](https://docs.databricks.com/aws/en/compute/sql-warehouse/real-time#connectivity) that the ADBC and ODBC
drivers use. If you are not targeting Lakehouse//RT, prefer
[`DatabricksConfig`][adbc_poolhouse.DatabricksConfig].

## Installation

This backend needs the `databricks-python` extra, which pulls in
`databricks-sql-connector` (with PyArrow):

```bash
pip install "adbc-poolhouse[databricks-python]"
```

OAuth machine-to-machine auth additionally needs `databricks-sdk`, which the
connector itself does not require. When you use that auth method, install the
`databricks-python-m2m` extra instead — it adds the SDK on top of everything above:

```bash
pip install "adbc-poolhouse[databricks-python-m2m]"
```

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
`client_secret`. This mode needs the `databricks-python-m2m` extra (see
[Installation](#installation)). The credentials provider is built lazily when the
pool opens a connection, so constructing the config does no network work; if
`databricks-sdk` is not installed, that first connection fails with an error
pointing you at the extra:

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

## Pool lifecycle and tuning

`DatabricksPythonConfig` builds an ordinary pool, so
[`create_pool`][adbc_poolhouse.create_pool],
[`managed_pool`][adbc_poolhouse.managed_pool], and
[`close_pool`][adbc_poolhouse.close_pool] work exactly as they do for the ADBC
backends:

```python
from pydantic import SecretStr
from adbc_poolhouse import DatabricksPythonConfig, create_pool, close_pool

config = DatabricksPythonConfig(
    host="adb-xxx.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/abc123",
    token=SecretStr("dapi..."),  # pragma: allowlist secret
    pool_size=10,
    max_overflow=5,
)
pool = create_pool(config)
try:
    with pool.connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1")
finally:
    close_pool(pool)
```

The pool-tuning fields (`pool_size`, `max_overflow`, `timeout`, `recycle`,
`pre_ping`) are inherited from
[`BaseWarehouseConfig`][adbc_poolhouse.BaseWarehouseConfig] and behave the same on
this connector-backed pool as on the ADBC backends. One connector session opens per
pooled connection, so the checkout ceiling is `pool_size + max_overflow`. Size it
against the Databricks warehouse's own connection limit. See
[Pool tuning](configuration.md#pool-tuning) for the field defaults and
[Sizing under load](configuration.md#sizing-under-load) for tuning under concurrency.

## Cursor surface

Pooled connections present the ADBC DBAPI cursor, the same interface the ADBC
backends expose. The connector is Arrow-native, so the Arrow accessors return
real PyArrow objects:

```python
pool = create_pool(config)  # config from any of the examples above
with pool.connect() as conn:
    cur = conn.cursor()
    cur.execute("SELECT 1 AS n")
    table = cur.fetch_arrow_table()  # pyarrow.Table
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

## Async

The async entry points work with this backend too.
[`create_async_pool`][adbc_poolhouse.create_async_pool],
[`managed_async_pool`][adbc_poolhouse.managed_async_pool], and
[`close_async_pool`][adbc_poolhouse.close_async_pool] accept a
`DatabricksPythonConfig` the same way they accept an ADBC config, running each
blocking connector call on a worker thread:

```python
import anyio
from pydantic import SecretStr
from adbc_poolhouse import DatabricksPythonConfig, create_async_pool, close_async_pool


async def main():
    config = DatabricksPythonConfig(
        host="adb-xxx.azuredatabricks.net",
        http_path="/sql/1.0/warehouses/abc123",
        token=SecretStr("dapi..."),  # pragma: allowlist secret
    )
    pool = create_async_pool(config)
    try:
        async with await pool.connect() as conn:
            cur = conn.cursor()  # synchronous, no await
            await cur.execute("SELECT 1")
            table = await cur.fetch_arrow_table()
    finally:
        await close_async_pool(pool)


anyio.run(main)
```

The method-support rules carry over: the ADBC-only methods listed under
[Unsupported methods](#unsupported-methods) raise `NotSupportedError` on the async
surface as well, because the async cursor offloads to the same connector. Install the
`[async]` extra and see the [async pool guide](async.md) for the concurrency model and
the experimental-API caveat.

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
- [Async pool](async.md) — the asyncio/trio wrapper and its concurrency model
