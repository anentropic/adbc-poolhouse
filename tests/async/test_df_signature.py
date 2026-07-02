"""
Async DataFrame signature + import-surface contract (DF-01/DF-02, PKG-02) --- Wave-0 RED.

Two runtime-companion contracts for Phase 31:

- **Signature (DF-01/DF-02):** `AsyncCursor.fetch_df` / `fetch_polars` exist and take
  only `self` (no arguments --- simpler than `adbc_ingest`, which forwards a payload;
  D-31-03). This runtime-introspection test pins that with `inspect.signature`, so a
  GREEN implementation that adds a spurious parameter fails here.
- **Import surface (PKG-02):** `import adbc_poolhouse` must succeed with pandas/polars
  ABSENT. pandas/polars stay `TYPE_CHECKING`-only string annotations on the public
  methods and are never runtime-imported by the package (D-31-07/D-31-08). This test
  imports the package in-process and asserts it succeeds --- env-free today (the
  annotation strings are never evaluated), and it must remain so after `uv sync` pulls
  the dev-group deps.

The authoritative `_SyncCursor` Protocol-coverage gate is basedpyright-strict over
`_cursor.py` (`.venv/bin/basedpyright src/adbc_poolhouse/_async/_cursor.py`) --- it
proves the structural Protocol carries `fetch_df` / `fetch_polars` as `-> object`
(D-31-06) and that `BlockingStubCursor` satisfies it. That static gate runs in Plan
31-02; this file is the runtime companion a plain `pytest` run exercises.

Wave-0 status: `AsyncCursor.fetch_df` / `fetch_polars` do NOT exist yet, so the
introspection below fails (RED) --- the acceptance signal. The `import_surface` case
may already PASS (it only imports the package); that is acceptable.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from adbc_poolhouse._async._cursor import AsyncCursor

# The two new zero-arg methods under test.
_METHODS = ("fetch_df", "fetch_polars")


@pytest.mark.parametrize("method_name", _METHODS)
def test_method_exists_on_async_cursor(method_name: str) -> None:
    """`AsyncCursor` exposes `fetch_df` / `fetch_polars` (RED until Plan 31-02 lands them)."""
    assert hasattr(AsyncCursor, method_name), f"AsyncCursor.{method_name} not defined yet"


@pytest.mark.parametrize("method_name", _METHODS)
def test_method_takes_only_self(method_name: str) -> None:
    """
    `fetch_df` / `fetch_polars` take only `self` --- no extra parameters.

    Introspects the public signature and asserts the sole parameter is `self`
    (D-31-03: bare method reference, no `functools.partial`, no args --- unlike
    `adbc_ingest`). A GREEN implementation that adds a parameter fails here.
    """
    signature = inspect.signature(getattr(AsyncCursor, method_name))
    assert list(signature.parameters) == ["self"], (
        f"{method_name} must take only self, got {list(signature.parameters)}"
    )


def test_import_surface_no_pandas_polars_runtime_dependency() -> None:
    """
    `import adbc_poolhouse` succeeds without runtime-importing pandas/polars (PKG-02).

    pandas/polars are `TYPE_CHECKING`-only annotations on the public methods and are
    never imported at runtime by the package (D-31-07/D-31-08). Importing the package
    in-process must therefore always succeed --- the deferred string annotations are
    never evaluated by a consumer. This case may PASS in Wave 0 (it only imports the
    package); that is acceptable.
    """
    module = importlib.import_module("adbc_poolhouse")
    assert module is not None
