# Snowflake guide

Install the Snowflake extra:

```bash
pip install adbc-poolhouse[snowflake]
```

Or with uv:

```bash
uv add "adbc-poolhouse[snowflake]"
```

## Auth methods

`SnowflakeConfig` supports four auth methods: password, JWT private key, OAuth, and external browser. Set the fields matching your method; unset fields are omitted from the connection.

### Password

```python
from adbc_poolhouse import SnowflakeConfig, create_pool

config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    password="s3cret",  # pragma: allowlist secret
    database="MY_DB",
    schema_="MY_SCHEMA",
)
pool = create_pool(config)
```

### JWT private key

Use either a file path or PEM content — not both. Providing both raises `ConfigurationError`.

```python
from pathlib import Path
from adbc_poolhouse import SnowflakeConfig

# From file path
config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    private_key_path=Path("/keys/rsa.p8"),
)
```

```python
from pydantic import SecretStr
from adbc_poolhouse import SnowflakeConfig

# From PEM content
config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    private_key_pem=SecretStr("-----BEGIN PRIVATE KEY-----\n..."),
)
```

`private_key_pem` is a `SecretStr` — the PEM content is masked in repr output. Pass the raw string with `.get_secret_value()` if you need to inspect it.

### OAuth

```python
config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    token="eyJ...",
    authenticator="oauth",
)
```

### External browser

For interactive SSO logins. Not suitable for headless or CI environments.

```python
config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    authenticator="externalbrowser",
)
```

## Loading from environment variables

`SnowflakeConfig` reads all fields from environment variables with the `SNOWFLAKE_` prefix:

```bash
export SNOWFLAKE_ACCOUNT=myorg-myaccount
export SNOWFLAKE_USER=me
export SNOWFLAKE_PASSWORD=s3cret
export SNOWFLAKE_DATABASE=MY_DB
```

```python
config = SnowflakeConfig()  # reads from env
```

## Snapshot testing in CI

Snowflake tests use [Syrupy](https://github.com/syrupy-project/syrupy) snapshots. Real credentials are required to record snapshots locally; the recorded snapshots are committed to the repository and replayed in CI without credentials.

To record snapshots, see the workflow in [CONTRIBUTING.md](https://github.com/anentropic/adbc-poolhouse/blob/main/CONTRIBUTING.md).

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning, secret fields
- [Consumer patterns](consumer-patterns.md) — dbt profiles.yml shim pattern
