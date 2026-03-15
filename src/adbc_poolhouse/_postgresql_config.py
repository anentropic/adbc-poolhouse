"""PostgreSQL warehouse configuration."""

from __future__ import annotations

import importlib.util
from urllib.parse import quote

from pydantic import SecretStr  # noqa: TC002
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class PostgreSQLConfig(BaseWarehouseConfig):
    """
    PostgreSQL warehouse configuration.

    The PostgreSQL ADBC driver wraps libpq. Specify the connection either as
    a full URI or via individual fields. If neither is provided, libpq falls
    back to its own environment variables (``PGHOST``, ``PGUSER``, etc.).

    Pool tuning fields are inherited and loaded from POSTGRESQL_* env vars.

    Examples:
        URI mode::

            PostgreSQLConfig(uri="postgresql://me:s3cret@host/mydb")  # pragma: allowlist secret

        Individual fields::

            PostgreSQLConfig(host="db.example.com", user="me", database="mydb")
    """

    model_config = SettingsConfigDict(env_prefix="POSTGRESQL_")

    uri: str | None = None
    """libpq connection URI. Takes precedence over individual fields.
    Format: ``postgresql://[user[:password]@][host][:port][/dbname][?params]``
    Env: POSTGRESQL_URI."""

    host: str | None = None
    """Database hostname or IP address. Env: POSTGRESQL_HOST."""

    port: int | None = None
    """Database port. Defaults to 5432 when omitted. Env: POSTGRESQL_PORT."""

    user: str | None = None
    """Database username. Env: POSTGRESQL_USER."""

    password: SecretStr | None = None
    """Database password. Env: POSTGRESQL_PASSWORD."""

    database: str | None = None
    """Database name. Env: POSTGRESQL_DATABASE."""

    sslmode: str | None = None
    """SSL mode. Accepted values: ``disable``, ``allow``, ``prefer``,
    ``require``, ``verify-ca``, ``verify-full``. Env: POSTGRESQL_SSLMODE."""

    use_copy: bool = True
    """Use PostgreSQL COPY protocol for bulk query execution (driver default:
    True). Disable if COPY triggers permission errors. Env: POSTGRESQL_USE_COPY."""

    def _driver_path(self) -> str:
        return self._resolve_driver_path("adbc_driver_postgresql")

    def _dbapi_module(self) -> str | None:
        if importlib.util.find_spec("adbc_driver_postgresql") is not None:
            return "adbc_driver_postgresql.dbapi"
        return None

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert PostgreSQL config fields to ADBC driver kwargs.

        Supports three modes:

        - **URI mode** (``uri`` set): passed directly as ``{"uri": ...}``.
        - **Decomposed mode**: builds a libpq URI from ``host``, ``port``,
          ``user``, ``password``, ``database``, and ``sslmode``. Password is
          URL-encoded via :func:`urllib.parse.quote` with ``safe=""``.
        - **Empty mode**: returns ``{}`` so libpq resolves from env vars.

        Returns:
            ADBC driver kwargs for ``adbc_driver_manager.dbapi.connect()``.
        """
        if self.uri is not None:
            return {"uri": self.uri}

        # Decomposed mode -- build URI only if at least one field is set.
        has_fields = any([self.host, self.user, self.password, self.database, self.sslmode])
        if not has_fields:
            return {}

        uri = "postgresql://"

        if self.user is not None:
            uri += quote(self.user, safe="")
            if self.password is not None:
                uri += ":" + quote(self.password.get_secret_value(), safe="")
            uri += "@"

        if self.host is not None:
            uri += self.host

        if self.port is not None:
            uri += f":{self.port}"

        if self.database is not None:
            uri += f"/{self.database}"

        if self.sslmode is not None:
            uri += f"?sslmode={self.sslmode}"

        return {"uri": uri}
