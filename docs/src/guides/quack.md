# Quack

!!! warning "Alpha driver"
    The [`adbc-driver-quack`](https://github.com/gizmodata/adbc-driver-quack) package is an alpha release (latest: `0.1.0a6` as of this writing). APIs and behaviour may change between releases.

Quack is a remote protocol for DuckDB servers. [`QuackConfig`][adbc_poolhouse.QuackConfig] connects to a Quack endpoint and accepts either a full `quack://` URI or decomposed `host`/`port` fields, with optional bearer token and TLS flags.

## Install

```bash
pip install --pre adbc-poolhouse[quack]
```

The `--pre` flag is required because `adbc-driver-quack` is published as a pre-release (alpha). Pip's default resolver excludes pre-releases unless you opt in.

## Connection

[`QuackConfig`][adbc_poolhouse.QuackConfig] supports two mutually exclusive connection modes: URI mode or decomposed mode. Setting both `uri` and `host`, or setting neither, raises [`ConfigurationError`][adbc_poolhouse.ConfigurationError] (wrapped as a Pydantic `ValidationError`).

### URI mode

```python
from adbc_poolhouse import QuackConfig, create_pool

config = QuackConfig(uri="quack://quack.example.com:8080")
pool = create_pool(config)
```

The `uri` field is a plain `str`, not `SecretStr`. The Quack driver's URI cannot embed credentials, so there is nothing to mask.

### Decomposed mode

```python
from adbc_poolhouse import QuackConfig, create_pool

config = QuackConfig(host="quack.example.com", port=8080)
pool = create_pool(config)
```

`port` is optional. When omitted, the rebuilt URI is `quack://{host}` with no trailing colon.

### Authentication and TLS

```python
from pydantic import SecretStr

from adbc_poolhouse import QuackConfig, create_pool

config = QuackConfig(
    host="quack.example.com",
    port=8080,
    token=SecretStr("YOUR-TOKEN-HERE"),  # pragma: allowlist secret
    tls=True,
)
pool = create_pool(config)
```

The token is passed via the `adbc.quack.token` kwarg and is never embedded in the URI. The `tls=True` flag emits `adbc.quack.tls=true`; when `tls=False` (the default) the kwarg is omitted so the driver's own default applies.

## Loading from environment variables

[`QuackConfig`][adbc_poolhouse.QuackConfig] reads all fields from environment variables with the `QUACK_` prefix. The recognised variables are `QUACK_URI`, `QUACK_HOST`, `QUACK_PORT`, `QUACK_TOKEN`, and `QUACK_TLS`.

```bash
export QUACK_HOST=quack.example.com
export QUACK_PORT=8080
export QUACK_TOKEN=your-token-here  # pragma: allowlist secret
export QUACK_TLS=true
```

```python
from adbc_poolhouse import QuackConfig, create_pool

config = QuackConfig()  # picks up QUACK_HOST, QUACK_PORT, QUACK_TOKEN, QUACK_TLS
pool = create_pool(config)
```

The same mutual-exclusion rule applies to env-loaded fields. Set `QUACK_URI` or `QUACK_HOST`, not both.

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning, secret handling
- [Pool lifecycle](pool-lifecycle.md) — `close_pool`, pytest fixtures
- [QuackConfig][adbc_poolhouse.QuackConfig] — API reference
