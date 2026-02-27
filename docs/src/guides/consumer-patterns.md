# Consumer patterns

Patterns for integrating adbc-poolhouse into an application.

## FastAPI with SQLAlchemy ORM

`create_pool` returns a SQLAlchemy `QueuePool`. To use it with the SQLAlchemy ORM, pass `creator=pool.connect` to `create_engine` — SQLAlchemy calls `creator()` whenever it needs a new raw connection.

Create the pool at application startup and dispose it at shutdown using FastAPI's lifespan context:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import create_engine
from adbc_poolhouse import DuckDBConfig, create_pool

pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = create_pool(DuckDBConfig(database="/data/warehouse.db"))
    yield
    pool.dispose()
    pool._adbc_source.close()


app = FastAPI(lifespan=lifespan)
```

To wire the pool into a SQLAlchemy session factory, use `creator=pool.connect` when calling `create_engine`. Keep in mind that `adbc_poolhouse` manages the connection pool itself — pass `poolclass=NullPool` to SQLAlchemy so it does not add a second pool on top:

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

engine = create_engine("duckdb://", creator=pool.connect, poolclass=NullPool)
```

For Snowflake or other warehouses, replace `DuckDBConfig` with the matching config class. The lifespan pattern is the same.

## Loading credentials from dbt

If your project has a dbt `profiles.yml`, you can load credentials from it using dbt-core's profile API. This handles Jinja templating — including `env_var()` calls — so it works correctly where plain YAML parsing would not.

```python
from dbt.config.profile import Profile, read_profile
from dbt.config.renderer import ProfileRenderer
from adbc_poolhouse import SnowflakeConfig, create_pool

raw_profiles = read_profile("~/.dbt")
renderer = ProfileRenderer(cli_vars={})

profile = Profile.from_raw_profiles(
    raw_profiles=raw_profiles,
    profile_name="my_project",  # matches `profile:` in dbt_project.yml
    renderer=renderer,
    target_override="dev",  # None uses the profile's default target
)

creds = profile.credentials  # SnowflakeCredentials, Jinja already resolved

config = SnowflakeConfig(
    account=creds.account,
    user=creds.user,
    password=creds.password,
    database=creds.database,
    schema_=creds.schema,
    warehouse=creds.warehouse,
    role=creds.role,
)
pool = create_pool(config)
```

`Profile.from_raw_profiles` is available in dbt-core 1.0 and later. It is part of dbt-core's internal API, not a documented public contract, but it has been stable across the 1.x series.

```bash
pip install dbt-core
# or install your adapter, which pulls in dbt-core:
pip install dbt-snowflake
```

For production deployments, load credentials from environment variables instead of from the profiles file. `SnowflakeConfig` reads all fields from environment variables using the `SNOWFLAKE_` prefix — see [Configuration reference](configuration.md) for details.

## See also

- [Pool lifecycle](pool-lifecycle.md) — dispose pattern and pytest fixtures
- [Snowflake guide](snowflake.md) — auth methods including JWT and OAuth
- [Configuration reference](configuration.md) — environment variable loading
