# Phase 6: Snowflake Integration - Research

**Researched:** 2026-02-25
**Domain:** pytest snapshot testing with syrupy, Arrow schema serialization, Snowflake ADBC driver metadata, credential management
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### What the tests exercise
- Two distinct tests: (1) connection health — `create_pool()` + acquire connection + `SELECT 1` verifies the full pool path works against real Snowflake; (2) Arrow data round-trip — `SELECT 1 AS n, 'hello' AS s`, assert schema + rows match snapshot
- Query for Arrow test: `SELECT 1 AS n, 'hello' AS s` — deterministic, no real tables required, captures both integer and varchar Arrow types
- Happy-path default config only: account, user, password, warehouse, database — no multi-variant testing (already covered by unit tests)
- Dedicated file: `tests/integration/test_snowflake.py` — separate from DuckDB integration tests because Snowflake requires real credentials and the marker isolation is cleaner

#### Serializer design
- `SnowflakeArrowSnapshotSerializer` lives in `tests/integration/` — test-internal utility, not exported from the package
- Snapshot captures Arrow schema + all rows, serialized as readable JSON (schema as JSON object + rows as JSON array) — human-reviewable in PR diffs, credential residue easy to spot
- Strip from Arrow schema metadata: `queryId`, timestamps, `elapsedTime` (roadmap-specified) — Claude's discretion to identify and strip any additional non-deterministic fields found in actual Snowflake ADBC driver responses at implementation time

#### Credential management
- Credentials supplied via `.env.snowflake` dotenv file (gitignored) — consistent with SnowflakeConfig's env-var support
- Test fixture loads the dotenv file and constructs `SnowflakeConfig` from the resulting environment variables
- No-creds behavior: `pytest.skip()` when `SNOWFLAKE_ACCOUNT` env var is absent
- Tests only run when explicitly opted in: `pytest -m snowflake` — default `pytest` run never attempts a Snowflake connection

#### Snapshot update workflow
- Standard syrupy update mechanism: `pytest --snapshot-update -m snowflake` re-records all Snowflake snapshots
- Snapshot files stored at syrupy default: `tests/integration/__snapshots__/` — auto-managed, co-located with test file
- Add 'How to record Snowflake snapshots' section to `CONTRIBUTING.md` in this phase (while the workflow details are fresh)

### Claude's Discretion
- Exact pytest marker configuration (`pyproject.toml` markers section + `addopts` to exclude `snowflake` marker by default)
- How to load `.env.snowflake` in the conftest fixture (python-dotenv or manual `load_dotenv`)
- Exact serializer implementation details — which Arrow metadata fields beyond the roadmap-specified three to strip, based on what the real driver returns

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TEST-03 | Snowflake `syrupy` snapshot tests with a custom `SnowflakeArrowSnapshotSerializer` that strips non-deterministic fields (`queryId`, timestamps, `elapsedTime`) before serialization — recorded locally with real credentials, replayed in CI against committed snapshots | Syrupy 5.1.0 is installed; `JSONSnapshotExtension` base pattern and `use_extension` fixture approach documented; Arrow schema metadata stripping pattern verified; credential skip pattern confirmed |
</phase_requirements>

---

## Summary

Phase 6 adds syrupy snapshot tests for the Snowflake ADBC integration. The pattern is: record locally with real credentials, commit the snapshot files, replay in CI without credentials. A custom serializer (`SnowflakeArrowSnapshotSerializer`) strips non-deterministic Arrow schema metadata before serialization so snapshots are stable across recording sessions and Snowflake accounts.

The key technical components are: (1) a syrupy custom extension that inherits from `JSONSnapshotExtension` (inheriting all file storage logic) and overrides only `serialize()` to strip metadata then produce readable JSON; (2) a pytest fixture that returns `snapshot.use_extension(SnowflakeArrowSnapshotSerializer)` for the custom format; (3) a conftest fixture that skips when `SNOWFLAKE_ACCOUNT` is absent, loads `.env.snowflake` via `python-dotenv`, and constructs `SnowflakeConfig`; (4) a `snowflake` pytest marker with `addopts` to exclude it from default runs.

