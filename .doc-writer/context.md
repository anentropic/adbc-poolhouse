# Doc Writer Context

**Generated:** 2026-06-29
**Source:** /doc-writer:setup researcher
**Editable:** Yes -- manual edits are preserved until the next --refresh-context run. To make permanent changes, edit config.yaml and re-run setup.

## Project Summary

adbc-poolhouse is a Python library (3.11+) that provides connection pooling for ADBC drivers from typed warehouse configs. The headline contract is "one config in, one pool out": `create_pool(SnowflakeConfig(...))` returns a ready-to-use SQLAlchemy `QueuePool`, where each pooled connection is an ADBC connection cloned from a single source connection. It supports 13 warehouse backends -- BigQuery, DuckDB, FlightSQL, PostgreSQL, Snowflake, SQLite (PyPI drivers), plus ClickHouse, Databricks, MSSQL/Azure SQL/Fabric, MySQL, Redshift, Trino (Foundry-distributed) -- each gated behind a dependency extra, with custom-backend support for drivers without a built-in config class. An **experimental** async surface (`create_async_pool`, `managed_async_pool`, `close_async_pool`) lives behind the `[async]` extra and is loaded lazily (PEP 562) so the sync path stays anyio-free.

Public API (from `__all__`): config classes per backend (`DuckDBConfig`, `SnowflakeConfig`, etc.), the base `WarehouseConfig`/`BaseWarehouseConfig`, sync entry points `create_pool`/`close_pool`/`managed_pool`, lazy async entry points `create_async_pool`/`close_async_pool`/`managed_async_pool`, and exceptions `PoolhouseError`/`ConfigurationError`/`ConnectionBusyError`.

## User Persona: Library authors making ADBC queries

### Profile
- **Skill level:** Expert
- **What they know:** Fluent in Python at expert level. Comfortable with ADBC and its DBAPI/cursor model (connection -> cursor -> execute -> fetch). Strong SQL. Understands warehouse drivers and how to declare optional dependency extras. Do NOT explain Python idioms, context managers, ADBC cursors, or SQL.
- **What to always explain:** Connection-pooling concepts and their trade-offs -- pool size vs. max-overflow, the checkout/checkin connection lifecycle, pre-ping and connection recycling, draining/closing a pool, and specifically *why* pooling matters for ADBC (whose DBAPI ships no pool of its own). Treat pooling as the genuinely new material; everything around it is familiar.
- **Their world:** They build libraries and tools that issue ADBC queries against warehouses and need robust pooling without hand-rolling it. They reach for a typed config and a factory call rather than wiring up SQLAlchemy pool internals themselves. They care about clean public surfaces, predictable lifecycle semantics, and not leaking connections in code that others will depend on.
- **How they found this library:** They already knew ADBC's DBAPI has no built-in pooling and went looking for an existing, maintained solution instead of writing their own pool wrapper.

### Common Tasks
- Create a pool from a typed warehouse config: pass a `SomeConfig(...)` to `create_pool` and get a `QueuePool` back.
- Check connections out and back in: use `pool.connect()` as a context manager to borrow and auto-return a connection.
- Tune pool sizing: choose `pool_size` / `max_overflow` and related knobs for their workload.
- Manage pool lifecycle: drain and close with `close_pool` (or `managed_pool` as a context manager) to release the underlying ADBC source connection.
- Select the right backend extra: install the matching extra (e.g. `[snowflake]`, `[duckdb]`) for their warehouse.
- Optionally use the async surface: reach for `create_async_pool` and friends behind the `[async]` extra (flag as experimental).

### Writing Guidance for This Persona
- When explaining pooling knobs, assume they know what a connection and a cursor are, but spell out what each pool parameter *does* and when to change it.
- Use precise pooling vocabulary (checkout, checkin, overflow, recycle, pre-ping, drain) and define each the first time it appears on a page.
- Examples should reflect library-author concerns: clean creation/teardown, not leaking the source connection, exposing a pool sensibly. DuckDB is the credential-free example backend used across the existing docs.

## User Persona: Application developers building ADBC-backed backends/servers

