# Phase 26: Packaging & Extra Scoping - Research

**Researched:** 2026-06-28
**Domain:** Python packaging (optional-dependency extras), PEP 562 lazy imports, basedpyright-strict variadic-generic typing, uv-driven CI dependency scoping
**Confidence:** HIGH

## Summary

Phase 26 is narrow and mechanical, exactly as the CONTEXT.md assumptions discussion framed it. The PEP 562 import guard already ships in `src/adbc_poolhouse/__init__.py` (Phase 24/25) and basedpyright strict already reports `0 errors, 0 warnings, 0 notes` on `src/adbc_poolhouse/_async/` [VERIFIED: ran `basedpyright src/adbc_poolhouse/_async/`]. So this phase delivers four things: the `[async]` extra in `pyproject.toml` (PKG-01), regression tests that lock in the already-built guard (PKG-02/03), a dedicated no-anyio CI job (PKG-04), and a typing-tightening pass on the offload forwarding surface (PKG-05).

The single highest-value finding concerns PKG-05. The requirement text says "use `ParamSpec`/`Concatenate`", but **ParamSpec is the wrong tool for the offload chokepoint** and would not even compile. `offload()` (and `cancellable_offload()`) have their own keyword-only parameters (`limiter`, `on_dispatch`, `on_abort`), and the typing spec explicitly forbids a keyword-only parameter appearing after `*args: P.args` [CITED: typing.python.org/en/latest/spec/generics.html — "Placing keyword-only parameters between the `*args` and `**kwargs` is forbidden"]. I verified this empirically: a ParamSpec variant fails with `error: Keyword parameter "limiter" cannot appear in signature after ParamSpec args parameter (reportGeneralTypeIssues)` [VERIFIED: basedpyright probe]. The correct, idiomatic answer is the **TypeVarTuple / `Unpack` (PEP 646)** pattern — which is precisely what anyio itself uses to type `to_thread.run_sync`, `from_thread.run_sync`, and `TaskGroup.start_soon` [VERIFIED: inspected anyio 4.14.1 source: `func: Callable[[Unpack[PosArgsT]], T_Retval], *args: Unpack[PosArgsT]`]. A TypeVarTuple-typed `offload` preserves return types exactly, accepts the existing 0/1/2-positional-arg call sites unchanged, survives the `lambda: fn(*args)` indirection, and — the whole point of the tightening — now flags wrong positional-arg types that the current `Callable[..., _T]` + `*args: object` silently accepts [VERIFIED: basedpyright probe caught `fetchmany("not-an-int")`].

The no-anyio install recipe is clean because anyio is pulled **only** by the `dev` dependency-group, never by any runtime dependency [VERIFIED: uv.lock — runtime deps are `adbc-driver-manager`, `pydantic-settings`, `sqlalchemy`; anyio/trio/aiotools live under the `dev` group]. `uv sync --no-default-groups --extra duckdb` excludes anyio. The one gotcha: the no-anyio test run must **deselect `tests/async/`** (its modules import anyio at collection time) and pytest itself must be supplied without the dev group (pytest does not pull anyio transitively).

**Primary recommendation:** Type the offload surface with a `TypeVarTuple` (`Unpack[Ts]`, importable from `typing` on 3.11) mirroring anyio's own `run_sync` signature — not ParamSpec/Concatenate. Add the `[async]` extra pinned to `anyio>=4.13`. Prove the guard with a subprocess-isolated regression test (anyio blocked via a meta-path finder) so anyio need not be uninstalled in the dev env. Add a CI job that runs `uv sync --no-default-groups --extra duckdb`, asserts `import anyio` fails, and runs the sync suite with `tests/async/` deselected.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (PKG-02/03):** The PEP 562 lazy import guard is already implemented in `src/adbc_poolhouse/__init__.py` (Phase 24/25). Phase 26 **adds regression tests** that prove it — (a) `import adbc_poolhouse` succeeds with anyio absent, and (b) accessing an async symbol without anyio raises an `ImportError` whose message names the `[async]` extra. Phase 26 does **not** rewrite the `__getattr__` machinery.
- **D-02 (PKG-01):** The `[async]` optional-dependency extra pins **`anyio>=4.13`** (NOT the `>=4.0.0` the requirement text originally read). `>=4.13` matches the existing `dev` dependency-group floor and currently resolves to anyio **4.14.1** (latest). The extra adds anyio and nothing else; `[all]` gains `adbc-poolhouse[async]`. REQUIREMENTS.md PKG-01 is corrected to `>=4.13` as part of this phase's context.
- **D-03 (PKG-05):** Tighten the async typing surface so argument types are actually checked at the offload boundary. Today `offload()` in `src/adbc_poolhouse/_async/_offload.py` uses the loose `Callable[..., _T]` + `*args: object`, which passes strict only because it accepts anything. The **exact mechanism** is for the researcher to resolve (see Standard Stack — the answer is TypeVarTuple, not ParamSpec). Goal: real argument-type checking while keeping basedpyright strict at 0 errors. The factory overloads already hand-mirror the 6 sync overloads (6 == 6) and pass strict, so the focus is the offload/wrapper forwarding surface, not the factory.
- **D-04 (PKG-04):** Add a dedicated CI job that installs the package **without** anyio (package + a sync test backend such as duckdb, and none of the dev/test dependency groups that pull anyio + trio) and runs the existing sync test suite to green. The current single `quality` job always has anyio (it is in the `dev` group), so proving the zero-cost-sync claim requires a separate job. The crux is the minimal-install recipe, not the test run itself.

