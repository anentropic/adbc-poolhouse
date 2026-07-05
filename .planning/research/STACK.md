# Technology Stack

**Project:** adbc-poolhouse v1.5.0 — Async Cursor Completion
**Researched:** 2026-07-01
**Research Type:** Subsequent Milestone — four deferred async cursor methods (`fetch_record_batch`, `adbc_ingest`, `fetch_df`, `fetch_polars`) + P2 async edge-case suite
**Overall confidence:** HIGH — every claim below is grounded in introspection of the packages installed in this repo's `.venv`, cross-checked against latest PyPI releases.

## Headline Conclusion

**v1.5.0 requires ZERO new runtime dependencies and ZERO new extras.** All four new methods are pure offload wrappers over methods that **already exist natively** on the wrapped `adbc_driver_manager.dbapi.Cursor` — identical in shape to the already-shipped `fetch_arrow_table` (ACUR-04). Their only Arrow-side need is `pyarrow`, which is already a core runtime dependency (`pyarrow>=23.0.1`, installed `24.0.0`). pandas and polars stay **user-supplied runtime deps** — ADBC itself raises a clear `ModuleNotFoundError` if they are absent, exactly how poolhouse already treats missing ADBC drivers. The only optional change is a **dev-group-only** addition of pandas/polars so the test suite can actually exercise `fetch_df`/`fetch_polars`.

This mirrors and extends the v1.4.0 posture ("the async layer adds exactly one runtime dependency, `anyio`, behind `[async]`") — v1.5.0 adds none.

## Ground-Truth Method Signatures (from installed `adbc-driver-manager==1.11.0`)

Introspected via `.venv/bin/python -c "import inspect, adbc_driver_manager.dbapi as d; ..."`. These are the exact signatures the async wrappers offload to.

### `fetch_record_batch`

```python
def fetch_record_batch(self) -> "pyarrow.RecordBatchReader": ...
```

- No parameters. Returns a **streaming** `pyarrow.RecordBatchReader` bound to the underlying result/statement.
- Source calls `_requires_pyarrow()` and raises `ProgrammingError("Cannot fetch_record_batch() before execute()", INVALID_STATE)` if called before `execute()`.
- **Design headline (already flagged in requirements):** unlike `fetch_arrow_table` (which materializes a self-owning `pyarrow.Table`), this returns a **reader tied to the cursor/connection lifetime**. Reading batches after the connection is checked in (reset event closes the cursor) will dangle (RESEARCH Pitfall 7 / EDGE-21). The `RecordBatchReader`-lifetime-vs-reset-event-checkin question is a **design** concern for the roadmap, **not** a stack/dependency concern — no new library solves it.

### `adbc_ingest`

```python
def adbc_ingest(
    self,
    table_name: str,
    data: pyarrow.RecordBatch | pyarrow.Table | pyarrow.RecordBatchReader | CapsuleType,
    mode: Literal["append", "create", "replace", "create_append"] = "create",
    *,
    catalog_name: str | None = None,
    db_schema_name: str | None = None,
    temporary: bool = False,
) -> int: ...
```

- `data` accepts any Arrow PyCapsule-Protocol object (`__arrow_c_array__` / `__arrow_c_stream__`), so callers are **not** forced to hold a `pyarrow` object — anything Arrow-compatible works. `CapsuleType` is the raw PyCapsule case.
- `catalog_name`, `db_schema_name`, `temporary` are marked **EXPERIMENTAL** in the ADBC docstring — surface them as-is; do not add stability guarantees.
- Returns `int` (rows inserted, or `-1` if the driver cannot report).
- Note: this method **writes** — it holds the connection for the duration of a bulk load. It is a natural fit for the existing `cancellable_offload` + `on_abort=self._owner.invalidate` pattern (a cancelled mid-ingest C call poisons the connection).

### `fetch_df`

```python
def fetch_df(self) -> "pandas.DataFrame": ...
```

- No parameters. Internally delegates to `self._results.fetch_df()` → `reader.read_pandas()` (a **pyarrow** method that imports pandas lazily).
- Raises `ProgrammingError("Cannot fetch_df() before execute()", INVALID_STATE)` before `execute()`.

### `fetch_polars`

```python
def fetch_polars(self) -> "polars.DataFrame": ...
```

- No parameters. Internally does `import polars; polars.from_arrow(self.fetch_arrow())`.
- Raises `ProgrammingError` before `execute()`.

## How ADBC Signals Missing pandas / polars (verified)

This is the evidence backing "pandas/polars must NOT become poolhouse deps." Confirmed by running the pyarrow/ADBC code paths with pandas and polars **uninstalled** in this `.venv`:

