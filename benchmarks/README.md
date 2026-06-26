# GIL-release benchmarks

This directory measures one thing: does an ADBC operation release the GIL while
it runs? When it does, calls on separate threads overlap and you get real
parallelism. When it doesn't, the calls line up behind each other and run
serially no matter how many threads you throw at them.

These benchmarks live outside `src/`, so they never ship in the wheel. They drive
the *real* `create_pool(DuckDBConfig(...))` checkout path — the same path the
Phase 24 async wrappers offload to threads — so the numbers reflect production
behaviour rather than a contrived micro-test. Concurrency here is raw threads
(`threading.Barrier` + `ThreadPoolExecutor`); there is no async code in the spike.

## Run it

Both measurements at full size (chooses `N = min(4, cpu_count)`):

```bash
.venv/bin/python -m benchmarks.gil_release --measure both
```

A quick smoke run while you are iterating:

```bash
.venv/bin/python -m benchmarks.gil_release --measure both --n 2 --rows 1000000 --trials 1
```

Flags:

- `--measure {execute,fetch,both}` — pick one operation or run both.
- `--n` — concurrent connections and threads (defaults to `min(4, cpu_count)`).
- `--rows` — row count driving the heavy query. Bigger means a longer, cleaner
  single-call time; size it so one call takes well over a second.
- `--trials` — trials per phase; the median is reported.

Run the harness unit tests with:

```bash
.venv/bin/pytest tests/test_benchmarks_harness.py -q
```

## Read the numbers

Each measurement prints a `report` dict. The figure that matters is `speedup_x`,
read against two reference points:

| `speedup_x` | Meaning |
|-------------|---------|
| `≈ N` | The operation parallelized — the GIL was released during the call. |
| `≈ 1` | The operation serialized — the GIL was held (or re-acquired) throughout. |

The two measurements probe opposite ends of this:

- **`execute` (SPIKE-01)** runs a heavy C-side join and consumes a single row.
  The work happens inside the DuckDB engine with the GIL released, so concurrent
  calls overlap. Expect `speedup_x` to climb toward `N`.
- **`fetch_arrow_table` (SPIKE-02)** materializes a large result into an Arrow
  table. That materialization re-holds the GIL, so concurrent fetches serialize.
  Expect `speedup_x` to stay near `1`, regardless of `N`.

`parallel_efficiency` is just `speedup_x / N` — the fraction of ideal parallelism
you actually got. `ideal_parallel_s` (equal to the single-call time) and
`full_serial_s` (`N ×` the single-call time) bracket where the measured `wall_s`
should land.

A reminder on scale: tiny queries finish faster than the thread-pool and barrier
overhead around them, which smears the ratio toward the middle. If your smoke run
shows `execute` and `fetch` looking similar, the rows are too small — that is
overhead, not a finding. Use a full-size run for any number you intend to quote.

## Where the numbers go

The medians from a full-size run feed
[`22-GO-NO-GO.md`](../.planning/phases/22-feasibility-spike/22-GO-NO-GO.md)
(plan 02), which interprets them into the milestone go/no-go decision. This
benchmark is also a regression check: re-run it after Phase 24 ships the async
wrappers to confirm the offload behaviour still matches what the spike measured.
