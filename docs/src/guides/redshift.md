# Redshift guide

The Redshift ADBC driver is distributed via the ADBC Driver Foundry, not PyPI.
Follow the [Foundry installation guide](https://arrow.apache.org/adbc/current/driver/installation.html) to install it before using `RedshiftConfig`.

`adbc-poolhouse` does not need a separate extra for Redshift:

```bash
pip install adbc-poolhouse
```

## Connection

`RedshiftConfig` supports provisioned clusters (standard SQL auth and IAM) and
Redshift Serverless. Specify the connection as a URI or via decomposed fields.

### URI

```python
from adbc_poolhouse import RedshiftConfig, create_pool

config = RedshiftConfig(
    uri="redshift://me:s3cret@my-cluster.us-east-1.redshift.amazonaws.com:5439/mydb",  # pragma: allowlist secret
)
pool = create_pool(config)
```

### Decomposed fields

```python
config = RedshiftConfig(
    host="my-cluster.us-east-1.redshift.amazonaws.com",
    port=5439,
    user="me",
    password="s3cret",  # pragma: allowlist secret
    database="mydb",
)
pool = create_pool(config)
```

## Loading from environment variables

`RedshiftConfig` reads all fields from environment variables with the `REDSHIFT_` prefix:

```bash
export REDSHIFT_HOST=my-cluster.us-east-1.redshift.amazonaws.com
export REDSHIFT_USER=me
export REDSHIFT_PASSWORD=s3cret  # pragma: allowlist secret
export REDSHIFT_DATABASE=mydb
```

```python
config = RedshiftConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