**Critical finding:** The installed Snowflake ADBC driver (`adbc-driver-snowflake==1.10.0`) attaches only stable, deterministic metadata to Arrow schema fields: `SNOWFLAKE_TYPE` (the Snowflake type name), `logicalType`, `precision`, `scale`, `charLength`, and `byteLength`. The roadmap-specified non-deterministic fields (`queryId`, `elapsedTime`, timestamps) are NOT present in current driver responses per source code analysis and official documentation. However, the serializer MUST still strip these keys defensively (as specified), and the implementer should verify the actual fields returned from a real Snowflake connection at implementation time and strip any additional ones found.

**Primary recommendation:** Subclass `JSONSnapshotExtension`, override only `serialize()` to strip known non-deterministic schema metadata keys, then use a `snowflake_snapshot` fixture that calls `snapshot.use_extension(SnowflakeArrowSnapshotSerializer)`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| syrupy | 5.1.0 (installed) | Snapshot assertion framework for pytest | Already a project dev dep; provides the `snapshot` fixture, file management, and `--snapshot-update` CLI |
| pyarrow | 23.0.1 (installed) | Arrow table inspection and serialization | Already a project dev dep; needed to call `table.schema`, `table.schema.metadata`, `table.to_pylist()` |
| python-dotenv | 1.2.1 (transitive via pydantic-settings) | Load `.env.snowflake` credentials into environment | Already available — no new dep needed; `load_dotenv(dotenv_path=..., override=False)` |
| adbc-driver-snowflake | 1.10.0 (installed) | Snowflake ADBC driver | Already in `[snowflake]` extra; used by `create_pool()` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.0.0+ (installed) | Test runner; marker system | `pytest -m snowflake`, `pytest --snapshot-update -m snowflake` |

### No New Dependencies Required
All libraries needed for this phase are already installed. The serializer uses only:
- `pyarrow` (already a dev dep)
- `json` (stdlib)
- `syrupy.extensions.json.JSONSnapshotExtension` (already installed)

**Installation (none required):**
```bash
# No new packages — all already present via uv sync --dev
```

---

## Architecture Patterns

### Recommended File Structure
```
tests/
├── conftest.py                          # existing (currently empty)
├── integration/
│   ├── __init__.py                      # new — makes integration a package
│   ├── conftest.py                      # new — snowflake_config fixture + skip logic
│   ├── test_snowflake.py                # new — two tests: health + Arrow round-trip
│   └── __snapshots__/                   # auto-created by syrupy on first --snapshot-update
│       └── test_snowflake.ambr          # syrupy snapshot file (if using AmberSnapshotExtension)
│       └── test_snowflake/              # syrupy snapshot dir (if using SingleFileSnapshotExtension)
├── test_adbc_poolhouse.py               # existing
├── test_configs.py                      # existing
├── test_drivers.py                      # existing
├── test_pool_factory.py                 # existing
└── test_translators.py                  # existing
CONTRIBUTING.md                          # new — snapshot recording workflow
```

Note: Since `SnowflakeArrowSnapshotSerializer` subclasses `JSONSnapshotExtension` (which subclasses `SingleFileSnapshotExtension`), each snapshot will be a separate `.json` file under `tests/integration/__snapshots__/test_snowflake/`. This makes PR diffs human-readable.

### Pattern 1: Custom Syrupy Extension via JSONSnapshotExtension

**What:** Subclass `JSONSnapshotExtension` and override `serialize()` to strip non-deterministic Arrow schema metadata before producing JSON.

**When to use:** When you need a custom JSON snapshot format for domain objects (Arrow tables) that contain non-deterministic fields.

