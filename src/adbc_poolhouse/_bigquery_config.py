"""BigQuery warehouse configuration."""

from __future__ import annotations

from pydantic import SecretStr  # noqa: TC002
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class BigQueryConfig(BaseWarehouseConfig):
    """
    BigQuery warehouse configuration.

    Supports SDK default auth (ADC), JSON credential file, JSON credential
    string, and user authentication flows.

    Pool tuning fields are inherited and loaded from BIGQUERY_* env vars.
    """

    model_config = SettingsConfigDict(env_prefix="BIGQUERY_")

    auth_type: str | None = None
    """Auth method: 'bigquery' (SDK default/ADC), 'json_credential_file',
    'json_credential_string', 'user_authentication'. Env: BIGQUERY_AUTH_TYPE."""

    auth_credentials: SecretStr | None = None
    """JSON credentials file path or encoded credential string, depending on
    auth_type. Env: BIGQUERY_AUTH_CREDENTIALS."""

    auth_client_id: str | None = None
    """OAuth client ID for user_authentication flow. Env: BIGQUERY_AUTH_CLIENT_ID."""

    auth_client_secret: SecretStr | None = None
    """OAuth client secret for user_authentication flow. Env: BIGQUERY_AUTH_CLIENT_SECRET."""

    auth_refresh_token: SecretStr | None = None
    """OAuth refresh token for user_authentication flow. Env: BIGQUERY_AUTH_REFRESH_TOKEN."""

    project_id: str | None = None
    """GCP project ID. Env: BIGQUERY_PROJECT_ID."""

    dataset_id: str | None = None
    """Default dataset. Env: BIGQUERY_DATASET_ID."""
