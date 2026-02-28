# BigQuery guide

Install the BigQuery extra:

```bash
pip install adbc-poolhouse[bigquery]
```

Or with uv:

```bash
uv add "adbc-poolhouse[bigquery]"
```

## Auth methods

`BigQueryConfig` supports four auth methods via `auth_type`.

### Application Default Credentials

When `auth_type` is unset, the driver uses Google Application Default Credentials. Run `gcloud auth application-default login` to configure them locally, or set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key file path.

```python
from adbc_poolhouse import BigQueryConfig, create_pool

config = BigQueryConfig(project_id="my-gcp-project")
pool = create_pool(config)
```

### JSON credential file

```python
config = BigQueryConfig(
    auth_type="json_credential_file",
    auth_credentials_path="/keys/service_account.json",
    project_id="my-gcp-project",
)
```

### JSON credential string

Pass the key file contents directly as a string instead of a path:

```python
config = BigQueryConfig(
    auth_type="json_credential_string",
    project_id="my-gcp-project",
)
```

Set `BIGQUERY_AUTH_CREDENTIALS_PATH` or supply the JSON string via your secrets manager before calling `create_pool`.

### User authentication (OAuth)

```python
config = BigQueryConfig(
    auth_type="user_authentication",
    auth_client_id="...",
    auth_client_secret="...",
    auth_refresh_token="...",
    project_id="my-gcp-project",
)
```

## Loading from environment variables

`BigQueryConfig` reads all fields from environment variables with the `BIGQUERY_` prefix:

```bash
export BIGQUERY_PROJECT_ID=my-gcp-project
export BIGQUERY_DATASET_ID=my_dataset
```

```python
config = BigQueryConfig()  # reads from env
```

## See also

- [Configuration reference](configuration.md) — env_prefix, pool tuning
- [Consumer patterns](consumer-patterns.md) — FastAPI and dbt examples
