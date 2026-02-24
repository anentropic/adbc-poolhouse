"""Teradata warehouse configuration."""

from __future__ import annotations

# TODO(teradata): Verify all field names against the installed Columnar ADBC
# Teradata driver when available. Fields below are triangulated from the
# Teradata JDBC driver and teradatasql Python driver parameter names.
# The Columnar ADBC driver docs page (docs.adbc-drivers.org/drivers/teradata)
# returned 404 at research time (2026-02-24).
from pydantic import SecretStr  # noqa: TC002
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class TeradataConfig(BaseWarehouseConfig):
    """
    Teradata warehouse configuration.

    Uses the Columnar ADBC Teradata driver (Foundry-distributed, not on PyPI).

    .. warning::
        Field names are triangulated from the Teradata JDBC driver and
        teradatasql Python driver documentation. The Columnar ADBC Teradata
        driver documentation was unavailable at research time. Verify field
        names against the installed driver before use in production.

    Pool tuning fields are inherited and loaded from TERADATA_* env vars.

    Note: This driver is distributed via the ADBC Driver Foundry, not PyPI.
    See project Phase 7 documentation for Foundry installation instructions.
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

    def _adbc_driver_key(self) -> str:
        return "teradata"
