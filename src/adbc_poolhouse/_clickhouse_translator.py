"""ClickHouse ADBC parameter translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._clickhouse_config import ClickHouseConfig


def translate_clickhouse(config: ClickHouseConfig) -> dict[str, str]:
    """
    Translate ClickHouseConfig to ADBC driver kwargs.

    Supports two modes:

    - **URI mode** (``uri`` set): the URI is passed directly as the ``uri``
      kwarg. URI may embed credentials — stored as ``SecretStr`` to prevent
      accidental logging.
    - **Decomposed mode** (``host`` and ``username`` set): returns individual
      kwargs directly (``username``, ``host``, ``port``, and optionally
      ``password`` and ``database``). Unlike MySQL, ClickHouse does not use
      a URI string for decomposed mode — the Columnar driver accepts these
      kwargs directly.

    The config validator ensures at least one mode is fully specified before
    this function is called.

    Args:
        config: A validated ``ClickHouseConfig`` instance.

    Returns:
        A ``dict[str, str]`` of ADBC driver kwargs for
        ``adbc_driver_manager.dbapi.connect()``.

    Examples:
        >>> from adbc_poolhouse._clickhouse_config import ClickHouseConfig
        >>> from adbc_poolhouse._clickhouse_translator import translate_clickhouse
        >>> config = ClickHouseConfig(
        ...     host="localhost",
        ...     username="default",
        ...     database="mydb",
        ... )
        >>> result = translate_clickhouse(config)
        >>> result["username"]
        'default'
        >>> result["port"]
        '8123'
    """
    if config.uri is not None:
        return {"uri": config.uri.get_secret_value()}

    # Decomposed mode — model_validator guarantees host and username are set
    assert config.host is not None
    assert config.username is not None

    kwargs: dict[str, str] = {
        "username": config.username,
        "host": config.host,
        "port": str(config.port),
    }
    if config.password is not None:
        kwargs["password"] = config.password.get_secret_value()
    if config.database is not None:
        kwargs["database"] = config.database
    return kwargs
