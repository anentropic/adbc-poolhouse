"""
Type aliases for the adbc-poolhouse pool assembly layer.

This module holds type aliases that Phase 5 needs to annotate the pool
creator callable. All ``cast()`` calls that reconcile ADBC connection types
with SQLAlchemy protocol expectations are concentrated here and in
``_driver_api.py``.

Internal only — not exported from ``__init__.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_driver_manager.dbapi import Connection


# Type alias for the callable that QueuePool.creator expects.
# QueuePool requires Callable[[], DBAPIConnection] but ADBC's Connection
# type does not satisfy SQLAlchemy's internal _DBAPIConnection Protocol
# without a cast(). Phase 5 uses this alias as the cast target.
AdbcCreatorFn = Callable[[], "Connection"]
