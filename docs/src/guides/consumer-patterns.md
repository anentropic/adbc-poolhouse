# Consumer patterns

Patterns for integrating adbc-poolhouse into an application. A pool is shared infrastructure: build it once when the process starts, borrow a connection per request, and close it when the process shuts down.

Which pool you build depends on the handlers that will use it. An async framework is best served by the async pool, which keeps every blocking driver call off the event loop. The sync pool works too, but only from handlers that are allowed to block.

## FastAPI lifespan with the async pool

!!! warning "Experimental"
    The async API is experimental. Its surface may change between minor releases. See the [async pool guide](async.md) for the full caveat.

[`managed_async_pool`][adbc_poolhouse.managed_async_pool] is an async context manager, which makes it a direct fit for a lifespan hook: the pool opens when the application starts and closes when it stops. Store it on `app.state` so handlers can reach it without a module-level global.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from adbc_poolhouse import DuckDBConfig, managed_async_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with managed_async_pool(
        DuckDBConfig(database="/data/warehouse.db"),
        pool_size=10,
        max_overflow=5,
    ) as pool:
        app.state.pool = pool
        yield
    # the pool is closed here, after the server stops serving


app = FastAPI(lifespan=lifespan)


@app.get("/answer")
async def answer(request: Request):
    async with await request.app.state.pool.connect() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 42 AS answer")
            table = await cur.fetch_arrow_table()
    return {"answer": table.column("answer")[0].as_py()}
