"""PostgreSQL warehouse configuration."""

from __future__ import annotations

from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class PostgreSQLConfig(BaseWarehouseConfig):
    """
    PostgreSQL warehouse configuration.

    The PostgreSQL ADBC driver wraps libpq. All connection parameters
    (host, port, user, password, dbname, sslmode, etc.) are specified
    in the URI following libpq connection string format:
    postgresql://user:password@host:5432/dbname?sslmode=require  # pragma: allowlist secret

    Pool tuning fields are inherited and loaded from POSTGRESQL_* env vars.
    """

    model_config = SettingsConfigDict(env_prefix="POSTGRESQL_")

    uri: str | None = None
    """libpq connection URI. Env: POSTGRESQL_URI.
    Format: postgresql://[user[:password]@][host][:port][/dbname][?params]"""

    use_copy: bool = True
    """Use PostgreSQL COPY protocol for bulk query execution (driver default:
    True). Disable if COPY triggers permission errors. Env: POSTGRESQL_USE_COPY."""
