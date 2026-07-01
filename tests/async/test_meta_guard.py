"""
EDGE-27 / EDGE-30 real-package meta-guards over the whole `tests/async/` suite.

This file is the Wave-3 closing meta-test for Phase 27. The exhaustive synthetic
self-tests for the two guard callables (violator strings, the allow-list cases,
the absent-root no-op) live in the top-level sync file `tests/test_async_guard.py`
under `TestAsyncTestHygiene` / `TestPositiveSleepScan`. This file is the thin
real-package counterpart: it points the now-complete guards at the live
`tests/async/` directory and asserts they find nothing, certifying that every
EDGE and Wave-2 file in the package observes the no-`asyncio`, anyio-parametrized,
no-positive-`sleep` discipline.

Because this plan runs LAST, the scan validates every Wave-2 file (read-path
matrix, Arrow stability, limiter stress) as well as the original EDGE suite.

The scans are read-only `ast.parse` walks over the source; they never import or
run the inspected modules, so these tests need no event loop and carry no
`@pytest.mark.anyio` marker even though they sit in the dual-backend directory.
"""

from __future__ import annotations

from tests._async_harness.guard import (
    scan_async_test_hygiene,
    scan_for_positive_sleep,
)

# Repo-relative scan root. Scoped to `tests/async/` ONLY for the sleep guard:
# the harness package (`tests/_async_harness/`) has DELIBERATE positive sleeps
# under virtual clocks (e.g. `anyio.sleep(3600)`), so scanning the harness root
# would false-positive (RESEARCH Pitfall 1, D-27-02 scope lock).
_ASYNC_TESTS = "tests/async"


class TestRealAsyncTestPackageHygiene:
    """EDGE-27 / EDGE-30: the live `tests/async/` package scans clean."""

    def test_async_test_package_hygiene(self) -> None:
        """
        `scan_async_test_hygiene("tests/async") == []` (EDGE-27, D-27-01).

        Proves the whole async test package observes the asyncio/trio dual-backend
        axis: no `import asyncio` / `from asyncio import ...`, no
        `@pytest.mark.asyncio` (plain or called form), and every `async def test_*`
        carries `@pytest.mark.anyio`. Per D-27-03 the "both backends" here is the
        anyio asyncio/trio axis the marker selects, not the DuckDB/Snowflake axis
        (which is TEST-02's concern). The anyio signal is marker PRESENCE, never a
        literal `anyio_backend` argument (RESEARCH Pitfall 2).
        """
        assert scan_async_test_hygiene(_ASYNC_TESTS) == []

    def test_no_positive_sleep_in_async_tests(self) -> None:
        """
        `scan_for_positive_sleep("tests/async") == []` (EDGE-30).

        Proves no async test introduces a positive-duration real-time sleep: every
        `<mod>.sleep(...)` / bare `sleep(...)` either uses `sleep(0)` /
        `sleep(0.0)` checkpoints or a non-literal argument. The scan root is
        `tests/async/` ONLY — the harness keeps deliberate positive sleeps under
        virtual clocks, which this guard must not see (RESEARCH Pitfall 1).
        """
        assert scan_for_positive_sleep(_ASYNC_TESTS) == []
