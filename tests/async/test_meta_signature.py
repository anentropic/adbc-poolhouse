"""
Async connection metadata signature contract (META-01) --- Wave-0 RED scaffolding.

Phase 34 adds six `adbc_get_*` metadata methods to
[`AsyncConnection`][adbc_poolhouse._async._connection.AsyncConnection], each an
async offload wrapper over the sync `adbc_driver_manager.dbapi.Connection`. The
verified driver signatures (`adbc_driver_manager` 1.11.0, introspected via
`inspect.signature`) pin the call-site shape: `adbc_get_objects` /
`adbc_get_table_schema` / `adbc_get_statistics` expose their filter arguments as
KEYWORD-ONLY (after `*`), while `adbc_get_table_schema.table_name` stays
positional. This runtime-introspection test locks that shape, so a GREEN
implementation that drops the `*` --- or moves a positional behind it --- fails
here.

The authoritative Protocol-coverage gate is basedpyright-strict over
`_connection.py` (`.venv/bin/basedpyright
src/adbc_poolhouse/_async/_connection.py`), which proves the `_SyncConnection`
structural Protocol carries the six methods. That static gate runs in Plan 34-02;
this file is the runtime companion a plain `pytest` run exercises.

Wave-0 status: none of the six `adbc_get_*` methods exist on `AsyncConnection`
yet, so the introspection below raises `AttributeError` and every test FAILS
(RED) --- the acceptance signal.
"""

from __future__ import annotations

import inspect

import pytest

from adbc_poolhouse._async._connection import AsyncConnection

# Every metadata method that MUST exist on the async connection (META-01).
_ALL_METHODS = (
    "adbc_get_info",
    "adbc_get_objects",
    "adbc_get_table_schema",
    "adbc_get_table_types",
    "adbc_get_statistics",
    "adbc_get_statistic_names",
)

# `adbc_get_objects` filter params that MUST be keyword-only (verified driver sig).
_GET_OBJECTS_KEYWORD_ONLY = (
    "depth",
    "catalog_filter",
    "db_schema_filter",
    "table_name_filter",
    "table_types_filter",
    "column_name_filter",
)

# `adbc_get_table_schema` filter params that MUST be keyword-only.
_GET_TABLE_SCHEMA_KEYWORD_ONLY = ("catalog_filter", "db_schema_filter")

# `adbc_get_statistics` filter params that MUST be keyword-only.
_GET_STATISTICS_KEYWORD_ONLY = (
    "catalog_filter",
    "db_schema_filter",
    "table_name_filter",
    "approximate",
)


def test_all_metadata_methods_exist_on_async_connection() -> None:
    """`AsyncConnection` exposes all six `adbc_get_*` methods (RED until Plan 34-02)."""
    for name in _ALL_METHODS:
        assert hasattr(AsyncConnection, name), f"AsyncConnection.{name} not defined yet"


def test_get_objects_filters_are_keyword_only() -> None:
    """
    Every `adbc_get_objects` filter (incl. `depth`) is KEYWORD_ONLY.

    Introspects the public signature and asserts each of the six filter arguments
    has `KEYWORD_ONLY` kind --- the verified driver shape (all filters after `*`),
    which the async wrapper must preserve.
    """
    signature = inspect.signature(AsyncConnection.adbc_get_objects)
    for name in _GET_OBJECTS_KEYWORD_ONLY:
        assert name in signature.parameters, f"missing keyword-only param: {name}"
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{name} must be keyword-only"
        )


def test_get_objects_depth_default_is_all() -> None:
    """`adbc_get_objects` `depth` defaults to `"all"` (verified driver default)."""
    signature = inspect.signature(AsyncConnection.adbc_get_objects)
    assert signature.parameters["depth"].default == "all"


def test_get_table_schema_table_name_is_positional() -> None:
    """
    `adbc_get_table_schema.table_name` stays positional; its filters are keyword-only.

    The complement of the keyword-only check: the identifier argument must remain
    callable positionally (asserted NOT `KEYWORD_ONLY`), while `catalog_filter` /
    `db_schema_filter` sit behind the `*`.
    """
    signature = inspect.signature(AsyncConnection.adbc_get_table_schema)
    assert "table_name" in signature.parameters, "missing positional param: table_name"
    assert signature.parameters["table_name"].kind is not inspect.Parameter.KEYWORD_ONLY, (
        "table_name must not be keyword-only"
    )
    for name in _GET_TABLE_SCHEMA_KEYWORD_ONLY:
        assert name in signature.parameters, f"missing keyword-only param: {name}"
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{name} must be keyword-only"
        )


def test_get_statistics_filters_are_keyword_only() -> None:
    """Every `adbc_get_statistics` filter (incl. `approximate`) is KEYWORD_ONLY."""
    signature = inspect.signature(AsyncConnection.adbc_get_statistics)
    for name in _GET_STATISTICS_KEYWORD_ONLY:
        assert name in signature.parameters, f"missing keyword-only param: {name}"
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{name} must be keyword-only"
        )


def test_no_arg_methods_take_only_self() -> None:
    """
    `adbc_get_info` / `adbc_get_table_types` / `adbc_get_statistic_names` take no params.

    Each of the three value/stream methods with no filters exposes only the bound
    `self` receiver --- no stray positional or keyword argument leaks into the
    async wrapper's signature.
    """
    for name in ("adbc_get_info", "adbc_get_table_types", "adbc_get_statistic_names"):
        signature = inspect.signature(getattr(AsyncConnection, name))
        assert list(signature.parameters) == ["self"], (
            f"{name} must take only self, got {list(signature.parameters)}"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
