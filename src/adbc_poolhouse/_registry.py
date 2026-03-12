"""Backend registry for plugin extensibility."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from adbc_poolhouse._exceptions import (
    BackendAlreadyRegisteredError,
    BackendNotRegisteredError,
)

if TYPE_CHECKING:
    from adbc_poolhouse._base_config import WarehouseConfig


# Type alias for translator function signature
TranslatorFunc = Callable[["WarehouseConfig"], dict[str, str]]

# Registration data: (config_class, translator, driver_path)
_Registration = tuple[type["WarehouseConfig"], TranslatorFunc, str]

# Forward lookup: name → registration
_registry: dict[str, _Registration] = {}

# Reverse lookup: config_class → name (for dispatch)
_config_to_name: dict[type[WarehouseConfig], str] = {}

# Lazy registration functions: config_class → registration function
_lazy_registrations: dict[type[WarehouseConfig], Callable[[], None]] = {}


def register_backend(
    name: str,
    config_class: type[WarehouseConfig],
    translator: TranslatorFunc,
    driver_path: str,
) -> None:
    """
    Register a backend with the registry.

    Args:
        name: Unique backend name (e.g., "adbc_driver_snowflake", "my_custom_backend").
        config_class: The config class for this backend (must be a class, not instance).
        translator: Function that translates config to ADBC connection kwargs.
        driver_path: Path or name passed to adbc_driver_manager.dbapi.connect(driver=...).

    Raises:
        BackendAlreadyRegisteredError: If a backend with this name already exists.
        TypeError: If config_class is not a class or translator is not callable.
    """
    if name in _registry:
        raise BackendAlreadyRegisteredError(name)

    if not isinstance(config_class, type):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"config_class must be a class, got {type(config_class).__name__}")

    if not callable(translator):
        raise TypeError(f"translator must be callable, got {type(translator).__name__}")

    _registry[name] = (config_class, translator, driver_path)
    _config_to_name[config_class] = name


def get_translator(config: WarehouseConfig) -> TranslatorFunc:
    """
    Get the translator function for a config instance.

    Args:
        config: A warehouse config instance.

    Returns:
        The translator function registered for this config type.

    Raises:
        BackendNotRegisteredError: If no backend is registered for this config type.
    """
    config_type = type(config)
    if config_type not in _config_to_name:
        raise BackendNotRegisteredError(config_type.__name__)

    name = _config_to_name[config_type]
    return _registry[name][1]


def get_driver_path(config: WarehouseConfig) -> str:
    """
    Get the driver path for a config instance.

    Args:
        config: A warehouse config instance.

    Returns:
        The driver path registered for this config type.

    Raises:
        BackendNotRegisteredError: If no backend is registered for this config type.
    """
    config_type = type(config)
    if config_type not in _config_to_name:
        raise BackendNotRegisteredError(config_type.__name__)

    name = _config_to_name[config_type]
    return _registry[name][2]


def ensure_registered(config: WarehouseConfig) -> None:
    """
    Ensure the backend for a config is registered.

    If the config type is already registered, returns immediately.
    If a lazy registration function exists, calls it to register the backend.
    Otherwise, raises BackendNotRegisteredError.

    Args:
        config: A warehouse config instance.

    Raises:
        BackendNotRegisteredError: If no backend is registered and no lazy
            registration function exists.
    """
    config_type = type(config)

    # Already registered
    if config_type in _config_to_name:
        return

    # Try lazy registration
    if config_type in _lazy_registrations:
        _lazy_registrations[config_type]()
        # After registration, config_type should be in _config_to_name
        if config_type not in _config_to_name:
            raise BackendNotRegisteredError(config_type.__name__)
        return

    raise BackendNotRegisteredError(config_type.__name__)


def register_lazy(
    config_class: type[WarehouseConfig], registration_func: Callable[[], None]
) -> None:
    """
    Register a lazy initialization function for a config class.

    The registration function will be called the first time a config of this
    type is encountered in ensure_registered(). This is used internally for
    built-in backends to avoid importing all translator modules at startup.

    Args:
        config_class: The config class to register lazily.
        registration_func: A function that, when called, registers the backend.
    """
    _lazy_registrations[config_class] = registration_func