| Method | Missing-dep trigger | Error surfaced | poolhouse action |
|--------|--------------------|-----------------|------------------|
| `fetch_df` | `reader.read_pandas()` (pyarrow) does `import pandas` lazily | `ModuleNotFoundError: No module named 'pandas'` (verified live) | **Do not catch, do not wrap.** Let it propagate through the offload chokepoint unchanged (ACUR-06 / EDGE-17), exactly like an `AdbcError`. |
| `fetch_polars` | ADBC's `fetch_polars` does `import polars` at call time | `ModuleNotFoundError: No module named 'polars'` | Same — propagate unchanged. |
| all four (before `execute`) | `self._results is None` | `adbc_driver_manager.dbapi.ProgrammingError` (subclass of `DatabaseError` → `Error` → `Exception`) | Propagate unchanged. |
| `fetch_record_batch` (no pyarrow) | `_requires_pyarrow()` | `ProgrammingError("This API requires PyArrow to be installed")` — unreachable for poolhouse since pyarrow is a hard core dep | N/A |

**Consequence for the roadmap:** poolhouse does not need a `try/except ImportError` or a bespoke "pandas not installed" error. The single offload chokepoint already re-raises worker exceptions with exact type and traceback. The clean, actionable `ModuleNotFoundError` reaches the caller verbatim — this is the *documented, intended* behaviour and is consistent with how poolhouse surfaces missing ADBC drivers. **Just document it** (guide note: "`fetch_df`/`fetch_polars` require you to install pandas/polars yourself").

## Recommended Stack (v1.5.0 delta)

### Core Runtime — NO CHANGES

| Technology | Current bound | Installed | Purpose in v1.5.0 | Why unchanged |
|------------|---------------|-----------|-------------------|----------------|
| `adbc-driver-manager` | `>=1.8.0` | `1.11.0` (= latest) | Provides all four methods natively on `dbapi.Cursor` | Methods present since well before 1.8.0; no bump needed |
| `pyarrow` | `>=23.0.1` (core dep) | `24.0.0` (= latest) | `RecordBatchReader` return type; `Table`/`RecordBatch`/PyCapsule inputs for `adbc_ingest`; underpins `read_pandas` and `from_arrow` | Already core; the streaming reader type is already available |
| `anyio` | `>=4.13` (`[async]` extra) | `4.14.1` (= latest) | Unchanged offload/limiter/cancel plumbing; new methods reuse `offload` / `cancellable_offload` verbatim | No new anyio surface used |

### Extras — NO CHANGES

`[async] = anyio>=4.13` stays exactly as shipped. **Do NOT add** a `[pandas]`, `[polars]`, or `[dataframe]` extra — the maintainer has ruled these out; pandas/polars are user-supplied, ADBC-signalled optional deps.

### Dev group — ONE optional addition (test-only)

| Library | Suggested dev bound | Latest | Why (dev-only) | Distinction |
|---------|--------------------|--------|-----------------|-------------|
| `pandas` | `pandas>=2.0` (or unpinned in `[dependency-groups].dev`) | `3.0.3` | So the suite can assert `fetch_df` returns a real `pandas.DataFrame` (not just that it offloads) | **DEV-GROUP ONLY — NOT a runtime dep, NOT an extra.** Exercises the method; never shipped. |
| `polars` | `polars>=1.0` (or unpinned) | `1.42.1` | So the suite can assert `fetch_polars` returns a real `polars.DataFrame` | Same — dev-group only. |

This is the crux distinction the downstream consumer asked for:

> **Runtime/extra dep** = poolhouse forces it on every consumer who installs the extra. ❌ Not doing this for pandas/polars.
> **Dev-group test dep** = only present in *this repo's* test env to actually call `fetch_df`/`fetch_polars` and check the return type. ✅ Acceptable and recommended.

**Alternative (equally valid):** add pandas/polars behind a **dev-only** marker/param and `pytest.importorskip("pandas")` / `importorskip("polars")` in the relevant tests, so contributors without them installed still get a green (skipped) suite. Recommend `importorskip` guards regardless, since the missing-dep propagation test (asserting `ModuleNotFoundError`) must run in an env where they are *absent* — a `no-df` test env or a subprocess/monkeypatched-import test.

### P2 edge-case suite — NO new dev deps

Audited EDGE-08, 13/14, 20, 22/23, 24, 31/32 in `.planning/research/ASYNC-EDGE-CASES.md`:

