# BigQuery guide

## Installation

Install the BigQuery extra:

```bash
pip install adbc-poolhouse[bigquery]
```

Or with uv:

```bash
uv add "adbc-poolhouse[bigquery]"
```

## Auth methods

[`BigQueryConfig`][adbc_poolhouse.BigQueryConfig] supports four auth methods via `auth_type`.

### Application Default Credentials

When `auth_type` is unset, the driver uses Google Application Default Credentials. Run `gcloud auth application-default login` to configure them locally, or set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key file path.

```python
from adbc_poolhouse import BigQueryConfig, create_pool

config = BigQueryConfig(project_id="my-gcp-project")
pool = create_pool(config)
```

### JSON credential file

`auth_credentials` carries the key file path:

```python
from adbc_poolhouse import BigQueryConfig

config = BigQueryConfig(
    auth_type="json_credential_file",
    auth_credentials="/keys/service_account.json",
    project_id="my-gcp-project",
)
```

### JSON credential string

`auth_credentials` carries the key file contents directly instead of a path. The same field serves both methods; `auth_type` is what tells the driver how to read it.

```python
from pydantic import SecretStr
from adbc_poolhouse import BigQueryConfig

config = BigQueryConfig(
    auth_type="json_credential_string",
    auth_credentials=SecretStr('{"type": "service_account", ...}'),
    project_id="my-gcp-project",
)
```

`auth_credentials` is a `SecretStr`, so the JSON is masked in repr output. Rather than embedding the key material in source, set `BIGQUERY_AUTH_CREDENTIALS` or pull the string from your secrets manager before calling [`create_pool`][adbc_poolhouse.create_pool].

### User authentication (OAuth)

```python
from adbc_poolhouse import BigQueryConfig

config = BigQueryConfig(
    auth_type="user_authentication",
    auth_client_id="...",
    auth_client_secret="...",
    auth_refresh_token="...",
    project_id="my-gcp-project",
)
```

## Loading from environment variables

[`BigQueryConfig`][adbc_poolhouse.BigQueryConfig] reads all fields from environment variables with the `BIGQUERY_` prefix:

```bash
export BIGQUERY_PROJECT_ID=my-gcp-project
export BIGQUERY_DATASET_ID=my_dataset
```

```python
config = BigQueryConfig()  # reads from env
```

## See also

- [Configuration](configuration.md) — env_prefix, pool tuning
- [Pool lifecycle](pool-lifecycle.md) — close_pool, pytest fixtures
- [Consumer patterns](consumer-patterns.md) — FastAPI and dbt examples