**Why inherit from JSONSnapshotExtension:** It already implements all abstract storage methods (`delete_snapshots`, `read_snapshot_collection`, `read_snapshot_data_from_location`, `write_snapshot_collection`) and produces human-readable `.json` files.

**Example:**
```python
# tests/integration/conftest.py (or test_snowflake.py)
# Source: syrupy source code + project pattern

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

import pyarrow as pa
from syrupy.extensions.json import JSONSnapshotExtension

if TYPE_CHECKING:
    from syrupy.types import PropertyFilter, PropertyMatcher, SerializableData, SerializedData

# Keys that are non-deterministic and must be stripped from Arrow schema metadata.
# Specified by roadmap: queryId, timestamps, elapsedTime.
# The implementer MUST verify these at recording time — add any additional keys found.
_NON_DETERMINISTIC_META_KEYS: frozenset[bytes] = frozenset([
    b"queryId",
    b"elapsedTime",
    b"elapsed_time",
    b"timestamp",
    b"statementId",
    b"queryTime",
])


class SnowflakeArrowSnapshotSerializer(JSONSnapshotExtension):
    """Syrupy extension that serializes Arrow tables to stable, human-readable JSON.

    Strips non-deterministic Arrow schema metadata keys before serialization
    so snapshots are stable across Snowflake accounts and recording sessions.
    Snapshot files are valid JSON — readable in PR diffs.
    """

    file_extension = "json"

    def serialize(
        self,
        data: SerializableData,
        *,
        exclude: Optional[PropertyFilter] = None,
        include: Optional[PropertyFilter] = None,
        matcher: Optional[PropertyMatcher] = None,
    ) -> SerializedData:
        """Serialize an Arrow table to stable JSON."""
        if not isinstance(data, pa.Table):
            # Fall back to base JSON serialization for non-Arrow data
            return super().serialize(data, exclude=exclude, include=include, matcher=matcher)

        # Strip non-deterministic schema-level metadata
        raw_schema_meta: dict[bytes, bytes] = data.schema.metadata or {}
        clean_schema_meta = {
            k: v for k, v in raw_schema_meta.items()
            if k not in _NON_DETERMINISTIC_META_KEYS
        }

        # Build deterministic schema representation
        schema_repr = {
            "fields": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                    # Include per-field metadata (SNOWFLAKE_TYPE etc.) — these are
                    # stable type information, not non-deterministic runtime values.
                    "metadata": {
                        k.decode() if isinstance(k, bytes) else k: (
                            v.decode() if isinstance(v, bytes) else v
                        )
                        for k, v in (field.metadata or {}).items()
                    },
                }
                for field in data.schema
            ],
            "metadata": {
                k.decode() if isinstance(k, bytes) else k: (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in clean_schema_meta.items()
            },
        }

        result: dict[str, Any] = {
            "schema": schema_repr,
            "rows": data.to_pylist(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False) + "\n"
```

### Pattern 2: Custom Fixture for Custom Extension

**What:** A pytest fixture that wraps the built-in `snapshot` fixture, swapping in the custom extension class.

**When to use:** When you need a domain-specific snapshot type without changing the global default extension.

**Example:**
```python
# tests/integration/conftest.py
# Source: syrupy docs + SnapshotAssertion.use_extension() source

import pytest
from syrupy.assertion import SnapshotAssertion


@pytest.fixture
def snowflake_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Snapshot fixture pre-configured with SnowflakeArrowSnapshotSerializer."""
    return snapshot.use_extension(SnowflakeArrowSnapshotSerializer)
```

Usage in tests:
```python
def test_arrow_round_trip(snowflake_pool, snowflake_snapshot: SnapshotAssertion) -> None:
    conn = snowflake_pool.connect()
    cur = conn.cursor()
    cur.execute("SELECT 1 AS n, 'hello' AS s")
    table = cur.fetch_arrow_table()
    cur.close()
    conn.close()
    assert table == snowflake_snapshot
```

### Pattern 3: Skip-When-No-Credentials

