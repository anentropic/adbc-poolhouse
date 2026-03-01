"""Redshift ADBC parameter translator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from adbc_poolhouse._redshift_config import RedshiftConfig


def translate_redshift(config: RedshiftConfig) -> dict[str, str]:
    """
    Translate RedshiftConfig to ADBC driver kwargs.

    Supports two connection modes:

    - **URI mode** (``uri`` set): passed directly as the ``uri`` kwarg.
    - **Individual fields mode**: builds a ``redshift://`` URI from ``host``,
      ``port``, ``user``, ``password``, ``database``, and ``sslmode``.
      ``password`` is URL-encoded via :func:`urllib.parse.quote` with
      ``safe=""`` so special characters do not corrupt the connection string.

    IAM and cluster fields (``cluster_type``, ``cluster_identifier``,
    ``workgroup_name``, ``aws_region``, ``aws_access_key_id``,
    ``aws_secret_access_key``) are always translated as separate driver kwargs
    when set, regardless of connection mode.

    Note:
        For IAM/serverless connections that need endpoint discovery
        (``redshift:///dbname``), supply ``uri="redshift:///dbname"`` explicitly.
        Individual fields mode covers standard SQL auth only.

    Args:
        config: A validated ``RedshiftConfig`` instance.

    Returns:
        A ``dict[str, str]`` of ADBC driver kwargs for
        ``adbc_driver_manager.dbapi.connect()``.

    Examples:
        >>> from adbc_poolhouse import RedshiftConfig
        >>> from adbc_poolhouse._redshift_translator import translate_redshift
        >>> result = translate_redshift(RedshiftConfig(uri="redshift://host:5439/mydb"))
        >>> result
        {'uri': 'redshift://host:5439/mydb'}
        >>> result = translate_redshift(
        ...     RedshiftConfig(host="host", user="me", database="mydb")
        ... )
        >>> result["uri"]
        'redshift://me@host/mydb'
    """
    kwargs: dict[str, str] = {}

    # URI: explicit passthrough or build from individual fields
    if config.uri is not None:
        kwargs["uri"] = config.uri
    elif _has_connection_fields(config):
        kwargs["uri"] = _build_uri(config)

    # IAM/cluster params (verified kwarg names from docs.adbc-drivers.org)
    if config.cluster_type is not None:
        kwargs["redshift.cluster_type"] = config.cluster_type
    if config.cluster_identifier is not None:
        kwargs["redshift.cluster_identifier"] = config.cluster_identifier
    if config.workgroup_name is not None:
        kwargs["redshift.workgroup_name"] = config.workgroup_name
    if config.aws_region is not None:
        kwargs["aws_region"] = config.aws_region
    if config.aws_access_key_id is not None:
        kwargs["aws_access_key_id"] = config.aws_access_key_id
    if config.aws_secret_access_key is not None:
        kwargs["aws_secret_access_key"] = config.aws_secret_access_key.get_secret_value()

    return kwargs


def _has_connection_fields(config: RedshiftConfig) -> bool:
    """Return True if any individual connection field is set."""
    return any([config.host, config.user, config.password, config.database, config.sslmode])


def _build_uri(config: RedshiftConfig) -> str:
    """Build a redshift:// URI from individual RedshiftConfig fields."""
    uri = "redshift://"

    if config.user is not None:
        uri += quote(config.user, safe="")
        if config.password is not None:
            uri += ":" + quote(config.password.get_secret_value(), safe="")
        uri += "@"

    if config.host is not None:
        uri += config.host

    if config.port is not None:
        uri += f":{config.port}"

    if config.database is not None:
        uri += f"/{config.database}"

    if config.sslmode is not None:
        uri += f"?sslmode={config.sslmode}"

    return uri
