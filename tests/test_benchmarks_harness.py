"""
Unit tests for the GIL-release benchmark harness arithmetic (SPIKE-01, SPIKE-02).

Exercises only the pure timing/arithmetic functions in ``benchmarks._harness`` on
synthetic timings -- no threads, no connection pool, no ADBC driver, and no
wall-clock assertion (those are hardware-dependent and flaky in CI).
"""

from __future__ import annotations

import statistics

from benchmarks._harness import median, parallel_efficiency, report, speedup


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