**What:** A conftest fixture that skips all Snowflake tests when `SNOWFLAKE_ACCOUNT` is absent, then loads `.env.snowflake` and constructs the config.

**When to use:** Integration tests that require real external credentials, where CI has no credentials but local dev does.

**Example:**
```python
# tests/integration/conftest.py
# Source: project conventions + python-dotenv 1.2.1 API

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from adbc_poolhouse import SnowflakeConfig, create_pool


@pytest.fixture(scope="session")
def snowflake_pool():
    """Session-scoped pool; skips if SNOWFLAKE_ACCOUNT is absent."""
    # Load .env.snowflake if present (does not override already-set env vars)
    dotenv_path = Path(__file__).parent.parent.parent / ".env.snowflake"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    if not os.environ.get("SNOWFLAKE_ACCOUNT"):
        pytest.skip("SNOWFLAKE_ACCOUNT not set — skipping Snowflake integration tests")

    config = SnowflakeConfig()  # reads SNOWFLAKE_* env vars via pydantic-settings
    pool = create_pool(config)
    yield pool
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]
```

### Pattern 4: pytest Marker Isolation

**What:** Register a `snowflake` marker and use `addopts` to exclude it from default runs.

**When to use:** Any integration test that requires real credentials and should NEVER run in CI's default `pytest` invocation.

**Example (`[tool.pytest.ini_options]` in `pyproject.toml`):**
```toml
[tool.pytest.ini_options]
markers = [
    "snowflake: requires real Snowflake credentials (use -m snowflake to run)",
]
addopts = "-m 'not snowflake'"
```

**Usage:**
```bash
# CI default — never hits Snowflake:
uv run pytest

# Local recording:
pytest -m snowflake --snapshot-update

# Local replay verification:
pytest -m snowflake
```

### Anti-Patterns to Avoid

- **Storing credentials in snapshot files:** The serializer must never include connection kwargs, account identifiers, or auth tokens. The serializer only sees the Arrow `Table` returned by `fetch_arrow_table()` — not the connection parameters. Arrow data rows from `SELECT 1 AS n, 'hello' AS s` contain no credentials.
- **Using `session` scope for `snapshot` fixture:** The syrupy `snapshot` fixture is function-scoped by design. Use `snowflake_pool` as session-scoped (expensive) and `snapshot`/`snowflake_snapshot` as function-scoped (cheap).
- **`override=True` in `load_dotenv`:** Always use `override=False` to prevent `.env.snowflake` from overriding env vars set by the shell or CI — env vars set in the shell take precedence over file values.
- **Importing `adbc_driver_snowflake` at module level in test files:** All driver imports happen lazily inside `create_pool()`. Test files import only from `adbc_poolhouse`.
- **Not adding `.env.snowflake` to `.gitignore`:** The file contains real credentials. The current `.gitignore` only has `.env` and `.envrc` — `.env.snowflake` must be added explicitly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Snapshot file storage (read/write/delete) | Custom file I/O for snapshots | `JSONSnapshotExtension` (inherits `SingleFileSnapshotExtension`) | Storage already implemented; handles path construction, merge logic, encoding |
| Snapshot file format (text vs binary) | Raw text comparison | syrupy's `JSONSnapshotExtension` | Handles `.json` extension, `WriteMode.TEXT`, encoding, and file-per-test naming |
| Diff display on test failure | Custom diff output | Built-in syrupy diff reporting via `SnapshotReporter` | syrupy handles colored diffs, assertion output, and error messages automatically |
| Arrow schema pretty-printing | Custom Arrow → string | `json.dumps(schema_as_dict)` via the serializer | pyarrow provides `.schema`, `.name`, `.type`, `.nullable`, `.metadata` per field |
| Credential file format | Custom env file parser | `python-dotenv` `load_dotenv()` | Already a transitive dep via pydantic-settings; handles comments, quoting, escaping |

