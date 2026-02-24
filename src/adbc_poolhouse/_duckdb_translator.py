"""DuckDB ADBC driver kwargs translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._duckdb_config import DuckDBConfig


def translate_duckdb(config: DuckDBConfig) -> dict[str, str]:
    """
    Translate DuckDBConfig to ADBC driver kwargs.

    Returns:
        Dict with 'path' key (always) and 'access_mode' = 'READ_ONLY' when
        config.read_only is True. All values are strings.

    Note:
        DuckDB driver uses 'path' (not 'database') and 'access_mode' (not 'read_only').
        Entrypoint 'duckdb_adbc_init' must be passed separately to dbapi.connect().
        Verified against duckdb docs and live testing.
    """
    kwargs: dict[str, str] = {"path": config.database}
    if config.read_only:
        kwargs["access_mode"] = "READ_ONLY"
    return kwargs
