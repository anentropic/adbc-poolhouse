# Phase 15: Replace Syrupy snapshot tests with pytest-adbc-replay VCR-style record/replay tests - Research

**Researched:** 2026-03-02
**Domain:** pytest plugin, ADBC testing, VCR-style cassette record/replay
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Plugin to use:**
- `pytest-adbc-replay` — already published on PyPI, just add it as a test dependency
- Replace `syrupy>=4.0` in `[project.optional-dependencies].dev` with `pytest-adbc-replay`
- No need to build a custom plugin

**Backend scope for cassette tests:**
- **Snowflake**: migrate the two existing tests (`test_connection_health`, `test_arrow_round_trip`)
- **Databricks**: add new cassette tests (no existing Snowflake-style tests exist for Databricks yet)
- **PostgreSQL, MySQL, ClickHouse, others**: deferred — will use Docker-based real connections in a future phase

**CI behaviour:**
- Cassettes are checked into the repository
- Cassette-based tests run in CI by default (no credentials required for replay)
- Recording requires real credentials and `--adbc-record=once` flag — done locally by developer

**Syrupy removal:**
- Remove `syrupy>=4.0` from `pyproject.toml`
- Delete `SnowflakeArrowSnapshotSerializer` class from `tests/integration/conftest.py`
- Delete `snowflake_snapshot` fixture from `tests/integration/conftest.py`
- Remove all syrupy imports (`JSONSnapshotExtension`, `SnapshotAssertion`, syrupy types)
- Delete any `.ambr` snapshot files if they exist (none found currently)

### Claude's Discretion

- Cassette directory location (default `tests/cassettes` is fine)
- Exact `adbc_auto_patch` driver module names for Snowflake and Databricks
- Cassette naming convention for each test
- Whether to keep `@pytest.mark.snowflake` alongside `@pytest.mark.adbc_cassette` or replace it

### Deferred Ideas (OUT OF SCOPE)

- Docker-based integration tests for PostgreSQL, MySQL, ClickHouse, and other local backends — future phase
- Adding cassette tests for other cloud backends (BigQuery, Redshift, etc.) — if/when credentials are available
</user_constraints>

---

## Summary

`pytest-adbc-replay` (v1.0.0a1) is a pytest plugin published by the same author as adbc-poolhouse. It provides VCR-style cassette record/replay for ADBC database connections. Tests decorated with `@pytest.mark.adbc_cassette()` intercept calls to ADBC driver `connect()` functions, serialize query/result pairs to disk (`.sql` + `.arrow` + `.json` file triplets), and replay from those files in CI without live credentials.

The migration path is clear: remove Syrupy from `pyproject.toml` and `tests/integration/conftest.py`, add `pytest-adbc-replay` as a dev dependency, configure `adbc_auto_patch` in `[tool.pytest.ini_options]`, and rewrite the two existing Snowflake tests plus add new Databricks tests using the `@pytest.mark.adbc_cassette` marker. The existing session-scoped `snowflake_pool` fixture remains useful for recording (it creates a live pool when credentials are present).

The key architectural insight for this project: adbc-poolhouse's `_driver_api.py` always calls connections through `adbc_driver_manager.dbapi.connect()` regardless of backend. For Snowflake, the PyPI driver package (`adbc_driver_snowflake`) also exposes its own `adbc_driver_snowflake.dbapi.connect()` which is the conventional intercept target. For Databricks (Foundry), there is no driver-specific dbapi module — the generic `adbc_driver_manager.dbapi` is the only call site. This difference determines the correct `adbc_auto_patch` values per backend.

