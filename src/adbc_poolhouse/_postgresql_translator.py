"""PostgreSQL ADBC driver kwargs translator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from adbc_poolhouse._postgresql_config import PostgreSQLConfig


def translate_postgresql(config: PostgreSQLConfig) -> dict[str, str]:
    """
    Translate PostgreSQLConfig to ADBC driver kwargs.

    Supports two modes:

    - **URI mode** (``uri`` set): passed directly as the ``uri`` kwarg.
    - **Individual fields mode**: builds a libpq URI from ``host``, ``port``,
      ``user``, ``password``, ``database``, and ``sslmode``. ``password`` is
      URL-encoded via :func:`urllib.parse.quote` with ``safe=""`` so special
      characters do not corrupt the connection string.

    If neither ``uri`` nor any individual fields are set, returns ``{}`` and
    lets libpq resolve the connection from its own environment variables.

    Note:
        ``adbc.postgresql.use_copy`` is a StatementOptions key — it is NOT a
        database-level kwarg and cannot be passed to ``dbapi.connect()``.

    Args:
        config: A validated ``PostgreSQLConfig`` instance.

    Returns:
        A ``dict[str, str]`` of ADBC driver kwargs for
        ``adbc_driver_manager.dbapi.connect()``.

    Examples:
        >>> from adbc_poolhouse import PostgreSQLConfig
        >>> from adbc_poolhouse._postgresql_translator import translate_postgresql
        >>> result = translate_postgresql(PostgreSQLConfig(uri="postgresql://localhost/mydb"))
        >>> result
        {'uri': 'postgresql://localhost/mydb'}
        >>> result = translate_postgresql(
        ...     PostgreSQLConfig(host="localhost", user="me", database="mydb")
        ... )
        >>> result["uri"]
        'postgresql://me@localhost/mydb'
    """
    if config.uri is not None:
        return {"uri": config.uri}

    # Individual fields mode — build URI only if at least one field is set.
    has_fields = any(
        [
            config.host,
            config.user,
            config.password,
            config.database,
            config.sslmode,
        ]
    )
    if not has_fields:
        return {}

    return {"uri": _build_uri(config)}


def _build_uri(config: PostgreSQLConfig) -> str:
    """Build a libpq URI from individual PostgreSQLConfig fields."""
    uri = "postgresql://"

    if config.user is not None:
        uri += quote(config.user, safe="")
        if config.password is not None:
            uri += ":" + quote(config.password.get_secret_value(), safe="")
        uri += "@"

    if config.host is not None:
        uri += config.host

    if config.port is not None:
        uri += f":{config.port}"

    if config.database is not None:
        uri += f"/{config.database}"

    if config.sslmode is not None:
        uri += f"?sslmode={config.sslmode}"

    return uri
