"""
Module-level ``connect()`` factory for the Databricks Python connector backend.

This module exists so the native connection factory is a single, patchable
symbol. `pytest-adbc-replay` records and replays by monkeypatching a module's
``connect`` (via its ``adbc_auto_patch`` list); pointing it at this module lets
the connector backend reuse the exact cassette methodology as the ADBC backends.

`connect()` returns a `_ConnectionAdapter`, so the recorder wraps something that
already presents the ADBC DBAPI surface (``fetch_arrow_table`` etc.) and needs no
connector-specific handling. The connector import is deferred to call time so
this module imports connector-free at pytest session start (replay-only CI).
"""

from __future__ import annotations

from typing import Any

from adbc_poolhouse._native_adapter import _ConnectionAdapter


def connect(**kwargs: Any) -> _ConnectionAdapter:
    """
    Open a Databricks Python-connector connection wrapped as ADBC DBAPI.

    Args:
        **kwargs: Connector connection kwargs as built by
            ``DatabricksPythonConfig.to_connect_kwargs()`` (``server_hostname``,
            ``http_path``, ``access_token`` / ``credentials_provider`` / ``auth_type``,
            ``catalog``, ``schema``, ``use_kernel``, ...).

    Returns:
        A `_ConnectionAdapter` presenting the ADBC DBAPI surface.
    """
    # The connector ships no type stubs; suppressions are concentrated on this
    # single lazy import + call, the only place the connector is touched directly.
    from databricks import sql  # type: ignore[reportMissingTypeStubs]  # noqa: PLC0415

    return _ConnectionAdapter(sql.connect(**kwargs))  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
