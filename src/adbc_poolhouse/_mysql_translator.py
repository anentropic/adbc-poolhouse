"""MySQL ADBC parameter translator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from adbc_poolhouse._mysql_config import MySQLConfig


def translate_mysql(config: MySQLConfig) -> dict[str, str]:
    """
    Translate MySQLConfig to ADBC driver kwargs.

    Supports two modes:

    - **URI mode** (``uri`` set): the URI is passed directly as the ``uri``
      kwarg. URI may embed credentials — stored as ``SecretStr`` to prevent
      accidental logging.
    - **Decomposed mode** (``host``, ``user``, ``database`` set): constructs
      the MySQL Go DSN URI ``user:pass@tcp(host:port)/db``.
      The password is URL-encoded via :func:`urllib.parse.quote` with
      ``safe=""`` so special characters (``+``, ``=``, ``/``, ``@``) are
      percent-encoded and do not corrupt the URI. When ``password`` is
      ``None``, the ``:pass`` segment is omitted entirely.

    The config validator ensures at least one mode is fully specified before
    this function is called.

    Args:
        config: A validated ``MySQLConfig`` instance.

    Returns:
        A ``dict[str, str]`` of ADBC driver kwargs for
        ``adbc_driver_manager.dbapi.connect()``.

    Examples:
        >>> from pydantic import SecretStr
        >>> from adbc_poolhouse._mysql_config import MySQLConfig
        >>> from adbc_poolhouse._mysql_translator import translate_mysql
        >>> config = MySQLConfig(
        ...     host="localhost",
        ...     user="root",
        ...     password=SecretStr("secret"),
        ...     database="demo",
        ... )
        >>> result = translate_mysql(config)
        >>> result["uri"]
        'root:secret@tcp(localhost:3306)/demo'
    """
    if config.uri is not None:
        return {"uri": config.uri.get_secret_value()}

    # Decomposed mode — model_validator guarantees host, user, database are set
    assert config.host is not None
    assert config.user is not None
    assert config.database is not None

    user = config.user
    host = config.host
    port = config.port
    db = config.database

    if config.password is not None:
        encoded_pass = quote(config.password.get_secret_value(), safe="")
        uri = f"{user}:{encoded_pass}@tcp({host}:{port})/{db}"
    else:
        uri = f"{user}@tcp({host}:{port})/{db}"

    return {"uri": uri}
