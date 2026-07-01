# Phase 22 go/no-go: async feasibility (SPIKE-03)

**Verdict: GO, with a named materialization caveat.** The ADBC C path releases the GIL during `execute`, so thread-offload gives real parallelism of C-side work; large `fetch_arrow_table` materialization stays GIL-bound and does not parallelize, which is a documented limit on concurrency, not a blocker. This document gates Phase 24.

## What the spike measured

Two benchmarks ran the real `create_pool(DuckDBConfig(database=<file>))` checkout path against in-proc DuckDB, driving concurrency with raw threads (`threading.Barrier` + `ThreadPoolExecutor`) — no async code, by design, so the GIL-release question stays isolated from the offload machinery that does not exist yet. Each phase warmed up once, ran several trials, and reports the median. The headline figure is `speedup_x`: near `N` means the operation parallelized (GIL released), near `1` means it serialized (GIL held).

Machine and method: 8-core box, CPython 3.14.2 standard GIL build, barrier-gated concurrent start, median of trials. Absolute ratios move with core count and dataset size; the asymmetry between the two operations is the finding, not the exact numbers. Re-run `python -m benchmarks.gil_release --measure both` to reproduce.

### execute — heavy C-side query (GIL-release proxy)

`python -m benchmarks.gil_release --measure execute --n 4 --rows 120000000 --trials 5` (a 20M-row join; single call ≈ 0.29s).

| Metric | Value |
|--------|-------|
| N (concurrent connections) | 4 |
| join rows | 20,000,000 |
| trials | 5 (median) |
| single_call_s | 0.2885 |
| wall_s | 0.4164 |
| ideal_parallel_s (lower bound) | 0.2885 |
| full_serial_s (upper bound) | 1.1540 |
| **speedup_x** | **2.77** |
| parallel_efficiency | 0.693 |

Four concurrent heavy queries finished in 0.42s wall instead of the 1.15s they would take back-to-back. That is ~0.69 of perfect parallelism. The C++ engine did its work with the GIL released, so the threads ran at the same time.

### fetch_arrow_table — large-result materialization (the real unknown)

`python -m benchmarks.gil_release --measure fetch --n 4 --rows 20000000 --trials 5` (a 20M-row projection; single call ≈ 0.59s).

| Metric | Value |
|--------|-------|
| N (concurrent connections) | 4 |
| fetch rows | 20,000,000 |
| trials | 5 (median) |
| single_call_s | 0.5921 |
| wall_s | 1.4211 |
| ideal_parallel_s (lower bound) | 0.5921 |
| full_serial_s (upper bound) | 2.3683 |
| **speedup_x** | **1.67** |
| parallel_efficiency | 0.417 |

The same four-thread setup reached only ~0.42 of ideal here. Building large Arrow tables re-holds the GIL, so concurrent fetches partly line up behind each other instead of overlapping. They do not fully serialize on this box, but they get nowhere near the parallelism `execute` shows.

This 8-core run reports a higher fetch ratio (1.67x) than the research session's earlier 1.2–1.4x. The magnitude shifts with hardware; the shape holds. `execute` parallelizes well, `fetch_arrow_table` does not. That is exactly what assumption A1 in the research log predicted.

## What the async layer may claim

The ADBC C path releases the GIL during `execute`. Offloading an `execute` call to a thread therefore buys real **parallelism** of the C-side work, and — by inference — real **I/O concurrency** on network backends, where concurrent queries overlap their network waits instead of running one at a time.

Hold the two terms apart, because they are different things:

- **Parallelism** is real simultaneous CPU work across cores. In CPython you normally need multiprocessing for this, except when a C extension releases the GIL — then plain threads get there (the NumPy pattern). The `execute` benchmark demonstrates this directly: heavy engine work on N threads, wall-clock approaching single-call time.
- **I/O concurrency** is overlapping wait states — network round-trips to a remote warehouse. This is the real-world payoff for the async layer. The enabling mechanism is the same (the GIL is released during the blocking C call), but the phenomenon is genuinely different from CPU parallelism.

## What the async layer must not claim

Not blanket parallelism. Large `fetch_arrow_table` materialization is GIL-bound and does not parallelize across concurrent fetches. Several big-result fetches running at once approach serialization, so the async win shrinks as result size grows. Anyone reading "async makes queries concurrent" should not expect four 2 GB fetches to land in the time of one.

## The inference gap, named

In-proc DuckDB has no network wait. So this spike proves the GIL is released and that C-side work parallelizes — it does not directly measure I/O concurrency. The I/O-concurrency claim is an inference layered on top of the measured GIL release: if the GIL is dropped during a blocking C call, then a blocking network call should overlap the same way. That inference is sound and the premise is well established, but the spike does not exercise a real network round-trip. Do not write it up as "we proved I/O concurrency." We proved GIL release and CPU parallelism, and we infer I/O concurrency from it.

Phase 27's dual-backend test matrix is where real-backend behaviour gets exercised, once the async surface exists.

## Guidance for Phase 24: offload granularity

Offload at **whole-operation granularity** — one `to_thread` per `execute`, one `to_thread` per `fetch_arrow_table`. Do not split a single query's execute and fetch across threads hoping to overlap them within one query: the fetch serializes regardless, so there is no intra-operation parallelism to win, and you would only add coordination cost and connection-lifetime risk.

Where the win is real is across queries. The dedicated per-pool `CapacityLimiter(pool_size + max_overflow)` governs how many operations run concurrently, and for I/O-bound work — queries waiting on a remote warehouse — that concurrency pays off. The materialization limit does not undercut this: a query that waits on the network before returning a modest result is exactly the case the async layer serves well. The large-result fetch is the case where the gain narrows, and the docs should say so.

The fetch serialization is a caveat, not a no-go. Materialization costs the same in the sync path today; the async layer does not make it worse. Treating the fetch number as a milestone blocker would misread it.

## Handoff to Phase 28 docs (DOCS-01)

The async guide must set expectations honestly: async wins are largest for latency-bound and I/O-bound queries (waiting on a remote backend), and smaller for CPU-bound large-result materialization (building big Arrow tables). Frame it as "concurrency where you wait, not where you crunch." Phase 28 owns the user-facing guide; this go/no-go is the planning record it draws from.

## Free-threaded note

All of the above is measured on the standard GIL build of CPython 3.14.2. No-GIL (free-threaded) behaviour is out of scope for the spike and unmeasured. On a free-threaded build the fetch materialization limit could change, but nothing here speaks to that.

## Packaging hygiene

The kept `benchmarks/` directory stays out of the built wheel. It lives outside `src/`, so the `uv_build` backend does not package it. A wheel build (`uv build --wheel`) of `adbc_poolhouse-1.3.1-py3-none-any.whl` contains only `adbc_poolhouse/` and `adbc_poolhouse-1.3.1.dist-info/` — zero `benchmark`-matching entries — so the spike code never ships to users. No `pyproject.toml` change was needed.

## See also

- [`22-01-SUMMARY.md`](./22-01-SUMMARY.md) — the benchmark harness and the source of the measured medians transcribed above.
- [`benchmarks/README.md`](../../../benchmarks/README.md) — how to run and read the benchmarks; also the post-Phase-24 regression check.
- [`22-CONTEXT.md`](./22-CONTEXT.md) — the locked parallelism vs I/O-concurrency terminology this document follows.
- [`22-RESEARCH.md`](./22-RESEARCH.md) — the source-level root cause and the Go/No-Go Document Contract this document satisfies.
