"""
Translate any warehouse config to ADBC driver kwargs.

Delegates to each config's ``to_adbc_kwargs()`` method. Backends that
have not yet been migrated fall back to the registry-based translator
function during the consolidation transition.

Internal only — not exported from ``__init__.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig


def translate_config(config: WarehouseConfig) -> dict[str, str]:
    """
    Translate any supported warehouse config to ADBC driver kwargs.

    Delegates to the config's ``to_adbc_kwargs()`` method. Falls back
    to the registry translator for backends not yet migrated.

    Returns:
        A dict[str, str] of kwargs to pass as ``db_kwargs`` to
        ``adbc_driver_manager.dbapi.connect()``. All values are strings.

    Raises:
        BackendNotRegisteredError: If ``config`` is not a recognised
            WarehouseConfig subclass.
    """
    from adbc_poolhouse._registry import ensure_registered

    ensure_registered(config)

    try:
        return config.to_adbc_kwargs()
    except NotImplementedError:
        # Transitional fallback: backends not yet migrated to to_adbc_kwargs()
        # still use registry-based translator functions. This path will be
        # removed once all 12 backends implement to_adbc_kwargs().
        from adbc_poolhouse._registry import get_translator

        translator = get_translator(config)
        return translator(config)