**Primary recommendation:** Use `adbc_driver_snowflake.dbapi` in `adbc_auto_patch` for Snowflake tests (matches the standard ADBC driver pattern confirmed in documentation) and `adbc_driver_manager.dbapi` for Databricks tests (confirmed by the CONTEXT.md author and by inspecting `_driver_api.py`). Both modules expose a `connect()` function that `adbc_auto_patch` can intercept.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pytest-adbc-replay` | `1.0.0a1` | Cassette record/replay for ADBC tests | Purpose-built for this project's exact use case; same author as adbc-poolhouse |
| `sqlglot` | `>=23.0` (transitive) | SQL normalization for cassette keys | Required by pytest-adbc-replay; handles dialect differences |
| `pyarrow` | `>=14.0` (transitive) | Arrow IPC serialization for cassette results | Required by pytest-adbc-replay; already in dev deps as `>=23.0.1` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `adbc-driver-manager` | `>=1.8.0` (already present) | Generic ADBC connect() intercept layer | Databricks cassette tests — Foundry drivers call through this module |
| `adbc-driver-snowflake` | `>=1.0.0` (via snowflake extra) | Snowflake-specific dbapi module | Snowflake cassette recording locally; not needed in CI for replay |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pytest-adbc-replay` | Keep Syrupy | Syrupy only snapshots final output; no SQL/params capture; does not replay transparently |
| `pytest-adbc-replay` | `pytest-recording` (VCR for HTTP) | Wrong protocol — VCR.py records HTTP, not ADBC |
| `pytest-adbc-replay` | Hand-roll monkeypatching | Significant complexity for same result; violates Don't Hand-Roll principle |

**Installation (to add to dev dependencies):**
```bash
uv add --dev pytest-adbc-replay
```

---

## Architecture Patterns

### Recommended Project Structure

```
tests/
├── cassettes/                     # NEW: committed cassette files
│   ├── snowflake_health/
│   │   └── adbc_driver_snowflake.dbapi/
│   │       ├── 000.sql            # normalized SQL
│   │       ├── 000.arrow          # Arrow IPC result
│   │       └── 000.json           # parameters
│   ├── snowflake_arrow_round_trip/
│   │   └── adbc_driver_snowflake.dbapi/
│   │       ├── 000.sql
│   │       ├── 000.arrow
│   │       └── 000.json
│   ├── databricks_health/
│   │   └── adbc_driver_manager.dbapi/
│   │       ├── 000.sql
│   │       ├── 000.arrow
│   │       └── 000.json
│   └── databricks_arrow_round_trip/
│       └── adbc_driver_manager.dbapi/
│           ├── 000.sql
│           ├── 000.arrow
│           └── 000.json
├── integration/
│   ├── conftest.py                # MODIFIED: remove Syrupy; keep snowflake_pool; add databricks_pool
│   ├── test_snowflake.py          # MODIFIED: rewrite using adbc_cassette marker
│   └── test_databricks.py         # NEW: Databricks cassette tests
└── conftest.py                    # unchanged
```

### Pattern 1: pyproject.toml Configuration

**What:** Add `pytest-adbc-replay` dev dep, configure `adbc_auto_patch` and replace the existing `addopts` / `markers` entries.

**When to use:** Phase setup — all tests in the session that touch the listed driver modules are interceptable.

**Example:**
```toml
# Source: https://pypi.org/project/pytest-adbc-replay/
[dependency-groups]
dev = [
    "adbc-poolhouse[duckdb]",
    "adbc-poolhouse[sqlite]",
    "basedpyright>=1.38.0",
    "coverage[toml]",
    "ipython>=9.10.0",
    "pdbpp>=0.12.0.post1",
    "pyarrow>=23.0.1",
    "pytest>=8.0.0",
    "pytest-cov>=6.0.0",
    "pytest-adbc-replay",         # replaces syrupy>=4.0
    "ruff>=0.15.1",
]

[tool.pytest.ini_options]
adbc_auto_patch = [
    "adbc_driver_snowflake.dbapi",
    "adbc_driver_manager.dbapi",
]
adbc_cassette_dir = "tests/cassettes"
markers = [
    "snowflake: requires real Snowflake credentials (recording only)",
    "databricks: requires real Databricks credentials (recording only)",
]
# Remove old addopts = "-m 'not snowflake'" — cassette tests now run without credentials
```

