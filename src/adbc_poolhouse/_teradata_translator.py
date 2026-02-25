"""
Teradata ADBC parameter translator.

TODO: LOW CONFIDENCE -- TeradataConfig field names were triangulated from Teradata JDBC
and teradatasql Python driver docs. As of 2026-02-25, Teradata is not listed in the
ADBC Driver Foundry (docs.adbc-drivers.org); the driver may be distributed separately
or not yet released. Verify field names against the actual driver when available.
Driver name: 'teradata' (LOW confidence -- inferred from Foundry naming pattern).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._teradata_config import TeradataConfig


def translate_teradata(config: TeradataConfig) -> dict[str, str]:
    """
    Translate TeradataConfig to ADBC driver kwargs.

    WARNING: LOW confidence. Teradata Foundry driver docs were unavailable (404)
    at research time. Field names triangulated from JDBC and teradatasql docs.
    Verify against actual driver before production use.
    """
    kwargs: dict[str, str] = {}

    # URI-first: if uri field exists on config, use it
    if config.uri is not None:
        kwargs["uri"] = config.uri
        return kwargs

    # Individual fields as fallback (LOW confidence key names)
    # Key names are inferred from Teradata JDBC / teradatasql Python driver parameter names.
    # Verify against installed Columnar ADBC Teradata driver before production use.
    if config.host is not None:
        kwargs["host"] = config.host  # LOW confidence key name
    if config.user is not None:
        kwargs["user"] = config.user  # LOW confidence key name
    if config.password is not None:
        # LOW confidence key name  # pragma: allowlist secret
        kwargs["password"] = config.password.get_secret_value()
    if config.database is not None:
        kwargs["database"] = config.database  # LOW confidence key name
    if config.port is not None:
        # LOW confidence key name (teradatasql uses dbs_port)
        kwargs["dbs_port"] = str(config.port)
    if config.logmech is not None:
        kwargs["logmech"] = config.logmech  # LOW confidence key name
    if config.tmode is not None:
        kwargs["tmode"] = config.tmode  # LOW confidence key name
    if config.sslmode is not None:
        kwargs["sslmode"] = config.sslmode  # LOW confidence key name

    return kwargs