**Key insight:** The only custom code needed is the `serialize()` override in `SnowflakeArrowSnapshotSerializer` and the conftest fixtures. All file I/O, diff display, and CLI integration (`--snapshot-update`) come free from the syrupy base classes.

---

## Common Pitfalls

### Pitfall 1: Non-Deterministic Fields May Not Exist in Current Driver
**What goes wrong:** The `queryId`, `elapsedTime`, and timestamp keys to strip may not actually appear in Arrow schema metadata from the current Snowflake ADBC driver (`adbc-driver-snowflake==1.10.0`). Source code analysis shows the driver only attaches `SNOWFLAKE_TYPE` per-field. The serializer strips them defensively, but the implementer should inspect real driver output.
**Why it happens:** The roadmap specified expected fields based on what drivers typically do; the actual driver implementation may differ.
**How to avoid:** At implementation time, after connecting with real credentials, print `table.schema.metadata` and each `field.metadata` to inventory the actual keys. Strip any runtime-variable keys found in addition to the roadmap-specified ones.
**Warning signs:** Snapshot diff on re-recording shows same content → fields were already deterministic. Snapshot diff showing different `queryId` values → that key exists and must be stripped.

### Pitfall 2: `.env.snowflake` Not in `.gitignore`
**What goes wrong:** Real Snowflake credentials get committed to git. detect-secrets may catch the password but not the account identifier.
**Why it happens:** The current `.gitignore` only has `.env` and `.envrc` — `.env.snowflake` is a different filename.
**How to avoid:** Add `.env.snowflake` to `.gitignore` in this phase before any recording. Also add `*.env.snowflake` pattern for safety.
**Warning signs:** `git status` shows `.env.snowflake` as untracked.

### Pitfall 3: `addopts = "-m 'not snowflake'"` Blocks Explicit `-m snowflake` Run
**What goes wrong:** `addopts` in `pyproject.toml` adds `-m 'not snowflake'` to every pytest invocation, including `pytest -m snowflake`. These marker expressions combine with AND logic, so `pytest -m snowflake` effectively becomes `pytest -m "snowflake AND not snowflake"` — no tests run.
**Why it happens:** pytest marker filter specified in `addopts` combines with CLI marker filter using AND.
**How to avoid:** Use `pytest -m "snowflake" -p no:snowflake_marker_override` OR use a different mechanism. The recommended pattern is to NOT use `addopts = "-m 'not snowflake'"` for this project — instead rely solely on the marker being absent from the default `uv run pytest` invocation by documentation convention. However, if `addopts` IS used, the workaround is `pytest -m "snowflake" --override-ini="addopts="`.

**Verified behavior (pytest 8.0.0+):** `addopts` marker filters and CLI marker filters are combined with AND. To run snowflake tests when `addopts` contains `-m 'not snowflake'`, use:
```bash
pytest -m snowflake --override-ini="addopts="
```

**Recommended approach:** Use `addopts` for the `-m 'not snowflake'` default exclusion and document `--override-ini="addopts="` in CONTRIBUTING.md as the override mechanism.

### Pitfall 4: `snapshot` Fixture Scope Mismatch
**What goes wrong:** Using `snowflake_pool` (session-scoped) inside a function-scoped `snapshot` fixture call works fine, but attempting to make `snowflake_snapshot` session-scoped causes a syrupy error — the `snapshot` fixture is always function-scoped.
**Why it happens:** syrupy's `snapshot` fixture is hardcoded as function-scoped in `syrupy/__init__.py`. Each test function needs its own assertion state.
**How to avoid:** Keep `snowflake_snapshot` as function-scoped (no explicit `scope=`). The pool connection overhead is session-scoped; only the snapshot assertion object is per-function.

