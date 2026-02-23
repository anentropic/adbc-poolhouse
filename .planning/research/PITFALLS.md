# PITFALLS — adbc-poolhouse

**Research Type:** Project Research — Pitfalls dimension for ADBC connection pooling library
**Milestone:** Greenfield — all implementation is pending
**Date:** 2026-02-23

---

## How to Read This Document

Each pitfall covers:
- **The problem**: what goes wrong and why it matters here
- **Warning signs**: how to detect the problem early
- **Prevention strategy**: concrete, actionable steps
- **Phase**: when to address it (P1 = core implementation, P2 = testing, P3 = PyPI publication)

---

## Domain: Wrapping ADBC dbapi in SQLAlchemy QueuePool

### PITFALL-1: Creator function called with no arguments — ADBC connect requires kwargs

**The problem:**
SQLAlchemy `QueuePool` expects a `creator` callable with signature `() -> connection`. The ADBC dbapi `connect()` functions (e.g. `adbc_driver_snowflake.dbapi.connect`, `adbc_driver_manager.dbapi.connect`) require at minimum a URI or driver path plus kwargs for auth. If you pass `adbc_driver_snowflake.dbapi.connect` directly as the creator, the pool will call it with zero arguments — which raises an error on first checkout. The fix is always to wrap in a lambda or `functools.partial`:

```python
# WRONG — pool calls creator() with no args
pool = QueuePool(creator=adbc_driver_snowflake.dbapi.connect)

# CORRECT — credentials captured in closure
def _make_creator(kwargs: dict[str, Any]) -> Callable[[], adbc.Connection]:
    def creator() -> adbc.Connection:
        return adbc_driver_snowflake.dbapi.connect(**kwargs)
    return creator
```

**Warning signs:**
- `TypeError: connect() missing required positional argument` on first `pool.connect()`
- Tests pass at pool construction time but fail at checkout time

**Prevention strategy:**
Wrap the driver's `connect` in a zero-argument closure in the pool factory. Validate the closure is callable with no args in a unit test using `DuckDB` (in-memory, no credentials).

**Phase:** P1 — pool factory implementation


### PITFALL-2: ADBC connections are not thread-safe — pooled connections may be shared

