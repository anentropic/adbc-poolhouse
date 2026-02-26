"""Trino warehouse configuration."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class TrinoConfig(BaseWarehouseConfig):
    """
    Trino warehouse configuration.

    Uses the Columnar ADBC Trino driver (Foundry-distributed, not on PyPI).
    Supports URI-based or decomposed field connection specification.

    Pool tuning fields are inherited and loaded from TRINO_* env vars.

    Note: This driver is distributed via the ADBC Driver Foundry, not PyPI.
    See the installation guide for Foundry setup instructions.
    """

    model_config = SettingsConfigDict(env_prefix="TRINO_")

    uri: str | None = None
    """Connection URI. Format: ``trino://[user[:password]@]host[:port][/catalog[/schema]][?params]``
    Env: TRINO_URI."""

    host: str | None = None
    """Trino coordinator hostname. Alternative to URI. Env: TRINO_HOST."""

    port: int | None = None
    """Trino coordinator port. Defaults: 8080 (HTTP), 8443 (HTTPS).
    Env: TRINO_PORT."""

    user: str | None = None
    """Username. Env: TRINO_USER."""

    password: SecretStr | None = None
    """Password (HTTPS connections only). Env: TRINO_PASSWORD."""

    catalog: str | None = None
    """Default catalog. Env: TRINO_CATALOG."""

    schema_: str | None = Field(default=None, validation_alias="schema", alias="schema")
    """Default schema. Python attribute is schema_ to avoid Pydantic conflicts.
    Env: TRINO_SCHEMA."""

    ssl: bool = True
    """Use HTTPS. Disable for local development clusters. Env: TRINO_SSL."""

    ssl_verify: bool = True
    """Verify SSL certificate. Env: TRINO_SSL_VERIFY."""

    source: str | None = None
    """Application identifier sent to Trino coordinator.
    Env: TRINO_SOURCE."""
