# Custom backends

adbc-poolhouse ships config classes for 12 ADBC backends. If your driver is not
on that list you have two options: pass
[raw driver arguments](configuration.md#raw-driver-arguments) to `create_pool()`
directly, or write a config class as described below.

## The short version

Inherit from [`BaseWarehouseConfig`][adbc_poolhouse.BaseWarehouseConfig] and
implement two methods:

```python
from adbc_poolhouse import BaseWarehouseConfig, create_pool
from pydantic_settings import SettingsConfigDict


class MyDriverConfig(BaseWarehouseConfig):
    model_config = SettingsConfigDict(env_prefix="MYDRIVER_")

    host: str
    port: int = 5000
    database: str = "default"

    def _driver_path(self) -> str:
        return self._resolve_driver_path("adbc_driver_mydriver")

    def to_adbc_kwargs(self) -> dict[str, str]:
        return {
            "uri": f"mydriver://{self.host}:{self.port}/{self.database}",
        }


pool = create_pool(MyDriverConfig(host="db.example.com"))
```

That is the complete implementation. `BaseWarehouseConfig` provides pool tuning
fields (`pool_size`, `max_overflow`, `timeout`, `recycle`) with sensible
defaults, and the `_adbc_entrypoint()` and `_dbapi_module()` methods return
`None` -- the right default for most drivers.

Library authors who prefer not to add a dependency on adbc-poolhouse (or
pydantic) can implement the
[`WarehouseConfig`][adbc_poolhouse.WarehouseConfig] protocol directly instead.
See [Without BaseWarehouseConfig](#without-basewarehouseconfig) below.

## What each method does

### `_driver_path()`

Called by `create_pool()` to locate the native ADBC driver. Return `None` if
the driver uses a Python dbapi module instead (see
[`_dbapi_module()`](#_dbapi_module) below). At least one of `_driver_path` or
`_dbapi_module` must return a non-None value.

Return one of:

- An absolute path to a shared library (`.so` / `.dylib` / `.dll`)
- A short package name like `"adbc_driver_mydriver"` that `adbc_driver_manager`
  resolves through its manifest
- `None` — when using `_dbapi_module()` instead

See the [ADBC driver manifests docs](https://arrow.apache.org/adbc/current/format/driver_manifests.html)
for details about driver path resolution.

The PyPI package for many drivers has a method like `_driver_path()` that
returns this value. A `_resolve_driver_path("adbc_driver_mydriver")` helper is
provided on `BaseWarehouseConfig` — it tries `importlib.util.find_spec` ->
import -> call the package's own `_driver_path()`, and falls back to returning
the package name if the package is not installed.

### `to_adbc_kwargs()`

Called by `create_pool()` to get the connection keyword arguments passed to the
ADBC driver. Return a `dict[str, str]` mapping ADBC option keys to values.

The exact keys depend on your driver. Common patterns:

| Driver style | Key | Example value |
|---|---|---|
| URI-based | `"uri"` | `"postgresql://host:5432/db"` |
| Path-based | `"path"` | `"/data/warehouse.db"` |
| Key-value | `"adbc.snowflake.sql.account"` | `"myorg-myaccount"` |

### `_adbc_entrypoint()`

Return the driver's init symbol name, or `None` for the default.

Most ADBC drivers use a default init function. Override this only when your
driver requires a non-standard symbol. Among the 12 built-in backends, only
DuckDB and SQLite override this method.

```python
def _adbc_entrypoint(self) -> str | None:
    return "my_driver_custom_init"
```

### `_dbapi_module()`

Some Python ADBC packages are not full ADBC drivers, but do expose the Python dbapi2-compatible ADBC interface.
In that case you can implement this method.

Return a dotted Python module path (e.g. `"adbc_driver_mydb.dbapi"`) to the module containing a `connect()` function. Return `None` otherwise.

When set, `create_pool()` imports the module and calls `connect()` directly
instead of loading a native shared library through `adbc_driver_manager`.

```python
import importlib.util


def _dbapi_module(self) -> str | None:
    if importlib.util.find_spec("adbc_driver_mydb") is not None:
        return "adbc_driver_mydb.dbapi"
    return None
```

## Pool tuning

`BaseWarehouseConfig` inherits four pool fields from
[`BaseSettings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/):

| Field | Default | Description |
|---|---|---|
| `pool_size` | `5` | Connections kept in the pool |
| `max_overflow` | `3` | Extra connections above `pool_size` |
| `timeout` | `30` | Seconds to wait before `TimeoutError` |
| `recycle` | `3600` | Seconds before a connection is replaced |

Your config's `env_prefix` applies to these fields automatically. With
`env_prefix="MYDRIVER_"`, setting `MYDRIVER_POOL_SIZE=10` in the environment
overrides the default.

For details, see the [configuration reference](configuration.md).

## Without BaseWarehouseConfig

You do not have to inherit from `BaseWarehouseConfig`. Any class that satisfies
the [`WarehouseConfig`][adbc_poolhouse.WarehouseConfig] protocol works:

```python
class StandaloneConfig:
    def __init__(self, uri: str) -> None:
        self.uri = uri
        self.pool_size = 5
        self.max_overflow = 3
        self.timeout = 30
        self.recycle = 3600

    def _driver_path(self) -> str | None:
        return "adbc_driver_mydriver"

    def _adbc_entrypoint(self) -> str | None:
        return None

    def _dbapi_module(self) -> str | None:
        return None

    def to_adbc_kwargs(self) -> dict[str, str]:
        return {"uri": self.uri}
```

This is more boilerplate than inheriting `BaseWarehouseConfig`. The standalone
approach is useful for library authors who do not want to pull in adbc-poolhouse
or pydantic as a transitive dependency.

## Protocol reference

The full contract, including underscore-prefixed methods normally hidden in the
API reference:

::: adbc_poolhouse.WarehouseConfig
    options:
      filters: []
      show_root_heading: true
      show_source: false
      skip_local_inventory: true

## See also

- [Pool lifecycle](pool-lifecycle.md) -- creating, using, and disposing pools
- [Configuration reference](configuration.md) -- env var loading and pool tuning
- [Raw driver arguments](configuration.md#raw-driver-arguments) -- using `create_pool()` without a config class