### Claude's Discretion
- Number and grouping of PLAN.md files; wave assignment.
- Exact pytest file/test names for the import-guard regression tests.
- Exact CI job name and `uv` install incantation for the no-anyio job, provided it genuinely excludes anyio.

### Deferred Ideas (OUT OF SCOPE)
- Dual-backend asyncio/trio parametrized test matrix → Phase 27.
- Async usage guide / API reference docs → Phase 28.
- Do not build new async runtime behaviour here — the module structure is frozen as of Phase 25.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PKG-01 | An `[async]` optional-dependency extra adds `anyio>=4.13` and nothing else; `[all]` includes it | Standard Stack → "PKG-01 extra shape"; exact `[project.optional-dependencies]` snippet mirroring existing `duckdb`/`all` entries. anyio 4.14.1 verified on PyPI + installed. |
| PKG-02 | `import adbc_poolhouse` succeeds with anyio not installed (PEP 562 `__getattr__` lazy import) | Already implemented (D-01). Code Examples → meta-path-finder + subprocess regression test that proves it without uninstalling anyio. Verified working live. |
| PKG-03 | Accessing an async symbol without anyio raises a clear `ImportError` naming the `[async]` extra | Already implemented (D-01). Verified live: `create_async_pool` access with anyio blocked raises `ImportError` containing `[async]`. Regression-test recipe in Code Examples. |
| PKG-04 | The existing sync test suite passes with anyio uninstalled (a CI job proves no hard async dependency) | Architecture → "No-anyio CI job". `uv sync --no-default-groups --extra duckdb` excludes anyio (verified via uv.lock). Must deselect `tests/async/` and assert `import anyio` fails. |
| PKG-05 | All async public API fully typed under basedpyright strict, mirroring the sync overloads | Standard Stack + Code Examples → TypeVarTuple/`Unpack` pattern (NOT ParamSpec). Empirically verified to type-check the real call sites and catch wrong arg types while keeping strict at 0 errors. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `[async]` extra declaration | Packaging metadata (`pyproject.toml`) | — | Optional-dependency extras are a `[project.optional-dependencies]` concern; nothing runtime. |
| Lazy import guard | Library import surface (`__init__.py`) | — | PEP 562 module `__getattr__` already owns this; verify only. |
| Offload arg-type checking | Type system (`_offload.py` / `_cancel.py` signatures) | Call sites (`_cursor.py`, `_pool.py`, `_connection.py`) | The chokepoint signature is where the variadic generic lives; call sites are consumers checked against it. |
| Zero-cost-sync proof | CI (`.github/workflows/ci.yml`) | Test suite (`tests/`, sync subset) | The claim is environmental (dependency scoping), so it belongs in a CI install recipe, not in app code. |
| Guard regression proof | Test suite (`tests/`) | — | Subprocess/meta-path simulation of anyio-absent; no production code change. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anyio` | `4.14.1` (floor `>=4.13`) | The only `[async]`-extra dependency; asyncio+trio-neutral thread offload | Already the milestone's chosen async foundation; floor matches the existing `dev` group [VERIFIED: pyproject `dev` group + uv.lock resolve to 4.14.1] |
| `basedpyright` | `1.39.5` (floor `>=1.38.0`) | Strict type checker; the PKG-05 gate | Project's pinned checker; strict mode already passes `_async/` at 0 errors [VERIFIED: `basedpyright --version`, `basedpyright src/adbc_poolhouse/_async/`] |
| `typing.TypeVarTuple` / `typing.Unpack` | stdlib (Python 3.11) | The PKG-05 typing mechanism for the variadic offload forwarder | Importable from `typing` on 3.11 (no `typing_extensions` needed); matches anyio's own `run_sync` typing [VERIFIED: `from typing import Unpack, TypeVarTuple` succeeds on 3.11/3.14] |
| `uv` | `0.9.18` | Dependency sync + CI install scoping | Project's package manager; `--no-default-groups`/`--extra` give exact dependency control [VERIFIED: `uv --version`] |
| `duckdb` (extra) | `>=0.9.1` | Sync test backend for the no-anyio job (in-proc, no network, no anyio) | Already an extra; the only backend needed to prove the sync path green |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | `>=8.0.0` | Test runner for the regression + no-anyio jobs | Always. Does NOT pull anyio transitively [VERIFIED: `importlib.metadata.requires('pytest')` has no anyio], so it can be supplied to the no-anyio job. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `TypeVarTuple` / `Unpack` | `ParamSpec` + `Concatenate` (as the requirement text suggests) | **Does not compile.** The offload signature has keyword-only `limiter`/`on_dispatch`; the typing spec forbids keyword-only params after `*args: P.args` [VERIFIED: basedpyright error `reportGeneralTypeIssues`]. ParamSpec also can't easily model the leading `adbc_cancel` param + the `*args` forward in `cancellable_offload`. Reject. |
| `TypeVarTuple` / `Unpack` | A bank of `@overload`s by arity (0-arg, 1-arg, 2-arg) | Works but verbose, brittle (must re-mirror every time a call shape changes), and diverges from anyio's own approach. The whole offload surface only ever forwards 0–2 positional args today, but a TypeVarTuple covers all arities in one signature for free. Reject as worse-maintenance. |
| `TypeVarTuple` / `Unpack` | Keep `Callable[..., _T]` + `*args: object`, tighten only call sites | Leaves the chokepoint accepting anything — fails the PKG-05 intent ("argument types actually checked at the offload boundary", D-03). Reject. |
| `--no-default-groups` | `--no-dev` | Equivalent for this repo (only one non-default group, `docs`, plus the default `dev`); `--no-default-groups` is the clearer, future-proof spelling. Either works. |

**Installation (PKG-01 — exact `pyproject.toml` shape):**

```toml
[project.optional-dependencies]
duckdb = ["duckdb>=0.9.1"]
# ... existing extras unchanged ...
async = ["anyio>=4.13"]            # NEW: the [async] extra, anyio and nothing else (D-02)
all = [
    "adbc-poolhouse[duckdb]",
    "adbc-poolhouse[snowflake]",
    "adbc-poolhouse[postgresql]",
    "adbc-poolhouse[quack]",
    "adbc-poolhouse[flightsql]",
    "adbc-poolhouse[bigquery]",
    "adbc-poolhouse[sqlite]",
    "adbc-poolhouse[async]",       # NEW: [all] includes [async] (D-02 / PKG-01)
]
```

**Version verification:**
- `anyio` — installed `4.14.1`, latest; floor `>=4.13` matches the `dev` group [VERIFIED: `importlib.metadata.version('anyio')` = 4.14.1; uv.lock]
- `trio` — `0.33.0` installed (relevant only because the no-anyio job must NOT pull it) [VERIFIED]
- `basedpyright` — `1.39.5` [VERIFIED]

## Package Legitimacy Audit

> No new third-party packages are introduced by this phase. The `[async]` extra references `anyio`, which is already a direct `dev`-group dependency and the milestone's chosen foundation (Phase 22+).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| anyio | PyPI | mature (>5 yrs) | very high | github.com/agronholm/anyio | OK | Already a project dependency; extra reuses it |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                          PKG-01: pyproject.toml
                  [project.optional-dependencies].async = ["anyio>=4.13"]
                                  │  (declares the extra; [all] includes it)
                                  ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  Sync consumer:  pip install adbc-poolhouse[duckdb]   (NO anyio)     │
  │      import adbc_poolhouse  ──►  __init__.py top-level imports        │
  │                                  (all sync; anyio-free)               │
  │      adbc_poolhouse.create_async_pool                                 │
  │            │                                                          │
  │            ▼  PEP 562 __getattr__  (PKG-02/03, already shipped)       │
  │      name in _LAZY_ASYNC_NAMES? ──► try: import _async               │
  │                                        │                              │
  │                              anyio absent? ──► raise ImportError      │
  │                                        │        "...[async]..."  ◄── PKG-03
  └────────────────────────────────────────┼─────────────────────────────┘
                                            ▼ anyio present
  ┌─────────────────────────────────────────────────────────────────────┐
  │  Async consumer:  pip install adbc-poolhouse[async,duckdb]           │
  │      create_async_pool ─► AsyncPool ─► AsyncConnection ─► AsyncCursor │
  │            │ every blocking call forwards through the ONE chokepoint  │
  │            ▼                                                          │
  │      offload(fn, *args, limiter=, on_dispatch=)   ◄── PKG-05 typing  │
  │      cancellable_offload(adbc_cancel, fn, *args, limiter=, on_abort=) │
  │            │  TypeVarTuple Ts: fn: Callable[[*Ts], R], *args: *Ts     │
  │            ▼                                                          │
  │      anyio.to_thread.run_sync(lambda: fn(*args), limiter=, ...)      │
  └─────────────────────────────────────────────────────────────────────┘

  CI (PKG-04):  job "sync-no-anyio"
     uv sync --no-default-groups --extra duckdb   (anyio/trio excluded)
       ─► assert `import anyio` fails
       ─► pytest tests/ --ignore=tests/async   (sync suite green)
```

