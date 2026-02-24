"""PostgreSQL ADBC driver kwargs translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._postgresql_config import PostgreSQLConfig


def translate_postgresql(config: PostgreSQLConfig) -> dict[str, str]:
    """
    Translate PostgreSQLConfig to ADBC driver kwargs.

    Returns:
        Dict with 'uri' key (if set). May be empty if uri is None.

    Note:
        'adbc.postgresql.use_copy' is a StatementOptions key — it is NOT a
        database-level kwarg and cannot be passed to dbapi.connect(). The
        use_copy field is intentionally omitted here. Phase 5 must handle it
        at the cursor level if needed.
        Verified against installed adbc_driver_postgresql source.
    """
    kwargs: dict[str, str] = {}
    if config.uri is not None:
        kwargs["uri"] = config.uri
    return kwargs
