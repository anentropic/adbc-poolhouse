# Phase 26: Packaging & Extra Scoping - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 6 (5 edits + 1 new; 1 optional new test)
**Analogs found:** 5 / 6 (one new test has no in-repo subprocess/meta-path analog — RESEARCH supplies it)

> This phase is mechanical: metadata + CI + typing-tightening + regression tests.
> Almost every change has a precise in-repo analog. The one genuinely new pattern
> (subprocess-isolated import-guard test) has no codebase precedent; RESEARCH.md
> Code Examples supplies a verified, ready-to-copy implementation.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` `[project.optional-dependencies]` | config (packaging) | transform (metadata) | existing `duckdb`/`all` extras in the same table | exact (self-analog) |
| `src/adbc_poolhouse/_async/_offload.py` | utility (dispatch chokepoint) | transform (variadic forward) | anyio 4.14.1 `to_thread.run_sync` + this file's own current signature | exact |
| `src/adbc_poolhouse/_async/_cancel.py` | utility (cancellation wrapper) | event-driven (task group) | `_offload.py` (same TypeVarTuple edit) + this file's own current signature | exact |
| `.github/workflows/ci.yml` `sync-no-anyio` job | config (CI) | request-response (job steps) | the existing `quality` job in the same file | exact (sibling job) |
| `tests/test_pkg_import_guard.py` (NEW) | test | event-driven (subprocess) | `tests/test_async_guard.py` (sync, anyio-free test conventions) for structure; RESEARCH for subprocess body | role-match (structure) / no-analog (subprocess mechanism) |
| `tests/test_pkg_extra.py` (NEW, optional) | test | transform (metadata assertion) | `tests/test_driver_imports.py` header + `importlib.metadata` usage | role-match |

---

## Pattern Assignments

### `pyproject.toml` — `[async]` extra (PKG-01) — `config`, transform

**Analog:** the existing extras table in the same file (self-analog; the strongest possible pattern).

**Current state** (`pyproject.toml` lines 16-32) — extra rows are single-element lists; `all` aggregates the package's own extras via `adbc-poolhouse[<name>]` self-references:
```toml
[project.optional-dependencies]
duckdb = ["duckdb>=0.9.1"]
snowflake = ["adbc-driver-snowflake>=1.0.0"]
postgresql = ["adbc-driver-postgresql>=1.0.0"]
quack = ["adbc-driver-quack>=0.1.0a1"]
flightsql = ["adbc-driver-flightsql>=1.0.0"]
bigquery = ["adbc-driver-bigquery>=1.3.0"]
sqlite = ["adbc-driver-sqlite>=1.0.0"]
all = [
    "adbc-poolhouse[duckdb]",
    "adbc-poolhouse[snowflake]",
    "adbc-poolhouse[postgresql]",
    "adbc-poolhouse[quack]",
    "adbc-poolhouse[flightsql]",
    "adbc-poolhouse[bigquery]",
    "adbc-poolhouse[sqlite]",
]
```

**Edit (additive, follows the row + `all`-aggregation pattern exactly):**
- Add one row `async = ["anyio>=4.13"]` after `sqlite` (line 23).
- Add `"adbc-poolhouse[async]",` as the last element of `all` (after line 31).

**Pin rationale (CONTEXT D-02):** `>=4.13` (NOT `>=4.0.0`) to match the `dev` group floor at line 56 (`"anyio>=4.13"`); resolves to 4.14.1.

**MANDATORY follow-up (RESEARCH Pitfall 5 + Runtime State Inventory):** run `uv lock` after the edit and commit `uv.lock`, or the existing `quality` job's `uv sync --locked` (line 34) fails with "lockfile out of date".

---

### `src/adbc_poolhouse/_async/_offload.py` — TypeVarTuple tighten (PKG-05) — `utility`, transform

**Analog:** anyio 4.14.1 `to_thread.run_sync` signature (`func: Callable[[Unpack[PosArgsT]], T_Retval], *args: Unpack[PosArgsT]`) — the canonical variadic-forwarder pattern. Verified in RESEARCH.

**Current imports + typevars** (`_offload.py` lines 24-37):
```python
from __future__ import annotations

import math
from typing import TYPE_CHECKING, TypeVar

import anyio
import anyio.to_thread

