"""Trino ADBC parameter translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._trino_config import TrinoConfig


def translate_trino(config: TrinoConfig) -> dict[str, str]:
    """
    Translate TrinoConfig to ADBC driver kwargs.

    Trino uses URI-based or decomposed field connection specification.
    Driver name: 'trino'. Verified from docs.adbc-drivers.org.

    When uri is provided, it takes precedence. Otherwise, individual fields
    are mapped to their ADBC key equivalents.
    """
    kwargs: dict[str, str] = {}

    # URI-first: if uri is set, use it as the primary connection spec
    if config.uri is not None:
        kwargs["uri"] = config.uri
        return kwargs

    # Decomposed fields (include only if not None)
    if config.host is not None:
        kwargs["host"] = config.host  # LOW confidence key name
    if config.port is not None:
        kwargs["port"] = str(config.port)  # LOW confidence key name
    if config.user is not None:
        kwargs["username"] = config.user  # LOW confidence key name
    if config.password is not None:
        # LOW confidence key name  # pragma: allowlist secret
        kwargs["password"] = config.password.get_secret_value()
    if config.catalog is not None:
        kwargs["catalog"] = config.catalog  # LOW confidence key name
    # CRITICAL: Python attribute is schema_ (trailing underscore); use config.schema_
    if config.schema_ is not None:
        kwargs["schema"] = config.schema_  # LOW confidence key name

    # SSL fields (bool -> 'true'/'false' strings)
    kwargs["ssl"] = str(config.ssl).lower()  # LOW confidence key name
    kwargs["ssl_verify"] = str(config.ssl_verify).lower()  # LOW confidence key name

    if config.source is not None:
        kwargs["source"] = config.source  # LOW confidence key name

    return kwargs
