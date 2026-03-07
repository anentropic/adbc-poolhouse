# Phase 3: Config Layer - Research

**Researched:** 2026-02-24
**Domain:** pydantic-settings, ADBC driver connection parameters, typed config models
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Module layout**
- Internal implementation: per-warehouse files (`_duckdb_config.py`, `_snowflake_config.py`, `_bigquery_config.py`, etc.) — one file per warehouse backend
- Public API: all config models re-exported from `adbc_poolhouse.__init__` — consumers use `from adbc_poolhouse import DuckDBConfig, SnowflakeConfig`
- A `WarehouseConfig` Protocol exported publicly from `adbc_poolhouse` — downstream code (e.g. Semantic ORM lib) type-annotates against it without importing every concrete class

**Inheritance structure**
- `BaseWarehouseConfig(BaseSettings)` — public, abstract (cannot be instantiated directly), holds the shared pool tuning fields with library defaults
- Pool tuning fields on base: `pool_size`, `max_overflow`, `timeout`, `recycle` — all optional with defaults from POOL-02
- All concrete warehouse configs inherit from `BaseWarehouseConfig` — flat field layout, no nested composition
- This design means `DUCKDB_POOL_SIZE`, `SNOWFLAKE_POOL_SIZE` etc. all work naturally via env_prefix without custom delimiter config
- `BaseWarehouseConfig` is part of the public API (exported from `__init__`)

**Validation error messages**
- Error messages are descriptive with diagnosis: explain WHAT went wrong and WHY it's a problem
- Mutual exclusivity errors include a fix hint (e.g. "use private_key_path for a file path or private_key_pem for PEM content, not both")
- Let Pydantic's `ValidationError` bubble through naturally — do NOT catch and re-raise as plain `ValueError`; our message appears inside the `ValidationError` context

**Foundry backend depth (CFG-06)**
- Researcher investigates BOTH the ADBC driver source/docs AND upstream warehouse docs (e.g. Databricks connection params, Teradata JDBC field names) to triangulate accurate field lists
- `MSSQLConfig`: one class covering SQL Server, Azure SQL, Fabric, and Synapse Analytics variants via optional variant-specific fields — NOT separate classes per variant
- When driver docs are sparse or ambiguous, include the field with a docstring note indicating the source of verification

### Claude's Discretion
- Exact field defaults for non-pool fields (e.g. default port values, optional vs required determination for lesser-used fields)
- Docstring style and content beyond what's captured in decisions above
- Field ordering within each config model

### Deferred Ideas (OUT OF SCOPE)
- Dev tooling for installing Foundry-distributed drivers locally (Databricks, Redshift, Trino, MSSQL, Teradata are not on PyPI) — noted for a future phase or standalone tooling task. Phase 3 uses doc research only; actual driver installation tooling is out of scope here.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CFG-01 | `DuckDBConfig` — Pydantic `BaseSettings` subclass covering all DuckDB ADBC connection parameters; `env_prefix="DUCKDB_"` | DuckDB ADBC docs confirm `path` (or `database` alias) is the primary field; driver/entrypoint are internal to driver manager |
| CFG-02 | `DuckDBConfig` `model_validator` raises `ValueError` when `database=":memory:"` and `pool_size > 1` | Verified: `@model_validator(mode='after')` raising `ValueError` is caught by pydantic as `ValidationError` — correct pattern |
| CFG-03 | `SnowflakeConfig` — Pydantic `BaseSettings` subclass covering all auth methods supported by `adbc-driver-snowflake`; `env_prefix="SNOWFLAKE_"` | Full parameter set documented from arrow.apache.org/adbc/current/driver/snowflake.html |
| CFG-04 | `SnowflakeConfig` private key: separate `private_key_path: Path \| None` and `private_key_pem: SecretStr \| None` fields with mutual exclusivity validator | Verified working with `@model_validator(mode='after')` pattern |
| CFG-05 | Config models for Apache ADBC backends: `BigQueryConfig`, `PostgreSQLConfig`, `FlightSQLConfig` — each a `BaseSettings` subclass with appropriate `env_prefix` | Parameters verified against official ADBC docs for all three |
| CFG-06 | Config models for Foundry-distributed backends: `DatabricksConfig`, `RedshiftConfig`, `TrinoConfig`, `MSSQLConfig`, `TeradataConfig` | Parameters documented from docs.adbc-drivers.org and docs.columnar.tech for all except Teradata (sparse — needs doc note) |
| CFG-07 | All config models: pool tuning kwargs (`pool_size`, `max_overflow`, `timeout`, `recycle`) on base class as optional fields | Verified: child class `model_config` env_prefix applies to inherited base fields — `DUCKDB_POOL_SIZE` works correctly |
| TEST-04 | Unit tests for all config models: field validation, `SecretStr` handling, `env_prefix` isolation, `model_validator` behaviour | pytest already installed; test patterns mapped in Architecture section |
</phase_requirements>

---

## Summary

Phase 3 implements typed, validated, environment-variable-friendly config models using pydantic-settings v2. The core pattern is `BaseWarehouseConfig(BaseSettings, abc.ABC)` with per-warehouse concrete subclasses, each defining their own `env_prefix` via `model_config = SettingsConfigDict(env_prefix='WAREHOUSE_')`. **Critical verified finding:** child class `env_prefix` applies naturally to inherited base class fields — `DUCKDB_POOL_SIZE` populates the inherited `pool_size` field on `DuckDBConfig` without any custom logic.

The abstract base pattern (`abc.ABC` + `@abc.abstractmethod`) correctly prevents direct `BaseWarehouseConfig()` instantiation while allowing concrete subclasses to instantiate normally. The `WarehouseConfig` Protocol with `@runtime_checkable` enables downstream type annotation without coupling to concrete classes. All pydantic-settings behaviors are verified against the installed version (pydantic-settings 2.13.1, pydantic 2.12.5).

ADBC connection parameters are fully documented for Apache drivers (DuckDB, Snowflake, PostgreSQL, BigQuery, FlightSQL). For Foundry drivers, Databricks, Redshift, Trino, and MSSQL are documented via docs.adbc-drivers.org. Teradata documentation is sparse (404 on driver-specific page) — fields must be documented with source attribution notes. The CONTEXT.md decision to use a URI-based field design for Foundry drivers (Databricks, Redshift, Trino, MSSQL all use URI connection strings) simplifies the field surface significantly.

