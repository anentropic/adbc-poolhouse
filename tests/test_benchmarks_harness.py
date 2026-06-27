"""
Unit tests for the GIL-release benchmark harness arithmetic (SPIKE-01, SPIKE-02).

Exercises only the pure timing/arithmetic functions in ``benchmarks._harness`` on
synthetic timings -- no threads, no connection pool, no ADBC driver, and no
wall-clock assertion (those are hardware-dependent and flaky in CI).
"""

from __future__ import annotations

import statistics

import pytest
from benchmarks._harness import (
    concurrent_wall,
    median,
    parallel_efficiency,
    report,
    speedup,
)


class TestHarnessArithmetic:
    """Pure-function arithmetic of the speedup/efficiency/report harness."""

    def test_ideal_parallel_speedup_equals_n(self) -> None:
        """Ideal-parallel timings (wall == single) give speedup == N."""
        assert speedup(1.0, 1.0, 4) == 4.0

    def test_full_serial_speedup_equals_one(self) -> None:
        """Full-serial timings (wall == N*single) give speedup == 1.0."""
        assert speedup(1.0, 4.0, 4) == 1.0

    def test_parallel_efficiency_ideal(self) -> None:
        """Ideal-parallel timings give parallel_efficiency == 1.0."""
        assert parallel_efficiency(1.0, 1.0, 4) == 1.0

    def test_parallel_efficiency_full_serial(self) -> None:
        """Full-serial timings give parallel_efficiency == 1/N."""
        assert parallel_efficiency(1.0, 4.0, 4) == 0.25

    def test_report_bounds_and_keys(self) -> None:
        """report() exposes the six keys with ideal == single and serial == N*single."""
        r = report(2.0, 2.0, 4)
        assert set(r) == {
            "single_call_s",
            "wall_s",
            "ideal_parallel_s",
            "full_serial_s",
            "speedup_x",
            "parallel_efficiency",
        }
        assert r["ideal_parallel_s"] == 2.0
        assert r["full_serial_s"] == 8.0
        assert r["single_call_s"] == 2.0
        assert r["wall_s"] == 2.0
        assert r["speedup_x"] == 4.0
        assert r["parallel_efficiency"] == 1.0

    def test_median_matches_statistics_median(self) -> None:
        """median() over a known list equals statistics.median of that list."""
        values = [0.3, 0.1, 0.2, 0.5, 0.4]
        assert median(values) == statistics.median(values)

    def test_n_equals_one_edge(self) -> None:
        """N == 1 edge: speedup == 1.0 and parallel_efficiency == 1.0."""
        assert speedup(1.0, 1.0, 1) == 1.0
        assert parallel_efficiency(1.0, 1.0, 1) == 1.0

    def test_speedup_zero_wall_raises(self) -> None:
        """A sub-resolution wall time (wall == 0.0) raises an actionable ValueError."""
        with pytest.raises(ValueError, match="wall must be > 0"):
            speedup(1.0, 0.0, 4)

    def test_parallel_efficiency_zero_wall_raises(self) -> None:
        """parallel_efficiency flows through speedup, so it also rejects wall == 0.0."""
        with pytest.raises(ValueError, match="wall must be > 0"):
            parallel_efficiency(1.0, 0.0, 4)

    def test_report_zero_wall_raises(self) -> None:
        """report() flows through speedup, so it also rejects wall == 0.0."""
        with pytest.raises(ValueError, match="wall must be > 0"):
            report(1.0, 0.0, 4)


class TestConcurrentWall:
    """The barrier-gated concurrent_wall driver, exercised with a synthetic call."""

    def test_returns_nonnegative_wall(self) -> None:
        """A no-op call over n connections yields a finite, non-negative wall time."""
        conns = list(range(4))
        wall = concurrent_wall(lambda _c: 0.0, conns, n=len(conns), trials=2)
        assert wall >= 0.0

    def test_conns_length_mismatch_raises(self) -> None:
        """A len(conns) != n mismatch fails loudly instead of deadlocking."""
        conns = list(range(2))
        with pytest.raises(ValueError, match=r"len\(conns\)=2 must equal n=4"):
            concurrent_wall(lambda _c: 0.0, conns, n=4, trials=1)
