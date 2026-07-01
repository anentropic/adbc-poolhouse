"""
EDGE-28 async-side meta-assert: the shipped `_async/` package scans clean.

The exhaustive guard self-tests (synthetic source strings, the malformed-file and
non-UTF-8 paths, the documented alias limitation) live in the top-level sync file
`tests/test_async_guard.py`. This file is the thin async-suite counterpart the
phase VALIDATION.md per-task map points at: it runs inside `tests/async/` so the
`tests/async/test_async_guard.py -q` command in the per-task map exercises the one
assertion that closes the cancellation phase --- that after the 25-02 rewire the
live package still contains no `import asyncio`, no bare `asyncio.CancelledError`
(the new `banned-asyncio-cancelled-error` rule), and no un-limitered
`to_thread.run_sync`.

The scan is a read-only `ast.parse` over the source; it never imports or runs the
inspected modules, so the test needs no event loop and carries no
`@pytest.mark.anyio` marker even though it sits in the dual-backend directory.
"""

from __future__ import annotations

from pathlib import Path

from tests._async_harness.guard import scan_async_package

# Repo-relative path to the shipped async package (trailing slash matches the
# VALIDATION.md / RESEARCH Pattern 4 spelling of the EDGE-28 assertion).
_ASYNC_PKG = "src/adbc_poolhouse/_async/"


class TestRealAsyncPackageClean:
    """EDGE-28 / CANCEL-04: the live `_async/` package is trio-neutral."""

    def test_scan_async_package_is_empty(self) -> None:
        """
        `scan_async_package("src/adbc_poolhouse/_async/") == []` incl. the new rule.

        Proves the cancellation rewire kept the async layer free of every banned
        form the guard knows about: `banned-asyncio-import`,
        `banned-asyncio-cancelled-error` (the EDGE-28 rule added in 25-01), and
        `to_thread-without-limiter`. The cooperative cancel path raises and
        re-raises the framework's own cancellation type via
        `anyio.get_cancelled_exc_class()`, never `asyncio.CancelledError`, so the
        new rule must find nothing here.
        """
        assert Path(_ASYNC_PKG).is_dir(), "the _async/ package must exist by Phase 24"
        assert scan_async_package(_ASYNC_PKG) == []
