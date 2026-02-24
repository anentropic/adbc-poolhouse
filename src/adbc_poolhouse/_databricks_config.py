"""Databricks warehouse configuration."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class DatabricksConfig(BaseWarehouseConfig):
    """
    Databricks warehouse configuration.

    Uses the Columnar ADBC Databricks driver (Foundry-distributed, not on
    PyPI). Install via the ADBC Driver Foundry.

    Supports PAT (personal access token) and OAuth (U2M and M2M) auth.
    Connection can be specified as a full URI or via decomposed fields.

    Pool tuning fields are inherited and loaded from DATABRICKS_* env vars.

    Note: This driver is distributed via the ADBC Driver Foundry, not PyPI.
    See project Phase 7 documentation for Foundry installation instructions.
    """

    model_config = SettingsConfigDict(env_prefix="DATABRICKS_")

    uri: SecretStr | None = None
    """Full connection URI: databricks://token:<token>@<host>:443/<http-path>
    May contain credentials — stored as SecretStr. Env: DATABRICKS_URI."""

    host: str | None = None
    """Databricks workspace hostname (e.g. 'adb-xxx.azuredatabricks.net').
    Alternative to embedding host in URI. Env: DATABRICKS_HOST."""

    http_path: str | None = None
    """SQL warehouse HTTP path (e.g. '/sql/1.0/warehouses/abc123').
    Env: DATABRICKS_HTTP_PATH."""

    token: SecretStr | None = None
    """Personal access token for PAT auth. Env: DATABRICKS_TOKEN."""

    auth_type: str | None = None
    """OAuth auth type: 'OAuthU2M' (browser-based) or 'OAuthM2M' (service
    principal). Omit for PAT auth. Env: DATABRICKS_AUTH_TYPE."""

    client_id: str | None = None
    """OAuth M2M service principal client ID. Env: DATABRICKS_CLIENT_ID."""

    client_secret: SecretStr | None = None
    """OAuth M2M service principal client secret. Env: DATABRICKS_CLIENT_SECRET."""

    catalog: str | None = None
    """Default Unity Catalog. Env: DATABRICKS_CATALOG."""

    schema_: str | None = Field(default=None, validation_alias="schema", alias="schema")
    """Default schema. Python attribute is schema_ to avoid Pydantic conflicts.
    Env: DATABRICKS_SCHEMA."""

    def _adbc_driver_key(self) -> str:
        return "databricks"
