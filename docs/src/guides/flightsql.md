# Apache Arrow Flight SQL guide

Install the Flight SQL extra:

```bash
pip install adbc-poolhouse[flightsql]
```

Or with uv:

```bash
uv add "adbc-poolhouse[flightsql]"
```

## Connection

`FlightSQLConfig` connects to any Arrow Flight SQL server. Set `uri` to the gRPC endpoint — `grpc://` for plaintext, `grpc+tls://` for TLS — and provide credentials via username/password or a raw authorization header.

### Username and password

```python
from adbc_poolhouse import FlightSQLConfig, create_pool

config = FlightSQLConfig(
    uri="grpc://localhost:32010",
    username="me",
    password="s3cret",  # pragma: allowlist secret
)
pool = create_pool(config)
```

### TLS with certificate verification

```python
config = FlightSQLConfig(
    uri="grpc+tls://db.example.com:443",
    username="me",
    password="s3cret",  # pragma: allowlist secret
    tls_root_certs="/path/to/ca.pem",
)
```

### Raw authorization header

Use `authorization_header` when the server expects a pre-formatted token (for example `Bearer eyJ...` or `Basic base64==`):

```python
config = FlightSQLConfig(
    uri="grpc+tls://db.example.com:443",
    authorization_header="Bearer eyJ...",
)
```

## Loading from environment variables

`FlightSQLConfig` reads all fields from environment variables with the `FLIGHTSQL_` prefix:

```bash
export FLIGHTSQL_URI=grpc+tls://db.example.com:443
export FLIGHTSQL_USERNAME=me
export FLIGHTSQL_PASSWORD=s3cret
```

```python
config = FlightSQLConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
