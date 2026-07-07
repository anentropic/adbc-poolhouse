"""
Async partitioned-execution signature contract (PART-01) --- regression coverage.

v1.5.1 adds two awaitable methods to `AsyncCursor`, closing the last gap in
async/sync parity for the raw-cursor ADBC surface:

- `adbc_execute_partitions(operation, parameters=None)` -> `(list[bytes], schema)`
  --- execute a query and return its distributed-result partition descriptors plus
  the result-set schema.
- `adbc_read_partition(partition)` -> `None` --- read one descriptor into the
  cursor's result set, drained afterwards via the usual `fetch_*` methods.

Both forward PLAIN POSITIONAL arguments, so --- as with the Phase 35
prepared-statement methods --- there is NO keyword-only shape to pin. This
runtime-introspection test asserts EXISTENCE only. The authoritative
Protocol-coverage gate is basedpyright-strict over `_cursor.py`
(`.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py`); this file is the
runtime companion a plain `pytest` run exercises.
"""

from __future__ import annotations

import pytest

from adbc_poolhouse._async._cursor import AsyncCursor


def test_adbc_execute_partitions_exists_on_async_cursor() -> None:
    """`AsyncCursor` exposes an `adbc_execute_partitions` method."""
    assert hasattr(AsyncCursor, "adbc_execute_partitions"), (
        "AsyncCursor.adbc_execute_partitions not defined"
    )


def test_adbc_read_partition_exists_on_async_cursor() -> None:
    """`AsyncCursor` exposes an `adbc_read_partition` method."""
    assert hasattr(AsyncCursor, "adbc_read_partition"), (
        "AsyncCursor.adbc_read_partition not defined"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