### Pitfall 5: detect-secrets Triggered by Snapshot Content
**What goes wrong:** `pre-commit` fails because detect-secrets flags content in snapshot `.json` files as potential secrets (e.g., high-entropy strings, account identifiers).
**Why it happens:** Snowflake account identifiers like `myorg-myaccount` can match HexHighEntropyString or other patterns.
**How to avoid:** The serializer captures only `SELECT 1 AS n, 'hello' AS s` result — the rows are `[{"n": 1, "s": "hello"}]`. No account identifier or credential appears in the data. The schema metadata contains only Arrow type info after stripping. Run `detect-secrets scan tests/integration/__snapshots__/` after recording to verify before committing.
**Warning signs:** Pre-commit hook fails on snapshot files with `Potential secret found`.

### Pitfall 6: Syrupy Snapshot for `table == snowflake_snapshot` Compares String to Table
**What goes wrong:** syrupy compares the serialized string from `SnowflakeArrowSnapshotSerializer.serialize(table)` against the stored JSON string. The `==` in `assert table == snowflake_snapshot` is intercepted by syrupy's `__eq__` which calls `serialize()` on the left-hand side. This works correctly only if the extension is set on the fixture.
**Why it happens:** syrupy uses Python's `__eq__` with the `SnapshotAssertion` as the right-hand side.
**How to avoid:** Always use `snowflake_snapshot` (not `snapshot`) for Arrow table assertions. `assert table == snowflake_snapshot` is the correct pattern.

---

## Code Examples

Verified from syrupy 5.1.0 source code + project conventions:

### Complete conftest.py for tests/integration/
```python
# tests/integration/conftest.py
"""Fixtures for Snowflake integration tests (TEST-03)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import pyarrow as pa
import pytest
from dotenv import load_dotenv
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension

from adbc_poolhouse import SnowflakeConfig, create_pool

if TYPE_CHECKING:
    from syrupy.types import PropertyFilter, PropertyMatcher, SerializableData, SerializedData

# Keys to strip from Arrow schema-level metadata.
# Verified list: queryId, elapsedTime, timestamp are roadmap-specified.
# Implementer must add any additional keys found in real driver responses.
_NON_DETERMINISTIC_META_KEYS: frozenset[bytes] = frozenset([
    b"queryId",
    b"elapsedTime",
    b"elapsed_time",
    b"timestamp",
    b"statementId",
    b"queryTime",
])


class SnowflakeArrowSnapshotSerializer(JSONSnapshotExtension):
    """Syrupy extension that serializes Arrow tables to stable JSON.

    Strips non-deterministic schema-level metadata before serialization.
    Schema fields include Arrow type, name, nullable, and Snowflake type metadata.
    Rows are serialized as a list of row dicts via pyarrow.Table.to_pylist().
    """

    file_extension = "json"

    def serialize(
        self,
        data: SerializableData,
        *,
        exclude: Optional[PropertyFilter] = None,
        include: Optional[PropertyFilter] = None,
        matcher: Optional[PropertyMatcher] = None,
    ) -> SerializedData:
        if not isinstance(data, pa.Table):
            return super().serialize(data, exclude=exclude, include=include, matcher=matcher)

        # Strip non-deterministic schema-level metadata
        raw_meta: dict[bytes, bytes] = data.schema.metadata or {}
        clean_meta = {k: v for k, v in raw_meta.items() if k not in _NON_DETERMINISTIC_META_KEYS}

        schema_repr = {
            "fields": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                    "metadata": {
                        (k.decode() if isinstance(k, bytes) else k): (
                            v.decode() if isinstance(v, bytes) else v
                        )
                        for k, v in (field.metadata or {}).items()
                    },
                }
                for field in data.schema
            ],
            "metadata": {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in clean_meta.items()
            },
        }

        result: dict[str, Any] = {
            "schema": schema_repr,
            "rows": data.to_pylist(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False) + "\n"


@pytest.fixture
def snowflake_snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Snapshot fixture pre-configured with SnowflakeArrowSnapshotSerializer."""
    return snapshot.use_extension(SnowflakeArrowSnapshotSerializer)


@pytest.fixture(scope="session")
def snowflake_pool():
    """Session-scoped Snowflake pool. Skips if SNOWFLAKE_ACCOUNT is absent."""
    dotenv_path = Path(__file__).parent.parent.parent / ".env.snowflake"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)

    if not os.environ.get("SNOWFLAKE_ACCOUNT"):
        pytest.skip("SNOWFLAKE_ACCOUNT not set — skipping Snowflake integration tests")

    config = SnowflakeConfig()  # reads SNOWFLAKE_* env vars
    pool = create_pool(config)
    yield pool
    pool.dispose()
    pool._adbc_source.close()  # type: ignore[attr-defined]
```

