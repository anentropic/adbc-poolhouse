"""
Async partitioned execution against a live Flight SQL server (PART-04).

Flight SQL is the only ADBC driver that implements partitioned result sets, so this
is the one suite that exercises `adbc_execute_partitions` / `adbc_read_partition`
end-to-end through a real driver rather than the blocking stub. It drives
poolhouse's actual async offload path (`FlightSQLConfig` + `adbc_driver_flightsql`)
against the in-process
[`PartitionFlightServer`][tests._flightsql_harness.partition_server.PartitionFlightServer],
which returns a fixed two-partition result (`id`, `name`).

The server is credential-free and in-process, so unlike the Snowflake/Databricks
cassette legs this runs on every CI machine that can bind a localhost socket. Both
async backends (asyncio x trio) via `anyio_backend`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool


class TestPart04FlightSQLLive:
    """PART-04: real Flight SQL execute_partitions -> read_partition round-trip."""

    @pytest.mark.anyio
    async def test_execute_partitions_returns_descriptors_and_schema(
        self, flightsql_async_pool: AsyncPool
    ) -> None:
        """
        `adbc_execute_partitions` returns opaque descriptors plus the result schema.

        The server splits the result across two endpoints, so the driver surfaces two
        partition descriptors (opaque `bytes`) and the `(id, name)` schema. The
        connection checks back in cleanly afterwards.
        """
        async with await flightsql_async_pool.connect() as conn:
            cursor = conn.cursor()
            partitions, schema = await cursor.adbc_execute_partitions("SELECT id, name FROM t")
            assert len(partitions) == 2
            assert all(isinstance(p, bytes) for p in partitions)
            assert schema is not None
            assert isinstance(schema, pyarrow.Schema)
            assert schema.names == ["id", "name"]
        assert flightsql_async_pool._pool.checkedout() == 0  # noqa: SLF001

    @pytest.mark.anyio
    async def test_read_partition_reassembles_full_result(
        self, flightsql_async_pool: AsyncPool
    ) -> None:
        """
        Reading every partition and concatenating reproduces the whole result set.

        Each descriptor is fed back to `adbc_read_partition`, then drained with
        `fetch_arrow_table`; the union of the two partitions is the fixed
        `{id: [1,2,3,4], name: [a,b,c,d]}` result the server serves (order-independent).
        """
        async with await flightsql_async_pool.connect() as conn:
            cursor = conn.cursor()
            partitions, _ = await cursor.adbc_execute_partitions("SELECT id, name FROM t")

            rows: list[tuple[int, str]] = []
            for descriptor in partitions:
                await cursor.adbc_read_partition(descriptor)
                table = await cursor.fetch_arrow_table()
                pydict = table.to_pydict()
                rows.extend(zip(pydict["id"], pydict["name"], strict=True))

        assert sorted(rows) == [(1, "a"), (2, "b"), (3, "c"), (4, "d")]
        assert flightsql_async_pool._pool.checkedout() == 0  # noqa: SLF001


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