Note: The old `addopts = "-m 'not snowflake'"` gating is no longer needed. Cassette tests run in CI by default because the plugin replays from disk in `none` mode (the default).

### Pattern 2: Migrated Test Using adbc_cassette Marker

**What:** Replace snapshot assertions with `@pytest.mark.adbc_cassette` decoration. The test body stays mostly the same; the assertion changes.

**When to use:** All Snowflake and Databricks integration tests in this phase.

**Example (migrated Snowflake test):**
```python
# Source: https://anentropic.github.io/pytest-adbc-replay/reference/markers/
import pytest

@pytest.mark.adbc_cassette("snowflake_health")
def test_connection_health(snowflake_pool) -> None:
    """Pool path works: create_pool() + acquire + SELECT 1 + checkin."""
    conn = snowflake_pool.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == 1
    cur.close()
    conn.close()

@pytest.mark.adbc_cassette("snowflake_arrow_round_trip")
def test_arrow_round_trip(snowflake_pool) -> None:
    """Arrow schema + rows round-trip correctly; cassette enforces stable output."""
    conn = snowflake_pool.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table is not None
    assert table.num_rows == 1
```

Note: The `== snowflake_snapshot` assertion is gone. The cassette is the record of truth — if the query's result changes, the cassette would need re-recording (`--adbc-record=once`), making the change visible in the PR diff.

### Pattern 3: New Databricks Tests

**What:** Add Databricks cassette tests mirroring the Snowflake pattern, using a `databricks_pool` fixture that gates on `DATABRICKS_URI` or `DATABRICKS_HOST+HTTP_PATH+TOKEN`.

**When to use:** Adding Databricks coverage from scratch.

**Example:**
```python
# Source: CONTEXT.md design intent
import pytest

@pytest.mark.adbc_cassette("databricks_health")
def test_connection_health(databricks_pool) -> None:
    """Pool path works: DatabricksConfig + create_pool() + SELECT 1."""
    conn = databricks_pool.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == 1
    cur.close()
    conn.close()

@pytest.mark.adbc_cassette("databricks_arrow_round_trip")
def test_arrow_round_trip(databricks_pool) -> None:
    """Arrow round-trip via Databricks; cassette enforces stable schema."""
    conn = databricks_pool.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table is not None
    assert table.num_rows == 1
```

### Pattern 4: Session-scoped Pool Fixtures for Recording

**What:** Keep the session-scoped pool fixture pattern from the existing conftest, gated on a required env var. During recording, the fixture creates a live pool. During CI replay, the cassette intercepts at the dbapi level so the pool's connect() call is never reached — but the fixture must still be structured to not crash when credentials are absent.

**When to use:** Both Snowflake (migrated) and Databricks (new) need a pool fixture.

**Example:**
```python
# Source: adapted from existing tests/integration/conftest.py
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from adbc_poolhouse import DatabricksConfig, SnowflakeConfig, create_pool


@pytest.fixture(scope="session")
def snowflake_pool():
    """Session-scoped Snowflake pool. Skips if SNOWFLAKE_ACCOUNT is absent (for recording)."""
    dotenv_path = Path(__file__).parent.parent.parent / ".env.snowflake"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    if not os.environ.get("SNOWFLAKE_ACCOUNT"):
        pytest.skip("SNOWFLAKE_ACCOUNT not set — skipping live Snowflake; use cassette replay")

    config = SnowflakeConfig()  # type: ignore[call-arg]
    pool = create_pool(config)
    yield pool
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def databricks_pool():
    """Session-scoped Databricks pool. Skips if credentials absent (for recording)."""
    dotenv_path = Path(__file__).parent.parent.parent / ".env.databricks"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    has_uri = bool(os.environ.get("DATABRICKS_URI"))
    has_decomposed = all(
        os.environ.get(k) for k in ["DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"]
    )
    if not has_uri and not has_decomposed:
        pytest.skip("Databricks credentials not set — skipping live Databricks; use cassette replay")

    config = DatabricksConfig()  # type: ignore[call-arg]
    pool = create_pool(config)
    yield pool
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]
```

