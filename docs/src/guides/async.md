# Async pool

The async API mirrors the sync one. Where the sync side has `create_pool`,
`managed_pool`, and `close_pool`, the async side has
[`create_async_pool`][adbc_poolhouse.create_async_pool],
[`managed_async_pool`][adbc_poolhouse.managed_async_pool], and
[`close_async_pool`][adbc_poolhouse.close_async_pool]. The wrapper runs each
blocking ADBC call on a worker thread (via [anyio](https://anyio.readthedocs.io/)),
so it works under both asyncio and trio.

Pool construction is synchronous because it does no per-call I/O. Checkout,
queries, and teardown are the parts that block, so those are the parts that get
awaited.

!!! warning "Experimental"

    The async API is experimental. Its surface may change between minor releases,
    so pin the version you build against and read the changelog before you upgrade.

    It is also incomplete. The following are not available yet on the async side:

    - **Arrow streaming** — `fetch_record_batch` and `async for batch in ...`
    - **Async bulk write** — `adbc_ingest`
    - **DataFrame convenience** — `fetch_df` and `fetch_polars`
    - **Async ADBC metadata** — `adbc_get_table_schema`, `adbc_get_objects`, `adbc_get_info`
    - **Async prepared statements** — `adbc_prepare`, `adbc_execute_schema`

    What you get today is checkout, `execute` / `executemany`, the `fetch*` methods,
    `fetch_arrow_table`, and cooperative cancellation. The rest is on the roadmap.

## Install

The async wrapper depends on `anyio`, which ships behind the `[async]` extra:

```bash
pip install adbc-poolhouse[async]
```

You still need an ADBC driver for your warehouse. See the
[installation table](../index.md#adbc-drivers) for the per-backend extra.

## A first query

The flow is checkout, cursor, execute, fetch, check in. The `async with` block
returns the connection to the pool when it exits.

```python
import anyio
from adbc_poolhouse import DuckDBConfig, create_async_pool, close_async_pool


async def main():
    pool = create_async_pool(DuckDBConfig(database="/tmp/warehouse.db"))  # synchronous: no await
    try:
        async with await pool.connect() as conn:
            cur = conn.cursor()  # synchronous: no await
            await cur.execute("SELECT 42 AS answer")
            table = await cur.fetch_arrow_table()
            print(table.column("answer")[0].as_py())  # 42
    finally:
        await close_async_pool(pool)


anyio.run(main)
```

Two calls are not coroutines, and that is deliberate:

- `conn.cursor()` does no I/O, so it returns directly with no `await`.
- `cur.description`, `cur.rowcount`, and `cur.arraysize` are plain property
  reads. Awaiting them would raise "coroutine was never awaited".

`fetch_arrow_table` returns a fully materialized `pyarrow.Table` that owns its
own buffers. You can
read it after the connection is checked in. It is never a streaming reader bound
to the cursor, so it will not dangle once the cursor closes.

For a script or a short-lived process, `managed_async_pool` closes the pool for
you on exit:

```python
from adbc_poolhouse import DuckDBConfig, managed_async_pool

async with managed_async_pool(DuckDBConfig(database="/tmp/warehouse.db")) as pool:
    async with await pool.connect() as conn:
        cur = conn.cursor()
        await cur.execute("SELECT 1")
# pool is closed here
```

## What actually runs in parallel

The concurrency win is not uniform across the call surface.

Each blocking call is offloaded to a worker thread. ADBC releases the GIL during
its C calls, so the `execute` step of several queries can run at the same time on
separate connections. The Phase 22 spike measured this on DuckDB: with four
concurrent `execute` calls, throughput scaled about 2.77x (roughly 69%
efficiency).

Materialization is different. `fetch_arrow_table` builds Python and pyarrow
objects, and that construction reacquires the GIL for parts of the work. The same
spike measured about 1.67x for four concurrent fetches (roughly 42% efficiency).
The fetch step partially serializes even though it runs off the event loop.

So the realistic picture: queries that spend their time in the driver (network
round-trips, server-side execution) parallelize well, and the win shrinks as more
of the wall-clock time goes into materializing large result sets in-process. If
you are fanning out many large `fetch_arrow_table` calls and expecting linear
speedup, you will not get it. Size your concurrency against the work that is
actually I/O-bound.

The measurements above came from an in-process DuckDB driver, which has no network
wait, so they capture the GIL behavior rather than real network concurrency. A
networked backend has genuine I/O latency to overlap, which is exactly the case
the worker-thread model is built for.

The pool caps concurrency for you. Each `AsyncPool` owns one
`anyio.CapacityLimiter` sized to `pool_size + max_overflow`, so the number of
in-flight offloaded calls can never exceed the pool's checkout ceiling. There is
no separate knob to tune and no global limiter to collide with.

## Do not share one async connection across concurrent tasks

An ADBC connection permits serialized access (one call at a time) but not
concurrent access. Each `AsyncConnection` belongs to exactly one task for its
lifetime. Check out a separate connection per task from the pool.

```python
import anyio

# WRONG: aliasing one connection across tasks
async with await pool.connect() as conn:
    cur = conn.cursor()
    async with anyio.create_task_group() as tg:
        tg.start_soon(run_query, cur)  # task A
        tg.start_soon(run_query, cur)  # task B, concurrent use of the SAME connection
# raises ConnectionBusyError: the second concurrent call is rejected


# RIGHT: one connection per task
async def worker(pool):
    async with await pool.connect() as conn:  # each task checks out its own
        cur = conn.cursor()
        await cur.execute("SELECT 1")


async with anyio.create_task_group() as tg:
    tg.start_soon(worker, pool)
    tg.start_soon(worker, pool)
```

A second concurrent call on the same connection raises
[`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError]. The wrapper sets a
flag on entry to each offloaded call and rejects any caller that arrives while one
is in flight. Two cursors on one connection count as the same connection, so they
trip the same guard.

Why a hard error and not silent queuing: serializing the calls would still let two
tasks' statements interleave inside one open transaction. The driver would not
crash, but the result is logically corrupt, and the bug stays hidden. Failing
loudly is the debuggable choice. The sync pool relies on the same
connection-per-thread convention; the async layer enforces it with an error
because task-group aliasing is easy to do by accident through a captured closure.

## Cleanup is shielded

[`close_async_pool`][adbc_poolhouse.close_async_pool] and the check-in inside
`async with` run their blocking teardown inside a shielded cancel scope. A
cancellation that arrives mid-close cannot abandon the pool or a connection in an
unknown state, so driver resources are released even when the surrounding task is
being torn down.

## Cancelling an in-flight query

Wrap a query in `fail_after` or `move_on_after` (or cancel its task group) to put
a deadline on `execute` and `fetch_arrow_table`:

!!! example

    ```python
    import anyio

    async with await pool.connect() as conn:
        cursor = conn.cursor()
        with anyio.fail_after(5):
            await cursor.execute("SELECT * FROM big_table")
            table = await cursor.fetch_arrow_table()
    ```

A blocking ADBC call runs on a worker thread that the event loop cannot interrupt
on its own. When the deadline fires while the query is in flight, the pool aborts
it cooperatively. It calls the driver's thread-safe `adbc_cancel` to unblock the
worker, joins that worker, then drops the now-poisoned connection from the pool
with [`AsyncConnection.invalidate`][adbc_poolhouse._async._connection.AsyncConnection.invalidate] rather than returning it. The
connection count stays correct, so the pool's checked-out count never includes a
connection that the pool has already reclaimed. Your task sees its own exception and nothing
from the driver: `fail_after` raises `TimeoutError`, `move_on_after` returns
quietly, and an explicit `scope.cancel()` surfaces no value at all. The same
cleanup runs underneath each of them.

A query cancelled before it reaches the driver (for example, the limiter is
saturated and the call is still queued for a worker) touches no connection and
leaves the pool unchanged: no `adbc_cancel`, no invalidate, nothing to recover.
Recovery itself runs under a shield, so a second cancellation arriving during
cleanup cannot leave the pool miscounted. The behaviour is identical under asyncio
and trio. Only the surfaced exception type differs, and that difference comes from
anyio's scope, not from anything the pool does.

## See also

- [Pool lifecycle](pool-lifecycle.md) for the sync dispose pattern and pytest
  fixtures
- [Configuration reference](configuration.md) for env var loading and pool tuning
- [API Reference](../reference/) for the generated `AsyncPool`,
  `AsyncConnection`, and `AsyncCursor` docs, including
  [`AsyncConnection.invalidate`][adbc_poolhouse._async._connection.AsyncConnection.invalidate]
  (the poison-recovery drop the cancellation path uses)
