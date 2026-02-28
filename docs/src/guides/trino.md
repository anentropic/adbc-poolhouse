# Trino guide

The Trino ADBC driver is distributed via the ADBC Driver Foundry, not PyPI.
Follow your Foundry installation guide to install it before using `TrinoConfig`.

`adbc-poolhouse` does not need a separate extra for Trino:

```bash
pip install adbc-poolhouse
```

## Connection

`TrinoConfig` supports URI-based or decomposed field connection specification.

### URI

```python
from adbc_poolhouse import TrinoConfig, create_pool

config = TrinoConfig(
    uri="trino://me:s3cret@trino.example.com:8443/my_catalog/my_schema",  # pragma: allowlist secret
)
pool = create_pool(config)
```

### Decomposed fields

```python
config = TrinoConfig(
    host="trino.example.com",
    port=8443,
    user="me",
    password="s3cret",  # pragma: allowlist secret
    catalog="my_catalog",
)
pool = create_pool(config)
```

## Loading from environment variables

`TrinoConfig` reads all fields from environment variables with the `TRINO_` prefix:

```bash
export TRINO_HOST=trino.example.com
export TRINO_USER=me
export TRINO_PASSWORD=s3cret  # pragma: allowlist secret
export TRINO_CATALOG=my_catalog
```

```python
config = TrinoConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
