"""Teradata warehouse configuration."""

from __future__ import annotations

# TODO(teradata): Verify all field names against the installed Columnar ADBC
# Teradata driver when available. Fields below are triangulated from the
# Teradata JDBC driver and teradatasql Python driver parameter names.
# As of 2026-02-25, Teradata is not listed in the ADBC Driver Foundry
# (docs.adbc-drivers.org); the driver may be distributed separately or
# not yet released. Verify field names before production use.
from pydantic import SecretStr  # noqa: TC002
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class TeradataConfig(BaseWarehouseConfig):
    """
    Teradata warehouse configuration.

    Uses the Columnar ADBC Teradata driver.

    .. warning::
        As of 2026-02-25, Teradata is not listed in the ADBC Driver Foundry
        (docs.adbc-drivers.org). The driver may be distributed separately or
        not yet released. Field names are triangulated from the Teradata JDBC
        driver and teradatasql Python driver documentation; verify against the
        actual installed driver before production use.

    Pool tuning fields are inherited and loaded from TERADATA_* env vars.
    """

    model_config = SettingsConfigDict(env_prefix="TERADATA_")

    host: str | None = None
    """Teradata server hostname.
    Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.
    Env: TERADATA_HOST."""

    user: str | None = None
    """Database username.
    Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.
    Env: TERADATA_USER."""

    password: SecretStr | None = None
    """Database password.
    Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.
    Env: TERADATA_PASSWORD."""

    database: str | None = None
    """Default database (Teradata term for schema/namespace).
    Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.
    Env: TERADATA_DATABASE."""

    port: int | None = None
    """Connection port. Teradata default: 1025.
    Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.
    Env: TERADATA_PORT."""

    logmech: str | None = None
    """Logon mechanism: 'TD2' (default), 'LDAP', 'KRB5', 'TDNEGO'.
    Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.
    Env: TERADATA_LOGMECH."""

    tmode: str | None = None
    """Transaction mode: 'ANSI' or 'TERA'.
    Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.
    Env: TERADATA_TMODE."""

    sslmode: str | None = None
    """SSL mode: 'DISABLE', 'ALLOW', 'PREFER', 'REQUIRE', 'VERIFY-CA', 'VERIFY-FULL'.
    Source: Teradata JDBC / teradatasql driver docs. Verify against Columnar ADBC driver.
    Env: TERADATA_SSLMODE."""

    uri: str | None = None
    """Full URI if the Columnar driver supports URI-based connection.
    Source: Inferred from Foundry driver URI patterns; unconfirmed for Teradata.
    Verify against Columnar ADBC driver.
    Env: TERADATA_URI."""