**Primary recommendation:** Use `BaseWarehouseConfig(BaseSettings, abc.ABC)` with a sentinel `@abc.abstractmethod` to block direct instantiation; concrete classes override only `model_config`. Implement `WarehouseConfig` as a `@runtime_checkable Protocol` with the four pool tuning fields. All config modules live in `src/adbc_poolhouse/_<warehouse>_config.py` with re-exports in `__init__.py`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-settings | >=2.0.0 (2.13.1 installed) | `BaseSettings` for env var loading, validation, `SecretStr` | Already a project runtime dependency; the canonical Python settings library |
| pydantic | >=2.0.0 (2.12.5 installed) | `model_validator`, `field_validator`, `SecretStr`, `ValidationError` | Already a transitive dependency of pydantic-settings |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathlib.Path` | stdlib | `private_key_path` field type for Snowflake | Prefer over `str` — provides OS-portable path handling |
| `typing.Protocol` + `@runtime_checkable` | stdlib | `WarehouseConfig` structural type | When downstream code needs to accept "any config" without importing all concrete classes |
| `abc.ABC` + `@abc.abstractmethod` | stdlib | Prevent direct `BaseWarehouseConfig()` instantiation | Standard Python abstract class pattern |
| `typing_extensions.Self` | stdlib (3.11+) | Return type annotation in `model_validator(mode='after')` | Required for correct typing of after-validators |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `abc.ABC` for abstract base | `raise NotImplementedError` in `__init__` | ABC gives proper `TypeError` at class definition check; `NotImplementedError` is a runtime surprise |
| Separate `private_key_path` and `private_key_pem` | Single `private_key: str` | Single `str` is ambiguous between file path and PEM content — rejected per CFG-04 |
| `@runtime_checkable Protocol` | `Union[DuckDBConfig, SnowflakeConfig, ...]` | Union breaks Open/Closed principle; Protocol allows new backends without changing type signatures |

**Installation:** No additional packages needed — pydantic-settings is already a runtime dependency.

---

## Architecture Patterns

### Recommended Project Structure
```
src/adbc_poolhouse/
├── __init__.py              # public re-exports: all Config classes + WarehouseConfig Protocol
├── _base_config.py          # BaseWarehouseConfig(BaseSettings, abc.ABC) + WarehouseConfig Protocol
├── _duckdb_config.py        # DuckDBConfig
├── _snowflake_config.py     # SnowflakeConfig
├── _bigquery_config.py      # BigQueryConfig
├── _postgresql_config.py    # PostgreSQLConfig
├── _flightsql_config.py     # FlightSQLConfig
├── _databricks_config.py    # DatabricksConfig
├── _redshift_config.py      # RedshiftConfig
├── _trino_config.py         # TrinoConfig
├── _mssql_config.py         # MSSQLConfig
└── _teradata_config.py      # TeradataConfig

tests/
├── conftest.py              # shared fixtures (monkeypatch env, config factories)
├── test_adbc_poolhouse.py   # existing (keep test_import)
└── test_configs.py          # TEST-04: all config model unit tests
```

### Pattern 1: BaseWarehouseConfig with Abstract Sentinel

**What:** `BaseWarehouseConfig` inherits from both `BaseSettings` and `abc.ABC`. A `@abc.abstractmethod` sentinel method prevents direct instantiation. Concrete subclasses implement the sentinel and define their own `env_prefix`.

**When to use:** Whenever you need a shared pool of fields but want to prevent the base being used directly.

**Verified working example:**
```python
# Source: verified locally against pydantic-settings 2.13.1
import abc
from typing_extensions import Self
from pydantic_settings import BaseSettings, SettingsConfigDict

class BaseWarehouseConfig(BaseSettings, abc.ABC):
    """Public base for all warehouse config models.

    Provides pool tuning fields. Cannot be instantiated directly.
    """
    pool_size: int = 5
    max_overflow: int = 3
    timeout: int = 30
    recycle: int = 3600

    @abc.abstractmethod
    def _adbc_driver_key(self) -> str:
        """Internal: returns the driver name/key for the ADBC driver manager."""
        ...


class DuckDBConfig(BaseWarehouseConfig):
    """DuckDB warehouse configuration."""
    model_config = SettingsConfigDict(env_prefix='DUCKDB_')

    database: str = ':memory:'

    def _adbc_driver_key(self) -> str:
        return 'duckdb'

    @model_validator(mode='after')
    def check_memory_pool_size(self) -> Self:
        if self.database == ':memory:' and self.pool_size > 1:
            raise ValueError(
                'pool_size > 1 with database=":memory:" will give each pool '
                'connection an isolated in-memory database — use pool_size=1 '
                'for in-memory DuckDB, or set database to a file path.'
            )
        return self
```

**Key verified behavior:** `DUCKDB_POOL_SIZE=10` env var populates `DuckDBConfig().pool_size` as `10`. The child class `env_prefix` applies to all fields including those inherited from `BaseWarehouseConfig`. No `Field(alias=...)` hacks needed.

### Pattern 2: WarehouseConfig Protocol

**What:** A `@runtime_checkable Protocol` with the pool tuning field signatures. Exported publicly. Downstream code accepts `config: WarehouseConfig` without importing any concrete class.

**When to use:** Public API type annotations in `create_pool()` and downstream library function signatures.

```python
# Source: verified locally, stdlib typing module
from typing import Protocol, runtime_checkable

@runtime_checkable
class WarehouseConfig(Protocol):
    """Structural type for any adbc-poolhouse warehouse config model.

    Downstream code annotates against this protocol to avoid importing
    concrete config classes.
    """
    pool_size: int
    max_overflow: int
    timeout: int
    recycle: int