| Edge case | What it needs | Already available? |
|-----------|---------------|---------------------|
| EDGE-08 (trio checkpoint delivery) | trio backend param | ✓ `trio>=0.31` in dev |
| EDGE-13/14 (contextvars in/out of worker) | stdlib `contextvars.ContextVar` | ✓ stdlib |
| EDGE-20 (cleanup error chaining) | stdlib exception `__context__` | ✓ stdlib |
| EDGE-22 (`__del__` → `ResourceWarning`) | `pytest.warns(ResourceWarning)` + `gc.collect()` | ✓ stdlib + pytest |
| EDGE-23 (no "coroutine never awaited") | `warnings`/`pytest.warns` on `RuntimeWarning` | ✓ stdlib + pytest |
| EDGE-24 (loop-shutdown, trio nursery canary) | trio nursery | ✓ `trio` in dev |
| EDGE-31/32 (timeout precision, `move_on_after`) | anyio `move_on_after`/`fail_after`; deterministic timing | ✓ anyio; `aiotools`/`pytest-timeout`/`pytest-repeat` already present |

**Conclusion:** the existing dev group (`anyio`, `trio`, `aiotools`, `pytest-repeat`, `pytest-timeout`, `pytest-adbc-replay`) fully covers the P2 suite. No additions required for edge cases.

## Typing / Stub Integration

### `_SyncCursor` Protocol extension (`src/adbc_poolhouse/_async/_cursor.py`)