### Profile
- **Skill level:** Expert
- **What they know:** Expert Python and SQL. Comfortable with ADBC and its DBAPI/cursor model. Experienced at building long-running backend/server applications and at declaring dependency extras. Do NOT explain servers, request lifecycles, Python, ADBC, or SQL.
- **What to always explain:** Pooling intricacies as they apply under load -- pool size vs. max-overflow tuning, per-request checkout/checkin, pre-ping and connection recycling, how the pool behaves under concurrent request load (contention, queueing, overflow exhaustion, timeouts), and tying pool lifecycle to app startup/shutdown.
- **Their world:** They run long-lived backends/servers that query a warehouse under concurrent request load. A pool is shared infrastructure: created once at startup, borrowed per request, drained at shutdown. They care about behaviour under saturation, stale-connection handling, and graceful shutdown.
- **How they found this library:** Building a warehouse-backed server, they hit the need for pooling under load and searched for an ADBC-compatible pool rather than rolling their own.

### Common Tasks
- Create a pool from a typed config at app startup: build the pool once and share it across request handlers.
- Check connections out and back in per request: borrow with `pool.connect()` for the duration of a request.
- Tune pool sizing for concurrency: size `pool_size`/`max_overflow` against expected concurrent requests and warehouse limits.
- Manage pool lifecycle across startup/shutdown: create on boot, drain/close on shutdown (lifespan hooks, `managed_pool`/`managed_async_pool`).
- Use the async surface in async servers: adopt `create_async_pool` and friends in async frameworks (experimental).
- Select the right backend extra: install the extra for their warehouse.

### Writing Guidance for This Persona
- When explaining sizing, frame it around concurrency: what happens when in-flight requests exceed `pool_size`, when overflow is exhausted, and how checkout timeouts surface.
- Emphasize lifecycle tied to process lifetime -- create-at-startup, drain-at-shutdown -- and how `managed_*` context managers fit framework lifespan hooks.
- Examples should show shared-pool-across-requests patterns and graceful shutdown, not one-off scripts. Call out concurrent-load behaviour (pre-ping for stale connections, recycle, `ConnectionBusyError`).

## Use Cases

### Pooling ADBC queries without hand-rolling a pool

**Problem:** ADBC's DBAPI gives you connections but no pool. A library or tool that issues many warehouse queries either opens a fresh connection per query (slow, wasteful, and risky under load) or has to build and maintain its own pooling layer -- connection reuse, sizing, stale-connection detection, teardown -- which is fiddly and easy to get wrong.
**What's possible:** Pass a typed config to `create_pool` and receive a configured SQLAlchemy `QueuePool` whose connections are ADBC connections cloned from one source connection. Connection reuse, overflow, pre-ping, and recycle are handled by the pool. Show the minimal create -> `pool.connect()` -> `close_pool` arc, ideally with DuckDB so it runs with no credentials.
**Outcome:** Queries reuse warehouse connections instead of reconnecting each time; the consumer holds one pool object with predictable checkout/checkin semantics and a single drain-and-close call that releases the underlying ADBC source connection.
**Relevant persona(s):** Library authors making ADBC queries.
**Source:** inferred

### Sizing and lifecycle for a warehouse-backed server under load

**Problem:** A long-running server querying a warehouse must survive concurrent requests without exhausting connections, leaking them, or serving stale ones after the warehouse drops idle connections. Mis-sized pools either throttle throughput or overwhelm the warehouse's connection limit.
**What's possible:** Create the pool once at startup (or via `managed_pool` / `managed_async_pool` tied to a framework's lifespan), check a connection out per request with `pool.connect()`, tune `pool_size`/`max_overflow` for expected concurrency, and rely on pre-ping/recycle to keep connections healthy. Async servers can use the experimental `create_async_pool` surface behind the `[async]` extra.
**Outcome:** The server handles concurrent requests within a bounded connection budget, recovers from stale connections, surfaces saturation predictably (checkout timeouts / `ConnectionBusyError`), and drains cleanly on shutdown.
**Relevant persona(s):** Application developers building ADBC-backed backends/servers.
**Source:** inferred

### Targeting a specific warehouse via the right extra (or a custom backend)

**Problem:** Each warehouse needs its own ADBC driver and connection parameters, and shipping every driver by default would bloat installs. Users need to know which extra to install and how to express their warehouse's credentials in a typed, validated way -- or how to proceed when no built-in config class exists.
**What's possible:** Install the matching extra (e.g. `adbc-poolhouse[snowflake]`), instantiate the corresponding config class (which validates credentials, builds ADBC kwargs, and resolves the driver), and pass it to `create_pool`. For drivers without a built-in class, `create_pool` accepts raw driver arguments directly.
**Outcome:** The user installs only the drivers they need, gets validated configuration with clear errors (`ConfigurationError`), and can still pool a custom or unsupported backend.
**Relevant persona(s):** Both personas.
**Source:** inferred