```

**Verified:** `isinstance(DuckDBConfig(), WarehouseConfig)` returns `True` at runtime.

### Pattern 3: model_validator for Cross-Field Validation

**What:** `@model_validator(mode='after')` checks cross-field conditions after all individual fields are validated. Raises `ValueError` which pydantic wraps in `ValidationError`.

**When to use:** CFG-02 (DuckDB in-memory pool_size check), CFG-04 (Snowflake private key mutual exclusion), any future "these two fields cannot both be set" rule.

```python
# Source: verified locally against pydantic 2.12.5
from pydantic import model_validator
from typing_extensions import Self

@model_validator(mode='after')
def check_private_key_exclusion(self) -> Self:
    if self.private_key_path is not None and self.private_key_pem is not None:
        raise ValueError(
            'Provide only one of private_key_path (file path to PKCS1/PKCS8 key) '
            'or private_key_pem (PEM-encoded key content), not both. '
            'Use private_key_path for a key file, or private_key_pem for inline PEM.'
        )
    return self
```

**Note:** The `ValueError` raised inside a `model_validator` is NOT a plain Python `ValueError` to callers — pydantic catches it and re-wraps into `ValidationError`. This is correct behavior per the locked decisions.

### Pattern 4: SecretStr for Sensitive Fields

**What:** `pydantic.SecretStr` type masks sensitive values in `repr()` and `model_dump()`. Env var loading works transparently — pydantic-settings wraps the string value in `SecretStr` automatically.

**When to use:** All passwords, tokens, private key PEM content, OAuth client secrets. NOT for paths (use `Path` for `private_key_path`).

```python
# Source: verified locally
from pydantic import SecretStr
from pathlib import Path

class SnowflakeConfig(BaseWarehouseConfig):
    model_config = SettingsConfigDict(env_prefix='SNOWFLAKE_')

    account: str
    user: str | None = None
    password: SecretStr | None = None
    private_key_path: Path | None = None        # file path — NOT SecretStr
    private_key_pem: SecretStr | None = None    # PEM content — IS SecretStr
    private_key_passphrase: SecretStr | None = None
    # ... auth_type, warehouse, database, schema, role etc.
```

**Verified:** `SNOWFLAKE_PASSWORD=supersecret` → `config.password` is `SecretStr('**********')` in repr, `get_secret_value()` returns the real value.

### Anti-Patterns to Avoid

- **Nested composition for pool fields:** Don't put pool fields in a nested `PoolConfig` sub-model. Flat layout means `DUCKDB_POOL_SIZE` works naturally; nested would require `env_nested_delimiter='__'` and `DUCKDB_POOL__POOL_SIZE` syntax.
- **Single `private_key: str` field for Snowflake:** Ambiguous between file path and PEM content. Always use two typed fields with mutual exclusivity validator.
- **Catching and re-raising `ValidationError` as plain `ValueError`:** The locked decision requires letting `ValidationError` bubble. Don't `try/except ValidationError: raise ValueError(...)`.
- **`extra='forbid'` on base class:** Will break concrete subclasses if pydantic tries to validate child-only fields through the base. Use `extra='ignore'` or omit (default is 'ignore').
- **Declaring `model_config` on `BaseWarehouseConfig`:** Base should have no `env_prefix` — only concrete classes define their prefix. If base has an `env_prefix`, it would pollute the concrete class's prefix resolution.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Env var loading | Custom `os.environ.get()` chains | `pydantic-settings` `BaseSettings` | Type coercion, `.env` file support, Secret masking, nested parsing — all built-in |
| Secret masking in logs/repr | Custom `__repr__` overrides | `pydantic.SecretStr` | Handles `repr`, `str`, `model_dump`, JSON serialization modes correctly |
| Cross-field validation | Manual checks in `__init__` | `@model_validator(mode='after')` | Integrated with Pydantic's validation pipeline; errors appear in `ValidationError.errors()` with location paths |
| Abstract base enforcement | `raise TypeError` in `__init__` | `abc.ABC` + `@abc.abstractmethod` | Standard Python mechanism; IDEs recognize it; mypy/pyright understand it |
| Structural typing | Concrete class unions | `typing.Protocol` + `@runtime_checkable` | Open to new backends without changing signatures; `isinstance()` works at runtime |

---

## ADBC Driver Connection Parameters Reference

This section documents the verified field sets for each warehouse backend. Used by planner to define exact fields in each config class.

### DuckDB (CFG-01, CFG-02)

**Driver:** `adbc_driver_duckdb` (bundled in `duckdb>=0.9.1`)
**env_prefix:** `DUCKDB_`
**Source:** https://duckdb.org/docs/stable/clients/adbc.html, https://arrow.apache.org/adbc/current/driver/duckdb.html

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `database` | `str` | `':memory:'` | `DUCKDB_DATABASE` | File path or `:memory:`. ADBC docs use `path`; consumer-facing alias `database` is more intuitive |
| `read_only` | `bool` | `False` | `DUCKDB_READ_ONLY` | Open database in read-only mode |
| (pool fields) | — | — | `DUCKDB_POOL_SIZE` etc. | Inherited from `BaseWarehouseConfig` |

**Validator required:** `database=':memory:'` + `pool_size > 1` → `ValueError` (CFG-02)

### Snowflake (CFG-03, CFG-04)

**Driver:** `adbc-driver-snowflake>=1.0.0`
**env_prefix:** `SNOWFLAKE_`
**Source:** https://arrow.apache.org/adbc/current/driver/snowflake.html

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `account` | `str` | required | `SNOWFLAKE_ACCOUNT` | e.g. `foobar` from `https://foobar.snowflakecomputing.com` |
| `user` | `str \| None` | `None` | `SNOWFLAKE_USER` | Required for most auth types |
| `password` | `SecretStr \| None` | `None` | `SNOWFLAKE_PASSWORD` | |
| `auth_type` | `str \| None` | `None` | `SNOWFLAKE_AUTH_TYPE` | `auth_jwt`, `auth_ext_browser`, `auth_oauth`, `auth_mfa`, `auth_okta`, `auth_pat`, `auth_wif` |
| `private_key_path` | `Path \| None` | `None` | `SNOWFLAKE_PRIVATE_KEY_PATH` | PKCS1 private key file path |
| `private_key_pem` | `SecretStr \| None` | `None` | `SNOWFLAKE_PRIVATE_KEY_PEM` | PKCS8 key value (encrypted or unencrypted) |
| `private_key_passphrase` | `SecretStr \| None` | `None` | `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Decryption passcode for encrypted PKCS8 key |
| `jwt_expire_timeout` | `str \| None` | `None` | `SNOWFLAKE_JWT_EXPIRE_TIMEOUT` | Duration string e.g. `"300ms"`, `"1m30s"` |
| `oauth_token` | `SecretStr \| None` | `None` | `SNOWFLAKE_OAUTH_TOKEN` | For `auth_oauth` |
| `okta_url` | `str \| None` | `None` | `SNOWFLAKE_OKTA_URL` | Required for `auth_okta` |
| `identity_provider` | `str \| None` | `None` | `SNOWFLAKE_IDENTITY_PROVIDER` | For `auth_wif` |
| `database` | `str \| None` | `None` | `SNOWFLAKE_DATABASE` | Default database |
| `schema_` | `str \| None` | `None` | `SNOWFLAKE_SCHEMA` | Default schema (field named `schema_` to avoid Python keyword conflict) |
| `warehouse` | `str \| None` | `None` | `SNOWFLAKE_WAREHOUSE` | Warehouse selection |
| `role` | `str \| None` | `None` | `SNOWFLAKE_ROLE` | Authentication role |
| `region` | `str \| None` | `None` | `SNOWFLAKE_REGION` | Snowflake region |
| `host` | `str \| None` | `None` | `SNOWFLAKE_HOST` | Explicit host (alternative to account-based URI) |
| `port` | `int \| None` | `None` | `SNOWFLAKE_PORT` | Connection port |
| `protocol` | `str \| None` | `None` | `SNOWFLAKE_PROTOCOL` | `http` or `https` |
| `login_timeout` | `str \| None` | `None` | `SNOWFLAKE_LOGIN_TIMEOUT` | Login retry timeout |
| `request_timeout` | `str \| None` | `None` | `SNOWFLAKE_REQUEST_TIMEOUT` | Request retry timeout |
| `client_timeout` | `str \| None` | `None` | `SNOWFLAKE_CLIENT_TIMEOUT` | Network roundtrip timeout |
| `tls_skip_verify` | `bool` | `False` | `SNOWFLAKE_TLS_SKIP_VERIFY` | Disable TLS certificate verification |
| `ocsp_fail_open_mode` | `bool` | `True` | `SNOWFLAKE_OCSP_FAIL_OPEN_MODE` | OCSP fail open |
| `keep_session_alive` | `bool` | `False` | `SNOWFLAKE_KEEP_SESSION_ALIVE` | Session persistence |
| `app_name` | `str \| None` | `None` | `SNOWFLAKE_APP_NAME` | Application identifier |
| `disable_telemetry` | `bool` | `False` | `SNOWFLAKE_DISABLE_TELEMETRY` | Disable usage telemetry |
| `cache_mfa_token` | `bool` | `False` | `SNOWFLAKE_CACHE_MFA_TOKEN` | MFA token caching |
| `store_temp_creds` | `bool` | `False` | `SNOWFLAKE_STORE_TEMP_CREDS` | ID token caching |

**Validator required:** `private_key_path` and `private_key_pem` mutually exclusive (CFG-04)

**Note on `schema_`:** Python keyword `schema` must be avoided as a field name. Use `schema_` as the Python attribute with `alias='schema'` or use a `Field(alias='schema')` if needed for serialization compatibility. The env var will be `SNOWFLAKE_SCHEMA_` (with underscore) unless an alias is used — confirm via testing.

### PostgreSQL (CFG-05)

**Driver:** `adbc-driver-postgresql>=1.0.0`
**env_prefix:** `POSTGRESQL_`
**Source:** https://arrow.apache.org/adbc/current/driver/postgresql.html

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `uri` | `str \| None` | `None` | `POSTGRESQL_URI` | Primary connection method: `postgresql://user:pass@host:5432/dbname` |
| `use_copy` | `bool` | `True` | `POSTGRESQL_USE_COPY` | Use PostgreSQL COPY for query execution (driver optimization) |

