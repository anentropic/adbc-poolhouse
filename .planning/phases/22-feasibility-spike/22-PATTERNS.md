# Phase 22: Feasibility Spike - Pattern Map

**Mapped:** 2026-06-26
**Files analyzed:** 5 (4 created + 1 packaging verification)
**Analogs found:** 3 / 5 (2 greenfield — no `benchmarks/` precedent in repo)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `benchmarks/_harness.py` | utility (pure timing/arithmetic + barrier-gated runner) | batch / transform | none (greenfield) — borrow module/docstring conventions from `src/adbc_poolhouse/_duckdb_config.py` | no-analog (conventions only) |
| `benchmarks/gil_release.py` | utility / script entry (the two measurements + CLI) | request-response (pool checkout → execute/fetch) | `tests/test_pool_factory.py` (real `create_pool(DuckDBConfig(...))` checkout path) | role-partial; checkout path = exact |
| `benchmarks/__init__.py` | package marker (optional) | n/a | `tests/__init__.py` / any package `__init__.py` | trivial |
| `tests/test_benchmarks_harness.py` | test (unit, pure arithmetic on synthetic timings) | transform | `tests/test_translators.py` (pure-function unit tests, no driver/mocking) | exact |
| `pyproject.toml` (verify only — wheel excludes `benchmarks/`) | config | n/a | existing `[tool.uv_build]` / packaging section | verification |

**Greenfield note:** there is **no existing `benchmarks/` directory** in the repo (`ls benchmarks/` → no such file). This phase creates a brand-new top-level dir outside `src/`. There is therefore **no in-repo benchmark precedent** to copy structure from — the planner must borrow (a) the real checkout path from `tests/test_pool_factory.py`, (b) module/docstring conventions from `src/adbc_poolhouse/_duckdb_config.py`, and (c) the pure-unit-test shape from `tests/test_translators.py`. The harness internal structure and the methodology code are spelled out verbatim in `22-RESEARCH.md` (Patterns 1–3, Code Examples) and should be treated as the primary source for the *body* of these files.

## Pattern Assignments

### `benchmarks/gil_release.py` (utility/script, request-response)

**Analog:** `tests/test_pool_factory.py` — the only place in the repo that drives the real `create_pool(DuckDBConfig(...))` → `pool.connect()` → `cursor()` → `execute()` / `fetch_arrow_table()` → `close()` lifecycle that this benchmark must measure. This is the production checkout path CONTEXT mandates (not a bespoke per-thread `dbapi.connect()`).

**Import pattern** (`tests/test_pool_factory.py` lines 1-16) — public API import surface:
```python
from adbc_poolhouse import (
    ConfigurationError,
    DuckDBConfig,
    create_pool,
)
```
(Benchmark needs only `DuckDBConfig, create_pool`; import from the top-level package, not the `_`-prefixed module, matching this file. Add stdlib `tempfile, os, threading, time, statistics`, `concurrent.futures.ThreadPoolExecutor`, `argparse` per RESEARCH Standard Stack.)

**Core checkout-path pattern** (`tests/test_pool_factory.py` lines 54-69, `test_checkout_query_checkin_dispose`) — the exact lifecycle to wrap per worker thread:
```python
cfg = DuckDBConfig(database=str(tmp_path / "test.db"))
pool = create_pool(cfg)
try:
    conn = pool.connect()
    cur = conn.cursor()
    cur.execute("SELECT 42 AS answer")
    row = cur.fetchone()
    assert row == (42,)
    cur.close()
    conn.close()
    assert pool.checkedin() == 1
finally:
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]
```

**CRITICAL teardown idiom — copy verbatim:** every analog that calls `create_pool` pairs `pool.dispose()` with `pool._adbc_source.close()` in a `finally` (lines 67-69, 96-98, 535-537, 561-563). The benchmark MUST do the same after each measurement run or it leaks the ADBC source connection. The `# type: ignore[attr-defined]` comment is required (basedpyright strict mode, `_adbc_source` is private).

**File-backed DB for pool_size=N** (combine analog line 24 with RESEARCH Pitfall 1): the analog uses `tmp_path / "test.db"` (a real file) precisely because pool_size>1 needs file-backing. In a non-pytest script there is no `tmp_path` fixture, so use the RESEARCH Pattern 3 form instead:
```python
db = os.path.join(tempfile.mkdtemp(), "bench.db")   # file-backed: pool_size>1 allowed
pool = create_pool(DuckDBConfig(database=db, pool_size=N, max_overflow=0))
```

