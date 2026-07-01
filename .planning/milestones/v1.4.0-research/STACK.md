# Stack Research: adbc-poolhouse v1.4.0 Async API

**Research Date:** 2026-06-25
**Research Type:** Subsequent Milestone — Optional async API layer over the existing sync ADBC pool
**Milestone:** v1.4.0 — Async API
**Confidence:** HIGH

---

## Scope Note

This file covers ONLY the additions/changes the new async layer needs. The existing validated
stack (Pydantic BaseSettings; SQLAlchemy `sqlalchemy.pool` / `sqlalchemy.event`; ADBC Driver
Manager + per-backend drivers; mkdocs-material + mkdocstrings; uv; ruff; basedpyright strict; prek)
is settled and unchanged and is **not re-researched here**. Prior-milestone driver/CLI stack
research lives in git history.

The async layer adds exactly **one runtime dependency** (`anyio`) behind an `[async]` extra, plus
test wiring that reuses the existing pytest stack. No greenlet, no `sqlalchemy[asyncio]`, no native
async ADBC driver.

---

## Confidence Key

- HIGH — confirmed from multiple current sources (PyPI JSON API + official docs)
- MEDIUM — confirmed from one authoritative source
- LOW — single web-search source, unverified

---

## Recommended Stack

### Core Technologies (new for v1.4.0)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `anyio` | `>=4.0.0` (current stable **4.14.1**) | Async runtime-abstraction layer. Provides `anyio.to_thread.run_sync()` to offload blocking sync ADBC calls to a worker thread; `CapacityLimiter` to bound concurrent thread checkouts; cancellation scopes (`CancelScope` / `fail_after` / `move_on_after`) to wire `adbc_cancel` to cooperative cancellation; `anyio.Path` if async filesystem access is ever needed. | ADBC releases the GIL in its C calls, so thread-offload yields *real* concurrency with no native async driver. anyio is the only widely-used library that is **backend-neutral** (asyncio *and* trio) — required for the project's trio+asyncio neutrality posture. `to_thread.run_sync` already integrates a shared `CapacityLimiter` and propagates cancellation, so the cooperative-cancellation plumbing comes for free. Single small pure-Python dep. |

That is the **entire** new runtime dependency surface.

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `typing-extensions` | (transitive `>=4.5`) | Back-compat typing primitives. | **Do NOT add as a direct dep.** anyio already pulls it transitively on Python `< 3.13`. On our 3.11 floor `ParamSpec`, `Self`, `Coroutine`, `Awaitable` are all in stdlib `typing` / `collections.abc`. Add a direct dep only if our own code imports a genuinely 3.12+-only symbol (none identified). |
| `exceptiongroup` | — | PEP 654 `ExceptionGroup` / `except*` backport. | **Do NOT add.** anyio task groups raise native `ExceptionGroup` on 3.11+. anyio only declares the backport for `python_version < "3.11"`; our floor is 3.11, so it is never installed and `except*` is native. |
| `trio` | `>=0.32.0` (current **0.33.0**) | Trio event loop. | **Test-only, optional.** Pull via `anyio[trio]` in the dev group only if the suite is parametrized across asyncio + trio. Never a runtime dependency. |

### Development Tools (new test wiring)

| Tool | Purpose | Notes |
|------|---------|-------|
| anyio's **built-in pytest plugin** | Runs `@pytest.mark.anyio` (or auto-mode) coroutine tests; supplies the `anyio_backend` fixture. | **Bundled with anyio — no extra install.** Do **not** add `pytest-asyncio` (asyncio-only; conflicts with anyio's plugin in auto mode). Enable via marker mode (recommended) or `anyio_mode = "auto"` in `[tool.pytest.ini_options]`. |
| `anyio_backend` fixture | Parametrizes async tests across backends. | Defaults to asyncio only. To also cover trio, override in `conftest.py` (snippet below). Recommend default = asyncio for the cassette-replay suite, with an opt-in trio param over a thin smoke subset to prove backend-neutrality. |
| existing `pytest` (**9.1.1**, pinned `>=8.0.0`) + `pytest-adbc-replay` (`>=1.0.0a3`) | Cassette record/replay, reused unchanged. | The replay machinery patches the **sync** ADBC dbapi modules (`adbc_auto_patch`). Because the async wrapper calls the *same* sync methods via `to_thread.run_sync`, existing cassettes replay correctly when the async wrapper is driven from an `@pytest.mark.anyio` test — no new cassette format. |

---

## Installation

```bash
# Add the async runtime dep as an optional extra (uv edits pyproject + lockfile)
uv add --optional async "anyio>=4.0.0"

# Add trio to the dev group ONLY if parametrizing tests across backends
uv add --group dev "anyio[trio]>=4.0.0"   # or: uv add --group dev "trio>=0.32.0"
```