**Note:** The PostgreSQL ADBC driver wraps libpq — all connection parameters can be specified in the URI following libpq connection string format. Individual host/port/user/password fields are libpq parameters embedded in the URI rather than top-level driver options.

### BigQuery (CFG-05)

**Driver:** `adbc-driver-bigquery>=1.3.0`
**env_prefix:** `BIGQUERY_`
**Source:** https://github.com/apache/arrow-adbc/blob/main/python/adbc_driver_bigquery/adbc_driver_bigquery/__init__.py

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `auth_type` | `str \| None` | `None` | `BIGQUERY_AUTH_TYPE` | `bigquery` (SDK default), `json_credential_file`, `json_credential_string`, `user_authentication` |
| `auth_credentials` | `SecretStr \| None` | `None` | `BIGQUERY_AUTH_CREDENTIALS` | JSON credentials file path or encoded string |
| `auth_client_id` | `str \| None` | `None` | `BIGQUERY_AUTH_CLIENT_ID` | OAuth client ID |
| `auth_client_secret` | `SecretStr \| None` | `None` | `BIGQUERY_AUTH_CLIENT_SECRET` | OAuth client secret |
| `auth_refresh_token` | `SecretStr \| None` | `None` | `BIGQUERY_AUTH_REFRESH_TOKEN` | OAuth refresh token |
| `project_id` | `str \| None` | `None` | `BIGQUERY_PROJECT_ID` | GCP project ID |
| `dataset_id` | `str \| None` | `None` | `BIGQUERY_DATASET_ID` | Default dataset |

### FlightSQL (CFG-05)

