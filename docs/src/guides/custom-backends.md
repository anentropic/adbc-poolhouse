# Custom backends

adbc-poolhouse ships config classes for 12 ADBC backends. If your driver is not
on that list, write your own config class and pass it to `create_pool()`.

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

## What each method does

### `_driver_path()`

Called by `create_pool()` to locate the native ADBC driver.

Return one of:

- An absolute path to a shared library (`.so` / `.dylib` / `.dll`)
- A short package name like `"adbc_driver_mydriver"` that `adbc_driver_manager`
  resolves through its manifest

For PyPI drivers, call `self._resolve_driver_path("adbc_driver_mydriver")`. This
static method tries `importlib.util.find_spec` -> import -> call the package's
own `_driver_path()`, and falls back to returning the package name if the package
is not installed.

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

Return a dotted Python module path (e.g. `"adbc_driver_mydb.dbapi"`) if the
driver ships a Python package with a `connect()` function. Return `None`
otherwise.

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

    def _driver_path(self) -> str:
        return "adbc_driver_mydriver"

    def _adbc_entrypoint(self) -> str | None:
        return None

    def _dbapi_module(self) -> str | None:
        return None

    def to_adbc_kwargs(self) -> dict[str, str]:
        return {"uri": self.uri}
```

This is more boilerplate than inheriting `BaseWarehouseConfig`. The standalone
approach is useful when you cannot depend on `pydantic-settings` or need full
control over initialization.

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
- [Pool lifecycle: raw driver arguments](pool-lifecycle.md#raw-driver-arguments) -- using `create_pool()` without a config class