```

Each request checks out its own connection and returns it when the `async with` block exits. Never hand one connection to two concurrent tasks: the second caller is rejected with [`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError] rather than silently interleaving statements. Size `pool_size + max_overflow` against the requests you expect to be querying at the same time, and see [When the pool is saturated](async.md#when-the-pool-is-saturated) for what a request sees once that ceiling is reached.

A handler that writes needs one more call. Pooled connections are not in autocommit mode, so `await conn.commit()` has to run before the `async with` block exits or the write is rolled back at check-in without an error. [Committing writes](pool-lifecycle.md#committing-writes) has the detail.

If you would rather create and close the pool by hand, [`create_async_pool`][adbc_poolhouse.create_async_pool] and [`close_async_pool`][adbc_poolhouse.close_async_pool] split the same work across the two halves of the lifespan.

Closing is worth being precise about. It disposes the connections sitting idle in the pool and closes the underlying ADBC source connection, and it does that immediately: it neither waits for nor closes connections that are still checked out. The teardown itself is shielded from cancellation, so a shutdown signal cannot abandon the pool half-closed, but ordering is still yours to get right. A lifespan hook gives you that ordering for free under a server that shuts down gracefully, uvicorn included, because in-flight requests finish before the shutdown half of the lifespan runs. Anywhere else, drain your own work first.

## The sync pool in a FastAPI lifespan

[`managed_pool`][adbc_poolhouse.managed_pool] is a plain synchronous context manager, so it nests inside an `async def` lifespan without an `await`. The storage rule is the same as for the async pool: put it on `app.state` rather than in a module-level global.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from adbc_poolhouse import DuckDBConfig, managed_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    with managed_pool(DuckDBConfig(database="/data/warehouse.db")) as pool:
        app.state.pool = pool
        yield
    # the pool is closed here, after the server stops serving


app = FastAPI(lifespan=lifespan)


@app.get("/answer")
def answer(request: Request):  # plain def, so FastAPI runs it in a threadpool
    with request.app.state.pool.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 42 AS answer")
        return {"answer": cursor.fetchone()[0]}
```

The handler is a plain `def` on purpose. That is the rule the next section explains, and it decides how you size the pool: the concurrency the pool has to cover is the framework's threadpool, not the number of `async def` tasks in flight.

[`create_pool`][adbc_poolhouse.create_pool] and [`close_pool`][adbc_poolhouse.close_pool] split the same work across the two halves of the lifespan if you would rather have them explicit. Both block, but they run once at startup and once at shutdown, so calling them from an `async def` lifespan hook is fine.

For Snowflake or another warehouse, replace [`DuckDBConfig`][adbc_poolhouse.DuckDBConfig] with the matching config class. Nothing else about the pattern changes.

## Do not call the sync pool from an `async def` handler

[`create_pool`][adbc_poolhouse.create_pool] returns a synchronous SQLAlchemy `QueuePool`. `pool.connect()` blocks until a connection is free, and every driver call made through the connection blocks until the driver returns. Inside an `async def` handler that stalls the event loop for the whole query, so every other request the process is serving stops too, including requests that have nothing to do with the warehouse.

There are two ways out.

Declare the handler as a plain `def`. FastAPI and Starlette run non-async handlers in a threadpool, so the blocking work never touches the event loop, as in the [sync lifespan example](#the-sync-pool-in-a-fastapi-lifespan) above. The pool then needs to cover the threadpool workers that can be busy at once, the same sizing question as [Sizing under load](configuration.md#sizing-under-load) with the framework's threadpool as the source of concurrency.

Or use the async pool, which offloads each blocking call to a worker thread and bounds the fan-out for you. See the [lifespan example](#fastapi-lifespan-with-the-async-pool) above and the [async pool guide](async.md).

## Why the pool cannot back a SQLAlchemy Engine

`create_pool` returns a SQLAlchemy `QueuePool`, which invites an obvious next step: hand it to `create_engine(url, creator=pool.connect, poolclass=NullPool)` and query the warehouse through SQLAlchemy Core or the ORM. That does not work, and it is not something adbc-poolhouse can make work.

A SQLAlchemy dialect is written against one specific DBAPI, and it calls that DBAPI's own extras on every connection it is given. The PostgreSQL dialect calls psycopg2's `extras.register_uuid` on connect; the SQLite dialect calls pysqlite's `create_function`. Each also reads driver-specific attributes off the connection, psycopg2's `notices` and pysqlite's `isolation_level` among them. What the pool hands out is an ADBC connection. It implements the DBAPI interface, but none of those driver-specific extras, so the first checkout fails inside the dialect with a `TypeError` or an `AttributeError` before your query runs. Passing `creator=` only changes how a connection is opened; it does not make the dialect driver-agnostic. Third-party dialects layered on a built-in one, `duckdb-engine` included, inherit the same coupling.

Run the two side by side instead of stacking them. Keep adbc-poolhouse for the warehouse queries you want Arrow results from, and keep an ordinary SQLAlchemy engine, with its own driver and its own pool, for ORM work. Both open in the same lifespan hook and both go on `app.state`.

## Loading credentials from dbt

If your project has a dbt `profiles.yml`, you can load credentials from it using dbt-core's profile API. This handles Jinja templating, including `env_var()` calls, so it works correctly where plain YAML parsing would not.

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
    schema=creds.schema,
    warehouse=creds.warehouse,
    role=creds.role,
)
pool = create_pool(config)
```

The `schema` keyword has no trailing underscore: [`SnowflakeConfig`][adbc_poolhouse.SnowflakeConfig] declares the field with `alias="schema"`, and `schema_=` is rejected as an unknown field. The attribute is still `config.schema_` when you read it back.

`Profile.from_raw_profiles` is available in dbt-core 1.0 and later. It is part of dbt-core's internal API, not a documented public contract, but it has been stable across the 1.x series.

```bash
pip install dbt-core
# or install your adapter, which pulls in dbt-core:
pip install dbt-snowflake
```

For production deployments, load credentials from environment variables instead of from the profiles file. [`SnowflakeConfig`][adbc_poolhouse.SnowflakeConfig] reads all fields from environment variables using the `SNOWFLAKE_` prefix. See [Configuration](configuration.md) for details.

## See also

- [Async pool](async.md) — the asyncio/trio wrapper, saturation behaviour, and the one connection per task rule
- [Pool lifecycle](pool-lifecycle.md) — dispose pattern, committing writes, and pytest fixtures
- [Snowflake guide](snowflake.md) — auth methods including JWT and OAuth
- [Configuration](configuration.md) — environment variable loading