**Driver:** `adbc-driver-flightsql>=1.0.0`
**env_prefix:** `FLIGHTSQL_`
**Source:** https://arrow.apache.org/adbc/current/driver/flight_sql.html

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `uri` | `str` | required | `FLIGHTSQL_URI` | `grpc://host:port` or `grpc+tls://host:port` |
| `username` | `str \| None` | `None` | `FLIGHTSQL_USERNAME` | HTTP-style basic auth |
| `password` | `SecretStr \| None` | `None` | `FLIGHTSQL_PASSWORD` | HTTP-style basic auth |
| `authorization_header` | `SecretStr \| None` | `None` | `FLIGHTSQL_AUTHORIZATION_HEADER` | Custom auth header value |
| `mtls_cert_chain` | `str \| None` | `None` | `FLIGHTSQL_MTLS_CERT_CHAIN` | mTLS certificate chain |
| `mtls_private_key` | `SecretStr \| None` | `None` | `FLIGHTSQL_MTLS_PRIVATE_KEY` | mTLS private key |
| `tls_root_certs` | `str \| None` | `None` | `FLIGHTSQL_TLS_ROOT_CERTS` | Root certificates |
| `tls_skip_verify` | `bool` | `False` | `FLIGHTSQL_TLS_SKIP_VERIFY` | Disable TLS cert verification |
| `tls_override_hostname` | `str \| None` | `None` | `FLIGHTSQL_TLS_OVERRIDE_HOSTNAME` | Override TLS hostname |
| `connect_timeout` | `float \| None` | `None` | `FLIGHTSQL_CONNECT_TIMEOUT` | Connection timeout in seconds |
| `query_timeout` | `float \| None` | `None` | `FLIGHTSQL_QUERY_TIMEOUT` | Query timeout in seconds |
| `fetch_timeout` | `float \| None` | `None` | `FLIGHTSQL_FETCH_TIMEOUT` | Fetch timeout in seconds |
| `update_timeout` | `float \| None` | `None` | `FLIGHTSQL_UPDATE_TIMEOUT` | Update timeout in seconds |
| `authority` | `str \| None` | `None` | `FLIGHTSQL_AUTHORITY` | Override gRPC authority |
| `max_msg_size` | `int \| None` | `None` | `FLIGHTSQL_MAX_MSG_SIZE` | Max gRPC message size (driver default: 16 MiB) |
| `with_cookie_middleware` | `bool` | `False` | `FLIGHTSQL_WITH_COOKIE_MIDDLEWARE` | Enable cookie middleware |

### Databricks (CFG-06)

**Driver:** Columnar ADBC driver (Foundry-distributed, not on PyPI)
**env_prefix:** `DATABRICKS_`
**Source:** https://docs.adbc-drivers.org/drivers/databricks, columnar ADBC quickstarts

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `uri` | `SecretStr \| None` | `None` | `DATABRICKS_URI` | Full URI: `databricks://token:<token>@<host>:443/<http-path>` (PAT auth) or with OAuth params |
| `host` | `str \| None` | `None` | `DATABRICKS_HOST` | Workspace hostname (alternative to URI components) |
| `http_path` | `str \| None` | `None` | `DATABRICKS_HTTP_PATH` | SQL warehouse HTTP path |
| `token` | `SecretStr \| None` | `None` | `DATABRICKS_TOKEN` | Personal access token for PAT auth |
| `auth_type` | `str \| None` | `None` | `DATABRICKS_AUTH_TYPE` | `OAuthU2M`, `OAuthM2M` |
| `client_id` | `str \| None` | `None` | `DATABRICKS_CLIENT_ID` | OAuth M2M client ID |
| `client_secret` | `SecretStr \| None` | `None` | `DATABRICKS_CLIENT_SECRET` | OAuth M2M client secret |
| `catalog` | `str \| None` | `None` | `DATABRICKS_CATALOG` | Default Unity Catalog |
| `schema_` | `str \| None` | `None` | `DATABRICKS_SCHEMA` | Default schema |

**Confidence:** MEDIUM. URI format verified from docs.adbc-drivers.org. Host/token/http_path field decomposition is triangulated from environment variable conventions in the Databricks ecosystem. Driver version v0.1.2 is documented.

### Redshift (CFG-06)

**Driver:** Columnar ADBC driver (Foundry-distributed, not on PyPI)
**env_prefix:** `REDSHIFT_`
**Source:** https://docs.adbc-drivers.org/drivers/redshift

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `uri` | `str` | required | `REDSHIFT_URI` | `redshift://[user:password@]host[:port]/dbname[?params]` or `redshift:///dbname` for endpoint discovery |
| `cluster_type` | `str \| None` | `None` | `REDSHIFT_CLUSTER_TYPE` | `redshift`, `redshift-iam`, `redshift-serverless` |
| `cluster_identifier` | `str \| None` | `None` | `REDSHIFT_CLUSTER_IDENTIFIER` | Provisioned cluster identifier (for IAM mode) |
| `workgroup_name` | `str \| None` | `None` | `REDSHIFT_WORKGROUP_NAME` | Serverless workgroup name |
| `aws_region` | `str \| None` | `None` | `REDSHIFT_AWS_REGION` | AWS region e.g. `us-west-1` |
| `aws_access_key_id` | `str \| None` | `None` | `REDSHIFT_AWS_ACCESS_KEY_ID` | IAM access key |
| `aws_secret_access_key` | `SecretStr \| None` | `None` | `REDSHIFT_AWS_SECRET_ACCESS_KEY` | IAM secret key |
| `sslmode` | `str \| None` | `None` | `REDSHIFT_SSLMODE` | SSL configuration |

### Trino (CFG-06)

**Driver:** Columnar ADBC driver (Foundry-distributed, not on PyPI)
**env_prefix:** `TRINO_`
**Source:** https://docs.adbc-drivers.org/drivers/trino

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `uri` | `str` | required | `TRINO_URI` | `trino://[user[:password]@]host[:port][/catalog[/schema]][?params]` |
| `host` | `str \| None` | `None` | `TRINO_HOST` | Host (alternative if not using full URI) |
| `port` | `int \| None` | `None` | `TRINO_PORT` | Default 8080 (HTTP) or 8443 (HTTPS) |
| `user` | `str \| None` | `None` | `TRINO_USER` | Username |
| `password` | `SecretStr \| None` | `None` | `TRINO_PASSWORD` | Password (HTTPS only) |
| `catalog` | `str \| None` | `None` | `TRINO_CATALOG` | Default catalog |
| `schema_` | `str \| None` | `None` | `TRINO_SCHEMA` | Default schema |
| `ssl` | `bool` | `True` | `TRINO_SSL` | Use HTTPS |
| `ssl_verify` | `bool` | `True` | `TRINO_SSL_VERIFY` | Verify SSL certificate |
| `source` | `str \| None` | `None` | `TRINO_SOURCE` | Application identifier |

