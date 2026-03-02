"""ClickHouse warehouse configuration."""

from __future__ import annotations

from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class ClickHouseConfig(BaseWarehouseConfig):
    """
    ClickHouse warehouse configuration.

    Uses the Columnar ADBC ClickHouse driver (Foundry-distributed, not on
    PyPI). Install via the ADBC Driver Foundry:

        dbc install --pre clickhouse

    The ``--pre`` flag is required — only alpha releases are available
    (v0.1.0-alpha.1).

    Supports two connection modes:

    - URI mode: set ``uri`` with the full ClickHouse connection string.
    - Decomposed mode: set ``host`` and ``username`` together. ``password``,
      ``database``, and ``port`` are optional. ``port`` defaults to 8123
      (HTTP interface).

    At least one mode must be fully specified — construction raises
    ``ConfigurationError`` if neither is provided.

    Note: The field name is ``username``, not ``user``. The Columnar
    ClickHouse driver uses ``username`` as the kwarg key. Passing ``user``
    causes a silent auth failure.

    Pool tuning fields are inherited and loaded from CLICKHOUSE_* env vars.

    Note: This driver is distributed via the ADBC Driver Foundry, not PyPI.
    See the installation guide for Foundry setup instructions.
    """

    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_")

    uri: SecretStr | None = None
    """Full ClickHouse connection URI. May contain credentials — stored as
    SecretStr. Env: CLICKHOUSE_URI."""

    host: str | None = None
    """ClickHouse hostname. Alternative to embedding host in URI.
    Env: CLICKHOUSE_HOST."""

    port: int = 8123
    """ClickHouse HTTP interface port. Default: 8123. Env: CLICKHOUSE_PORT."""

    username: str | None = None
    """ClickHouse username. Maps to the ``username`` driver kwarg (not ``user``).
    Env: CLICKHOUSE_USERNAME."""

    password: SecretStr | None = None
    """ClickHouse password. Optional. Env: CLICKHOUSE_PASSWORD."""

    database: str | None = None
    """ClickHouse database name. Optional. Env: CLICKHOUSE_DATABASE."""

    @model_validator(mode="after")
    def check_connection_spec(self) -> Self:
        """Raise ConfigurationError if neither uri nor minimum decomposed fields are set."""
        has_uri = self.uri is not None
        has_decomposed = self.host is not None and self.username is not None
        if not has_uri and not has_decomposed:
            raise ConfigurationError(
                "ClickHouseConfig requires either 'uri' or at minimum "
                "'host' and 'username'. Got none of these."
            )
        return self
