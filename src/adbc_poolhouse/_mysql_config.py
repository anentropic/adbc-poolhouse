"""MySQL warehouse configuration."""

from __future__ import annotations

from typing import Self
from urllib.parse import quote

from pydantic import SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig
from adbc_poolhouse._exceptions import ConfigurationError  # noqa: TC001


class MySQLConfig(BaseWarehouseConfig):
    """
    MySQL warehouse configuration.

    Uses the Columnar ADBC MySQL driver (Foundry-distributed, not on
    PyPI). Install via the ADBC Driver Foundry (see DEVELOP.md for
    setup instructions).

    Supports two connection modes:

    - URI mode: set ``uri`` with the full MySQL connection string.
    - Decomposed mode: set ``host``, ``user``, and ``database`` together.
      ``password`` is optional — MySQL supports passwordless connections.
      ``port`` defaults to 3306.

    At least one mode must be fully specified — construction raises
    ``ConfigurationError`` if neither is provided.

    Pool tuning fields are inherited and loaded from MYSQL_* env vars.

    Note: This driver is distributed via the ADBC Driver Foundry, not PyPI.
    See the installation guide for Foundry setup instructions.
    """

    model_config = SettingsConfigDict(env_prefix="MYSQL_")

    uri: SecretStr | None = None
    """Full MySQL connection URI. May contain credentials — stored as
    SecretStr. Env: MYSQL_URI."""

    host: str | None = None
    """MySQL hostname. Alternative to embedding host in URI.
    Env: MYSQL_HOST."""

    port: int = 3306
    """MySQL port. Default: 3306. Env: MYSQL_PORT."""

    user: str | None = None
    """MySQL username. Env: MYSQL_USER."""

    password: SecretStr | None = None
    """MySQL password. Optional — MySQL supports passwordless connections.
    Env: MYSQL_PASSWORD."""

    database: str | None = None
    """MySQL database name. Env: MYSQL_DATABASE."""

    @model_validator(mode="after")
    def check_connection_spec(self) -> Self:
        """Raise ConfigurationError if neither uri nor all minimum decomposed fields are set."""
        has_uri = self.uri is not None
        has_decomposed = (
            self.host is not None and self.user is not None and self.database is not None
        )
        if not has_uri and not has_decomposed:
            raise ConfigurationError(
                "MySQLConfig requires either 'uri' or all of 'host', 'user', "
                "and 'database'. Got none of these."
            )
        return self

    def _driver_path(self) -> str:
        return "mysql"

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert MySQL config fields to ADBC driver kwargs.

        Supports two modes:

        - **URI mode** (``uri`` set): extracts ``SecretStr`` value and returns
          ``{"uri": ...}``.
        - **Decomposed mode**: builds a Go DSN from ``user``, ``password``,
          ``host``, ``port``, and ``database``. Password is URL-encoded via
          `urllib.parse.quote` with ``safe=""``.

        Returns:
            ADBC driver kwargs for ``adbc_driver_manager.dbapi.connect()``.
        """
        if self.uri is not None:
            return {"uri": self.uri.get_secret_value()}

        # Decomposed mode -- model_validator guarantees host, user, database.
        assert self.host is not None
        assert self.user is not None
        assert self.database is not None

        if self.password is not None:
            encoded_pass = quote(self.password.get_secret_value(), safe="")
            uri = f"{self.user}:{encoded_pass}@tcp({self.host}:{self.port})/{self.database}"
        else:
            uri = f"{self.user}@tcp({self.host}:{self.port})/{self.database}"

        return {"uri": uri}