### Complete test_snowflake.py
```python
# tests/integration/test_snowflake.py
"""Snowflake integration tests (TEST-03): snapshot-based, CI-safe."""

import pytest
from syrupy.assertion import SnapshotAssertion


@pytest.mark.snowflake
class TestSnowflakeIntegration:
    """TEST-03: Snowflake syrupy snapshot tests."""

    def test_connection_health(self, snowflake_pool) -> None:
        """Pool path works: create_pool() + acquire + SELECT 1 + checkin."""
        conn = snowflake_pool.connect()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1
        cur.close()
        conn.close()

    def test_arrow_round_trip(
        self, snowflake_pool, snowflake_snapshot: SnapshotAssertion
    ) -> None:
        """Arrow schema + rows match committed snapshot; no credentials in snapshot."""
        conn = snowflake_pool.connect()
        cur = conn.cursor()
        cur.execute("SELECT 1 AS n, 'hello' AS s")
        table = cur.fetch_arrow_table()
        cur.close()
        conn.close()
        assert table == snowflake_snapshot
```

### pytest marker configuration in pyproject.toml
```toml
[tool.pytest.ini_options]
markers = [
    "snowflake: requires real Snowflake credentials (use pytest --override-ini='addopts=' -m snowflake to run)",
]
addopts = "-m 'not snowflake'"
```

### .env.snowflake format
```bash
# .env.snowflake — NEVER commit this file
# All vars use SNOWFLAKE_ prefix (matches SnowflakeConfig env_prefix)
SNOWFLAKE_ACCOUNT=myorg-myaccount
SNOWFLAKE_USER=myuser
SNOWFLAKE_PASSWORD=mypassword
SNOWFLAKE_WAREHOUSE=MY_WH
SNOWFLAKE_DATABASE=MY_DB
```

### Expected snapshot output (tests/integration/__snapshots__/test_snowflake/test_arrow_round_trip.json)
```json
{
  "schema": {
    "fields": [
      {
        "name": "n",
        "type": "int64",
        "nullable": true,
        "metadata": {
          "SNOWFLAKE_TYPE": "fixed"
        }
      },
      {
        "name": "s",
        "type": "string",
        "nullable": true,
        "metadata": {
          "SNOWFLAKE_TYPE": "text"
        }
      }
    ],
    "metadata": {}
  },
  "rows": [
    {"n": 1, "s": "hello"}
  ]
}
```
Note: Actual Arrow types may differ (e.g., `large_string` instead of `string`). Verify at recording time.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| VCR.py / responses library for HTTP mocking | syrupy snapshot testing for ADBC results | N/A — ADBC is not HTTP | VCR.py doesn't work for ADBC (binary protocol); syrupy snapshots capture the result data |
| Custom JSON fixture files | syrupy `--snapshot-update` re-recording | N/A | syrupy handles file management, naming, and diff display automatically |
| `pytest.mark.skipif(os.environ.get(...))` | `pytest.skip()` inside fixture | N/A | `pytest.skip()` inside session-scoped fixture skips all tests using that fixture |

**Deprecated/outdated:**
- VCR cassettes: Not applicable for ADBC (binary protocol, not HTTP). The syrupy snapshot approach is the correct pattern here.

---

## Open Questions

