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

    def _driver_path(self) -> str:
        return "trino"

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert config to ADBC driver connection kwargs.

        Supports two modes:

        - URI mode (``uri`` set): returns ``{uri: ...}``.
        - Decomposed mode: maps individual fields to their ADBC key
          equivalents. Boolean defaults (``ssl``, ``ssl_verify``) are
          always included as ``'true'``/``'false'`` strings.

        Returns:
            Dict of ADBC driver kwargs for ``adbc_driver_manager.dbapi.connect()``.
        """
        kwargs: dict[str, str] = {}

        # URI-first: if uri is set, use it as the primary connection spec
        if self.uri is not None:
            kwargs["uri"] = self.uri
            return kwargs

        # Decomposed fields (include only if not None)
        if self.host is not None:
            kwargs["host"] = self.host
        if self.port is not None:
            kwargs["port"] = str(self.port)
        if self.user is not None:
            kwargs["username"] = self.user
        if self.password is not None:
            kwargs["password"] = self.password.get_secret_value()  # pragma: allowlist secret
        if self.catalog is not None:
            kwargs["catalog"] = self.catalog
        if self.schema_ is not None:
            kwargs["schema"] = self.schema_

        # SSL fields (bool -> 'true'/'false' strings, always included)
        kwargs["ssl"] = str(self.ssl).lower()
        kwargs["ssl_verify"] = str(self.ssl_verify).lower()

        if self.source is not None:
            kwargs["source"] = self.source

        return kwargs