### pyproject.toml wiring

Add to `[project.optional-dependencies]` alongside the per-backend extras:

```toml
[project.optional-dependencies]
async = ["anyio>=4.0.0"]
# ... existing duckdb / snowflake / postgresql / quack / flightsql / bigquery / sqlite ...
all = [
    # ... existing backend extras ...
    "adbc-poolhouse[async]",   # recommended: include async in `all`
]
```

The existing `dev` group already depends on `adbc-poolhouse[all]`, so once `async` is listed in
`all`, anyio is automatically available to the test suite. Add `anyio[trio]` to `dev` separately
**only** if running the trio-parametrized smoke subset:

```toml
[dependency-groups]
dev = [
    "adbc-poolhouse[all]",     # brings anyio once `async` is in `all`
    "anyio[trio]>=4.0.0",      # add ONLY for trio-parametrized tests
    # ... existing dev deps unchanged ...
]
```

### Test plugin config

Marker mode (recommended — explicit, no clash risk). Mark async tests with `@pytest.mark.anyio`;
no `anyio_mode` line needed.

Optional `conftest.py` to parametrize across backends (opt-in trio coverage):

```python
import pytest

@pytest.fixture(
    params=[
        pytest.param("asyncio", id="asyncio"),
        pytest.param("trio", id="trio"),   # requires anyio[trio] in dev group
    ]
)
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return request.param
```

