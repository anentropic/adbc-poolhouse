# Contributing to adbc-poolhouse

## How to Record Snowflake Snapshots

Snowflake integration tests use [syrupy](https://github.com/syrupy-project/syrupy) snapshot testing.
Snapshots are committed to the repository and replayed in CI without credentials.

### Prerequisites

1. A Snowflake account with a warehouse and database you can query.
2. Create `.env.snowflake` in the project root (this file is gitignored — never commit it):

   ```bash
   # .env.snowflake — NEVER commit this file
   SNOWFLAKE_ACCOUNT=myorg-myaccount
   SNOWFLAKE_USER=myuser
   SNOWFLAKE_PASSWORD=mypassword
   SNOWFLAKE_WAREHOUSE=MY_WH
   SNOWFLAKE_DATABASE=MY_DB
   ```

3. Install the Snowflake extra:

   ```bash
   uv sync --extra snowflake
   ```

### Recording Snapshots

```bash
pytest --override-ini="addopts=" -m snowflake --snapshot-update
```

This connects to Snowflake with real credentials, executes the test queries, and writes
snapshot files to `tests/integration/__snapshots__/`.

> **Note:** `addopts` in `pyproject.toml` excludes the `snowflake` marker from default runs.
> The `--override-ini="addopts="` flag clears that exclusion for this invocation.

### Verifying Snapshots

After recording, verify snapshots replay correctly without credentials by checking the
snapshot files contain no account identifiers or credentials:

```bash
# Verify no secrets in snapshots (detect-secrets should already catch this):
uv run detect-secrets scan tests/integration/__snapshots__/

# Verify snapshots match (no credentials in environment):
unset SNOWFLAKE_ACCOUNT && pytest --override-ini="addopts=" -m snowflake
# Expected: tests are skipped (SNOWFLAKE_ACCOUNT not set)
```

### Committing Snapshots

Snapshot files in `tests/integration/__snapshots__/` are committed to the repository.
Before committing, run `uv run prek` to ensure detect-secrets passes on the snapshot content.

### CI Behavior

In CI, `SNOWFLAKE_ACCOUNT` is not set. The `snowflake_pool` fixture detects this and calls
`pytest.skip()`, skipping all Snowflake tests without any connection attempt. Default `uv run pytest`
never runs the `snowflake` marker (excluded via `addopts` in `pyproject.toml`).
