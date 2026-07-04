# Async pool

The async API mirrors the sync one. Where the sync side has [`create_pool`][adbc_poolhouse.create_pool],
[`managed_pool`][adbc_poolhouse.managed_pool], and [`close_pool`][adbc_poolhouse.close_pool], the async side has
[`create_async_pool`][adbc_poolhouse.create_async_pool],
[`managed_async_pool`][adbc_poolhouse.managed_async_pool], and
[`close_async_pool`][adbc_poolhouse.close_async_pool].

The wrapper is built on
[anyio](https://anyio.readthedocs.io/), which runs on top of either __asyncio__ or
__trio__. It offloads each blocking ADBC call to a worker thread under whichever of
those your application already runs, the same code works under either.

Pool construction is synchronous because it does no per-call I/O. Checkout,
queries, and teardown are the parts that block, so those are the parts that get
awaited.

!!! warning "Experimental"

    The async API is experimental. Its surface may change between minor releases,
    so pin the version you build against and read the changelog before you upgrade.

    It is also incomplete. The following are not available yet on the async side:

    - **Async prepared statements** — `adbc_prepare`, `adbc_execute_schema`

    What you get today is checkout, `execute` / `executemany`, the `fetch*` methods,
    `fetch_arrow_table`, Arrow streaming through `fetch_record_batch`, bulk write
    through `adbc_ingest`, the six `adbc_get_*` connection-metadata methods (see
    [Connection metadata](#connection-metadata)), DataFrame convenience through
    `fetch_df` / `fetch_polars`, and cooperative cancellation. The rest is on the
    roadmap.

## Install

The async wrapper depends on `anyio`, which ships behind the `[async]` extra:

```bash
pip install adbc-poolhouse[async]
```

You still need an ADBC driver for your warehouse. See the
[installation table](../index.md#adbc-drivers) for the per-backend extra.

## A first query

The flow is checkout, cursor, execute, fetch, check in. The connection and the
cursor are both async context managers, so a nested `async with` pair checks the
connection back into the pool and closes the cursor when the block exits.

```python
import anyio
from adbc_poolhouse import DuckDBConfig, create_async_pool, close_async_pool


async def main():
    pool = create_async_pool(DuckDBConfig(database="/tmp/warehouse.db"))  # synchronous: no await
    try:
        async with await pool.connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 42 AS answer")
                table = await cur.fetch_arrow_table()
                print(table.column("answer")[0].as_py())  # 42
    finally:
        await close_async_pool(pool)


anyio.run(main)
```

The `async with await pool.connect()` line stacks two keywords because two things
happen. `pool.connect()` is a coroutine: awaiting it checks a connection out of the
pool and hands back an [`AsyncConnection`][adbc_poolhouse._async._connection.AsyncConnection]. That connection is itself an async context
manager, and the `async with` checks it back in when the block exits. Read it
inside out: `await pool.connect()` runs first, then `async with` wraps the result.

`conn.cursor()` is not awaited, because it does no I/O and returns the cursor
directly. The cursor is still an async context manager, so `async with` closes it
on exit. That is the rule across the whole surface: every call that reaches the
driver is awaited, while `cursor()` and the `description` / `rowcount` /
`arraysize` property reads are not.

If you have used psycopg3's async interface, this will feel familiar. The
connection-and-cursor context-manager shape, including the `async with await
...connect()` form, is deliberately the same.

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
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
# pool is closed here
```

## What actually runs in parallel

The concurrency win is not uniform across the call surface.

Each blocking call is offloaded to a worker thread. ADBC releases the GIL during
its C calls, so the `execute` step of several queries can run at the same time on
separate connections. Benchmarking during v1.4.0 development measured this on
DuckDB: with four concurrent `execute` calls, throughput scaled about 2.77x
(roughly 69% efficiency).

Materialization is different. `fetch_arrow_table` builds Python and pyarrow
objects, and that construction reacquires the GIL for parts of the work. The same
benchmark measured about 1.67x for four concurrent fetches (roughly 42% efficiency).
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

The pool caps concurrency for you. Each [`AsyncPool`][adbc_poolhouse._async._pool.AsyncPool] owns one
`anyio.CapacityLimiter` sized to `pool_size + max_overflow`, so the number of
in-flight offloaded calls can never exceed the pool's checkout ceiling. There is
no separate knob to tune and no global limiter to collide with.

## Streaming a result set batch by batch

`fetch_arrow_table` materializes the whole result before it returns. For a large
query that is a lot of memory to hold at once. When you want to process the rows in
chunks instead, `fetch_record_batch` hands you an
[`AsyncRecordBatchReader`][adbc_poolhouse._async._reader.AsyncRecordBatchReader]:
an async iterator that pulls one `pyarrow.RecordBatch` at a time, each pull offloaded
off the event loop.

The canonical form stacks `async with` over the awaited `fetch_record_batch`, then
iterates:

```python
import anyio
from adbc_poolhouse import DuckDBConfig, managed_async_pool

async with managed_async_pool(DuckDBConfig(database="/tmp/warehouse.db")) as pool:
    async with await pool.connect() as conn:
        cursor = conn.cursor()
        await cursor.execute("SELECT * FROM events WHERE day = ?", ["2026-06-27"])
        async with await cursor.fetch_record_batch() as reader:
            async for batch in reader:
                process(batch)  # a pyarrow.RecordBatch, one chunk at a time
```

The `async with await cursor.fetch_record_batch()` line reads the same way as
`async with await pool.connect()`: awaiting the coroutine builds the reader, and
`async with` wraps the result so it closes when the block exits. Inside, `async for`
drives the reader — each iteration awaits the next batch on a worker thread.

### Always close the reader

Use `async with`. It is the only path that guarantees the reader closes on every
exit: a normal drain, a `break` partway through, an exception in the loop body, or a
cancellation from an outer deadline. Draining the stream is not the same as closing
it. After the last batch, the underlying Arrow C stream still sits on the cursor
until `close` runs, so the reader will not release the connection on exhaustion
alone.

That matters because a live reader locks its connection for its whole lifetime, not
just during a pull. While the reader is open, any other operation on the same
connection raises
[`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError]: a second cursor, an
`execute`, a `commit`, all of it. The lock clears when you close the reader. A reader
you drain but forget to close keeps the connection busy until check-in reclaims it,
and its finalizer emits a `ResourceWarning` to tell you so. `async with` closes it for
you, so reach for it and the question does not come up.

### Reading after the reader is gone

The reader is bound to its checked-out connection. Once you close the reader, or once
the connection checks back into the pool, the underlying stream is closed. A read
after that point raises `pyarrow.lib.ArrowInvalid` — the driver's own
closed-stream error. Poolhouse does not wrap it in a bespoke type or convert it into
a silent no-op; you get the native exception, never a segfault or a read of freed
memory.

```python
async with await pool.connect() as conn:
    cursor = conn.cursor()
    await cursor.execute("SELECT * FROM events")
    reader = await cursor.fetch_record_batch()
    first = await reader.__anext__()
# connection checked back in here; the stream is closed
await reader.__anext__()  # raises pyarrow.lib.ArrowInvalid
```

Keep the reader's work inside the `async with await pool.connect()` block. If you
need rows after the connection is gone, materialize them with `fetch_arrow_table`
instead — that returns a `pyarrow.Table` that owns its buffers and outlives the
cursor.

### What streaming does and does not parallelize

Each `read_next_batch` pull is offloaded individually through the pool limiter, the
same limiter that bounds every other async call. A slow pull does not block the event
loop, and a cancelled pull aborts the in-flight C call through the cursor's
`adbc_cancel`, then invalidates the connection so the pool's count stays correct.

The pull runs off the loop, but it is not free of the GIL. Reading a batch
materializes Arrow objects, and that construction reacquires the GIL for parts of the
work — the same behavior described under
[What actually runs in parallel](#what-actually-runs-in-parallel) for
`fetch_arrow_table`. Streaming trades peak memory for a steady per-batch cost; it does
not turn one reader into a parallel pipeline. Batches from a single reader arrive one
at a time, in order. Real overlap comes from running separate readers on separate
connections, each checked out from the pool.

## Bulk-loading Arrow data

`adbc_ingest` writes an Arrow dataset straight into a table. Hand it a
`pyarrow.Table`, `RecordBatch`, `RecordBatchReader`, or an Arrow C-stream capsule
and the driver loads it in one offloaded call, returning the number of rows written:

```python
import pyarrow as pa
from adbc_poolhouse import DuckDBConfig, managed_async_pool

people = pa.table({"id": [1, 2, 3], "name": ["a", "b", "c"]})

async with managed_async_pool(DuckDBConfig(database="/tmp/warehouse.db")) as pool:
    async with await pool.connect() as conn:
        cursor = conn.cursor()
        written = await cursor.adbc_ingest("people", people, mode="create")  # 3
        await cursor.adbc_ingest("people", people, mode="append")  # 3 more, 6 total
```

The dataset reaches the driver unconverted. Poolhouse does no validation, so a
malformed payload or a bad table name surfaces the driver's own error. The row
count is whatever the driver reports, which is `-1` when it cannot count.

### The four write modes

`mode` is passed through verbatim. It defaults to `create`:

| `mode` | Effect |
|--------|--------|
| `create` | Create a new table. Fails if it already exists. |
| `append` | Add rows to an existing table. |
| `create_append` | Create the table if it is missing, then append. |
| `replace` | **Drop** the existing table and recreate it. |

`replace` is the one to watch. It is not a row-level upsert: it **drops** the
existing table and its data, then recreates it from the new dataset. If you meant
to add or update rows, use `append` or `create_append`.

`catalog_name`, `db_schema_name`, and `temporary` route the table to a specific
catalog or schema, or create it as temporary. The driver marks all three
EXPERIMENTAL, so treat their behaviour as subject to change.

### A cancelled ingest recovers the connection, not the table

Cancelling an in-flight `adbc_ingest` (a `fail_after` deadline, a `move_on_after`,
or a cancelled task group) aborts it the same way `execute` and `fetch_arrow_table`
are aborted: the driver's `adbc_cancel` unblocks the worker, and the now-poisoned
connection is invalidated rather than returned to the pool, so the checked-out
count stays correct.

What that recovers is the connection, not the table. A bulk load aborted partway
through can leave rows already written, and poolhouse does not roll them back — it
cannot, since the write is not wrapped in a transaction it controls. After a
cancelled ingest, treat the target table as being in an undefined state and clean
it up yourself before retrying.

## Fetching a DataFrame

`fetch_df` returns a `pandas.DataFrame` and `fetch_polars` returns a
`polars.DataFrame`. Each is a single offloaded call, like `fetch_arrow_table` — the
driver materializes the frame on the worker thread, and the connection checks back
in the moment the call returns:

```python
from adbc_poolhouse import DuckDBConfig, managed_async_pool

async with managed_async_pool(DuckDBConfig(database=":memory:")) as pool:
    async with await pool.connect() as conn:
        cursor = conn.cursor()
        await cursor.execute("SELECT 1 AS a, 2 AS b")
        df = await cursor.fetch_df()  # a pandas.DataFrame
```

Swap `fetch_df` for `fetch_polars` when you want a polars frame instead. The
returned frame owns its buffers, so it stays valid after the connection is checked
in — you can read it outside the `async with` block, the same way a
`fetch_arrow_table` result survives checkin.

pandas and polars are not poolhouse dependencies. You install whichever you use.
Poolhouse never imports them: the driver imports pandas or polars on the worker
thread as part of the fetch, so a missing install surfaces the native
`ModuleNotFoundError` unchanged. Poolhouse adds no availability pre-check and no
wrapping, exactly as the underlying sync ADBC method behaves.

## Connection metadata

The connection exposes the driver's ADBC metadata calls, each offloaded to a worker
thread like every other blocking call. Three of them return a self-owning value you
can read after check-in:

```python
async with await pool.connect() as conn:
    info = await conn.adbc_get_info()  # a dict of driver/vendor codes
    schema = await conn.adbc_get_table_schema("people")  # a pyarrow.Schema
    types = await conn.adbc_get_table_types()  # a list of table-type names
```

`adbc_get_objects` is different. It streams the catalog/schema/table hierarchy
through an [`AsyncRecordBatchReader`][adbc_poolhouse._async._reader.AsyncRecordBatchReader]
instead of materializing it, so you consume it the same way as `fetch_record_batch`:
stack `async with` over the awaited call and iterate.

```python
async with await pool.connect() as conn:
    async with await conn.adbc_get_objects(depth="tables") as reader:
        async for batch in reader:
            process(batch)  # a pyarrow.RecordBatch, each pull offloaded
```

Two caveats carry over from the underlying calls. First, none of the six is
cooperatively cancellable. They run through the same non-interruptible offload as
`commit` and `rollback`, so a surrounding `fail_after` or `move_on_after` cannot
abort an in-flight metadata call; the deadline waits until the driver returns.
Second, the streaming reader locks its connection for its whole lifetime, the same
way the reader from `fetch_record_batch` does. While it is open, a foreign call on
the same connection raises
[`ConnectionBusyError`][adbc_poolhouse.ConnectionBusyError], so drain and close it
(reach for `async with`) before the next operation.

`adbc_get_statistics` and `adbc_get_statistic_names` follow the same streaming shape,
but not every backend implements them. DuckDB raises the driver's native
`NotSupportedError`, which poolhouse passes through unwrapped.

### See also

- [Streaming a result set batch by batch](#streaming-a-result-set-batch-by-batch)
  for the reader-lifetime rules the metadata stream inherits
- [API Reference](../reference/) for the generated `AsyncConnection` metadata methods
  with their Parameters / Returns / Raises

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
  `AsyncConnection`, [`AsyncCursor`][adbc_poolhouse._async._cursor.AsyncCursor], and
  [`AsyncRecordBatchReader`][adbc_poolhouse._async._reader.AsyncRecordBatchReader]
  docs, including
  [`AsyncConnection.invalidate`][adbc_poolhouse._async._connection.AsyncConnection.invalidate]
  (the poison-recovery drop the cancellation path uses)