**The two measurement bodies** are given verbatim in `22-RESEARCH.md` Code Examples — copy these, do not re-derive:
- SPIKE-01 `time_execute` / `HEAVY_EXEC` (RESEARCH lines 318-334) — heavy C-side join + `fetchone()` (tiny result isolates execute).
- SPIKE-02 `time_fetch` / `HEAVY_FETCH` (RESEARCH lines 336-351) — 20M-row `range` projection + `fetch_arrow_table()`.

**Concurrency driver:** raw threads via `threading.Barrier(N)` + `ThreadPoolExecutor` (RESEARCH Pattern 1, lines 197-213). NOT anyio (locked).

**Anti-patterns from analog/RESEARCH to NOT copy:**
- Do NOT use `database=":memory:"` with `pool_size=N` — `DuckDBConfig.check_memory_pool_size` (`_duckdb_config.py` lines 102-112) raises `ConfigurationError`. File-backed only.
- Do NOT share one connection across threads (RESEARCH anti-patterns) — each thread checks out its own via `pool.connect()`.

---

### `benchmarks/_harness.py` (utility, batch/transform) — GREENFIELD

**No code analog** (no prior benchmark/timing module exists). The function bodies come straight from `22-RESEARCH.md` Patterns 1-2 (lines 197-225): `concurrent_wall(call, conns, n, trials)`, single-call baseline, and the `speedup = (N * single) / wall` / `parallel_efficiency` arithmetic. Keep these as **pure functions** so `tests/test_benchmarks_harness.py` can exercise the arithmetic on synthetic timings without spinning threads.

**Module-header + docstring convention** — borrow from `src/adbc_poolhouse/_duckdb_config.py` (lines 1-27):
```python
"""DuckDB warehouse configuration."""

from __future__ import annotations
```
Apply: one-line module docstring, `from __future__ import annotations` first import. Per CLAUDE.md / MEMORY: Google-style docstrings (Args/Returns/Raises), **Markdown** in docstrings (not RST `:role:`), `Example:` (singular) with ` ```python ` fenced blocks for the admonition box. See `_duckdb_config.py` lines 89-100 (`to_adbc_kwargs`) for the in-repo Returns-block shape and lines 22-26 for the `Example:` block shape.

**Separation-of-concerns to preserve:** keep all `create_pool` / DuckDB / connection-checkout code in `gil_release.py`; keep `_harness.py` free of any ADBC import so its math is trivially unit-testable (mirrors how `test_translators.py` tests pure config output with "no mocking needed, no ADBC driver installed", `test_translators.py` lines 4-6).

---

### `tests/test_benchmarks_harness.py` (test, unit — transform)

**Analog:** `tests/test_translators.py` (lines 1-55) — the repo's model for a **pure-function unit test with no driver, no pool, no mocking**. RESEARCH explicitly warns NOT to assert on real wall-clock speedup in CI (flaky, hardware-dependent — RESEARCH line 445 / Pitfall 3); assert only on the harness arithmetic against synthetic inputs. This makes `test_translators.py` (not the integration-style `test_pool_factory.py`) the correct analog.

**Module docstring + requirement-ID convention** (`test_translators.py` lines 1-6):
```python
"""
Unit tests for config ``to_adbc_kwargs()`` methods (TEST-05).

Tests assert exact ``dict[str, str]`` output for given config inputs.
Config models are pure data objects -- no mocking needed, no ADBC driver installed.
"""

from __future__ import annotations
```
Apply: module docstring naming the requirement (here: SPIKE-01/02 harness math), the "pure, no mocking" framing, and `from __future__ import annotations`.

**Class-per-subject + descriptive-docstring-per-test convention** (`test_translators.py` lines 28-55):
```python
class TestDuckDBToAdbcKwargs:
    """Unit tests for DuckDBConfig.to_adbc_kwargs() method."""

    def test_memory_database(self) -> None:
        """DuckDBConfig().to_adbc_kwargs() uses ':memory:' by default — maps to path key."""
        result = DuckDBConfig().to_adbc_kwargs()
        assert result == {"path": ":memory:"}
