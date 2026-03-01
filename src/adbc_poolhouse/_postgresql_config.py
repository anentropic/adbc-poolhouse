"""PostgreSQL warehouse configuration."""

from __future__ import annotations

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