### Component Responsibilities

| File | Responsibility in Phase 26 | Change type |
|------|---------------------------|-------------|
| `pyproject.toml` `[project.optional-dependencies]` | Declare `async = ["anyio>=4.13"]`; add it to `all` | EDIT (additive) |
| `src/adbc_poolhouse/__init__.py` | PEP 562 guard | NO CHANGE — verify only (D-01) |
| `src/adbc_poolhouse/_async/_offload.py` | `offload()` signature: `Callable[..., _T]`+`*args: object` → TypeVarTuple `Callable[[Unpack[_Ts]], _T]`+`*args: Unpack[_Ts]` | EDIT (signature tighten) |
| `src/adbc_poolhouse/_async/_cancel.py` | `cancellable_offload()` same tighten, keeping leading `adbc_cancel` param | EDIT (signature tighten) |
| `.github/workflows/ci.yml` | Add a `sync-no-anyio` job alongside `quality` | EDIT (additive) |
| `tests/test_pkg_import_guard.py` (or similar) | NEW regression test for PKG-02/03 (subprocess + meta-path block) | NEW |

### Recommended Project Structure
```
src/adbc_poolhouse/
├── __init__.py            # PEP 562 guard (verify, don't touch)
└── _async/
    ├── _offload.py        # TypeVarTuple tighten (PKG-05)
    └── _cancel.py         # TypeVarTuple tighten (PKG-05)
tests/
├── test_pkg_import_guard.py   # NEW: PKG-02/03 regression (subprocess-isolated)
└── async/                     # MUST be deselected by the no-anyio CI job
.github/workflows/ci.yml       # NEW sync-no-anyio job
pyproject.toml                 # [async] extra (PKG-01)
```

