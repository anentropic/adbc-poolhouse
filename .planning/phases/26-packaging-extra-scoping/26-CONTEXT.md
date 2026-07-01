# Phase 26: Packaging & Extra Scoping - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning
**Source:** /gsd-discuss-phase 26 --assumptions (assumptions-mode discussion)

<domain>
## Phase Boundary

Ship the async surface behind an `[async]` optional-dependency extra at **zero cost
to sync users**, and bring all async public API under basedpyright-strict typing.

The headline finding from the assumptions discussion: **most of the import-guard
machinery already shipped in Phases 24–25.** `src/adbc_poolhouse/__init__.py` already
contains the PEP 562 `__getattr__` lazy-import, the `TYPE_CHECKING` async
re-declarations, and the `ImportError` that names the `[async]` extra. basedpyright
strict already passes the `_async` package at **0 errors**. So Phase 26 is narrower
and more mechanical than the roadmap line implies — it is *packaging metadata + a CI
guard job + regression tests that prove the already-built guard + a typing-tightening
pass*, not a from-scratch build of the guard.

**In scope:** the `[async]` extra (PKG-01), the no-anyio CI guard job (PKG-04),
regression tests locking in the existing import guard (PKG-02/03), a typing-tightening
pass on the async/offload surface (PKG-05).

**Out of scope:** the dual-backend asyncio/trio test matrix (Phase 27); async usage
docs (Phase 28). Do not build new async runtime behaviour here — the module structure
is frozen as of Phase 25.
</domain>

<decisions>
## Implementation Decisions

### PKG-02/03 — Import guard: verify, do not rebuild
- **D-01**: The PEP 562 lazy import guard is already implemented in
  `src/adbc_poolhouse/__init__.py` (Phase 24/25). Phase 26 **adds regression tests**
  that prove it — (a) `import adbc_poolhouse` succeeds with anyio absent, and (b)
  accessing an async symbol without anyio raises an `ImportError` whose message names
  the `[async]` extra. Phase 26 does **not** rewrite the `__getattr__` machinery.

### PKG-01 — The `[async]` extra
- **D-02**: The `[async]` optional-dependency extra pins **`anyio>=4.13`** (NOT the
  `>=4.0.0` the requirement text originally read). `>=4.13` matches the existing `dev`
  dependency-group floor and currently resolves to anyio **4.14.1** (latest). The extra
  adds anyio and nothing else; `[all]` gains `adbc-poolhouse[async]`. REQUIREMENTS.md
  PKG-01 is corrected to `>=4.13` as part of this phase's context.

### PKG-05 — Tighten async typing
- **D-03**: Tighten the async typing surface so argument types are actually checked at
  the offload boundary. Today `offload()` in `src/adbc_poolhouse/_async/_offload.py`
  uses the loose `Callable[..., _T]` + `*args: object`, which passes strict only because
  it accepts anything. The **exact mechanism** (`ParamSpec`/`Concatenate` per the
  requirement, vs. an alternative that fits a generic dispatch chokepoint) is an open
  question for the **researcher** to resolve — `offload` forwards heterogeneous
  bound-method args, so a naive `ParamSpec` may fight the checker. Goal: real
  argument-type checking while keeping basedpyright strict at 0 errors. The factory
  overloads already hand-mirror the 6 sync overloads (6 == 6) and pass strict, so the
  focus is the offload/wrapper forwarding surface, not the factory.

### PKG-04 — No-anyio CI guard job
- **D-04**: Add a dedicated CI job that installs the package **without** anyio (a
  deliberately minimal install — package + a sync test backend such as duckdb, and
  none of the dev/test dependency groups that pull anyio + trio) and runs the existing
  sync test suite to green. The current single `quality` job always has anyio (it is in
  the `dev` group), so proving the zero-cost-sync claim requires a separate job. The
  crux of this requirement is the minimal-install recipe, not the test run itself.

### Claude's Discretion
- Number and grouping of PLAN.md files; wave assignment.
- Exact pytest file/test names for the import-guard regression tests.
- Exact CI job name and `uv` install incantation for the no-anyio job, provided it
  genuinely excludes anyio.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Already-built import guard (PKG-02/03 — verify, don't rebuild)
- `src/adbc_poolhouse/__init__.py` — PEP 562 `__getattr__`, `_LAZY_ASYNC_NAMES`,
  `TYPE_CHECKING` async re-declarations, and the `ImportError` naming `[async]`.
- `src/adbc_poolhouse/_async/__init__.py` — the lazily-imported async entry points.

### Typing target (PKG-05)
- `src/adbc_poolhouse/_async/_offload.py` — the single offload chokepoint;
  `Callable[..., _T]` + `*args: object` is the loose signature to tighten.
- `src/adbc_poolhouse/_async/_factory.py` — hand-mirrored async overloads (reference
  for "mirror the sync overloads").
- `pyproject.toml` `[tool.basedpyright]` — `typeCheckingMode = "strict"`,
  `pythonVersion = "3.11"`.

### Packaging (PKG-01)
- `pyproject.toml` `[project.optional-dependencies]` — existing extras pattern
  (`duckdb`, `snowflake`, …, `all`) to follow; `[dependency-groups].dev` already pins
  `anyio>=4.13`.

### CI (PKG-04)
- `.github/workflows/ci.yml` — current `quality` matrix job; the no-anyio guard job
  slots alongside it.

### Requirements
- `.planning/REQUIREMENTS.md` — PKG-01 … PKG-05.
</canonical_refs>

<specifics>
## Specific Ideas

- anyio floor `>=4.13`, resolving to 4.14.1 (verified installed + latest on PyPI).
- The no-anyio CI job must avoid `uv sync --dev` (the dev group bundles anyio + trio);
  install only the package plus a sync backend extra (e.g. `--extra duckdb`).
- basedpyright strict currently reports `0 errors, 0 warnings, 0 notes` on `_async/` —
  PKG-05 is tightening, not error-fixing; a regression must not be introduced.
</specifics>

<deferred>
## Deferred Ideas

- Dual-backend asyncio/trio parametrized test matrix → Phase 27.
- Async usage guide / API reference docs → Phase 28.
</deferred>

---

*Phase: 26-packaging-extra-scoping*
*Context gathered: 2026-06-28 via /gsd-discuss-phase 26 --assumptions*
