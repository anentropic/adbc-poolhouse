"""SQLite ADBC driver kwargs translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._sqlite_config import SQLiteConfig


def translate_sqlite(config: SQLiteConfig) -> dict[str, str]:
    """
    Translate SQLiteConfig to ADBC driver kwargs.

    Returns:
        Dict with a single 'uri' key mapped to the database path or
        ':memory:'. All values are strings.

    Note:
        SQLite driver uses 'uri' (not 'path' — that is DuckDB's key).
        The translator is intentionally minimal: only one key is emitted.
    """
    return {"uri": config.database}
