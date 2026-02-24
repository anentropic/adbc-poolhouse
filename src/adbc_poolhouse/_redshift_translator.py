"""Redshift ADBC parameter translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._redshift_config import RedshiftConfig


def translate_redshift(config: RedshiftConfig) -> dict[str, str]:
    """
    Translate RedshiftConfig to ADBC driver kwargs.

    Redshift uses URI-only connection model. Driver name: 'redshift'.
    Verified from docs.adbc-drivers.org.
    Note: RedshiftConfig.uri is plain str (credentials are separate IAM fields).
    """
    kwargs: dict[str, str] = {}
    if config.uri is not None:
        kwargs["uri"] = config.uri
    return kwargs
