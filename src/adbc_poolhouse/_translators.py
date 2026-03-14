"""
Translate any warehouse config to ADBC driver kwargs.

Delegates to each config's ``to_adbc_kwargs()`` method. All 12 built-in
backends implement this method directly on their config class.

Internal only -- not exported from ``__init__.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig


def translate_config(config: WarehouseConfig) -> dict[str, str]:
    """
    Translate any supported warehouse config to ADBC driver kwargs.

    Delegates to the config's ``to_adbc_kwargs()`` method.

    Returns:
        A dict[str, str] of kwargs to pass as ``db_kwargs`` to
        ``adbc_driver_manager.dbapi.connect()``. All values are strings.

    Raises:
        BackendNotRegisteredError: If ``config`` is not a recognised
            WarehouseConfig subclass.
    """
    from adbc_poolhouse._registry import ensure_registered

    ensure_registered(config)

    return config.to_adbc_kwargs()