```
Apply: group harness tests in a class (e.g. `TestHarnessArithmetic`); each test has a one-line docstring describing the exact assertion; plain `assert ==` on computed values. Test cases: `speedup == N` for ideal-parallel synthetic timings, `speedup == 1` for full-serial synthetic timings, `median` over a known list, bounds (`ideal == single`, `full_serial == N*single`), and an edge (n=1).

**Note:** no pytest marker needed (the `markers` in `pyproject.toml` lines 72-75 are only `snowflake`/`databricks` for live integration). This is a plain unit test that runs in the default `tests/` collection.

---

### `benchmarks/__init__.py` (optional package marker)

If `benchmarks/` is made importable (RESEARCH recommends it so `python -m benchmarks.gil_release` works), add an `__init__.py`. Analog: any empty/docstring-only package marker such as `tests/__init__.py`. Keep it docstring-clean (one-line module docstring) per the kept-artifact posture.

---

### `pyproject.toml` (verify only)

**No edit expected.** RESEARCH Assumption A2 (line 394) + Runtime State Inventory (line 281): `benchmarks/` lives **outside `src/`**, so `uv_build` excludes it from the wheel by default. The planner's task here is a one-line **verification** (e.g. `uv build` then inspect the wheel does not contain `benchmarks/`), not a change. Flag if any packaging glob in `pyproject.toml` would pick it up.

## Shared Patterns

### Pool lifecycle teardown (applies to every `create_pool` call in the benchmark)
**Source:** `tests/test_pool_factory.py` lines 67-69 (and repeated 96-98, 535-537, 561-563)
```python
finally:
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]
```
**Apply to:** `benchmarks/gil_release.py` — wrap every benchmark run so the ADBC source connection is closed even on error. This is a universal idiom across all four `create_pool` integration tests in the repo; not copying it leaks connections.

### Module/docstring conventions (applies to all kept `benchmarks/` modules)
**Source:** `src/adbc_poolhouse/_duckdb_config.py` lines 1-3, 89-100; CLAUDE.md; MEMORY.md
- `"""One-line module docstring."""` then `from __future__ import annotations` as first import.
- Google-style docstrings (Args/Returns/Raises). **Markdown** inline (`` `create_pool` ``), never RST `:func:` / `:class:`.
- `Example:` (singular) + ` ```python ` fenced block for an admonition box (MEMORY).
**Apply to:** `_harness.py`, `gil_release.py`, `__init__.py`. CONTEXT requires the kept benchmark be "polished enough to re-run" → docstring-clean. (Docs gate: `benchmarks/` is NOT a shipped package symbol and adds no `docs/src/` pages, so `mkdocs build --strict` should be unaffected — RESEARCH line 462 — but verify.)

### Pure-function / no-driver test discipline
**Source:** `tests/test_translators.py` lines 4-6 ("pure data objects -- no mocking needed, no ADBC driver installed")
**Apply to:** `tests/test_benchmarks_harness.py` — test the harness *arithmetic only* on synthetic timings; never invoke threads, pools, or wall-clock assertions in the unit test (RESEARCH line 445).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `benchmarks/_harness.py` | utility | batch/transform | No timing-harness / benchmark module exists anywhere in the repo. Greenfield. Use RESEARCH Patterns 1-2 for the body; borrow only module/docstring conventions from `_duckdb_config.py`. |
| `benchmarks/` directory itself | — | — | No `benchmarks/` precedent (`ls benchmarks/` → absent). First benchmark dir in the project; structure comes from RESEARCH "Recommended Project Structure" (lines 180-191), not from an existing sibling. |
| `.planning/phases/22-feasibility-spike/22-GO-NO-GO.md` | prose deliverable (SPIKE-03) | — | Written planning artifact, not code — no code analog applies. Its required structure is the "Go/No-Go Document Contract" in `22-RESEARCH.md` lines 367-378 (8-point checklist). Voice: apply `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` + humanizer pass per CLAUDE.md, even though it is a `.planning/` artifact not `docs/src/`. |

**Scratch / throwaway scaffolding:** CONTEXT/RESEARCH call for throwaway probes (dataset sweeps, optional `fetchall` debug control) to live in `$TMPDIR` or a git-ignored `scratch/`. **Note for planner:** `.gitignore` currently has **no `scratch/` entry** (verified — grep for `scratch` returns nothing). If a `scratch/` dir is used, the planner must add it to `.gitignore` or the throwaway artifacts will be tracked. Prefer `$TMPDIR` to avoid touching `.gitignore`.

## Metadata

**Analog search scope:** `tests/` (all), `tests/integration/`, `src/adbc_poolhouse/` (config + pool factory), `pyproject.toml`, `.gitignore`, `tests/conftest.py`.
**Files scanned:** `tests/test_pool_factory.py` (lines 1-110, 510-564), `tests/test_translators.py` (lines 1-75), `src/adbc_poolhouse/_duckdb_config.py` (full), `tests/conftest.py` (header), `pyproject.toml` (pytest/build sections). Confirmed `benchmarks/` does not exist; `checkedout`/`checkedin` usage located in `test_pool_factory.py` only.
**Pattern extraction date:** 2026-06-26