### Pattern 1: TypeVarTuple offload forwarder (PKG-05)
**What:** Type the single dispatch chokepoint so the positional args forwarded to `fn` are checked against `fn`'s signature, while the helper's own keyword-only params (`limiter`, `on_dispatch`) stay outside the variadic. This is anyio's own `to_thread.run_sync` pattern.
**When to use:** Any generic "run this callable with these positional args" forwarder that also has its own keyword-only configuration params.
**Example (verified to type-check; see Code Examples for the full diff):**
```python
# Source: anyio 4.14.1 to_thread.run_sync signature (verified by source inspection)
from typing import TypeVar, TypeVarTuple, Unpack
from collections.abc import Callable

_T = TypeVar("_T")
_Ts = TypeVarTuple("_Ts")

async def offload(
    fn: Callable[[Unpack[_Ts]], _T],
    *args: Unpack[_Ts],
    limiter: CapacityLimiter,
    on_dispatch: Callable[[], None] | None = None,
) -> _T:
    async with limiter:
        if on_dispatch is not None:
            on_dispatch()
        inner_limiter = anyio.CapacityLimiter(math.inf)
        return await anyio.to_thread.run_sync(
            lambda: fn(*args), limiter=inner_limiter, abandon_on_cancel=False
        )
```

### Pattern 2: Subprocess-isolated import-guard regression (PKG-02/03)
**What:** Prove the anyio-absent paths without uninstalling anyio from the dev env, by running a child `python -c`/script in which a meta-path finder raises `ImportError` for any `anyio` import.
**When to use:** Testing a PEP 562 lazy-import / optional-dependency guard in a CI env where the dependency IS installed.
**Why subprocess (not just monkeypatch in-process):** `sys.modules` may already cache `anyio` / `adbc_poolhouse._async` from an earlier test in the same process; the import guard's `try: import _async` would then succeed against the cache and the negative path would never fire. A fresh subprocess guarantees a clean module table. (An in-process `monkeypatch` on `sys.meta_path` works too **only** if `anyio` and `adbc_poolhouse._async` have not yet been imported in that worker — fragile under pytest's shared process; prefer subprocess.)

### Pattern 3: No-anyio CI job (PKG-04)
**What:** A second CI job that installs only runtime deps + a sync backend (duckdb) + pytest, with the `dev` group (which carries anyio/trio) excluded, asserts anyio is genuinely absent, then runs the sync suite.
**Recipe (verified to exclude anyio via uv.lock analysis):**
```yaml
  sync-no-anyio:
    name: Sync suite without anyio
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
          cache-dependency-glob: "uv.lock"
          python-version: "3.11"
      # --no-default-groups drops the `dev` group (anyio + trio + aiotools);
      # --extra duckdb gives the in-proc sync backend. pytest is NOT a runtime
      # dep and NOT in this install, so supply it with --with at run time.
      - name: Sync runtime + sync backend (no anyio)
        run: uv sync --locked --no-default-groups --extra duckdb
      - name: Assert anyio is genuinely absent
        run: |
          uv run --no-default-groups --extra duckdb python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('anyio') is None else 'anyio present')"
      - name: Run sync suite (async dir deselected)
        run: uv run --no-default-groups --extra duckdb --with pytest --with pytest-adbc-replay pytest tests/ --ignore=tests/async
```
> Note: confirm the precise `uv run --with` spelling against the project's uv version during planning; an equivalent is a dedicated PEP 735 `[dependency-groups].sync-test = ["pytest", "pytest-adbc-replay"]` group installed with `--no-default-groups --group sync-test --extra duckdb`. Either keeps anyio out.