The structural Protocol at lines 50–74 must gain four members. Verified strict-clean against `.venv/bin/basedpyright` (strict mode, the repo's config) in-repo:

```python
class _SyncCursor(Protocol):
    ...  # existing members
    def fetch_record_batch(self) -> pyarrow.RecordBatchReader: ...
    def adbc_ingest(
        self,
        table_name: str,
        data: pyarrow.RecordBatch | pyarrow.Table | pyarrow.RecordBatchReader | CapsuleType,
        mode: Literal["append", "create", "replace", "create_append"] = ...,
        *,
        catalog_name: str | None = ...,
        db_schema_name: str | None = ...,
        temporary: bool = ...,
    ) -> int: ...
    def fetch_df(self) -> object: ...      # pandas.DataFrame at runtime; see note below
    def fetch_polars(self) -> object: ...  # polars.DataFrame at runtime; see note below
```

Probe result: extended Protocol with the full `adbc_ingest` union (including `CapsuleType`) produced **0 real diagnostics** under strict basedpyright (only a throwaway `reportUnusedClass` from the probe scaffold itself).

### The pyarrow-stub reality (important, verified)

pyarrow `24.0.0` **does ship `py.typed`** and an `__init__.pyi`, **but that stub is an official placeholder**:

```python
"""Type stubs for PyArrow. This is a placeholder stub file.
Complete type annotations will be added in subsequent PRs."""
def __getattr__(name: str) -> Any: ...   # TODO(GH-48970): remove before release
```

**Implication:** every `pyarrow.X` member (`RecordBatchReader`, `Table`, `RecordBatch`, …) currently resolves to `Any` under basedpyright. This is why the existing `fetch_arrow_table(self) -> pyarrow.Table` annotation is already strict-clean (verified: `_cursor.py` → 0 errors), and why `-> pyarrow.RecordBatchReader` and the `adbc_ingest` `data` union will be equally clean — they degrade to `Any`, which strict mode accepts silently. **No stub package (`pyarrow-stubs`) is needed**, and adding one would risk introducing *stricter* checks than the placeholder currently enforces (avoid). Keep the annotations as real `pyarrow.*` names (self-documenting, forward-compatible with pyarrow's future real stubs) under `if TYPE_CHECKING`.

### `CapsuleType` typing

- ADBC's own stub imports `CapsuleType` from `typing_extensions` under `TYPE_CHECKING`.
- In this repo (Python floor 3.11): `types.CapsuleType` exists only on 3.13+; `typing_extensions.CapsuleType` is available (typing-extensions is a transitive dep via anyio/pydantic). **Recommendation:** import `CapsuleType` from `typing_extensions` under `TYPE_CHECKING` (matches ADBC's own choice, works on the 3.11 floor). Do **not** add `typing-extensions` as a direct runtime dep — it is TYPE_CHECKING-only here and already transitively present.

### `fetch_df` / `fetch_polars` return-type annotation choice

The wrappers can annotate returns as:
- **`-> object`** on the Protocol (poolhouse never depends on pandas/polars types) — simplest, strict-clean, no conditional import of pandas/polars stubs. **Recommended for the Protocol.**
- On the **public** `AsyncCursor.fetch_df`/`fetch_polars` methods, annotate `-> "pandas.DataFrame"` / `-> "polars.DataFrame"` under `if TYPE_CHECKING: import pandas, polars` (string/deferred annotations, never imported at runtime). This gives consumers accurate return types in their IDE **without** making pandas/polars a runtime import. basedpyright treats an unresolved `pandas`/`polars` import as `reportMissingImports` **only if** the modules aren't installed in the type-checking env — since they are in the **dev group**, the repo's own type-check run resolves them. Consumers who lack them still get correct behaviour (the string annotation is never evaluated). **Recommendation:** use the TYPE_CHECKING string-annotation approach on the public methods for good DX; keep the internal `_SyncCursor` Protocol members at `-> object` (driver-agnostic, no stub coupling).

## Alternatives Considered (and rejected)

| Category | Chosen | Alternative | Why not |
|----------|--------|-------------|---------|
| pandas/polars availability | User-supplied; ADBC raises `ModuleNotFoundError` | `[pandas]`/`[polars]` poolhouse extras | Maintainer ruling; consistent with driver treatment; ADBC already signals cleanly |
| Missing-dep handling | Propagate ADBC's `ModuleNotFoundError` unchanged | Catch + re-raise `PoolhouseError` | Offload chokepoint intentionally never re-wraps (ACUR-06/EDGE-17); the native error is already clear and actionable |
| pyarrow typing | Real `pyarrow.*` names under TYPE_CHECKING (resolve to `Any`) | Add `pyarrow-stubs` dev dep | Placeholder official stub already makes members `Any`; third-party stubs could add spurious strict errors; official stubs land in a future pyarrow |
| `CapsuleType` source | `typing_extensions` (TYPE_CHECKING) | `types.CapsuleType` | `types.CapsuleType` is 3.13+ only; floor is 3.11 |
| pandas/polars in tests | dev-group + `importorskip` guards | test with monkeypatched fakes only | Real libs give a real return-type assertion; `importorskip` keeps the suite green for contributors without them |

## Installation (dev env delta)

No consumer-facing install changes. For the **development** environment only:

```bash
# Add to [dependency-groups].dev in pyproject.toml (test-only, never shipped):
#   "pandas>=2.0",
#   "polars>=1.0",
uv sync
```

No change to `[project.dependencies]`, no change to `[project.optional-dependencies]`.

## Version Confirmation (2026-07-01)

Installed-in-`.venv` vs latest-on-PyPI (WebFetch of `pypi.org/pypi/<pkg>/json`):

| Package | Installed (`.venv`) | Latest PyPI | Notes |
|---------|--------------------|-------------|-------|
| `adbc-driver-manager` | 1.11.0 | 1.11.0 | Provides all four methods; up to date |
| `pyarrow` | 24.0.0 | 24.0.0 | `RecordBatchReader` present; ships placeholder `py.typed` stub |
| `anyio` | 4.14.1 | 4.14.1 | Unchanged from v1.4.0 |
| `trio` | 0.33.0 | 0.33.0 (installed) | dev-only, edge suite |
| `aiotools` | 2.2.3 | (installed) | dev-only, timing/scheduling edge tests |
| `basedpyright` | 1.39.5 | (installed) | strict-mode gate |
| `pandas` | **not installed** | 3.0.3 | proposed dev-group add |
| `polars` | **not installed** | 1.42.1 | proposed dev-group add |

Context7 MCP was unavailable in this session; versions were confirmed directly against PyPI JSON and by introspecting the installed packages (higher-fidelity than Context7 for this "exact installed signature" question).

## Sources

- Installed-package introspection via `.venv/bin/python -c "import inspect, adbc_driver_manager.dbapi as d; ..."` — signatures + source of all four methods (HIGH confidence, ground truth).
- Live missing-dep behaviour: ran `reader.read_pandas()` / `import polars` with pandas & polars absent in `.venv` → `ModuleNotFoundError` (HIGH, verified).
- `.venv/bin/basedpyright` strict-mode probes on `_cursor.py` and an extended-Protocol scaffold (HIGH, verified: 0 real diagnostics).
- pyarrow `__init__.pyi` placeholder-stub contents read from the installed wheel (HIGH, verified).
- PyPI JSON for adbc-driver-manager (1.11.0), pyarrow (24.0.0), anyio (4.14.1), pandas (3.0.3), polars (1.42.1) (HIGH).
- `.planning/milestones/v1.4.0-research/STACK.md` — the `[async]`/anyio "one runtime dep" posture this milestone continues (project doc).
- `.planning/research/ASYNC-EDGE-CASES.md` — P2 edge-case definitions (EDGE-08/13/14/20/22/23/24/31/32) confirming stdlib-only test needs (project doc).
