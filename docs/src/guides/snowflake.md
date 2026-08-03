# Snowflake guide

## Installation

Install the Snowflake extra:

```bash
pip install adbc-poolhouse[snowflake]
```

Or with uv:

```bash
uv add "adbc-poolhouse[snowflake]"
```

## Auth methods

[`SnowflakeConfig`][adbc_poolhouse.SnowflakeConfig] supports password auth plus the methods selected by `auth_type`. Leave `auth_type` unset for password auth; otherwise set it to one of `auth_jwt`, `auth_ext_browser`, `auth_oauth`, `auth_mfa`, `auth_okta`, `auth_pat`, or `auth_wif`, and fill in the fields that method needs. Unset fields are omitted from the connection.

The four methods worked through below cover the common cases. The remaining three follow the same shape: set `auth_type` and the credential fields for the method. MFA adds `cache_mfa_token`, Okta adds `okta_url`, and workload identity federation adds `identity_provider`. See the [API Reference](../reference/adbc_poolhouse.md) for the full field list.

### Password

```python
from adbc_poolhouse import SnowflakeConfig, create_pool

config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    password="s3cret",  # pragma: allowlist secret
    database="MY_DB",
    schema="MY_SCHEMA",
)
pool = create_pool(config)
```

The `schema` keyword is spelled without a trailing underscore because the field carries `alias="schema"`. Passing `schema_=` is rejected as an unknown field. Reading it back off the config uses the Python attribute name, `config.schema_`.

### JWT private key

Use either a file path or PEM content, not both. Providing both fails validation, so `SnowflakeConfig(...)` raises `pydantic.ValidationError`. See [Error handling](configuration.md#error-handling) for what to catch around config construction.

```python
from pathlib import Path
from adbc_poolhouse import SnowflakeConfig

# From file path
config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    auth_type="auth_jwt",
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
    auth_type="auth_jwt",
    private_key_pem=SecretStr("-----BEGIN PRIVATE KEY-----\n..."),
)
```

`private_key_pem` is a `SecretStr`, so the PEM content is masked in repr output. Pass the raw string with `.get_secret_value()` if you need to inspect it.

### OAuth

The bearer token goes in `oauth_token`, which is a `SecretStr`:

```python
from pydantic import SecretStr
from adbc_poolhouse import SnowflakeConfig

config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    auth_type="auth_oauth",
    oauth_token=SecretStr("eyJ..."),
)
```

### External browser

For interactive SSO logins. Not suitable for headless or CI environments.

```python
from adbc_poolhouse import SnowflakeConfig

config = SnowflakeConfig(
    account="myorg-myaccount",
    user="me",
    auth_type="auth_ext_browser",
)
```

## Loading from environment variables

[`SnowflakeConfig`][adbc_poolhouse.SnowflakeConfig] reads all fields from environment variables with the `SNOWFLAKE_` prefix:

```bash
export SNOWFLAKE_ACCOUNT=myorg-myaccount
export SNOWFLAKE_USER=me
export SNOWFLAKE_PASSWORD=s3cret
export SNOWFLAKE_DATABASE=MY_DB
```

```python
config = SnowflakeConfig()  # reads from env
```

## See also

- [Configuration](configuration.md) — env_prefix, pool tuning, secret fields
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
- [Consumer patterns](consumer-patterns.md) — dbt profile integration