### MSSQL (CFG-06)

**Driver:** Columnar ADBC driver (Foundry-distributed, not on PyPI)
**env_prefix:** `MSSQL_`
**Source:** https://docs.adbc-drivers.org/drivers/mssql, https://deepwiki.com/columnar-tech/adbc-quickstarts/4.1-microsoft-sql-server

**Note:** Per CONTEXT.md decision, one class covers SQL Server, Azure SQL, Azure Fabric, and Synapse Analytics via optional variant-specific fields.

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `uri` | `str \| None` | `None` | `MSSQL_URI` | `mssql://user:pass@host[:port][/instance][?params]` or `sqlserver://...` |
| `host` | `str \| None` | `None` | `MSSQL_HOST` | Hostname or IP |
| `port` | `int \| None` | `None` | `MSSQL_PORT` | Default 1433 |
| `instance` | `str \| None` | `None` | `MSSQL_INSTANCE` | SQL Server named instance e.g. `SQLExpress` |
| `user` | `str \| None` | `None` | `MSSQL_USER` | SQL auth username |
| `password` | `SecretStr \| None` | `None` | `MSSQL_PASSWORD` | SQL auth password |
| `database` | `str \| None` | `None` | `MSSQL_DATABASE` | Target database |
| `trust_server_certificate` | `bool` | `False` | `MSSQL_TRUST_SERVER_CERTIFICATE` | Accept self-signed certs |
| `connection_timeout` | `int \| None` | `None` | `MSSQL_CONNECTION_TIMEOUT` | Connection timeout seconds |
| `fedauth` | `str \| None` | `None` | `MSSQL_FEDAUTH` | EntraID/Azure AD federated auth method |

### Teradata (CFG-06)

**Driver:** Columnar ADBC driver (Foundry-distributed, not on PyPI)
**env_prefix:** `TERADATA_`
**Source:** Teradata JDBC docs (triangulated — docs.adbc-drivers.org/drivers/teradata returned 404)

**Confidence: LOW** — Teradata ADBC driver documentation page was not reachable. Fields below are triangulated from Teradata JDBC/ODBC docs and the teradatasql Python driver parameter names, which the Columnar driver is likely to mirror. Each field MUST have a docstring note indicating this source uncertainty.

| Field | Python Type | Default | Env Var | Notes |
|-------|-------------|---------|---------|-------|
| `host` | `str` | required | `TERADATA_HOST` | Teradata server hostname |
| `user` | `str \| None` | `None` | `TERADATA_USER` | Database username |
| `password` | `SecretStr \| None` | `None` | `TERADATA_PASSWORD` | Database password |
| `database` | `str \| None` | `None` | `TERADATA_DATABASE` | Default database |
| `port` | `int \| None` | `None` | `TERADATA_PORT` | Default 1025 |
| `logmech` | `str \| None` | `None` | `TERADATA_LOGMECH` | Logon mechanism: `TD2`, `LDAP`, `KRB5`, `TDNEGO` |
| `tmode` | `str \| None` | `None` | `TERADATA_TMODE` | Transaction mode: `ANSI`, `TERA` |
| `sslmode` | `str \| None` | `None` | `TERADATA_SSLMODE` | SSL mode: `DISABLE`, `ALLOW`, `PREFER`, `REQUIRE`, `VERIFY-CA`, `VERIFY-FULL` |
| `uri` | `str \| None` | `None` | `TERADATA_URI` | Full URI if driver supports URI-based connection |

**Docstring note required on each field:** "Source: Triangulated from Teradata JDBC/teradatasql driver docs — Columnar ADBC driver docs unavailable at research time. Verify against installed driver."

---

## Common Pitfalls

### Pitfall 1: `schema` Python Keyword Collision

**What goes wrong:** Using `schema` as a field name causes `SyntaxError` or shadowing Pydantic's own `model_json_schema` method.

**Why it happens:** `schema` is not a Python reserved word but IS a special name in Pydantic v1 that caused conflicts; in v2 it's `model_json_schema`. However naming a field `schema` directly can still surprise IDE tools and linters.

**How to avoid:** Name the field `schema_` and use `Field(alias='schema', validation_alias='schema')` if the ADBC driver kwarg must be literally `schema`. The env var `SNOWFLAKE_SCHEMA` will still work via validation_alias.

**Warning signs:** Linter warnings about shadowing; mypy errors about field name conflicts.

### Pitfall 2: env_prefix on BaseWarehouseConfig

**What goes wrong:** If `model_config = SettingsConfigDict(env_prefix='...')` is set on `BaseWarehouseConfig`, child class prefixes may not behave as expected for pool tuning fields.

**Why it happens:** Child `model_config` merges with parent `model_config`. If base has an `env_prefix`, child class env_prefix does NOT fully override it — the behavior depends on MRO resolution.

**How to avoid:** Do NOT set `env_prefix` on `BaseWarehouseConfig`. Only concrete subclasses define their prefix. Verified: child `env_prefix` alone is sufficient for all fields including inherited ones.

**Warning signs:** `POOL_SIZE` (no prefix) populates `pool_size` when you expected `DUCKDB_POOL_SIZE` to be required.

### Pitfall 3: SecretStr in model_dump Serialization

**What goes wrong:** `model_dump(mode='json')` serializes `SecretStr` as `'**********'` (masked), not the real value. ADBC driver kwargs builders in Phase 4 will receive the masked string.

**Why it happens:** This is intentional pydantic behavior, but Phase 4 translators must call `.get_secret_value()` on `SecretStr` fields.

**How to avoid:** Phase 4 translators must detect `SecretStr` fields and call `.get_secret_value()`. Phase 3 configs are correctly designed — this is a Phase 4 concern to document as a known handoff point.

**Warning signs:** ADBC driver auth fails with `'**********'` as the password value.

### Pitfall 4: ValidationError vs ValueError in model_validator

**What goes wrong:** Code calling `DuckDBConfig(database=':memory:', pool_size=2)` catches `ValueError` but never fires — the actual exception type is `ValidationError`.

