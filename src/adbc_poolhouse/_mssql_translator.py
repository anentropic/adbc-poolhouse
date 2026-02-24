"""Microsoft SQL Server / Azure SQL / Azure Fabric / Synapse Analytics ADBC parameter translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._mssql_config import MSSQLConfig


def translate_mssql(config: MSSQLConfig) -> dict[str, str]:
    """
    Translate MSSQLConfig to ADBC driver kwargs.

    MSSQL supports URI-based or decomposed field connection specification.
    Driver name: 'mssql'. Verified from docs.adbc-drivers.org.

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
    if config.instance is not None:
        kwargs["instance"] = config.instance  # LOW confidence key name
    if config.user is not None:
        kwargs["username"] = config.user  # LOW confidence key name
    if config.password is not None:
        # LOW confidence key name  # pragma: allowlist secret
        kwargs["password"] = config.password.get_secret_value()
    if config.database is not None:
        kwargs["database"] = config.database  # LOW confidence key name

    # Boolean flag (always include)
    # LOW confidence key name
    kwargs["trustServerCertificate"] = str(config.trust_server_certificate).lower()

    if config.connection_timeout is not None:
        kwargs["connectionTimeout"] = str(config.connection_timeout)  # LOW confidence key name
    if config.fedauth is not None:
        kwargs["fedauth"] = config.fedauth  # LOW confidence key name

    return kwargs
