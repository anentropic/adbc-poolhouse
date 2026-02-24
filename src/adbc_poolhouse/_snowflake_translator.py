"""
Snowflake ADBC parameter translator.

Verified against installed adbc_driver_snowflake source. Key 'username' and
'password' are plain string keys, not prefixed with 'adbc.snowflake.sql.*'.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adbc_poolhouse._snowflake_config import SnowflakeConfig


def translate_snowflake(config: SnowflakeConfig) -> dict[str, str]:
    """
    Translate SnowflakeConfig to ADBC driver kwargs.

    Returns a dict[str, str] suitable for passing as db_kwargs to
    adbc_driver_manager.dbapi.connect(). All values are strings; None fields
    are omitted. Boolean fields are always included as 'true'/'false' strings.

    Key names verified against installed adbc_driver_snowflake DatabaseOptions
    and AuthType enums. 'username' and 'password' are plain string keys (not
    prefixed with 'adbc.snowflake.sql.*').
    """
    kwargs: dict[str, str] = {}

    # --- Identity (always include) ---
    kwargs["adbc.snowflake.sql.account"] = config.account

    # --- Auth (include only if not None) ---
    if config.user is not None:
        kwargs["username"] = config.user
    if config.password is not None:
        kwargs["password"] = config.password.get_secret_value()  # pragma: allowlist secret
    if config.auth_type is not None:
        kwargs["adbc.snowflake.sql.auth_type"] = config.auth_type

    # --- JWT / private key (include only if not None) ---
    if config.private_key_path is not None:
        kwargs["adbc.snowflake.sql.client_option.jwt_private_key"] = str(config.private_key_path)
    if config.private_key_pem is not None:
        kwargs["adbc.snowflake.sql.client_option.jwt_private_key_pkcs8_value"] = (
            config.private_key_pem.get_secret_value()  # pragma: allowlist secret
        )
    if config.private_key_passphrase is not None:
        kwargs["adbc.snowflake.sql.client_option.jwt_private_key_pkcs8_password"] = (
            config.private_key_passphrase.get_secret_value()  # pragma: allowlist secret
        )
    if config.jwt_expire_timeout is not None:
        kwargs["adbc.snowflake.sql.client_option.jwt_expire_timeout"] = config.jwt_expire_timeout

    # --- OAuth / Okta / WIF (include only if not None) ---
    if config.oauth_token is not None:
        kwargs["adbc.snowflake.sql.client_option.auth_token"] = (
            config.oauth_token.get_secret_value()  # pragma: allowlist secret
        )
    if config.okta_url is not None:
        kwargs["adbc.snowflake.sql.client_option.okta_url"] = config.okta_url
    if config.identity_provider is not None:
        kwargs["adbc.snowflake.sql.client_option.identity_provider"] = config.identity_provider

    # --- Session / scope (include only if not None) ---
    if config.database is not None:
        kwargs["adbc.snowflake.sql.db"] = config.database
    # CRITICAL: Python attribute is schema_ (trailing underscore); ADBC key has no underscore
    if config.schema_ is not None:
        kwargs["adbc.snowflake.sql.schema"] = config.schema_
    if config.warehouse is not None:
        kwargs["adbc.snowflake.sql.warehouse"] = config.warehouse
    if config.role is not None:
        kwargs["adbc.snowflake.sql.role"] = config.role
    if config.region is not None:
        kwargs["adbc.snowflake.sql.region"] = config.region

    # --- Connection (include only if not None) ---
    if config.host is not None:
        kwargs["adbc.snowflake.sql.uri.host"] = config.host
    if config.port is not None:
        kwargs["adbc.snowflake.sql.uri.port"] = str(config.port)
    if config.protocol is not None:
        kwargs["adbc.snowflake.sql.uri.protocol"] = config.protocol

    # --- Timeouts (include only if not None) ---
    if config.login_timeout is not None:
        kwargs["adbc.snowflake.sql.client_option.login_timeout"] = config.login_timeout
    if config.request_timeout is not None:
        kwargs["adbc.snowflake.sql.client_option.request_timeout"] = config.request_timeout
    if config.client_timeout is not None:
        kwargs["adbc.snowflake.sql.client_option.client_timeout"] = config.client_timeout

    # --- Boolean flags (always include — fields have explicit defaults in SnowflakeConfig) ---
    # bool -> str(val).lower() produces 'true' or 'false'
    kwargs["adbc.snowflake.sql.client_option.tls_skip_verify"] = str(config.tls_skip_verify).lower()
    kwargs["adbc.snowflake.sql.client_option.ocsp_fail_open_mode"] = str(
        config.ocsp_fail_open_mode
    ).lower()
    kwargs["adbc.snowflake.sql.client_option.keep_session_alive"] = str(
        config.keep_session_alive
    ).lower()
    kwargs["adbc.snowflake.sql.client_option.disable_telemetry"] = str(
        config.disable_telemetry
    ).lower()
    kwargs["adbc.snowflake.sql.client_option.cache_mfa_token"] = str(config.cache_mfa_token).lower()
    kwargs["adbc.snowflake.sql.client_option.store_temp_creds"] = str(
        config.store_temp_creds
    ).lower()

    # --- Misc (include only if not None) ---
    if config.app_name is not None:
        kwargs["adbc.snowflake.sql.client_option.app_name"] = config.app_name

    return kwargs