**Why it happens:** Pydantic wraps `ValueError` raised in validators into `ValidationError`. This is correct per the locked decisions, but test code must `pytest.raises(ValidationError)` not `pytest.raises(ValueError)`.

**How to avoid:** Unit tests use `from pydantic import ValidationError` and `pytest.raises(ValidationError)`. README/docstring on each validator notes "raises `ValidationError`."

**Warning signs:** `pytest.raises(ValueError)` test passes when it should catch `ValidationError`.

### Pitfall 5: Teradata Driver Documentation Gap

**What goes wrong:** TeradataConfig fields are implemented based on JDBC/teradatasql docs, but the Columnar ADBC driver may use different parameter names.

**Why it happens:** docs.adbc-drivers.org/drivers/teradata returned 404 at research time. The driver is new (Columnar launched Oct 2025).

**How to avoid:** Each `TeradataConfig` field should have a docstring noting the source. When the Columnar driver is installed in a test environment, verify field names against driver errors. Consider adding a `# TODO(teradata): verify field names against installed driver` comment in the implementation.

**Warning signs:** Translator fails with "unknown option" errors for Teradata fields.

---

## Code Examples

Verified patterns from official sources and local testing:

### BaseWarehouseConfig + Concrete Subclass

```python
# Source: verified locally, pydantic-settings 2.13.1 + pydantic 2.12.5
import abc
from typing import Protocol, runtime_checkable
from typing_extensions import Self
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@runtime_checkable
class WarehouseConfig(Protocol):
    pool_size: int
    max_overflow: int
    timeout: int
    recycle: int


class BaseWarehouseConfig(BaseSettings, abc.ABC):
    pool_size: int = 5
    max_overflow: int = 3
    timeout: int = 30
    recycle: int = 3600

    @abc.abstractmethod
    def _adbc_driver_key(self) -> str:
        ...


class DuckDBConfig(BaseWarehouseConfig):
    model_config = SettingsConfigDict(env_prefix='DUCKDB_')
    database: str = ':memory:'
    read_only: bool = False

    def _adbc_driver_key(self) -> str:
        return 'duckdb'

    @model_validator(mode='after')
    def check_memory_pool_size(self) -> Self:
        if self.database == ':memory:' and self.pool_size > 1:
            raise ValueError(
                'pool_size > 1 with database=":memory:" will give each pool '
                'connection an isolated in-memory database (each connection '
                'sees a different empty DB). Use pool_size=1 for in-memory '
                'DuckDB, or set database to a file path for shared state.'
            )
        return self
```

### Snowflake with Mutual Exclusion

```python
# Source: verified locally, pydantic 2.12.5
from pathlib import Path
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


class SnowflakeConfig(BaseWarehouseConfig):
    model_config = SettingsConfigDict(env_prefix='SNOWFLAKE_')

    account: str
    user: str | None = None
    password: SecretStr | None = None
    private_key_path: Path | None = None
    private_key_pem: SecretStr | None = None
    private_key_passphrase: SecretStr | None = None

    def _adbc_driver_key(self) -> str:
        return 'snowflake'

    @model_validator(mode='after')
    def check_private_key_exclusion(self) -> Self:
        if self.private_key_path is not None and self.private_key_pem is not None:
            raise ValueError(
                'Provide only one of private_key_path (path to a PKCS1/PKCS8 '
                'private key file) or private_key_pem (inline PEM-encoded key '
                'content), not both. Use private_key_path for a key file, or '
                'private_key_pem for inline PEM content.'
            )
        return self
```

### Unit Test Pattern (TEST-04)

```python
# Source: pytest patterns for pydantic-settings
import os
import pytest
from pydantic import ValidationError
from adbc_poolhouse import DuckDBConfig, SnowflakeConfig


class TestDuckDBConfig:
    def test_default_construction(self):
        d = DuckDBConfig()
        assert d.database == ':memory:'
        assert d.pool_size == 5

    def test_memory_pool_size_validator(self):
        with pytest.raises(ValidationError, match='pool_size > 1'):
            DuckDBConfig(database=':memory:', pool_size=2)

    def test_memory_pool_size_1_valid(self):
        d = DuckDBConfig(database=':memory:', pool_size=1)
        assert d.pool_size == 1

    def test_file_database_pool_size_2_valid(self):
        d = DuckDBConfig(database='/tmp/test.duckdb', pool_size=2)
        assert d.pool_size == 2

    def test_env_prefix_isolation(self, monkeypatch):
        monkeypatch.setenv('DUCKDB_POOL_SIZE', '8')
        monkeypatch.setenv('SNOWFLAKE_POOL_SIZE', '3')  # should NOT affect DuckDB
        d = DuckDBConfig()
        assert d.pool_size == 8

    def test_env_prefix_pool_tuning(self, monkeypatch):
        monkeypatch.setenv('DUCKDB_POOL_SIZE', '10')
        monkeypatch.setenv('DUCKDB_MAX_OVERFLOW', '5')
        d = DuckDBConfig()
        assert d.pool_size == 10
        assert d.max_overflow == 5


class TestSnowflakeConfig:
    def test_private_key_mutual_exclusion(self):
        from pathlib import Path
        with pytest.raises(ValidationError, match='private_key_path'):
            SnowflakeConfig(
                account='myaccount',
                private_key_path=Path('/tmp/key.p8'),
                private_key_pem='-----BEGIN PRIVATE KEY-----',
            )

    def test_secret_str_not_exposed(self, monkeypatch):
        monkeypatch.setenv('SNOWFLAKE_ACCOUNT', 'myaccount')
        monkeypatch.setenv('SNOWFLAKE_PASSWORD', 'supersecret')
        s = SnowflakeConfig()
        assert 'supersecret' not in repr(s)
        assert s.password.get_secret_value() == 'supersecret'
```

### Public __init__.py Pattern