if TYPE_CHECKING:
    from collections.abc import Callable

    from anyio import CapacityLimiter

_T = TypeVar("_T")
```

**Current loose signature** (`_offload.py` lines 40-45) — the exact lines to tighten:
```python
async def offload(
    fn: Callable[..., _T],
    *args: object,
    limiter: CapacityLimiter,
    on_dispatch: Callable[[], None] | None = None,
) -> _T:
```

**Edit (signature only — RESEARCH Code Examples, verified to type-check):**
- Import additions on line 27: `from typing import TYPE_CHECKING, TypeVar, TypeVarTuple, Unpack`
- Add typevar after line 37: `_Ts = TypeVarTuple("_Ts")`
- `fn: Callable[..., _T]` → `fn: Callable[[Unpack[_Ts]], _T]`
- `*args: object` → `*args: Unpack[_Ts]`

**Body — DO NOT TOUCH** (`_offload.py` lines 100-108). The literal `anyio.to_thread.run_sync(lambda: fn(*args), limiter=..., abandon_on_cancel=False)` chokepoint must stay byte-for-byte:
```python
    async with limiter:
        if on_dispatch is not None:
            on_dispatch()
        inner_limiter = anyio.CapacityLimiter(math.inf)
        return await anyio.to_thread.run_sync(
            lambda: fn(*args),
            limiter=inner_limiter,
            abandon_on_cancel=False,
        )
```
**Why (RESEARCH Pitfall 4 / Anti-Patterns):** the `scan_async_package` guard matches the literal `anyio.to_thread.run_sync` attribute chain. Aliasing or rewording the call slips the guard. Change annotations only.

**Docstring note (CONTEXT / CLAUDE.md docs gate):** the existing `*args` / `Args` block (lines 63-90) stays; if you reword the `*args` description, keep it **Markdown** (backticks, not RST `:role:`) per project memory.

---

### `src/adbc_poolhouse/_async/_cancel.py` — TypeVarTuple tighten (PKG-05) — `utility`, event-driven

**Analog:** `_offload.py` (the sibling edit above) — same `TypeVarTuple`/`Unpack` mechanism, with one extra leading positional param (`adbc_cancel`) preserved before `fn`.

**Current imports + typevar** (`_cancel.py` lines 23-37):
```python
from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import anyio
from anyio import get_cancelled_exc_class

from adbc_poolhouse._async._offload import offload

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from anyio import CapacityLimiter

_T = TypeVar("_T")
```

**Current loose signature** (`_cancel.py` lines 40-46):
```python
async def cancellable_offload(
    adbc_cancel: Callable[[], None],
    fn: Callable[..., _T],
    *args: object,
    limiter: CapacityLimiter,
    on_abort: Callable[[], Awaitable[None]] | None = None,
) -> _T:
```

**Edit (signature only — RESEARCH Code Examples, verified):**
- Line 25: `from typing import TYPE_CHECKING, TypeVar, TypeVarTuple, Unpack`
- Add after line 37: `_Ts = TypeVarTuple("_Ts")`
- `adbc_cancel: Callable[[], None]` — **leave the leading param unchanged** (it precedes `fn`, outside the variadic).
- `fn: Callable[..., _T]` → `fn: Callable[[Unpack[_Ts]], _T]`
- `*args: object` → `*args: Unpack[_Ts]`

**Body — DO NOT TOUCH.** The inner re-forward already type-checks under the new signature (`_cancel.py` lines 185-192):
```python
    async def _worker() -> None:
        try:
            result["v"] = await offload(
                fn,
                *args,
                limiter=limiter,
                on_dispatch=_mark_started,
            )  # abandon_on_cancel=False
        finally:
            done.set()  # release the watcher on the success/error path
```
The `result: dict[str, _T]` shuttle (line 154) and the `BaseExceptionGroup` unwrap (lines 200-219) are unaffected by the signature change [RESEARCH-verified].

---

### `.github/workflows/ci.yml` — `sync-no-anyio` job (PKG-04) — `config`, request-response

**Analog:** the existing `quality` job in the same file (sibling job — the strongest analog).

**Existing `quality` job** (`ci.yml` lines 13-47) — copy its checkout + setup-uv shape, then diverge on the sync/test steps:
```yaml
  quality:
    name: Quality gates
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      matrix:
        python-version: ["3.11", "3.14"]
      fail-fast: false
    steps:
      - name: Checkout
        uses: actions/checkout@v6
      - name: Set up uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
          cache-dependency-glob: "uv.lock"
          python-version: ${{ matrix.python-version }}
      - name: Sync dependencies
        run: uv sync --locked --dev --extra duckdb        # <-- the WITH-anyio install
      - name: Install prek
        run: uv tool install prek
      - name: Run quality gates
        run: prek run --all-files
      - name: Tests
        run: uv run pytest
      - name: Cache pruning
        if: always()
        run: uv cache prune --ci
