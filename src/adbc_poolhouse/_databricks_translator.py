"""Databricks ADBC parameter translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._databricks_config import DatabricksConfig


def translate_databricks(config: DatabricksConfig) -> dict[str, str]:
    """
    Translate DatabricksConfig to ADBC driver kwargs.

    Databricks uses URI-only connection model. Driver name: 'databricks'.
    Verified from docs.adbc-drivers.org.
    Note: DatabricksConfig.uri is SecretStr (URI may embed PAT token).
    """
    kwargs: dict[str, str] = {}
    if config.uri is not None:
        kwargs["uri"] = config.uri.get_secret_value()
    return kwargs
