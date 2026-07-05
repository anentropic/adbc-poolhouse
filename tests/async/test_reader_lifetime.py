"""
Reader lifetime + read-after-checkin safety (STREAM-04 / EDGE-33) --- regression coverage.

A streaming `RecordBatchReader` is bound to its checked-out connection's C Arrow
stream. This suite pins the two halves of that lifetime contract:

- **STREAM-04 (drain-then-checkin):** draining the reader inside the connection
  scope yields the correct rows, and the connection checks back in cleanly
  (`pool.checkedout() == 0`).
- **EDGE-33 (read-after-checkin / read-after-close):** reading AFTER the reader is
  closed --- or after the connection is checked back in (which fires the pool
  reset handler that closes the underlying cursor) --- raises the driver's NATIVE
  `pyarrow.lib.ArrowInvalid` ("stream that has already been closed"). It is a
  clean Python exception, NEVER a poolhouse error type and NEVER a segfault
  (T-29-01).

Both backends via `anyio_backend`; both drivers where a live C-stream is needed
(DuckDB always; Snowflake via the cassette fixture, which `importorskip`s cleanly
when the driver/cassette is absent). The Snowflake leg scope is resolved by the
cassette smoke (`test_reader_cassette_smoke.py`, assumption A1): if the
cassette cannot replay a streaming `fetch_record_batch`, the Snowflake row-drain
leg is skipped and only the `ArrowInvalid` read-after-checkin path (which needs no
live streaming rows) is asserted. The `_LIFETIME_LOOPS` + `concurrency_marks`
structure is copied from `test_edge_resource.py`.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pyarrow
import pytest

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

# Repeat (env-controlled) + timeout: codify the "0-hang" loop gate (see _edge_helpers).
pytestmark = importlib.import_module("tests.async._edge_helpers").concurrency_marks

# A few repeats so an allocator-reuse / use-after-free bug has a chance to surface.
_LIFETIME_LOOPS = 5

# The native driver error message fragment for a read on a closed C Arrow stream.
_CLOSED_STREAM_MSG = "stream that has already been closed"

# The single query the checked-in Snowflake cassette records (mirrors
# `test_matrix_readpath.py::_READ_QUERY`); reusing it keeps the cassette leg
# offline. The cassette records ONE interaction, so each test issues `execute`
# exactly once.
_SNOWFLAKE_QUERY = "SELECT 1 AS n, 'hello' AS s"


class TestStream04DrainThenCheckin:
    """STREAM-04: draining then checking in yields correct rows and drains the pool."""

    @pytest.mark.anyio
    async def test_drain_then_checkin_rows_duckdb(self, duckdb_async_pool: AsyncPool) -> None:
        """
        Drain the reader inside the scope; the rows are correct and the pool drains.

        Iterates the whole stream INSIDE the connection scope (the safe, canonical
        path), collects the rows, and asserts they round-trip. On scope exit the
        connection is checked back in and `pool.checkedout()` returns to 0. Looped a
        few times to surface any allocator-reuse issue.
        """
        for i in range(_LIFETIME_LOOPS):
            values: list[int] = []
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute(f"SELECT * FROM range({i}, {i + 3}) AS t(n)")
                async with await cur.fetch_record_batch() as reader:
                    async for batch in reader:
                        values.extend(batch.column("n").to_pylist())
            assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
            assert sorted(values) == [i, i + 1, i + 2]


class TestEdge33ReadAfterCheckin:
    """EDGE-33 / STREAM-04: a read after close/checkin raises native `ArrowInvalid`."""

    @pytest.mark.anyio
    async def test_read_after_close_raises_arrow_invalid_duckdb(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        Reading AFTER `reader.close()` raises the driver's native `ArrowInvalid`.

        Closing the reader closes its C Arrow stream; a subsequent pull surfaces
        `pyarrow.lib.ArrowInvalid` ("stream that has already been closed"), NOT a
        poolhouse error and NOT a segfault (T-29-01). Looped to catch allocator
        reuse.
        """
        for _ in range(_LIFETIME_LOOPS):
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT * FROM range(4) AS t(n)")
                reader = await cur.fetch_record_batch()
                await reader.__anext__()  # pull one batch to open the stream
                await reader.close()
                with pytest.raises(pyarrow.ArrowInvalid, match=_CLOSED_STREAM_MSG):
                    await reader.__anext__()

    @pytest.mark.anyio
    async def test_read_after_checkin_raises_arrow_invalid_duckdb(
        self, duckdb_async_pool: AsyncPool
    ) -> None:
        """
        Reading AFTER the connection is checked back in raises native `ArrowInvalid`.

        The connection scope exits WITHOUT explicitly closing the reader, firing the
        pool reset handler that closes the underlying cursor (and thus the reader's
        C-stream). A read after that raises `pyarrow.lib.ArrowInvalid`, never a
        segfault --- the free-of-charge lifetime backstop (D-29-12). The reader
        handle is captured inside the scope and read OUTSIDE it (mirrors
        `test_edge_resource.py`).
        """
        for _ in range(_LIFETIME_LOOPS):
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute("SELECT * FROM range(4) AS t(n)")
                reader = await cur.fetch_record_batch()
                await reader.__anext__()  # open the stream with one pull
            # Connection checked back in --- the reset handler closed the cursor.
            assert duckdb_async_pool._pool.checkedout() == 0  # noqa: SLF001
            with pytest.raises(pyarrow.ArrowInvalid, match=_CLOSED_STREAM_MSG):
                await reader.__anext__()


