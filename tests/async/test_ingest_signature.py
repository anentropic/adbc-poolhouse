"""
Async bulk-write signature contract (INGEST-01) --- regression coverage.

Phase 30's public `AsyncCursor.adbc_ingest` surfaces `mode`, `catalog_name`,
`db_schema_name`, and `temporary` as KEYWORD-ONLY (after `*`, D-30-03), while
`table_name` and `data` stay positional. This runtime-introspection test pins that
call-site shape with `inspect.signature`, so a GREEN implementation that forgets
the `*` (or moves a positional behind it) fails here.

The authoritative Protocol-coverage gate is basedpyright-strict over `_cursor.py`
(`.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py`) --- it proves the
`_SyncCursor` structural Protocol carries `adbc_ingest` and the
`BlockingStubCursor` satisfies it. That static gate runs in Plan 30-02; this file
is the runtime companion that a plain `pytest` run exercises.

Status: `AsyncCursor.adbc_ingest` is implemented (Plan 30-02); this file is passing
regression coverage of the keyword-only/positional signature contract above.
"""

from __future__ import annotations

import inspect

import pytest

from adbc_poolhouse._async._cursor import AsyncCursor

# Params that MUST be keyword-only on the public method (after `*`, D-30-03).
_KEYWORD_ONLY = ("mode", "catalog_name", "db_schema_name", "temporary")
# Params that MUST stay positional (never behind the `*`).
_POSITIONAL = ("table_name", "data")


def test_adbc_ingest_exists_on_async_cursor() -> None:
    """`AsyncCursor` exposes an `adbc_ingest` method (RED until Plan 30-02 lands it)."""
    assert hasattr(AsyncCursor, "adbc_ingest"), "AsyncCursor.adbc_ingest not defined yet"


def test_keyword_only_params_are_keyword_only() -> None:
    """
    `mode` / `catalog_name` / `db_schema_name` / `temporary` are KEYWORD_ONLY.

    Introspects the public signature and asserts each of the four configuration
    arguments has `KEYWORD_ONLY` kind --- the cleaner call site D-30-03 mandates
    (poolhouse tightens even `mode`, which the driver leaves positional-or-keyword).
    """
    signature = inspect.signature(AsyncCursor.adbc_ingest)
    for name in _KEYWORD_ONLY:
        assert name in signature.parameters, f"missing keyword-only param: {name}"
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{name} must be keyword-only"
        )


def test_positional_params_are_not_keyword_only() -> None:
    """
    `table_name` and `data` stay positional (never pushed behind the `*`).

    The complement of the keyword-only check: the two payload arguments must remain
    callable positionally, so they are asserted NOT to be `KEYWORD_ONLY`.
    """
    signature = inspect.signature(AsyncCursor.adbc_ingest)
    for name in _POSITIONAL:
        assert name in signature.parameters, f"missing positional param: {name}"
        assert signature.parameters[name].kind is not inspect.Parameter.KEYWORD_ONLY, (
            f"{name} must not be keyword-only"
        )


def test_mode_default_is_create() -> None:
    """`mode` defaults to `"create"` (D-30-05) --- the safe, non-destructive default."""
    signature = inspect.signature(AsyncCursor.adbc_ingest)
    assert signature.parameters["mode"].default == "create"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
