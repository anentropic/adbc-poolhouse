# Quick Task 10: Rewrite integration tests to use pool API - Context

**Gathered:** 2026-03-07
**Status:** Ready for planning

<domain>
## Task Boundary

Rewrite integration tests to exercise adbc-poolhouse's pool API (create_pool/close_pool) instead of raw adbc_driver connections, and wire up the conftest fixtures that are currently unused.

</domain>

<decisions>
## Implementation Decisions

### Cassette replay compatibility
- Extending pytest-adbc-replay to support adbc_clone() on ReplayConnection
- Requirements doc written to ../pytest-adbc-replay/_notes/pool-clone-support.md
- Pool-based integration tests will use cassettes and run in CI via replay
- Tests will be broken until pytest-adbc-replay adds adbc_clone() support — that's expected

### Test structure
- Integration tests should use pool fixtures from conftest.py
- Tests exercise create_pool → pool.connect() → cursor.execute() → close_pool
- Cassette recording/replay works through the auto-patched connect() + new adbc_clone()

### Claude's Discretion
- Exact test assertions and structure

</decisions>

<specifics>
## Specific Ideas

- conftest.py already has session-scoped snowflake_pool and databricks_pool fixtures using create_pool/close_pool
- Tests should inject those fixtures instead of building raw connections
- Remove the per-test-file _connect_kwargs / _db_kwargs helpers (that logic belongs in conftest)

</specifics>