> These use cases were inferred from persona context and codebase analysis. To promote use cases to a documentation section, run `/doc-writer:setup` and provide explicit use cases.

## Tone: warm-businesslike

### Writing Rules
- Open each page with a brief (1-2 sentence) statement of what it covers and why it matters to the reader.
- Give multiple examples per concept where it helps: a basic case first, then a common variation (e.g. file-backed vs. in-memory, sync vs. async).
- Include "Common Mistakes" or "Troubleshooting" notes where pooling pitfalls are likely (leaked pools, overflow exhaustion, stale connections, forgetting to drain).
- Use transition sentences between major sections so pages read as a flow, not a list of fragments.
- Use admonitions for tips, warnings, and important notes -- including a standing warning that the async surface is experimental.
- Stay warm but professional: no jokes, no first person, no casual asides. Define each pooling term on first use; do not over-explain Python, ADBC, or SQL.

## Framework Preferences: mkdocs-material

### Navigation Strategy
- Strategy: Sections as top tabs (desired target). Note: `mkdocs.yml` currently enables `navigation.sections` (sidebar-only grouping), NOT `navigation.tabs`. The target is to render top-level nav groups (Getting Started, Guides, API Reference, Changelog) as top tabs -- this requires adding `navigation.tabs` to `theme.features`. Treat tabs as flat (no dropdowns), derived from top-level `nav` entries.
- Each tab maps to a section; the sidebar should show only the active section's pages. Section index pages should list their children with a one-sentence abstract each (the `section-index` plugin is already enabled, so a section's index page is the clickable landing page for that group).
- Front page (`index.md`) is linked as "Overview" at the same level as the main sections. Use "Overview" not "Home". (Current nav labels it "Getting Started" -> `index.md`; prefer "Overview".)

### Features to Use
- Admonitions (`admonition`): use `!!! note/tip/warning` for tips, warnings, and important notes. Reserve a `!!! warning` for the experimental async surface. Do not stack multiple admonitions back-to-back.
- Collapsible details (`pymdownx.details`): use `???`/`???+` for long supplementary material (extended troubleshooting, advanced sizing notes) that would otherwise interrupt the main flow.
- Content tabs (`pymdownx.tabbed`, alternate style): use `=== "Label"` to present parallel variants -- sync vs. async, install commands per backend, or per-warehouse config snippets. Keep tabbed content genuinely parallel.
- Code annotations (`content.code.annotate` + `attr_list`/`md_in_html`): attach numbered callouts to lines in code blocks to explain pooling parameters inline. Already enabled in theme features.
- Code copy (`content.code.copy`) and syntax highlighting (`pymdownx.highlight`): always specify a language identifier on fenced blocks (` ```python `, ` ```bash `).
- Cross-references via mkdocstrings: link API symbols with the `[`Name`][adbc_poolhouse.Name]` autoref syntax (as used in existing guides); link between guides with relative `.md` links.

### House style for docstrings (mkdocstrings, Google handler)
- Use **Google-style docstrings** with `Args:` / `Returns:` / `Raises:` sections (the configured `docstring_style: google`, rendered as tables).
- Write docstring bodies in **Markdown, NOT reStructuredText**. Use backtick code spans (`` `create_pool` ``), never RST roles like `:func:` or `:class:` -- RST roles render as stray colons.
- Use `Example:` (singular) for an admonition-boxed, syntax-highlighted fenced ```python block. Use `Examples:` (plural) only for plain `>>>` doctest blocks without the admonition box.
- Public symbols need Google-style docstrings (Args/Returns/Raises); key entry points need an `Example:` block. The build gate is `uv run mkdocs build --strict` (or `.venv/bin/mkdocs build --strict` under sandbox).

### Features NOT to Use
- `navigation.tabs` is the target but not yet enabled -- agents authoring nav should add it deliberately, not assume it is already active.
- Mermaid diagrams (`mermaid` custom fence) are configured but use sparingly -- only where a lifecycle/flow genuinely needs a diagram, not decoratively.
- Do not introduce features absent from `mkdocs.yml` (e.g. `navigation.indexes` beyond the `section-index` plugin's behaviour, footnotes, tasklists, or other pymdownx extensions not listed). If a feature is not in `markdown_extensions` or `theme.features`, do not emit its syntax.
