"""Redshift warehouse configuration."""

from __future__ import annotations

from urllib.parse import quote

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
    See the installation guide for Foundry setup instructions.
    """

    model_config = SettingsConfigDict(env_prefix="REDSHIFT_")

    uri: str | None = None
    """Connection URI: redshift://[user:password@]host[:port]/dbname[?params]
    Use redshift:///dbname for automatic endpoint discovery.
    Env: REDSHIFT_URI."""

    host: str | None = None
    """Redshift cluster hostname. Alternative to URI. Env: REDSHIFT_HOST."""

    port: int | None = None
    """Port number. Default: 5439. Env: REDSHIFT_PORT."""

    user: str | None = None
    """Database username. Env: REDSHIFT_USER."""

    password: SecretStr | None = None
    """Database password. Env: REDSHIFT_PASSWORD."""

    database: str | None = None
    """Target database name. Env: REDSHIFT_DATABASE."""

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

    def _driver_path(self) -> str:
        return "redshift"

    def to_adbc_kwargs(self) -> dict[str, str]:
        """
        Convert Redshift config fields to ADBC driver kwargs.

        Supports two connection modes:

        - **URI mode** (``uri`` set): passed directly as ``{"uri": ...}``.
        - **Decomposed mode**: builds a ``redshift://`` URI from ``host``,
          ``port``, ``user``, ``password``, ``database``, and ``sslmode``.
          Password is URL-encoded via `urllib.parse.quote` with
          ``safe=""``.

        IAM and cluster fields (``cluster_type``, ``cluster_identifier``,
        ``workgroup_name``, ``aws_region``, ``aws_access_key_id``,
        ``aws_secret_access_key``) are always translated as separate driver
        kwargs when set, regardless of connection mode.

        Returns:
            ADBC driver kwargs for ``adbc_driver_manager.dbapi.connect()``.
        """
        kwargs: dict[str, str] = {}

        # URI: explicit passthrough or build from individual fields
        if self.uri is not None:
            kwargs["uri"] = self.uri
        elif any([self.host, self.user, self.password, self.database, self.sslmode]):
            kwargs["uri"] = self._build_uri()

        # IAM/cluster params
        if self.cluster_type is not None:
            kwargs["redshift.cluster_type"] = self.cluster_type
        if self.cluster_identifier is not None:
            kwargs["redshift.cluster_identifier"] = self.cluster_identifier
        if self.workgroup_name is not None:
            kwargs["redshift.workgroup_name"] = self.workgroup_name
        if self.aws_region is not None:
            kwargs["aws_region"] = self.aws_region
        if self.aws_access_key_id is not None:
            kwargs["aws_access_key_id"] = self.aws_access_key_id
        if self.aws_secret_access_key is not None:
            kwargs["aws_secret_access_key"] = self.aws_secret_access_key.get_secret_value()

        return kwargs

    def _build_uri(self) -> str:
        """Build a redshift:// URI from individual fields."""
        uri = "redshift://"

        if self.user is not None:
            uri += quote(self.user, safe="")
            if self.password is not None:
                uri += ":" + quote(self.password.get_secret_value(), safe="")
            uri += "@"

        if self.host is not None:
            uri += self.host

        if self.port is not None:
            uri += f":{self.port}"

        if self.database is not None:
            uri += f"/{self.database}"

        if self.sslmode is not None:
            uri += f"?sslmode={self.sslmode}"

        return uri