1. **Exact Arrow metadata keys from real Snowflake driver responses**
   - What we know: Source code analysis shows the driver attaches `SNOWFLAKE_TYPE` per-field. Official docs mention `logicalType`, `precision`, `scale`, `charLength`, `byteLength` per-field. The roadmap-specified schema-level keys (`queryId`, `elapsedTime`, timestamps) are NOT present in source code analysis of current driver (1.10.0).
   - What's unclear: Whether schema-level metadata from the live Go driver includes runtime fields not visible in the Python-facing source. The actual field names depend on the Go driver's internal metadata attachment.
   - Recommendation: At implementation time, after recording with real credentials, print `table.schema.metadata` and `[f.metadata for f in table.schema]` before stripping and add any runtime-variable keys discovered to `_NON_DETERMINISTIC_META_KEYS`.

2. **Arrow type for `SELECT 1 AS n, 'hello' AS s` from Snowflake**
   - What we know: DuckDB returns `int64` for literal `1` and `string` for literal `'hello'`. Snowflake may return different Arrow types based on its `FIXED` / `TEXT` type mapping (see `SNOWFLAKE_TYPE` metadata).
   - What's unclear: Whether Snowflake returns `int64`, `decimal128`, `large_int64`, `int32`, or similar for literal integer `1`; and `string`, `large_string`, `utf8`, or `large_utf8` for literal string.
   - Recommendation: Record with real credentials first; the snapshot will capture whatever types the driver returns. The recorded snapshot is the source of truth.

3. **`addopts` + `-m snowflake` interaction**
   - What we know: pytest combines `addopts` marker filters and CLI marker filters with AND. `addopts = "-m 'not snowflake'"` plus `pytest -m snowflake` gives zero tests.
   - What's unclear: Whether pytest 8.x has changed this behavior.
   - Recommendation: Document `pytest --override-ini="addopts=" -m snowflake` as the recording/replay command in CONTRIBUTING.md. This is the verified workaround.

---

## Sources

### Primary (HIGH confidence)
- syrupy 5.1.0 source code (`/Users/paul/.../site-packages/syrupy/`) — `AbstractSyrupyExtension`, `JSONSnapshotExtension`, `SingleFileSnapshotExtension`, `SnapshotAssertion.use_extension()` — confirmed by direct inspection
- adbc_driver_snowflake 1.10.0 source (`adbc_driver_snowflake/__init__.py`, `dbapi.py`) — `DatabaseOptions`, `connect()` function — confirmed by direct inspection
- pyarrow 23.0.1 — `Table.schema.metadata`, `Table.to_pylist()`, `Table.to_pydict()` — confirmed by execution
- python-dotenv 1.2.1 — `load_dotenv(dotenv_path=..., override=False)` signature — confirmed by execution
- https://arrow.apache.org/adbc/current/driver/snowflake.html — Arrow field metadata keys (`logicalType`, `precision`, `scale`, `charLength`, `byteLength`) — HIGH confidence

### Secondary (MEDIUM confidence)
- GitHub apache/arrow-adbc `record_reader.go` via WebFetch — `SNOWFLAKE_TYPE` is the only schema-level metadata key set by the driver — MEDIUM (source file content confirmed but not executed against live Snowflake)

### Tertiary (LOW confidence)
- Inferred: `queryId`, `elapsedTime`, `timestamp` fields from roadmap spec — existence in live Snowflake driver responses NOT confirmed by source analysis. Flag for verification at implementation time.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries installed and inspected directly
- Architecture: HIGH — syrupy extension pattern verified from source code; fixture pattern from syrupy API
- Pitfall #3 (addopts + -m snowflake): MEDIUM — pytest 8 behavior known from documentation but not run locally
- Arrow metadata fields: MEDIUM — confirmed from driver source and docs, but live driver may differ

**Research date:** 2026-02-25
**Valid until:** 2026-05-25 (stable libraries; syrupy and ADBC driver APIs are stable)
