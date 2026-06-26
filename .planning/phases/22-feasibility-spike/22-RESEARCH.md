# Phase 22: Feasibility Spike - Research

**Researched:** 2026-06-26
**Domain:** Empirical GIL-release measurement for ADBC `execute` vs `fetch_arrow_table` (in-proc DuckDB through the ADBC driver manager), plus benchmark methodology and go/no-go authoring
**Confidence:** HIGH (the central unknown was settled empirically this session against the project's own installed driver stack)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Phase boundary — measurement spike, no production code.** Two DuckDB benchmarks through the real ADBC driver-manager path (N concurrent `execute` = SPIKE-01; N concurrent `fetch_arrow_table` = SPIKE-02) plus a written go/no-go (SPIKE-03). Out of scope: any `src/adbc_poolhouse/_async/` code, anyio, `CapacityLimiter`, `to_thread`, cancellation, the Phase 23 harness, real network backends, free-threaded/no-GIL builds.

**Terminology framing (LOCKED — the go/no-go doc MUST use these terms precisely):**
- **Parallelism** = real simultaneous CPU work across cores. In CPython only via multiprocessing *except* when a C extension releases the GIL — then plain threads parallelize (the NumPy pattern). A heavy DuckDB query on N threads, *if ADBC releases the GIL*, is observed as parallelism (wall-clock approaches single-call time).
- **I/O concurrency** = overlapping *wait* states (network round-trips). The async layer's real-world payoff. Same enabling mechanism (GIL released during the blocking C call) but a genuinely different phenomenon from CPU parallelism.
- The `execute` benchmark is a **proxy for the GIL-release mechanism**. It directly demonstrates parallelism of C-side compute. In-proc DuckDB has **no I/O wait**, so the benchmark **cannot itself demonstrate I/O concurrency** — it shows the GIL is released, from which I/O concurrency on network backends is *inferred*. The go/no-go MUST name this inference gap and MUST NOT dress up "GIL released → threads parallelize a heavy query" as "we proved I/O concurrency."

**What each benchmark tests:**
- SPIKE-01 (execute): Does the ADBC C driver release the GIL during `execute`? Observed as thread parallelism of C++ engine work. Basis for *inferring* I/O concurrency. HIGH confidence in research; spike confirms empirically.
- SPIKE-02 (fetch_arrow_table): The core unknown. Does pyarrow `Table` materialization release the GIL (→ parallelizes) or re-acquire it (→ serializes)? MEDIUM confidence; this is what the spike exists to settle. Drives Phase 24 offload granularity and Phase 28 doc honesty.

**Concurrency mechanism:** Drive concurrency with **raw threads** (`ThreadPoolExecutor` / `threading.Thread`) — **NOT** anyio. Isolate the GIL-release question from async machinery that doesn't exist yet.

**"Slow I/O-bound execute" simulation:** No real network. Through the ADBC driver manager against in-proc DuckDB. Default "slow execute" is a **heavy C-side query** (large join / aggregation / `generate_series`) that runs in the DuckDB C++ engine with the GIL released. If demonstrating I/O-bound (wait-state) concurrency specifically, simulate the wait deliberately but the wait MUST block with the GIL released to be faithful — a Python scalar UDF that `sleep()`s re-acquires the GIL and measures the wrong thing, so prefer a controlled heavy C-side query over injected sleeps.

**Artifact tiers (two distinct categories):**
- **Benchmark code** (timing harness + the execute and fetch_arrow_table measurements): **KEPT and polished enough to re-run** — e.g. a `benchmarks/` directory. Reusable as a regression check after Phase 24. Maintained-artifact posture.
- **Spike scaffolding** (exploratory probing, dataset-generation experiments, one-off diagnostics): **throwaway** — not kept, not polished.

**Methodology:** Warmup runs, multiple trials, report **median** (in-proc DuckDB is fast and jittery; single-shot timing is unreliable). Ideal-parallel baseline: `single_call_time` (perfect scaling) vs `N × single_call_time` (full serialization). The **speedup ratio** against these bounds is the headline number for each benchmark. Choose N and dataset/result sizes so each call runs in seconds (not microseconds) and thread-pool startup cost does not swamp the signal.

**Tooling / deps:** No new runtime dependencies. Stdlib `time.perf_counter` for timing. Existing `[duckdb]` optional extra + `adbc-driver-duckdb`.

**Go/no-go document:** Lives at `.planning/phases/22-feasibility-spike/` (planning artifact, written prose, gates Phase 24). It is the SPIKE-03 deliverable — not user-facing docs (Phase 28 owns the honest user guide, informed by these findings).

### Claude's Discretion
- Exact dataset shape, N values, and trial counts (subject to the methodology constraints above).
- Internal structure of the benchmark harness module(s) and the throwaway spike scaffolding.
- Precise format of the go/no-go document, provided it covers: claim/disclaim, the parallelism-vs-I/O-concurrency inference gap, and offload-granularity guidance for Phase 24.

### Deferred Ideas (OUT OF SCOPE)
- Validating I/O concurrency against a real network backend (Snowflake cassette / live) — out of scope; Phase 27 dual-backend matrix exercises real backends once the async surface exists.
- Free-threaded (no-GIL) Python behaviour — not measured here.
- `fetchall` serialization control — deferred unless needed for debugging. A contrast measurement of concurrent `fetchall` (pure Python-object construction, definitely holds the GIL) was considered as a known-serialized control. **Decision: do NOT include it by default.** Only reach for it if the `fetch_arrow_table` numbers are ambiguous and we need to debug *why* materialization behaves as it does.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPIKE-01 | A DuckDB benchmark measures wall-clock of N concurrent slow (I/O-bound) queries against ideal-parallel, demonstrating real GIL release during `execute` | Settled empirically this session: heavy C-side `execute` parallelizes near-ideally (measured **3.22x at N=4** small, **3.67x at N=4** at 20M-row scale). Heavy-query shapes, sizing, and the exact `execute`+`fetchone` drive path are documented under Architecture Patterns and Code Examples. |
| SPIKE-02 | A DuckDB benchmark measures N concurrent large `fetch_arrow_table` calls against ideal-parallel, quantifying whether pyarrow materialization parallelizes or serializes on the GIL | Settled empirically: `fetch_arrow_table` materialization **largely serializes** (measured **1.23x at N=4** small, **1.40x at N=4** at 20M rows — wall-clock sits near full-serial, far from ideal-parallel). Root cause traced in source (`_reader.pyx::read_all` → `pyarrow.RecordBatchReader.read_all`). This is the central go/no-go input. |
| SPIKE-03 | A written go/no-go records which concurrency the async layer can honestly claim (and what to disclaim), feeding offload-granularity and documentation decisions | The go/no-go content checklist, the claim/disclaim split implied by the measured numbers, the parallelism-vs-I/O-concurrency inference gap, and Phase 24 offload-granularity guidance are all specified under "Go/No-Go Document Contract" and "Architecture Patterns". |
</phase_requirements>

## Summary

This phase exists to settle one MEDIUM-confidence premise empirically before any async code is written: does ADBC release the GIL not only during `execute` (HIGH confidence) but also during `fetch_arrow_table` materialization (the unknown)? I ran the measurement this session against the project's exact installed stack (Python 3.14, adbc-driver-manager 1.11.0, adbc-driver-duckdb, pyarrow 24.0.0, duckdb 1.5.2, standard GIL build) and the answer is clear and asymmetric:

- **`execute` (heavy C-side compute) parallelizes near-ideally** — measured **3.22x speedup at N=4** on a small heavy join, and **3.67x at N=4** on a 20M-row aggregation. Wall-clock approaches single-call time. The GIL is released during the DuckDB C++ engine work, exactly as the premise asserts.
- **`fetch_arrow_table` (Arrow Table materialization) largely serializes** — measured **1.23x at N=4** small and **1.40x at N=4** on 20M rows. Wall-clock sits close to *full serialization* (`N × single_call_time`), far from ideal-parallel. The GIL is re-held during `pyarrow.RecordBatchReader.read_all()`, so concurrent large fetches contend.

The root cause is visible in the shipped ADBC source (the `.pyx` files are distributed, not just compiled): `Cursor.fetch_arrow_table` → `_RowIterator.fetch_arrow_table` → `_blocking_call(self.reader.read_all, ...)` → `AdbcRecordBatchReader.read_all` → `pyarrow.RecordBatchReader.read_all()`. The `with nogil:` blocks that release the GIL live in the *statement execute/stream-fetch* path in `_lib.pyx`; the per-batch Arrow object construction inside pyarrow's `read_all` re-acquires the GIL to build Python-visible `pyarrow.Table` objects, which is where concurrent fetches collide.

**Primary recommendation:** Build the two benchmarks driving the real `create_pool(DuckDBConfig(...))` → `pool.connect()` → `cursor()` → `execute` / `fetch_arrow_table` → `close()` path on a **file-backed** DuckDB DB with `pool_size=N` (in-memory forces `pool_size=1`). Use a `threading.Barrier(N)` so all worker threads enter the timed region simultaneously, warmup once, report the median of several trials, and headline each benchmark as a speedup ratio bounded by `single_call_time` (ideal) and `N × single_call_time` (full serial). The go/no-go is a clear GO with one named caveat: GIL release is real (so I/O concurrency on network backends is soundly inferred and CORE/ACUR offload is justified), but `fetch_arrow_table` is materialization-bound — so the async layer must offload at whole-operation granularity (never split execute from fetch hoping to overlap them), and Phase 28 docs must say async wins are I/O-bound, not a blanket parallelism claim.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Heavy query compute (`execute`) | ADBC C/C++ driver (DuckDB engine) | — | Runs under `with nogil:` in `_lib.pyx`; the GIL is released so threads parallelize the C++ engine work. This is the GIL-release proxy. |
| Result materialization (`fetch_arrow_table`) | pyarrow (Python-C boundary) | ADBC `_reader` | `read_all` builds Python-visible `pyarrow.Table` objects; GIL is re-held during object construction, so concurrent calls serialize. |
| Concurrency driver | stdlib `threading` / `ThreadPoolExecutor` | — | Raw threads isolate the GIL question from anyio (locked). |
| Connection lifecycle | SQLAlchemy `QueuePool` (sync core, reused verbatim) | ADBC dbapi | Benchmark drives the real `create_pool` checkout path so it measures the production code path, not a bespoke connection. |
| Timing / measurement | stdlib `time.perf_counter` + `statistics.median` | — | No new deps; monotonic high-resolution clock. |
| Go/no-go interpretation | written prose (planning artifact) | — | Translates the two speedup ratios into a claim/disclaim that gates Phase 24. |

## Standard Stack

This is a measurement spike with **no new runtime dependencies** (locked). Everything used is already installed via the existing `[duckdb]` extra and the dev group. The "stack" is the stdlib + the already-present driver chain.

### Core
| Library | Version (verified this session) | Purpose | Why Standard |
|---------|--------------------------------|---------|--------------|
| `time` (stdlib) | — | `time.perf_counter()` monotonic high-resolution timing | Locked; correct primitive for wall-clock measurement, immune to clock adjustments |
| `statistics` (stdlib) | — | `median()` over trials | In-proc DuckDB is jittery; median is the locked reporting statistic |
| `threading` / `concurrent.futures` (stdlib) | — | `ThreadPoolExecutor`, `Barrier` to drive N concurrent calls | Locked: raw threads, NOT anyio |
| `adbc_driver_manager` | 1.11.0 [VERIFIED: installed in .venv] | The driver-manager `dbapi` surface the benchmark drives | Already a hard runtime dep |
| `adbc_driver_duckdb` | present [VERIFIED: importable in .venv] | The in-proc DuckDB ADBC driver (`adbc_driver_duckdb.dbapi`) | Provides the real C-side engine under test |
| `pyarrow` | 24.0.0 [VERIFIED: installed in .venv] | `fetch_arrow_table` returns a `pyarrow.Table`; materialization is the SPIKE-02 subject | Dev-group dep; required for Arrow fetch |
| `duckdb` | 1.5.2 [VERIFIED: installed in .venv] | DuckDB engine (via `[duckdb]` extra) | Already present |
| `adbc_poolhouse` (`create_pool`, `DuckDBConfig`) | 1.3.1 (this repo) | Drives the real production checkout path | The whole point: benchmark the shipped sync code path |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tempfile` (stdlib) | — | Scratch file-backed DuckDB DB path | Needed because in-memory DuckDB forces `pool_size=1` (configs reject `pool_size>1` with `:memory:`) — see Pitfall 1 |
| `argparse` (stdlib) | — | Optional CLI for re-runnable benchmark (N, row count, trials) | Discretionary; helps the "re-runnable regression check" posture |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Driving `create_pool` checkout path | One bespoke `adbc_driver_duckdb.dbapi.connect()` per thread | Simpler, but does NOT measure the production code path (CONTEXT wants the real driver-manager path). Bespoke connect is fine ONLY for throwaway spike scaffolding, not the kept benchmark. |
| `threading.Barrier` start gate | `ThreadPoolExecutor.map` without a barrier | Without a barrier, thread spin-up staggers the start and *understates* parallelism (early threads finish before late ones start). Barrier makes the overlap real. |
| Heavy C-side query as "slow execute" | Python scalar UDF that `time.sleep()`s | **Wrong** — a Python UDF re-acquires the GIL and would falsely show serialization. Locked against. See Pitfall 2. |
| `time.perf_counter` | `time.time` / `timeit` | `time.time` is wall-clock (NTP-adjustable); `timeit` disables GC and adds framing unsuited to a threaded harness. `perf_counter` is the locked, correct choice. |

**Installation:** No install step. All dependencies are present in the existing dev environment (`uv sync` with the `[duckdb]` extra + dev group). The benchmark only imports stdlib + already-installed `adbc_poolhouse`, `pyarrow`, and the DuckDB driver.

**Version verification (run this session):**
```
adbc_driver_manager 1.11.0    [VERIFIED: .venv import]
pyarrow             24.0.0     [VERIFIED: .venv import]
duckdb              1.5.2      [VERIFIED: .venv import]
python              3.14.2     [VERIFIED: .venv]
GIL                 standard (sys._is_gil_enabled() == True)  [VERIFIED]
```

## Package Legitimacy Audit

> No external packages are installed by this phase. All libraries used are stdlib or already-present hard/dev dependencies verified by direct import in the project's `.venv` this session. No legitimacy gate applies.

| Package | Registry | Source Repo | Verdict | Disposition |
|---------|----------|-------------|---------|-------------|
| `adbc_driver_manager` | PyPI (already a dep) | apache/arrow-adbc | OK (pre-existing) | No action — already in `dependencies` |
| `adbc_driver_duckdb` | PyPI (`[duckdb]` chain) | apache/arrow-adbc | OK (pre-existing) | No action |
| `pyarrow` | PyPI (dev group) | apache/arrow | OK (pre-existing) | No action |
| `duckdb` | PyPI (`[duckdb]` extra) | duckdb/duckdb | OK (pre-existing) | No action |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                       benchmark harness (KEPT artifact, e.g. benchmarks/)
                                     │
              ┌──────────────────────┴───────────────────────┐
              │  setup: file-backed DuckDB DB (tempfile)      │
              │  create_pool(DuckDBConfig(database=<file>,    │
              │              pool_size=N, max_overflow=0))    │
              │  warmup 1 call (seeds N live connections)     │
              └──────────────────────┬───────────────────────┘
                                     │
        single-call baseline ◄───────┤  median of T trials, 1 thread
        (single_call_time)           │
                                     │
                   ┌─────────────────┴──────────────────┐
                   │  concurrent region (median of T)    │
                   │  ThreadPoolExecutor(max_workers=N)  │
                   │  threading.Barrier(N) start gate    │
                   └─────────────────┬──────────────────┘
                                     │  each of N threads:
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                             ▼
  conn = pool.connect()      conn = pool.connect()         conn = pool.connect()
  cur = conn.cursor()        cur = conn.cursor()           cur = conn.cursor()
  cur.execute(HEAVY)  ───────────────────────────────► [DuckDB C++ engine]
     │  SPIKE-01: GIL RELEASED (with nogil in _lib.pyx) → threads parallelize
  cur.fetch_arrow_table() ───────────────────────────► [pyarrow read_all]
     │  SPIKE-02: GIL RE-HELD during Table build → threads serialize
  cur.close(); conn.close()  (reset event → _release_arrow_allocators)
        │                            │                             │
        └────────────────────────────┴─────────────────────────────┘
                                     │
                          wall_clock_time = max over threads
                                     │
              speedup = N*single_call_time / wall_clock_time
              bounds:  1.0 (full serial)  ◄──►  N (ideal parallel)
                                     │
                                     ▼
                  go/no-go (SPIKE-03): claim/disclaim + offload guidance
```

### Recommended Project Structure
```
benchmarks/                        # KEPT, re-runnable regression artifact
├── __init__.py                    # (optional) keep importable; docstring-clean
├── _harness.py                    # timing core: barrier-gated concurrent runner,
│                                  #   median-of-trials, single vs N, speedup calc
├── gil_release.py                 # the two measurements (SPIKE-01 execute,
│                                  #   SPIKE-02 fetch_arrow_table); CLI entry
└── README.md                      # how to run + how to read the speedup numbers
.planning/phases/22-feasibility-spike/
└── 22-GO-NO-GO.md                 # SPIKE-03 deliverable (written prose)
```
Throwaway spike scaffolding (dataset-size sweeps, fetchall debugging probe, one-off diagnostics) lives in a scratch location (e.g. `$TMPDIR` or a git-ignored `scratch/`) and is NOT committed.

### Pattern 1: Barrier-gated concurrent timing
**What:** All N worker threads block on a `threading.Barrier(N)` before the timed call, so the timed region reflects genuine overlap rather than staggered start/finish.
**When to use:** Every concurrent measurement in this spike.
**Example:**
```python
# Source: verified this session against the installed driver stack
import threading, time, statistics
from concurrent.futures import ThreadPoolExecutor

def concurrent_wall(call, conns, n, trials):
    def trial():
        barrier = threading.Barrier(n)
        def task(conn):
            barrier.wait()            # release all threads together
            return call(conn)
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(task, conns))
        return time.perf_counter() - t0
    return statistics.median(trial() for _ in range(trials))
```

### Pattern 2: Single-call baseline + speedup bounds
**What:** Headline number is `speedup = N * single_call_time / wall_clock_time`, interpreted against two bounds: `1.0` = full serialization, `N` = ideal parallelism.
**When to use:** Reporting both SPIKE-01 and SPIKE-02.
**Example:**
```python
# Source: methodology locked in CONTEXT; arithmetic verified this session
single = statistics.median(time_one(conns[0]) for _ in range(trials))  # 1 thread
wall   = concurrent_wall(time_one, conns, n=N, trials=trials)
speedup       = (N * single) / wall          # → ~N means parallel, ~1 means serial
parallel_eff  = speedup / N                   # fraction of ideal achieved
```

### Pattern 3: Drive the real production checkout path (KEPT benchmark)
**What:** Use `create_pool(DuckDBConfig(...))` and check out per-thread connections, so the benchmark measures the same path Phase 24 will wrap.
**When to use:** The kept benchmark (not throwaway scaffolding).
**Example:**
```python
# Source: verified this session — checkedout()==0 after, reset fires correctly
import tempfile, os
from adbc_poolhouse import DuckDBConfig, create_pool

db = os.path.join(tempfile.mkdtemp(), "bench.db")   # file-backed: pool_size>1 allowed
pool = create_pool(DuckDBConfig(database=db, pool_size=N, max_overflow=0))

def one(query):
    conn = pool.connect()
    try:
        cur = conn.cursor()
        cur.execute(query)
        tbl = cur.fetch_arrow_table()        # SPIKE-02; for SPIKE-01 use cur.fetchone()
        cur.close()
        return tbl.num_rows
    finally:
        conn.close()   # returns to pool → reset event → _release_arrow_allocators
```

### Anti-Patterns to Avoid
- **In-memory DuckDB with `pool_size=N`:** `DuckDBConfig` *rejects* `pool_size>1` with `database=":memory:"` (each in-memory connection is an isolated empty DB). Use a file-backed temp DB for `pool_size=N`. (Pitfall 1)
- **Python `sleep()` UDF to simulate slow I/O:** re-acquires the GIL; measures the opposite of what you want. Use a heavy C-side query. (Pitfall 2)
- **No start barrier:** staggered thread start understates parallelism. (Pattern 1)
- **Microsecond-scale queries:** thread-pool spin-up and Python framing swamp the signal. Size queries to ~0.1–1s+ per call. (Pitfall 3)
- **Splitting execute and fetch into separate timed offloads hoping they overlap:** fetch serializes on the GIL, so this buys nothing and complicates the design — informs Phase 24 offload granularity, not the spike itself.
- **Sharing one connection across threads:** ADBC forbids concurrent access; each thread needs its own checked-out connection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Concurrent thread start synchronization | Sleep-then-hope, manual flags | `threading.Barrier(N)` | Deterministic simultaneous release; no race |
| Robust central-tendency over jittery trials | Mean, hand-rolled sort-and-pick | `statistics.median` | Locked; resistant to outliers/jitter |
| High-resolution wall-clock | `time.time()` deltas | `time.perf_counter()` | Monotonic, not NTP-adjustable; locked |
| In-proc DuckDB connection + heavy compute | Custom C harness, raw libduckdb | `create_pool(DuckDBConfig(...))` + heavy SQL | Drives the real production path; DuckDB does the C-side work |
| GIL-release detection | `ctypes`/`sys` GIL introspection hacks | Wall-clock speedup ratio | The speedup ratio *is* the GIL-release signal; introspection is fragile and unnecessary |

**Key insight:** The entire spike is a wall-clock differential experiment. The only thing worth building is a tight, honest timing harness; everything underneath (engine, GIL behaviour, Arrow materialization) is already in the installed libraries and must not be reimplemented.

## Runtime State Inventory

> Greenfield-style spike (adds a `benchmarks/` dir + one planning doc; writes no production/runtime code, registers no services, stores no keyed data). Included for completeness because the phase touches packaging surface.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — benchmark uses an ephemeral `tempfile` DuckDB DB discarded each run | None |
| Live service config | None — DuckDB in-proc only, no network, no external service | None |
| OS-registered state | None — no daemons, schedulers, or registrations | None |
| Secrets/env vars | None — no credentials; DuckDB needs none. (`DUCKDB_*` env vars exist for config but the benchmark sets `database` explicitly) | None |
| Build artifacts | A new top-level `benchmarks/` dir. If made an importable package, confirm it is NOT shipped in the wheel (it is outside `src/`, so `uv_build` won't include it by default — verify no packaging glob picks it up) | Verify `benchmarks/` stays out of the built wheel (it should, being outside `src/`) |

## Common Pitfalls

### Pitfall 1: In-memory DuckDB silently can't host a multi-connection pool
**What goes wrong:** `create_pool(DuckDBConfig(pool_size=N))` with the default `database=":memory:"` raises `ConfigurationError` (each in-memory connection is an isolated empty DB; the config enforces `pool_size=1`). A benchmark that needs N concurrent connections cannot use the default config.
**Why it happens:** In-memory DuckDB databases are per-connection isolated; the config guards against the footgun.
**How to avoid:** Use a file-backed temp DB: `DuckDBConfig(database=str(tmp/"bench.db"), pool_size=N, max_overflow=0)`. Verified this session (`pool.checkedout()==0` after, correct results). The heavy query uses `range(...)` / `generate_series` so no pre-loaded data is needed — the file DB can be empty.
**Warning signs:** `ConfigurationError: pool_size > 1 with database=":memory:"` at pool creation.

### Pitfall 2: Python `sleep()` UDF measures the wrong thing
**What goes wrong:** Simulating "slow I/O-bound execute" with a Python scalar UDF that `time.sleep()`s makes the concurrent benchmark *serialize* — but for the wrong reason (the Python UDF re-acquires the GIL), falsely implying ADBC doesn't release it.
**Why it happens:** A Python callback inside the query re-enters the interpreter and holds the GIL for its whole duration.
**How to avoid:** Use a heavy *C-side* query (large `range`/`generate_series` join or aggregation) so all the work stays in the DuckDB C++ engine under `with nogil:`. If a deliberate timed wait is ever needed, it must block with the GIL released (a pure-C sleep), not a Python UDF. Locked in CONTEXT; verified by the execute result (3.2–3.7x) which proves the C path releases the GIL.
**Warning signs:** "execute" benchmark showing ~1.0x speedup (would contradict the well-established HIGH-confidence premise and the measured result).

### Pitfall 3: Microsecond queries hidden under thread-pool overhead
**What goes wrong:** `SELECT 1`-scale calls finish in microseconds; `ThreadPoolExecutor` spin-up, the barrier, and Python framing dominate, so the speedup ratio is noise.
**Why it happens:** Fixed per-call Python/thread overhead is constant; if the real work is tiny, overhead is the signal.
**How to avoid:** Size each call to ~0.1–1s+. Verified working sizes this session: execute heavy join over `range(0, 3_000_000)`-scale or a 20M-row `range` aggregate; fetch of 8M–20M rows (≈0.5s single-call at 20M). Warm up once before timing. Report median of ≥3 trials.
**Warning signs:** Wildly varying speedup across trials; speedup > N (impossible — indicates timing the wrong region or staggered starts).

### Pitfall 4: Staggered thread start understates parallelism
**What goes wrong:** Without a start barrier, the first thread's call may finish before the last thread's begins, so the "concurrent" wall-clock is closer to serial than reality.
**Why it happens:** Thread creation and scheduling are not simultaneous.
**How to avoid:** `threading.Barrier(N)` released inside each task immediately before the timed call (Pattern 1).
**Warning signs:** execute speedup noticeably below the expected ~N even though the C path releases the GIL.

### Pitfall 5: Conflating the measured fetch serialization with a "no-go"
**What goes wrong:** Reading SPIKE-02's ~1.2–1.4x as "the async layer doesn't work" and blocking the milestone.
**Why it happens:** Misframing materialization-bound serialization as a failure of the GIL premise.
**How to avoid:** The go/no-go must separate the two findings: GIL release during `execute` is confirmed (→ I/O concurrency on network backends is soundly *inferred* → GO), while `fetch_arrow_table` is materialization-bound (→ a *named caveat* on concurrency for large-result fetches, plus offload-granularity guidance — NOT a blocker). The real-world async payoff is network *wait* overlap, which the execute result supports; materialization cost exists in sync today too.
**Warning signs:** Go/no-go prose that treats the fetch number as gating the whole milestone rather than as a documented limit.

## Code Examples

### SPIKE-01: concurrent heavy `execute` (GIL-release proxy)
```python
# Source: verified this session — measured 3.22x (N=4, small) / 3.67x (N=4, 20M rows)
HEAVY_EXEC = """
SELECT count(*) FROM (
  SELECT a.i AS x FROM range(0, 3000000) a(i)
  JOIN range(0, 30) b(j) ON (a.i % 7) = (b.j % 7)
) t
"""
def time_execute(conn):
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(HEAVY_EXEC)
    cur.fetchone()                # tiny result: isolates execute, not materialization
    dt = time.perf_counter() - t0
    cur.close()
    return dt
```

### SPIKE-02: concurrent large `fetch_arrow_table` (materialization)
```python
# Source: verified this session — measured 1.23x (N=4, 8M) / 1.40x (N=4, 20M rows)
HEAVY_FETCH = (
    "SELECT i, i*2 AS j, i%97 AS k, hash(i) AS h, (i*3.14159) AS f "
    "FROM range(0, 20000000) t(i)"
)
def time_fetch(conn):
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(HEAVY_FETCH)
    tbl = cur.fetch_arrow_table()     # the GIL-bound materialization under test
    dt = time.perf_counter() - t0
    cur.close()
    return dt
```

### Reading the result (speedup interpretation)
```python
# speedup ≈ N   → parallel (GIL released)     [execute: ~3.2–3.7 at N=4]
# speedup ≈ 1   → serial   (GIL re-held)      [fetch:   ~1.2–1.4 at N=4]
report = {
    "single_call_s": single,
    "wall_s": wall,
    "ideal_parallel_s": single,          # lower bound
    "full_serial_s": N * single,         # upper bound
    "speedup_x": (N * single) / wall,
    "parallel_efficiency": ((N * single) / wall) / N,
}
```

## Go/No-Go Document Contract (SPIKE-03)

The `22-GO-NO-GO.md` deliverable MUST contain, at minimum:

1. **Verdict line:** GO / NO-GO with one sentence. (Expected: **GO with a named materialization caveat**, given the measured numbers.)
2. **The two measured speedup ratios** (execute vs fetch_arrow_table), each with N, dataset size, single-call/wall/ideal/serial times, and median-of-trials methodology stated.
3. **Claim** (what the async layer may honestly assert): the ADBC C path releases the GIL during `execute`, so thread-offload yields real **parallelism of C-side work** and — by inference — real **I/O concurrency** on network backends (overlapping query waits).
4. **Disclaim** (what it must NOT assert): blanket parallelism. Large `fetch_arrow_table` materialization is GIL-bound and **does not parallelize** across concurrent fetches; concurrent big-result fetches approach serialization.
5. **The inference gap, named explicitly:** in-proc DuckDB has no network wait, so this spike proves GIL release / CPU parallelism but *infers* I/O concurrency; it does not directly measure I/O concurrency. Phase 27's dual-backend matrix is where real-backend behaviour is exercised.
6. **Offload-granularity guidance for Phase 24:** offload at **whole-operation granularity** (one `to_thread` per `execute`, one per `fetch_arrow_table`); do **not** attempt to overlap a single query's execute and fetch hoping for intra-operation parallelism — fetch serializes regardless. The dedicated `CapacityLimiter(pool_size + max_overflow)` still governs cross-query concurrency, where the win is real for I/O-bound work.
7. **Doc-honesty handoff to Phase 28 (DOCS-01):** the async guide must state async wins are largest for latency/I/O-bound queries and smaller for CPU-bound large-result materialization.
8. **(Optional) Free-threaded note:** measured on the standard GIL build only; no-GIL behaviour is out of scope and unmeasured.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Assume "ADBC releases the GIL" applies to every method | Per-operation: `execute` releases (parallel), `fetch_arrow_table` materialization re-holds (serial) | Settled by this spike | Drives offload granularity + honest docs |
| GIL-release belief based on inference from native driver construction | Empirically measured against the project's exact installed stack | This session | Upgrades the SPIKE-02 premise from MEDIUM to HIGH-confidence measured fact |

**Deprecated/outdated:** None applicable — this is a fresh measurement, not a migration.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The exact speedup numbers (3.22x/3.67x execute; 1.23x/1.40x fetch) are representative; the *kept* benchmark will reproduce the same *shape* (execute ≫ fetch) on CI hardware, though absolute ratios vary by core count and dataset size | Summary, Code Examples | Low — the qualitative asymmetry (execute parallel, fetch serial) is robust and matches the source-level root cause; only absolute magnitudes shift. The benchmark is designed to re-measure, so this self-corrects. |
| A2 | `benchmarks/` (outside `src/`) is excluded from the built wheel by `uv_build` default packaging | Runtime State Inventory | Low — outside `src/` is not packaged by default; a one-line build check confirms. |

**Note:** The two headline empirical findings (execute parallelizes, fetch serializes) are **[VERIFIED: measured this session against the project's installed adbc/pyarrow/duckdb stack]**, not assumed. Only the items above carry residual assumption.

## Open Questions

1. **Exact N, dataset size, and trial count for the kept benchmark.**
   - What we know: N=4 with 8M–20M row fetches and `range(0,3M)`-scale execute joins gives clean, seconds-scale, reproducible signal on this machine.
   - What's unclear: the ideal defaults for CI hardware (which may have fewer cores). Speedup is bounded by available cores.
   - Recommendation: parameterize N / rows / trials (CLI or constants); default N to `min(4, os.cpu_count())`, size queries to ≥0.3s single-call, trials=5. This is Claude's-discretion territory per CONTEXT.

2. **Whether to include the throwaway `fetchall` control.**
   - What we know: locked OFF by default; only for debugging ambiguous fetch numbers.
   - What's unclear: nothing — the fetch numbers were unambiguous this session (clearly serial), so the control is not needed.
   - Recommendation: omit by default; keep a commented/throwaway probe pattern in scratch only if the planner wants a debugging affordance.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (standard GIL build) | Whole spike | ✓ | 3.14.2 | — |
| `adbc_driver_manager` | driver-manager path | ✓ | 1.11.0 | — |
| `adbc_driver_duckdb` | in-proc DuckDB engine | ✓ | present | — |
| `duckdb` | DuckDB engine (`[duckdb]` extra) | ✓ | 1.5.2 | — |
| `pyarrow` | `fetch_arrow_table` materialization | ✓ | 24.0.0 | — |
| `adbc_poolhouse` (`create_pool`, `DuckDBConfig`) | real checkout path | ✓ | 1.3.1 (repo) | bespoke per-thread `dbapi.connect()` (throwaway only) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none required — full stack present and verified.

## Validation Architecture

> nyquist_validation is enabled (config.json `workflow.nyquist_validation: true`). This phase produces *measurement* artifacts, not behavioural production code, so validation is lighter than a feature phase: the benchmark must run end-to-end and produce sane numbers, and the kept harness should have a smoke test.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0.0 (existing, in dev group) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest tests/ -x -q` (use `.venv/bin/` under sandbox per MEMORY) |
| Full suite command | `.venv/bin/pytest -q` |
| Benchmark smoke | `.venv/bin/python -m benchmarks.gil_release --n 2 --rows 1000000 --trials 1` (fast sanity, if CLI added) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPIKE-01 | Concurrent heavy `execute` runs and reports speedup ≈ N (parallel) | smoke/benchmark | `.venv/bin/python -m benchmarks.gil_release --measure execute --n 2` | ❌ Wave 0 |
| SPIKE-02 | Concurrent large `fetch_arrow_table` runs and reports speedup (≈1, serial) | smoke/benchmark | `.venv/bin/python -m benchmarks.gil_release --measure fetch --n 2` | ❌ Wave 0 |
| SPIKE-01/02 | Harness math: speedup, median, bounds compute correctly | unit | `.venv/bin/pytest tests/test_benchmarks_harness.py -x` (assert on tiny synthetic timings) | ❌ Wave 0 |
| SPIKE-03 | Go/no-go doc exists and contains the required sections | manual review | n/a (prose deliverable; reviewed against the SPIKE-03 contract above) | ❌ Wave 0 |

Note: do NOT assert on absolute wall-clock speedup in a CI unit test (flaky, hardware-dependent — see Pitfall 3). Unit-test the *pure* harness arithmetic (speedup/median/bounds) against synthetic inputs; treat the actual benchmark as a runnable smoke/regression script, not a pass/fail CI gate.

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/ -x -q` (existing sync suite stays green; benchmark adds no runtime import to the package)
- **Per wave merge:** `.venv/bin/pytest -q` + a manual benchmark smoke run
- **Phase gate:** full sync suite green; benchmark runs end-to-end producing the two speedup numbers; go/no-go doc reviewed against the SPIKE-03 contract

### Wave 0 Gaps
- [ ] `benchmarks/_harness.py` — barrier-gated runner + median + speedup/bounds (pure functions unit-testable)
- [ ] `benchmarks/gil_release.py` — the two measurements + CLI entry (SPIKE-01, SPIKE-02)
- [ ] `tests/test_benchmarks_harness.py` — unit test of harness arithmetic on synthetic timings
- [ ] `.planning/phases/22-feasibility-spike/22-GO-NO-GO.md` — SPIKE-03 deliverable
- [ ] (no framework install needed — pytest already present)

## Project Constraints (from CLAUDE.md / MEMORY)

- **Docstring style:** Google-style (Args/Returns/Raises), **Markdown** in docstrings (not RST `:role:` syntax). `Example:` (singular) for admonition + fenced ` ```python ` blocks. The kept `benchmarks/` module should be docstring-clean even though it is a spike artifact (CONTEXT: "polished enough to re-run"; objective note: "any kept benchmark module should still be docstring-clean").
- **Docs gate (Phase ≥7):** `uv run mkdocs build --strict` must pass for the phase. This spike adds no `docs/src/` content and no new *public* package symbols (`benchmarks/` is not part of the shipped package / `__init__.py`), so the strict build should be unaffected — but **verify** the build still passes if anything in the package surface changes. Prefer `.venv/bin/mkdocs build --strict` under sandbox (MEMORY: uv-sandbox workaround).
- **Sandbox tooling:** prefer `.venv/bin/<tool>` over `uv run <tool>` for hooks/mkdocs/pytest to avoid sandbox permission prompts (MEMORY).
- **docs-author skill:** `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` — load if writing any prose/docstrings; applies project voice + humanizer pass. The go/no-go is a *planning* artifact (not `docs/src/`), but its prose should still be clear and honest per the skill's voice.
- **STATE.md may be stale:** trust git tags + pyproject + ROADMAP over STATE.md frontmatter (MEMORY).

## Sources

### Primary (HIGH confidence — verified this session)
- Direct empirical measurement against the project's installed stack (`.venv`): execute 3.22x/3.67x, fetch 1.23x/1.40x at N=4 — the decisive SPIKE-01/02 evidence.
- ADBC driver-manager shipped source (read directly): `adbc_driver_manager/dbapi.py` (`Cursor.fetch_arrow_table` → `_RowIterator.fetch_arrow_table` → `_blocking_call(reader.read_all, ...)`), `_reader.pyx` (`AdbcRecordBatchReader.read_all` → `pyarrow.RecordBatchReader.read_all`), `_lib.pyx` (`with nogil:` blocks in execute/stream-fetch; `_blocking_call_impl` only installs the SIGINT handler on the main thread).
- adbc-poolhouse source (read directly): `_pool_factory.py` (`_create_pool_impl`, `reset` event → `_release_arrow_allocators`, defaults), `_driver_api.py` (driver-manager connect shapes), `_duckdb_config.py` (in-memory `pool_size=1` enforcement).
- Verified library versions via `.venv` import: adbc_driver_manager 1.11.0, pyarrow 24.0.0, duckdb 1.5.2, Python 3.14.2, standard GIL build.

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` and `PITFALLS.md` (Pitfall 3) — flagged the GIL/materialization premise as the secondary risk; this spike's measurement resolves it.

### Tertiary (LOW confidence)
- None — the central claim was measured, not inferred.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and version-verified; no new deps.
- Architecture (benchmark methodology): HIGH — patterns verified end-to-end this session, including the real `create_pool` checkout path with `checkedout()==0` after.
- Central findings (execute parallel / fetch serial): HIGH — directly measured against the exact installed stack and corroborated by reading the shipped `.pyx`/`.py` source.
- Pitfalls: HIGH — in-memory `pool_size` guard, sleep-UDF trap, and overhead/start-stagger issues all confirmed against code/measurement.

**Research date:** 2026-06-26
**Valid until:** ~2026-07-26 for the methodology (stable). The measured ratios are tied to the installed adbc/pyarrow/duckdb versions and this machine's core count; the kept benchmark is the living source of truth and should be re-run on CI hardware during planning/execution.
