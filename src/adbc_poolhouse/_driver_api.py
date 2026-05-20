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
import inspect
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

    When ``dbapi_module`` is provided, the connection is created through that
    driver's own ``.dbapi.connect()`` instead of routing through
    ``adbc_driver_manager.dbapi``. The function introspects the target
    module's ``connect()`` signature to handle three distinct shapes:

    - **Family A** (Snowflake, BigQuery): accepts a ``db_kwargs`` parameter
      and either has no ``uri`` parameter or ``uri`` has a default --
      called as ``connect(db_kwargs=kwargs)``.
    - **Family A'** (PostgreSQL, FlightSQL, Quack): accepts ``db_kwargs``
      AND declares ``uri`` as a required positional (no default). The
      dispatcher pops ``"uri"`` from ``kwargs`` and calls
      ``connect(uri_val, db_kwargs=kwargs)``. ``db_kwargs`` is always passed
      by name because some of these drivers declare it KEYWORD_ONLY.
    - **Family B** (DuckDB, SQLite): no ``db_kwargs`` parameter -- called as
      ``connect(**kwargs)`` with kwargs unpacked directly.

    This signature detection ensures tools that monkeypatch per-driver DBAPI
    modules (e.g. pytest-adbc-replay) intercept at the correct module.

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
            ``config.to_adbc_kwargs()``.
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
        ImportError: When the ADBC driver is not found (NOT_FOUND status).
            Message contains ``https://docs.adbc-drivers.org/``.
    """
    if dbapi_module is not None:
        mod = importlib.import_module(dbapi_module)
        sig = inspect.signature(mod.connect)  # type: ignore[reportUnknownMemberType]
        params = sig.parameters
        if "db_kwargs" in params:
            uri_param = params.get("uri")
            if uri_param is not None and uri_param.default is inspect.Parameter.empty:
                # Family A' — uri is a REQUIRED parameter. Pop it from kwargs and
                # pass explicitly so the driver's signature is satisfied; remaining
                # keys ride as db_kwargs=. KeyError from the pop is intentional —
                # fail loud on a config-shape mismatch.
                # db_kwargs is passed by name because Quack declares it KEYWORD_ONLY.
                uri_val = kwargs.pop("uri")
                if uri_param.kind is inspect.Parameter.KEYWORD_ONLY:
                    # `def connect(*, uri, db_kwargs=None)` — pass uri by name.
                    conn = mod.connect(uri=uri_val, db_kwargs=kwargs)  # type: ignore[no-any-return]
                else:
                    # POSITIONAL_ONLY / POSITIONAL_OR_KEYWORD (Quack, Postgres, FlightSQL).
                    conn = mod.connect(uri_val, db_kwargs=kwargs)  # type: ignore[no-any-return]
            else:
                # Family A (Snowflake / BigQuery): uri optional or absent — driver
                # picks `uri` out of db_kwargs itself if it cares.
                conn = mod.connect(db_kwargs=kwargs)  # type: ignore[no-any-return]
        else:
            # Family B (DuckDB / SQLite): no db_kwargs parameter.
            conn = mod.connect(**kwargs)  # type: ignore[no-any-return]
        return conn  # type: ignore[return-value]

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
            raise ImportError(
                f"ADBC driver '{driver_path}' not found. See: https://docs.adbc-drivers.org/"
            ) from exc
        raise  # re-raise other ADBC status errors raw

    return conn  # type: ignore[return-value]
