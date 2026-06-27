"""
Behavioural async test suite (Phase 24 verification backbone).

This package holds the real-driver lifecycle test plus the structural EDGE
suite assigned to Phase 24. Its own `conftest.py` defines the `anyio_backend`
fixture so every test here runs under BOTH asyncio and trio; that fixture is
deliberately confined to this directory (never the root conftest) so the
synchronous suite is never dragged under the anyio plugin (PKG-04, Pitfall 6).
"""
