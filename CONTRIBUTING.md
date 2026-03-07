# Contributing to adbc-poolhouse

## How to Record Integration Test Cassettes

Integration tests use [pytest-adbc-replay](https://github.com/paulhendricks/pytest-adbc-replay) cassette-based record/replay.
Cassettes are committed to `tests/cassettes/` and replayed in CI without credentials.

### Prerequisites

1. A live account for the backend you want to test (Snowflake, Databricks, etc.).
2. Create `.env` in the project root (this file is gitignored — never commit it):

   ```bash
   # .env — NEVER commit this file

   # Snowflake
   SNOWFLAKE_ACCOUNT=myorg-myaccount
   SNOWFLAKE_USER=myuser
   SNOWFLAKE_PASSWORD=mypassword
   SNOWFLAKE_WAREHOUSE=MY_WH
   SNOWFLAKE_DATABASE=MY_DB

   # Databricks (URI mode)
   DATABRICKS_URI=grpc+tls://my-workspace.cloud.databricks.com:443/sql/1.0/warehouses/abc?token=dapi...

   # Databricks (decomposed mode — alternative to URI)
   # DATABRICKS_HOST=my-workspace.cloud.databricks.com
   # DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/abc
   # DATABRICKS_TOKEN=dapi...
   ```

3. Install the relevant extras:

   ```bash
   uv sync --extra snowflake
   ```

### Recording Cassettes

```bash
pytest --adbc-record=once -m snowflake
pytest --adbc-record=once -m databricks
```

This connects with real credentials, executes the test queries, and writes cassette
files to `tests/cassettes/`.

### CI Replay

In CI, no credentials are set. Tests replay from committed cassettes automatically —
no connection attempt is made. Default `uv run pytest` excludes the `snowflake` and
`databricks` markers (configured via `addopts` in `pyproject.toml`).

### Committing Cassettes

Cassette files in `tests/cassettes/` are committed to the repository.
Before committing, run `uv run prek` to ensure detect-secrets passes on the cassette content.
