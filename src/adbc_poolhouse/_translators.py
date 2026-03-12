"""
Translate any warehouse config to ADBC driver kwargs.

This module is the dispatch coordinator for Phase 4. It imports all
10 per-warehouse translator functions and exposes a single
``translate_config()`` entry point for Phase 5.

Internal only — not exported from ``__init__.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig


def translate_config(config: WarehouseConfig) -> dict[str, str]:
    """
    Translate any supported warehouse config to ADBC driver kwargs.

    Queries the backend registry for the appropriate per-warehouse
    translator function and returns the result dict. All values are strings.

    Returns:
        A dict[str, str] of kwargs to pass as ``db_kwargs`` to
        ``adbc_driver_manager.dbapi.connect()``. All values are strings.

    Raises:
        BackendNotRegisteredError: If ``config`` is not a recognised
            WarehouseConfig subclass.
    """
    from adbc_poolhouse._registry import ensure_registered, get_translator

    ensure_registered(config)
    translator = get_translator(config)
    return translator(config)
