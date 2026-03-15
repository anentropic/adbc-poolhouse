"""Tests for the backend registry and related infrastructure."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from adbc_poolhouse._exceptions import (
    BackendAlreadyRegisteredError,
    BackendNotRegisteredError,
    PoolhouseError,
    RegistryError,
)

if TYPE_CHECKING:
    from collections.abc import Generator


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


@pytest.fixture
def clean_registry() -> Generator[None, Any, None]:
    """Clear registry state before and after each test."""
    from adbc_poolhouse._registry import _config_to_name, _registry

    # Clear before test
    _registry.clear()
    _config_to_name.clear()
    yield
    # Clear after test
    _registry.clear()
    _config_to_name.clear()


class TestRegisterBackend:
    """Tests for register_backend() validation and registration."""

    def test_valid_registration_succeeds(
        self, dummy_backend: dict[str, object], clean_registry: None
    ) -> None:
        """register_backend() with 3 params (no translator) succeeds."""
        from adbc_poolhouse._registry import register_backend

        # Should not raise any exception
        register_backend(
            name=str(dummy_backend["name"]),
            config_class=dummy_backend["config_class"],  # type: ignore[arg-type]
            driver_path=str(dummy_backend["driver_path"]),
        )

    def test_registration_stores_two_tuple(
        self, dummy_backend: dict[str, object], clean_registry: None
    ) -> None:
        """register_backend() stores (config_class, driver_path) 2-tuple."""
        from adbc_poolhouse._registry import _registry, register_backend

        name = str(dummy_backend["name"])
        register_backend(
            name=name,
            config_class=dummy_backend["config_class"],  # type: ignore[arg-type]
            driver_path=str(dummy_backend["driver_path"]),
        )

        entry = _registry[name]
        assert len(entry) == 2
        assert entry[0] is dummy_backend["config_class"]
        assert entry[1] == dummy_backend["driver_path"]

    def test_duplicate_name_raises(
        self, dummy_backend: dict[str, object], clean_registry: None
    ) -> None:
        """register_backend() with duplicate name raises BackendAlreadyRegisteredError."""
        from adbc_poolhouse._registry import register_backend

        name = str(dummy_backend["name"])
        register_backend(
            name=name,
            config_class=dummy_backend["config_class"],  # type: ignore[arg-type]
            driver_path=str(dummy_backend["driver_path"]),
        )

        # Second registration with same name should raise
        with pytest.raises(BackendAlreadyRegisteredError, match=name):
            register_backend(
                name=name,
                config_class=dummy_backend["config_class"],  # type: ignore[arg-type]
                driver_path=str(dummy_backend["driver_path"]),
            )

    def test_none_config_class_raises_type_error(
        self, dummy_backend: dict[str, object], clean_registry: None
    ) -> None:
        """register_backend() with None config_class raises TypeError."""
        from adbc_poolhouse._registry import register_backend

        with pytest.raises(TypeError, match="config_class must be a class"):
            register_backend(
                name="test_backend",
                config_class=None,  # type: ignore[arg-type]
                driver_path=str(dummy_backend["driver_path"]),
            )


class TestRegistryLookup:
    """Tests for get_driver_path() lookup."""

    def test_get_driver_path_returns_correct_path(
        self, dummy_backend: dict[str, object], clean_registry: None
    ) -> None:
        """get_driver_path() returns correct driver_path for registered backend."""
        from adbc_poolhouse._registry import get_driver_path, register_backend

        register_backend(
            name=str(dummy_backend["name"]),
            config_class=dummy_backend["config_class"],  # type: ignore[arg-type]
            driver_path=str(dummy_backend["driver_path"]),
        )

        config = dummy_backend["config_instance"]
        driver_path = get_driver_path(config)  # type: ignore[arg-type]
        assert driver_path == dummy_backend["driver_path"]

    def test_get_driver_path_unregistered_raises(
        self, dummy_backend: dict[str, object], clean_registry: None
    ) -> None:
        """get_driver_path() for unregistered config raises BackendNotRegisteredError."""
        from adbc_poolhouse._registry import get_driver_path

        config = dummy_backend["config_instance"]
        config_type_name = type(config).__name__

        with pytest.raises(BackendNotRegisteredError, match=config_type_name):
            get_driver_path(config)  # type: ignore[arg-type]

    def test_get_translator_not_exported(self) -> None:
        """get_translator is no longer available in the registry module."""
        from adbc_poolhouse import _registry

        assert not hasattr(_registry, "get_translator")


class TestDummyBackend:
    """Tests for the dummy backend fixture."""

    def test_fixture_can_be_registered(
        self, dummy_backend: dict[str, object], clean_registry: None
    ) -> None:
        """The fixture can be used with register_backend()."""
        from adbc_poolhouse._registry import register_backend

        # Should not raise any exception
        register_backend(
            name=str(dummy_backend["name"]),
            config_class=dummy_backend["config_class"],  # type: ignore[arg-type]
            driver_path=str(dummy_backend["driver_path"]),
        )

    def test_registered_dummy_backend_returns_correct_driver_path(
        self, dummy_backend: dict[str, object], clean_registry: None
    ) -> None:
        """Registered dummy backend returns correct driver_path."""
        from adbc_poolhouse._registry import get_driver_path, register_backend

        register_backend(
            name=str(dummy_backend["name"]),
            config_class=dummy_backend["config_class"],  # type: ignore[arg-type]
            driver_path=str(dummy_backend["driver_path"]),
        )

        config = dummy_backend["config_instance"]

        # Verify driver_path
        driver_path = get_driver_path(config)  # type: ignore[arg-type]
        assert driver_path == dummy_backend["driver_path"]


class TestRegistryIntegration:
    """Tests for registry integration with resolve_driver()."""
