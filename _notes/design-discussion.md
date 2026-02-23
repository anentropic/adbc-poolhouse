# adbc-poolhouse: Design Discussion Notes

*From dbt-open-sl project initialization, 2026-02-23*

---

## Origin

During initialization of `dbt-open-sl` (an ADBC driver wrapping dbt's semantic layer), we identified that the connection layer — ADBC config translation, driver detection, and connection pooling — is needed by two separate projects:

1. **dbt-open-sl** — translates dbt `profiles.yml` into ADBC connections
2. **Semantic ORM** (planned) — a Django-ORM-like builder for semantic layers, supporting multiple backends

Rather than duplicate this logic, we decided to extract it as a shared library.

---

## What This Library Does

Takes a typed warehouse configuration and returns a pooled ADBC connection.

**One config in, one pool out.**

```
Pydantic warehouse config (e.g. SnowflakeConfig)
  → Parameter translation (config fields → ADBC driver kwargs)
  → Driver detection (PyPI package or Foundry shared lib)
  → SQLAlchemy QueuePool of ADBC dbapi connections
```

## What This Library Does NOT Do

- **No multi-warehouse orchestration** — consumers who need multiple warehouses call `create_pool()` multiple times and manage the dict of pools themselves
- **No query execution** — just gives you a pooled connection. Execution is the consumer's job.
- **No knowledge of dbt** — does not read `profiles.yml` or know about dbt concepts. dbt-open-sl provides its own translation shim from profiles.yml to this lib's config models.

---

## Scope

### In Scope

- **Pydantic BaseSettings models per warehouse type** — SnowflakeConfig, DuckDBConfig, BigQueryConfig, etc. Typed, validated, environment-variable-friendly.
- **Parameter translation** — maps config fields to ADBC driver kwargs (e.g. `SnowflakeConfig.account` → `adbc.snowflake.sql.account`)
- **Driver detection** — tries PyPI package import first (Apache drivers like `adbc_driver_snowflake`), falls back to `adbc_driver_manager` (Foundry drivers like `databricks`)
- **Connection pooling** — SQLAlchemy QueuePool wrapping ADBC dbapi connections. Pre-ping health checks, overflow management, recycle for token expiry.
- **Helpful error messages** — when a required ADBC driver is not installed

### Out of Scope

- Query execution (consumers borrow a connection and execute themselves)
- Multi-pool management (consumers manage multiple pools)
- Any knowledge of dbt, semantic layers, or MetricFlow
- REST/HTTP/Flight SQL serving

---

## How Consumers Use It

### Semantic ORM (direct config)

The ORM uses the Pydantic models directly — they may even be the same models the ORM exposes to its users:

```python
from adbc_poolhouse import SnowflakeConfig, create_pool

config = SnowflakeConfig(account="xy123", warehouse="COMPUTE_WH", ...)
pool = create_pool(config)
```

### dbt-open-sl (profiles.yml shim)

dbt-open-sl reads profiles.yml and translates to the shared lib's config:

```python
from adbc_poolhouse import SnowflakeConfig, create_pool

# dbt-open-sl's own code:
target_config = parse_profiles_yml(project_dir, target)
config = translate_to_poolhouse_config(target_config)  # dict → SnowflakeConfig
pool = create_pool(config)
```

---

## Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| Pydantic BaseSettings for config | Typed, validated, env-var support comes free, familiar to Python devs |
| SQLAlchemy QueuePool (not hand-rolled) | Battle-tested, thread-safe, handles pre-ping/overflow/recycle/events. Only imports `sqlalchemy.pool` + `sqlalchemy.event`, not the ORM |
| One pool per call, no multi-warehouse | Keep the lib simple. Multi-warehouse routing is consumer business logic |
| Config + pool only, no execution | Execution semantics differ per consumer. Pool gives you a connection, you decide what to do with it |
| Support both PyPI and Foundry drivers | Apache ADBC drivers install via pip, Foundry drivers via `dbc` CLI. Both load through `adbc_driver_manager` |

---

## Warehouse Coverage

Based on the ADBC Driver Foundry (launched Oct 2025) and Apache Arrow ADBC:

| Warehouse | Driver Source | Install | Priority |
|-----------|--------------|---------|----------|
| DuckDB | Apache (built-in) | `pip install duckdb` | v1 (testing) |
| Snowflake | Apache | `pip install adbc-driver-snowflake` | v1 (production) |
| BigQuery | Apache + Foundry | `pip install adbc-driver-bigquery` | Future |
| PostgreSQL | Apache | `pip install adbc-driver-postgresql` | Future |
| Databricks | Foundry | `dbc install databricks` | Future |
| Redshift | Foundry | `dbc install redshift` | Future |
| Trino | Foundry | `dbc install trino` | Future |
| MSSQL/Fabric/Synapse | Foundry | `dbc install mssql` | Future |
| Spark | Apache (Flight SQL) | `pip install adbc-driver-flightsql` | Future |
| Teradata | Foundry | `dbc install teradata` | Future |

v1 targets DuckDB (dev/test) and Snowflake (first production target). Architecture supports all others — adding a warehouse is adding one config model and one translator function.

---

## Pool Configuration

Default pool settings (configurable by consumer):

| Setting | Default | Purpose |
|---------|---------|---------|
| `pool_size` | 5 | Steady-state idle connections |
| `max_overflow` | 3 | Burst capacity above pool_size |
| `timeout` | 30s | Wait time when all connections busy |
| `pool_pre_ping` | True | Health check before checkout (catches stale sessions) |
| `recycle` | 3600s | Recreate connections older than 1hr (prevents token expiry) |

---

## Technical Details

Detailed connection layer design (warehouse-specific parameter translation, auth method mapping, private key handling, error handling, testing strategy) is documented in:

- `dbt-open-sl/_notes/dbt-open-sl-connection-layer.md`

That document was written before the extraction decision, so it includes dbt-specific concerns (profiles.yml reading, Jinja rendering) that belong in dbt-open-sl, not this shared lib. The ADBC parameter translation and pool management sections are directly applicable.

---

## Quality Requirements

From the dbt-open-sl discussion — the author cares about:

- Thorough test coverage
- Idiomatic, Pythonic interfaces
- Strongly-typed modern Python (basedpyright strict mode)
- High quality documentation
- Good developer experience for library consumers
- Apache 2.0 license

---

## Naming

Working name: `adbc-poolhouse` (package name TBD during project initialization).
