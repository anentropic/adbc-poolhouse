"""Microsoft SQL Server / Azure SQL / Azure Fabric / Synapse Analytics configuration."""

from __future__ import annotations

from pydantic import SecretStr  # noqa: TC002
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class MSSQLConfig(BaseWarehouseConfig):
    """
    Microsoft SQL Server / Azure SQL / Azure Fabric / Synapse Analytics configuration.

    Uses the Columnar ADBC MSSQL driver (Foundry-distributed, not on PyPI).
    One class covers all Microsoft SQL variants via optional variant-specific fields:
    - SQL Server: use host + port + instance (or URI)
    - Azure SQL: use host + port, optionally fedauth for Entra ID / Azure AD auth
    - Azure Fabric / Synapse Analytics: use fedauth for managed identity or
      service principal authentication

    Pool tuning fields are inherited and loaded from MSSQL_* env vars.

    Note: This driver is distributed via the ADBC Driver Foundry, not PyPI.
    See project Phase 7 documentation for Foundry installation instructions.
    """

    model_config = SettingsConfigDict(env_prefix="MSSQL_")

    uri: str | None = None
    """Connection URI: mssql://user:pass@host[:port][/instance][?params]  # pragma: allowlist secret
    Also accepts sqlserver:// scheme. Env: MSSQL_URI."""

    host: str | None = None
    """Hostname or IP address. Alternative to URI-based connection.
    Env: MSSQL_HOST."""

    port: int | None = None
    """Port number. Default: 1433. Env: MSSQL_PORT."""

    instance: str | None = None
    """SQL Server named instance (e.g. 'SQLExpress'). Env: MSSQL_INSTANCE."""

    user: str | None = None
    """SQL auth username. Env: MSSQL_USER."""

    password: SecretStr | None = None
    """SQL auth password. Env: MSSQL_PASSWORD."""

    database: str | None = None
    """Target database name. Env: MSSQL_DATABASE."""

    trust_server_certificate: bool = False
    """Accept self-signed TLS certificates. Enable for local development.
    Env: MSSQL_TRUST_SERVER_CERTIFICATE."""

    connection_timeout: int | None = None
    """Connection timeout in seconds. Env: MSSQL_CONNECTION_TIMEOUT."""

    fedauth: str | None = None
    """Federated authentication method for Entra ID / Azure AD.
    Used for Azure SQL, Azure Fabric, and Synapse Analytics.
    Values: 'ActiveDirectoryPassword', 'ActiveDirectoryMsi',
    'ActiveDirectoryServicePrincipal', 'ActiveDirectoryInteractive'.
    Env: MSSQL_FEDAUTH."""
