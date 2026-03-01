"""Databricks ADBC parameter translator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from adbc_poolhouse._databricks_config import DatabricksConfig


def translate_databricks(config: DatabricksConfig) -> dict[str, str]:
    """
    Translate DatabricksConfig to ADBC driver kwargs.

    Supports two modes:

    - **URI mode** (``uri`` set): the URI is passed directly as the ``uri``
      kwarg. URI may embed the PAT token — stored as ``SecretStr`` to prevent
      accidental logging.
    - **Decomposed mode** (``host``, ``http_path``, ``token`` set): constructs
      the Databricks Go DSN URI ``databricks://token:{encoded}@{host}:443{path}``.
      The token is URL-encoded via :func:`urllib.parse.quote` with ``safe=""``
      so PAT special characters (``+``, ``=``, ``/``, ``@``) are percent-encoded
      and do not corrupt the URI.

    The config validator ensures at least one mode is fully specified before
    this function is called.

    Args:
        config: A validated ``DatabricksConfig`` instance.

    Returns:
        A ``dict[str, str]`` of ADBC driver kwargs for
        ``adbc_driver_manager.dbapi.connect()``.

    Examples:
        >>> from pydantic import SecretStr
        >>> from adbc_poolhouse import DatabricksConfig
        >>> from adbc_poolhouse._databricks_translator import translate_databricks
        >>> config = DatabricksConfig(
        ...     host="host.example.com",
        ...     http_path="/wh/abc",
        ...     token=SecretStr("tok"),  # pragma: allowlist secret
        ... )
        >>> result = translate_databricks(config)
        >>> result["uri"].startswith("databricks://token:")
        True
    """
    if config.uri is not None:
        return {"uri": config.uri.get_secret_value()}

    # Decomposed-field mode — model_validator guarantees all three are set
    assert config.host is not None
    assert config.http_path is not None
    assert config.token is not None

    encoded_token = quote(config.token.get_secret_value(), safe="")
    uri = f"databricks://token:{encoded_token}@{config.host}:443{config.http_path}"
    return {"uri": uri}