**The problem:**
ADBC dbapi connections follow DB-API 2.0 (PEP 249) which does not guarantee thread-safety at the connection level (most are "thread-safety level 1": threads can share the module but not individual connections). SQLAlchemy `QueuePool` is designed to give each thread its own checked-out connection — but misuse patterns can still cause cross-thread connection sharing. Specifically:
- Consumers who hold a reference to a checked-out connection and pass it to another thread will corrupt it
- Pool recycle (`recycle=3600`) reuses connections across time but never across concurrent threads — this is correct, but if the ADBC connection has its own thread-affinity (e.g. DuckDB's in-process mode has GIL-bound state), recycling can surface subtle bugs

**Warning signs:**
- Race conditions or "cursor already in use" errors under concurrent load
- DuckDB in-memory mode silently corrupts state when two threads share a single `:memory:` connection

**Prevention strategy:**
- Document in the public API that consumers must not share a checked-out connection across threads
- For DuckDB in integration tests, always use a named file database (e.g. `/tmp/test.duckdb`) rather than `:memory:` when testing pool checkout under threading — `:memory:` is per-connection and an in-memory DuckDB database lives inside one connection object; two connections to `:memory:` are two different empty databases, which surprises users

**Phase:** P1 — pool factory; P2 — integration tests


### PITFALL-3: Pre-ping `pool_pre_ping=True` requires the ADBC driver to support `cursor.execute("SELECT 1")`

**The problem:**
SQLAlchemy's pre-ping mechanism issues a lightweight SQL statement to verify a connection is alive before handing it to the consumer. SQLAlchemy's `QueuePool` has a `pre_ping` parameter but the canonical mechanism for non-SQLAlchemy-ORM usage is listening to the `connect` event or using the `Pool.pre_ping` parameter added in SQLAlchemy 2.0. The problem is that ADBC's DB-API cursor does not always support bare `SELECT 1` reliably:
- The Snowflake ADBC driver may raise if the session has expired (which is the correct trigger for pre-ping) but the exception type is a driver-specific subclass, not `OperationalError` — SQLAlchemy's built-in pre-ping logic catches `OperationalError` and recycles; if the Snowflake driver raises `DatabaseError` or a custom class, the pre-ping fails with an unhandled exception instead of silently recycling
- For DuckDB, `SELECT 1` works fine

**Warning signs:**
- Pre-ping exceptions leak to the consumer as unexpected `DatabaseError` instead of transparent reconnection
- Pool connections fail after sitting idle past the Snowflake session timeout (default 4 hours) if pre-ping doesn't catch the right exception type

**Prevention strategy:**
- Use the SQLAlchemy `Pool` event system (`event.listen(pool, "checkout", _check_connection)`) to implement a custom pre-ping handler that catches all driver-specific exception types, rather than relying on SQLAlchemy's ORM-centric pre-ping
- Alternatively, set `recycle` shorter than the Snowflake session timeout (Snowflake default is 240 minutes; set `recycle=3600` to stay well under it) so connections are replaced before they go stale, making pre-ping less critical
- Test pre-ping behaviour explicitly in integration tests by manually invalidating a connection

**Phase:** P1 — pool factory; P2 — Snowflake integration tests


### PITFALL-4: ADBC connections hold Arrow memory that is not released on pool checkin

**The problem:**
ADBC connections maintain an Arrow allocator context. When SQLAlchemy's pool checks a connection back in (`pool.checkin()`), it does not call any ADBC-specific cleanup. If a consumer fetched a large result set, the Arrow buffers may remain live until the connection is physically recycled. In high-throughput scenarios this causes memory growth that looks like a pool leak but is actually an Arrow allocator leak.

**Warning signs:**
- RSS memory grows monotonically across many queries even though queries complete
- Memory does not recover until `pool.dispose()` is called

**Prevention strategy:**
- Use `AdbcConnection.close()` (not cursor close) in the pool's `reset_agent` to ensure Arrow allocators are torn down on checkin. This requires a custom reset event listener on the pool
- Document that consumers should call `cursor.close()` explicitly before returning a connection to the pool
- Write a memory-usage test with DuckDB that fetches a large Arrow result and verifies RSS does not leak after checkin

**Phase:** P1 — pool factory; P2 — integration tests


### PITFALL-5: `QueuePool` `timeout` parameter has confusing semantics with ADBC

**The problem:**
SQLAlchemy's `QueuePool` `timeout` parameter controls how long `pool.connect()` will wait for a connection to become available when the pool is exhausted (all `pool_size + max_overflow` connections are checked out). It does NOT control the network timeout for establishing a new physical connection to the warehouse. The ADBC driver's own connect timeout (e.g. Snowflake's `login_timeout`) is a separate concern set in the driver kwargs. Conflating these causes misconfigured pools where:
- `timeout=30` means "wait 30s for a slot" but the consumer assumes it means "give up if Snowflake doesn't respond in 30s"
- Network timeout is effectively infinite unless explicitly passed to the ADBC driver

**Warning signs:**
- Consumers report hangs when Snowflake is unreachable — pool waits for `max_overflow` slots that are all stuck in `connect()` indefinitely
- Pool exhaustion during network partition looks like "connection refused" but takes far longer than expected

**Prevention strategy:**
- In `SnowflakeConfig`, expose a `login_timeout_seconds` field (maps to `adbc.snowflake.sql.client_option.login_timeout`) and pass it through to the driver kwargs
- Add docstring clarification to `create_pool()` distinguishing pool checkout timeout (`timeout=`) from driver connection timeout (driver-specific kwargs)
- Default `login_timeout_seconds` to a sensible value (e.g. 60s) rather than leaving it at the driver default (infinite or very large)

**Phase:** P1 — config models and pool factory

---

## Domain: Multi-Backend Driver Detection

### PITFALL-6: Catching `ImportError` on `adbc_driver_snowflake` import hides other errors

**The problem:**
The planned driver detection strategy is:
```python
try:
    import adbc_driver_snowflake.dbapi as dbapi
except ImportError:
    # fall back to adbc_driver_manager
```
The problem: if `adbc_driver_snowflake` is installed but has a broken native extension (e.g. wrong platform, ABI mismatch, missing shared library), Python raises `ImportError` with a message like `cannot import name 'dbapi' from 'adbc_driver_snowflake'` or a `dlopen` failure. This is caught by the same `except ImportError` block and silently falls back to `adbc_driver_manager` — which then also fails because the Foundry driver for Snowflake doesn't exist. The root cause (broken installation) is invisible.

**Warning signs:**
- `ImportError: DLL load failed while importing _lib` or `ImportError: cannot import name 'dbapi'` swallowed silently
- Consumer gets a cryptic "driver not found" error from `adbc_driver_manager` with no hint that the PyPI driver was installed but broken

**Prevention strategy:**
- Distinguish "module not present" from "module present but broken" by checking the error message or using `importlib.util.find_spec()` before attempting the import:
  ```python
  import importlib.util
  spec = importlib.util.find_spec("adbc_driver_snowflake")
  if spec is not None:
      # module is present — import it; let any ImportError propagate (it's a real error)
      import adbc_driver_snowflake.dbapi as dbapi
  else:
      # module not installed — use fallback
      ...
  ```
- Re-raise `ImportError` with an augmented message that names the broken package and suggests reinstalling
- Test the fallback path explicitly with a mock that simulates a broken import

**Phase:** P1 — driver detection layer


### PITFALL-7: `adbc_driver_manager.dbapi.connect()` requires `driver_name` not `entrypoint`

**The problem:**
`adbc_driver_manager.dbapi.connect()` has two distinct call patterns depending on whether the driver is a PyPI package or a Foundry shared library:
- PyPI drivers: `connect(driver="adbc_driver_snowflake.lib", ...)` — `driver` is the Python module path to the `.lib` submodule
- Foundry drivers: `connect(driver="/path/to/libadbc_driver_databricks.so", ...)` — `driver` is a filesystem path

The error when you get this wrong is a cryptic `RuntimeError: ADBC_STATUS_NOT_FOUND: Driver 'adbc_driver_snowflake' not found` — the error message does not tell you whether the issue is the driver path format or that the driver isn't installed. Additionally, the `.lib` submodule path is not the same as the PyPI package name: `adbc_driver_snowflake` (package) vs `adbc_driver_snowflake.lib` (the C extension module path passed to the manager).

**Warning signs:**
- `RuntimeError: ADBC_STATUS_NOT_FOUND` when using `adbc_driver_manager` to load a driver that is installed on PyPI
- Driver loads fine with direct import but fails through `adbc_driver_manager`

**Prevention strategy:**
- Maintain an explicit mapping from warehouse type to both the PyPI module path and the `adbc_driver_manager` driver path:
  ```python
  DRIVER_PATHS = {
      "snowflake": {
          "pypi_module": "adbc_driver_snowflake",
          "pypi_lib_path": "adbc_driver_snowflake.lib",
      },
      "duckdb": {
          "pypi_module": "adbc_driver_duckdb",
          "pypi_lib_path": "adbc_driver_duckdb.lib",
      },
  }
  ```
- Integration test the `adbc_driver_manager` path explicitly, even for PyPI drivers (DuckDB can be tested locally without credentials)

**Phase:** P1 — driver detection layer


### PITFALL-8: Driver detection fires on import, not on `create_pool()` call

**The problem:**
If driver detection logic runs at module import time (e.g. at the top level of `adbc_poolhouse/__init__.py`), then `import adbc_poolhouse` will fail or emit warnings if no ADBC drivers are installed — even if the user only wants to construct a config object without creating a pool. This breaks introspection tools, documentation generators, and lightweight consumers that only use the config models.

**Warning signs:**
- `import adbc_poolhouse` raises `ImportError` or `RuntimeError` in CI where optional drivers aren't installed
- `mkdocstrings` fails to build API docs because the import fails

**Prevention strategy:**
- All driver detection must be lazy — deferred to `create_pool()` call time, not import time
- Config model imports (`SnowflakeConfig`, `DuckDBConfig`) must have zero ADBC driver dependencies
- Mark driver imports as `TYPE_CHECKING`-only where the type is only needed for annotations:
  ```python
  from __future__ import annotations
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      import adbc_driver_snowflake.dbapi
  ```

**Phase:** P1 — module design, driver detection layer

---

## Domain: Pydantic BaseSettings Config Models

### PITFALL-9: Pydantic `SecretStr` fields don't round-trip through env vars without explicit coercion

**The problem:**
`pydantic-settings` reads environment variables as strings and coerces them to field types. For `SecretStr` fields (e.g. `password: SecretStr`), the coercion works at model construction time. However, when the secret value is extracted for passing to the ADBC driver (`config.password.get_secret_value()`), the type is now `str` — but basedpyright strict mode will flag this as `str | None` unless the field is declared non-optional with a default or marked `Required`. More dangerously, if the field is `SecretStr | None` (optional password), calling `.get_secret_value()` on the un-checked `None` case causes a runtime `AttributeError`.

**Warning signs:**
- basedpyright reports `Object of type "None" cannot be used as type "SecretStr"` on parameter translation
- `AttributeError: 'NoneType' object has no attribute 'get_secret_value'` in edge-case auth flows (e.g. key-pair auth where password is not needed)

**Prevention strategy:**
- Use discriminated union config models rather than optional fields: e.g. `SnowflakePasswordAuth` and `SnowflakeKeyPairAuth` as separate Pydantic models with a `Literal` discriminator, rather than one model with many optional fields
- Where `SecretStr | None` is genuinely needed, assert the non-None value is present before calling `.get_secret_value()` — the assertion is typed with `assert config.password is not None` which narrows the type for basedpyright
- Test all optional-secret edge cases explicitly (missing password, empty password, password=None)

**Phase:** P1 — config models


### PITFALL-10: Environment variable prefix collision between multiple warehouse configs

**The problem:**
`pydantic-settings` uses an `env_prefix` on the `Settings` inner class to namespace env vars. If `SnowflakeConfig` uses `SNOWFLAKE_` and `DuckDBConfig` uses `DUCKDB_`, this works correctly. However:
- If the prefix is not set (default is empty string), `SnowflakeConfig` will greedily read any env var whose name matches a field name — e.g. a `DATABASE` field on `DuckDBConfig` would read from `DATABASE` in the environment, which may be set by the system (Heroku, Docker, etc.) to point to a PostgreSQL URL
- When two consumers (dbt-open-sl + Semantic ORM) are used together in the same process, their environment variable spaces must not collide

**Warning signs:**
- Config model picks up the wrong value from the environment silently
- `DuckDBConfig.database` unexpectedly points to `postgresql://...` because `DATABASE` is in the environment

**Prevention strategy:**
- Mandate explicit `env_prefix` on every config model (`model_config = SettingsConfigDict(env_prefix="SNOWFLAKE_")`)
- Add a validation test for each config model that asserts it does NOT read from unprefixed env vars
- Document env var names explicitly in the config model docstring

**Phase:** P1 — config models


### PITFALL-11: Snowflake private key auth — PEM bytes vs. PEM string vs. decrypted key

**The problem:**
Snowflake ADBC driver's key-pair authentication (`adbc.snowflake.sql.auth_type = "snowflake_jwt"`) requires the private key as either:
- A decrypted PEM string (if passphrase-protected, the driver decrypts internally)
- A path to a PEM file
- Raw DER bytes

The field in `SnowflakeConfig` could be `str` (PEM content), `Path` (file path), or `bytes` (DER). If you define it as `str` (the natural Pydantic choice), then:
- Consumers who pass a file path as a string get a confusing failure (the driver tries to parse the path as PEM content)
- Consumers who set the env var `SNOWFLAKE_PRIVATE_KEY` to a file path string receive it as `str` and it is silently treated as PEM content, not as a path

**Warning signs:**
- Snowflake JWT auth fails with `Error decoding private key` when the field contains a file path
- Different auth behaviour depending on whether the config was created programmatically or from env vars

**Prevention strategy:**
- Use separate fields: `private_key_path: Path | None` and `private_key_pem: SecretStr | None`, never a single polymorphic field
- Add a `model_validator` that asserts at most one of these fields is set
- In the parameter translation layer, resolve the path to bytes before passing to the ADBC driver
- Test both private key field variants in unit tests

**Phase:** P1 — Snowflake config model and parameter translation


### PITFALL-12: `model_config = SettingsConfigDict(...)` is not inherited cleanly in subclasses

**The problem:**
If a base `WarehouseConfig(BaseSettings)` defines `model_config` and a subclass `SnowflakeConfig(WarehouseConfig)` also defines `model_config`, Pydantic v2 merges the configs, but only the fields declared at each level — not a true deep merge. In practice, if `WarehouseConfig` sets `frozen=True` and `SnowflakeConfig` sets `env_prefix="SNOWFLAKE_"`, the subclass config may not have `frozen=True` unless it explicitly re-specifies it. This is subtle and only shows up when a consumer mutates a config that should be immutable.

**Warning signs:**
- `config.account = "other"` succeeds (no `ValidationError`) when `frozen=True` was intended
- basedpyright does not catch this because `frozen` affects runtime behaviour, not static types

**Prevention strategy:**
- Keep all config models as direct `BaseSettings` subclasses with their own complete `model_config`, rather than inheriting from an intermediate base
- Write a test asserting that mutation raises `ValidationError` for each config model
- If a shared base is genuinely needed, test the merged config explicitly using `model_config.__dict__`

**Phase:** P1 — config models

---

## Domain: PyPI Publication with Optional Dependencies

### PITFALL-13: Optional extras are silently omitted from `requires-python` validation

**The problem:**
`pyproject.toml` optional extras (`[project.optional-dependencies]`) are not validated by PyPI or pip against `requires-python`. If `adbc-driver-snowflake` requires Python ≥ 3.9 and `adbc-poolhouse` requires Python ≥ 3.11, pip will install `adbc-poolhouse[snowflake]` on Python 3.9 with no error. However, this project's issue is the reverse: an optional dep may drop support for a Python version this library still claims to support. When a future version of `adbc-driver-snowflake` drops Python 3.11, `pip install adbc-poolhouse[snowflake]` on Python 3.11 will fail at resolution time with a confusing error that names the transitive dependency, not `adbc-poolhouse`.

**Warning signs:**
- CI fails on Python 3.11 with `No solution found for adbc-driver-snowflake` after an optional dep bumps its `requires-python`
- The error message names the transitive dep, not `adbc-poolhouse`, confusing consumers

**Prevention strategy:**
- Pin optional extras with a generous but explicit upper bound: `adbc-driver-snowflake>=1.0.0,<2.0.0` in the extras
- CI matrix must install and test each extra combination: `uv sync --extra snowflake` on both Python 3.11 and 3.14
- Monitor optional dep changelogs for `requires-python` bumps as part of dependency review

**Phase:** P3 — PyPI publication; also relevant in CI setup


### PITFALL-14: `sqlalchemy` as a core dependency pulls in the full ORM

**The problem:**
The design decision is to use `sqlalchemy.pool` and `sqlalchemy.event` only — not the ORM. But `sqlalchemy` on PyPI is a single package; there is no `sqlalchemy-pool` sub-package. Declaring `sqlalchemy` as a runtime dependency will install the full SQLAlchemy package (including ORM, dialects, async machinery). This is approximately 2MB and dozens of modules that consumers don't need. While harmless in production, it:
- Increases install size for lightweight consumers (e.g. a CLI tool that just wants a connection pool)
- Creates a surprising dependency graph (consumer sees `sqlalchemy` in `pip list` and assumes ORM usage)
- Conflicts with consumers who pin SQLAlchemy at different major versions for their own ORM usage

**Warning signs:**
- Consumers open issues asking why `adbc-poolhouse` requires SQLAlchemy if it's "just a pool"
- Version conflicts when a consumer project also uses SQLAlchemy ORM at a different version

**Prevention strategy:**
- Accept the full `sqlalchemy` dependency — it is unavoidable — but document clearly in the README that only the pool submodule is used
- Declare a version range that accommodates SQLAlchemy 2.x LTS: `sqlalchemy>=2.0.0,<3.0.0`
- Consider (but likely reject for v1) implementing a hand-rolled minimal pool to eliminate this dependency; defer to v2 only if real consumers raise it as a blocker
- Internal code must only import from `sqlalchemy.pool` and `sqlalchemy.event` — enforce this with a ruff custom rule or a grep-based pre-commit hook

**Phase:** P1 — dependency declarations; P3 — publication documentation


### PITFALL-15: Missing `py.typed` marker invalidates PEP 561 compliance on PyPI

**The problem:**
The repo already has `src/adbc_poolhouse/py.typed` — good. However, the `py.typed` marker must also be declared in `pyproject.toml` under `[tool.uv]` or as package data so that the build backend (`uv_build`) includes it in the wheel. If `py.typed` is omitted from the wheel manifest (which `uv_build` may do if not explicitly included, depending on version), the installed package will not be PEP 561 compliant even though the source has the file. Consumers' type checkers will then treat the package as untyped and silently ignore its type annotations.

**Warning signs:**
- `basedpyright` on a consumer project reports `Import "adbc_poolhouse" could not be resolved from source` or `No type stubs found`
- `pip show adbc-poolhouse` installed in a consumer project; checking the installed wheel contents with `zipinfo` shows no `py.typed`

**Prevention strategy:**
- Verify the built wheel contains `py.typed` by inspecting the wheel artifact before publication: `python -m zipfile -l dist/adbc_poolhouse-*.whl | grep py.typed`
- Add this check to the release workflow's validation step (alongside the existing smoke test)
- With `uv_build`, `py.typed` is included automatically if it is a file within the package source — confirm this is the case once `uv_build` version is updated

**Phase:** P3 — release workflow validation


### PITFALL-16: PyPI trusted publishing OIDC requires exact workflow filename match

**The problem:**
The project uses OIDC trusted publishing (`id-token: write`, `pypa/gh-action-pypi-publish`) to publish to PyPI without a stored API token. Trusted publishing on PyPI requires the workflow file to be pre-registered with the exact name. If the workflow file is renamed or the repository is forked, the OIDC token will be rejected with `403 Forbidden - Invalid token`. This silently fails late in the release process (after the wheel is built and validated).

**Warning signs:**
- Release workflow passes all validation steps but fails at the PyPI publish step with `403`
- Log shows `invalid-publisher` from the PyPI API

**Prevention strategy:**
- Register the trusted publisher on PyPI before the first release, using the exact workflow filename `.github/workflows/release.yml`
- Add a pre-release checklist item: verify trusted publisher is configured
- Document the trusted publisher setup in `DEVELOP.md`

**Phase:** P3 — first PyPI publication

---

## Domain: Snapshot Testing with Syrupy for Snowflake

### PITFALL-17: Syrupy snapshots capture non-deterministic data (timestamps, query IDs, metadata)

**The problem:**
Snowflake responses include metadata fields that change on every query execution:
- `queryId` (UUID per query)
- `creationTime`, `endTime` timestamps
- `elapsedTime` in milliseconds
- Session tokens embedded in error messages
- Arrow batch metadata (e.g. `statistics` dict with wall-clock timing)

If the snapshot captures the raw response object or Arrow RecordBatch metadata, the snapshot will fail on every replay because these fields differ. syrupy's default serialiser (`AmberSnapshotSerializer`) will diff the entire object tree, causing spurious failures on any re-recording.

**Warning signs:**
- Snapshot tests pass locally on recording day but fail immediately on re-recording
- CI failures with `snapshot does not match` on timestamp or ID fields that aren't the data under test

**Prevention strategy:**
- Create a custom syrupy extension class that strips non-deterministic metadata before serialisation:
  ```python
  class SnowflakeArrowSnapshotSerializer(AmberSnapshotSerializer):
      STRIP_KEYS = {"queryId", "creationTime", "endTime", "elapsedTime"}
      def serialize(self, data, ...):
          return super().serialize(self._strip_metadata(data), ...)
  ```
- Only snapshot the Arrow schema and data content; never snapshot execution metadata
- For RecordBatch results, snapshot the schema (`batch.schema`) and sorted data (`batch.to_pydict()` with keys sorted) separately

**Phase:** P2 — Snowflake snapshot test implementation


### PITFALL-18: Syrupy snapshot update workflow is not CI-safe

**The problem:**
syrupy snapshots are updated by running `pytest --snapshot-update`. If a developer runs this locally after a schema change and the updated snapshots reflect incorrect behaviour (e.g. a bug in the parameter translation), the wrong snapshot gets committed. Once committed, CI passes forever because CI compares against the (wrong) snapshot. Unlike regular assertions, snapshot failures are "silent correctness regressions" — CI goes green but the actual data changed.

**Warning signs:**
- Snapshot files are modified in a commit alongside implementation changes without explicit review
- `--snapshot-update` is run as part of the normal test command rather than as an explicit opt-in

**Prevention strategy:**
- Never run `--snapshot-update` in CI — fail if snapshots are stale, never auto-update
- Add a CI step that runs with `--snapshot-warn-unused` to detect orphaned snapshots
- Require snapshot updates to be in a dedicated commit with a `test(snapshots): update` commit message convention to make them easy to review
- Write a `DEVELOP.md` section on when and how to update snapshots (re-record against real Snowflake, review the diff carefully, commit separately)

**Phase:** P2 — Snowflake snapshot test workflow


### PITFALL-19: Committed Snowflake snapshots may contain credential residue

**The problem:**
If the Snowflake response contains any reflection of the connection parameters (e.g. error messages that echo the account identifier, the username in session metadata, or auth token fragments in response headers), the committed snapshot file will contain credentials. This is subtle — the snapshot is a serialised Arrow response, and the Snowflake ADBC driver sometimes includes the account name in query result metadata.

**Warning signs:**
- Pre-commit secret scanner (e.g. `detect-secrets`, `gitleaks`) flags the snapshot files
- Snapshot file contains strings matching the `SNOWFLAKE_ACCOUNT` env var value

**Prevention strategy:**
- Always record snapshots against a dedicated test Snowflake account/user with minimal permissions
- Inspect snapshot files before committing with a grep for the account name and username
- Add `detect-secrets` to pre-commit hooks before recording any snapshots
- Design the custom snapshot serialiser (PITFALL-17) to also strip account identifiers and usernames from result metadata

**Phase:** P2 — Snowflake snapshot recording workflow; should be done before first recording


### PITFALL-20: `adbc-driver-snowflake` is not available on PyPI for Windows in CI

**The problem:**
`adbc-driver-snowflake` publishes prebuilt wheels for Linux (x86_64, aarch64) and macOS (x86_64, arm64) but historically has been slow to publish Windows wheels. GitHub Actions CI running on `ubuntu-latest` is fine, but if CI is ever extended to `windows-latest`, the install step for Snowflake integration tests will fail with `No matching distribution found for adbc-driver-snowflake`. This is not a current blocker (current CI is Linux only), but it can surprise if a Windows-using consumer tries to install.

**Warning signs:**
- `pip install adbc-driver-snowflake` fails on Windows with `No matching distribution found`
- CI fails on a Windows runner added to the matrix

**Prevention strategy:**
- Keep CI on `ubuntu-latest` runners for Snowflake integration tests
- Document Windows support status in `README.md`: "Windows not currently supported for Snowflake backend; DuckDB backend supports Windows"
- Use `pytest.mark.skipif(sys.platform == "win32", reason="adbc-driver-snowflake not available on Windows")` on Snowflake tests

**Phase:** P2 — CI configuration; P3 — documentation

---

## Domain: Python 3.11+ with basedpyright Strict Mode

### PITFALL-21: `pythonVersion = "3.14"` in basedpyright misses 3.11 compatibility bugs

**The problem (already flagged in CONCERNS.md):**
The project `requires-python = ">=3.11"` but `[tool.basedpyright]` sets `pythonVersion = "3.14"`. basedpyright's strict mode type-checks against 3.14 semantics. Features that are valid in 3.14 but not in 3.11 pass the type checker but raise `SyntaxError` or `AttributeError` at runtime for 3.11 users. Specific risks:
- `tomllib` in stdlib (3.11+, fine) but `tomllib.loads` API vs `tomlib.load` (fine)
- `typing.TypeVar` with `default=` parameter (PEP 696, 3.13+) — silently accepted in strict 3.14 mode, fails at runtime on 3.11
- `ExceptionGroup` / `except*` syntax (3.11+, fine) — but `BaseExceptionGroup` subclassing behaviour differs
- `typing.override` decorator (3.12+) — using it in code that must run on 3.11 requires `from typing_extensions import override`

**Warning signs:**
- CI on Python 3.11 runner fails with `AttributeError` or `SyntaxError` on code that passed basedpyright
- `TypeError: TypeVar() got an unexpected keyword argument 'default'` on 3.11

**Prevention strategy (hardened beyond CONCERNS.md):**
- Set `pythonVersion = "3.11"` in `[tool.basedpyright]` immediately — this is the correct setting
- Add `from __future__ import annotations` to all source files to defer annotation evaluation and avoid 3.10/3.11 annotation syntax differences
- For any 3.12+ stdlib additions needed (e.g. `typing.override`), import from `typing_extensions` with a version guard
- Run the full CI matrix (Python 3.11 + 3.14) from day one of implementation, not just before publication

**Phase:** P1 — must fix before any implementation is written


### PITFALL-22: SQLAlchemy pool stubs are incomplete — basedpyright strict mode will require `cast()` or `type: ignore`

**The problem:**
SQLAlchemy's type stubs (`sqlalchemy-stubs` / bundled in SQLAlchemy 2.x) are extensive but focused on the ORM layer. The pool submodule (`sqlalchemy.pool.QueuePool`, `sqlalchemy.event`) has looser typing. In strict mode, basedpyright will flag:
- `QueuePool` constructor `creator` parameter typed as `Callable[[], Any]` — too loose, but changing it requires a cast
- `event.listen(pool, "checkout", handler)` — the event system uses `Any` for the event name and handler signature; strict mode may flag the handler's parameter types as `Unknown`
- `pool.connect()` returns `PoolProxiedConnection` which has `__enter__`/`__exit__` typed, but methods like `cursor()` return `Any`

**Warning signs:**
- basedpyright emits `error: Argument of type "(...) -> AdbcConnection" is not assignable to parameter "creator" of type "Callable[[], Any]"` (the types actually match, but strict mode reports an issue with variance)
- Multiple `Unknown` type warnings from SQLAlchemy event system in strict mode

**Prevention strategy:**
- Accept that SQLAlchemy pool interop will require a small number of `cast()` calls and document them with comments explaining why
- Do not use blanket `# type: ignore` — prefer `cast(PoolProxiedConnection, pool.connect())` which is explicit
- Write a `_pool_types.py` internal module that defines typed wrappers around the SQLAlchemy pool API surface used by this library; this isolates the `cast()` calls to one file and keeps the rest of the codebase clean

**Phase:** P1 — pool factory implementation


### PITFALL-23: basedpyright strict `reportUnknownMemberType` fires on `adbc_driver_*` packages

**The problem:**
The ADBC driver packages (`adbc_driver_snowflake`, `adbc_driver_duckdb`, `adbc_driver_manager`) have partial or absent type stubs. basedpyright strict mode's `reportUnknownMemberType` and `reportUnknownVariableType` rules will fire on almost every interaction with these packages. This creates a choice: either disable the rules globally (losing the value of strict mode) or wrap all ADBC driver usage behind a typed internal API.

**Warning signs:**
- basedpyright reports dozens of `error: Type of "connect" is partially unknown` on driver imports
- Pre-commit hook fails on every file that touches `adbc_driver_*`

**Prevention strategy:**
- Create a `src/adbc_poolhouse/_driver_api.py` typed facade that wraps ADBC driver calls with explicit return types:
  ```python
  from typing import Any
  import adbc_driver_snowflake.dbapi as _sf_dbapi

  def snowflake_connect(**kwargs: Any) -> "_sf_dbapi.Connection":
      return _sf_dbapi.connect(**kwargs)  # type: ignore[no-any-return]
  ```
  Isolate all `type: ignore` suppressions to this one file
- Add inline `pyright: ignore` comments with explanatory notes, not blanket disables
- Submit type stub PRs upstream to ADBC driver repos if the stubs are simply missing

**Phase:** P1 — first implementation step, before writing pool factory

---

## Cross-Cutting Risks

### PITFALL-24: DuckDB in-memory database is not shared across connections in the pool

**The problem:**
`DuckDBConfig(database=":memory:")` is appealing for tests because it needs no filesystem access. But a DuckDB `:memory:` database is scoped to a single connection. When `QueuePool` maintains multiple connections to `":memory:"`, each connection has its own isolated in-memory database. A table created on one connection is invisible to another. This surprises users who use `:memory:` for integration tests that involve multi-connection scenarios (e.g. "write on one connection, read on another").

DuckDB supports a shared in-memory mode via `:memory:?cache=shared` on some versions, but this is version-dependent and not official ADBC API behaviour.

**Warning signs:**
- Integration test passes when `pool_size=1` but fails when `pool_size=2` with "table not found"
- DuckDB `:memory:` tests pass in isolation but fail when run in parallel with `pytest-xdist`

**Prevention strategy:**
- In documentation and tests, use a named temp file database for DuckDB pool tests: `DuckDBConfig(database="/tmp/test.duckdb")`
- In `DuckDBConfig`, add a `model_validator` that emits a `UserWarning` when `database=":memory:"` and `pool_size > 1`: "`:memory:` databases are connection-scoped; use a named database or pool_size=1"
- Write a test that explicitly verifies the isolation behaviour so it is documented rather than silently surprising

**Phase:** P1 — DuckDB config model; P2 — integration tests


### PITFALL-25: `pool.dispose()` is a consumer responsibility but is easy to forget — resource leak on library teardown

**The problem:**
`QueuePool` keeps live connections open until `.dispose()` is called. Since the library explicitly has no global state and the consumer owns the pool, pool cleanup is entirely the consumer's responsibility. In practice:
- Long-running applications that recreate pools (e.g. on config reload) will accumulate leaked ADBC connections if they don't dispose the old pool
- Test suites that create pools in fixtures without teardown will exhaust Snowflake's session limit

**Warning signs:**
- Snowflake dashboard shows accumulating idle sessions from the test suite
- `ResourceWarning: unclosed connection` at process exit

**Prevention strategy:**
- Implement `__enter__`/`__exit__` on the returned pool object (SQLAlchemy `QueuePool` already supports context manager protocol via `.connect()`, but the pool itself does not — consider returning a wrapper)
- Alternatively, document prominently that `pool.dispose()` must be called, and show it in every usage example
- In pytest fixtures: always yield the pool and call `pool.dispose()` in teardown:
  ```python
  @pytest.fixture
  def duckdb_pool():
      pool = create_pool(DuckDBConfig(database=":memory:"))
      yield pool
      pool.dispose()
  ```

**Phase:** P1 — pool factory design; P2 — test fixtures

---

## Summary: Phase Mapping

| Phase | Pitfalls to Address |
|-------|---------------------|
| P1 — Core Implementation | PITFALL-1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 21, 22, 23, 24, 25 |
| P2 — Testing | PITFALL-2, 3, 4, 17, 18, 19, 20, 24, 25 |
| P3 — PyPI Publication | PITFALL-13, 14, 15, 16, 20 |

High-risk items that must be resolved before writing any implementation code:
- **PITFALL-21** — fix `pythonVersion` in basedpyright config before writing a single line
- **PITFALL-8** — lazy driver detection design decision before designing module structure
- **PITFALL-23** — ADBC driver typing facade before pool factory

---

*Generated: 2026-02-23*
*Scope: adbc-poolhouse greenfield implementation pitfalls*
