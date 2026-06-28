"""
Arrow allocator-stability proof (TEST-03): no leak across many cursor lifecycles.

The highest-risk failure mode of the async DB wrapper is a silent Arrow-allocator
leak --- a `pyarrow.Table` (or the cursor that produced it) that quietly retains
its backing buffers across check-ins, so memory creeps up under sustained load.
This proves that does not happen, with a deterministic metric rather than process
RSS (which is non-deterministic and would flake, D-27-07).

The primary signal is `pyarrow.total_allocated_bytes()`: capture a baseline after
`gc.collect()`, run N>=100 cycles of (open -> execute -> `fetch_arrow_table` ->
`del tbl` -> checkin) on the real DuckDB pool, then `gc.collect()` again and assert
the delta is zero (no monotonic growth). A belt-and-braces second assertion counts
the pool `reset` event --- the `_release_arrow_allocators` symmetric-cleanup path
(ACONN-06 / D-27-08) --- firing exactly once per checkin, observed via a SQLAlchemy
event listener so no frozen `src/` symbol is touched. Run x{asyncio, trio} (D-27-09).
"""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING

import pyarrow
import pytest
from sqlalchemy import event

if TYPE_CHECKING:
    from adbc_poolhouse._async._pool import AsyncPool

# D-27-07: at least 100 cycles so a per-cycle allocator leak compounds into a
# clearly non-zero delta if the symmetric-cleanup invariant is ever broken.
_N = 100


class TestStability03ArrowAllocator:
    """No Arrow allocator growth, and one reset per checkin, over N>=100 cycles."""

    @pytest.mark.anyio
    async def test_no_allocator_growth_and_one_reset_per_checkin(
        self,
        duckdb_async_pool: AsyncPool,
        anyio_backend_name: str,
        request: pytest.FixtureRequest,
    ) -> None:
        """
        Run N>=100 cursor lifecycles and prove no allocator growth + one reset each.

        Each cycle opens a connection, executes a trivial SELECT, materializes a
        `pyarrow.Table` via `fetch_arrow_table`, drops the only reference, and exits
        the connection scope (checkin), which fires the pool reset event that runs
        `_release_arrow_allocators`. After the loop, the `pyarrow` allocator delta
        from baseline must be zero (no monotonic growth, D-27-07) and the reset
        event must have fired exactly `_N` times (one per checkin, ACONN-06 /
        D-27-08). Runs under both asyncio and trio (D-27-09).
        """
        # Requested only to drive the x{asyncio, trio} axis via @pytest.mark.anyio;
        # the backend string itself is unused (convention: test_edge_resource.py:57).
        del anyio_backend_name

        # Belt-and-braces (D-27-08 / ACONN-06): observe the pool's reset event --- the
        # _release_arrow_allocators symmetric-cleanup path --- WITHOUT patching frozen
        # src/. The SQLAlchemy listener counts; it does not alter behaviour.
        reset_count = 0

        def _on_reset(dbapi_conn: object, conn_record: object, reset_state: object) -> None:
            nonlocal reset_count
            del dbapi_conn, conn_record, reset_state
            reset_count += 1

        event.listen(duckdb_async_pool._pool, "reset", _on_reset)
        # Explicit teardown (IN-02): the listener closes over the test-local
        # `reset_count`, so remove it on finalize rather than relying on the pool's
        # own disposal to drop it implicitly --- the intent is then unambiguous.
        request.addfinalizer(lambda: event.remove(duckdb_async_pool._pool, "reset", _on_reset))

        # Primary signal (D-27-07): pyarrow allocator delta, NOT process RSS. Settle
        # any pending frees first so the baseline is the true post-GC floor.
        gc.collect()
        baseline = pyarrow.total_allocated_bytes()

        for i in range(_N):
            async with await duckdb_async_pool.connect() as conn:
                cur = conn.cursor()
                await cur.execute(f"SELECT {i} AS n")
                tbl = await cur.fetch_arrow_table()
                # Drop the only ref to the materialized table inside the loop; the
                # scope exit then checks the connection back in and fires reset.
                del tbl
            # Connection is checked back in here; reset has fired for this cycle.
            assert duckdb_async_pool._pool.checkedout() == 0

        # Reclaim anything the loop left collectable, then measure the delta. Zero
        # means no buffer survived check-in across all N cycles (verified
        # deterministic this session). The documented fallback if a future Arrow
        # build makes exact-zero brittle is `delta < single_table_bytes`
        # (RESEARCH Pitfall 5) --- exact-zero is asserted first.
        gc.collect()
        delta = pyarrow.total_allocated_bytes() - baseline
        assert delta == 0, f"Arrow allocator grew by {delta} bytes over {_N} cycles"

        # One reset per checkin --- the _release_arrow_allocators path fired exactly
        # once for each of the N cycles (ACONN-06 symmetric cleanup).
        assert reset_count == _N, f"expected {_N} resets, got {reset_count}"
