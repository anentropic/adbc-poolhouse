"""
Async prepared-statement signature contract (PREP-01) --- Wave-0 RED scaffolding.

Phase 35 adds two awaitable methods to `AsyncCursor`:

- `adbc_prepare(operation)` -> `pyarrow.Schema | None` --- prepare a query without
  executing it, returning the bind-parameter schema (or `None`).
- `adbc_execute_schema(operation, parameters=None)` -> `pyarrow.Schema` --- return
  the result-set schema WITHOUT executing the query.

Both forward PLAIN POSITIONAL arguments (D-35-02/03), so --- unlike Phase 30's
`adbc_ingest` --- there is NO keyword-only shape to pin. This runtime-introspection
test therefore asserts EXISTENCE only. The authoritative Protocol-coverage gate is
basedpyright-strict over `_cursor.py`
(`.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py`), which runs in Plan
35-02; this file is the runtime companion a plain `pytest` run exercises.

Wave-0 status: neither `AsyncCursor.adbc_prepare` nor `adbc_execute_schema` exists
yet, so the assertions below FAIL (RED) --- the acceptance signal. Plan 35-02 turns
them GREEN.
"""

from __future__ import annotations

import pytest

from adbc_poolhouse._async._cursor import AsyncCursor


def test_adbc_prepare_exists_on_async_cursor() -> None:
    """`AsyncCursor` exposes an `adbc_prepare` method (RED until Plan 35-02 lands it)."""
    assert hasattr(AsyncCursor, "adbc_prepare"), "AsyncCursor.adbc_prepare not defined yet"


def test_adbc_execute_schema_exists_on_async_cursor() -> None:
    """`AsyncCursor` exposes an `adbc_execute_schema` method (RED until Plan 35-02)."""
    assert hasattr(AsyncCursor, "adbc_execute_schema"), (
        "AsyncCursor.adbc_execute_schema not defined yet"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
