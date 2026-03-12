"""
ADBC driver manager facade.

This module is the single location for all ``adbc_driver_manager`` type
suppressions and for the Foundry NOT_FOUND catch-and-reraise logic (DRIV-03).

All ``cast()`` calls and ``# type: ignore`` suppressions touching ADBC types
must live here. No other module may import ``adbc_driver_manager`` directly.

``adbc_driver_manager`` is a runtime dependency (always installed as a
transitive dep of any warehouse driver). Its top-level import here is
intentional — do not make it lazy.

Internal only — not exported from ``__init__.py``.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import adbc_driver_manager
import adbc_driver_manager.dbapi  # runtime import — adbc-driver-manager always present

if TYPE_CHECKING:
    from adbc_driver_manager.dbapi import Connection


def create_adbc_connection(
    driver_path: str,
    kwargs: dict[str, str],
    *,
    entrypoint: str | None = None,
    dbapi_module: str | None = None,
) -> Connection:
    """
    Create an ADBC DBAPI connection.

    All ``cast()`` and ``# type: ignore`` suppressions for the ADBC driver
    manager are concentrated in this module (DRIV-03).

    When ``dbapi_module`` is provided (PyPI drivers like Snowflake, BigQuery),
    the connection is created through that driver's own ``.dbapi.connect()``
    instead of routing through ``adbc_driver_manager.dbapi``. This ensures
    tools that monkeypatch per-driver DBAPI modules (e.g. pytest-adbc-replay)
    intercept at the correct module.

    For Foundry drivers (Databricks, Redshift, Trino, MSSQL, MySQL):
    if the driver manifest is not found, ``adbc_driver_manager`` raises an
    ``Error`` subclass with ``status_code == AdbcStatusCode.NOT_FOUND``. This
    is caught here and re-raised as ``ImportError`` with a human-readable
    message pointing to https://docs.adbc-drivers.org/ (DRIV-03 locked).

    All other ADBC exceptions (auth failures, network errors, etc.) pass
    through raw — wrapping is a Phase 5+ concern.

    Args:
        driver_path: Absolute path to the driver shared library, or a short
            driver name for manifest-based resolution (Foundry drivers and
            PyPI Path 2 fallback).
        kwargs: ADBC ``db_kwargs`` as ``dict[str, str]`` from
            ``translate_config()``.
        entrypoint: Optional ADBC entry-point symbol. Required for DuckDB
            (``entrypoint='duckdb_adbc_init'``).
        dbapi_module: Dotted module name for a PyPI driver's own DBAPI module
            (e.g. ``"adbc_driver_snowflake.dbapi"``). When provided, the
            connection is created through that module instead of
            ``adbc_driver_manager.dbapi``. ``None`` falls back to the
            manager path.

    Returns:
        An open ADBC DBAPI connection.

    Raises:
        ImportError: When a Foundry driver manifest is absent (NOT_FOUND).
            Message contains ``https://docs.adbc-drivers.org/``.
    """
    if dbapi_module is not None:
        mod = importlib.import_module(dbapi_module)
        conn = mod.connect(db_kwargs=kwargs)  # type: ignore[no-any-return]
        return conn  # type: ignore[return-value]

    # Build a reverse lookup: short driver name → dbc install name.
    # Used to construct the ImportError message when a Foundry driver manifest
    # is missing (adbc_driver_manager raises NOT_FOUND in that case).
    _foundry_name_to_install: dict[str, str] = {
        "clickhouse": "clickhouse",
        "databricks": "databricks",
        "mssql": "mssql",
        "mysql": "mysql",
        "redshift": "redshift",
        "trino": "trino",
    }

    try:
        # All ADBC type suppressions are concentrated here (DRIV-03).
        # connect() accepts (driver, uri, entrypoint, db_kwargs, conn_kwargs, autocommit).
        # We pass driver_path as driver=; using keyword form is required so that
        # pytest-adbc-replay's monkeypatched connect() (which accepts **kwargs only)
        # can still pass through to the real connect for non-cassette tests.
        # dict[str, str] is assignable to dict[str, str | Path]; the ignore
        # suppresses basedpyright's overload-resolution complaint on driver_path.
        conn = adbc_driver_manager.dbapi.connect(  # type: ignore[call-overload]
            driver=driver_path,  # type: ignore[arg-type]
            entrypoint=entrypoint,  # type: ignore[arg-type]
            db_kwargs=kwargs,  # type: ignore[arg-type]
        )
    except adbc_driver_manager.Error as exc:  # type: ignore[attr-defined]
        # adbc_driver_manager.Error is the PEP-249 base; all status-carrying
        # exceptions (ProgrammingError, DatabaseError, etc.) inherit from it.
        # The status_code attribute holds an AdbcStatusCode int-enum value.
        # NOT_FOUND (3) is raised when dlopen() + manifest search both fail.
        if (
            getattr(exc, "status_code", None) == adbc_driver_manager.AdbcStatusCode.NOT_FOUND  # type: ignore[attr-defined]
        ) or "NOT_FOUND" in str(exc):
            install_name = _foundry_name_to_install.get(driver_path, driver_path)
            raise ImportError(
                f"ADBC driver '{driver_path}' not found. "
                f"Install it with: dbc install {install_name}\n"
                f"See: https://docs.adbc-drivers.org/"
            ) from exc
        raise  # re-raise other ADBC status errors raw

    return conn  # type: ignore[return-value]