**Critical question on fixture skip vs cassette replay:** When credentials are absent in CI, the `pytest.skip()` in the fixture would skip cassette tests too — cassettes would never be exercised. The fix is to restructure tests so the fixture is not required in replay mode. Two approaches:

1. **adbc_auto_patch approach (recommended):** Don't use the pool fixture at all. Use `adbc_auto_patch` to intercept the raw dbapi `connect()` call and create connections directly inside the test. The plugin's `none` mode provides a fake connection from the cassette. This is the canonical pytest-adbc-replay pattern.

2. **adbc_replay.wrap() approach:** Use the `adbc_replay` fixture explicitly, wrapping a connection at a lower level. More complex but still possible.

The CONTEXT.md says "the pool fixture can be kept (still useful for recording)" — this suggests the pool fixture strategy should **conditionally skip only for live connections** while cassette replay tests should not require the fixture at all. This is a design choice that needs to be settled in the plan.

### Anti-Patterns to Avoid

- **Using `pytest.skip()` on credential absence in a fixture that cassette tests depend on:** This blocks cassette replay in CI because the fixture is requested by the test function. Cassette tests should either use `adbc_auto_patch` (so no fixture is needed) or have a separate fixture path that does not skip.
- **Not adding cassette files to `.gitignore` negation:** The `.gitignore` does not currently ignore `tests/cassettes/` — this is correct; cassettes MUST be committed.
- **Setting `adbc_record_mode = once` in `pyproject.toml`:** This would re-record existing cassettes when credentials are present. Only pass `--adbc-record=once` on the CLI when intentionally updating cassettes.
- **Keeping `addopts = "-m 'not snowflake'"` after migration:** Once cassette tests run without credentials, this gate is unnecessary and would exclude cassette tests from CI.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cassette serialization | Custom Arrow + SQL serializer (like `SnowflakeArrowSnapshotSerializer`) | `pytest-adbc-replay` cassette format | Plugin handles SQL normalization, Arrow IPC, sequential numbering, and replay matching |
| Non-deterministic field stripping | Manual metadata key removal before snapshot comparison | Plugin handles replay from stored Arrow IPC | Arrow IPC captures exactly what was returned; replay uses the stored result, not a live query |
| CI gating on credentials | `addopts = "-m 'not snowflake'"` env-var gate | Default `none` record mode | In `none` mode, cassette tests run and pass without credentials; no CLI flag needed |
| Cassette directory management | Custom pytest plugin or conftest hooks | `adbc_cassette_dir` ini option | Plugin creates and manages the directory structure automatically |

**Key insight:** The `SnowflakeArrowSnapshotSerializer` class exists precisely to work around Syrupy's limitations with Arrow data and non-deterministic metadata. `pytest-adbc-replay` was designed for exactly this problem — it does not need any such workaround.

---

## Common Pitfalls

### Pitfall 1: Pool Fixture Skipping Blocks Cassette Replay

**What goes wrong:** The `snowflake_pool` fixture has `pytest.skip("SNOWFLAKE_ACCOUNT not set")`. If a cassette test requests this fixture, the test is skipped in CI even though the cassette should make credentials unnecessary.

**Why it happens:** The plugin intercepts at the dbapi `connect()` level, but the pool fixture runs before the test body. If the fixture skips, the test never runs — the plugin's cassette replay is never reached.

**How to avoid:** Design cassette tests so they do not depend on the pool fixture when replaying. Options:
  - Use raw dbapi connections inside the test (plugin intercepts these directly)
  - Keep two separate fixture variants: one for live recording (credentials required) and one for cassette replay (no skip, relies on plugin intercept)
  - Alternatively: check if cassette exists in the fixture and skip the skip (more complex)

