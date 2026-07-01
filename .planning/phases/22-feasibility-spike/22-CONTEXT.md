# Phase 22: Feasibility Spike - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning
**Source:** /gsd-discuss-phase 22 --assumptions (assumptions-mode discussion, captured into CONTEXT.md so downstream agents inherit the decisions)

<domain>
## Phase Boundary

This phase is a **measurement spike** that empirically validates the GIL-release premise underpinning the entire v1.4.0 async API, then records an honest go/no-go that fixes what concurrency the async layer may claim **before any production code is written**.

**In scope:**
- Two DuckDB benchmarks through the real ADBC driver-manager path:
  1. N concurrent `execute` calls (SPIKE-01)
  2. N concurrent `fetch_arrow_table` calls (SPIKE-02)
- A written go/no-go document (SPIKE-03) that interprets the numbers, states what the async layer can honestly claim vs disclaim, and explicitly gates Phase 24.

**Out of scope:**
- Any `src/adbc_poolhouse/_async/` code, anyio, `CapacityLimiter`, `to_thread`, cancellation.
- The Phase 23 test harness (`BlockingStubCursor`, virtual clock, import-lint).
- Real network backends. DuckDB in-proc only.
- Free-threaded / no-GIL (3.13t) builds — measure on the standard GIL build only.
</domain>

<decisions>
## Implementation Decisions

### Terminology framing (LOCKED — the go/no-go doc MUST use these terms precisely)
The user corrected sloppy "compute concurrency" phrasing. Hold this distinction in the benchmark interpretation and especially in the SPIKE-03 write-up:

- **Parallelism** = real simultaneous CPU work across cores. In CPython this is normally only possible via multiprocessing, **except** when a C extension releases the GIL — then plain *threads* achieve parallelism (the NumPy pattern). A heavy DuckDB query run on N threads, *if the ADBC driver releases the GIL*, is observed as **parallelism**: wall-clock approaches single-call time.
- **I/O concurrency** = overlapping *wait* states (network round-trips to a remote warehouse). The async layer's real-world payoff. Same enabling mechanism (GIL released during the blocking C call), but a genuinely different phenomenon from CPU parallelism.
- The `execute` benchmark is a **proxy for the GIL-release mechanism**. It directly demonstrates *parallelism of C-side compute*. Because in-proc DuckDB has **no I/O wait**, the benchmark **cannot itself demonstrate I/O concurrency** — it shows the GIL is released, from which I/O concurrency on network backends is *inferred*. The go/no-go MUST name this inference gap and MUST NOT dress up "GIL released → threads parallelize a heavy query" as "we proved I/O concurrency."

### What each benchmark actually tests
- **SPIKE-01 (execute):** Does the ADBC C driver release the GIL during `execute`? Observed as thread parallelism of C++ engine work. This is the basis for *inferring* I/O concurrency on real backends. Confidence on the premise is already HIGH from research; the spike confirms it empirically.
- **SPIKE-02 (fetch_arrow_table):** The core unknown. Does pyarrow `Table` materialization release the GIL (→ parallelizes across threads) or re-acquire it (→ serializes)? MEDIUM confidence in research; this is what the spike exists to settle. The answer drives Phase 24 offload granularity and Phase 28 doc honesty.

### Concurrency mechanism for the benchmark
- Drive concurrency with **raw threads** (`ThreadPoolExecutor` / `threading.Thread`) — **NOT** anyio. The point is to isolate the GIL-release question from the async machinery that doesn't exist yet. Pulling in `to_thread` + `CapacityLimiter` here would conflate the two.

### "Slow I/O-bound execute" — how to simulate
- **No real network.** Go through the ADBC driver manager against in-proc DuckDB.
- The default "slow execute" is a **heavy C-side query** (large join / aggregation / `generate_series`) that runs in the DuckDB C++ engine with the GIL released — this is the faithful GIL-release proxy.
- If we want to demonstrate I/O-bound (wait-state) concurrency specifically, **simulate the wait deliberately** (controlled, known duration) — but the wait MUST block with the GIL released to be faithful. A Python scalar UDF that `sleep()`s would re-acquire the GIL and measure the wrong thing, so prefer a controlled heavy C-side query over injected sleeps. Nail down the exact mechanism at plan/research time.

