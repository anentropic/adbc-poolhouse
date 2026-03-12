"""Tests for the backend registry and related infrastructure."""

from __future__ import annotations

from adbc_poolhouse._exceptions import (
    BackendAlreadyRegisteredError,
    BackendNotRegisteredError,
    PoolhouseError,
    RegistryError,
)


class TestRegistryExceptions:
    """Tests for the registry exception hierarchy."""

    def test_backend_already_registered_includes_name(self) -> None:
        """BackendAlreadyRegisteredError includes backend name in message."""
        name = "my_custom_backend"
        exc = BackendAlreadyRegisteredError(name)
        assert name in str(exc)
        assert "already registered" in str(exc).lower()

    def test_backend_not_registered_includes_hint(self) -> None:
        """BackendNotRegisteredError includes hint to call register_backend()."""
        config_name = "MyCustomConfig"
        exc = BackendNotRegisteredError(config_name)
        message = str(exc)
        assert config_name in message
        assert "register_backend" in message

    def test_both_exceptions_inherit_from_registry_error(self) -> None:
        """Both registry exceptions inherit from RegistryError."""
        assert issubclass(BackendAlreadyRegisteredError, RegistryError)
        assert issubclass(BackendNotRegisteredError, RegistryError)

    def test_registry_error_inherits_from_poolhouse_error(self) -> None:
        """RegistryError inherits from PoolhouseError."""
        assert issubclass(RegistryError, PoolhouseError)