### Anti-Patterns to Avoid
- **Using `ParamSpec`/`Concatenate` for the offload helper.** It will not compile — the keyword-only `limiter` cannot follow `*args: P.args` [VERIFIED]. Use TypeVarTuple. (The requirement text's wording is corrected by this research; record as a decision.)
- **Aliasing the `anyio.to_thread.run_sync` chokepoint while editing `_offload.py`.** The `scan_async_package` source guard matches the literal `anyio.to_thread.run_sync` attribute chain; an aliased re-import slips the guard (RESEARCH Pitfall 5 from earlier phases). Keep the literal call site intact — the PKG-05 change is to the *signature*, not the call.
- **Running the no-anyio job against the whole `tests/` tree.** `tests/async/` modules import anyio at collection time and will `ImportError` before any test runs. Deselect with `--ignore=tests/async`.
- **Uninstalling anyio in the dev env to test the guard.** Breaks the rest of the suite and is non-hermetic. Use subprocess + meta-path block.
- **Pinning `anyio>=4.0.0`** (the original requirement / ROADMAP text). CONTEXT.md D-02 corrects this to `>=4.13` to match the `dev` floor.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Variadic-positional forwarding type | A custom by-arity `@overload` bank or a `Protocol` per call shape | `TypeVarTuple` + `Unpack` (one signature) | One generic covers all arities, matches anyio's own typing, zero maintenance when call shapes change |
| Detecting "anyio absent" in a test | Re-importing under a patched `__import__` | `importlib.abc.MetaPathFinder` raising `ImportError` for `anyio*`, in a subprocess | Clean, deterministic, and immune to `sys.modules` caching; the import system's documented extension point |
| Excluding anyio from a CI install | Hand-editing a requirements file or `pip uninstall anyio` post-install | `uv sync --no-default-groups --extra duckdb` | Declarative, locked, reproducible; anyio is already group-scoped so exclusion is a flag, not surgery |
| Mirroring the sync overloads on the async factory | New overload work | Already done in `_factory.py` (6 == 6, passes strict) | D-03 scopes PKG-05 to the offload surface, not the factory |

**Key insight:** Every "build" in this phase is really a "wire-up of an existing primitive" — the guard exists, the overloads exist, anyio is already group-scoped, and the offload chokepoint already centralizes dispatch. The variadic-generic and the CI flag are both off-the-shelf.

## Runtime State Inventory

> This is a packaging/typing phase, not a rename/refactor/migration. No stored data, live service config, OS-registered state, secrets, or build artifacts carry a renamed string. Included for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore keys/IDs change | none |
| Live service config | None — no external service config changes | none |
| OS-registered state | None | none |
| Secrets/env vars | None — no secret/env key renamed | none |
| Build artifacts | The `[async]` extra changes package metadata; `uv.lock` will be regenerated and the built wheel's `requires-dist` will gain `extra == 'async'`. | Run `uv lock` after editing `pyproject.toml`; commit the updated `uv.lock`. CI `--locked` will fail otherwise. |

**Nothing found in category:** Stored data, live service config, OS-registered state, secrets — verified by inspection of the phase scope (metadata + signatures + CI + tests only).

## Common Pitfalls

### Pitfall 1: ParamSpec for a helper that has its own keyword-only params
**What goes wrong:** Following the requirement text literally (`ParamSpec`/`Concatenate`) produces `error: Keyword parameter "limiter" cannot appear in signature after ParamSpec args parameter`.
**Why it happens:** PEP 612 / typing spec forbids keyword-only params between `*args: P.args` and `**kwargs: P.kwargs`; `offload` needs keyword-only `limiter`/`on_dispatch`.
**How to avoid:** Use TypeVarTuple. The keyword-only params sit outside the variadic and are unaffected.
**Warning signs:** basedpyright `reportGeneralTypeIssues` on the helper signature.

### Pitfall 2: `sys.modules` caching defeats an in-process guard test
**What goes wrong:** A monkeypatch-based "anyio absent" test passes in isolation but the negative branch never executes when another test already imported `anyio` or `adbc_poolhouse._async` in the same worker.
**Why it happens:** `import _async` inside `__getattr__` returns the cached module; the `except ImportError` never triggers.
**How to avoid:** Run the guard assertion in a fresh subprocess where a meta-path finder blocks anyio before any import.
**Warning signs:** Test green locally, but coverage shows the `except ImportError` line never hit.

### Pitfall 3: No-anyio job collects `tests/async/` and dies at import
**What goes wrong:** `pytest tests/` errors during collection with `ModuleNotFoundError: No module named 'anyio'` from a `tests/async/*` module.
**Why it happens:** Async test modules `import anyio` / use `@pytest.mark.anyio` at module scope.
**How to avoid:** `pytest tests/ --ignore=tests/async`. (Note: `tests/test_async_guard.py` is SAFE — its `anyio` mentions are string literals fed to the AST scanner, not real imports [VERIFIED].)
**Warning signs:** Collection error before any test executes.

### Pitfall 4: Editing `_offload.py` aliases the chokepoint
**What goes wrong:** Refactoring the import to `from anyio.to_thread import run_sync` to "clean up" the signature edit silently breaks the `scan_async_package` guard.
**Why it happens:** The guard matches the literal `anyio.to_thread.run_sync` attribute chain.
**How to avoid:** Change only the `def offload(...)` annotations; leave the call expression byte-for-byte. Re-run `tests/async/test_async_guard.py` (note: that test itself needs anyio, so run it in the normal `quality` job, not the no-anyio job).
**Warning signs:** `scan_async_package` returns a non-empty `to_thread-without-limiter` / banned list.

### Pitfall 5: Forgetting to relock after the extra
**What goes wrong:** CI `quality` job (`uv sync --locked`) fails because `pyproject.toml` and `uv.lock` disagree after adding the `[async]` extra.
**Why it happens:** `--locked` refuses to update the lockfile.
**How to avoid:** `uv lock` after editing `pyproject.toml`; commit `uv.lock`.
**Warning signs:** `error: The lockfile ... is out of date`.

## Code Examples

### PKG-05: tighten `offload()` (the exact edit)
```python
# src/adbc_poolhouse/_async/_offload.py  (signature only — call site UNCHANGED)
# Source: pattern mirrors anyio 4.14.1 to_thread.run_sync (verified by inspection)
from typing import TYPE_CHECKING, TypeVar, TypeVarTuple, Unpack

_T = TypeVar("_T")
_Ts = TypeVarTuple("_Ts")          # NEW

async def offload(
    fn: Callable[[Unpack[_Ts]], _T],   # was: Callable[..., _T]
    *args: Unpack[_Ts],                # was: *args: object
    limiter: CapacityLimiter,
    on_dispatch: Callable[[], None] | None = None,
) -> _T:
    async with limiter:
        if on_dispatch is not None:
            on_dispatch()
        inner_limiter = anyio.CapacityLimiter(math.inf)
        return await anyio.to_thread.run_sync(
            lambda: fn(*args), limiter=inner_limiter, abandon_on_cancel=False
        )
```
Verified behaviour against the real call sites [VERIFIED: basedpyright probe]:
- `offload(self._pool.connect, limiter=lim)` → returns the fairy type (0 args). OK.
- `offload(close_pool, self._pool, limiter=lim)` → 1 arg, type-checked. OK.
- `offload(self._cursor.execute, operation, parameters, limiter=lim)` → 2 args, type-checked. OK.
- NEW negative: passing a wrong-typed positional now errors (`fetchmany("x")` → `reportArgumentType`). This is the PKG-05 win.

### PKG-05: tighten `cancellable_offload()` (leading param + variadic)
```python
# src/adbc_poolhouse/_async/_cancel.py  (signature only)
_T = TypeVar("_T")
_Ts = TypeVarTuple("_Ts")

async def cancellable_offload(
    adbc_cancel: Callable[[], None],
    fn: Callable[[Unpack[_Ts]], _T],   # was: Callable[..., _T]
    *args: Unpack[_Ts],                # was: *args: object
    limiter: CapacityLimiter,
    on_abort: Callable[[], Awaitable[None]] | None = None,
) -> _T:
    ...
    result["v"] = await offload(fn, *args, limiter=limiter, on_dispatch=_mark_started)
    ...
```
The leading `adbc_cancel` param sits before `fn`; the `*args` after `fn` are the variadic, and the inner `offload(fn, *args, ...)` re-forwards them — both type-check [VERIFIED: basedpyright probe]. Note the `result: dict[str, _T]` shuttle and the `BaseExceptionGroup` unwrap are unaffected by the signature change.

### PKG-02/03: subprocess-isolated regression test
```python
# tests/test_pkg_import_guard.py  (anyio-free at module level; spawns a child)
from __future__ import annotations
import subprocess, sys, textwrap

_CHILD = textwrap.dedent(
    """
    import importlib.abc, sys
    class _Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name == "anyio" or name.startswith("anyio."):
                raise ImportError(f"No module named {name!r} (simulated absent)")
            return None
    sys.meta_path.insert(0, _Blocker())
    import adbc_poolhouse
    assert "create_pool" in dir(adbc_poolhouse)          # PKG-02: sync import OK
    try:
        adbc_poolhouse.create_async_pool                  # PKG-03: triggers guard
    except ImportError as e:
        assert "[async]" in str(e), str(e)
        print("GUARD_OK")
    else:
        raise AssertionError("expected ImportError")
    """
)

def test_import_guard_without_anyio() -> None:
    out = subprocess.run(
        [sys.executable, "-c", _CHILD], capture_output=True, text=True, check=True
    )
    assert "GUARD_OK" in out.stdout
```
Verified live: with anyio blocked, `import adbc_poolhouse` succeeds (`create_pool` present) and `create_async_pool` access raises `ImportError` containing `[async]` [VERIFIED: ran the meta-path-block probe].

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ParamSpec`/`Concatenate` for arg-forwarding helpers (requirement text) | `TypeVarTuple`/`Unpack` (PEP 646) for positional-variadic forwarders that have their own keyword-only params | PEP 646 accepted (3.11) | The correct mechanism for offload; matches anyio's own `run_sync` typing |
| Inline `*Ts` star syntax | `Unpack[Ts]` spelling | inline `*Ts` is 3.12+; project pins `pythonVersion = "3.11"` | Must use `Unpack[Ts]`, importable from `typing` on 3.11 [VERIFIED] |
| `requirements.txt` + `pip uninstall` for dependency scoping | `uv` dependency-groups + `--no-default-groups`/`--extra` | uv adoption | Declarative, locked exclusion of anyio |

**Deprecated/outdated:**
- `anyio>=4.0.0` floor (original PKG-01/ROADMAP text): superseded by `>=4.13` per D-02.
- `cancellable=` kwarg of `to_thread.run_sync`: deprecated since anyio 4.1.0 in favour of `abandon_on_cancel=` [VERIFIED: anyio source]. Codebase already uses `abandon_on_cancel=False` — no action.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `uv run --with pytest ...` is the right spelling to add pytest to the no-anyio job at run time | Pattern 3 / CI recipe | Low — a PEP 735 `sync-test` dependency-group is an equivalent fallback; planner should confirm the exact `uv run --with`/`--group` spelling against uv 0.9.18 during planning. CI is iterable. |

**All other claims in this research were VERIFIED (tool-confirmed) or CITED (typing spec).** The TypeVarTuple typing, the ParamSpec failure, the guard behaviour, the anyio dependency scoping, the basedpyright-strict 0-error baseline, and the anyio version are all empirically verified in this session.

## Open Questions

1. **Exact `uv` incantation to supply pytest to the no-anyio job**
   - What we know: `--no-default-groups --extra duckdb` excludes anyio; pytest is not a runtime dep and not pulled by anyio.
   - What's unclear: whether to add pytest via `uv run --with pytest` or a dedicated PEP 735 `sync-test` group.
   - Recommendation: Try `--with` first (least lockfile churn); fall back to a `sync-test` group if `--with` interacts awkwardly with `--locked`. Either is correct; CI is cheap to iterate.

2. **Should the no-anyio job also run `tests/test_async_guard.py`?**
   - What we know: that file is anyio-free at runtime (mentions are string literals), so it CAN run without anyio.
   - What's unclear: whether running it adds value in the no-anyio job (it's already in the `quality` job).
   - Recommendation: Leave it to the `quality` job; the no-anyio job's purpose is the sync suite + the `import anyio` failure assertion. Planner's discretion.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| anyio | `[async]` extra, PKG-05 typing check | ✓ | 4.14.1 | — |
| basedpyright | PKG-05 gate | ✓ | 1.39.5 | — |
| uv | PKG-01 relock, PKG-04 CI recipe | ✓ | 0.9.18 | — |
| duckdb | no-anyio sync backend | ✓ (extra) | >=0.9.1 | sqlite extra (also anyio-free) |
| pytest | regression + no-anyio tests | ✓ | >=8.0.0 | — |
| Python 3.11 | `pythonVersion` target for typing | dev env is 3.14; CI matrix includes 3.11 | 3.14 local / 3.11+3.14 CI | `Unpack` works on both [VERIFIED] |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none blocking.

## Validation Architecture

> nyquist_validation is enabled (`.planning/config.json`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=8.0.0` (anyio plugin used only for `tests/async/`, NOT for this phase's new tests) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest tests/test_pkg_import_guard.py -q` (new guard test) |
| Full suite command | `.venv/bin/pytest` (all) ; plus `.venv/bin/basedpyright src/adbc_poolhouse/_async/` for PKG-05 |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PKG-01 | `[async]` extra exists, pins `anyio>=4.13`, `[all]` includes it; lockfile resolves | unit (config assertion) + `uv lock --check` | `.venv/bin/pytest tests/test_pkg_extra.py -q` (assert `importlib.metadata.metadata('adbc-poolhouse')` provides extra `async`); `uv lock --locked` in CI | ❌ Wave 0 (test) |
| PKG-02 | `import adbc_poolhouse` succeeds with anyio absent | integration (subprocess + meta-path block) | `.venv/bin/pytest tests/test_pkg_import_guard.py::test_sync_import_without_anyio -q` | ❌ Wave 0 |
| PKG-03 | Async symbol access without anyio raises `ImportError` naming `[async]` | integration (subprocess + meta-path block) | `.venv/bin/pytest tests/test_pkg_import_guard.py::test_async_access_without_anyio_raises -q` | ❌ Wave 0 |
| PKG-04 | Sync suite passes with anyio uninstalled | CI job (environmental) | CI `sync-no-anyio` job: `uv sync --no-default-groups --extra duckdb` → assert no anyio → `pytest tests/ --ignore=tests/async` | ❌ Wave 0 (ci.yml) |
| PKG-05 | All async public API typed under basedpyright strict; offload args actually checked | static analysis + regression | `.venv/bin/basedpyright src/adbc_poolhouse/_async/` (expect `0 errors`); optional `reveal_type`/expect-error fixtures | ✅ tool exists; ❌ assertion harness Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/basedpyright src/adbc_poolhouse/_async/` (PKG-05) and `.venv/bin/pytest tests/test_pkg_import_guard.py -q` (PKG-02/03).
- **Per wave merge:** `.venv/bin/pytest` (full) + `.venv/bin/basedpyright` (full, `src` + `tests`).
- **Phase gate:** Full suite green under both the standard env AND the no-anyio job; `.venv/bin/mkdocs build --strict` (docs gate, see below); `uv lock --locked` clean.

### Wave 0 Gaps
- [ ] `tests/test_pkg_import_guard.py` — subprocess + meta-path block; covers PKG-02, PKG-03.
- [ ] `tests/test_pkg_extra.py` — asserts the `async` extra is declared and `[all]` includes it; covers PKG-01.
- [ ] `.github/workflows/ci.yml` — new `sync-no-anyio` job; covers PKG-04.
- [ ] (Optional) a basedpyright expect-error fixture proving a wrong-typed offload arg is now rejected — strengthens PKG-05 beyond "0 errors". Planner's discretion; the empirical probe in this research already demonstrates it.

*Existing infra covered:* `.venv/bin/basedpyright` (PKG-05 gate) and the sync test suite (PKG-04 target) already exist.

## Project Constraints (from CLAUDE.md)

- **Docs quality gate (phases >= 7):** This is Phase 26, so the gate applies even though the phase is packaging/typing. Plans MUST include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in `<execution_context>` [VERIFIED: skill file present at that path].
  - Any new public symbol needs Google-style docstrings (Args/Returns/Raises). *Note:* PKG-05 edits only existing `offload`/`cancellable_offload` signatures, whose docstrings already exist and need no behavioural change — but if the `*args` description changes wording, keep it Markdown (not RST) per project memory.
  - Consumer-facing behaviour change here: the `[async]` extra (PKG-01) is consumer-facing. Whether it must appear in a guide now or in Phase 28 (DOCS-03 lists the extra) is a planner call — DOCS-03 is the dedicated requirement, but a minimal mention (e.g. install instructions) may belong here. Treat the install-extra line as in-scope-discretionary.
  - `.venv/bin/mkdocs build --strict` must pass (use `.venv/bin/mkdocs` under sandbox per project memory, not `uv run mkdocs`).
  - Humanizer pass on any new/rewritten prose.
- **Docstring style (project memory):** Google-style; **Markdown** in docstrings, NOT RST (`` `create_pool` `` not `` :func:`create_pool` ``). `Example:` (singular) for admonition blocks.
- **Workflow gotchas (project memory):** STATE.md can be stale (trust git tags + pyproject + ROADMAP); prefer `.venv/bin/<tool>` over `uv run <tool>` under sandbox; run any concurrency/async test in a loop, not once (not directly relevant — this phase's new tests are sync/subprocess); zsh `!` in loop `if ! cmd` silently fakes green (use `rc=$?`); gsd-tools lacks some mutation handlers (edit STATE/ROADMAP/REQUIREMENTS by hand, commit via `query commit --files`).

## Sources

### Primary (HIGH confidence)
- anyio 4.14.1 source (`to_thread.py`, `from_thread.py`, `_core/_eventloop.py`) — `run_sync` typed with `TypeVarTuple PosArgsT` + `Unpack`; `abandon_on_cancel` replaces deprecated `cancellable` [VERIFIED: local source inspection]
- basedpyright 1.39.5 — empirical probes confirming TypeVarTuple type-checks the real offload call sites, catches wrong arg types, and that ParamSpec fails with `reportGeneralTypeIssues`; `_async/` baseline `0 errors` [VERIFIED: ran basedpyright]
- `uv.lock` — anyio/trio/aiotools are `dev`-group-only; runtime deps (`adbc-driver-manager`, `pydantic-settings`, `sqlalchemy`) pull no anyio [VERIFIED]
- `src/adbc_poolhouse/__init__.py`, `_async/_offload.py`, `_async/_cancel.py`, `_async/_cursor.py`, `_async/_factory.py`, `.github/workflows/ci.yml`, `pyproject.toml` — read in full [VERIFIED]
- Live guard probe — meta-path-blocked `import adbc_poolhouse` succeeds; `create_async_pool` access raises `ImportError` naming `[async]` [VERIFIED]

### Secondary (MEDIUM confidence)
- typing spec / PEP 612 / PEP 646 — "keyword-only parameters between `*args` and `**kwargs` is forbidden"; `Callable[[*Ts], R]` + `*args: *Ts` forwarding; inline `*Ts` is 3.12+ [CITED: https://typing.python.org/en/latest/spec/generics.html]

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version and the TypeVarTuple mechanism are tool-verified.
- Architecture: HIGH — guard, overloads, and dependency scoping all verified against the live repo.
- Pitfalls: HIGH — each pitfall was either reproduced (ParamSpec failure, anyio-block) or confirmed by source/lock inspection.
- PKG-05 typing recommendation: HIGH — empirically type-checked against the actual call sites, including the negative case.

**Research date:** 2026-06-28
**Valid until:** 2026-07-28 (stable — packaging/typing domain; anyio API and the typing spec are slow-moving)