### Artifact tiers (two distinct categories)
- **Benchmark code** (the timing harness + the execute and fetch_arrow_table measurements): **KEPT and polished enough to re-run** — e.g. a `benchmarks/` directory. Reusable as a regression check after Phase 24 ships the async wrappers. This pulls it into the project's maintained-artifact posture.
- **Spike scaffolding** (exploratory probing, dataset-generation experiments, one-off diagnostics): **throwaway** — not kept, not polished.

### Methodology
- Warmup runs, multiple trials, report **median** (in-proc DuckDB is fast and jittery; single-shot timing is unreliable).
- **Ideal-parallel baseline:** `single_call_time` (perfect scaling) vs `N × single_call_time` (full serialization). The **speedup ratio** against these bounds is the headline number for each benchmark.
- Choose N and dataset/result sizes so each call runs in seconds (not microseconds) and thread-pool startup cost does not swamp the signal.

### Tooling / deps
- No new runtime dependencies. Stdlib `time.perf_counter` for timing. Uses the existing `[duckdb]` optional extra (already present) + `adbc-driver-duckdb`.

### Go/no-go document
- Lives at `.planning/phases/22-feasibility-spike/` (planning artifact, written prose, gates Phase 24). It is the SPIKE-03 deliverable — not user-facing docs (Phase 28 owns the honest user guide, informed by these findings).

### Claude's Discretion
- Exact dataset shape, N values, and trial counts (subject to the methodology constraints above).
- Internal structure of the benchmark harness module(s) and the throwaway spike scaffolding.
- Precise format of the go/no-go document, provided it covers: claim/disclaim, the parallelism-vs-I/O-concurrency inference gap, and offload-granularity guidance for Phase 24.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition & requirements
- `.planning/ROADMAP.md` — Phase 22 details, success criteria, dependency on Phase 21.1, gates Phase 24.
- `.planning/REQUIREMENTS.md` — SPIKE-01, SPIKE-02, SPIKE-03 acceptance text.

### Research grounding (GIL premise)
- `.planning/research/SUMMARY.md` — Executive summary; flags the GIL-release premise for pyarrow materialization as the secondary risk requiring a feasibility spike (HIGH confidence on execute, MEDIUM on materialization).
- `.planning/research/PITFALLS.md` — Pitfall 3 (GIL / pyarrow materialization caveat) — the specific risk this spike resolves.

### Sync path being benchmarked
- `src/adbc_poolhouse/_driver_api.py` — ADBC driver-manager connection path the benchmark drives.
- `src/adbc_poolhouse/_duckdb_config.py` — DuckDB config used to build the in-proc pool.
- `pyproject.toml` — `[duckdb]` optional extra; dev/test tooling.
</canonical_refs>

<specifics>
## Specific Ideas

- A contrast measurement of concurrent `fetchall` (pure Python-object construction, which definitely holds the GIL) was considered as a known-serialized control. **Decision: do NOT include it by default.** Only reach for it if the `fetch_arrow_table` numbers are ambiguous and we need to debug *why* materialization behaves as it does.
- The execute benchmark's heavy-query approach means SPIKE-01 demonstrates the GIL is released during `execute`; the I/O-concurrency claim for network backends is an inference layered on top, to be stated as such.
</specifics>

<deferred>
## Deferred Ideas

- Validating I/O concurrency against a real network backend (e.g. Snowflake cassette / live) — out of scope for the spike; the Phase 27 dual-backend matrix exercises real backends once the async surface exists.
- Free-threaded (no-GIL) Python behaviour — not measured here.
- `fetchall` serialization control — deferred unless needed for debugging (see Specific Ideas).
</deferred>

---

*Phase: 22-feasibility-spike*
*Context gathered: 2026-06-26 via /gsd-discuss-phase --assumptions, captured to CONTEXT.md*