**Warning signs:** Tests show as `SKIPPED` in CI rather than `PASSED`.

### Pitfall 2: adbc_auto_patch Module Name is Wrong for Foundry Backends

**What goes wrong:** Using `adbc_driver_databricks.dbapi` (which does not exist as a PyPI package) instead of `adbc_driver_manager.dbapi` for Databricks tests.

**Why it happens:** The Foundry Databricks driver has no Python package named `adbc_driver_databricks` — its connect() is always called through `adbc_driver_manager.dbapi.connect()`. The plugin monkeypatches the module listed in `adbc_auto_patch`, so the wrong module name results in no interception.

**How to avoid:** Use `adbc_driver_manager.dbapi` for all Foundry-based backends. Confirmed by examining `_driver_api.py` which always calls `adbc_driver_manager.dbapi.connect()`.

**Warning signs:** Tests fail with a real connection error in CI (e.g., `ImportError: ADBC driver 'databricks' not found`) instead of replaying from cassette.

### Pitfall 3: `.env.databricks` Not in .gitignore

**What goes wrong:** A developer accidentally commits Databricks credentials.

**Why it happens:** The `.gitignore` already excludes `.env.snowflake` explicitly. The new `.env.databricks` file needs the same treatment.

**How to avoid:** Add `.env.databricks` / `*.env.databricks` to `.gitignore` during this phase.

**Warning signs:** `detect-secrets` pre-commit hook fires on CI.

### Pitfall 4: Cassette Tests Not Running in CI (Old addopts Gate)

**What goes wrong:** The existing `addopts = "-m 'not snowflake'"` in `pyproject.toml` excludes tests marked `snowflake` from default runs. If migrated tests keep the `@pytest.mark.snowflake` marker, they are still excluded in CI.

**Why it happens:** The `addopts` gate was designed for the Syrupy approach where live credentials were required. With cassette replay, the gate is no longer needed.

**How to avoid:** Remove `addopts = "-m 'not snowflake'"` entirely, or change it to exclude only tests that truly require live credentials (not cassette tests).

**Warning signs:** Cassette test files are never run in `uv run pytest` output (zero collected).

### Pitfall 5: Arrow Binary Cassettes are Large

**What goes wrong:** Arrow IPC files committed to git for complex queries can be large. For simple tests like `SELECT 1` the files are tiny, but the team should be aware.

**Why it happens:** Arrow IPC includes full schema metadata. For `SELECT 1 AS n, 'hello' AS s` the result is tiny, but production-style queries with wide schemas can produce notable binary blobs.

**How to avoid:** The tests in this phase use trivial queries (`SELECT 1`, `SELECT 1 AS n, 'hello' AS s`) — file sizes will be minimal. Document the size constraint in the test design (CONTEXT.md already notes this).

**Warning signs:** `git add tests/cassettes/` produces unexpectedly large commits.

---

## Code Examples

Verified patterns from official sources:

### pyproject.toml Configuration

```toml
# Source: https://pypi.org/project/pytest-adbc-replay/ + https://anentropic.github.io/pytest-adbc-replay/reference/configuration/
[tool.pytest.ini_options]
adbc_auto_patch = [
    "adbc_driver_snowflake.dbapi",
    "adbc_driver_manager.dbapi",
]
adbc_cassette_dir = "tests/cassettes"
markers = [
    "snowflake: requires live Snowflake credentials (recording only; cassettes checked in for CI replay)",
    "databricks: requires live Databricks credentials (recording only; cassettes checked in for CI replay)",
]
```

### Marker API

```python
# Source: https://anentropic.github.io/pytest-adbc-replay/reference/markers/
# name parameter sets cassette directory name under adbc_cassette_dir
@pytest.mark.adbc_cassette("my_cassette_name")
def test_example():
    ...

# With per-test dialect override (optional)
@pytest.mark.adbc_cassette("my_cassette_name", dialect="snowflake")
def test_example():
    ...
```

### Recording vs Replay Workflow