Omit the fixture entirely to run asyncio-only (anyio's default).

---

## Integration Points

- **Offload primitive:** every async wrapper method (`connect`, `execute`, `executemany`,
  `fetch*`, `fetch_arrow_table`, pool create/close) calls the corresponding sync ADBC/QueuePool
  method inside `anyio.to_thread.run_sync(...)`. The sync code path is untouched.
- **Checkout bounding:** use an anyio `CapacityLimiter` (passed to `to_thread.run_sync(..., limiter=...)`)
  rather than tuning the worker thread pool directly, so the limit is honoured identically under
  asyncio and trio. This is the trio-safe analogue of the "anyio-native checkout limiter" option in
  PROJECT.md's open design decision.
- **Cancellation:** wrap offloaded calls in an `anyio.CancelScope` (or `fail_after`/`move_on_after`)
  and, on cancellation, call the connection's `adbc_cancel()` so the in-flight C call is interrupted
  cooperatively. `to_thread.run_sync(cancellable=...)` controls whether the awaiting task detaches.
- **Genericity:** the async layer wraps the existing `WarehouseConfig`-driven sync pool, so one async
  implementation covers all 13 backends with no per-backend code.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `anyio.to_thread.run_sync` | `asyncio.to_thread` / `loop.run_in_executor` | Only if the project drops trio-neutrality and commits to asyncio-only. These lack a built-in `CapacityLimiter` and cancellation integration and lock out trio users. Not recommended. |
| anyio built-in pytest plugin | `pytest-asyncio` | Only for an asyncio-exclusive codebase that never touches anyio. Conflicts with anyio's plugin and cannot drive trio. Avoid. |
| Sync driver + thread-offload | Native async ADBC driver | No native async ADBC/dbapi driver exists. Revisit only if one ships upstream — but feasibility is explicitly thread-offload. |
| Plain sync `QueuePool` + anyio-offloaded checkout | `sqlalchemy.AsyncAdaptedQueuePool` via `create_async_engine` | Never for this project — see "What NOT to Add". |

---

## What NOT to Add — Decision Table

| Candidate | Verdict | Rationale |
|-----------|---------|-----------|
| `sqlalchemy[asyncio]` / `AsyncAdaptedQueuePool` / `create_async_engine` | **DO NOT ADD** | `AsyncAdaptedQueuePool` is asyncio-bound and assumes a **natively-async DBAPI** (asyncpg/aiomysql/aiosqlite-style). ADBC has **no** async DBAPI, so it cannot satisfy the pool's await points. SQLAlchemy docs state plain `QueuePool` is "not compatible with asyncio and `create_async_engine()`". It does **not** replace the thread-offload, and adopting it drags in greenlet and pins us to asyncio, breaking trio-neutrality. It remains a *reference*, not a foundation. |
| `greenlet` (direct/runtime dep) | **DO NOT ADD** | Only relevant as SQLAlchemy's sync↔async shim, which we are not using. asyncio-oriented, adds hidden scheduling, unnecessary for thread-offload. (May still arrive transitively via base SQLAlchemy on some platforms; we never `import greenlet` and never declare it.) |
| `pytest-asyncio` | **DO NOT ADD** | asyncio-only; conflicts with anyio's bundled pytest plugin in auto mode. Use anyio's plugin (`@pytest.mark.anyio` + `anyio_backend`). |
| `exceptiongroup` backport | **DO NOT ADD** | Native `ExceptionGroup` / `except*` exist on Python ≥3.11 (our floor). Backport only installs on `<3.11`. |
| Direct `typing-extensions` dep | **DO NOT ADD** | Redundant on Python ≥3.11 (`ParamSpec`, `Self`, `Coroutine`, `Awaitable` are stdlib); arrives transitively via anyio anyway. |
| Native async ADBC driver | **DOES NOT EXIST** | Async is achieved by offloading the sync driver to threads. |
| Upper version caps (e.g. `anyio<5`) | **DO NOT ADD** | Project policy is open lower bounds only; caps cause downstream dep-resolution conflicts for the two known consumers (dbt-open-sl, Semantic ORM). Use `anyio>=4.0.0`. |

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `anyio 4.14.1` | Python `>=3.10` | Project floor 3.11 → fully covered. On 3.11/3.12 anyio pulls `typing_extensions>=4.5` transitively; on ≥3.13 it does not. |
| `anyio 4.x` | `exceptiongroup` only on `python_version < "3.11"` | 3.11 floor → backport never installed; native `ExceptionGroup` used. |
| `anyio[trio]` 4.14.1 | `trio>=0.32.0` (current 0.33.0) | Test-only extra; never a runtime dep. |
| `anyio` | `sqlalchemy 2.x` `QueuePool` | Orthogonal — anyio offloads sync `QueuePool` calls to threads. No version constraint between them. |
| anyio pytest plugin | `pytest 8/9.x` (project `>=8.0.0`, current 9.1.1) | Bundled with anyio; works with current pytest. Must NOT coexist with `pytest-asyncio` auto mode. |
| `basedpyright 1.38+` strict | anyio typing on 3.11 | anyio ships `py.typed` and is fully typed; wrappers typed with stdlib `ParamSpec` / `Self` / `Coroutine[Any, Any, T]` — no extra typing dep for strict mode. |

---

## Lower-Bound Choice

**`anyio>=4.0.0`** (current stable 4.14.1). Rationale:

- anyio 4.0 is the release that adopted native PEP 654 `ExceptionGroup` and the modern
  `to_thread.run_sync` / `CapacityLimiter` / cancellation-scope API used here.
- An open `>=4.0.0` lower bound matches the project's "open lower bounds, no upper caps" policy and
  maximises consumer compatibility while guaranteeing the APIs we rely on.
- No reason to pin higher (e.g. `>=4.14`); nothing we use was added after 4.0.

---

## Open Questions / Gaps

- **Checkout-wait strategy** (PROJECT.md open design decision): plain sync `QueuePool` with an
  anyio-offloaded checkout-and-execute vs. an anyio-native `CapacityLimiter` in front of the pool.
  Stack-wise both need only `anyio` — no extra dependency either way. This is an architecture
  decision, resolved in ARCHITECTURE research, not a stack addition.
- **`cancellable=` semantics for `to_thread.run_sync`**: whether to detach the awaiting task on
  cancellation (the thread keeps running until `adbc_cancel` lands) vs. block. Behavioural detail for
  the cancellation design; no dependency impact.

---

## Sources

- PyPI JSON API (`pypi.org/pypi/<pkg>/json`) — verified current versions and anyio 4.14.1 dependency
  markers: anyio 4.14.1 (`requires-python >=3.10`; `exceptiongroup; python_version<"3.11"`,
  `typing_extensions>=4.5; python_version<"3.13"`, `trio>=0.32.0; extra=="trio"`), exceptiongroup
  1.3.1, typing-extensions 4.15.0, pytest 9.1.1, greenlet 3.5.2, trio 0.33.0. **HIGH**
- [AnyIO Testing docs](https://anyio.readthedocs.io/en/stable/testing.html) — built-in pytest plugin,
  `@pytest.mark.anyio`, `anyio_mode = "auto"`, `anyio_backend` parametrization, explicit conflict
  warning vs pytest-asyncio. **HIGH**
- [AnyIO Tasks docs](https://anyio.readthedocs.io/en/stable/tasks.html) +
  [Migration 3→4](https://anyio.readthedocs.io/en/stable/migration.html) — task groups raise native
  PEP 654 `ExceptionGroup`; backport only needed `<3.11`. **HIGH**
- [SQLAlchemy 2.0 asyncio docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) +
  [Connection Pooling docs](https://docs.sqlalchemy.org/en/20/core/pooling.html) —
  `AsyncAdaptedQueuePool` requires a natively-async DBAPI and uses greenlet; plain `QueuePool` is
  "not compatible with asyncio"; confirms thread-offload remains required and
  greenlet/sqlalchemy[asyncio] should be avoided. **HIGH**

---
*Research by Claude Code — 2026-06-25*
*Sources: PyPI JSON API, anyio.readthedocs.io, docs.sqlalchemy.org*
