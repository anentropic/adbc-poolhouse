"""Unit tests for BaseWarehouseConfig and WarehouseConfig Protocol."""

from __future__ import annotations

import pytest

from adbc_poolhouse._base_config import BaseWarehouseConfig, WarehouseConfig


class TestWarehouseConfigProtocol:
    """Verify WarehouseConfig Protocol declares to_adbc_kwargs()."""

    def test_protocol_has_to_adbc_kwargs(self) -> None:
        """WarehouseConfig Protocol declares to_adbc_kwargs() method."""
        assert hasattr(WarehouseConfig, "to_adbc_kwargs")

    def test_concrete_class_satisfies_protocol(self) -> None:
        """A concrete class with to_adbc_kwargs() satisfies WarehouseConfig Protocol."""

        class ConcreteConfig:
            pool_size: int = 5
            max_overflow: int = 3
            timeout: int = 30
            recycle: int = 3600

            def _adbc_entrypoint(self) -> str | None:
                return None

            def to_adbc_kwargs(self) -> dict[str, str]:
                return {"key": "value"}

        assert isinstance(ConcreteConfig(), WarehouseConfig)


class TestBaseWarehouseConfig:
    """Verify BaseWarehouseConfig.to_adbc_kwargs() raises NotImplementedError."""

    def test_to_adbc_kwargs_raises_not_implemented(self) -> None:
        """BaseWarehouseConfig.to_adbc_kwargs() raises NotImplementedError."""
        config = BaseWarehouseConfig()
        with pytest.raises(NotImplementedError, match="BaseWarehouseConfig must implement"):
            config.to_adbc_kwargs()