```python
# src/adbc_poolhouse/__init__.py
"""Connection pooling for ADBC drivers from typed warehouse configs."""

from adbc_poolhouse._base_config import BaseWarehouseConfig, WarehouseConfig
from adbc_poolhouse._duckdb_config import DuckDBConfig
from adbc_poolhouse._snowflake_config import SnowflakeConfig
from adbc_poolhouse._bigquery_config import BigQueryConfig
from adbc_poolhouse._postgresql_config import PostgreSQLConfig
from adbc_poolhouse._flightsql_config import FlightSQLConfig
from adbc_poolhouse._databricks_config import DatabricksConfig
from adbc_poolhouse._redshift_config import RedshiftConfig
from adbc_poolhouse._trino_config import TrinoConfig
from adbc_poolhouse._mssql_config import MSSQLConfig
from adbc_poolhouse._teradata_config import TeradataConfig

__all__ = [
    'WarehouseConfig',
    'BaseWarehouseConfig',
    'DuckDBConfig',
    'SnowflakeConfig',
    'BigQueryConfig',
    'PostgreSQLConfig',
    'FlightSQLConfig',
    'DatabricksConfig',
    'RedshiftConfig',
    'TrinoConfig',
    'MSSQLConfig',
    'TeradataConfig',
]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pydantic v1 `BaseSettings` in pydantic itself | pydantic-settings separate package | pydantic v2 (2023) | Must install `pydantic-settings` separately — already in project deps |
| v1 `class Config:` inner class | v2 `model_config = SettingsConfigDict(...)` | pydantic v2 | Affects how `env_prefix` is declared; no more `class Config` |
| v1 `@validator` | v2 `@field_validator` / `@model_validator` | pydantic v2 | `@model_validator(mode='after')` replaces `@validator(..., always=True)` |
| v1 `@root_validator` | v2 `@model_validator(mode='before'/'after'/'wrap')` | pydantic v2 | Different import, different signature |

**Deprecated/outdated:**
- `class Config:` inner class: replaced by `model_config = SettingsConfigDict(...)` in pydantic-settings v2
- `@root_validator`: replaced by `@model_validator` — do not use in new code

---

## Open Questions

1. **`schema` field naming for Snowflake, Databricks, Trino**
   - What we know: Python linters warn on `schema` as a field name; Pydantic v2 itself uses `model_json_schema`; the ADBC driver kwarg is literally `schema`
   - What's unclear: Does `Field(alias='schema')` cause env var to be read from `SNOWFLAKE_SCHEMA` or `SNOWFLAKE_SCHEMA_`? Need to test.
   - Recommendation: Test `schema_` field with `Field(validation_alias='schema')` — validate env var name in a quick test during Wave 0

2. **TeradataConfig field accuracy**
   - What we know: docs.adbc-drivers.org/drivers/teradata returned 404; fields triangulated from teradatasql/JDBC docs
   - What's unclear: Columnar ADBC Teradata driver may use different parameter names or a URI-based connection pattern like the other Foundry drivers
   - Recommendation: Implement with LOW-confidence fields and add docstring source notes; planner should include a "verify on driver install" note in the TeradataConfig task

3. **`_adbc_driver_key()` abstractmethod design**
   - What we know: Using `@abc.abstractmethod` on a method prevents `BaseWarehouseConfig()` instantiation; tested and confirmed working
   - What's unclear: Whether this internal method creates unwanted exposure in the public API (even with underscore prefix, it appears in `help()`)
   - Recommendation: Accept — the underscore prefix makes the intent clear; document in `BaseWarehouseConfig` docstring as "internal, not part of public API"

---

## Sources

### Primary (HIGH confidence)
- `/pydantic/pydantic-settings` (Context7) — `BaseSettings`, `SettingsConfigDict`, `env_prefix` behavior
- `/pydantic/pydantic` (Context7) — `model_validator`, `SecretStr`, `abc.ABC` integration, `ValidationError`
- https://arrow.apache.org/adbc/current/driver/snowflake.html — Snowflake ADBC parameter set
- https://arrow.apache.org/adbc/current/driver/postgresql.html — PostgreSQL ADBC parameter set
- https://arrow.apache.org/adbc/current/driver/flight_sql.html — FlightSQL ADBC parameter set
- https://github.com/apache/arrow-adbc/blob/main/python/adbc_driver_bigquery/adbc_driver_bigquery/__init__.py — BigQuery ADBC constants
- https://docs.adbc-drivers.org/drivers/databricks — Databricks URI format and auth options
- https://docs.adbc-drivers.org/drivers/redshift — Redshift connection parameters
- https://docs.adbc-drivers.org/drivers/trino — Trino URI format and parameters
- https://docs.adbc-drivers.org/drivers/mssql — MSSQL URI format and auth
- Local verification tests (pydantic-settings 2.13.1, pydantic 2.12.5) — env_prefix inheritance, abstract base, SecretStr, model_validator behavior

### Secondary (MEDIUM confidence)
- https://duckdb.org/docs/stable/clients/adbc.html — DuckDB connection options (redirected, sparse on Python-level params)
- https://github.com/pydantic/pydantic-settings/issues/179 — confirmed child class env_prefix behavior (issue closed; behavior confirmed by local test)
- https://deepwiki.com/columnar-tech/adbc-quickstarts/4.1-microsoft-sql-server — MSSQL connection string examples

### Tertiary (LOW confidence)
- Teradata fields: triangulated from teradatasql PyPI driver and JDBC docs — Columnar ADBC docs unavailable (404)
- Databricks `host`/`token`/`http_path` field decomposition: triangulated from Databricks ecosystem conventions; URI format is confirmed, individual field decomposition is inferred

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pydantic-settings is already a runtime dep; behavior verified locally
- Architecture: HIGH — all critical patterns (env_prefix inheritance, abstract base, Protocol) verified with working code
- Apache driver parameters (DuckDB, Snowflake, PostgreSQL, BigQuery, FlightSQL): HIGH — from official ADBC docs
- Foundry driver parameters (Databricks, Redshift, Trino, MSSQL): MEDIUM — from docs.adbc-drivers.org (live docs)
- Teradata parameters: LOW — docs.adbc-drivers.org/drivers/teradata returned 404; fields triangulated
- Pitfalls: HIGH — each pitfall identified from official docs, GitHub issues, or local testing

**Research date:** 2026-02-24
**Valid until:** 2026-05-24 (stable ecosystem — pydantic-settings changes slowly; Foundry drivers are new but field-level changes are unlikely without major version bumps)
