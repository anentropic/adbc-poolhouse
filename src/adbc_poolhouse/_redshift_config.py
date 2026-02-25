"""Redshift warehouse configuration."""

from __future__ import annotations

from pydantic import SecretStr  # noqa: TC002
from pydantic_settings import SettingsConfigDict

from adbc_poolhouse._base_config import BaseWarehouseConfig


class RedshiftConfig(BaseWarehouseConfig):
    """
    Redshift warehouse configuration.

    Uses the Columnar ADBC Redshift driver (Foundry-distributed, not on
    PyPI). Supports provisioned clusters (standard and IAM auth) and
    Redshift Serverless.

    Pool tuning fields are inherited and loaded from REDSHIFT_* env vars.

    Note: This driver is distributed via the ADBC Driver Foundry, not PyPI.
    See project Phase 7 documentation for Foundry installation instructions.
    """

    model_config = SettingsConfigDict(env_prefix="REDSHIFT_")

    uri: str | None = None
    """Connection URI: redshift://[user:password@]host[:port]/dbname[?params]
    Use redshift:///dbname for automatic endpoint discovery.
    Env: REDSHIFT_URI."""

    cluster_type: str | None = None
    """Cluster variant: 'redshift' (standard), 'redshift-iam', or
    'redshift-serverless'. Env: REDSHIFT_CLUSTER_TYPE."""

    cluster_identifier: str | None = None
    """Provisioned cluster identifier (required for IAM auth).
    Env: REDSHIFT_CLUSTER_IDENTIFIER."""

    workgroup_name: str | None = None
    """Serverless workgroup name. Env: REDSHIFT_WORKGROUP_NAME."""

    aws_region: str | None = None
    """AWS region (e.g. 'us-west-2'). Env: REDSHIFT_AWS_REGION."""

    aws_access_key_id: str | None = None
    """AWS IAM access key ID. Env: REDSHIFT_AWS_ACCESS_KEY_ID."""

    aws_secret_access_key: SecretStr | None = None
    """AWS IAM secret access key. Env: REDSHIFT_AWS_SECRET_ACCESS_KEY."""

    sslmode: str | None = None
    """SSL mode (e.g. 'require', 'verify-full'). Env: REDSHIFT_SSLMODE."""