```bash
# Record (requires live credentials):
pytest --adbc-record=once tests/integration/test_snowflake.py

# Replay (default — no credentials needed):
uv run pytest
```

### Cassette Directory Structure

```
# Source: https://anentropic.github.io/pytest-adbc-replay/reference/cassette-format/
tests/cassettes/{cassette_name}/{driver_module}/
├── 000.sql      # First query, normalized SQL
├── 000.arrow    # First result, Arrow IPC binary
└── 000.json     # First query parameters (null if none)
```

### Sensitive Value Scrubbing

```toml
# Source: https://anentropic.github.io/pytest-adbc-replay/reference/configuration/
[tool.pytest.ini_options]
adbc_scrub_keys = ["token", "password", "uri"]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Syrupy snapshot (`== snowflake_snapshot`) | `@pytest.mark.adbc_cassette` + cassette replay | Phase 15 | Tests run in CI without credentials; SQL changes visible as text diffs |
| `SnowflakeArrowSnapshotSerializer` hand-rolled serializer | Built-in Arrow IPC cassette format | Phase 15 | No custom code to maintain; Arrow schema fully preserved |
| `addopts = "-m 'not snowflake'"` CI gate | Cassette replay in `none` mode (default) | Phase 15 | Cassette tests run automatically in CI with no special flags |
| Only Snowflake coverage | Snowflake + Databricks cassette coverage | Phase 15 | Databricks integration is now test-visible |

**Deprecated/outdated:**
- `syrupy>=4.0`: remove from dev deps; no longer needed
- `SnowflakeArrowSnapshotSerializer`: delete class entirely; plugin handles serialization
- `snowflake_snapshot` fixture: delete; no longer needed
- `addopts = "-m 'not snowflake'"`: remove; cassette tests do not require credentials

---

## Open Questions

1. **Pool fixture skip vs cassette replay — how to reconcile**
   - What we know: `snowflake_pool` has `pytest.skip()` when `SNOWFLAKE_ACCOUNT` is absent; cassette tests should not skip in CI.
   - What's unclear: The canonical pytest-adbc-replay pattern uses `adbc_auto_patch` with raw dbapi connections in tests, bypassing the pool fixture. But adbc-poolhouse's tests test the pool itself.
   - Recommendation: For cassette tests, open a connection through `create_pool()` as usual. The plugin intercepts the underlying `adbc_driver_snowflake.dbapi.connect()` that the pool calls internally. The fixture skip must be restructured: only skip when the cassette is also absent (recording mode); replay mode should not require credentials. The simplest fix is to make the fixture NOT skip when credentials are absent — instead let it `yield None` — and have the test check for `None` pool and mark as expected failure if in recording mode. Alternatively, mark the test with `@pytest.mark.skipif(not cassette_exists, ...)`. The planner should decide the exact pattern.

2. **`adbc_driver_manager.dbapi` intercept for Databricks — verified or inferred?**
   - What we know: `adbc_driver_manager.dbapi.connect()` exists (verified by `dir()` inspection); `_driver_api.py` always calls through this module; the CONTEXT.md states this is the intercept layer.
   - What's unclear: Whether pytest-adbc-replay's `adbc_auto_patch` mechanism successfully intercepts `adbc_driver_manager.dbapi.connect()` specifically (no official docs example shows this exact module name for Foundry backends).
   - Recommendation: HIGH confidence this works — the plugin monkeypatches any module's `connect()` function; `adbc_driver_manager.dbapi` has `connect` as a public attribute. Verified indirectly by the plugin source design (architecture supports any module name). Flag as a recording-phase validation point: record a Databricks cassette and confirm the `.arrow` file is created in the `adbc_driver_manager.dbapi/` subdirectory.

3. **Keep or remove `@pytest.mark.snowflake` alongside `@pytest.mark.adbc_cassette`?**
   - What we know: The old marker was used to gate tests from running without credentials; with cassette replay this gate is no longer needed.
   - What's unclear: Whether keeping `@pytest.mark.snowflake` provides useful semantic grouping (e.g., for `pytest -m snowflake --adbc-record=once` workflows).
   - Recommendation: Keep the marker for its semantic value (lets developers run `pytest -m snowflake --adbc-record=once` to re-record), but remove it from the `addopts` exclusion. Apply both markers: `@pytest.mark.snowflake` AND `@pytest.mark.adbc_cassette(...)`.

---

## Documentation Requirements

Phase 15 touches test infrastructure, not the public library API. The documentation requirements are therefore minimal:

- **No new public symbols** — no new classes or functions in `src/adbc_poolhouse/`
- **No API reference changes** — `mkdocstrings` output is unchanged
- **`uv run mkdocs build --strict`** — must pass (no docs source changes expected)
- **Potential guide update:** The `snowflake.md` guide may benefit from a note about how integration tests work (cassette-based, credentials not required for CI). This is at Claude's discretion.

The docs-author skill (`@.claude/skills/adbc-poolhouse-docs-author/SKILL.md`) must be included per `CLAUDE.md` requirements for phases >= 7, but the humanizer pass and docstring work applies only if any prose or docstrings are modified.

---

## Sources

### Primary (HIGH confidence)

- `https://pypi.org/project/pytest-adbc-replay/` — version 1.0.0a1, Python >=3.11, dependencies (adbc-driver-manager >=1.0.0, pyarrow >=14.0, sqlglot >=23.0, pytest >=8.0)
- `https://anentropic.github.io/pytest-adbc-replay/reference/configuration/` — all ini keys and CLI flags with types and defaults
- `https://anentropic.github.io/pytest-adbc-replay/reference/markers/` — `@pytest.mark.adbc_cassette` API: `name` parameter and `dialect` override
- `https://anentropic.github.io/pytest-adbc-replay/reference/fixtures/` — `adbc_connect`, `adbc_replay`, `adbc_scrubber`, `adbc_param_serialisers` fixture signatures
- `https://anentropic.github.io/pytest-adbc-replay/reference/cassette-format/` — `.sql`/`.arrow`/`.json` triplet format, sequential numbering, directory structure
- `https://anentropic.github.io/pytest-adbc-replay/how-to/multiple-drivers/` — `adbc_auto_patch` multi-driver configuration, per-driver dialect
- `https://anentropic.github.io/pytest-adbc-replay/how-to/ci-without-credentials/` — CI integration pattern, `none` mode as default
- `https://github.com/anentropic/pytest-adbc-replay` — repository structure, README content
- Codebase inspection: `adbc_driver_manager.dbapi.connect` confirmed present via `dir()` call on live environment
- Codebase inspection: `_driver_api.py` confirms Foundry backends always call `adbc_driver_manager.dbapi.connect()`
- Codebase inspection: `_drivers.py` confirms Snowflake uses `adbc_driver_snowflake` package name

### Secondary (MEDIUM confidence)

- `https://github.com/anentropic/pytest-adbc-replay/blob/main/src/pytest_adbc_replay/plugin.py` — plugin architecture: monkeypatch of any module's `connect()`; `adbc_driver_manager.dbapi` support is inferred from design (no explicit docs example)
- `https://arrow.apache.org/adbc/current/python/api/adbc_driver_snowflake.html` — Snowflake driver has `dbapi` submodule with `connect()`

### Tertiary (LOW confidence)

- None. All critical claims verified with primary sources.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — package on PyPI, documentation fetched directly, version confirmed
- Architecture patterns: HIGH — configuration keys, marker API, cassette format all from official docs
- Pitfalls: MEDIUM — pool fixture skip issue is inferred from plugin design + existing code patterns; Foundry intercept module name is MEDIUM (inferred, not explicitly documented)

**Research date:** 2026-03-02
**Valid until:** 2026-06-02 (plugin is alpha; check for breaking changes before planning if more than 3 months pass)