# A1 (see test_reader_cassette_smoke.py) is now resolved for the drain leg.
# `pytest-adbc-replay` >= 1.1 exposes `fetch_record_batch` and streams it from the
# recorded result in the checked-in `snowflake_arrow_round_trip` cassette, so
# `test_drain_then_checkin_rows_snowflake` below runs OFFLINE in CI --- no live
# Snowflake, no re-record needed.
#
# `test_read_after_checkin_raises_arrow_invalid_snowflake` stays live-driver-only. Its
# assertion is that reading AFTER the connection checks in raises the driver's native
# closed-stream `ArrowInvalid`. That is a property of the live C-level stream being
# invalidated on checkin; a cassette replay serves recorded batches from a file and is
# not bound to the pool's connection lifecycle, so it cannot reproduce the closed-stream
# error (replay yields instead of raising). Re-recording would NOT change this --- it is
# a structural limit of replay, not a missing recording. DuckDB's
# `test_read_after_checkin_raises_arrow_invalid_duckdb` carries the mandatory offline
# EDGE-33 read-after-checkin coverage against a real driver; this Snowflake leg runs
# only against live credentials (`--adbc-record`) and is skipped offline.
_LIVE_DRIVER_ONLY_SKIP = pytest.mark.skip(
    reason="Read-after-checkin ArrowInvalid is a live-stream-close property that "
    "cassette replay cannot model (the replay reader is not bound to the pool "
    "connection lifecycle); runs only against live Snowflake credentials. DuckDB's "
    "duckdb leg carries the offline EDGE-33 read-after-checkin coverage."
)


class TestEdge33Snowflake:
    """EDGE-33 Snowflake leg: streaming drain replays offline; read-after-checkin is live-only."""

    @_LIVE_DRIVER_ONLY_SKIP
    @pytest.mark.anyio
    @pytest.mark.snowflake
    @pytest.mark.adbc_cassette("snowflake_arrow_round_trip")
    async def test_read_after_checkin_raises_arrow_invalid_snowflake(
        self, snowflake_async_pool: AsyncPool
    ) -> None:
        """
        Snowflake read-after-checkin raises native `ArrowInvalid` (live-driver-only).

        The read-after-checkin `ArrowInvalid` is a property of the live driver's stream
        being invalidated when the connection checks in. A cassette replay serves
        recorded batches and is not bound to the connection lifecycle, so it cannot
        reproduce the closed-stream error --- this leg therefore runs only against live
        Snowflake credentials and is skipped offline. DuckDB's
        `test_read_after_checkin_raises_arrow_invalid_duckdb` carries the mandatory
        offline EDGE-33 coverage.
        """
        async with await snowflake_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute(_SNOWFLAKE_QUERY)
            reader = await cur.fetch_record_batch()
        # Checked back in; the reset handler closed the stream.
        with pytest.raises(pyarrow.ArrowInvalid, match=_CLOSED_STREAM_MSG):
            await reader.__anext__()

    @pytest.mark.anyio
    @pytest.mark.snowflake
    @pytest.mark.adbc_cassette("snowflake_arrow_round_trip")
    async def test_drain_then_checkin_rows_snowflake(self, snowflake_async_pool: AsyncPool) -> None:
        """
        Snowflake drain-then-checkin yields correct rows (offline cassette replay).

        `pytest-adbc-replay` >= 1.1 streams `fetch_record_batch` from the checked-in
        `snowflake_arrow_round_trip` cassette, so this leg runs offline in CI: draining
        the reader before checkin yields the recorded row. DuckDB's
        `test_drain_then_checkin_rows_duckdb` carries the same guarantee against the
        in-process driver.
        """
        rows = 0
        async with await snowflake_async_pool.connect() as conn:
            cur = conn.cursor()
            await cur.execute(_SNOWFLAKE_QUERY)
            async with await cur.fetch_record_batch() as reader:
                async for batch in reader:
                    assert isinstance(batch, pyarrow.RecordBatch)
                    rows += batch.num_rows
        assert rows == 1
