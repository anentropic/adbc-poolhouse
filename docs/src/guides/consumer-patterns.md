# Consumer patterns

Two patterns for integrating adbc-poolhouse into an application: FastAPI with SQLAlchemy ORM, and loading credentials from a dbt profiles file.

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

## dbt profiles.yml shim

If your project already has a dbt `profiles.yml`, you can read credentials from it directly and build the matching adbc-poolhouse config. This avoids duplicating connection details.

```python
import yaml
from pathlib import Path
from adbc_poolhouse import SnowflakeConfig, create_pool

# Load dbt profile
profiles_path = Path.home() / ".dbt" / "profiles.yml"
with profiles_path.open() as f:
    profiles = yaml.safe_load(f)

creds = profiles["my_project"]["outputs"]["dev"]

config = SnowflakeConfig(
    account=creds["account"],
    user=creds["user"],
    password=creds["password"],
    database=creds["database"],
    schema_=creds["schema"],
)
pool = create_pool(config)
```

This requires `pyyaml`, which is not bundled with adbc-poolhouse. Install it separately:

```bash
pip install pyyaml
```

For production deployments, load credentials from environment variables instead of from the profiles file. `SnowflakeConfig` reads all fields from environment variables using the `SNOWFLAKE_` prefix — see [Configuration reference](configuration.md) for details.

## See also

- [Pool lifecycle](pool-lifecycle.md) — dispose pattern and pytest fixtures
- [Snowflake guide](snowflake.md) — auth methods including JWT and OAuth
- [Configuration reference](configuration.md) — environment variable loading