```

**Key divergence (RESEARCH Pattern 3 / Architecture):** the new job replaces `quality`'s line-34 install (`--dev --extra duckdb`, which pulls anyio) with a **no-dev** install, adds an explicit "anyio is absent" assertion, and deselects `tests/async`:
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
      - name: Sync runtime + sync backend (no anyio)
        run: uv sync --locked --no-default-groups --extra duckdb
      - name: Assert anyio is genuinely absent
        run: uv run --no-default-groups --extra duckdb python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('anyio') is None else 'anyio present')"
      - name: Run sync suite (async dir deselected)
        run: uv run --no-default-groups --extra duckdb --with pytest --with pytest-adbc-replay pytest tests/ --ignore=tests/async
```
**Notes for the planner:**
- `--no-default-groups` drops the `dev` group (the *only* place anyio/trio/aiotools live — RESEARCH-verified via uv.lock). Equivalent: `--no-dev`.
- pytest + pytest-adbc-replay are NOT runtime deps and NOT in the no-dev install → supply via `uv run --with` (RESEARCH Open Question 1: confirm `--with` spelling against uv 0.9.18; fallback is a PEP 735 `[dependency-groups].sync-test` group).
- `--ignore=tests/async` is mandatory: those modules import anyio at collection time (RESEARCH Pitfall 3). Note `tests/test_async_guard.py` (top-level) is SAFE to collect — its anyio mentions are string literals fed to the AST scanner.
- Keep `quality`'s `--locked` so the relocked `uv.lock` is enforced here too.

---

### `tests/test_pkg_import_guard.py` (NEW) — PKG-02/03 regression — `test`, event-driven (subprocess)

**Structure analog:** `tests/test_async_guard.py` — the convention for an anyio-free, plain-sync test module (no `@pytest.mark.anyio`), module docstring + `from __future__ import annotations`. See its header (lines 1-15) and the top-level sync test functions for the house style.

**Subprocess/meta-path mechanism — NO in-repo analog.** Grep across `tests/` found zero uses of `subprocess`, `sys.meta_path`, `MetaPathFinder`, or `sys.modules` manipulation. This pattern is genuinely new to the codebase. Copy it from **RESEARCH.md Code Examples → "PKG-02/03: subprocess-isolated regression test"** (verified live in the research session):
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
**Why subprocess, not in-process monkeypatch (RESEARCH Pitfall 2):** `sys.modules` may already cache `anyio` / `adbc_poolhouse._async` from an earlier test in the worker; the guard's `try: import _async` would hit the cache and the negative path never fires. A fresh child guarantees a clean module table.

**Target symbol — ground truth** (`src/adbc_poolhouse/__init__.py`):
- The guarded names (line 70): `_LAZY_ASYNC_NAMES = frozenset({"create_async_pool", "managed_async_pool", "close_async_pool"})`.
- The exact ImportError the test asserts against (lines 92-95): the message contains the literal `adbc-poolhouse[async]`, so `assert "[async]" in str(e)` holds:
```python
            raise ImportError(
                f"{name!r} requires the optional async dependencies. "
                "Install them with: pip install adbc-poolhouse[async]"
            ) from exc
```
**Planner discretion (CONTEXT):** exact file/test names. RESEARCH's Test Map suggests splitting into `test_sync_import_without_anyio` (PKG-02) and `test_async_access_without_anyio_raises` (PKG-03) — two functions sharing the meta-path-block child.

---

### `tests/test_pkg_extra.py` (NEW, optional — PKG-01 assertion) — `test`, transform

**Analog:** `tests/test_driver_imports.py` header (lines 1-19) for module-docstring + `import importlib.util` convention; the same `importlib.metadata` family is the assertion tool.

