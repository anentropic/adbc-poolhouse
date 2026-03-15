"""Unit tests for BaseWarehouseConfig and WarehouseConfig Protocol."""

from __future__ import annotations

import pytest

from adbc_poolhouse._base_config import BaseWarehouseConfig, WarehouseConfig


class TestWarehouseConfigProtocol:
    """Verify WarehouseConfig Protocol declares expected methods."""

    def test_protocol_has_to_adbc_kwargs(self) -> None:
        """WarehouseConfig Protocol declares to_adbc_kwargs() method."""
        assert hasattr(WarehouseConfig, "to_adbc_kwargs")

    def test_protocol_has_driver_path(self) -> None:
        """WarehouseConfig Protocol declares _driver_path() method."""
        assert hasattr(WarehouseConfig, "_driver_path")

    def test_protocol_has_dbapi_module(self) -> None:
        """WarehouseConfig Protocol declares _dbapi_module() method."""
        assert hasattr(WarehouseConfig, "_dbapi_module")

    def test_concrete_class_satisfies_protocol(self) -> None:
        """A concrete class with all required methods satisfies WarehouseConfig Protocol."""

        class ConcreteConfig:
            pool_size: int = 5
            max_overflow: int = 3
            timeout: int = 30
            recycle: int = 3600

            def _adbc_entrypoint(self) -> str | None:
                return None

            def _driver_path(self) -> str:
                return "test"

            def _dbapi_module(self) -> str | None:
                return None

            def to_adbc_kwargs(self) -> dict[str, str]:
                return {"key": "value"}

        assert isinstance(ConcreteConfig(), WarehouseConfig)


class TestBaseWarehouseConfig:
    """Verify BaseWarehouseConfig is ABC with correct abstract methods."""

    def test_cannot_instantiate_abstract(self) -> None:
        """BaseWarehouseConfig cannot be instantiated directly (ABC enforcement)."""
        with pytest.raises(TypeError, match="abstract method"):
            BaseWarehouseConfig()  # type: ignore[abstract]

    def test_abstract_methods(self) -> None:
        """BaseWarehouseConfig declares to_adbc_kwargs as abstract."""
        assert BaseWarehouseConfig.__abstractmethods__ == frozenset({"to_adbc_kwargs"})
