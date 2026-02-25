"""Snowflake integration tests (TEST-03): snapshot-based, CI-safe."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


@pytest.mark.snowflake
class TestSnowflakeIntegration:
    """
    TEST-03: Snowflake syrupy snapshot tests.

    Run locally: pytest --override-ini="addopts=" -m snowflake
    Record: pytest --override-ini="addopts=" -m snowflake --snapshot-update
    """

    def test_connection_health(self, snowflake_pool: Any) -> None:
        """Pool path works: create_pool() + acquire + SELECT 1 + checkin."""
        conn = snowflake_pool.connect()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1
        cur.close()
        conn.close()

    def test_arrow_round_trip(
        self,
        snowflake_pool: Any,
        snowflake_snapshot: SnapshotAssertion,
    ) -> None:
        """Arrow schema + rows match committed snapshot; no credentials in snapshot."""
        conn = snowflake_pool.connect()
        cur = conn.cursor()
        cur.execute("SELECT 1 AS n, 'hello' AS s")
        table = cur.fetch_arrow_table()
        cur.close()
        conn.close()
        assert table == snowflake_snapshot
