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

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert config to ADBC driver connection kwargs.

        All keys use the ``adbc.bigquery.sql.*`` prefix verified from the
        ``adbc_driver_bigquery.DatabaseOptions`` enum. Only non-None fields
        are included.

        Returns:
            Dict of ADBC driver kwargs. Empty when no fields are set.
        """
        kwargs: dict[str, str] = {}
        if self.auth_type is not None:
            kwargs["adbc.bigquery.sql.auth_type"] = self.auth_type
        if self.auth_credentials is not None:
            kwargs["adbc.bigquery.sql.auth_credentials"] = self.auth_credentials.get_secret_value()
        if self.auth_client_id is not None:
            kwargs["adbc.bigquery.sql.auth.client_id"] = self.auth_client_id
        if self.auth_client_secret is not None:
            kwargs["adbc.bigquery.sql.auth.client_secret"] = (
                self.auth_client_secret.get_secret_value()
            )
        if self.auth_refresh_token is not None:
            kwargs["adbc.bigquery.sql.auth.refresh_token"] = (
                self.auth_refresh_token.get_secret_value()
            )
        if self.project_id is not None:
            kwargs["adbc.bigquery.sql.project_id"] = self.project_id
        if self.dataset_id is not None:
            kwargs["adbc.bigquery.sql.dataset_id"] = self.dataset_id
        return kwargs