**Pattern:** assert the `async` extra is declared and `[all]` includes it via package metadata, e.g.:
```python
from __future__ import annotations
import importlib.metadata

def test_async_extra_is_declared() -> None:
    meta = importlib.metadata.metadata("adbc-poolhouse")
    assert "async" in (meta.get_all("Provides-Extra") or [])
```
**Planner discretion:** RESEARCH Test Map lists this as a Wave-0 gap for PKG-01; the `uv lock --locked` CI check already covers lockfile coherence, so this test is a belt-and-suspenders metadata assertion. Whether to add it is the planner's call.

---

## Shared Patterns

### Guard literal-chokepoint discipline (applies to BOTH `_offload.py` and `_cancel.py`)
**Source:** `src/adbc_poolhouse/_async/_offload.py` lines 100-108 (the one `anyio.to_thread.run_sync` call) + `tests/test_async_guard.py::TestRealAsyncPackage` (lines 162-185).
**Apply to:** Every PKG-05 edit.
**Rule:** change only `def` annotations; never alias, reword, or move the `anyio.to_thread.run_sync` attribute chain. Re-run `tests/test_async_guard.py` (in the WITH-anyio `quality` env, not the no-anyio job) after editing to confirm `scan_async_package` stays clean.

### TypeVarTuple variadic forwarder (applies to BOTH offload signatures)
**Source:** anyio 4.14.1 `to_thread.run_sync` + RESEARCH Pattern 1.
**Apply to:** `offload` and `cancellable_offload`.
**Excerpt (3.11-compatible spelling — `Unpack[_Ts]`, NOT inline `*_Ts` which is 3.12+):**
```python
from typing import TypeVar, TypeVarTuple, Unpack
_T = TypeVar("_T")
_Ts = TypeVarTuple("_Ts")
#   fn: Callable[[Unpack[_Ts]], _T], *args: Unpack[_Ts]   keyword-only params stay OUTSIDE the variadic
```
**Anti-pattern (RESEARCH Pitfall 1):** do NOT use `ParamSpec`/`Concatenate` (the original requirement wording) — the keyword-only `limiter` cannot follow `*args: P.args`; basedpyright errors with `reportGeneralTypeIssues`.

### anyio-free / no-dev install discipline (applies to CI job + both new tests)
**Source:** RESEARCH (uv.lock analysis) + `pyproject.toml` dependency-groups (lines 44-67).
**Apply to:** the `sync-no-anyio` CI job and both new test modules.
**Rule:** anyio/trio/aiotools live ONLY in the `dev` group. Keep new test modules anyio-free at import time (subprocess for the guard, `importlib.metadata` for the extra) so they collect in the no-anyio job. Deselect `tests/async` in that job.

### Per-task verification commands (CLAUDE.md / project memory: prefer `.venv/bin/<tool>` under sandbox)
- PKG-05 gate: `.venv/bin/basedpyright src/adbc_poolhouse/_async/` (expect `0 errors, 0 warnings, 0 notes`).
- PKG-02/03 gate: `.venv/bin/pytest tests/test_pkg_import_guard.py -q`.
- Guard regression: `.venv/bin/pytest tests/test_async_guard.py -q`.
- Docs gate (phase >= 7): `.venv/bin/mkdocs build --strict`; include `@.claude/skills/adbc-poolhouse-docs-author/SKILL.md` in plan `<execution_context>`.
- Relock: `uv lock` then commit `uv.lock` (CI `--locked` fails otherwise).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/test_pkg_import_guard.py` (subprocess + meta-path mechanism) | test | event-driven | No existing test in `tests/` uses `subprocess`, `sys.meta_path`, `MetaPathFinder`, or `sys.modules` manipulation. The module *structure* mirrors `tests/test_async_guard.py`, but the anyio-block mechanism is new — copy from RESEARCH.md Code Examples (verified live). |

---

## Metadata

**Analog search scope:** `pyproject.toml`, `src/adbc_poolhouse/__init__.py`, `src/adbc_poolhouse/_async/{_offload,_cancel}.py`, `.github/workflows/ci.yml`, `tests/` (full listing + grep for subprocess/meta-path), `tests/test_async_guard.py`, `tests/test_driver_imports.py`.
**Files scanned:** 7 read in full/targeted + `tests/` directory grep.
**Pattern extraction date:** 2026-06-28
