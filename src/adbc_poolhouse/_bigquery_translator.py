"""BigQuery ADBC driver kwargs translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._bigquery_config import BigQueryConfig


def translate_bigquery(config: BigQueryConfig) -> dict[str, str]:
    """
    Translate BigQueryConfig to ADBC driver kwargs.

    All keys verified from installed adbc_driver_bigquery.DatabaseOptions enum.
    Only non-None fields are included in the output dict.
    """
    kwargs: dict[str, str] = {}
    if config.auth_type is not None:
        kwargs["adbc.bigquery.sql.auth_type"] = config.auth_type
    if config.auth_credentials is not None:
        kwargs["adbc.bigquery.sql.auth_credentials"] = config.auth_credentials.get_secret_value()
    if config.auth_client_id is not None:
        kwargs["adbc.bigquery.sql.auth.client_id"] = config.auth_client_id
    if config.auth_client_secret is not None:
        kwargs["adbc.bigquery.sql.auth.client_secret"] = (
            config.auth_client_secret.get_secret_value()
        )
    if config.auth_refresh_token is not None:
        kwargs["adbc.bigquery.sql.auth.refresh_token"] = (
            config.auth_refresh_token.get_secret_value()
        )
    if config.project_id is not None:
        kwargs["adbc.bigquery.sql.project_id"] = config.project_id
    if config.dataset_id is not None:
        kwargs["adbc.bigquery.sql.dataset_id"] = config.dataset_id
    return kwargs
